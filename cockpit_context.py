"""Project structured research into display fields without losing its provenance."""
from collections.abc import Mapping


def claim_text(value):
    if isinstance(value, dict):
        return value.get("value")
    return value


def present(value):
    return value is not None and value != "" and value != [] and value != {} and str(value).lower() not in {"unknown", "unbekannt"}


def project_context(data, context):
    """Keep typed context nested, fill only empty flat aliases used by legacy panels."""
    def put(key, value):
        source_value = value
        value = claim_text(value)
        if present(value) and not present(data.get(key)):
            data[key] = value
        elif present(value) and str(value).casefold() != str(data.get(key)).casefold():
            data.setdefault("_research_conflicts", []).append({"Field": key.replace("_", " ").title(),
                "Original value": str(data[key]), "Research value": str(value),
                "Evidence IDs": ", ".join(source_value.get("evidence_ids", [])) if isinstance(source_value, dict) else ""})
    structured = any(key in context for key in ("company", "product", "traction", "funding", "research_status"))
    if not structured:
        data.update(context)
        return
    data["market_intelligence"] = context.get("market_intelligence") or data.get("market_intelligence")
    data["research_updated_at"] = context.get("updated_at")
    product = context.get("product") or {}
    for field, targets in {
        "customer_problem": ("customer_problem", "problem_statement"), "solution": ("solution", "product_mechanics"),
        "target_customers": ("target_customers",), "economic_buyer": ("economic_buyer",),
        "business_model": ("business_model",), "maturity": ("product_stage",), "advantage": ("differentiation",),
        "technology": ("technology", "technology_advantage"), "ip": ("ip",),
        "development_status": ("development_status",), "next_milestone": ("next_milestone",),
    }.items():
        for target in targets:
            put(target, product.get(field))
    company = context.get("company") or {}
    put("location", company.get("headquarters") or company.get("reported_location"))
    put("company_status", company.get("company_status"))
    data["founding_date_status"] = company.get("founding_date_status")
    if company.get("founding_date_status") == "documented":
        put("founded_on", company.get("founding_date"))
    profiles = {p["name"]: dict(p) for p in data.get("founder_profiles", []) if isinstance(p, dict) and p.get("name")}
    for founder in context.get("founders", []):
        name = founder.get("name")
        if not name:
            continue
        profile = profiles.setdefault(name, {"name": name})
        for key, value in founder.items():
            if key != "name" and present(claim_text(value)) and not present(profile.get(key)):
                profile[key] = claim_text(value)
    data["founder_profiles"] = list(profiles.values())
    names = [name for name in data.get("founders", []) if isinstance(name, str)]
    data["founders"] = list(dict.fromkeys([*names, *profiles]))
    funding = context.get("funding") or {}
    for field in ("capital_need", "round_size_eur", "asking_pre_money_eur", "use_of_funds", "burn_rate", "cash_runway", "fundraising_status"):
        put(field, funding.get(field))
    put("funding_status", funding.get("status"))
    metrics = (context.get("traction") or {}).get("reported_metrics") or {}
    for metric, key in (("revenue", "annual_revenue_eur"), ("customer_count", "customer_count")):
        observations = [v for v in metrics.get(metric, []) if v.get("data_type") == "observed"
                        and (key != "annual_revenue_eur" or v.get("currency") == "EUR")]
        if observations:
            latest = max(observations, key=lambda v: v["period"]["end_year"])
            put(key, latest)
            if data.get(key) == latest["value"]:
                data.setdefault("_operating_measures", {})[key] = latest
    market = context.get("market_intelligence") or {}
    put("target_market", market.get("market_definition"))


def source_records(record):
    """Include company, founder, traction, funding, market and scoring evidence."""
    found = {}
    def walk(value):
        if isinstance(value, Mapping):
            if (value.get("finding") or value.get("aussage")) and ("url" in value or "quelle" in value):
                key = tuple(str(value.get(k) or "") for k in ("evidence_id", "source", "url", "quelle", "finding", "aussage", "field", "dimension", "kriterium", "document_date", "source_date", "published_on", "datum", "punkte"))
                found.setdefault(key, dict(value))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(record)
    return list(found.values())


def context_for(lead):
    context = lead.raw.get("context_v2")
    return context if isinstance(context, dict) else {}


def market_for(lead):
    market = context_for(lead).get("market_intelligence") or lead.data.get("market_intelligence") or {}
    return market if isinstance(market, dict) else {}


def evidence_for(lead, value):
    ids = value.get("evidence_ids", []) if isinstance(value, dict) else []
    return [e for e in lead.evidence if e.get("evidence_id") in ids]


def measure_label(measure):
    if not isinstance(measure, dict) or not isinstance(measure.get("value"), (float, int)):
        return "Not supplied"
    value = measure["value"]
    currency = measure.get("currency") or ""
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency + " " if currency else "")
    unit = measure.get("unit", "")
    unit = "" if unit == "Betrag" and currency else "/ year" if unit == "pro Jahr" else unit
    if unit == "Anteil":
        value, unit = value * 100, "%"
    amount = f"{value:,.4f}".rstrip("0").rstrip(".") if value != int(value) else f"{value:,.0f}"
    return f"{symbol}{amount} {unit}".strip()
