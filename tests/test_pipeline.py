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
    assert "founders" not in leads[0].model_dump()


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


def test_dashboard_flow():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()
    assert not app.exception
    next(b for b in app.button if b.label.endswith("Startups finden")).click().run()
    assert len(app.dataframe) == 1
    next(b for b in app.button if b.label == "Kontext erfassen").click().run()
    assert len(app.dataframe) == 2
    next(b for b in app.button if b.label == "Bewerten und sortieren").click().run()
    assert len(app.dataframe) == 3
    assert not app.exception
    next(b for b in app.button if b.label.endswith("Startups finden")).click().run()
    assert len(app.dataframe) == 1
    assert not app.exception


