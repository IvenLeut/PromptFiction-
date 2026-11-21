from analyst_store import save_decision, load_decisions
from demo_portfolio import get_demo_result
from screening import filter_leads, high_priority, review_status
import pytest


def test_persistence_update_and_namespace():
    save_decision("demo", "id-1", "Contact", "Call next week", "Relevant team")
    assert load_decisions("demo")["id-1"]["notes"] == "Call next week"
    assert load_decisions("live") == {}
    save_decision("demo", "id-1", "Watchlist", "Wait for prototype", "Too early")
    assert load_decisions("demo")["id-1"]["decision"] == "Watchlist"
    with pytest.raises(ValueError):
        save_decision("demo", "id-1", "Reject", "", " ")


def test_exclusion_and_unknown_do_not_disappear_behind_scores():
    lead = get_demo_result().leads[0].model_copy(update={"overall_score": 99, "fund_fit_score": 99,
        "earliness_score": 99, "eligibility_status": "Eligible", "hard_exclusions": ["Mandate"]})
    decisions = {lead.id: {"decision": "Contact"}}
    assert review_status(lead, decisions) == "Excluded"
    assert not high_priority(lead, decisions)
    unknown = lead.model_copy(update={"hard_exclusions": [], "fund_fit_score": None})
    assert not high_priority(unknown, {})


def test_filters_and_missing_sort_values():
    leads = get_demo_result().leads
    chosen = leads[0]
    assert all(x.industry == chosen.industry for x in filter_leads(leads, {}, search=chosen.industry.value))
    assert all(x.location == chosen.location for x in filter_leads(leads, {}, locations=[chosen.location]))
    assert all(x.eligibility_status == "Unknown" for x in filter_leads(leads, {}, fit="Ungeklärt"))
    unknown = chosen.model_copy(update={"id": "missing", "discovered_at": None})
    assert filter_leads([unknown, chosen], {}, sort_by="Entdeckungsdatum")[-1].id == "missing"


def test_decision_ui_roundtrip():
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(x for x in app.button if x.label == "Analyse starten").click().run()
    lead = app.session_state.analysis.result.leads[0]
    app.query_params["startup"] = lead.id
    app.run()
    app.radio[0].set_value("Watchlist")
    next(x for x in app.text_area if x.label == "Analysten-Notizen").set_value("Test note")
    next(x for x in app.text_area if x.label == "Begründung der Entscheidung").set_value("Verify market")
    next(x for x in app.button if x.label == "Entscheidung speichern").click().run()
    assert not app.exception
    assert load_decisions("demo")[lead.id]["decision"] == "Watchlist"
    app.run()
    assert app.radio[0].value == "Watchlist"
    assert next(x for x in app.text_area if x.label == "Analysten-Notizen").value == "Test note"
