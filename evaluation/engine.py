"""Schritt 3: Bewertung. Die Rechenlogik liegt in scoring/, hier nur die Übersetzung.

Schnittstelle (Vertrag aus Schritt 2, SCORING_HANDOFF.md): `evaluate(ScoringInput) -> EvaluationScores`.
Die Pipeline reicht zusätzlich das Dossier als `lead=` durch, weil der ScoringInput keine Gründerprofile,
Förderbeträge, Rechtsform, Partner oder Patente enthält. Ohne `lead` wird nur der ScoringInput bewertet.
Gilt ein Parameter im ScoringInput als `usable`, hat er Vorrang vor dem gleichbedeutenden Dossierfeld.
Stichtag: `as_of=`, sonst `ScoringInput.as_of`, sonst heute.

Regeln der Übersetzung:
- Felder aus Schritt 1 (Name, Beschreibung, Gründer, Gründungsdatum) gelten als durch `source_url` belegt.
- Felder aus Schritt 2 zählen nur mit einem Evidence-Eintrag gleichen `field`-Namens (seine URL wird die Quelle);
  Listeneinträge (`grants`, `partners`, `patents`, `founder_profiles`) tragen ihre URL selbst.
- Freitext wird nur bei exakter Übereinstimmung mit einem bekannten Wert übersetzt, sonst bleibt das Kriterium neutral.
"""
import re
from datetime import date

from models import EnrichedLead, EvaluatedLead, EvaluationScores, Industry
from pipeline import industry_unclassified
from scoring import load_config, score_dossier
from scoring_models import ScoringInput

BRANCHE = {Industry.AI: "digital_tech", Industry.FINTECH: "digital_tech", Industry.CLIMATE: "climate_tech",
           Industry.HEALTH: "life_sciences", Industry.INDUSTRIAL: "industrial_deep_tech"}
STAGE_LABEL = {"pre_gruendung": "Pre-Seed", "in_gruendung": "Pre-Seed", "pre_seed": "Pre-Seed", "seed": "Seed", "zu_spaet": "Early Growth"}
REIFE = {"idee": "idee", "konzept": "idee", "paper": "paper", "forschung": "paper", "laborprototyp": "labor_prototyp",
         "labor_prototyp": "labor_prototyp", "labor-prototyp": "labor_prototyp", "prototyp": "prototyp", "mvp": "prototyp",
         "pilot": "pilot", "pilotkunden": "pilot", "pilotphase": "pilot", "erste kunden": "erste_kunden", "erste_kunden": "erste_kunden",
         "marktstart": "erste_kunden", "am_markt": "erste_kunden", "umsatz": "erste_kunden"}
SPAETE_RUNDEN = {"series a", "series b", "series c", "series d", "growth", "late stage"}
# Evidence fields whose source_date is a real dated signal about this project. Everything else (database hits,
# first_db_date, idw mentions/round-ups, *_alt candidates, model quotes) is context, not a signal: a namesake
# Crunchbase capture or an unrelated press round-up must not become the "first signal" of a project.
SIGNAL_FIELDS = {"grants", "idw", "founding_year_mention", "first_web_capture"}
_CONFIG = None


def _config() -> dict:
    global _CONFIG
    _CONFIG = _CONFIG or load_config()
    return _CONFIG


def _sourced(value, url):
    return {"wert": value, "quelle": url} if value is not None and url else None


def _is_signal(e) -> bool:
    source = e.source or ""
    return (bool(e.source_date) and e.field in SIGNAL_FIELDS and not source.startswith("Ollama-Zitat")
            and "(Erwähnung)" not in source)  # "idw (Erwähnung)": name mention in a round-up, same as idw_mention


def _branche(lead: EnrichedLead) -> str | None:
    if lead.htgf_sector:
        return lead.htgf_sector
    return None if industry_unclassified(lead) else BRANCHE[lead.industry]


# Kein Personenname: Impressums-Überschriften und Ämter (Rektor einer Uni ist nicht Gründer).
_KEIN_NAME = re.compile(r"(?i)(?<!\w)(register|registergericht|vat|ust|id|development|product|commercial|gmbh|ug|ag|kg|e\.?v\.?|"
                        r"rector|rektor\w*|pr(ä|ae)sident\w*|kanzler\w*|dekan\w*|vorstand|impressum|kontakt|telefon|e-mail|"
                        r"amtsgericht|hrb|universit\w*|hochschule|institut\w*|team|management|sales|marketing)(?!\w)")


