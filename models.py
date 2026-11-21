"""Shared contracts. Changes should be agreed across all module owners.

Import direction (no cycles; each module imports only modules listed before it):
    research_models -> scoring_models -> models -> scoring_market -> scoring_input -> pipeline
research_models and scoring_models never import models; scoring_input imports models (EnrichedLead).

Field order matters: pydantic uses it for model_dump and JSON-schema property order (examples/*.json,
tests/test_contracts.py). Do not reorder fields; add new ones at the end of their model.
Class docstrings become schema "description"s, so classes are documented with comments here.
"""
from enum import Enum
from datetime import date as Date
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from research_models import ContextV2, Contract, Evidence
from scoring_models import ScoringInput


# Step-1 category the user asks for.
class Industry(str, Enum):
    AI = "AI / Software"
    CLIMATE = "ClimateTech"
    HEALTH = "HealthTech"
    FINTECH = "FinTech"
    INDUSTRIAL = "Industrial / DeepTech"


# Step-1 request (dashboard -> pipeline.discover).
class SearchCriteria(Contract):
    industry: Industry
    country: Literal["DE"] = "DE"
    limit: int = Field(default=30, ge=1, le=200)


# Step 1/2: one captured source text; scoring_input.py parses labelled lines from `evidence`.
class SourceSignal(Contract):
    source: str = Field(min_length=1)
    type: str = Field(min_length=1)
    url: HttpUrl
    date: Date | None = None
    evidence: str = Field(min_length=1)
    subject_lead_id: str | None = None


class Grant(Contract):
    """Public funding (e.g. EXIST) with its catalogue URL."""
    programme: str = Field(min_length=1)
    reference: str | None = None  # Förderkennzeichen
    recipient: str | None = None
    amount_eur: int | None = Field(default=None, ge=0)
    start: Date | None = None
    end: Date | None = None
    url: HttpUrl


# Step 2: a named customer/pilot/research partner, backed by a quote and URL.
class Partner(Contract):
    name: str = Field(min_length=1)
    kind: Literal["kunde", "pilot", "loi", "design_partner", "forschungspartner"]
    quote: str | None = None
    url: HttpUrl


# Step 2 (context/patents): a filed or granted patent.
class Patent(Contract):
    status: Literal["patent_angemeldet", "patent_erteilt"]
    title: str | None = None
    quote: str | None = None
    url: HttpUrl


# Step 1 output (sourcing). Steps 2-3 must not change these fields (pipeline._preserve).
CONTACT_EMAIL_PATTERN = r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


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
    contact_email: str | None = Field(default=None, pattern=CONTACT_EMAIL_PATTERN)
    founding_year: int | None = Field(default=None, ge=1800, le=2100)
    founding_month: int | None = Field(default=None, ge=1, le=12)
    founded_day: int | None = Field(default=None, ge=1, le=31)
    founding_country: Literal["DE"] | None = None
    field_evidence: dict[str, list[Evidence]] = Field(default_factory=dict)
    screening_as_of: Date | None = None
    has_vc: bool | None = None
    signals: list[SourceSignal] = Field(default_factory=list)
    prioritization_reason: str | None = None  # "Priorität N: …" from sourcing; pipeline.lead_priority parses N
    htgf_sector: Literal["digital_tech", "industrial_deep_tech", "climate_tech",
                         "life_sciences", "chemie_materialien"] | None = None

    @model_validator(mode="after")
    def validate_founding_day(self):
        if self.founded_day is not None:
            if self.founding_year is None or self.founding_month is None:
                raise ValueError("Ein Gründungstag benötigt Monat und Jahr.")
            Date(self.founding_year, self.founding_month, self.founded_day)
        return self


