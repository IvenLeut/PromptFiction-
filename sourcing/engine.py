"""Step-1 pipeline provider: `search(criteria)` over the Förderkatalog sourcing (sourcing/mapping.py).

Alternative input (Leonard/Iven, cockpit branch): an explicit FounderRadar screening export
(`ScreeningReport`, JSON with `criteria` + `confirmed`). `read_context_leads` reads either a RawLead array or
such a report (used by `python -m context`); `search` uses the report instead of the Förderkatalog when
`FOUNDERRADAR_SCREENING_REPORT` points to one.
"""
import calendar
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, TypeAdapter, model_validator

from context.cache import Cache
from models import CONTACT_EMAIL_PATTERN, Contract, Evidence, Industry, RawLead, SearchCriteria, SourceSignal
from sourcing.foekat_export import DEFAULT_PREFIXES, DEFAULT_SINCE, ExportError
from sourcing.mapping import BASIS_ORDER, run


logger = logging.getLogger(__name__)

SINCE_ENV = "FOEKAT_SINCE"
SCREENING_ENV = "FOUNDERRADAR_SCREENING_REPORT"


class SourcingError(RuntimeError):
    """Total failure of the discovery source; the pipeline reports it instead of showing invented data."""


class SourcingLeads(list):
    """The leads `search` returns (a plain list for every caller) plus the export's completeness.

    `complete` is False when the catalogue export could not be fully validated; the leads are then the
    validated part only and `warnings` says which queries fell short."""

    def __init__(self, leads=(), *, complete: bool = True, warnings: list[str] | None = None):
        super().__init__(leads)
        self.complete = complete
        self.warnings = list(warnings or [])


def since_default() -> date:
    """Project start filter: FOEKAT_SINCE (YYYY-MM-DD) or 2024-01-01."""
    value = os.environ.get(SINCE_ENV)
    return date.fromisoformat(value) if value else DEFAULT_SINCE


def search(criteria: SearchCriteria, *, since: date | None = None, prefixes: tuple[str, ...] = DEFAULT_PREFIXES,
           cache: Cache | None = None, fetch=None, include_unclassified: bool = False,
           as_of: date | None = None) -> SourcingLeads:
    """Integrate discovery provider here; return source-backed basic metadata.

    Do not enrich, score or rank. Country DE must refer to a German base,
    not merely a German-language website or a .de domain.

    Provider: EXIST projects (FKZ 03EF*/03EG*) from the Förderkatalog des Bundes via its CSV export
    (sourcing/foekat_export.py, sourcing/FOEKAT.md). Returns the leads of `criteria.industry` whose industry
    was classified from the project title (basis "thema") first, then those classified only from the
    institute/recipient name (basis "institut"); within a basis by priority desc, project start desc, id
    (sourcing/mapping.py). Leads without any keyword hit (basis "default", programme default industry) are
    not members of an industry and are returned only with `include_unclassified=True` (last). Note: the CLI
    (`python -m sourcing foekat`) includes them by default; this function excludes them by default because
    the pipeline asks for members of one industry. At most `criteria.limit` leads, cut after sorting.
    Country DE is backed by the catalogue row (Staat of recipient/executing unit). Responses come from
    `.cache/context.db` when present. `as_of` is the priority reference date (default: retrieval date of
    the export).

    Raises SourcingError on total failure (any ExportError, or an incomplete export without a single
    validated row). An incomplete export with validated rows returns those leads, logs a warning and sets
    `complete=False` and `warnings` on the returned SourcingLeads.
    """
    if screening := os.getenv(SCREENING_ENV):
        return _screening_search(Path(screening), criteria)
    try:
        result = run(prefixes, since or since_default(), fetch=fetch, cache=cache if cache is not None else Cache(),
                     as_of=as_of)
    except ExportError as exc:
        raise SourcingError("Förderkatalog-Sourcing fehlgeschlagen: %s" % exc) from exc
    export = result.export
    if not export.rows and not export.complete:
        raise SourcingError("Förderkatalog-Sourcing ohne validierte Zeilen: " + "; ".join(export.warnings))
    if not export.complete:
        logger.warning("Förderkatalog-Export unvollständig, nur validierte Zeilen verwendet (%d): %s",
                       len(export.rows), "; ".join(export.warnings))
    found = [lead for lead in result.leads if lead.industry == criteria.industry
             and (include_unclassified or result.info[lead.id].basis != "default")]
    found.sort(key=lambda lead: (BASIS_ORDER[result.info[lead.id].basis], result.info[lead.id].sort_key()))
    return SourcingLeads(found[:criteria.limit], complete=export.complete, warnings=export.warnings)


