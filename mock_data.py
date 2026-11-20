"""Entirely fictional fixtures; no real startup or investment claims."""
from models import EnrichedLead, EvaluatedLead, Evidence, Industry, RawLead, SearchCriteria


def search(criteria: SearchCriteria) -> list[RawLead]:
    return [
        RawLead(
            id=f"demo-{criteria.industry.name.lower()}-{index}",
            name=f"Demo {criteria.industry.value} {index}",
            description="Fiktives Early-Stage-Projekt zum Entwickeln der Schnittstellen.",
            industry=criteria.industry,
            country="DE",
            location=city,
            source_url=f"https://example.org/startup/{index}",
            country_evidence=Evidence(
                source="Fiktiver Demo-Datensatz",
                url=f"https://example.org/startup/{index}",
                finding=f"Fiktiver Standort: {city}, Deutschland.",
            ),
            is_demo=True,
        )
        for index, city in enumerate(["Berlin", "München", "Hamburg"], start=1)
    ][:criteria.limit]


def enrich(lead: RawLead) -> EnrichedLead:
    return EnrichedLead(
        **lead.model_dump(), founders=["Demo-Gründerin", "Demo-Gründer"],
        evidence=[Evidence(source="Fiktive Recherche", url=lead.source_url,
                           finding="Angenommener Prototyp; keine reale Recherche.")],
        funding_stage="Pre-Seed (fiktiv)",
    )


def evaluate(lead: EnrichedLead) -> EvaluatedLead:
    index = int(lead.id.rsplit("-", 1)[1])
    return EvaluatedLead(
        **lead.model_dump(), quality_score=70 + index * 5,
        earliness_score=90 - index * 3, confidence_score=60,
        investment_thesis="Fiktive Investment-These zur Vorschau der Detailansicht.",
        risks=["Nur Testdaten; keine verifizierten Angaben."],
    )
