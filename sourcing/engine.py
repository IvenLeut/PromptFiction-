import os
from datetime import date

from context.cache import Cache
from models import RawLead, SearchCriteria
from sourcing.foekat_export import DEFAULT_SINCE, ExportError
from sourcing.mapping import run

SINCE_ENV = "FOEKAT_SINCE"


class SourcingError(RuntimeError):
    """Total failure of the discovery source; the pipeline reports it instead of showing invented data."""


def since_default() -> date:
    """Project start filter: FOEKAT_SINCE (YYYY-MM-DD) or 2024-01-01."""
    value = os.environ.get(SINCE_ENV)
    return date.fromisoformat(value) if value else DEFAULT_SINCE


def search(criteria: SearchCriteria, *, since: date | None = None, prefixes=("03EF", "03EG"),
           cache: Cache | None = None, fetch=None) -> list[RawLead]:
    """Integrate discovery provider here; return source-backed basic metadata.

    Do not enrich, score or rank. Country DE must refer to a German base,
    not merely a German-language website or a .de domain.

    Provider: EXIST projects (FKZ 03EF*/03EG*) from the Förderkatalog des Bundes via its CSV export
    (sourcing/foekat_export.py, sourcing/FOEKAT.md). Returns the leads of `criteria.industry`, newest
    project start first, then id; country DE is backed by the catalogue row (Staat of recipient/executing
    unit). Responses come from `.cache/context.db` when present. Raises SourcingError on total failure.
    """
    try:
        result = run(prefixes, since or since_default(), fetch=fetch, cache=cache if cache is not None else Cache())
    except ExportError as exc:
        raise SourcingError("Förderkatalog-Sourcing fehlgeschlagen: %s" % exc) from exc
    if not result.export.rows and not result.export.complete:
        raise SourcingError("Förderkatalog-Sourcing ohne validierte Zeilen: " + "; ".join(result.export.warnings))
    return [lead for lead in result.leads if lead.industry == criteria.industry]
