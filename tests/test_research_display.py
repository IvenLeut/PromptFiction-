"""Regression coverage for the native research contract and truthful presentation."""
from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from cockpit_context import context_for, evidence_for, market_for, measure_label
from cockpit_data import adapt, fund_fit
from cockpit_research_v2 import provenance, series_figure
from cockpit_service import load_workspace, start_analysis
from models import Industry


@pytest.fixture(scope="module")
def industrial():
    return next(l for l in load_workspace(start_analysis(Industry.INDUSTRIAL)) if l.id == "industrial-16")


def test_native_claims_keep_names_details_sources_and_original_record(industrial):
    original = deepcopy(industrial.raw)
    lead = adapt(original)
    assert original == industrial.raw
    assert all(isinstance(name, str) for name in lead.data["founders"])
    assert lead.data["economic_buyer"] == context_for(lead)["product"]["economic_buyer"]["value"]
    assert lead.data["technology"] == context_for(lead)["product"]["technology"]["value"]
    assert any(p.get("role") for p in lead.data["founder_profiles"])
    evidence_ids = {e["evidence_id"] for e in lead.evidence}

    def check(value):
        if isinstance(value, dict):
            assert set(value.get("evidence_ids", [])) <= evidence_ids
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(context_for(lead))


def test_market_model_is_not_company_revenue_or_valuation(industrial):
    market = market_for(industrial)
    assert market["tam"]["value"] == 2414124000
    assert "assumptions" in provenance(industrial, market["tam"])
    assert "Eurostat SBS" in {e["source"] for e in evidence_for(industrial, market["tam"])}
    series = market["historical_growth"][0]
    fig = series_figure(series)
    assert list(fig.data[0].y) == [206391, 204554, 201177]
    assert fig.layout.yaxis.title.text == "Unternehmen"
    assert series["cagr"]["value"] < 0
    assert "-" in measure_label(series["cagr"])
    transaction = market["comparable_transactions"][0]
    assert transaction["transaction_value"]["value"] == 1400000
    assert transaction["company_valuation"] is None and transaction["ev_revenue"] is None


def test_series_does_not_join_different_units_or_duplicate_years(industrial):
    series = deepcopy(market_for(industrial)["historical_growth"][0])
    series["points"][1]["currency"] = "EUR"
    assert series_figure(series) is None
    series = deepcopy(market_for(industrial)["historical_growth"][0])
    series["points"][1]["period"] = dict(series["points"][0]["period"])
    assert series_figure(series).data[0].mode == "markers"


@pytest.mark.parametrize("industry", list(Industry))
def test_each_sector_profile_renders_available_operating_facts(industry):
    app = AppTest.from_string(f'''
from cockpit_service import load_workspace, start_analysis
from cockpit_details import company
from models import Industry
leads = load_workspace(start_analysis(Industry({industry.value!r})))
company(next(lead for lead in leads if lead.id.endswith('-16')), {{}})
''', default_timeout=30).run()
    assert not app.exception
    html = " ".join(item.value for item in app.markdown)
    assert "Business model" in html or "Product" in html
    assert "{'value':" not in html
    if industry == Industry.INDUSTRIAL:
        assert {"TAM", "SAM", "SOM"} <= {m.label for m in app.metric}
        assert "Eurostat SBS" in html and "Werksleitung" in html
        assert "source reference unresolved" not in html
        assert any("Siemens" in str(df.value) for df in app.dataframe)


def test_zero_operating_metrics_are_visible_and_conflicting_age_is_not_a_match():
    app = AppTest.from_string('''
from cockpit_data import adapt
from cockpit_details import operational_kpis
operational_kpis(adapt({"name":"Zero", "customer_count":0, "annual_revenue_eur":0, "team_size":0, "funding_total_eur":0}))
''').run()
    assert not app.exception
    assert "Customers" in app.markdown[0].value and ">0<" in app.markdown[0].value
    lead = adapt({"name": "Conflict", "founding_year": 2026, "context_v2": {"company": {"founding_date_status": "conflicting"}}})
    assert next(r for r in fund_fit(lead)[1] if r["Criterion"] == "Company age")["Status"] == "Unknown"


def test_conflicting_revenue_does_not_borrow_period_or_turn_pilots_into_customers():
    measure = {"value": 120000, "unit": "pro Jahr", "currency": "EUR", "geography": "Germany",
               "period": {"start_year": 2025, "end_year": 2025}, "data_type": "observed", "evidence_ids": ["revenue-proof"]}
    record = {"name": "Conflicting records", "annual_revenue_eur": 80000,
              "context_v2": {"traction": {"paid_pilots": [{"value": "Pilot A"}], "reported_metrics": {"revenue": [measure]}}}}
    lead = adapt(record)
    assert lead.data["annual_revenue_eur"] == 80000
    assert not lead.data.get("_operating_measures")
    assert lead.data["_research_conflicts"][0]["Research value"] == "120000"
    assert lead.data.get("customer_count") is None
    record.pop("annual_revenue_eur")
    lead = adapt(record)
    assert lead.data["annual_revenue_eur"] == 120000
    assert lead.data["_operating_measures"]["annual_revenue_eur"]["period"]["end_year"] == 2025
    assert "/ year" in measure_label(measure)
