"""Lossless boundary for scoring exports, AnalysisRun and future v2 extensions.

This module never calls an engine or calculates an investment score.
"""
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import calendar
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

CONFIG = json.loads((Path(__file__).parent / "config/htgf.v1.json").read_text(encoding="utf-8"))
SECTORS = {"digital_tech": "Digital Tech", "AI / Software": "Digital Tech", "FinTech": "Digital Tech",
           "industrial_deep_tech": "Industrial / DeepTech", "climate_tech": "ClimateTech",
           "life_sciences": "Life Sciences", "HealthTech": "Life Sciences", "chemie_materialien": "Chemistry"}
STAGES = {"pre_gruendung": "Pre-incorporation", "in_gruendung": "In formation",
          "pre_seed": "Pre-Seed", "seed": "Seed", "zu_spaet": "Outside sourcing scope"}


def number(value, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 and (maximum is None or value <= maximum) else None


def url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        return value if parts.scheme in {"https", "http"} and parts.hostname and not parts.username else None
    except ValueError:
        return None


def is_example(value):
    host = urlsplit(url(value) or "").hostname or ""
    return any(host == domain or host.endswith("." + domain) for domain in ("example.org", "example.com", "example.net"))


def items(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def known(value):
    return value is not None and value != "" and value != [] and value != {} and str(value).lower() not in {"unknown", "unbekannt"}


@dataclass
class Lead:
    id: str
    name: str
    sector: str
    stage: str
    data: dict
    raw: dict
    evidence: list[dict]
    scores: dict
    confidence: float | None
    demo: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def namespace(self):
        return "demo" if self.demo else "live"

    @property
    def excluded(self):
        return bool(self.data.get("hard_exclusions") or self.data.get("ausschluss_grund")
                    or self.data.get("eligibility_status") == "Excluded"
                    or self.data.get("noise_class") not in (None, "", "vc_potenzial"))

    @property
    def sources(self):
        return {e["url"] for e in self.evidence if e["url"]}

    @property
    def recommendation(self):
        # Only supplied recommendations; pipeline status is never an analyst decision.
        return self.data.get("machine_recommendation") or ("Excluded by sourcing" if self.excluded else "Not supplied")


def adapt(record):
    if not isinstance(record, dict):
        raise ValueError("Each lead must be a JSON object.")
    data = dict(record)
    for extension in ("context_v2", "evaluation_v2"):
        if isinstance(record.get(extension), dict):
            data.update(record[extension])
            for canonical, legacy_key in {"overall_score": "gesamt_score", "market_potential_score": "marktpotenzial_score", "risk_score": "risiko_score",
                                          "investment_thesis": "investmenthypothese", "why_contact_now": "why_now"}.items():
                if canonical in record[extension]:
                    data[legacy_key] = record[extension][canonical]
    name = data.get("name_unternehmen") or data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A company name is required.")
    for key in ("teilwerte", "market_intelligence", "competitive_positioning", "sector_research"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            raise ValueError(f"{name}: {key} must be an object or null.")
    research = data.get("market_intelligence") or {}
    for key in ("sizing", "growth_series"):
        if research.get(key) is not None and not isinstance(research[key], list):
            raise ValueError(f"{name}: market_intelligence.{key} must be an array.")
    if any(not isinstance(group, dict) for group in (data.get("teilwerte") or {}).values()):
        raise ValueError(f"{name}: score dimensions must contain criteria objects.")
    identity = str(data.get("lead_id") or data.get("id") or sha256(
        (name.casefold() + "|" + str(data.get("website") or "")).encode()).hexdigest()[:20])
    evidence = []
    for entry in items(data.get("evidence")):
        if not isinstance(entry, dict):
            continue
        source = url(entry.get("url") or entry.get("quelle"))
        dimension = entry.get("dimension") or entry.get("field") or "other"
        category = {"team": "Team", "marktpotenzial": "Market", "risiko": "Risk", "stage": "Stage"}.get(dimension, "Other")
        if category == "Other":
            category = next((label for word, label in (("founder", "Team"), ("market", "Market"), ("risk", "Risk"), ("stage", "Stage")) if word in dimension), "Other")
        evidence.append({"category": category, "criterion": entry.get("kriterium") or entry.get("field") or dimension,
                         "statement": entry.get("aussage") or entry.get("finding") or "",
                         "url": source, "date": entry.get("datum") or entry.get("published_on") or entry.get("source_date"),
                         "retrieved_at": entry.get("retrieved_at"), "points": number(entry.get("punkte"), 100),
                         "verification": "Demo source" if is_example(source) else "Source supplied; not independently verified" if source else "No source / unassessed"})
    scores = {}
    warnings = []
    subvalues = data.get("teilwerte") or {}
    mapping = {"Quality": ("gesamt_score", "overall_score", None), "Market": ("marktpotenzial_score", "market_potential_score", "marktpotenzial"),
               "Team": ("team_score", "team_score", "team"), "Risk": ("risiko_score", "risk_score", "risiko"),
               "Earliness": ("earliness_score", "earliness_score", None)}
    legacy = "gesamt_score" in data
    for label, (old, new, dimension) in mapping.items():
        value = number(data.get(old) if old in data else data.get(new), 100)
        criteria = subvalues.get(dimension, {}) if dimension else {}
        has_evidence = any(e["url"] and e["category"] == label for e in evidence)
        if criteria and not any(c.get("belegt") for c in criteria.values() if isinstance(c, dict)):
            value = None
        elif legacy and value == 50 and dimension and not criteria and not has_evidence:
            value = None
        scores[label] = value
    if legacy and scores["Quality"] is not None and all(scores[x] is None for x in ("Market", "Team", "Risk")):
        scores["Quality"] = None
        warnings.append("Aggregate contains only neutral defaults; not assessed.")
    confidence = number(data.get("confidence"), 1) if "confidence" in data else number(data.get("confidence_score"), 100)
    if "confidence" not in data and confidence is not None:
        confidence /= 100
    if confidence is not None and confidence < .3:
        warnings.append("Low confidence: insufficient evidence for an investment briefing.")
    if subvalues and any(not c.get("belegt") for group in subvalues.values() if isinstance(group, dict) for c in group.values() if isinstance(c, dict)):
        warnings.append("Reported scores include 50-point defaults for missing criteria; see Evidence.")
    demo = bool(data.get("is_demo") or "dummy" in name.casefold() or identity.startswith("dummy-")
                or any(is_example(e["url"]) for e in evidence) or is_example(data.get("website")))
    data["value_proposition"] = data.get("value_proposition") or data.get("produktbeschreibung") or data.get("description")
    data["investment_thesis"] = data.get("investmenthypothese") or data.get("investment_thesis")
    data["why_contact_now"] = data.get("why_now") or data.get("why_contact_now")
    data["founders"] = data.get("founders") or [x.strip() for x in (data.get("name_gruender") or "").split(";") if x.strip()]
    data["open_questions"] = data.get("offene_punkte") or data.get("open_questions") or data.get("research_questions") or []
    return Lead(identity, name, SECTORS.get(data.get("branche") or data.get("htgf_sector") or data.get("industry"), data.get("industry") or "Not assessed"),
                STAGES.get(data.get("stage"), data.get("stage_classification") or data.get("stage") or "Not assessed"),
                data, record, evidence, scores, confidence, demo, warnings)


def load_payload(payload):
    if isinstance(payload, dict):
        if "result" in payload:
            payload = payload["result"]
        if isinstance(payload, dict) and "leads" in payload:
            payload = payload["leads"]
        elif isinstance(payload, dict):
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("Expected a scores list, a lead, ResearchResult or AnalysisRun.")
    leads = [adapt(row) for row in payload]
    identities = [lead.id for lead in leads]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate lead IDs: import rejected to prevent decision collisions.")
    return leads


def fund_fit(lead, today=None):
    today = today or date.today()
    d = lead.data
    rows = []
    def add(criterion, status, reason):
        rows.append({"Criterion": criterion, "Status": status, "Rationale": reason})
    stage = "Match" if lead.stage in CONFIG["stages"] else "No Match" if lead.stage == "Early Growth" else "Unknown"
    add("Stage", stage, lead.stage + "; sourcing exclusions are assessed separately")
    add("Sector", "Match" if lead.sector in CONFIG["sectors"] else "Unknown", lead.sector)
    year = d.get("gruendungsjahr") or d.get("founding_year")
    age_status, age_reason = "Unknown", "Confirmed incorporation date missing"
    try:
        exact = date.fromisoformat(str(d.get("founded_on"))) if d.get("founded_on") else None
        if d.get("gruendung_ist_proxy"):
            age_reason = "Grant start is a proxy, not confirmed incorporation"
        elif exact or year:
            month = d.get("gruendungsmonat") or d.get("founding_month")
            earliest = exact or date(int(year), int(month or 1), 1)
            latest = exact or date(int(year), int(month or 12), calendar.monthrange(int(year), int(month or 12))[1])
            cutoff = today.replace(year=today.year - CONFIG["max_age_years"], day=min(today.day, calendar.monthrange(today.year - CONFIG["max_age_years"], today.month)[1]))
            age_status = "Unknown" if earliest > today else "Match" if earliest >= cutoff and latest <= today else "No Match" if latest < cutoff else "Unknown"
            age_reason = f"Incorporation {earliest}–{latest}; maximum {CONFIG['max_age_years']} years"
    except (ValueError, TypeError):
        pass
    add("Company age", age_status, age_reason)
    german = d.get("country") in {"DE", "Germany", "Deutschland"} or d.get("german_presence") is True
    add("Geographic presence", "Match" if german else "Unknown", "German presence supplied" if german else "German office / establishment must be confirmed")
    ticket = number(d.get("round_size_eur") or d.get("capital_need_eur"))
    add("Investment size", "Match" if ticket and ticket >= CONFIG["initial_sweet_spot_eur"] else "Unknown", CONFIG["ticket_note"])
    add("Portfolio overlap", "Unknown", str(d.get("portfolio_overlap") or "No portfolio comparison available"))
    core = rows[:4]
    status = "Likely Out of Scope" if any(r["Status"] == "No Match" for r in core) else "Potential Fit" if all(r["Status"] == "Match" for r in core) else "Review Required"
    return status, rows


def investment_scenario(investment, pre_money, dilution, exit_equity):
    values = [number(x) for x in (investment, pre_money, dilution, exit_equity)]
    if any(x is None for x in values) or investment <= 0 or dilution > 1:
        raise ValueError("Positive investment, nonnegative values and dilution between 0 and 1 required.")
    post = pre_money + investment
    ownership = investment / post
    final = ownership * (1 - dilution)
    proceeds = exit_equity * final
    return {"Post-money valuation": post, "Initial ownership": ownership,
            "Ownership after dilution": final, "Exit proceeds": proceeds, "MOIC": proceeds / investment}
