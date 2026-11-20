from models import RawLead, SearchCriteria


def search(criteria: SearchCriteria) -> list[RawLead]:
    """Integrate discovery provider here; return source-backed basic metadata.

    Do not enrich, score or rank. Country DE must refer to a German base,
    not merely a German-language website or a .de domain.
    """
    raise NotImplementedError("Noch kein echter Sourcing-Anbieter angebunden. Demo-Modus verwenden.")
