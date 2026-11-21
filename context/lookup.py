"""Common result type and shared conventions of the enrichment modules (see context/ENRICHMENT.md)."""
from __future__ import annotations

from dataclasses import dataclass, field

from models import Evidence, SourceSignal

# --- Evidence/SourceSignal `source` labels ---------------------------------------------------------
# Defined once; the string values are matched downstream and must not change:
# evaluation/engine.py checks `startswith("Ollama-Zitat")` and `"(Erwähnung)" in source`,
# context/classify.py and context/engine.py check `startswith(SOURCE_IDW_MENTION)`.
SOURCE_FOEKAT = "Förderkatalog"
SOURCE_IMPRINT = "Impressum"
SOURCE_IDW = "idw"
SOURCE_IDW_MENTION = "idw (Erwähnung)"     # press round-up that names the lead once: context, not a signal
SOURCE_OPENALEX = "OpenAlex"
SOURCE_PATENTS = "Google Patents"
SOURCE_WAYBACK_CDX = "Wayback CDX"          # evidence derived from a CDX index query
SOURCE_WAYBACK = "Wayback"                  # signal pointing at the archived page itself
SOURCE_MODEL = "ollama"                     # classifier output (context.classify)
SOURCE_WEBSITE = "Unternehmenswebsite"
SOURCE_ORIGINAL = "Fundquelle"
SOURCE_WEBSITE_MATCH = "Website-Abgleich"     # context/website_match.py: project name -> company website
SOURCE_PROJECT_PAGE = "Projektseite (Hochschule)"  # university/institute page about the project, not a company site
SOURCE_SOURCING = "Sourcing"                # fallback when a lead carries no source_name
MODEL_QUOTE_PREFIX = "Ollama-Zitat aus "    # + source of the quoted signal (context.ollama via engine)

# --- Namesake windows ------------------------------------------------------------------------------
# A dated hit that precedes the earliest sourced signal (e.g. the EXIST project start) by more than this
# belongs, most likely, to a namesake. The windows differ on purpose:
# * web: a start-up's domain or Crunchbase/Dealroom profile appears with or shortly before the project;
#   a capture a year earlier is a parked domain or a slug clash ("sensai" on Crunchbase in 2019).
# * press: research groups publish results (idw press releases, "X wurde gegründet" sentences) one to two
#   years before the spin-off's EXIST project, so a wider window keeps those genuine articles.
WEB_NAMESAKE_YEARS = 1      # context/wayback.py
PRESS_NAMESAKE_YEARS = 2    # context/engine.py: idw articles and founding-year hints


@dataclass
class Lookup:
    """Result of one lookup: fields for EnrichedLead, their evidence, texts for later steps, errors."""
    fields: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    signals: list[SourceSignal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, value, *, url: str, finding: str, source: str, source_date=None) -> None:
        """Set a field and attach the evidence that backs it in one step."""
        self.fields[name] = value
        self.evidence.append(Evidence(field=name, url=url, finding=finding[:1000], source=source, source_date=source_date))

    def merge(self, other: Lookup) -> Lookup:
        """Add `other` into this lookup; fields already set here win."""
        for name, value in other.fields.items():
            self.fields.setdefault(name, value)
        self.evidence.extend(other.evidence)
        self.signals.extend(other.signals)
        self.errors.extend(other.errors)
        return self
