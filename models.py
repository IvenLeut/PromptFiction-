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


class FounderProfile(Contract):
    name: str = Field(min_length=1)
    role: str | None = None
    qualifications: str | None = None
    # Enrichment (context step). Each value is backed by its own URL; None = not found, never guessed.
    institution: str | None = None
    background: Literal["tech", "business", "beides"] | None = None
    prior_experience: list[Literal["fruehere_gruendung", "industrie"]] = Field(default_factory=list)
    openalex_url: HttpUrl | None = None
    works_total: int | None = Field(default=None, ge=0)
    works_in_field: int | None = Field(default=None, ge=0)
    match_confidence: float | None = Field(default=None, ge=0, le=1)
    source_url: HttpUrl | None = None


class Grant(Contract):
    """Public funding (e.g. EXIST) with its catalogue URL."""
    programme: str = Field(min_length=1)
    reference: str | None = None  # Förderkennzeichen
    recipient: str | None = None
    amount_eur: int | None = Field(default=None, ge=0)
    start: Date | None = None
    end: Date | None = None
    url: HttpUrl


class Partner(Contract):
    name: str = Field(min_length=1)
    kind: Literal["kunde", "pilot", "loi", "design_partner", "forschungspartner"]
    quote: str | None = None
    url: HttpUrl


class Patent(Contract):
    status: Literal["patent_angemeldet", "patent_erteilt"]
    title: str | None = None
    quote: str | None = None
    url: HttpUrl


class RawLead(Contract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    industry: Industry
    country: str | None = None
    location: str | None = None
    source_url: HttpUrl
    source_name: str | None = None
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


class EnrichedLead(RawLead):
    evidence: list[Evidence] = Field(default_factory=list)
    context_v2: ContextV2 | None = None
    founder_profiles: list[FounderProfile] = Field(default_factory=list)
    target_customers: str | None = None
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
    funding_status: Literal["vc_backed", "non_vc_funded", "unfunded", "funded", "conflicting", "unknown"] = "unknown"
    vc_status: Literal["confirmed", "reported_none", "conflicting", "unknown"] = "unknown"
    first_signal_date: Date | None = None
    # Scoring inputs (context step, 2026-11-20). Every scalar below has an Evidence entry with the same
    # `field` name carrying the source URL; list items carry their own URL. None/empty = not found.
    imprint_url: HttpUrl | None = None
    imprint_email: str | None = None                   # generic mailbox from the imprint (contact_email is a step-1 field)
    founding_year_hint: int | None = Field(default=None, ge=1900, le=2100)  # from a sourced sentence "… 2018 gegründet"
    legal_form: str | None = None                      # e.g. "GmbH", "UG (haftungsbeschränkt)", "keine"
    in_formation: bool | None = None                   # "i.G." / "in Gründung"
    managing_directors: list[str] = Field(default_factory=list)
    register_id: str | None = None                     # e.g. "HRB 12345 B, Amtsgericht Berlin"
    grants: list[Grant] = Field(default_factory=list)
    partners: list[Partner] = Field(default_factory=list)
    patents: list[Patent] = Field(default_factory=list)
    ip_status: Literal["keine", "patent_angemeldet", "patent_erteilt"] | None = None
    product_type: Literal["software", "plattform", "hardware", "hardware_software", "wirkstoff"] | None = None
    regulated_market: bool | None = None
    market_size_eur: int | None = Field(default=None, ge=0)
    business_model: Literal["b2b", "b2c", "b2b2c"] | None = None
    competitors: list[str] = Field(default_factory=list)
    in_databases: bool | None = None                   # Crunchbase/Dealroom profile found
    first_db_date: Date | None = None
    database_urls: list[HttpUrl] = Field(default_factory=list)
    first_web_capture: Date | None = None              # Wayback first capture of the website
    match_confidence: float | None = Field(default=None, ge=0, le=1)  # project/person -> company match
    enrichment_sources: list[str] = Field(default_factory=list)       # which lookups ran, e.g. ["impressum", "openalex"]
    enrichment_errors: list[str] = Field(default_factory=list)        # lookups that failed, with reason
    funding_stage: str | None = None
    founded_on: Date | None = None
    team_size: int | None = Field(default=None, ge=0)
    funding_total_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_funding_on: Date | None = None
    product_stage: str | None = None  # free text in demo fixtures; the context step emits the scoring enum (idee … am_markt)
    customer_count: int | None = Field(default=None, ge=0)
    annual_revenue_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    traction_notes: str | None = None


class EvaluatedLead(EnrichedLead):
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