# Step 2 (context/openalex, context/team): a founder with optional research profile; the cockpit fields
# (relevant_experience, distinctive_skills, evidence) come from the investment-cockpit branch.
class FounderProfile(Contract):
    qualifications: str | None = None
    name: str = Field(min_length=1)
    role: str | None = None
    background: Literal["tech", "business", "beides"] | None = None
    # Enrichment (context step). Each value is backed by its own URL; None = not found, never guessed.
    institution: str | None = None
    prior_experience: list[Literal["fruehere_gruendung", "industrie"]] = Field(default_factory=list)
    openalex_url: HttpUrl | None = None
    works_total: int | None = Field(default=None, ge=0)
    works_in_field: int | None = Field(default=None, ge=0)
    match_confidence: float | None = Field(default=None, ge=0, le=1)
    source_url: HttpUrl | None = None
    relevant_experience: str | None = None
    distinctive_skills: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class FundingEvent(Contract):
    announced_on: Date | None = None
    amount_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    investors: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


# Step 2 output (context). Sections below are grouped by comment only; the field order is part of the
# contract (see module docstring) and therefore not regrouped.
class EnrichedLead(RawLead):
    # --- Step-1 fields are inherited from RawLead. ---
    # --- Evidence and context_v2 / scoring handoff (context owner) ---
    evidence: list[Evidence] = Field(default_factory=list)
    context_v2: ContextV2 | None = None
    scoring_sources: list[SourceSignal] | None = None
    scoring_input: ScoringInput | None = None          # handoff to step 3; rebuilt by pipeline in live mode
    # --- Legacy context fields (free-text dossier, valuation inputs, status) ---
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
    # --- Enrichment for scoring (scoring owner) ---
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
    in_databases: bool | None = None                   # Crunchbase/Dealroom profile found
    first_db_date: Date | None = None
    database_urls: list[HttpUrl] = Field(default_factory=list)
    first_web_capture: Date | None = None              # Wayback first capture of the website
    match_confidence: float | None = Field(default=None, ge=0, le=1)  # project/person -> company match
    enrichment_sources: list[str] = Field(default_factory=list)       # which lookups ran, e.g. ["impressum", "openalex"]
    enrichment_errors: list[str] = Field(default_factory=list)        # lookups that failed, with reason
    # --- Legacy context fields, continued (demo fixtures and dashboard deep dive) ---
    funding_stage: str | None = None
    founded_on: Date | None = None
    team_size: int | None = Field(default=None, ge=0)
    funding_total_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_funding_on: Date | None = None
    product_stage: str | None = None  # free text in demo fixtures; the context step emits the scoring enum (idee … am_markt)
    customer_count: int | None = Field(default=None, ge=0)
    annual_revenue_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    traction_notes: str | None = None
    # Step 2 (context/website_match.py, 2026-11-21): company website found for a lead without a step-1 `website`
    # (RawLead.website must not change, pipeline._preserve). Evidence field="matched_website"; see match_confidence.
    matched_website: HttpUrl | None = None


# Cockpit (Iven): one key strength/risk with its rationale and evidence.
class InvestmentArgument(Contract):
    statement: str
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)


# Step 3 output of the evaluator (evaluation/engine.py or demo), merged with the dossier.
class EvaluationScores(Contract):
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
    earliness_delta_months: int | None = Field(default=None, ge=0)
    scoring_status: Literal["bewertet", "zurueck_an_sourcing"] | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    investment_thesis: str
    risks: list[str] = Field(default_factory=list)


# Step 3 result row: dossier + scores; ranked by pipeline.ranking_key.
class EvaluatedLead(EvaluationScores, EnrichedLead):
    pass


# A lead that failed or was held back in step 2 or 3; `message` is shown to users (German).
class PipelineIssue(Contract):
    lead_id: str
    stage: Literal["context", "evaluation"]
    message: str


# Step 3 result: ranked leads plus issues.
class ResearchResult(Contract):
    leads: list[EvaluatedLead] = Field(default_factory=list)
    issues: list[PipelineIssue] = Field(default_factory=list)


# Step 2 result (examples/context-schema.json).
class ContextResult(Contract):
    leads: list[EnrichedLead] = Field(default_factory=list)
    issues: list[PipelineIssue] = Field(default_factory=list)


# Dashboard contract for one run of steps 1-3 (examples/analysis-schema.json).
class AnalysisRun(Contract):
    schema_version: Literal["2.0"] = "2.0"
    criteria: SearchCriteria
    mode: Literal["demo", "live"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discovered_count: int = Field(ge=0)
    enriched_count: int = Field(ge=0)
    result: ResearchResult