def _personenname(name: str) -> str | None:
    """Plausibler Personenname aus dem Impressum (2–5 Wörter, Großbuchstaben am Wortanfang), sonst None. Titel werden entfernt."""
    name = re.sub(r"(?i)\b(prof|dr|dipl|ing|med|rer|nat|habil|mba|msc|bsc)\.?(-\w+\.?)?\s*", "", (name or "").strip()).strip(" ,;")
    teile = name.split()
    if _KEIN_NAME.search(name) or not 2 <= len(teile) <= 5:
        return None
    if not all(re.fullmatch(r"[A-ZÄÖÜ][\w'’.-]*|von|van|de|der|zu|du|di|da|le|la", t) for t in teile):
        return None
    return name


def _namekey(name: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", name.lower())


def _katalog_zeile(lead: EnrichedLead, url: str, label: str) -> str | None:
    """'Label: Wert' aus einem Förderkatalog-Text (Signal oder Evidence) mit derselben URL."""
    texte = [s.evidence for s in lead.signals if str(s.url) == url] + [e.finding for e in lead.evidence if str(e.url) == url]
    for t in texte:
        m = re.search(r"%s:\s*([^\n;]+)" % re.escape(label), t or "")
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _grant(lead: EnrichedLead, g) -> dict:
    url = str(g.url)
    return {"programm": g.programme, "summe_eur": g.amount_eur, "start": g.start.isoformat() if g.start else None,
            "ende": g.end.isoformat() if g.end else None, "quelle": url, "kennzeichen": g.reference, "empfaenger": g.recipient,
            "ausfuehrende_stelle": _katalog_zeile(lead, url, "Ausführende Stelle"), "thema": _katalog_zeile(lead, url, "Thema")}


def to_dossier(lead: EnrichedLead, cfg: dict) -> dict:
    """EnrichedLead -> scorer dossier (the untyped contract with scoring/engine.py; field rules: scoring/SCORING.md).

    Facts are `{"wert", "quelle"}` (or None when unsourced); list entries carry their own `quelle`/`url`.

    | key | value | from |
    |---|---|---|
    | lead_id, source_url | str | `id`, `source_url` |
    | name_unternehmen, beschreibung_rohtext | fact | `name`, `description` (source: `source_url`) |
    | deutschland_beleg | fact | `country_evidence` |
    | website | str | `website`, else `matched_website` (context/website_match.py) |
    | email | fact | `contact_email` or `imprint_email` |
    | branche | str or None | `htgf_sector`, else `industry` unless unclassified |
    | rechtsform | fact | `legal_form` (+ " i.G." if `in_formation`) |
    | gruendungsdatum, gruendungsjahr_hinweis | fact | `founded_on`/`founding_year[_month]`, `founding_year_hint` |
    | team | [{name, rolle, institut, quelle, openalex, papers_im_feld, hintergrund, vorerfahrung}] | `founder_profiles`, `founders` |
    | reifegrad, produkt_typ, regulierter_markt, ip | fact | `product_stage` (via REIFE), `product_type`, `regulated_market`, `patents`/`ip_status` |
    | markt | {zielkunde, modell, volumen_eur: fact} | `target_customers`, `business_model`, `market_size_eur` |
    | partner | [{name, typ, quelle}] | `partners`, `customer_count` |
    | wettbewerber | [{name, quelle}] | `competitors` |
    | foerderung | [{programm, summe_eur, start, ende, quelle, kennzeichen, empfaenger, ausfuehrende_stelle, thema}] | `grants`; Stelle/Thema aus Signal-/Evidence-Text derselben URL |
    | website_text | fact | Evidence `website_text` (Website-Text, context/website_match) |
    | funding_meldung | fact(True) | late `funding_stage`, `funding_total_eur` ≥ config, confirmed `vc_status` |
    | in_databases, in_databases_quelle, first_db_date, match_confidence | sourcing metadata | same-named fields |
    | signals | [{typ, url, datum}] | `signals`, dated signal evidence, `first_web_capture` |

    scoring/engine.py ignores keys it does not know, so adding a key here is safe; renaming one is not.
    """
    by_field = {}
    for e in lead.evidence:
        if e.field:
            by_field.setdefault(e.field, e)
    quelle = str(lead.source_url)

    def src(*fields):
        return next((str(by_field[f].url) for f in fields if f in by_field), None)

    def src_rule(field):
        """Source only if the value came from a rule, not from a model quote (those are verbatim but often off-topic)."""
        e = by_field.get(field)
        return str(e.url) if e and not e.source.startswith("Ollama-Zitat") else None

    reife = REIFE.get((lead.product_stage or "").strip().lower())
    if lead.founded_on and src("founded_on"):
        gruendung = {"wert": lead.founded_on.isoformat(), "quelle": src("founded_on")}
    elif lead.founding_year:
        wert = "%d-%02d" % (lead.founding_year, lead.founding_month) if lead.founding_month else str(lead.founding_year)
        gruendung = {"wert": wert, "quelle": quelle}
    else:
        gruendung = None
    # A year from a press sentence is weaker than a register/imprint date: separate field, never an exclusion.
    hinweis = _sourced(lead.founding_year_hint, src("founding_year_mention")) if lead.founding_year_hint else None
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
        url = str(p.source_url) if p.source_url else src("founder_profiles") or quelle
        aus_impressum = "impressum" in (p.role or "").lower()  # context: role "Geschäftsführung (Impressum)"
        name = _personenname(p.name) if aus_impressum else p.name
        if not name or _namekey(name) in {_namekey(t["name"]) for t in team}:
            continue
        team.append({"name": name, "rolle": p.role or "Gründer", "institut": p.institution, "quelle": url,
                     "openalex": str(p.openalex_url) if p.openalex_url else None, "papers_im_feld": p.works_in_field,
                     "papers_gesamt": p.works_total, "match_confidence": p.match_confidence,
                     "hintergrund": p.background, "vorerfahrung": list(p.prior_experience)}
                    | ({"herkunft": "impressum"} if aus_impressum else {}))
    for name in lead.founders:
        if name not in {t["name"] for t in team}:
            team.append({"name": name, "rolle": "Gründer", "quelle": quelle})
    # Geschäftsführung aus dem Impressum (öffentliche Geschäftsdaten), wenn context kein Profil zu dieser Person hat.
    gf_url = src_rule("managing_directors") or (str(lead.imprint_url) if lead.imprint_url else None)
    for name in lead.managing_directors if gf_url else []:
        name = _personenname(name)
        if name and _namekey(name) not in {_namekey(t["name"]) for t in team}:
            team.append({"name": name, "rolle": "Geschäftsführung", "quelle": gf_url, "herkunft": "impressum"})

    partner = [{"name": x.name, "typ": x.kind, "quelle": str(x.url)} for x in lead.partners]
    if lead.customer_count and src("customer_count"):
        partner.append({"name": "%d Kunden" % lead.customer_count, "typ": "kunde", "quelle": src("customer_count")})
    ip = None
    if lead.patents:
        best = max(lead.patents, key=lambda x: x.status == "patent_erteilt")
        ip = {"wert": best.status, "quelle": str(best.url)}
    elif lead.ip_status and src("ip_status"):
        ip = {"wert": lead.ip_status, "quelle": src("ip_status")}

    signals = [{"typ": s.type, "url": str(s.url), "datum": s.date.isoformat() if s.date else None} for s in lead.signals]
    signals += [{"typ": "wayback" if e.field == "first_web_capture" else e.field, "url": str(e.url), "datum": e.source_date.isoformat()} for e in lead.evidence if _is_signal(e)]
    if lead.first_web_capture and src("first_web_capture"):
        signals.append({"typ": "wayback", "url": src("first_web_capture"), "datum": lead.first_web_capture.isoformat()})
    signals = [s for i, s in enumerate(signals) if (s["url"], s["datum"]) not in {(x["url"], x["datum"]) for x in signals[:i]}]
    if lead.is_demo and not any(s["datum"] for s in signals) and lead.country_evidence:
        # Demo-Fixtures haben keine datierten Signale; nur dort gilt das Abrufdatum des Fundbelegs als Signaldatum.
        signals.append({"typ": "demo", "url": str(lead.country_evidence.url), "datum": lead.country_evidence.retrieved_at.date().isoformat()})
    ce = lead.country_evidence
    return {
        "lead_id": lead.id,
        "name_unternehmen": {"wert": lead.name, "quelle": quelle},
        "beschreibung_rohtext": {"wert": lead.description, "quelle": quelle},
        "deutschland_beleg": {"wert": ce.finding, "quelle": str(ce.url)} if ce else None,
        "website": str(lead.website or lead.matched_website) if (lead.website or lead.matched_website) else None,
        "email": _sourced(lead.contact_email, quelle) or _sourced(lead.imprint_email, src("contact_email")),
        "branche": _branche(lead),
        "rechtsform": rechtsform,
        "gruendungsdatum": gruendung,
        "gruendungsjahr_hinweis": hinweis,
        "team": team,
        "reifegrad": _sourced(reife, src("product_stage")) if reife else None,
        # alle Fundstellen der Reifegrad-Klassifikation (ohne Modellzitate): seed braucht zwei unabhängige Domains
        "reifegrad_quellen": sorted({str(e.url) for e in lead.evidence if e.field == "product_stage"
                                     and not e.source.startswith("Ollama-Zitat")}) if reife else None,
        "produkt_typ": _sourced(lead.product_type, src("product_type")),
        "regulierter_markt": _sourced(lead.regulated_market, src("regulated_market")),
        "ip": ip,
        "markt": {"zielkunde": _sourced(lead.target_customers, src_rule("target_customers")),
                  "modell": _sourced(lead.business_model, src("business_model")),
                  "volumen_eur": _sourced(lead.market_size_eur, src("market_size_eur"))},
        "partner": partner,
        "wettbewerber": [{"name": c, "quelle": src("competitors")} for c in lead.competitors if src("competitors")],
        "foerderung": [_grant(lead, g) for g in lead.grants],
        "website_text": ({"wert": by_field["website_text"].finding, "quelle": str(by_field["website_text"].url)}
                         if "website_text" in by_field and not by_field["website_text"].source.startswith("Ollama-Zitat") else None),
        "funding_meldung": funding,
        "in_databases": lead.in_databases if src("in_databases") or lead.in_databases is None else None,
        "in_databases_quelle": src("in_databases"),
        "first_db_date": lead.first_db_date.isoformat() if lead.first_db_date and src("first_db_date") else None,
        "match_confidence": lead.match_confidence,
        "signals": signals,
        "source_url": quelle,
    }


REIFE_AUS_EN = {"idea": "idee", "paper": "paper", "lab_prototype": "labor_prototyp", "prototype": "prototyp", "mvp": "prototyp",
            "pilot": "pilot", "first_customers": "erste_kunden", "commercial": "erste_kunden"}


def _evidence_url(scoring: ScoringInput, parameter):
    return next((str(scoring.evidence[k].url) for k in parameter.evidence_ids if k in scoring.evidence), None)


def apply_scoring_input(dossier: dict, scoring: ScoringInput) -> dict:
    """Overlay the usable, frozen parameters of the step-2 ScoringInput onto the scorer dossier.

    `public_grant` is deliberately not mapped: it only says *that* a grant exists, while `foerderung` comes from
    `lead.grants` (programme, amount, term per Förderkatalog row). Mapping it would add a second entry for the same grant.
    """
    def usable(p):
        return p.status == "usable" and p.value is not None and _evidence_url(scoring, p)

    if usable(scoring.founded):
        f = scoring.founded.value
        wert = "-".join(["%04d" % f.year] + ["%02d" % x for x in (f.month, f.day) if x is not None])
        dossier["gruendungsdatum"] = {"wert": wert, "quelle": _evidence_url(scoring, scoring.founded)}
    if usable(scoring.product_stage) and scoring.product_stage.value in REIFE_AUS_EN:
        dossier["reifegrad"] = {"wert": REIFE_AUS_EN[scoring.product_stage.value], "quelle": _evidence_url(scoring, scoring.product_stage)}
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
               for e in scoring.evidence.values()]
    country_url = _evidence_url(scoring, scoring.country) if scoring.country.status == "usable" else None
    return {"lead_id": scoring.lead_id, "name_unternehmen": {"wert": scoring.lead_id, "quelle": urls[0] if urls else None},
            "beschreibung_rohtext": {"wert": scoring.lead_id, "quelle": urls[0] if urls else None},
            "deutschland_beleg": {"wert": "DE", "quelle": country_url} if country_url else None,
            "signals": signals, "source_url": urls[0] if urls else None}


