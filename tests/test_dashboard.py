from pathlib import Path
from urllib.parse import unquote

import pytest
from pydantic import ValidationError

from dashboard import build_figure, contact_url, shortlist
from demo_portfolio import get_demo_result
from models import ResearchResult


def test_fixtures_and_contract_roundtrip():
    result = get_demo_result()
    assert len(result.leads) == 30
    assert len({x.id for x in result.leads}) == 30
    assert ResearchResult.model_validate_json(result.model_dump_json()) == result
    assert all(x.is_demo and x.country == "DE" for x in result.leads)
    assert all(x.contact_email is None or x.contact_email.endswith("@example.org") for x in result.leads)


def test_top_selection_and_missing_values():
    leads = get_demo_result().leads
    assert len(shortlist(leads, top_n=20)) == 20
    assert len(shortlist(leads)) == 10
    assert shortlist(leads)[0].overall_score >= shortlist(leads)[-1].overall_score
    assert len(shortlist(leads, industry="HealthTech")) == 6
    missing = leads[0].model_copy(update={"overall_score": None, "risk_score": None})
    shown = shortlist([missing, leads[1]])
    assert shown[-1].id == missing.id
    fig, omitted = build_figure(shown, missing.id)
    assert omitted == 1
    assert list(fig.data[0].x) == [leads[1].risk_score]
    assert list(fig.data[0].y) == [leads[1].company_score]
    assert list(fig.data[0].z) == [leads[1].market_potential_score]


def test_contact_draft_and_validation():
    lead = next(x for x in get_demo_result().leads if x.contact_email)
    assert unquote(contact_url(lead)).startswith(f"mailto:{lead.contact_email}?subject=Intro")
    assert contact_url(lead.model_copy(update={"contact_email": None})) is None
    with pytest.raises(ValidationError):
        lead.contact_email = "hello@example.org\nBcc:other@example.org"
    with pytest.raises(ValidationError):
        lead.founding_month = 13


def choose_source(app, source):
    """Pick the data source on the start page ("snapshot" is the default)."""
    radio = next(x for x in app.radio if x.label == "Data source")
    assert radio.value == "snapshot"
    radio.set_value(source).run()
    assert not app.exception
    return app


def start_app(category=None):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert not app.dataframe
    assert not app.get("plotly_chart")
    choose_source(app, "demo")
    if category:
        next(x for x in app.radio if x.label == "Category").set_value(category)
    next(b for b in app.button if b.label == "Start analysis").click().run()
    assert not app.exception
    return app


def test_dashboard_filters_and_detail():
    from models import Industry
    app = start_app(Industry.HEALTH)
    assert len(app.dataframe[0].value) == 10
    assert len(app.get("plotly_chart")) == 3
    next(x for x in app.selectbox if x.label == "Show ranking").set_value(20).run()
    assert len(app.dataframe[0].value) == 20
    from hashlib import sha256
    shown = shortlist(app.session_state.analysis.result.leads, top_n=20)
    assert all(x.industry == Industry.HEALTH for x in shown)
    signature = sha256("|".join(x.id for x in shown).encode()).hexdigest()[:12]
    app.session_state[f"ranking_{signature}_1"] = {"selection": {"rows": [1], "columns": [], "cells": []}}
    app.run()
    assert not app.exception
    assert app.query_params["startup"] == shown[1].id
    assert app.title[0].value == shown[1].name
    assert not app.dataframe
    assert len(app.tabs) == 4  # incl. the investment briefing & decision tab (cockpit branch)
    next(x for x in app.button if x.key == "back_to_portfolio").click().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 20
    assert not app.query_params.get("startup")
    next(x for x in app.button if x.label == "New analysis").click().run()
    assert not app.dataframe
    next(x for x in app.radio if x.label == "Category").set_value(Industry.CLIMATE)
    next(x for x in app.button if x.label == "Start analysis").click().run()
    assert all(x.industry == Industry.CLIMATE for x in app.session_state.analysis.result.leads)
    assert len(app.dataframe[0].value) == 10
    assert not app.exception


def test_detail_direct_link_and_unknown_id():
    app = start_app()
    lead = app.session_state.analysis.result.leads[3]
    app.query_params["startup"] = lead.id
    app.run()
    assert not app.exception
    assert app.title[0].value == lead.name
    app.query_params["startup"] = "unknown"
    app.run()
    assert any("not in the current run" in x.value for x in app.warning)
    next(x for x in app.button if x.label == "Back to overview").click().run()
    assert len(app.dataframe[0].value) == 10


