"""Common result type of the enrichment modules (see context/ENRICHMENT.md)."""
from __future__ import annotations

from dataclasses import dataclass, field

from models import Evidence, SourceSignal


@dataclass
class Lookup:
    fields: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    signals: list[SourceSignal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, value, *, url: str, finding: str, source: str, source_date=None) -> None:
        """Set a field and attach the evidence that backs it in one step."""
        self.fields[name] = value
        self.evidence.append(Evidence(field=name, url=url, finding=finding[:1000], source=source, source_date=source_date))

    def merge(self, other: "Lookup") -> "Lookup":
        for name, value in other.fields.items():
            self.fields.setdefault(name, value)
        self.evidence.extend(other.evidence)
        self.signals.extend(other.signals)
        self.errors.extend(other.errors)
        return self
