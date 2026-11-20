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
    assert unquote(contact_url(lead)).startswith(f"mailto:{lead.contact_email}?subject=Austausch")
    assert contact_url(lead.model_copy(update={"contact_email": None})) is None
    with pytest.raises(ValidationError):
        lead.contact_email = "hello@example.org\nBcc:other@example.org"
    with pytest.raises(ValidationError):
        lead.founding_month = 13


def start_app(category=None):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert not app.dataframe
    assert not app.get("plotly_chart")
    if category:
        app.radio[0].set_value(category)
    next(b for b in app.button if b.label == "Analyse starten").click().run()
    assert not app.exception
    return app


def test_dashboard_filters_and_detail():
    from models import Industry
    app = start_app(Industry.HEALTH)
    assert len(app.dataframe[0].value) == 10
    assert len(app.get("plotly_chart")) == 3
    next(x for x in app.selectbox if x.label == "Ranking anzeigen").set_value(20).run()
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
    assert len(app.tabs) == 3
    next(x for x in app.button if x.key == "back_to_portfolio").click().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 20
    assert not app.query_params.get("startup")
    next(x for x in app.button if x.label == "Neue Analyse").click().run()
    assert not app.dataframe
    app.radio[0].set_value(Industry.CLIMATE)
    next(x for x in app.button if x.label == "Analyse starten").click().run()
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
    assert any("nicht vorhanden" in x.value for x in app.warning)
    next(x for x in app.button if x.label == "Zurück zur Übersicht").click().run()
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
    assert "Marktrecherche" in [tab.label for tab in app.tabs]
    assert {"TAM", "SAM", "SOM"} <= {metric.label for metric in app.metric}
    assert any("Eurostat SBS" in item.value for item in app.markdown)
