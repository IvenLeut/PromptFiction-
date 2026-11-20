"""Shared contracts. Changes should be agreed across all module owners."""
from enum import Enum
from datetime import date as Date
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, HttpUrl

from research_models import ContextV2, Contract, Evidence


class Industry(str, Enum):
    AI = "AI / Software"
    CLIMATE = "ClimateTech"
    HEALTH = "HealthTech"
    FINTECH = "FinTech"
    INDUSTRIAL = "Industrial / DeepTech"


class SearchCriteria(Contract):
    industry: Industry
    country: Literal["DE"] = "DE"
    limit: int = Field(default=30, ge=1, le=200)



class SourceSignal(Contract):
    source: str = Field(min_length=1)
    type: str = Field(min_length=1)
    url: HttpUrl
    date: Date | None = None
    evidence: str = Field(min_length=1)


class RawLead(Contract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    industry: Industry
    country: str | None = None
    location: str | None = None
    source_url: HttpUrl
    source_name: str | None = None
    discovery_source: str | None = None
    first_signal_date: Date | None = None
    discovered_at: datetime | None = None
    initial_signal: str | None = None
    country_evidence: Evidence | None = None
    is_demo: bool = False
    website: HttpUrl | None = None
    founders: list[str] = Field(default_factory=list)
    contact_email: str | None = Field(default=None, pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
    founding_year: int | None = Field(default=None, ge=1800, le=2100)
    founding_month: int | None = Field(default=None, ge=1, le=12)
    has_vc: bool | None = None
    signals: list[SourceSignal] = Field(default_factory=list)
    prioritization_reason: str | None = None
    htgf_sector: Literal["digital_tech", "industrial_deep_tech", "climate_tech",
                         "life_sciences", "chemie_materialien"] | None = None


class FounderProfile(Contract):
    qualifications: str | None = None
    name: str
    role: str | None = None
    background: str | None = None
    relevant_experience: str | None = None
    distinctive_skills: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class FundingEvent(Contract):
    announced_on: Date | None = None
    amount_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    investors: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class EnrichedLead(RawLead):
    context_v2: ContextV2 | None = None
    founder_profiles: list[FounderProfile] = Field(default_factory=list)
    problem_statement: str | None = None
    target_customers: str | None = None
    product_mechanics: str | None = None
    product_maturity: Literal["Idea", "Prototype", "MVP", "Market", "Unknown"] = "Unknown"
    business_model: str | None = None
    target_market: str | None = None
    competitors: list[str] = Field(default_factory=list)
    technology_advantage: str | None = None
    differentiation: str | None = None
    traction_evidence: list[Evidence] = Field(default_factory=list)
    funding_events: list[FundingEvent] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    customer_problem: str | None = None
    solution: str | None = None
    market: str | None = None
    technology: str | None = None
    competition: str | None = None
    sales: str | None = None
    capital_need: str | None = None
    round_size_eur: int | None = Field(default=None, gt=0)
    asking_pre_money_eur: int | None = Field(default=None, gt=0)
    research_questions: list[str] = Field(default_factory=list)
    funding_status: Literal["Bootstrapped", "Grant-funded", "Pre-Seed", "Seed", "Later", "Unknown", "vc_backed", "non_vc_funded", "unfunded", "funded", "conflicting", "unknown"] = "Unknown"
    vc_status: Literal["confirmed", "reported_none", "conflicting", "unknown"] = "unknown"
    first_signal_date: Date | None = None
    funding_stage: str | None = None
    founded_on: Date | None = None
    team_size: int | None = Field(default=None, ge=0)
    funding_total_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_funding_on: Date | None = None
    product_stage: str | None = None
    customer_count: int | None = Field(default=None, ge=0)
    annual_revenue_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    traction_notes: str | None = None


class InvestmentArgument(Contract):
    statement: str
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)


class EvaluatedLead(EnrichedLead):
    # Preserve the scoring engine's full evidence and missing-value semantics.
    evaluation_v2: dict | None = None
    technology_score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    why_contact_now: str | None = None
    key_strengths: list[InvestmentArgument] = Field(default_factory=list, max_length=3)
    key_risks: list[InvestmentArgument] = Field(default_factory=list, max_length=3)
    score_rationales: dict[str, str] = Field(default_factory=dict)
    fund_fit_score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    team_score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    hard_exclusions: list[str] = Field(default_factory=list)
    eligibility_status: Literal["Eligible", "Excluded", "Unknown"] = "Unknown"
    fund_fit_rationale: str | None = None
    team_rationale: str | None = None
    earliness_rationale: str | None = None
    overall_score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    company_score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    market_potential_score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    risk_score: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    stage_classification: Literal["Pre-Seed", "Seed", "Early Growth", "Unbekannt"]
    value_proposition: str = Field(min_length=1)
    score_drivers: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    earliness_score: float | None = Field(default=None, ge=0, le=100)
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    investment_thesis: str
    risks: list[str] = Field(default_factory=list)


class PipelineIssue(Contract):
    lead_id: str
    stage: Literal["context", "evaluation"]
    message: str


class ResearchResult(Contract):
    leads: list[EvaluatedLead] = Field(default_factory=list)
    issues: list[PipelineIssue] = Field(default_factory=list)


class ContextResult(Contract):
    leads: list[EnrichedLead] = Field(default_factory=list)
    issues: list[PipelineIssue] = Field(default_factory=list)


class AnalysisRun(Contract):
    schema_version: Literal["2.0"] = "2.0"
    criteria: SearchCriteria
    mode: Literal["demo", "live"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discovered_count: int = Field(ge=0)
    enriched_count: int = Field(ge=0)
    result: ResearchResult
