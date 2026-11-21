"""Normalize captured lead sources for scoring without reading dossier interpretations (step 2 -> 3 handoff).

Owner: context step; consumed by pipeline.evaluate_context and evaluation/engine.py. Market sizing and
growth come from scoring_market.py.
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import re
from typing import Literal

from models import EnrichedLead
from research_models import Period
from scoring_market import market_parameters
from scoring_models import (
    Count, GrantStatus, Parameter, PartialDate, PositiveCents, ProductStage, RoundStage, ScoringEvidence,
    ScoringInput, VCStatus,
)

STAGES = {
    "idea": "Idee|Idea|Konzept|Concept",
    "paper": "Paper|Forschungsarbeit",
    "lab_prototype": "Laborprototyp|Labor-Prototyp|Lab prototype",
    "prototype": "Prototyp|Prototype",
    "mvp": "MVP|Minimum viable product",
    "pilot": "Pilot|Pilotprojekt|Pilot phase|Pilotphase",
    "first_customers": "Erste Kunden|First customers",
    "commercial": "Am Markt|Marktreif und verfügbar|Commercial|Commercially available|On the market|Launched",
}
VC_BACKED = r"VC[- ]backed|VC[- ]finanziert|Venture[- ]capital[- ]backed"
VC_STATES = {
    "confirmed": rf"Ja|Yes|Vorhanden|{VC_BACKED}",
    "reported_none": r"Nein|No|Kein VC|No VC",
}
GRANT_STATES = {
    "applied": r"Antrag eingereicht|Antrag gestellt|Application submitted",
    "approved": r"Bewilligt|Approved|Awarded",
    "received": r"Ausbezahlt|Erhalten|Received|Disbursed",
    "none_reported": r"Keine|None",
}
ROUND_STAGES = {
    "pre_seed": r"Pre[- ]Seed", "seed": "Seed", "series_a": "Series A",
    "series_b": "Series B", "series_c": "Series C", "other": "Other|Sonstige",
}
LABELS = {
    "founded": r"Gründungsdatum|Founding date",
    "product_stage": r"Produktreife|Produktstatus|Product stage",
    "vc_status": r"VC-Status|VC status",
    "funding_status": r"Finanzierungsstatus|Funding status",
    "public_grant": r"Öffentliche Förderung|Fördermittel|Public grants?",
    "completed_rounds": r"Abgeschlossene Eigenkapitalrunde|Completed equity round",
    "planned_round": r"Geplante Finanzierungsrunde|Planned funding round",
    "round_size_eur_cents": r"Rundengröße|Round size",
    "asking_pre_money_eur_cents": r"Geforderte Pre-Money-Bewertung|Asking pre-money valuation",
}
METRICS = {
    "annual_revenue_eur_cents": r"Jahresumsatz|Annual revenue",
    "annual_customer_count": r"Kundenanzahl|Customer count",
    "annual_paying_customer_count": r"Anzahl zahlender Kunden|Paying customer count",
    "annual_revenue_growth_pct": r"Umsatzwachstum|Revenue growth",
}
VOCABULARY = {
    "product_stage": STAGES, "vc_status": VC_STATES, "public_grant": GRANT_STATES,
    "completed_rounds": ROUND_STAGES, "planned_round": ROUND_STAGES,
}
HEADERS = r"Unternehmen|Company"


def _after(value: PartialDate, as_of: date | None) -> bool:
    """True if a (partial) date lies after the as-of date."""
    return bool(as_of) and value.components() > (as_of.year, as_of.month, as_of.day)


def _labelled(line, names):
    match = re.fullmatch(rf"(?:{names})\s*[:–]\s*(.+)", line, re.IGNORECASE)
    return match[1] if match else None


def _enum(text, choices):
    return next((value for value, pattern in choices.items()
                 if re.fullmatch(pattern, text.strip(" ."), re.IGNORECASE)), None)


def _money(text):
    match = re.fullmatch(r"(?:€\s*(.+)|(.+?)\s*(?:EUR|€))", text.strip(), re.IGNORECASE)
    if match is None:
        return None
    number = (match[1] or match[2]).strip()
    scale = 1
    if scaled := re.fullmatch(r"(.+?)\s+(Mio\.?|million|Tsd\.?|thousand)", number, re.IGNORECASE):
        number = scaled[1]
        scale = 1000 if scaled[2].lower().startswith(("tsd", "thousand")) else 1_000_000
    # A single dot/comma followed by three digits is ambiguous without a stated locale.
    if re.fullmatch(r"\d{1,3}(?: \d{3}){1,4}(?:[.,]\d{1,2})?", number):
        number = number.replace(" ", "")
    elif re.fullmatch(r"\d{1,3}([.,])\d{3}(?:\1\d{3}){1,3}", number):
        number = re.sub(r"[.,]", "", number)
    elif grouped := re.fullmatch(r"\d{1,3}([.,])\d{3}(?:\1\d{3})*([.,])\d{1,2}", number):
        if grouped[1] == grouped[2]:
            return None
        number = number.replace(grouped[1], "")
    if not re.fullmatch(r"\d{1,15}(?:[.,]\d{1,2})?", number):
        return None
    return int(Decimal(number.replace(",", ".")) * scale * 100)


def _date(text):
    try:
        if re.fullmatch(r"\d{4}(?:-\d{2})?", text):
            parts = text.split("-")
            return PartialDate(year=int(parts[0]), month=int(parts[1]) if len(parts) == 2 else None,
                               precision="month" if len(parts) == 2 else "year")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            value = date.fromisoformat(text)
        else:
            value = datetime.strptime(text, "%d.%m.%Y").date()
        return PartialDate(year=value.year, month=value.month, day=value.day, precision="day")
    except ValueError:
        return None


def _metric_value(metric, text):
    if metric == "annual_revenue_eur_cents":
        return _money(text)
    if metric == "annual_revenue_growth_pct":
        if re.fullmatch(r"[+-]?\d{1,6}(?:[.,]\d{1,2})?\s*%", text):
            return Decimal(text.removesuffix("%").strip().replace(",", "."))
        return None
    return int(text) if re.fullmatch(r"\d{1,12}", text) else None


def _bound_to_company(lead, signal, lines):
    subjects = {value.casefold() for line in lines if (value := _labelled(line, HEADERS))}
    if subjects and subjects != {" ".join(lead.name.split()).casefold()}:
        return False
    if signal.subject_lead_id is not None:
        return signal.subject_lead_id == lead.id
    if subjects:
        return True
    # An original discovery URL can belong to a publisher or a directory.
    if (lead.website and lead.website.host and signal.url.host and
            lead.website.host.removeprefix("www.") == signal.url.host.removeprefix("www.")):
        return True
    return None


def _assertions(lines):
    known = "|".join(LABELS.values())
    for index, line in enumerate(lines):
        if len(line) > 1000:
            continue
        if re.fullmatch(known, line, re.IGNORECASE) and index + 1 < len(lines):
            following = lines[index + 1]
            if len(following) <= 1000 and not re.match(rf"(?:{known}|{HEADERS})\b", following, re.IGNORECASE):
                yield f"{line}: {following}", f"{line}\n{following}"
        yield line, line


class _Candidates:
    """Collected (value, evidence id) candidates per scoring key, resolved into Parameters."""
    def __init__(self, lead_id):
        self.lead_id = lead_id
        self.values = defaultdict(list)
        self.evidence = {}

    def add_evidence(self, url, excerpt, *, document_date=None, kind="source_excerpt", source_snapshot_id=None):
        item = ScoringEvidence(url=url, excerpt=excerpt, document_date=document_date,
                               kind=kind, subject_lead_id=self.lead_id, source_snapshot_id=source_snapshot_id)
        key = item.stable_id()
        self.evidence[key] = item
        return key

    def resolve(self, key, model, *, rule=None, **metadata):
        options = self.values.get(key, ())
        ids = sorted({evidence_id for _, evidence_id in options})
        base = dict(rule=rule or f"company.{key}", evidence_ids=ids, **metadata)
        if not options:
            return model(status="missing", **base)
        values = [value for value, _ in options if value is not None]
        if key == "founded" and values:
            value = max(values, key=lambda item: len(item.components()))
            conflict = any(value.components()[:len(other.components())] != other.components() for other in values)
        else:
            value = values[0] if values else None
            conflict = any(other != value for other in values)
        if conflict:
            return model(status="conflicting", **base)
        if len(values) != len(options):
            return model(status="ambiguous", **base)
        upstream_only = all(self.evidence[item].kind == "upstream_field" for item in ids)
        return model(value=value, status="informational" if upstream_only and key == "founded" else "usable",
                     provenance="upstream_reported" if upstream_only else "source_reported", **base)


def _collect(lead, as_of):
    candidates = _Candidates(lead.id)
    source = lead.country_evidence
    if (lead.country == "DE" and source and source.verification_status != "assumption"
            and not (as_of and source.document_date and source.document_date > as_of)):
        reference = candidates.add_evidence(source.url, source.finding, document_date=source.document_date,
                                            kind="upstream_field")
        candidates.values["country"].append(("DE", reference))
    if lead.has_vc is not None:
        reference = candidates.add_evidence(lead.source_url, f"has_vc = {str(lead.has_vc).lower()}",
                                            kind="upstream_field")
        candidates.values["vc_status"].append(("confirmed" if lead.has_vc else "reported_none", reference))
    if lead.founding_year is not None:
        founding = PartialDate(year=lead.founding_year, month=lead.founding_month,
                               precision="month" if lead.founding_month else "year")
        reference = candidates.add_evidence(lead.source_url, f"founding = {founding.components()}",
                                            kind="upstream_field")
        candidates.values["founded"].append((None if _after(founding, as_of) else founding, reference))
    for signal in lead.scoring_sources if lead.scoring_sources is not None else lead.signals:
        if as_of and signal.date and signal.date > as_of:
            continue
        lines = [" ".join(line.split()) for line in signal.evidence.splitlines() if line.strip()]
        bound = _bound_to_company(lead, signal, lines)
        if bound is False:
            continue
        snapshot_id = sha256(signal.model_dump_json().encode("utf-8")).hexdigest()
        for line, excerpt in _assertions(lines):
            for key, value in _parse_line(line, as_of):
                reference = candidates.add_evidence(signal.url, excerpt, document_date=signal.date,
                                                    kind="source_excerpt" if bound else "unbound_excerpt",
                                                    source_snapshot_id=snapshot_id)
                candidates.values[key].append((value if bound else None, reference))
    return candidates


def _parse_line(line, as_of):
    for field, names in LABELS.items():
        if not (text := _labelled(line, names)):
            continue
        if field == "funding_status":
            if re.fullmatch(VC_BACKED, text.strip(" ."), re.IGNORECASE):
                yield "vc_status", "confirmed"
        elif field == "founded":
            value = _date(text)
            if value and _after(value, as_of):
                value = None
            yield field, value
        elif field.endswith("_cents"):
            value = _money(text)
            yield field, value if value is not None and value > 0 else None
        else:
            yield field, _enum(text, VOCABULARY[field])
    for metric, label in METRICS.items():
        if match := re.fullmatch(rf"(?:{label})\s+((?:19|20)\d{{2}})\s*:\s*(.+)", line, re.IGNORECASE):
            year = int(match[1])
            if not as_of or year <= as_of.year:
                yield (metric, year), _metric_value(metric, match[2])


def admission_issue(scoring: ScoringInput) -> str | None:
    if scoring.country.status != "usable":
        return "Kein nutzbarer Deutschland-Beleg am Stichtag."
    if scoring.vc_status.value == "confirmed" or scoring.vc_status.status == "conflicting":
        return "VC-Finanzierung gefunden oder widersprüchlich gemeldet."
    return None


def build_scoring_input(lead: EnrichedLead, *, as_of: date | None = None) -> ScoringInput:
    """Build the step-3 ScoringInput from source material; previously exported scores and facts are ignored."""
    items = _collect(lead, as_of)
    resolve = items.resolve
    metrics = {}
    for metric in METRICS:
        years = sorted(key[1] for key in items.values if isinstance(key, tuple) and key[0] == metric)
        money = metric.endswith("_cents")
        percent = metric.endswith("_pct")
        metrics[metric] = [
            resolve((metric, year), Parameter[Decimal] if percent else Parameter[Count],
                    rule=f"company.{metric}", period=Period(start_year=year, end_year=year),
                    unit="percent" if percent else "cent" if money else "customer",
                    currency="EUR" if money else None) for year in years
        ]
    rounds = []
    for stage in sorted({value for value, _ in items.values["completed_rounds"] if value is not None}):
        # Each supported stage is a reported occurrence, not a round count.
        ids = sorted({key for value, key in items.values["completed_rounds"] if value == stage})
        rounds.append(Parameter[RoundStage](value=stage, status="usable", provenance="source_reported",
                                            rule="company.completed_rounds", evidence_ids=ids))
    if any(value is None for value, _ in items.values["completed_rounds"]):
        ids = sorted({key for value, key in items.values["completed_rounds"] if value is None})
        rounds.append(Parameter[RoundStage](status="ambiguous", rule="company.completed_rounds", evidence_ids=ids))
    market = lead.context_v2.market_intelligence if lead.context_v2 else None
    return ScoringInput(
        lead_id=lead.id, as_of=as_of, country=resolve("country", Parameter[Literal["DE"]]),
        founded=resolve("founded", Parameter[PartialDate]), product_stage=resolve("product_stage", Parameter[ProductStage]),
        vc_status=resolve("vc_status", Parameter[VCStatus]), public_grant=resolve("public_grant", Parameter[GrantStatus]),
        completed_rounds=rounds, planned_round=resolve("planned_round", Parameter[RoundStage]),
        round_size_eur_cents=resolve("round_size_eur_cents", Parameter[PositiveCents], unit="cent", currency="EUR"),
        asking_pre_money_eur_cents=resolve("asking_pre_money_eur_cents", Parameter[PositiveCents], unit="cent", currency="EUR"),
        **metrics, **market_parameters(market, items.add_evidence, as_of),
        evidence=dict(sorted(items.evidence.items())),
    )
