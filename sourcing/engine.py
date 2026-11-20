"""Read confirmed companies from an explicit FounderRadar screening export."""
import calendar
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, TypeAdapter, model_validator

from models import CONTACT_EMAIL_PATTERN, Contract, Evidence, Industry, RawLead, SearchCriteria, SourceSignal


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


def search(criteria: SearchCriteria) -> list[RawLead]:
    path = os.getenv("FOUNDERRADAR_SCREENING_REPORT")
    if not path:
        raise NotImplementedError("Live-Sourcing benötigt einen Screening-Export in FOUNDERRADAR_SCREENING_REPORT.")
    try:
        report = read_screening_report(Path(path))
    except OSError as exc:
        raise ValueError("Der konfigurierte Screening-Export ist nicht lesbar.") from exc
    if report.criteria.industry != criteria.industry:
        raise ValueError("Die gewählte Branche stimmt nicht mit dem konfigurierten Screening-Export überein.")
    return report.leads()
