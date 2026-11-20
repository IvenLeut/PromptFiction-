"""Schritt 3: Bewertung. Die Rechenlogik liegt in scoring/, hier nur die Übersetzung.

Schnittstelle (Toms Vertrag, SCORING_HANDOFF.md): `evaluate(ScoringInput) -> EvaluationScores`.
Die Pipeline reicht zusätzlich das Dossier als `lead=` durch, weil der ScoringInput keine Gründerprofile,
Förderbeträge, Rechtsform, Partner oder Patente enthält. Ohne `lead` wird nur der ScoringInput bewertet.
Gilt ein Parameter im ScoringInput als `usable`, hat er Vorrang vor dem gleichbedeutenden Dossierfeld.

Regeln der Übersetzung:
- Felder aus Schritt 1 (Name, Beschreibung, Gründer, Gründungsdatum) gelten als durch `source_url` belegt.
- Felder aus Schritt 2 zählen nur mit einem Evidence-Eintrag gleichen `field`-Namens (seine URL wird die Quelle);
  Listeneinträge (`grants`, `partners`, `patents`, `founder_profiles`) tragen ihre URL selbst.
- Freitext wird nur bei exakter Übereinstimmung mit einem bekannten Wert übersetzt, sonst bleibt das Kriterium neutral.
"""
from datetime import date

from models import EnrichedLead, EvaluatedLead, EvaluationScores, Industry
from scoring import load_config, score_dossier
from scoring_models import ScoringInput
from scoring_input import source_binding

BRANCHE = {Industry.AI: "digital_tech", Industry.FINTECH: "digital_tech", Industry.CLIMATE: "climate_tech",
           Industry.HEALTH: "life_sciences", Industry.INDUSTRIAL: "industrial_deep_tech"}
STAGE = {"pre_gruendung": "Pre-Seed", "in_gruendung": "Pre-Seed", "pre_seed": "Pre-Seed", "seed": "Seed", "zu_spaet": "Early Growth"}
REIFE = {"idee": "idee", "konzept": "idee", "paper": "paper", "forschung": "paper", "laborprototyp": "labor_prototyp",
         "labor_prototyp": "labor_prototyp", "labor-prototyp": "labor_prototyp", "prototyp": "prototyp", "mvp": "prototyp",
         "pilot": "pilot", "pilotkunden": "pilot", "pilotphase": "pilot", "erste kunden": "erste_kunden", "erste_kunden": "erste_kunden",
         "marktstart": "erste_kunden", "am_markt": "erste_kunden", "umsatz": "erste_kunden"}
SPAETE_RUNDEN = {"series a", "series b", "series c", "series d", "growth", "late stage"}
_CONFIG = None


def _sourced(value, url):
    return {"wert": value, "quelle": url} if value is not None and url else None


