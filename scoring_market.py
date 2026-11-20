"""Deterministic market calculations from curated market inputs."""
from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext

from research_models import Period
from scoring_models import Calculation, CalculationInput, MarketGrowth, Parameter

Number = Parameter[Decimal]
SIZING_KEYS = ("addressable_companies", "annual_revenue_per_company", "serviceable_share", "delivery_capacity")


def _input(name, measure, sources, add_evidence, as_of):
    items = [sources.get(key) for key in measure.evidence_ids]
    if any(item is None for item in items):
        raise ValueError(f"Marktparameter {name} referenziert einen unbekannten Beleg.")
    allowed = {"source_reviewed", "assumption"} if measure.data_type == "assumption" else {"source_reviewed"}
    if (as_of and measure.data_type == "observed" and measure.period.end_year > as_of.year
            or any(item.verification_status not in allowed
                   or (as_of and item.document_date and item.document_date > as_of) for item in items)):
        return None
    ids = sorted({add_evidence(
        item.url, item.finding, document_date=item.document_date,
        kind="market_assumption" if item.verification_status == "assumption" else "reviewed_market_input",
    ) for item in items})
    return CalculationInput(
        parameter=name, value=Decimal(str(measure.value)), unit=measure.unit, currency=measure.currency,
        period=measure.period, geography=measure.geography,
        provenance="scenario" if measure.data_type == "assumption" else measure.data_type, evidence_ids=ids,
    )


def _calculated(rule, value, method, inputs, *, unit, currency, period, provenance):
    return Number(
        status="usable" if provenance == "observed" else "informational", value=value,
        rule=rule, provenance=provenance, unit=unit, currency=currency, period=period,
        geography=inputs[0].geography,
        evidence_ids=sorted({key for item in inputs for key in item.evidence_ids}),
        calculation=Calculation(method=method, inputs=inputs),
    )


def _sizing(inputs):
    result = {name: Number(status="missing", rule=f"market.{name}") for name in ("tam", "sam", "som")}
    count, price, share, capacity = (inputs.get(key) for key in SIZING_KEYS)
    if count is None or price is None:
        return result
    same_scope = lambda item: item.period == count.period and item.geography == count.geography
    if (not same_scope(price) or count.unit != "Unternehmen" or count.currency is not None
            or count.value < 0 or count.value != count.value.to_integral_value()
            or price.unit != "pro Unternehmen und Jahr" or not price.currency or price.value <= 0):
        raise ValueError("TAM benötigt eine Kundenzahl und einen Jahrespreis im gleichen Markt und Zeitraum.")
    levels = [("tam", count.value, [count, price], "Kundenzahl × Jahrespreis pro Kunde")]
    if share is not None:
        if not same_scope(share) or share.unit != "Anteil" or share.currency or not 0 <= share.value <= 1:
            raise ValueError("Der SAM-Anteil passt nicht zur TAM-Grundgesamtheit.")
        serviceable = (count.value * share.value).to_integral_value(rounding=ROUND_FLOOR)
        levels.append(("sam", serviceable, [count, price, share], "floor(Kundenzahl × erreichbarer Anteil) × Jahrespreis"))
        if capacity is not None:
            if (not same_scope(capacity) or capacity.unit != "Unternehmen" or capacity.currency
                    or capacity.value < 0 or capacity.value != capacity.value.to_integral_value()):
                raise ValueError("Die SOM-Kapazität passt nicht zur TAM-Grundgesamtheit.")
            levels.append(("som", min(serviceable, capacity.value), [count, price, share, capacity],
                           "min(floor(Kundenzahl × erreichbarer Anteil), Kapazität) × Jahrespreis"))
    for name, companies, args, method in levels:
        kinds = {item.provenance for item in args}
        provenance = "scenario" if "scenario" in kinds else "forecast" if "forecast" in kinds else "estimate"
        result[name] = _calculated(f"market.{name}", companies * price.value, method, args,
                                   unit="per_year", currency=price.currency, period=count.period,
                                   provenance=provenance)
    return result


def _growth(metric, points, *, historical):
    rule = "market.historical_cagr" if historical else "market.forecast_cagr"
    missing = Number(status="missing", rule=rule)
    if len(points) < 2 or any(point is None for point in points):
        return MarketGrowth(metric=metric, cagr=missing)
    points.sort(key=lambda point: point.period.end_year)
    first, last = points[0], points[-1]
    years = last.period.end_year - first.period.end_year
    if any(point.period.start_year != point.period.end_year or point.value < 0
           or (point.provenance == "observed") != historical for point in points):
        raise ValueError(f"Nicht vergleichbare Jahresreihe: {metric}")
    by_year = defaultdict(list)
    for point in points:
        by_year[point.period.end_year].append(point)
    period = Period(start_year=first.period.start_year, end_year=last.period.end_year)
    if any(len({point.value for point in entries}) > 1 for entries in by_year.values()):
        return MarketGrowth(metric=metric, cagr=Number(
            status="conflicting", rule=rule, period=period, geography=first.geography, unit="percent_per_year",
            evidence_ids=sorted({key for point in points for key in point.evidence_ids}),
        ))
    if years == 0 or first.value == 0:
        return MarketGrowth(metric=metric, cagr=missing)
    kinds = {point.provenance for point in points}
    provenance = ("observed" if historical else "scenario" if "scenario" in kinds
                  else "forecast" if kinds == {"forecast"} else "estimate")
    value = ((last.value / first.value) ** (Decimal(1) / years) - 1) * 100
    if value.adjusted() <= 25:
        value = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    endpoints = sorted([*by_year[period.start_year], *by_year[period.end_year]],
                       key=lambda point: (point.period.start_year, point.model_dump_json()))
    return MarketGrowth(metric=metric, cagr=_calculated(
        rule, value, "((Endwert / Anfangswert) ^ (1 / Jahre) - 1) × 100", endpoints, unit="percent_per_year",
        currency=None, period=period,
        provenance=provenance,
    ))


def market_parameters(market, add_evidence, as_of):
    if market is None:
        return dict(_sizing({}), market_growth=[])
    sources = {item.evidence_id: item for item in market.sources}
    if len(sources) != len(market.sources):
        raise ValueError("Doppelte Beleg-ID in den Marktquellen.")
    with localcontext(prec=34, rounding=ROUND_HALF_EVEN):
        sizing = _sizing({key: _input(key, market.sizing_inputs[key], sources, add_evidence, as_of)
                          for key in SIZING_KEYS if key in market.sizing_inputs})
        groups = defaultdict(list)
        for historical, entries in ((True, market.historical_growth), (False, market.forecast_growth)):
            for series in entries:
                first = series.points[0]
                scope = first.unit, first.currency, first.geography
                if any((point.unit, point.currency, point.geography) != scope for point in series.points):
                    raise ValueError(f"Nicht vergleichbare Jahresreihe: {series.metric}")
                groups[(series.metric, historical, *scope)].extend(
                    _input(series.metric, point, sources, add_evidence, as_of) for point in series.points
                )
        growth = [_growth(metric, points, historical=historical)
                  for (metric, historical, _unit, _currency, _geography), points in groups.items()]
    growth.sort(key=lambda item: (item.metric, item.cagr.rule, item.model_dump_json()))
    return dict(sizing, market_growth=growth)
