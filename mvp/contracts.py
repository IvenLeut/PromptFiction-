"""Versioned contracts for the demo workflow; unknown is never a numeric default."""
from datetime import date, datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(Contract):
    url: str
    title: str
    retrieved_at: str
    sha256: str
    kind: str = 'company'


class Fact(Contract):
    value: str
    source_url: str
    quote: str
    basis: str = 'rule_extraction'


class Dossier(Contract):
    id: str
    name: str
    website: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    facts: dict[str, Fact] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)
    identity_status: str = 'unresolved'
    earliest_founding: date | None = None
    latest_founding: date | None = None
    founding_basis: str | None = None
    issues: list[str] = Field(default_factory=list)
    # A discovery observation is never silently promoted to current context.
    refresh_status: str = 'not_requested'


class Criterion(Contract):
    key: str
    label: str
    weight: int
    points: int | None = Field(default=None, ge=0, le=100)
    reason: str
    facts: list[str] = Field(default_factory=list)


class Assessment(Contract):
    dossier: Dossier
    queue: Literal['ranked', 'research', 'excluded']
    reasons: list[str]
    stage: str
    score: float | None = None
    score_upper: float | None = None
    company_score: float | None = None
    market_score: float | None = None
    risk: str
    coverage: float
    criteria: list[Criterion]
    hypothesis: str
    next_steps: list[str]
    htgf_fit: str


class RunOptions(Contract):
    as_of: date = Field(default_factory=date.today)
    max_age_months: Literal[24, 36] = 24
    sectors: list[str] = Field(default_factory=lambda: ['AI / Software', 'ClimateTech', 'HealthTech', 'FinTech', 'Industrial / DeepTech'])
    mode: Literal['live', 'replay'] = 'live'
    limit: int = Field(default=15, ge=5, le=50)
    project_budget: int = Field(default=12, ge=0, le=733)


class Run(Contract):
    schema_version: str = 'mvp.1'
    rule_version: str = 'early-stage.2'
    id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    options: RunOptions
    input_hash: str
    source_snapshot_date: str
    assessments: list[Assessment]
    project_audit: list[dict]
    counts: dict[str, int]
    warnings: list[str]
    llm_calls: int = 0