def to_dossier(lead: EnrichedLead, cfg: dict, *, as_of: date | None = None) -> dict:
    by_field = {}
    snapshots = lead.scoring_sources if lead.scoring_sources is not None else lead.signals

    def available(item):
        documented = item.document_date or item.source_date
        if as_of is not None and documented is not None and documented > as_of:
            return False
        quote = " ".join(item.finding.split())
        origins = [signal for signal in snapshots if signal.url == item.url
                   and quote in " ".join(signal.evidence.split())]
        return not origins or any(
            source_binding(lead, signal) is not False
            and (as_of is None or signal.date is None or signal.date <= as_of)
            for signal in origins
        )

    for e in lead.evidence:
        if e.field and available(e) and (lead.is_demo or e.verification_status != "assumption"):
            by_field.setdefault(e.field, e)

    def available_on(url, fields, anchor=None):
        entries = [item for item in lead.evidence if item.url == url and item.field in fields]
        if anchor:
            specific = [item for item in entries if anchor.casefold() in item.finding.casefold()]
            entries = specific or entries
        return not entries or any(available(item) and (lead.is_demo or item.verification_status != "assumption")
                                  for item in entries)
    quelle = str(lead.source_url)

    def src(*fields):
        return next((str(by_field[f].url) for f in fields if f in by_field), None)

    def src_rule(field):
        """Source only if the value came from a rule, not from a model quote (those are verbatim but often off-topic)."""
        e = by_field.get(field)
        return str(e.url) if e and not e.source.startswith("Ollama-Zitat") else None

    reife = REIFE.get((lead.product_stage or "").strip().lower())
    if lead.founded_on and src("founded_on", "company.founding_date"):
        gruendung = {"wert": lead.founded_on.isoformat(), "quelle": src("founded_on", "company.founding_date")}
    elif lead.founding_year:
        wert = str(lead.founding_year)
        if lead.founding_month is not None:
            wert += f"-{lead.founding_month:02d}"
        if lead.founded_day is not None:
            wert += f"-{lead.founded_day:02d}"
        gruendung = {"wert": wert, "quelle": src("founding_month", "founding_year") or quelle}
    elif lead.founding_year_hint and src("founding_year_mention"):
        gruendung = {"wert": str(lead.founding_year_hint), "quelle": src("founding_year_mention")}
    else:
        gruendung = None
    if (lead.funding_stage or "").strip().lower() in SPAETE_RUNDEN and src("funding_stage"):
        funding = {"wert": True, "quelle": src("funding_stage")}
    elif (lead.funding_total_eur or 0) >= cfg["adapter_zu_spaet_ab_funding_eur"] and src("funding_total_eur"):
        funding = {"wert": True, "quelle": src("funding_total_eur")}
    elif lead.vc_status == "confirmed" and src("vc_status"):
        funding = {"wert": True, "quelle": src("vc_status")}
    else:
        funding = None

    rechtsform = None
    if lead.legal_form and src("legal_form"):
        rechtsform = {"wert": lead.legal_form + (" i.G." if lead.in_formation else ""), "quelle": src("legal_form")}

    team = []
    for p in lead.founder_profiles:
        if p.source_url and not available_on(p.source_url, {"founder_profiles"}, p.name):
            continue
        url = str(p.source_url) if p.source_url else src("founder_profiles") or quelle
        team.append({"name": p.name, "rolle": p.role or "Gründer", "institut": p.institution, "quelle": url,
                     "openalex": str(p.openalex_url) if p.openalex_url else None, "papers_im_feld": p.works_in_field,
                     "hintergrund": p.background, "vorerfahrung": list(p.prior_experience)})
    for name in lead.founders:
        if name not in {t["name"] for t in team}:
            team.append({"name": name, "rolle": "Gründer", "quelle": quelle})

    partner = [{"name": x.name, "typ": x.kind, "quelle": str(x.url)} for x in lead.partners
               if available_on(x.url, {"partners"}, x.quote or x.name)]
    if lead.customer_count and src("customer_count"):
        partner.append({"name": "%d Kunden" % lead.customer_count, "typ": "kunde", "quelle": src("customer_count")})
    ip = None
    patents = [item for item in lead.patents if available_on(item.url, {"patents", "ip_status"}, item.quote or item.title)]
    if patents:
        best = max(patents, key=lambda x: x.status == "patent_erteilt")
        ip = {"wert": best.status, "quelle": str(best.url)}
    elif lead.ip_status and src("ip_status"):
        ip = {"wert": lead.ip_status, "quelle": src("ip_status")}

    signals = [{"typ": signal.type, "url": str(signal.url), "datum": signal.date.isoformat() if signal.date else None}
               for signal in lead.signals if source_binding(lead, signal) is not False
               and (as_of is None or signal.date is None or signal.date <= as_of)]
    signals += [{"typ": e.field or "kontext", "url": str(e.url), "datum": e.source_date.isoformat()}
                for e in lead.evidence if e.source_date and available(e)
                and (lead.is_demo or e.verification_status != "assumption")]
    if lead.first_web_capture and src("first_web_capture"):
        signals.append({"typ": "wayback", "url": src("first_web_capture"), "datum": lead.first_web_capture.isoformat()})
    if lead.is_demo and not any(s["datum"] for s in signals) and lead.country_evidence:
        # Demo-Fixtures haben keine datierten Signale; nur dort gilt das Abrufdatum des Fundbelegs als Signaldatum.
        signals.append({"typ": "demo", "url": str(lead.country_evidence.url), "datum": lead.country_evidence.retrieved_at.date().isoformat()})
    ce = lead.country_evidence
    if ce and (not available(ce) or (ce.verification_status == "assumption" and not lead.is_demo)):
        ce = None
    return {
        "lead_id": lead.id,
        "name_unternehmen": {"wert": lead.name, "quelle": quelle},
        "beschreibung_rohtext": {"wert": lead.description, "quelle": quelle},
        "deutschland_beleg": {"wert": ce.finding, "quelle": str(ce.url)} if ce else None,
        "website": str(lead.website) if lead.website else None,
        "email": _sourced(lead.contact_email, quelle) or _sourced(lead.imprint_email, src("contact_email")),
        "branche": lead.htgf_sector or BRANCHE[lead.industry],
        "rechtsform": rechtsform,
        "gruendungsdatum": gruendung,
        "team": team,
        "reifegrad": _sourced(reife, src("product_stage")) if reife else None,
        "produkt_typ": _sourced(lead.product_type, src("product_type")),
        "regulierter_markt": _sourced(lead.regulated_market, src("regulated_market")),
        "ip": ip,
        "markt": {"zielkunde": _sourced(lead.target_customers, src_rule("target_customers")),
                  "modell": _sourced(lead.business_model, src("business_model")),
                  "volumen_eur": _sourced(lead.market_size_eur, src("market_size_eur"))},
        "partner": partner,
        "wettbewerber": [{"name": c, "quelle": src("competitors")} for c in lead.competitors if src("competitors")],
        "foerderung": [{"programm": g.programme, "summe_eur": g.amount_eur, "start": g.start.isoformat() if g.start else None,
                        "ende": g.end.isoformat() if g.end else None, "quelle": str(g.url)} for g in lead.grants
                       if available_on(g.url, {"grants"}, g.reference)],
        "funding_meldung": funding,
        "in_databases": lead.in_databases if src("in_databases") or lead.in_databases is None else None,
        "in_databases_quelle": src("in_databases"),
        "first_db_date": lead.first_db_date.isoformat() if lead.first_db_date and src("first_db_date") else None,
        "match_confidence": lead.match_confidence,
        "signals": signals,
        "source_url": quelle,
    }


