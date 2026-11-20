import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from analyst_store import load_decisions, save_decision
from cockpit_data import adapt, fund_fit, investment_scenario, load_payload
from cockpit_research import comparable_series

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def leads():
    return load_payload(json.loads((ROOT / "examples/scoring/scores.json").read_text(encoding="utf-8")))


def test_all_ten_real_scoring_fixtures(leads):
    assert len(leads) == 10
    assert all(lead.demo for lead in leads)
    contract = leads[0]
    assert contract.name.startswith("Kontraktwerk")
    assert contract.scores["Quality"] == 82.5
    assert contract.confidence == .89
    assert contract.data["investment_thesis"] == contract.raw["investmenthypothese"]
    assert len(contract.evidence) == len(contract.raw["evidence"])
    assert any(e["criterion"] == "regulatorik" for e in leads[1].evidence)
    assert leads[2].confidence == .53  # FerroSense, sparse technical research
    assert leads[3].scores["Team"] is None and leads[3].scores["Market"] is None
    assert leads[4].confidence == .01 and leads[4].warnings
    assert leads[5].excluded and leads[7].excluded  # agency / hobby
    assert leads[6].excluded and fund_fit(leads[6])[0] != "Potential Fit"
    assert fund_fit(leads[8], date(2026, 11, 20))[0] == "Likely Out of Scope"
    assert all(v is None for v in leads[9].scores.values())


def test_adapter_preserves_source_and_supports_v2(leads):
    original = leads[0].raw
    revised = dict(original, context_v2={"market_intelligence": {"definition": "Contracts"}}, evaluation_v2={"why_contact_now": "New pilot"})
    lead = adapt(revised)
    assert lead.raw == revised
    assert lead.data["market_intelligence"]["definition"] == "Contracts"
    # A supplied canonical extension must override a legacy alias.
    assert lead.data["why_contact_now"] == "New pilot"


def test_native_analysis_and_single_record():
    payload = json.loads((ROOT / "examples/analysis-demo.json").read_text(encoding="utf-8"))
    leads = load_payload(payload)
    assert leads
    assert load_payload(leads[0].raw)[0].id == leads[0].id
    with pytest.raises(ValueError, match="Duplicate"):
        load_payload([leads[0].raw, leads[0].raw])
    with pytest.raises(ValueError):
        load_payload({"unrelated": "object"})


def test_missing_invalid_and_zero_values():
    lead = adapt({"name": "Minimal", "confidence": None, "risk_score": 0, "overall_score": float("nan")})
    assert lead.confidence is None
    assert lead.scores["Risk"] == 0
    assert lead.scores["Quality"] is None
    assert fund_fit(lead)[0] == "Review Required"
    assert adapt({"name": "Demo URL", "website": "https://example.org/x"}).demo
    assert adapt({"name": "Invalid", "confidence": 12}).confidence is None
    with pytest.raises(ValueError, match="must be an array"):
        adapt({"name": "Malformed", "market_intelligence": {"growth_series": 42}})


def test_fit_age_proxy_boundary_and_ticket():
    base = {"name": "Fit", "industry": "AI / Software", "stage_classification": "Seed", "country": "DE", "founding_year": 2025}
    assert fund_fit(adapt(base), date(2026, 11, 20))[0] == "Potential Fit"
    assert fund_fit(adapt(dict(base, gruendung_ist_proxy=True)), date(2026, 11, 20))[0] == "Review Required"
    assert fund_fit(adapt(dict(base, founding_year=2023)), date(2026, 11, 20))[0] == "Review Required"
    assert fund_fit(adapt(dict(base, founding_year=2022)), date(2026, 11, 20))[0] == "Likely Out of Scope"
    assert fund_fit(adapt(dict(base, round_size_eur=100000)), date(2026, 11, 20))[0] == "Potential Fit"  # not a hard minimum
    assert fund_fit(adapt(dict(base, founding_year=2028)), date(2026, 11, 20))[0] == "Review Required"


def test_scenario_math_and_boundaries():
    result = investment_scenario(800000, 3200000, .2, 20000000)
    assert result["Post-money valuation"] == 4000000
    assert result["Initial ownership"] == .2
    assert result["Ownership after dilution"] == pytest.approx(.16)
    assert result["Exit proceeds"] == pytest.approx(3200000)
    assert result["MOIC"] == pytest.approx(4)
    assert investment_scenario(1, 0, 1, 100)["MOIC"] == 0
    for args in [(0, 1, 0, 1), (1, 1, 1.1, 1), (1, -1, 0, 1), (1, 1, 0, float("inf"))]:
        with pytest.raises(ValueError):
            investment_scenario(*args)


