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


def test_no_live_fallback(monkeypatch):
    # The sourcing placeholder was replaced by the Förderkatalog sourcing; a failed live discovery must still raise.
    from context.foekat import FoekatError
    from sourcing.engine import SourcingError

    class Offline:
        def fetch(self, *args, **kwargs):
            raise FoekatError("URLError")
    monkeypatch.setenv("CONTEXT_CACHE", "off")
    monkeypatch.setattr("sourcing.foekat_export.Session", Offline)
    found = []
    with pytest.raises(SourcingError):
        found = discover(SearchCriteria(industry=Industry.AI), use_mock=False)
    assert found == []


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

def _evaluated(lead_id, score, reason=None):
    from demo_portfolio import demo_enrich, demo_evaluate, demo_search
    lead = demo_evaluate(demo_enrich(demo_search(SearchCriteria(industry=Industry.AI, limit=1))[0]))
    return lead.model_copy(update={"id": lead_id, "overall_score": score, "prioritization_reason": reason})


def test_lead_priority_parsing():
    from pipeline import lead_priority
    assert lead_priority(_evaluated("a", 1, "Priorität 90: EXIST-Forschungstransfer.")) == 90
    assert lead_priority(_evaluated("a", 1, "Priorität 250: zu hoch.")) == 100
    assert lead_priority(_evaluated("a", 1, "EXIST, Priorität 90: nicht am Anfang.")) == 0
    assert lead_priority(_evaluated("a", 1, "Priorität hoch")) == 0
    assert lead_priority(_evaluated("a", 1)) == 0


def test_ranking_ties_broken_by_priority_missing_score_last():
    from pipeline import ranking_key
    leads = [_evaluated("a", 70, "Priorität 40: x."), _evaluated("b", None, "Priorität 99: x."),
             _evaluated("c", 70, "Priorität 80: x."), _evaluated("d", 80), _evaluated("e", 70)]
    assert [x.id for x in sorted(leads, key=ranking_key)] == ["d", "c", "a", "e", "b"]


def test_evaluate_context_sorts_by_ranking_key():
    leads = [_evaluated("a", 70, "Priorität 40: x."), _evaluated("c", 70, "Priorität 80: x.")]
    result = evaluate_context(leads, evaluator=lambda lead: lead)
    assert [x.id for x in result.leads] == ["c", "a"]


def test_demo_order_unchanged_by_priority_tie_break():
    from pipeline import run_pipeline
    for industry in Industry:
        leads = run_pipeline(SearchCriteria(industry=industry)).result.leads
        assert all(x.prioritization_reason is None for x in leads)
        old = sorted(leads, key=lambda x: (x.overall_score is None, -(x.overall_score or 0), x.id))
        assert [x.id for x in leads] == [x.id for x in old]


def _live_lead(index, priority):
    lead = mock_data.search(SearchCriteria(industry=Industry.AI))[0]
    return lead.model_copy(update={"id": f"live-{index}", "is_demo": False,
                                   "prioritization_reason": f"Priorität {priority}: Test."})


def test_live_discover_keeps_provider_order_and_limit():
    # sourcing.engine.search sorts by priority and cuts at criteria.limit; discover must neither re-sort nor cut again.
    criteria = SearchCriteria(industry=Industry.AI, limit=3)
    sourced = [_live_lead(1, 90), _live_lead(2, 95), _live_lead(3, 40)]
    assert [x.id for x in discover(criteria, use_mock=False, provider=lambda c: sourced[:c.limit])] == \
        ["live-1", "live-2", "live-3"]
    dropped = [sourced[0], sourced[1].model_copy(update={"country_evidence": None}), sourced[2]]
    assert [x.id for x in discover(criteria, use_mock=False, provider=lambda _: dropped)] == ["live-1", "live-3"]
    uncapped = sourced + [_live_lead(4, 99)]
    assert [x.id for x in discover(criteria, use_mock=False, provider=lambda _: uncapped)] == \
        ["live-1", "live-2", "live-3"]
    with pytest.raises(ValueError):
        discover(criteria, use_mock=False, provider=lambda _: mock_data.search(criteria))


@pytest.mark.parametrize("has_vc, scored", [(None, True), (False, True), (True, False)])
def test_live_vc_gate(has_vc, scored):
    lead = mock_data.enrich(_live_lead(1, 50).model_copy(update={"has_vc": has_vc}))
    lead = lead.model_copy(update={"is_demo": False})
    seen = {}

    def evaluator(scoring, *, lead):
        seen["lead"] = lead.id
        return dict(overall_score=50, company_score=50, market_potential_score=50, risk_score=50,
                    stage_classification="Unbekannt", value_proposition="Test.", investment_thesis="Test.")
    result = evaluate_context([lead], use_mock=False, evaluator=evaluator)
    assert [x.id for x in result.leads] == (["live-1"] if scored else [])
    assert (seen.get("lead") == "live-1") is scored
    if not scored:
        assert result.issues[0].message == "VC-Finanzierung gefunden oder widersprüchlich gemeldet."


def test_failed_evaluation_is_logged_with_type(caplog):
    lead = mock_data.enrich(_live_lead(1, 50))
    def broken(scoring):
        raise KeyError("x")
    result = evaluate_context([lead], use_mock=False, evaluator=broken)
    assert result.issues[0].message == "Bewertung fehlgeschlagen. Details im Server-Log."
    assert "live-1" in caplog.text and "KeyError" in caplog.text
