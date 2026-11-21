"""Render source-linked research in the startup detail view."""
import plotly.graph_objects as go
import streamlit as st

from research_models import ContextV2
from ui_theme import format_date, md_escape

# Maximum levels of the two sector scales shown at the end of the market tab.
TRL_MAX, MCL_MAX = 9, 6


def _claims(owner, labels: dict[str, str]):
    """One text line per filled claim of ``owner``."""
    for field, label in labels.items():
        claim = getattr(owner, field)
        if claim:
            st.text(f"{label} · {claim.value}")


def render_company_research(context: ContextV2):
    """Founders, company, product, funding and traction facts from step 2."""
    if context.founders:
        st.subheader("Founding team")
        for founder in context.founders:
            st.text(founder.name)
            _claims(founder, {"role": "Role", "qualifications": "Qualifications", "previous_companies": "Previous companies",
                              "founding_experience": "Founding experience",
                              "customer_problem_experience": "Experience with the customer problem"})
    _claims(context.company, {"headquarters": "Headquarters", "company_status": "Company status"})
    if context.company.founding_date:
        date_status = {"documented": "date stated by source", "reported": "reported in sourcing"}
        st.text(f"Founded · {context.company.founding_date.value} · "
                f"{date_status.get(context.company.founding_date_status, 'open')}")
    elif context.company.founding_date_status == "conflicting":
        st.caption("The sources give conflicting founding dates.")
    _claims(context.product, {
        "customer_problem": "Customer problem", "solution": "Solution", "target_customers": "Target customers",
        "economic_buyer": "Economic buyer", "business_model": "Business model",
        "advantage": "Competitive advantage", "technology": "Technology", "ip": "IP rights",
        "development_status": "Development status", "next_milestone": "Product milestone",
    })
    funding = context.funding
    status_labels = {"unknown": "Unknown", "vc_backed": "VC funding reported",
                     "non_vc_funded": "Grants or self-funding documented",
                     "unfunded": "Reported as unfunded", "funded": "Funding type open",
                     "conflicting": "Conflicting information"}
    vc_labels = {"unknown": "Unknown", "confirmed": "Investment reported", "reported_none": "No investment reported",
                 "conflicting": "Conflicting information"}
    st.text(f"Funding status · {status_labels[funding.status]}")
    st.text(f"VC investment · {vc_labels[funding.vc_status]}")
    for owner, fields in [
        (context.traction, {"paid_customers": "Paying customers", "customers_payment_unknown": "Customers · payment status open",
                            "paid_pilots": "Paid pilots", "unpaid_pilots": "Unpaid pilots",
                            "pilots_payment_unknown": "Pilots · payment status open", "lois": "Letters of intent",
                            "commercial_partners": "Commercial partners", "research_partners": "Research partners"}),
        (funding, {"public_grants": "Public funding", "rounds": "Previous rounds", "investors": "Investors"}),
    ]:
        for field, label in fields.items():
            if claims := getattr(owner, field):
                st.text(f"{label} · " + ", ".join(claim.value for claim in claims))
    _claims(context.traction, {"usage": "Product usage", "revenue": "Revenue", "growth": "Revenue growth"})
    metric_labels = {"revenue": "Annual revenue", "revenue_growth": "Revenue growth", "customer_count": "Customer count"}
    for kind, metrics in context.traction.reported_metrics.items():
        for measure in metrics:
            st.text(f"{metric_labels.get(kind, kind)} {measure.period.end_year} · {_measure(measure)}")
    _claims(funding, {"fundraising_status": "Fundraising", "planned_round": "Planned round",
                      "capital_need": "Capital need", "use_of_funds": "Use of funds",
                      "next_milestone": "Funding milestone", "time_to_milestone": "Time frame",
                      "burn_rate": "Burn Rate", "cash_runway": "Cash Runway"})


def _measure(measure) -> str:
    """Measured value with two decimals and space as thousands separator; "Open" if missing."""
    if measure is None:
        return "Open"
    return f"{measure.value:,.2f} {measure.currency or ''} {measure.unit}".replace(",", " ").strip()