def _score_record(lead: EnrichedLead | None, scoring: ScoringInput | None, as_of: date | None) -> dict:
    cfg = _config()
    dossier = to_dossier(lead, cfg) if lead is not None else _dossier_from_scoring(scoring)
    if scoring is not None:
        dossier = apply_scoring_input(dossier, scoring)
    stichtag = as_of or (scoring.as_of if scoring is not None else None) or date.today()
    return score_dossier(dossier, cfg, stichtag)


def _is_risk(e: dict) -> bool:
    return e["dimension"] == "risiko" and e["punkte"] is not None and e["punkte"] >= _config()["texte"]["risiko_ab"] * 100


def _driver(e: dict) -> str:
    text = ("Risikomindernd: " if e["dimension"] == "risiko" else "") + e["aussage"]
    return "%s (Quelle: %s)" % (text, e["url"])


def _scores(r: dict, lead: EnrichedLead | None) -> dict:
    """Score record (scoring/scores.schema.json) -> EvaluationScores fields."""
    belege = [e for e in r["evidence"] if e["url"] and e["dimension"] in ("team", "marktpotenzial", "risiko")]
    fragen = list(dict.fromkeys((list(lead.research_questions) if lead else []) + r["offene_punkte"]))
    beschreibung = (lead.description or lead.name) if lead else r["lead_id"]
    return dict(
        overall_score=r["gesamt_score"], company_score=r["team_score"],
        market_potential_score=r["marktpotenzial_score"], risk_score=r["risiko_score"],
        stage_classification=STAGE_LABEL.get(r["stage"], "Unbekannt"),
        value_proposition=r["value_proposition"] or beschreibung,
        investment_thesis=r["investmenthypothese"] or "Nicht bewertet. %s." % r["ausschluss_grund"],
        confidence_score=round(r["confidence"] * 100, 1),
        # Only risk criteria at or above texte.risiko_ab are risks; lower ones reduce risk and count as drivers.
        score_drivers=[_driver(e) for e in belege if not _is_risk(e)],
        risks=["%s (Quelle: %s)" % (e["aussage"], e["url"]) for e in belege if _is_risk(e)]
              + (["Ausschluss: " + r["ausschluss_grund"]] if r["ausschluss_grund"] else []),
        open_questions=fragen,
    )


def evaluate(scoring: ScoringInput | EnrichedLead, *, lead: EnrichedLead | None = None, as_of: date | None = None):
    """Live scoring.

    - `evaluate(ScoringInput, lead=EnrichedLead) -> EvaluationScores`: the pipeline path (the step-2 handoff plus dossier).
    - `evaluate(ScoringInput) -> EvaluationScores`: frozen handoff only.
    - `evaluate(EnrichedLead) -> EvaluatedLead`: direct call with a dossier; its own `scoring_input` is overlaid if set.

    The admission gate (`scoring_input.admission_issue`: no usable DE evidence, VC confirmed or conflicting) is
    applied by `pipeline.evaluate_context` before this function, so such leads never arrive here on the
    pipeline path. Called directly, a lead with a confirmed VC status is not rejected but scored as
    "zu_spaet" (`funding_meldung`): no overall score, stage "Early Growth", the reason in `risks`.
    """
    if isinstance(scoring, EnrichedLead):
        lead, scoring, as_lead = scoring, scoring.scoring_input, True
    else:
        as_lead = False
    fields = _scores(_score_record(lead, scoring, as_of), lead)
    return EvaluatedLead(**lead.model_dump(), **fields) if as_lead else EvaluationScores(**fields)
