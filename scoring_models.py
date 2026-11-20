"""Versioned, deterministic input and evidence for step 3."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field, HttpUrl, model_validator

from research_models import Contract, Period

T = TypeVar("T")
ProductStage = Literal["idea", "paper", "lab_prototype", "prototype", "mvp", "pilot", "first_customers", "commercial"]
VCStatus = Literal["confirmed", "reported_none"]
GrantStatus = Literal["applied", "approved", "received", "none_reported"]
RoundStage = Literal["pre_seed", "seed", "series_a", "series_b", "series_c", "other"]
Provenance = Literal["source_reported", "upstream_reported", "observed", "estimate", "forecast", "scenario"]
Count = Annotated[int, Field(strict=True, ge=0)]
PositiveCents = Annotated[int, Field(strict=True, gt=0)]


class PartialDate(Contract):
    year: int = Field(ge=1800, le=2200)
    month: int | None = None
    day: int | None = None
    precision: Literal["year", "month", "day"]

    @model_validator(mode="after")
    def validate_precision(self):
        actual = "day" if self.day is not None else "month" if self.month is not None else "year"
        if self.precision != actual or (self.day is not None and self.month is None):
            raise ValueError("Datum und Genauigkeit stimmen nicht überein.")
        date(self.year, self.month if self.month is not None else 1,
             self.day if self.day is not None else 1)
        return self

    def components(self):
        return tuple(part for part in (self.year, self.month, self.day) if part is not None)


class ScoringEvidence(Contract):
    url: HttpUrl
    excerpt: str = Field(min_length=1)
    document_date: date | None = None
    kind: Literal["source_excerpt", "unbound_excerpt", "upstream_field", "reviewed_market_input", "market_assumption"]
    subject_lead_id: str = Field(min_length=1)
    source_snapshot_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def stable_id(self):
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class CalculationInput(Contract):
    parameter: str
    value: Decimal = Field(allow_inf_nan=False)
    unit: str
    currency: str | None = None
    period: Period
    geography: str
    provenance: Provenance
    evidence_ids: list[str] = Field(min_length=1)


class Calculation(Contract):
    method: str
    inputs: list[CalculationInput] = Field(min_length=1)


class Parameter(Contract, Generic[T]):
    value: T | None = None
    status: Literal["usable", "missing", "ambiguous", "conflicting", "informational"]
    rule: str
    provenance: Provenance | None = None
    unit: str | None = None
    currency: str | None = None
    period: Period | None = None
    geography: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    calculation: Calculation | None = None

    @model_validator(mode="after")
    def check_value_and_status(self):
        if self.status in {"usable", "informational"}:
            if self.value is None or not self.evidence_ids or self.provenance is None:
                raise ValueError("Ein Wert benötigt Belege und Herkunft.")
        elif self.value is not None or self.calculation is not None:
            raise ValueError("Ein offener Parameter darf keinen Wert enthalten.")
        if self.status == "usable" and self.provenance in {"estimate", "forecast", "scenario"}:
            raise ValueError("Schätzungen, Prognosen und Szenarien sind keine Scoring-Fakten.")
        if self.status in {"ambiguous", "conflicting"} and not self.evidence_ids:
            raise ValueError("Mehrdeutigkeit und Konflikte benötigen Belege.")
        return self


class MarketGrowth(Contract):
    metric: str
    cagr: Parameter[Decimal]


class ScoringInput(Contract):
    schema_version: Literal["1.0"] = "1.0"
    rules_version: Literal["1.0"] = "1.0"
    lead_id: str
    as_of: date | None = None
    country: Parameter[Literal["DE"]]
    founded: Parameter[PartialDate]
    product_stage: Parameter[ProductStage]
    vc_status: Parameter[VCStatus]
    public_grant: Parameter[GrantStatus]
    completed_rounds: list[Parameter[RoundStage]]
    planned_round: Parameter[RoundStage]
    round_size_eur_cents: Parameter[PositiveCents]
    asking_pre_money_eur_cents: Parameter[PositiveCents]
    annual_revenue_eur_cents: list[Parameter[Count]]
    annual_customer_count: list[Parameter[Count]]
    annual_paying_customer_count: list[Parameter[Count]]
    annual_revenue_growth_pct: list[Parameter[Decimal]]
    tam: Parameter[Decimal]
    sam: Parameter[Decimal]
    som: Parameter[Decimal]
    market_growth: list[MarketGrowth]
    evidence: dict[str, ScoringEvidence]

    @model_validator(mode="after")
    def check_references(self):
        if any(item.subject_lead_id != self.lead_id for item in self.evidence.values()):
            raise ValueError("Ein Beleg ist einem anderen Lead zugeordnet.")
        if any(key != item.stable_id() for key, item in self.evidence.items()):
            raise ValueError("Eine Evidence-ID stimmt nicht mit ihrem Beleg überein.")
        parameters = [
            self.country, self.founded, self.product_stage, self.vc_status, self.public_grant,
            *self.completed_rounds, self.planned_round, self.round_size_eur_cents, self.asking_pre_money_eur_cents,
            *self.annual_revenue_eur_cents, *self.annual_customer_count, *self.annual_paying_customer_count,
            *self.annual_revenue_growth_pct, self.tam, self.sam, self.som,
            *(entry.cagr for entry in self.market_growth),
        ]
        for item in parameters:
            ids = set(item.evidence_ids)
            if not ids <= self.evidence.keys():
                raise ValueError("Unbekannte Evidence-ID im Scoring-Parameter.")
            if item.status == "usable" and any(
                self.evidence[key].kind in {"unbound_excerpt", "market_assumption"} for key in ids
            ):
                raise ValueError("Offene Quellenzuordnung oder Szenarioannahmen im Scoring-Parameter.")
            if item.calculation and any(not set(arg.evidence_ids) <= ids for arg in item.calculation.inputs):
                raise ValueError("Berechnung referenziert Belege außerhalb des Parameters.")
        return self
