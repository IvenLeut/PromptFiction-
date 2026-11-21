import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from streamlit.testing.v1 import AppTest

from analyst_store import load_decisions, load_history, save_decision
from cockpit_data import adapt, load_payload
from cockpit_service import email_draft, start_analysis, load_workspace
from cockpit_visuals import pipeline_scatter, stage_bars, score_profile, evidence_coverage
from models import Industry

ROOT = Path(__file__).resolve().parents[1]


def button(app, label):
    return next(x for x in app.button if x.label == label)


def workspace():
    app = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30).run()
    button(app, "Start analysis").click().run()
    assert not app.exception
    return app


def test_category_pipeline_navigation_tracking_and_reload():
    app = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30).run()
    assert app.title[0].value == "Choose your investment focus"
    assert not app.get("file_uploader")
    next(x for x in app.radio if x.label == "Sector").set_value(Industry.CLIMATE)
    button(app, "Start analysis").click().run()
    assert not app.exception
    assert app.title[0].value == "Investment overview"
    run = app.session_state.cockpit_run
    assert run.criteria.industry == Industry.CLIMATE
    assert len(run.result.leads) == 30
    assert len(app.get("plotly_chart")) == 2
    button(app, "Open deep dive").click().run()
    assert not app.exception
    assert "Market & competition" in [t.label for t in app.tabs]
    identity = app.session_state.selected_company
    next(x for x in app.radio if x.label == "Decision").set_value("Contact")
    next(x for x in app.text_area if x.label == "Reason for decision").set_value("Validate pilot evidence")
    next(x for x in app.text_input if x.label == "Next action").set_value("Request customer reference")
    next(x for x in app.text_input if x.label == "Owner").set_value("Alex")
    app.date_input[0].set_value(date.today()-timedelta(days=1))
    button(app, "Save decision & activity").click().run()
    assert not app.exception
    saved = load_decisions("demo")[identity]
    assert saved["next_action"] == "Request customer reference"
    assert saved["outreach_status"] == "Not contacted"
    assert len(load_history("demo", identity)) == 1
    next(x for x in app.radio if x.label == "Workspace").set_value("Activities").run()
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]["Owner"] == "Alex"
    button(app, "Open deep dive").click().run()
    next(x for x in app.selectbox if x.label == "Task status").set_value("Done")
    next(x for x in app.selectbox if x.label == "Outreach status").set_value("Contacted")
    button(app, "Save decision & activity").click().run()
    assert load_decisions("demo")[identity]["task_status"] == "Done"
    assert len(load_history("demo", identity)) == 2
    # Starting a fresh session and analysis preserves the local analyst workflow.
    again = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30).run()
    next(x for x in again.radio if x.label == "Sector").set_value(Industry.CLIMATE)
    button(again, "Start analysis").click().run()
    next(x for x in again.radio if x.label == "Workspace").set_value("Activities").run()
    assert not again.dataframe  # completed tasks leave the open queue
    again.get("button_group")[0].set_value("Completed").run()
    assert len(again.dataframe[0].value) == 1
    button(again, "Change sector").click().run()
    assert again.title[0].value == "Choose your investment focus"


def test_row_navigation_and_empty_filter_recovery():
    app = workspace()
    expected = app.dataframe[0].value.iloc[1]["Company"]
    app.session_state[app.dataframe[0].key] = {"selection": {"rows": [1], "columns": [], "cells": []}}
    app.run()
    assert app.title[0].value == expected
    next(x for x in app.radio if x.label == "Workspace").set_value("Dealflow").run()
    assert app.title[0].value == "Dealflow"
    assert len(app.dataframe[0].value) == 30
    next(x for x in app.text_input if x.label == "Search").set_value("no-such-company-xyz").run()
    assert not app.dataframe
    button(app, "Reset view and filters").click().run()
    assert len(app.dataframe[0].value) == 30
    assert not app.exception


@pytest.mark.parametrize("index", range(10))
def test_legacy_company_profiles_render(index):
    script = f'''
import json
from pathlib import Path
import streamlit as st
from cockpit_details import company
from cockpit_data import load_payload
company(load_payload(json.loads(Path("examples/scoring/scores.json").read_text(encoding="utf-8")))[{index}], {{}})
'''
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    assert "Market opportunity" in [x.label for x in app.tabs]
    assert not app.get("file_uploader")