def test_market_chart_refuses_unsourced_or_incomparable_data():
    row = {"year": 2025, "value": 10, "unit": "EUR million", "definition": "A market", "geography": "DE", "as_of": "2026-11-20", "source": "https://research.example.org", "kind": "Historical"}
    valid = [row, dict(row, year=2026, kind="Forecast", value=12)]
    assert len(comparable_series(valid)) == 2
    for bad in [dict(row, source=None), dict(row, unit="USD"), dict(row, geography="US"), dict(row, kind=None), dict(row, value=None)]:
        assert comparable_series([valid[1], bad]) == []


def test_storage_migrates_legacy_database_and_keeps_namespaces(monkeypatch, tmp_path):
    path = tmp_path / "old.sqlite3"
    monkeypatch.setenv("FOUNDERRADAR_DB", str(path))
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE decisions (namespace TEXT, lead_id TEXT, decision TEXT, notes TEXT, reason TEXT, updated_at TEXT, PRIMARY KEY(namespace,lead_id))")
        conn.execute("INSERT INTO decisions VALUES ('demo','x','Watchlist','keep','check','2026-11-20')")
    assert load_decisions("demo")["x"]["notes"] == "keep"
    save_decision("demo", "x", "Contact", "note", "Relevant", "Schedule call", "Alex")
    assert load_decisions("demo")["x"]["next_action"] == "Schedule call"
    assert load_decisions("demo")["x"]["analyst_name"] == "Alex"
    assert load_decisions("live") == {}


def test_ui_navigation_decision_persistence_and_noise(leads):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Investment Pipeline"
    assert len(app.dataframe[0].value) == 10
    next(x for x in app.radio if x.label == "Sourcing relevance").set_value("Excluded only").run()
    assert len(app.dataframe[0].value) == 5  # includes OhneBeleg: returned to sourcing
    next(x for x in app.radio if x.label == "Sourcing relevance").set_value("All leads").run()
    next(x for x in app.button if x.label == "Open research").click().run()
    assert not app.exception
    assert app.title[0].value.startswith("Kontraktwerk")
    assert [x.label for x in app.tabs] == ["Investment Overview", "Market Intelligence", "Competition", "Funding & Valuation", "Discovery & Evidence"]
    next(x for x in app.radio if x.label == "Decision").set_value("Watchlist")
    next(x for x in app.text_area if x.label == "Reason for decision").set_value("Verify customer pilots")
    next(x for x in app.text_input if x.label == "Next action").set_value("Request pilot reference")
    next(x for x in app.button if x.label == "Save decision").click().run()
    assert not app.exception
    assert load_decisions("demo")[leads[0].id]["next_action"] == "Request pilot reference"
    next(x for x in app.radio if x.label == "Workspace").set_value("Watchlist").run()
    assert len(app.dataframe[0].value) == 1
    # New app session reads the existing database rather than Session State.
    again = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30).run()
    next(x for x in again.radio if x.label == "Workspace").set_value("Screening Decisions").run()
    assert len(again.dataframe[0].value) == 1


@pytest.mark.parametrize("index", range(10))
def test_every_company_profile_renders(leads, index):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30)
    app.query_params["company"] = leads[index].id
    app.run()
    assert not app.exception
    assert app.title[0].value == leads[index].name


def test_row_selection_can_return_to_dealflow():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "cockpit.py"), default_timeout=30).run()
    key = app.dataframe[0].key
    app.session_state[key] = {"selection": {"rows": [1], "columns": [], "cells": []}}
    app.run()
    assert app.title[0].value.startswith("OsteoPrint")
    next(x for x in app.radio if x.label == "Workspace").set_value("Dealflow").run()
    assert app.title[0].value == "Investment Pipeline"
    assert not app.exception


def test_context_date_can_only_fill_empty_from_evidence():
    from pipeline import _preserve
    from models import RawLead, EnrichedLead, Evidence
    raw = RawLead(id="x", name="X", description="X", industry="AI / Software", source_url="https://example.org")
    when = date(2026, 1, 1)
    enriched = EnrichedLead(**raw.model_dump(exclude={"first_signal_date"}), first_signal_date=when)
    with pytest.raises(ValueError):
        _preserve(raw, enriched)
    enriched.evidence = [Evidence(source="A", url="https://example.org", finding="dated signal", field="first_signal_date", source_date=when)]
    _preserve(raw, enriched)
    raw.first_signal_date = date(2025, 1, 1)
    with pytest.raises(ValueError):
        _preserve(raw, enriched)
