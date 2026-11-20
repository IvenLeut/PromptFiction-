"""Entirely fictional fixtures; no real startup or investment claims.

Three minimal leads per industry, used as the default provider/enricher/evaluator of
pipeline.discover / collect_context / evaluate_context when called with use_mock=True and no
provider (unit tests, tests/test_pipeline.py). The dashboard demo (run_pipeline, app.py) uses the
30-lead portfolio in demo_portfolio.py instead.
"""
from models import EnrichedLead, EvaluatedLead, Evidence, RawLead, SearchCriteria


def search(criteria: SearchCriteria) -> list[RawLead]:
    """Step-1 fixture: three fictional German leads of `criteria.industry`."""
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
            founders=["Demo-Gründerin", "Demo-Gründer"],
        )
        for index, city in enumerate(["Berlin", "München", "Hamburg"], start=1)
    ][:criteria.limit]


def enrich(lead: RawLead) -> EnrichedLead:
    """Step-2 fixture: one fictional evidence entry, no real research."""
    return EnrichedLead(
        **lead.model_dump(),
        evidence=[Evidence(source="Fiktive Recherche", url=lead.source_url,
                           finding="Angenommener Prototyp; keine reale Recherche.")],
        funding_stage="Pre-Seed (fiktiv)",
    )


def evaluate(lead: EnrichedLead) -> EvaluatedLead:
    """Step-3 fixture: scores rise with the lead index (index 3 ranks first)."""
    index = int(lead.id.rsplit("-", 1)[1])
    return EvaluatedLead(
        **lead.model_dump(), quality_score=70 + index * 5,
        overall_score=70 + index * 5, company_score=70 + index * 5,
        market_potential_score=80, risk_score=40,
        stage_classification="Pre-Seed", value_proposition="Fiktive Produktbeschreibung.",
        earliness_score=90 - index * 3, confidence_score=60,
        investment_thesis="Fiktive Investment-These zur Vorschau der Detailansicht.",
        risks=["Nur Testdaten; keine verifizierten Angaben."],
    )