STAGE_EN = {"idea": "idee", "paper": "paper", "lab_prototype": "labor_prototyp", "prototype": "prototyp", "mvp": "prototyp",
            "pilot": "pilot", "first_customers": "erste_kunden", "commercial": "erste_kunden"}


def _evidence_url(scoring: ScoringInput, parameter):
    return next((str(scoring.evidence[k].url) for k in parameter.evidence_ids if k in scoring.evidence), None)


def apply_scoring_input(dossier: dict, scoring: ScoringInput) -> dict:
    """Overlay the usable, frozen parameters of Tom's ScoringInput onto the scorer dossier."""
    def usable(p):
        return p.status == "usable" and p.value is not None and _evidence_url(scoring, p)

    for field, parameter in (("gruendungsdatum", scoring.founded), ("reifegrad", scoring.product_stage),
                             ("funding_meldung", scoring.vc_status)):
        if parameter.status in {"ambiguous", "conflicting"}:
            dossier.pop(field, None)
    if scoring.country.status != "usable":
        dossier.pop("deutschland_beleg", None)

    if usable(scoring.founded):
        f = scoring.founded.value
        wert = "-".join(["%04d" % f.year] + ["%02d" % x for x in (f.month, f.day) if x is not None])
        dossier["gruendungsdatum"] = {"wert": wert, "quelle": _evidence_url(scoring, scoring.founded)}
    if usable(scoring.product_stage) and scoring.product_stage.value in STAGE_EN:
        dossier["reifegrad"] = {"wert": STAGE_EN[scoring.product_stage.value], "quelle": _evidence_url(scoring, scoring.product_stage)}
    late = [r for r in scoring.completed_rounds if usable(r) and r.value in {"series_a", "series_b", "series_c"}]
    if late or (usable(scoring.vc_status) and scoring.vc_status.value == "confirmed"):
        src = _evidence_url(scoring, late[0] if late else scoring.vc_status)
        dossier["funding_meldung"] = {"wert": True, "quelle": src}
    for p in scoring.annual_paying_customer_count:
        if usable(p) and p.value:
            dossier.setdefault("partner", []).append({"name": "%d zahlende Kunden" % p.value, "typ": "kunde",
                                                       "quelle": _evidence_url(scoring, p)})
            break
    if usable(scoring.tam):
        dossier.setdefault("markt", {})["volumen_eur"] = {"wert": float(scoring.tam.value), "quelle": _evidence_url(scoring, scoring.tam)}
    return dossier


