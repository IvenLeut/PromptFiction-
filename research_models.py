"""Additive research contract (step 2, context_v2) consumed by scoring and the dashboard.

Imports nothing from this repo; models.py and scoring_models.py build on it. Class docstrings become
JSON-schema descriptions, so classes are documented with comments.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


# Base of every shared model: unknown keys are rejected, assignments are validated.
class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# A sourced finding (step 2); `evidence_id` is derived from its identity when not given.
class Evidence(Contract):
    source: str = Field(min_length=1)
    url: HttpUrl
    finding: str = Field(min_length=1)
    field: str | None = None
    published_on: date | None = None
    source_date: date | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_id: str = Field(default="", min_length=1)
    document_date: date | None = None
    verification_status: Literal[
        "unverified", "source_matched", "source_reviewed", "assumption"
    ] = "unverified"
    dimension: str | None = None
    kriterium: str | None = None
    aussage: str | None = None
    datum: date | datetime | None = None
    punkte: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, raw):
        """Map legacy scoring keys (aussage, datum) and fill source, dates and evidence_id."""
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        if "finding" not in data and data.get("aussage"):
            data["finding"] = data["aussage"]
        if "source" not in data and data.get("url"):
            data["source"] = urlsplit(str(data["url"])).hostname or str(data["url"])
        document_date = data.get("document_date") or data.get("source_date") or data.get("published_on")
        if document_date is None and data.get("datum"):
            document_date = str(data["datum"])[:10]
        if document_date:
            data.setdefault("document_date", document_date)
            data.setdefault("source_date", document_date)
        if "evidence_id" not in data:
            identity = [data.get(key) for key in ("url", "field", "dimension", "kriterium", "finding")]
            identity.append(document_date)
            digest = sha256(json.dumps(identity, default=str, ensure_ascii=False).encode("utf-8"))
            data["evidence_id"] = digest.hexdigest()[:24]
        return data


class Claim(Contract):
    value: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    origin: Literal["source_statement", "model_selected_quote", "analyst_interpretation"] = "source_statement"


class CompanyResearch(Contract):
    founding_date: Claim | None = None
    founding_date_status: Literal["documented", "reported", "conflicting", "unknown"] = "unknown"
    headquarters: Claim | None = None
    reported_location: Claim | None = None
    germany_evidence_ids: list[str] = Field(default_factory=list)
    company_status: Claim | None = None


class FounderResearch(Contract):
    name: str
    role: Claim | None = None
    qualifications: Claim | None = None
    previous_companies: Claim | None = None
    founding_experience: Claim | None = None
    customer_problem_experience: Claim | None = None


class ProductResearch(Contract):
    customer_problem: Claim | None = None
    solution: Claim | None = None
    target_customers: Claim | None = None
    economic_buyer: Claim | None = None
    business_model: Claim | None = None
    maturity: Claim | None = None
    advantage: Claim | None = None
    technology: Claim | None = None
    ip: Claim | None = None
    development_status: Claim | None = None
    next_milestone: Claim | None = None


class TractionResearch(Contract):
    paid_customers: list[Claim] = Field(default_factory=list)
    customers_payment_unknown: list[Claim] = Field(default_factory=list)
    paid_pilots: list[Claim] = Field(default_factory=list)
    unpaid_pilots: list[Claim] = Field(default_factory=list)
    pilots_payment_unknown: list[Claim] = Field(default_factory=list)
    lois: list[Claim] = Field(default_factory=list)
    commercial_partners: list[Claim] = Field(default_factory=list)
    research_partners: list[Claim] = Field(default_factory=list)
    usage: Claim | None = None
    revenue: Claim | None = None
    growth: Claim | None = None
    reported_metrics: dict[str, list["MarketMeasure"]] = Field(default_factory=dict)


class FundingResearch(Contract):
    status: Literal["vc_backed", "non_vc_funded", "unfunded", "funded", "conflicting", "unknown"] = "unknown"
    vc_status: Literal["confirmed", "reported_none", "conflicting", "unknown"] = "unknown"
    status_evidence_ids: list[str] = Field(default_factory=list)
    rounds: list[Claim] = Field(default_factory=list)
    investors: list[Claim] = Field(default_factory=list)
    public_grants: list[Claim] = Field(default_factory=list)
    fundraising_status: Claim | None = None
    planned_round: Claim | None = None
    capital_need: Claim | None = None
    use_of_funds: Claim | None = None
    next_milestone: Claim | None = None
    time_to_milestone: Claim | None = None
    burn_rate: Claim | None = None
    cash_runway: Claim | None = None
    round_size_eur: int | None = None
    asking_pre_money_eur: int | None = None
    round_terms_evidence_ids: list[str] = Field(default_factory=list)


class Period(Contract):
    start_year: int = Field(ge=1800, le=2200)
    end_year: int = Field(ge=1800, le=2200)

    @model_validator(mode="after")
    def chronological(self):
        if self.start_year > self.end_year:
            raise ValueError("Der Beginn muss vor oder am Ende der Periode liegen.")
        return self


class MarketMeasure(Contract):
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)
    currency: str | None = Field(pattern=r"^[A-Z]{3}$")
    geography: str = Field(min_length=1)
    period: Period
    methodology: str = Field(min_length=1)
    data_type: Literal["observed", "estimate", "forecast", "assumption"]
    evidence_ids: list[str] = Field(min_length=1)


class MarketSeries(Contract):
    metric: str = Field(min_length=1)
    points: list[MarketMeasure] = Field(min_length=1)
    cagr: MarketMeasure | None = None


class Competitor(Contract):
    name: str
    website: HttpUrl
    product: str
    target_customers: str | None = None
    segment: str | None = None
    geography: str | None = None
    development_stage: str | None = None
    differentiation: str | None = None
    known_funding: MarketMeasure | None = None
    selection_reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ComparableTransaction(Contract):
    company: str
    date: date
    sector: str
    transaction_type: Literal["pre_seed", "seed", "other_funding", "acquisition", "exit", "portfolio_reference"]
    transaction_value: MarketMeasure | None = None
    company_valuation: MarketMeasure | None = None
    enterprise_value: MarketMeasure | None = None
    revenue: MarketMeasure | None = None
    ebitda: MarketMeasure | None = None
    ev_revenue: MarketMeasure | None = None
    ev_ebitda: MarketMeasure | None = None
    original_source: HttpUrl
    comparability_reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class CapitalRequirements(Contract):
    planned_round: Claim | None = None
    capital_need: MarketMeasure | None = None
    use_of_funds: Claim | None = None
    next_milestone: Claim | None = None
    time_to_milestone: MarketMeasure | None = None
    burn_rate: MarketMeasure | None = None
    cash_runway: MarketMeasure | None = None
    investment_need: MarketMeasure | None = None


class ReadinessLevel(Contract):
    level: int = Field(ge=1, le=9)
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    origin: Literal["reported", "analyst_interpretation"]


class SectorMetrics(Contract):
    arr: MarketMeasure | None = None
    growth: MarketMeasure | None = None
    retention: MarketMeasure | None = None
    customer_base: MarketMeasure | None = None
    unit_economics: dict[str, MarketMeasure] = Field(default_factory=dict)
    manufacturing_cost: MarketMeasure | None = None
    technology_readiness: ReadinessLevel | None = None
    market_certainty: ReadinessLevel | None = None
    patents: Claim | None = None
    technical_milestone: Claim | None = None
    pilot_projects: list[Claim] = Field(default_factory=list)
    scale_up_risks: Claim | None = None
    research_phase: Claim | None = None
    regulatory_path: Claim | None = None
    clinical_milestone: Claim | None = None
    capital_to_catalyst: MarketMeasure | None = None

    @model_validator(mode="after")
    def market_certainty_scale(self):
        if self.market_certainty and self.market_certainty.level > 6:
            raise ValueError("Market Certainty Level muss zwischen 1 und 6 liegen.")
        return self


class MarketIntelligence(Contract):
    market_definition: Claim | None = None
    target_segment: Claim | None = None
    target_geography: Claim | None = None
    tam: MarketMeasure | None = None
    sam: MarketMeasure | None = None
    som: MarketMeasure | None = None
    sizing_inputs: dict[str, MarketMeasure] = Field(default_factory=dict)
    historical_growth: list[MarketSeries] = Field(default_factory=list)
    forecast_growth: list[MarketSeries] = Field(default_factory=list)
    growth_drivers: list[Claim] = Field(default_factory=list)
    growth_factors: dict[Literal["technological", "regulatory", "commercial"], list[Claim]] = Field(default_factory=dict)
    market_risks: list[Claim] = Field(default_factory=list)
    competitors: list[Competitor] = Field(default_factory=list, max_length=5)
    comparison_dimensions: list[str] = Field(default_factory=list)
    comparable_transactions: list[ComparableTransaction] = Field(default_factory=list)
    capital_requirements: CapitalRequirements = Field(default_factory=CapitalRequirements)
    sector_metrics: SectorMetrics = Field(default_factory=SectorMetrics)
    research_gaps: list[str] = Field(default_factory=list)
    sources: list[Evidence] = Field(default_factory=list, max_length=50)


class ResearchStatus(Contract):
    mode: Literal["light", "standard", "targeted"]
    market: Literal["not_requested", "partial", "complete"] = "not_requested"
    gaps: list[str] = Field(default_factory=list)


class ContextV2(Contract):
    company: CompanyResearch = Field(default_factory=CompanyResearch)
    founders: list[FounderResearch] = Field(default_factory=list)
    product: ProductResearch = Field(default_factory=ProductResearch)
    traction: TractionResearch = Field(default_factory=TractionResearch)
    funding: FundingResearch = Field(default_factory=FundingResearch)
    discovery_signals: list[Evidence] = Field(default_factory=list)
    market_intelligence: MarketIntelligence | None = None
    research_status: ResearchStatus
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


TractionResearch.model_rebuild()
