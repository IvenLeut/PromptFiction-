"""Shared contracts. Changes should be agreed across all module owners."""
from enum import Enum
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


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


class Evidence(Contract):
    source: str = Field(min_length=1)
    url: HttpUrl
    finding: str = Field(min_length=1)
    field: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RawLead(Contract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    industry: Industry
    country: str | None = None
    location: str | None = None
    source_url: HttpUrl
    country_evidence: Evidence | None = None
    is_demo: bool = False


class EnrichedLead(RawLead):
    website: HttpUrl | None = None
    founders: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    funding_stage: str | None = None
    founded_on: date | None = None
    team_size: int | None = Field(default=None, ge=0)
    funding_total_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_funding_on: date | None = None
    product_stage: str | None = None
    customer_count: int | None = Field(default=None, ge=0)
    annual_revenue_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    traction_notes: str | None = None


class EvaluatedLead(EnrichedLead):
    quality_score: float = Field(ge=0, le=100)
    earliness_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
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