def test_visualizations_match_data():
    from charts import stage_figure, comparison_figure
    from collections import Counter
    leads = shortlist(get_demo_result().leads)
    pie = stage_figure(leads).data[0]
    assert dict(zip(pie.labels, pie.values)) == dict(Counter(x.stage_classification for x in leads))
    comparison = comparison_figure(leads)
    assert list(comparison.data[0].x) == [x.company_score for x in reversed(leads)]
    assert list(comparison.data[2].x) == [x.risk_score for x in reversed(leads)]


def test_industrial_demo_renders_market_and_sources():
    from models import Industry

    app = start_app(Industry.INDUSTRIAL)
    app.query_params["startup"] = "industrial-16"
    app.run()
    assert not app.exception
    assert "Market research" in [tab.label for tab in app.tabs]
    assert {"TAM", "SAM", "SOM"} <= {metric.label for metric in app.metric}
    assert any("Eurostat SBS" in item.value for item in app.markdown)


# --- Live-like leads (Förderkatalog dossiers, scored offline) -------------------------------------------

SAMPLE_DOSSIERS = Path(__file__).resolve().parents[1] / "examples" / "sourcing" / "sample_dossiers.json"


def live_leads():
    """Two live EvaluatedLeads from the committed dossiers; the second is marked industry_unclassified."""
    import json

    from models import EnrichedLead
    from pipeline import evaluate_context

    dossiers = json.loads(SAMPLE_DOSSIERS.read_text(encoding="utf-8"))["leads"][:2]
    enriched = [EnrichedLead.model_validate(x) for x in dossiers]
    leads = evaluate_context(enriched, use_mock=False).leads
    assert len(leads) == 2 and not any(x.is_demo for x in leads)
    first, second = leads
    signal = second.signals[0]
    marked = signal.model_copy(update={"evidence": signal.evidence.replace("Hinweise: ", "Hinweise: industry_unclassified, ")})
    second = second.model_copy(update={
        "signals": [marked, *second.signals[1:]], "htgf_sector": None,
        "open_questions": [f"Testfrage {i}?" for i in range(1, 21)],
    })
    return [first, second]


def live_run(leads):
    from models import AnalysisRun, SearchCriteria
    return AnalysisRun(criteria=SearchCriteria(industry=leads[0].industry, limit=10), mode="live",
                       discovered_count=len(leads), enriched_count=len(leads), result=ResearchResult(leads=leads))


def start_live_app(monkeypatch, run=None, error=None):
    """Start the app with the live toggle on; run_pipeline is replaced (no network)."""
    import pipeline
    from streamlit.testing.v1 import AppTest

    calls = []

    def fake_run_pipeline(criteria, **kwargs):
        calls.append((criteria, kwargs))
        if error:
            raise error
        return run

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    choose_source(app, "live")
    next(b for b in app.button if b.label == "Start analysis").click().run()
    assert not app.exception
    return app, calls


def test_ranking_tie_break_uses_step1_priority():
    lead = get_demo_result().leads[0]
    low = lead.model_copy(update={"id": "a-low", "prioritization_reason": "Priorität 40: Test"})
    high = lead.model_copy(update={"id": "b-high", "prioritization_reason": "Priorität 90: Test"})
    none = lead.model_copy(update={"id": "c-none", "prioritization_reason": None})
    assert [x.id for x in shortlist([none, low, high])] == ["b-high", "a-low", "c-none"]


def test_industry_label_priority_line_and_source_links():
    from dashboard import industry_label, priority_line, source_link_markdown

    plain, unclassified = live_leads()
    assert industry_label(plain) == plain.industry.value
    assert industry_label(unclassified) == "unclassified"
    assert all(industry_label(x) == x.industry.value for x in get_demo_result().leads)
    number, rest = plain.prioritization_reason.split(":", 1)
    assert priority_line(plain) == f"{number.replace('Priorität', 'Priority')} – {rest.strip()}"
    assert priority_line(get_demo_result().leads[0]) is None
    text = source_link_markdown("Dünne Datenlage (Quelle: https://example.org/a?b=1)")
    assert text == "Dünne Datenlage ([Source](https://example.org/a?b=1))"
    assert source_link_markdown("Thin data (source: https://example.org/a?b=1)") == "Thin data ([Source](https://example.org/a?b=1))"
    assert source_link_markdown("Without source") == "Without source"


