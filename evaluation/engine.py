"""Schritt 3: EnrichedLead -> EvaluatedLead. Die Rechenlogik liegt in scoring/, hier nur die Übersetzung.

Regeln der Übersetzung:
- Felder aus Schritt 1 (Name, Beschreibung, Gründer, Gründungsdatum) gelten als durch `source_url` belegt.
- Felder aus Schritt 2 zählen nur, wenn ein Evidence-Eintrag mit passendem `field` existiert.
- Freitext wird nur bei exakter Übereinstimmung mit einem bekannten Wert übersetzt, sonst bleibt das Kriterium neutral.
- EnrichedLead kennt weder Rechtsform, Papers, Förderung, IP noch Marktvolumen. Diese Kriterien bleiben neutral.
"""
from datetime import date

from models import EnrichedLead, EvaluatedLead, Industry
from scoring import load_config, score_dossier

BRANCHE = {Industry.AI: "digital_tech", Industry.FINTECH: "digital_tech", Industry.CLIMATE: "climate_tech",
           Industry.HEALTH: "life_sciences", Industry.INDUSTRIAL: "industrial_deep_tech"}
STAGE = {"pre_gruendung": "Pre-Seed", "in_gruendung": "Pre-Seed", "pre_seed": "Pre-Seed", "seed": "Seed", "zu_spaet": "Early Growth"}
REIFE = {"idee": "idee", "konzept": "idee", "paper": "paper", "forschung": "paper", "laborprototyp": "labor_prototyp",
         "labor-prototyp": "labor_prototyp", "prototyp": "prototyp", "mvp": "prototyp", "pilot": "pilot", "pilotkunden": "pilot",
         "pilotphase": "pilot", "erste kunden": "erste_kunden", "marktstart": "erste_kunden", "umsatz": "erste_kunden"}
SPAETE_RUNDEN = {"series a", "series b", "series c", "series d", "growth", "late stage"}
_CONFIG = None


def to_dossier(lead: EnrichedLead, cfg: dict) -> dict:
    by_field = {e.field: e for e in lead.evidence if e.field}
    quelle = str(lead.source_url)

    def src(*fields):
        return next((str(by_field[f].url) for f in fields if f in by_field), None)

    reife = REIFE.get((lead.product_stage or "").strip().lower())
    if lead.founded_on and src("founded_on"):        # Schritt-2-Feld: nur mit eigenem Evidence-Eintrag
        gruendung = {"wert": lead.founded_on.isoformat(), "quelle": src("founded_on")}
    elif lead.founding_year:                           # Schritt-1-Feld: belegt durch source_url; ohne Monat nur das Jahr
        wert = "%d-%02d" % (lead.founding_year, lead.founding_month) if lead.founding_month else str(lead.founding_year)
        gruendung = {"wert": wert, "quelle": quelle}
    else:
        gruendung = None
    if (lead.funding_stage or "").strip().lower() in SPAETE_RUNDEN and src("funding_stage"):
        funding = {"wert": True, "quelle": src("funding_stage")}
    elif (lead.funding_total_eur or 0) >= cfg["adapter_zu_spaet_ab_funding_eur"] and src("funding_total_eur"):
        funding = {"wert": True, "quelle": src("funding_total_eur")}
    else:
        funding = None
    ce = lead.country_evidence
    return {
        "lead_id": lead.id,
        "name_unternehmen": {"wert": lead.name, "quelle": quelle},
        "beschreibung_rohtext": {"wert": lead.description, "quelle": quelle},
        "deutschland_beleg": {"wert": ce.finding, "quelle": str(ce.url)} if ce else None,
        "website": str(lead.website) if lead.website else None,
        "branche": BRANCHE[lead.industry],
        "team": [{"name": n, "rolle": "Gründer", "quelle": quelle} for n in lead.founders],
        "reifegrad": {"wert": reife, "quelle": src("product_stage")} if reife else None,
        "gruendungsdatum": gruendung,
        "funding_meldung": funding,
        "partner": [{"name": "%d Kunden" % lead.customer_count, "typ": "kunde", "quelle": src("customer_count")}] if lead.customer_count else None,
        # Evidence kennt nur das Abrufdatum. Es dient hier allein dazu, die Quellen zu zählen; kein Datum davon wird ausgegeben.
        "signals": [{"typ": e.field or "kontext", "url": str(e.url), "datum": e.retrieved_at.date().isoformat()} for e in lead.evidence],
        "source_url": quelle,
    }


def evaluate(lead: EnrichedLead) -> EvaluatedLead:
    """Evaluate researched evidence; preserve enriched fields."""
    global _CONFIG
    _CONFIG = _CONFIG or load_config()
    r = score_dossier(to_dossier(lead, _CONFIG), _CONFIG, date.today())
    belege = [e for e in r["evidence"] if e["url"] and e["dimension"] in ("team", "marktpotenzial", "risiko")]
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
        open_questions=r["offene_punkte"],
    )