def render_market(context: ContextV2):
    """Market tab: sizing, growth, competitors, transactions, capital needs and research gaps."""
    market = context.market_intelligence
    st.caption(f"Research updated on {format_date(context.updated_at)}")
    if market.market_definition:
        st.text(market.market_definition.value)
    _claims(market, {"target_segment": "Target segment", "target_geography": "Target geography"})
    for column, name in zip(st.columns(3), ("TAM", "SAM", "SOM")):
        measure = getattr(market, name.lower())
        column.metric(name, _measure(measure))
        if measure:
            column.caption(md_escape(f"{measure.geography} · reference year {measure.period.end_year} · "
                                     f"{measure.data_type} · {measure.methodology}"))
    if market.sizing_inputs:
        with st.expander("Market sizing data and assumptions"):
            for measure in market.sizing_inputs.values():
                st.text(f"{measure.methodology} · {_measure(measure)} · {measure.data_type} · {measure.period.end_year}")
    _render_growth(market)
    _render_competition(market)
    _render_capital_and_levels(market)
    if market.research_gaps:
        st.subheader("Open points")
        for gap in market.research_gaps:
            st.text(f"• {gap}")


def _render_growth(market):
    """Historical and forecast series, growth drivers and market risks."""
    for title, series_list in (("Historical data", market.historical_growth),
                               ("Forecasts and scenarios", market.forecast_growth)):
        if series_list:
            st.subheader(title)
        for series in series_list:
            points = series.points
            chart = go.Figure()
            for data_type in dict.fromkeys(point.data_type for point in points):
                selected = [point for point in points if point.data_type == data_type]
                chart.add_scatter(x=[point.period.end_year for point in selected],
                                  y=[point.value for point in selected], mode="lines+markers",
                                  name=data_type, text=[point.methodology for point in selected])
            chart.update_layout(title=series.metric, yaxis_title=points[0].unit,
                                xaxis=dict(title="Year", dtick=1))
            st.plotly_chart(chart, width="stretch")
            if series.cagr:
                st.caption(f"CAGR {series.cagr.period.start_year}–{series.cagr.period.end_year} · {_measure(series.cagr)}")
    for label, claims in (("Growth drivers", market.growth_drivers), ("Market risks", market.market_risks)):
        if claims:
            st.subheader(label)
            for claim in claims:
                st.text(claim.value)


def _render_competition(market):
    """Competitor and comparable-transaction tables."""
    if market.competitors:
        st.subheader("Competitive landscape")
        st.dataframe([{"Company": x.name, "Product": x.product, "Target customers": x.target_customers,
                       "Differentiation": x.differentiation, "Why comparable": x.selection_reason,
                       "Website": str(x.website)} for x in market.competitors],
                     hide_index=True, column_config={"Website": st.column_config.LinkColumn()})
        if market.comparison_dimensions:
            st.caption("Comparison dimensions · " + md_escape(", ".join(market.comparison_dimensions)))
    if market.comparable_transactions:
        st.subheader("Comparable transactions")
        st.dataframe([{"Company": x.company, "Date": x.date, "Type": x.transaction_type,
                       "Volume": _measure(x.transaction_value), "Valuation": _measure(x.company_valuation),
                       "Why comparable": x.comparability_reason, "Source": str(x.original_source)}
                      for x in market.comparable_transactions], hide_index=True,
                     column_config={"Source": st.column_config.LinkColumn()})


def _render_capital_and_levels(market):
    """Capital requirements and the TRL/MCL sector levels."""
    capital = market.capital_requirements
    capital_metrics = {
        "capital_need": "Capital need", "time_to_milestone": "Time to milestone",
        "burn_rate": "Burn rate", "cash_runway": "Cash runway", "investment_need": "Investment need",
    }
    if any(capital.model_dump(exclude_none=True).values()):
        st.subheader("Capital requirements")
        _claims(capital, {"planned_round": "Planned round", "use_of_funds": "Use of funds",
                          "next_milestone": "Next milestone"})
        for field, label in capital_metrics.items():
            if measure := getattr(capital, field):
                st.text(f"{label} · {_measure(measure)} · {measure.data_type} · {measure.methodology}")
    levels = market.sector_metrics
    for label, level, maximum in (("Technology Readiness Level", levels.technology_readiness, TRL_MAX),
                                  ("Market Certainty Level", levels.market_certainty, MCL_MAX)):
        if level:
            st.text(f"{label} · {level.level}/{maximum} · {level.rationale}")