class ScreeningCriteria(Contract):
    industry: Industry
    country: Literal["DE"] = "DE"
    limit: int | None = None
    as_of: date
    window_start: date | None = None
    window_end: date | None = None

    @property
    def start(self):
        if self.window_start is not None:
            return self.window_start
        year = max(1, self.as_of.year - 3)
        return self.as_of.replace(year=year, day=min(self.as_of.day, calendar.monthrange(year, self.as_of.month)[1]))


class ScreeningLead(RawLead):
    country: Literal["DE"]
    country_evidence: Evidence
    location: str = Field(min_length=1)
    website: HttpUrl
    founders: list[str] = Field(min_length=1)
    contact_email: str = Field(
        pattern=CONTACT_EMAIL_PATTERN,
        validation_alias=AliasChoices("email", "contact_email"),
    )
    founding_year: int = Field(ge=1800, le=2100)
    founding_month: int = Field(ge=1, le=12)
    founding_country: Literal["DE"]

    @model_validator(mode="after")
    def check_evidence(self):
        if self.is_demo:
            raise ValueError("Der Screening-Bericht enthält einen Demo-Lead.")
        if not self.name.strip() or not self.location.strip() or any(not item.strip() for item in self.founders):
            raise ValueError("Im Screening-Bericht fehlen Firmenname, Sitz oder Gründernamen.")
        required = ("name", "website", "founders", "email", "founding_year", "founding_month",
                    "founding_country", "country", "location", "industry")
        if any(not self.field_evidence.get(field) for field in required):
            raise ValueError("Im Screening-Bericht fehlen Pflichtbelege.")
        mailbox, domain = self.contact_email.rsplit("@", 1)
        if (not mailbox or mailbox.startswith(".") or mailbox.endswith(".") or ".." in mailbox
                or any(not label or label.startswith("-") or label.endswith("-") for label in domain.split("."))):
            raise ValueError("Ungültige geschäftliche E-Mail-Adresse im Screening-Bericht.")
        pattern = rf"(?<![\w.%+-]){re.escape(self.contact_email)}(?![\w@-]|\.[\w-])"
        if not any(re.search(pattern, item.finding, re.I) for item in self.field_evidence["email"]):
            raise ValueError("Die E-Mail-Adresse ist im Screening-Bericht unbelegt.")
        if self.country_evidence not in self.field_evidence["country"]:
            raise ValueError("Der Deutschland-Beleg fehlt in den Feldbelegen des Screening-Berichts.")
        return self


class ScreeningReport(Contract):
    criteria: ScreeningCriteria
    confirmed: list[ScreeningLead]
    keyword_version: str
    review_count: int = 0
    excluded_count: int = 0
    statuses: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_rows(self):
        end = self.criteria.window_end or self.criteria.as_of
        if not self.criteria.start <= end <= self.criteria.as_of:
            raise ValueError("Ungültiges Gründungsfenster im Screening-Bericht.")
        identities = set()
        for lead in self.confirmed:
            if lead.id in identities:
                raise ValueError("Doppelte Lead-ID im Screening-Bericht.")
            identities.add(lead.id)
            y, m = lead.founding_year, lead.founding_month
            first = date(y, m, lead.founded_day or 1)
            last = date(y, m, lead.founded_day or calendar.monthrange(y, m)[1])
            if lead.industry != self.criteria.industry or first < self.criteria.start or last > end:
                raise ValueError(f"{lead.id}: Branche oder Gründungsdatum liegt außerhalb des Screening-Auftrags.")
        return self

    def leads(self):
        result = []
        for row in self.confirmed:
            data = row.model_dump()
            data["screening_as_of"] = self.criteria.as_of
            if not row.source_name:
                data["source_name"] = row.field_evidence["name"][0].source
            date_evidence = {e.evidence_id: e for entries in row.field_evidence.values() for e in entries
                             if e.document_date and e.document_date <= self.criteria.as_of}
            data["signals"] = [*row.signals, *(
                SourceSignal(source=e.source, type="screening", url=e.url, date=e.document_date,
                             evidence=e.finding, subject_lead_id=row.id) for e in date_evidence.values()
            )]
            result.append(RawLead.model_validate(data))
        return result


def read_screening_report(path: Path) -> ScreeningReport:
    return ScreeningReport.model_validate_json(path.read_bytes())


def read_context_leads(path: Path) -> list[RawLead]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and "confirmed" in data:
        return ScreeningReport.model_validate(data).leads()
    return TypeAdapter(list[RawLead]).validate_python(data)


def _screening_search(path: Path, criteria: SearchCriteria) -> SourcingLeads:
    try:
        report = read_screening_report(path)
    except OSError as exc:
        raise ValueError("Der konfigurierte Screening-Export ist nicht lesbar.") from exc
    if report.criteria.industry != criteria.industry:
        raise ValueError("Die gewählte Branche stimmt nicht mit dem konfigurierten Screening-Export überein.")
    return SourcingLeads(report.leads())
