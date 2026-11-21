"""Source-linked displays for the typed company and market research contract."""
from html import escape

import plotly.graph_objects as go
import streamlit as st

from cockpit_context import claim_text, context_for, evidence_for, market_for, measure_label, present
from cockpit_data import url
from cockpit_style import fact_rows
from cockpit_visuals import base

COLORS = ["#d59c85", "#b9869b", "#71aeb7", "#b7b883"]


def provenance(lead, value):
    sources = evidence_for(lead, value)
    kind = value.get("data_type") or value.get("origin", "") if isinstance(value, dict) else ""
    if any(e["verification"] == "Demo / assumption" for e in sources):
        return "Estimate · includes assumptions" if kind == "estimate" else "Demo / assumption"
    return {"source_statement": "Source statement", "model_selected_quote": "Extracted quotation",
            "analyst_interpretation": "Analyst interpretation", "observed": "Reported observation",
            "estimate": "Estimate", "forecast": "Forecast", "assumption": "Analyst assumption"}.get(kind, "Reported")


def reference_links(lead, value):
    sources = evidence_for(lead, value)
    links = {e["url"]: e.get("source") or "Source" for e in sources if e["url"]}
    return " · ".join(f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(name)}</a>' for link, name in links.items())


def fields(lead, owner, labels):
    """Compact rows retain claim meaning, type and clickable evidence."""
    rows = []
    for key, label in labels.items():
        value = owner.get(key)
        if not present(value):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            rendered = measure_label(item) if isinstance(item, dict) and isinstance(item.get("value"), (int, float)) else claim_text(item)
            if not present(rendered):
                continue
            sources = reference_links(lead, item)
            note = provenance(lead, item) if isinstance(item, dict) else "Supplied information"
            if isinstance(item, dict) and item.get("evidence_ids") and not sources:
                note += " · source reference unresolved"
            if isinstance(item, dict) and item.get("period"):
                period = item["period"]
                years = str(period["start_year"]) if period["start_year"] == period["end_year"] else f"{period['start_year']}–{period['end_year']}"
                note += f" · {years} · {item.get('geography', '')}"
            rows.append(f'<div class="research-row"><span>{escape(label)}</span><div>{escape(str(rendered))}<small>{escape(note)}{(" · " + sources) if sources else ""}</small></div></div>')
    if rows:
        st.markdown("".join(rows), unsafe_allow_html=True)
    return bool(rows)


