from pathlib import Path
import pytest
from pydantic import ValidationError
import mock_data
from models import Industry, SearchCriteria
from pipeline import collect_context, discover, evaluate_context


def test_country_fixed():
    with pytest.raises(ValidationError):
        SearchCriteria(industry=Industry.AI, country="AT")


def test_discovery_filters_without_ranking():
    criteria = SearchCriteria(industry=Industry.AI)
    a, b, c = mock_data.search(criteria)
    foreign = a.model_copy(update={"id": "foreign", "country": "AT"})
    unknown = a.model_copy(update={"id": "unknown", "country_evidence": None})
    other = a.model_copy(update={"id": "other", "industry": Industry.HEALTH})
    leads = discover(criteria, provider=lambda _: [foreign, unknown, b, b, other, a])
    assert [x.id for x in leads] == [b.id, a.id]
    assert "quality_score" not in leads[0].model_dump()
    assert "founders" in leads[0].model_dump()


def test_stages():
    raw = discover(SearchCriteria(industry=Industry.CLIMATE))
    context = collect_context(raw)
    assert not context.issues
    assert [x.id for x in context.leads] == [x.id for x in raw]
    assert context.leads[0].team_size is None
    assert "quality_score" not in context.leads[0].model_dump()
    result = evaluate_context(context.leads)
    assert not result.issues
    assert [x.quality_score for x in result.leads] == [85, 80, 75]


def test_partial_failure():
    raw = discover(SearchCriteria(industry=Industry.AI))
    def enrich(lead):
        if lead.id == raw[0].id:
            raise RuntimeError("Provider unavailable")
        return mock_data.enrich(lead)
    result = collect_context(raw, enricher=enrich)
    assert len(result.leads) == 2
    assert result.issues[0].lead_id == raw[0].id


def test_no_live_fallback():
    with pytest.raises(NotImplementedError):
        discover(SearchCriteria(industry=Industry.AI), use_mock=False)


def test_no_mixing():
    with pytest.raises(ValueError):
        collect_context(discover(SearchCriteria(industry=Industry.AI)), use_mock=False)


def test_preserve_geography():
    raw = discover(SearchCriteria(industry=Industry.AI))
    result = collect_context(raw, enricher=lambda x: mock_data.enrich(x).model_copy(update={"country": "AT"}))
    assert not result.leads
    assert len(result.issues) == 3


def test_full_category_pipeline():
    from pipeline import run_pipeline
    from models import AnalysisRun
    seen = []
    result = run_pipeline(SearchCriteria(industry=Industry.HEALTH),
                          on_progress=lambda percent, message: seen.append(percent))
    assert result.discovered_count == result.enriched_count == len(result.result.leads) == 30
    assert seen == [0, 33, 66, 100]
    assert all(x.industry == Industry.HEALTH and x.country == "DE" for x in result.result.leads)
    assert not result.result.issues
    assert result.result.leads[0].overall_score >= result.result.leads[-1].overall_score
    assert AnalysisRun.model_validate_json(result.model_dump_json()) == result


def test_step_one_contract_survives_processing():
    from demo_portfolio import demo_search, demo_enrich, demo_evaluate
    from models import RawLead
    raw = demo_search(SearchCriteria(industry=Industry.AI, limit=1))[0]
    assert {"founders", "contact_email", "website", "founding_year", "founding_month", "location"} <= set(raw.model_dump())
    assert "overall_score" not in raw.model_dump()
    enriched = demo_enrich(raw)
    assert "stage_classification" not in enriched.model_dump()
    evaluated = demo_evaluate(enriched)
    assert evaluated.model_dump(include=set(RawLead.model_fields)) == raw.model_dump()
    assert evaluated.value_proposition and evaluated.investment_thesis


def test_pipeline_preserves_partial_errors():
    from pipeline import run_pipeline
    from demo_portfolio import demo_enrich
    def sometimes(lead):
        if lead.id.endswith("01"):
            raise RuntimeError("Unavailable")
        return demo_enrich(lead)
    result = run_pipeline(SearchCriteria(industry=Industry.FINTECH, limit=3), enricher=sometimes)
    assert result.discovered_count == 3
    assert result.enriched_count == len(result.result.leads) == 2
    assert len(result.result.issues) == 1