def _dossier_from_scoring(scoring: ScoringInput) -> dict:
    """Minimal dossier when only the ScoringInput is available (no lead passed)."""
    urls = [str(e.url) for e in scoring.evidence.values()]
    signals = [{"typ": e.kind, "url": str(e.url), "datum": e.document_date.isoformat() if e.document_date else None}
               for e in scoring.evidence.values() if e.kind != "unbound_excerpt"]
    country_url = _evidence_url(scoring, scoring.country) if scoring.country.status == "usable" else None
    return {"lead_id": scoring.lead_id, "name_unternehmen": {"wert": scoring.lead_id, "quelle": urls[0] if urls else None},
            "beschreibung_rohtext": {"wert": scoring.lead_id, "quelle": urls[0] if urls else None},
            "deutschland_beleg": {"wert": "DE", "quelle": country_url} if country_url else None,
            "signals": signals, "source_url": urls[0] if urls else None}


def score_lead(scoring: ScoringInput | None, *, lead: EnrichedLead | None = None,
               cfg: dict | None = None) -> dict:
    global _CONFIG
    if cfg is None:
        _CONFIG = _CONFIG or load_config()
        cfg = _CONFIG
    if lead is not None and scoring is not None and lead.id != scoring.lead_id:
        raise ValueError("ScoringInput und Dossier gehören zu verschiedenen Leads.")
    stichtag = scoring.as_of if scoring is not None else None
    stichtag = stichtag or date.today()
    dossier = to_dossier(lead, cfg, as_of=stichtag) if lead is not None else _dossier_from_scoring(scoring)
    if scoring is not None:
        dossier = apply_scoring_input(dossier, scoring)
    return score_dossier(dossier, cfg, stichtag)


def _scores(r: dict, lead: EnrichedLead | None) -> dict:
    belege = [e for e in r["evidence"] if e["url"] and e["dimension"] in ("team", "marktpotenzial", "risiko")]
    fragen = list(dict.fromkeys((list(lead.research_questions) if lead else []) + r["offene_punkte"]))
    beschreibung = (lead.description or lead.name) if lead else r["lead_id"]
    return dict(
        evaluation_v2=r,
        overall_score=r["gesamt_score"], company_score=r["team_score"],
        market_potential_score=r["marktpotenzial_score"], risk_score=r["risiko_score"],
        stage_classification=STAGE.get(r["stage"], "Unbekannt"),
        value_proposition=r["value_proposition"] or beschreibung,
        investment_thesis=r["investmenthypothese"] or "Nicht bewertet. %s." % r["ausschluss_grund"],
        confidence_score=round(r["confidence"] * 100, 1),
        earliness_delta_months=r["earliness_delta_monate"],
        scoring_status=r["status"],
        score_drivers=["%s (Quelle: %s)" % (e["aussage"], e["url"]) for e in belege if e["dimension"] != "risiko"],
        risks=["%s (Quelle: %s)" % (e["aussage"], e["url"]) for e in belege if e["dimension"] == "risiko"]
              + (["Ausschluss: " + r["ausschluss_grund"]] if r["ausschluss_grund"] else []),
        open_questions=fragen,
    )


def evaluate(scoring: ScoringInput | EnrichedLead, *, lead: EnrichedLead | None = None):
    """Live scoring.

    - `evaluate(ScoringInput, lead=EnrichedLead) -> EvaluationScores`: the pipeline path (Tom's handoff plus dossier).
    - `evaluate(ScoringInput) -> EvaluationScores`: frozen handoff only.
    - `evaluate(EnrichedLead) -> EvaluatedLead`: direct call with a dossier (kept for tests and scripts).
    """
    if isinstance(scoring, EnrichedLead):
        dossier_lead = scoring
        r = score_lead(dossier_lead.scoring_input, lead=dossier_lead)
        return EvaluatedLead(**dossier_lead.model_dump(), **_scores(r, dossier_lead))
    r = score_lead(scoring, lead=lead)
    return EvaluationScores(**_scores(r, lead))