def sources_note(lead, values):
    links = {}
    for value in values:
        for e in evidence_for(lead, value):
            if e["url"]:
                links[e["url"]] = e.get("source") or "Source"
    if links:
        st.markdown('<div class="source-line">Sources · ' + " · ".join(f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(name)}</a>' for link, name in links.items()) + '</div>', unsafe_allow_html=True)


def series_figure(series):
    """Never connect incompatible currencies, units, regions, methods or periods."""
    points = series.get("points") or []
    groups = {}
    for p in points:
        if not isinstance(p.get("value"), (int, float)) or not p.get("period"):
            continue
        key = (p.get("unit"), p.get("currency"), p.get("geography"), p.get("methodology"), p.get("data_type"))
        groups.setdefault(key, []).append(p)
    fig = base(245)
    for index, (key, values) in enumerate(groups.items()):
        values = sorted(values, key=lambda p: p["period"]["end_year"])
        years = [p["period"]["end_year"] for p in values]
        comparable = len(years) == len(set(years)) and all(p["period"]["start_year"] == p["period"]["end_year"] for p in values)
        fig.add_trace(go.Scatter(x=years, y=[p["value"] for p in values], mode="lines+markers" if comparable and len(values) > 1 else "markers",
                                name=" · ".join(str(x) for x in (key[4], key[1], key[0], key[2]) if x),
                                line=dict(color=COLORS[index % len(COLORS)], width=3, dash="solid" if key[4] == "observed" else "dash"),
                                marker_size=7, fill="tozeroy" if len(groups) == 1 else None,
                                fillcolor="rgba(205,232,234,.28)"))
    same_units = len({(k[0], k[1]) for k in groups}) <= 1
    if not same_units:
        return None
    fig.update_xaxes(title="Reference year", dtick=1)
    fig.update_yaxes(title=" ".join(str(v) for v in (points[0].get("currency"), points[0].get("unit")) if v) if points else "")
    fig.update_layout(showlegend=len(groups) > 1, legend=dict(orientation="h", y=-.3))
    return fig


def native_market(lead):
    market = market_for(lead)
    fields(lead, market, {"market_definition": "Market definition", "target_segment": "Target segment", "target_geography": "Geography"})
    sizing = [(label.upper(), market[label]) for label in ("tam", "sam", "som") if market.get(label)]
    if sizing:
        columns = st.columns(len(sizing))
        for column, (label, value) in zip(columns, sizing):
            with column, st.container(border=True):
                st.metric(label, measure_label(value))
                st.caption(f"{provenance(lead, value)} · {value['period']['end_year']} · {value['geography']}")
                sources_note(lead, [value])
    left, right = st.columns([1.6, 1])
    with left:
        series = [*market.get("historical_growth", []), *market.get("forecast_growth", [])]
        for index, observation in enumerate(series):
            with st.container(border=True):
                st.subheader(observation["metric"])
                fig = series_figure(observation)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch", key=f"market-series-{lead.id}-{index}", config={"displayModeBar": False})
                else:
                    st.caption("Different units or currencies; observations shown separately.")
                sources_note(lead, observation["points"])
                if observation.get("cagr"):
                    fields(lead, observation, {"cagr": "CAGR"})
                with st.expander("Underlying observations"):
                    fields(lead, {"observations": observation["points"]}, {"observations": observation["metric"]})
        if not series:
            st.caption("No comparable market time series supplied.")
        for key, label in (("growth_drivers", "Growth drivers"), ("market_risks", "Market risks")):
            if market.get(key):
                with st.container(border=True):
                    st.subheader(label)
                    fields(lead, market, {key: label})
        for key, claims in (market.get("growth_factors") or {}).items():
            fields(lead, {key: claims}, {key: key.title() + " drivers"})
    with right:
        inputs = market.get("sizing_inputs") or {}
        if sizing or inputs:
            with st.container(border=True):
                st.subheader("Market sizing model")
                st.caption("Derived opportunity, not company revenue. Assumptions remain visible.")
                fields(lead, inputs, {key: key.replace("_", " ").title() for key in inputs})
                with st.expander("Calculation and methodology"):
                    for label, measure in sizing:
                        st.write(f"**{label}:** {measure['methodology']}")
        if market.get("research_gaps"):
            with st.container(border=True):
                st.subheader("Research priorities")
                for gap in market["research_gaps"][:3]:
                    st.write("• " + gap)
                if len(market["research_gaps"]) > 3:
                    with st.expander("All open research questions"):
                        for gap in market["research_gaps"][3:]:
                            st.write("• " + gap)


def native_competition(lead):
    market = market_for(lead)
    rows = []
    for competitor in market.get("competitors", []):
        refs = evidence_for(lead, competitor)
        rows.append({"Company": competitor["name"], "Product": competitor.get("product"), "Customers": competitor.get("target_customers"),
                     "Segment": competitor.get("segment"), "Geography": competitor.get("geography"), "Stage": competitor.get("development_stage"),
                     "Differentiation": competitor.get("differentiation"), "Why comparable": competitor.get("selection_reason"),
                     "Funding": measure_label(competitor["known_funding"]) if competitor.get("known_funding") else None,
                     "Website": url(competitor.get("website")), "Source": next((e["url"] for e in refs if e["url"]), None)})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch", column_config={"Website": st.column_config.LinkColumn(), "Source": st.column_config.LinkColumn(), "Product": st.column_config.TextColumn(width=230), "Why comparable": st.column_config.TextColumn(width=270)})
        if market.get("comparison_dimensions"):
            st.caption("Comparison dimensions · " + " · ".join(market["comparison_dimensions"]))
    return bool(rows)


def transactions(lead):
    rows = market_for(lead).get("comparable_transactions") or []
    if not rows:
        return False
    st.subheader("Comparable transactions")
    for transaction in rows:
        with st.container(border=True):
            st.markdown(f"**{transaction['company']}** · {transaction['date']} · {transaction['transaction_type'].replace('_', ' ').title()}")
            st.caption(transaction.get("sector", ""))
            fields(lead, transaction, {"transaction_value": "Financing volume", "company_valuation": "Company valuation", "enterprise_value": "Enterprise value", "revenue": "Revenue", "ebitda": "EBITDA", "ev_revenue": "EV / revenue", "ev_ebitda": "EV / EBITDA"})
            st.write(transaction["comparability_reason"])
            if url(transaction.get("original_source")):
                st.link_button("Original transaction announcement", url(transaction["original_source"]))
    return True


def capital(lead):
    context = context_for(lead)
    funding = context.get("funding") or {}
    status = funding.get("status") if funding.get("status") != "unknown" else lead.data.get("funding_status")
    vc = funding.get("vc_status") if funding.get("vc_status") != "unknown" else lead.data.get("vc_status")
    status = "Conflicting sources" if status == "conflicting" else status
    fact_rows({"Funding classification": status, "VC participation": vc,
               "Prior VC reported": lead.data.get("has_vc")})
    sources_note(lead, [{"evidence_ids": funding.get("evidence_ids", [])}])
    fields(lead, funding, {"rounds": "Previous rounds", "investors": "Investors", "public_grants": "Public grants",
           "fundraising_status": "Fundraising", "planned_round": "Planned round", "capital_need": "Capital need",
           "use_of_funds": "Use of funds", "next_milestone": "Funding milestone", "time_to_milestone": "Time to milestone",
           "burn_rate": "Burn rate", "cash_runway": "Cash runway"})
    requirements = market_for(lead).get("capital_requirements") or {}
    fields(lead, requirements, {key: key.replace("_", " ").title() for key in requirements})


def sector_metrics(lead):
    metrics = market_for(lead).get("sector_metrics") or {}
    available = {key: value for key, value in metrics.items() if present(value)}
    if not available:
        return False
    levels = {key: available.pop(key) for key in ("technology_readiness", "market_certainty") if available.get(key)}
    units = available.pop("unit_economics", {})
    fields(lead, available, {key: key.replace("_", " ").upper() if key == "arr" else key.replace("_", " ").title() for key in available})
    fields(lead, units, {key: key.replace("_", " ").title() for key in units})
    for key, level in levels.items():
        maximum = 9 if key == "technology_readiness" else 6
        st.markdown(f"**{key.replace('_', ' ').title()}: {level['level']}/{maximum}**")
        st.caption(level["rationale"] + " · " + level.get("origin", ""))
        sources_note(lead, [level])
    if len(levels) == 2:
        fig = base(220)
        fig.add_scatter(x=[levels["technology_readiness"]["level"]], y=[levels["market_certainty"]["level"]], mode="markers", marker=dict(size=18, color="#b9869b"))
        fig.update_xaxes(title="Technology readiness", range=[.5, 9.5], dtick=1)
        fig.update_yaxes(title="Market certainty", range=[.5, 6.5], dtick=1)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    return True


def traction(lead):
    data = context_for(lead).get("traction") or {}
    fields(lead, data, {"paid_customers": "Paying customers", "customers_payment_unknown": "Customers · payment unknown",
           "paid_pilots": "Paid pilots", "unpaid_pilots": "Unpaid pilots", "pilots_payment_unknown": "Pilots · payment unknown",
           "lois": "Letters of intent", "commercial_partners": "Commercial partners", "research_partners": "Research partners",
           "usage": "Product usage", "revenue": "Reported revenue", "growth": "Reported growth"})
    for metric, values in (data.get("reported_metrics") or {}).items():
        st.subheader(metric.replace("_", " ").title())
        if len(values) > 1:
            figure = series_figure({"points": values})
            if figure is not None:
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
        fields(lead, {metric: values}, {metric: metric.replace("_", " ").title()})