def test_automatic_handoff_and_live_failure_without_demo_fallback(monkeypatch):
    calls = []
    def fake(criteria, **kwargs):
        calls.append((criteria, kwargs))
        raise NotImplementedError("provider missing")
    monkeypatch.setenv("FOUNDERRADAR_MODE", "live")
    monkeypatch.setattr("cockpit_service.pipeline.run_pipeline", fake)
    with pytest.raises(NotImplementedError):
        start_analysis(Industry.FINTECH)
    assert len(calls) == 1 and not calls[0][1]["use_mock"]
    assert calls[0][0].industry == Industry.FINTECH
    monkeypatch.setenv("FOUNDERRADAR_MODE", "invalid")
    with pytest.raises(ValueError):
        start_analysis(Industry.AI)


def test_optional_ollama_preserves_live_research_lookups(monkeypatch):
    monkeypatch.setenv("FOUNDERRADAR_MODE", "live")
    monkeypatch.setenv("FOUNDERRADAR_CONTEXT_MODE", "live")
    monkeypatch.setenv("FOUNDERRADAR_OLLAMA_MODEL", "local-test-model")
    calls = []
    lookups = {"model": "local-test-model", "imprint": object()}
    monkeypatch.setattr("context.engine.default_lookups", lambda **kwargs: calls.append(kwargs) or lookups)
    monkeypatch.setattr("cockpit_service.pipeline.run_pipeline", lambda criteria, **kwargs: kwargs)
    options = start_analysis(Industry.AI)
    assert calls == [{"model": "local-test-model"}]
    assert options["enricher"].keywords["lookups"] is lookups
    assert options["enricher"].keywords["extract_quotes"].args == ("local-test-model",)
    assert options["use_mock"] is False


def test_native_evaluation_preserves_scoring_evidence_and_exclusions():
    from evaluation.engine import evaluate
    from models import EnrichedLead, Evidence
    lead = EnrichedLead(id="live-metadata", name="Research Company", description="Technology research", industry=Industry.AI,
                        source_url="https://company.de", founders=["Founder"],
                        evidence=[Evidence(source="Company", url="https://company.de", finding="Early research", field="product_stage")])
    evaluated = evaluate(lead)
    original = evaluated.model_dump(mode="json")
    adapted = adapt(original)
    assert evaluated.evaluation_v2["teilwerte"] == adapted.data["teilwerte"]
    assert adapted.excluded == bool(evaluated.evaluation_v2.get("ausschluss_grund") or evaluated.evaluation_v2.get("noise_class") not in (None, "", "vc_potenzial"))
    assert any(e["statement"] == "Early research" for e in adapted.evidence)
    assert adapted.raw == original
    for label, dimension in (("Market", "marktpotenzial"), ("Team", "team"), ("Risk", "risiko")):
        criteria = evaluated.evaluation_v2["teilwerte"].get(dimension, {})
        if criteria and not any(c["belegt"] for c in criteria.values()):
            assert adapted.scores[label] is None


def test_analysis_run_serializes_exclusions_and_distinct_claims():
    from cockpit_data import fund_fit
    from models import AnalysisRun, SearchCriteria, ResearchResult
    run = start_analysis(Industry.AI)
    lead = run.result.leads[0]
    lead.founding_year = date.today().year
    lead.stage_classification = "Seed"
    lead.evaluation_v2 = {"gesamt_score": 88, "ausschluss_grund": "Eligibility unresolved", "evidence": [
        {"dimension": "team", "aussage": "Experienced founder", "url": "https://company.de"},
        {"dimension": "risiko", "aussage": "Eligibility unresolved", "url": "https://company.de"}]}
    rebuilt = AnalysisRun.model_validate_json(run.model_dump_json())
    adapted = next(l for l in load_workspace(rebuilt) if l.id == lead.id)
    assert adapted.excluded and fund_fit(adapted)[0] != "Potential Fit"
    assert sum(e["url"] == "https://company.de" for e in adapted.evidence) == 2


