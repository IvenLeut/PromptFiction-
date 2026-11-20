"""Schritt 3: EnrichedLead -> EvaluatedLead. Die Rechenlogik liegt in scoring/, hier nur die Übersetzung.

Regeln der Übersetzung:
- Felder aus Schritt 1 (Name, Beschreibung, Gründer, Gründungsdatum) gelten als durch `source_url` belegt.
- Felder aus Schritt 2 zählen nur mit einem Evidence-Eintrag gleichen `field`-Namens (seine URL wird die Quelle);
  Listeneinträge (`grants`, `partners`, `patents`, `founder_profiles`) tragen ihre URL selbst.
- Freitext wird nur bei exakter Übereinstimmung mit einem bekannten Wert übersetzt, sonst bleibt das Kriterium neutral.
"""
from datetime import date

from models import EnrichedLead, EvaluatedLead, Industry
from scoring import load_config, score_dossier

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


def to_dossier(lead: EnrichedLead, cfg: dict) -> dict:
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
        url = str(p.source_url) if p.source_url else src("founder_profiles") or quelle
        team.append({"name": p.name, "rolle": p.role or "Gründer", "institut": p.institution, "quelle": url,
                     "openalex": str(p.openalex_url) if p.openalex_url else None, "papers_im_feld": p.works_in_field,
                     "hintergrund": p.background, "vorerfahrung": list(p.prior_experience)})
    for name in lead.founders:
        if name not in {t["name"] for t in team}:
            team.append({"name": name, "rolle": "Gründer", "quelle": quelle})

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
    signals += [{"typ": e.field or "kontext", "url": str(e.url), "datum": e.source_date.isoformat()}
                for e in lead.evidence if e.source_date]
    if lead.first_web_capture and src("first_web_capture"):
        signals.append({"typ": "wayback", "url": src("first_web_capture"), "datum": lead.first_web_capture.isoformat()})
    if lead.is_demo and not any(s["datum"] for s in signals) and lead.country_evidence:
        # Demo-Fixtures haben keine datierten Signale; nur dort gilt das Abrufdatum des Fundbelegs als Signaldatum.
        signals.append({"typ": "demo", "url": str(lead.country_evidence.url), "datum": lead.country_evidence.retrieved_at.date().isoformat()})
    ce = lead.country_evidence
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
                        "ende": g.end.isoformat() if g.end else None, "quelle": str(g.url)} for g in lead.grants],
        "funding_meldung": funding,
        "in_databases": lead.in_databases if src("in_databases") or lead.in_databases is None else None,
        "in_databases_quelle": src("in_databases"),
        "first_db_date": lead.first_db_date.isoformat() if lead.first_db_date and src("first_db_date") else None,
        "match_confidence": lead.match_confidence,
        "signals": signals,
        "source_url": quelle,
    }


def evaluate(lead: EnrichedLead) -> EvaluatedLead:
    """Evaluate researched evidence; preserve enriched fields."""
    global _CONFIG
    _CONFIG = _CONFIG or load_config()
    r = score_dossier(to_dossier(lead, _CONFIG), _CONFIG, date.today())
    belege = [e for e in r["evidence"] if e["url"] and e["dimension"] in ("team", "marktpotenzial", "risiko")]
    fragen = list(dict.fromkeys(list(lead.research_questions) + r["offene_punkte"]))
    return EvaluatedLead(
        **lead.model_dump(),
        overall_score=r["gesamt_score"], company_score=r["team_score"],
        market_potential_score=r["marktpotenzial_score"], risk_score=r["risiko_score"],
        stage_classification=STAGE.get(r["stage"], "Unbekannt"),
        value_proposition=r["value_proposition"] or lead.description or lead.name,
        investment_thesis=r["investmenthypothese"] or "Nicht bewertet. %s." % r["ausschluss_grund"],
        confidence_score=round(r["confidence"] * 100, 1),
        score_drivers=["%s (Quelle: %s)" % (e["aussage"], e["url"]) for e in belege if e["dimension"] != "risiko"],
        risks=["%s (Quelle: %s)" % (e["aussage"], e["url"]) for e in belege if e["dimension"] == "risiko"]
              + (["Ausschluss: " + r["ausschluss_grund"]] if r["ausschluss_grund"] else []),
        open_questions=fragen,
    )