def test_live_toggle_runs_live_pipeline_and_renders_every_view(monkeypatch):
    leads = live_leads()
    app, calls = start_live_app(monkeypatch, run=live_run(leads))
    (criteria, kwargs), = calls
    assert kwargs["use_mock"] is False and criteria.limit == 10 and callable(kwargs["on_progress"])
    assert len(app.dataframe[0].value) == 2
    assert len(app.get("plotly_chart")) == 3
    assert any("LIVE ANALYSIS" in x.value for x in app.caption)
    for lead in leads:
        app.query_params["startup"] = lead.id
        app.run()
        assert not app.exception
        assert app.title[0].value == lead.name
        assert any(x.value.startswith("Priority ") for x in app.caption)
    assert any("unclassified" in x.value for x in app.markdown)
    assert any(x.label.endswith("more questions") for x in app.expander)
    assert any("[Source](https://" in x.value for x in app.warning)


def test_live_sourcing_error_shows_readable_message(monkeypatch):
    from sourcing.engine import SourcingError

    app, _ = start_live_app(monkeypatch, error=SourcingError("Förderkatalog-Sourcing fehlgeschlagen: Timeout"))
    assert any("funding catalogue (Förderkatalog) could not be queried" in x.value for x in app.error)
    assert "analysis" not in app.session_state


def test_sourced_signals_block_for_live_leads_only(monkeypatch):
    from deep_dive import sourced_signals

    plain, unclassified = live_leads()
    rows = sourced_signals(plain)
    labels = [label for label, _, _ in rows]
    assert labels[0] == "Public funding" and labels[-3:] == ["Startup databases", "First dated signal", "Open questions"]
    grant = plain.grants[0]
    _, value, url = rows[0]
    assert grant.programme in value and f"FKZ {grant.reference}" in value and "Term" in value and " EUR" in value
    assert url == str(grant.url)
    assert dict((label, value) for label, value, _ in rows)["Open questions"] == \
        str(len(dict.fromkeys([*plain.open_questions, *plain.research_questions])))
    assert all(sourced_signals(lead) == [] for lead in get_demo_result().leads)

    app, _ = start_live_app(monkeypatch, run=live_run([plain, unclassified]))
    app.query_params["startup"] = plain.id
    app.run()
    assert not app.exception
    assert any(x.value == "Documented signals" for x in app.subheader)
    assert any("[Open source](" in x.value for x in app.markdown)


def test_sourced_text_is_rendered_as_literal_markdown():
    from dashboard import source_link_markdown
    from ui_theme import md_escape

    assert md_escape("first_web_capture kostet $5 *netto* [1] <b>") == \
        r"first\_web\_capture kostet \$5 \*netto\* \[1\] \<b\>"
    assert md_escape("Ohne Sonderzeichen: 1.029.852 EUR – ok") == "Ohne Sonderzeichen: 1.029.852 EUR – ok"
    # line starts must not become lists or headings, line breaks survive, entities stay literal
    assert md_escape("- Punkt\n1. Schritt\n=== R&D") == "\\- Punkt  \n1\\. Schritt  \n\\=== R\\&D"
    assert source_link_markdown("Reife_grad $x$ (Quelle: https://example.org/a_b?c=1)") == \
        r"Reife\_grad \$x\$ ([Source](https://example.org/a_b?c=1))"


def test_screening_and_cockpit_views_and_decision_tab():
    """Integrated cockpit branch: screening longlist, investment cockpit and the decision form in the deep dive."""
    from models import Industry
    app = start_app(Industry.HEALTH)
    view = next(x for x in app.get("button_group") if x.label == "View")
    view.set_value("Screening & Decisions").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 30
    assert any("Screening" in x.value for x in app.title) or any("Screening" in str(x.value) for x in app.markdown)
    next(x for x in app.get("button_group") if x.label == "View").set_value("Investment Cockpit").run()
    assert not app.exception
    nav = next(x for x in app.radio if x.label == "Workspace")
    for page in ("Dealflow", "Company Deep Dive", "Activities", "Overview"):
        nav.set_value(page).run()
        assert not app.exception, page
        nav = next(x for x in app.radio if x.label == "Workspace")
    next(x for x in app.get("button_group") if x.label == "View").set_value("Radar").run()
    assert not app.exception and len(app.dataframe[0].value) == 10
    lead = app.session_state.analysis.result.leads[0]
    app.query_params["startup"] = lead.id
    app.run()
    assert not app.exception
    assert any(x.label == "Decision" for x in app.radio)