def test_ui_task_can_be_planned_without_decision():
    app = workspace()
    button(app, "Open deep dive").click().run()
    identity = app.session_state.selected_company
    next(x for x in app.text_input if x.label == "Action").set_value("Verify founders")
    next(x for x in app.text_input if x.label == "Assigned to").set_value("Alex")
    next(x for x in app.date_input if x.label == "Deadline").set_value(date.today()-timedelta(days=1))
    button(app, "Save next step").click().run()
    assert not app.exception
    assert load_decisions("demo")[identity]["decision"] == "Pending Review"
    next(x for x in app.radio if x.label == "Workspace").set_value("Overview").run()
    button(app, "Review overdue (1)").click().run()
    assert app.title[0].value == "Activities"
    assert len(app.dataframe[0].value) == 1


def test_mailto_is_safe_encoded_and_does_not_change_contact_state():
    lead = adapt({"id": "email", "name": "Company & Partners?\r\nBcc: nobody", "contact_email": "founder+vc@company.de"})
    draft = email_draft(lead)
    assert draft.startswith("mailto:founder%2Bvc@company.de?")
    query = parse_qs(urlsplit(draft).query)
    assert set(query) == {"subject", "body"}
    assert "\n" not in query["subject"][0]
    assert load_decisions("live") == {}
    for address in ["a@b.de\r\nBcc:x@y.de", "a@b.de?bcc=x@y.de", "a@localhost", "not an email"]:
        assert email_draft(adapt({"name": "X", "email": address})) is None


def test_tracking_history_boundaries_and_legacy_preservation():
    from cockpit import overdue
    past = (date.today()-timedelta(days=1)).isoformat()
    assert overdue({"due_date": past, "task_status": "Open"})
    assert not overdue({"due_date": date.today().isoformat(), "task_status": "Open"})
    assert not overdue({"due_date": past, "task_status": "Done"})
    save_decision("demo", "x", "Contact", "note", "reason", "Call", "Alex", past, "Replied", "Done")
    save_decision("demo", "x", "Watchlist", "new", "new reason", "Review", "Alex")
    current = load_decisions("demo")["x"]
    assert (current["due_date"], current["outreach_status"], current["task_status"]) == (past, "Replied", "Done")
    assert len(load_history("demo", "x")) == 2
    assert load_history("demo", "x")[1]["decision"] == "Contact"
    assert load_history("live", "x") == []
    with pytest.raises(ValueError):
        save_decision("demo", "x", "Contact", "", "reason", due_date="bad date")
    assert len(load_history("demo", "x")) == 2
    save_decision("demo", "x", "Contact", "", "reason", due_date="", task_status="Open")
    assert load_decisions("demo")["x"]["due_date"] == ""


def test_activity_without_investment_decision_and_atomic_history(monkeypatch):
    import sqlite3
    import os
    from analyst_store import save_activity
    save_activity("demo", "task-only", "Verify founder roles", "Alex", "", "Not contacted", "Open")
    assert load_decisions("demo")["task-only"]["decision"] == "Pending Review"
    save_decision("demo", "existing", "Reject", "keep notes", "not a mandate fit")
    save_activity("demo", "existing", "Archive research", "Alex", "", "Not contacted", "Done")
    assert load_decisions("demo")["existing"]["decision"] == "Reject"
    assert load_decisions("demo")["existing"]["notes"] == "keep notes"
    with sqlite3.connect(os.environ["FOUNDERRADAR_DB"]) as conn:
        conn.execute("CREATE TRIGGER reject_history BEFORE INSERT ON decision_history BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        save_decision("demo", "existing", "Contact", "changed", "changed")
    assert load_decisions("demo")["existing"]["decision"] == "Reject"
    assert len(load_history("demo", "existing")) == 2


def test_visualizations_use_supplied_values_and_keep_unknowns():
    leads = [adapt({"name": "Known", "overall_score": 0, "confidence_score": 70, "stage_classification": "Seed"}),
             adapt({"name": "Unknown", "stage_classification": "Unknown"})]
    fig = pipeline_scatter(leads)
    assert list(fig.data[0].x) == [0] and list(fig.data[0].y) == [70]
    assert sum(stage_bars(leads).data[0].x) == 2
    assert list(score_profile(leads[1]).data[0].x) == []
    legacy = load_payload(json.loads((ROOT/"examples/scoring/scores.json").read_text(encoding="utf-8")))[0]
    assert sum(sum(trace.x) for trace in evidence_coverage(legacy).data) == len(legacy.evidence)
