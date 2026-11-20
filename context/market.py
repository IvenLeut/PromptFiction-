"""Build market research for a selected lead from a bounded source dossier."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from math import isfinite
from typing import Any

from models import EnrichedLead
from research_models import CapitalRequirements, MarketIntelligence, MarketMeasure, MarketSeries, Period
from scoring_input import build_scoring_input


def _ids(*items):
    return list(dict.fromkeys(evidence_id for item in items for evidence_id in item.evidence_ids))


def _compatible(a, b):
    return (a.unit, a.currency, a.geography) == (b.unit, b.currency, b.geography)


def _cagr(series: MarketSeries, *, forecast: bool) -> MarketSeries:
    points = sorted(series.points, key=lambda point: point.period.end_year)
    first, last = points[0], points[-1]
    years = last.period.end_year - first.period.end_year
    types = {"forecast", "assumption", "estimate"} if forecast else {"observed"}
    if (not all(point.data_type in types and _compatible(point, first)
                and point.period.start_year == point.period.end_year for point in points)
            or len({point.period.end_year for point in points}) != len(points)):
        raise ValueError(f"Inkonsistente Jahresreihe: {series.metric}")
    cagr = None
    if years > 0 and first.value > 0 and last.value >= 0:
        rate = ((last.value / first.value) ** (1 / years) - 1) * 100
        if isfinite(rate):
            data_type = first.data_type if first.data_type == last.data_type else "estimate"
            cagr = MarketMeasure(
                value=rate, unit="% pro Jahr", currency=None, geography=first.geography,
                period=Period(start_year=first.period.start_year, end_year=last.period.end_year),
                methodology="((Endwert / Anfangswert)^(1 / Jahre) − 1) × 100",
                data_type=data_type, evidence_ids=_ids(first, last),
            )
    return MarketSeries(metric=series.metric, points=points, cagr=cagr)


def _market_size(count, price):
    if (count.unit != "Unternehmen" or not count.value.is_integer() or count.value < 0
            or price.unit != "pro Unternehmen und Jahr" or not price.currency or price.value <= 0
            or count.geography != price.geography or count.period != price.period):
        raise ValueError("Marktgröße benötigt Unternehmen und jährlichen Preis für dieselbe Geografie und Periode.")
    return MarketMeasure(
        value=Decimal(str(count.value)) * Decimal(str(price.value)), unit="pro Jahr", currency=price.currency,
        geography=count.geography, period=count.period,
        methodology=f"{count.value:,.0f} Unternehmen × {price.value:,.2f} {price.currency}/Unternehmen/Jahr. "
                    f"Grundgesamtheit: {count.methodology}",
        data_type="estimate", evidence_ids=_ids(count, price),
    )


def _subset(base, *, share=None, capacity=None):
    if share is not None:
        if (share.unit != "Anteil" or share.currency is not None or not 0 <= share.value <= 1
                or share.geography != base.geography or share.period != base.period):
            raise ValueError("SAM-Anteil muss zwischen 0 und 1 liegen und zur TAM-Grundgesamtheit passen.")
        fraction = Decimal(str(base.value)) * Decimal(str(share.value))
        value = int(fraction.to_integral_value(rounding=ROUND_FLOOR))
        detail = f"TAM-Grundgesamtheit × {share.value:.1%} erreichbarer Anteil, abgerundet"
        factor = share
    else:
        if (capacity.unit != base.unit or capacity.currency is not None or capacity.value < 0
                or not capacity.value.is_integer() or capacity.geography != base.geography
                or capacity.period != base.period):
            raise ValueError("SOM-Kapazität muss eine passende Anzahl Unternehmen sein.")
        value = min(capacity.value, base.value)
        detail = "Anzahl betreubarer Kunden, begrenzt auf die SAM-Grundgesamtheit"
        factor = capacity
    return MarketMeasure(
        value=value, unit=base.unit, currency=None, geography=base.geography, period=base.period,
        methodology=detail, data_type="estimate", evidence_ids=_ids(base, factor),
    )


def _multiple(ev, financial):
    if (ev is None or financial is None or ev.value <= 0 or financial.value <= 0
            or ev.currency is None or ev.currency != financial.currency
            or ev.unit != "Betrag" or financial.unit != "pro Jahr"
            or ev.geography != financial.geography
            or ev.data_type != "observed" or financial.data_type != "observed"
            or ev.period.start_year != ev.period.end_year
            or financial.period.start_year != financial.period.end_year
            or ev.period.end_year - financial.period.end_year not in {0, 1}):
        return None
    return MarketMeasure(
        value=ev.value / financial.value, unit="x", currency=None, geography=ev.geography,
        period=ev.period, methodology=f"Expliziter Enterprise Value / Jahreskennzahl {financial.period.end_year}",
        data_type="observed", evidence_ids=_ids(ev, financial),
    )


def _reference_ids(data: Any):
    if isinstance(data, dict):
        yield from data.get("evidence_ids", ())
        for key, value in data.items():
            if key not in {"evidence_ids", "sources"}:
                yield from _reference_ids(value)
    elif isinstance(data, list):
        for value in data:
            yield from _reference_ids(value)


def research_market(lead: EnrichedLead, research: MarketIntelligence) -> EnrichedLead:
    """Attach validated, source-backed market inputs and compute derived values."""
    if lead.context_v2 is None:
        raise ValueError("Für Marktrecherche zuerst den Lead mit Schritt 2 anreichern.")
    result = research.model_copy(deep=True)
    context = lead.context_v2.model_copy(deep=True)
    evidence = [*lead.evidence]
    source_ids = {item.evidence_id for item in result.sources}
    if len(source_ids) != len(result.sources):
        raise ValueError("Doppelte Evidence-ID in Marktquellen.")
    # Source-backed company claims remain linked when reused inside market research.
    funding = context.funding
    capital = result.capital_requirements
    result.capital_requirements = CapitalRequirements(**{
        key: getattr(capital, key) for key in ("capital_need", "time_to_milestone", "burn_rate", "cash_runway", "investment_need")
    }, **{
        key: getattr(capital, key) or getattr(funding, key)
        for key in ("planned_round", "use_of_funds", "next_milestone")
    })
    if not result.sector_metrics.pilot_projects:
        traction = context.traction
        result.sector_metrics.pilot_projects = [
            *traction.paid_pilots, *traction.unpaid_pilots, *traction.pilots_payment_unknown,
        ]
    available = {}
    for item in [*evidence, *result.sources, *([lead.country_evidence] if lead.country_evidence else [])]:
        previous = available.setdefault(item.evidence_id, item)
        if (previous.url, previous.field, previous.finding, previous.document_date) != (
            item.url, item.field, item.finding, item.document_date
        ):
            raise ValueError(f"Uneindeutige Evidence-ID: {item.evidence_id}")
    references = set(_reference_ids(result.model_dump()))
    if unknown := references - available.keys():
        raise ValueError(f"Unbekannte Evidence-IDs: {', '.join(sorted(unknown))}")
    for transaction in result.comparable_transactions:
        if not any(available[key].url == transaction.original_source for key in transaction.evidence_ids):
            raise ValueError(f"Originalquelle fehlt für {transaction.company}.")
        transaction.ev_revenue = _multiple(transaction.enterprise_value, transaction.revenue)
        transaction.ev_ebitda = _multiple(transaction.enterprise_value, transaction.ebitda)

    inputs = result.sizing_inputs
    count, price = inputs.get("addressable_companies"), inputs.get("annual_revenue_per_company")
    if count is not None and price is not None:
        if count.currency is not None:
            raise ValueError("Die Anzahl der Unternehmen darf keine Währung haben.")
        result.tam = _market_size(count, price)
        if share := inputs.get("serviceable_share"):
            serviceable = _subset(count, share=share)
            result.sam = _market_size(serviceable, price)
            if capacity := inputs.get("delivery_capacity"):
                result.som = _market_size(_subset(serviceable, capacity=capacity), price)
    result.historical_growth = [_cagr(series, forecast=False) for series in result.historical_growth]
    result.forecast_growth = [_cagr(series, forecast=True) for series in result.forecast_growth]
    gaps = {
        "Marktdefinition und Zielsegment": result.market_definition and result.target_segment,
        "Zielgeografie": result.target_geography,
        "Adressierbare Kundenbasis oder Jahreserlös je Kunde (TAM)": result.tam,
        "Belegter oder ausdrücklich modellierter erreichbarer Anteil (SAM)": result.sam,
        "Kundenkapazität oder belastbarer Marktanteil (SOM)": result.som,
        "Vergleichbare historische Zeitreihe": result.historical_growth,
        "Belastbare Marktprognose": result.forecast_growth,
        "Wachstumstreiber": result.growth_drivers,
        "Relevante Wettbewerber": result.competitors,
        "Öffentlich belegte Vergleichstransaktionen": result.comparable_transactions,
    }
    result.research_gaps = list(dict.fromkeys(
        [*result.research_gaps, *(label for label, value in gaps.items() if value is None or value == [])]
    ))
    result.sources = list({item.evidence_id: item for item in
                           [*result.sources, *(available[key] for key in sorted(references - source_ids))]}.values())
    context.market_intelligence = result
    context.research_status.mode = "targeted"
    context.research_status.market = "partial" if result.research_gaps else "complete"
    context.updated_at = datetime.now(timezone.utc)
    enriched = lead.model_copy(update={"context_v2": context})
    if not lead.is_demo:
        as_of = lead.scoring_input.as_of if lead.scoring_input else None
        enriched.scoring_input = build_scoring_input(enriched, as_of=as_of)
    return enriched
