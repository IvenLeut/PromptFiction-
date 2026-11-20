"""Research panels: supplied facts only; charts require comparable sourced observations."""
import plotly.graph_objects as go
import streamlit as st

from cockpit_data import items, known, number, url, investment_scenario
from cockpit_style import fact_rows


def facts(values):
    fact_rows(values)


def source_links(rows):
    links = sorted({url(row.get("source")) for row in rows if url(row.get("source"))})
    for link in links:
        st.link_button("Source: " + link.split("/")[2], link)


def comparable_series(rows):
    """Do not join different market definitions, geographies, units or vintages."""
    valid = [r for r in rows if isinstance(r, dict) and number(r.get("value")) is not None
             and isinstance(r.get("year"), int) and not isinstance(r.get("year"), bool)
             and url(r.get("source")) and all(r.get(k) for k in ("unit", "definition", "geography", "as_of"))
             and r.get("kind") in {"Historical", "Forecast"}]
    groups = {(r["unit"], r["definition"], r["geography"], r["as_of"]) for r in valid}
    if len(valid) != len(rows) or len(valid) < 2 or len(groups) != 1:
        return []
    if len({r["year"] for r in valid}) != len(valid):
        return []
    return sorted(valid, key=lambda r: r["year"])


def market(lead):
    st.subheader("Market Intelligence")
    st.caption("Market definition, addressable opportunity and growth drivers")
    d = lead.data
    research = d.get("market_intelligence") or {}
    if not isinstance(research, dict):
        research = {}
    if not research:
        left, right = st.columns([1.5, 1])
        with left, st.container(border=True, key="card-market-context"):
            st.subheader("Available market context")
            facts({"Target market": d.get("target_market") or d.get("market"), "Customers": d.get("target_customers")})
            evidence = [e for e in lead.evidence if e["category"] == "Market" and e["url"]]
            if evidence:
                st.dataframe(evidence, column_order=["statement", "criterion", "url"], column_config={"url": st.column_config.LinkColumn("Source")}, hide_index=True, width="stretch")
            else:
                st.caption("No sourced market evidence supplied.")
        with right, st.container(border=True, key="card-market-next"):
            st.subheader("Research to complete")
            st.markdown("1. Define the customer segment and geography.\n2. Source TAM, SAM and SOM with year and methodology.\n3. Validate growth drivers and buyer budgets.")
            st.caption("Market sizing and growth charts appear when comparable, sourced research is available from the pipeline.")
        return
    facts({"Market definition": research.get("definition") or d.get("target_market") or d.get("market"),
           "Target geography": research.get("geography"), "Reference year": research.get("year"),
           "Methodology": research.get("methodology")})
    sizing = research.get("sizing") or []
    valid = [r for r in sizing if isinstance(r, dict) and r.get("label") in {"TAM", "SAM", "SOM"}
             and number(r.get("value")) is not None and url(r.get("source")) and r.get("unit")]
    if (len(valid) == 3 and {r["label"] for r in valid} == {"TAM", "SAM", "SOM"}
            and len({r["unit"] for r in valid}) == 1 and all(research.get(k) for k in ("definition", "geography", "year", "methodology"))
            and dict((r["label"], r["value"]) for r in valid)["TAM"] >= dict((r["label"], r["value"]) for r in valid)["SAM"] >= dict((r["label"], r["value"]) for r in valid)["SOM"]):
        fig = go.Figure(go.Bar(x=[r["value"] for r in valid], y=[r["label"] for r in valid],
                               orientation="h", marker_color=["#24384b", "#637f91", "#ee795b"], name="Market size"))
        fig.update_layout(height=250, xaxis_title=valid[0]["unit"], yaxis_title="Market scope", margin=dict(l=0, r=20, t=10, b=20))
        st.plotly_chart(fig, width="stretch")
        source_links(valid)
    else:
        st.info("TAM / SAM / SOM not charted: comparable, sourced sizing and methodology required.")
    series = comparable_series(research.get("growth_series") or [])
    if series:
        fig = go.Figure()
        for kind, color, dash in (("Historical", "#24384b", "solid"), ("Forecast", "#ee795b", "dash")):
            rows = [r for r in series if r["kind"] == kind]
            if rows:
                fig.add_trace(go.Scatter(x=[r["year"] for r in rows], y=[r["value"] for r in rows],
                                        mode="lines+markers", name=kind, line=dict(color=color, dash=dash)))
        fig.update_layout(height=310, xaxis=dict(title="Year", dtick=1), yaxis_title=series[0]["unit"],
                          legend=dict(orientation="h"), margin=dict(l=0, r=20, t=10, b=20))
        st.plotly_chart(fig, width="stretch")
        first, last = series[0], series[-1]
        if first["value"] > 0 and last["year"] > first["year"]:
            cagr = (last["value"] / first["value"]) ** (1 / (last["year"] - first["year"])) - 1
            st.caption(f"Implied CAGR {first['year']}–{last['year']}: {cagr:.1%}. Includes forecasts where shown. Data as of {first['as_of']}.")
        source_links(series)
    else:
        st.caption("Growth chart unavailable: at least two comparable, dated and sourced observations are required.")
    facts({"Growth": research.get("growth"), "Maturity": research.get("maturity"),
           "Competition intensity": research.get("competition_intensity"), "Commercialization potential": research.get("commercialization_potential"),
           "Growth drivers": research.get("drivers"), "Key uncertainties": research.get("uncertainties")})
    evidence = [e for e in lead.evidence if e["category"] == "Market" and e["url"]]
    if evidence:
        st.markdown("#### Available market evidence")
        st.dataframe(evidence, column_order=["statement", "criterion", "url"], column_config={"url": st.column_config.LinkColumn("Source")}, hide_index=True, width="stretch")
    st.caption("Market research is supplied by the upstream pipeline. On-demand external research is not connected.")


def competition(lead):
    st.subheader("Competitive Landscape")
    d = lead.data
    competitors = items(d.get("competitors"))
    rows = [{"Company": c} if isinstance(c, str) else {
        label: c.get(key) for label, key in (("Company", "name"), ("Product", "product"), ("Customer segment", "customer_segment"),
        ("Geography", "geography"), ("Stage", "stage"), ("Differentiation", "differentiation"), ("Funding", "funding"), ("Source", "source"))}
        for c in competitors if isinstance(c, (str, dict))]
    if rows:
        for row in rows:
            if "Source" in row:
                row["Source"] = url(row["Source"])
        st.dataframe(rows, hide_index=True, width="stretch", column_config={"Source": st.column_config.LinkColumn()})
    else:
        st.info("No structured competitor comparison supplied.")
    facts({"Research": d.get("competition"), "Differentiation": d.get("differentiation"),
           "Technology": d.get("technology_advantage") or d.get("technology"), "IP / patents": d.get("ip"),
           "Switching costs": d.get("switching_costs"), "Network effects": d.get("network_effects"), "Weaknesses": d.get("competitive_weaknesses")})
    matrix = d.get("competitive_positioning") or {}
    points = matrix.get("points", []) if isinstance(matrix, dict) else []
    if (len(points) >= 2 and all(matrix.get(k) for k in ("x_label", "y_label", "rationale"))
            and all(isinstance(p, dict) and url(p.get("source")) and number(p.get("x")) is not None and number(p.get("y")) is not None for p in points)):
        fig = go.Figure(go.Scatter(x=[p["x"] for p in points], y=[p["y"] for p in points],
                                  mode="markers+text", text=[p.get("name", "") for p in points], textposition="top center",
                                  marker=dict(size=13, color="#ee795b")))
        fig.update_layout(xaxis_title=matrix["x_label"], yaxis_title=matrix["y_label"], height=330)
        st.plotly_chart(fig, width="stretch")
        st.caption(matrix["rationale"])
        source_links(points)
    else:
        st.caption("Positioning map requires sourced coordinates and a documented rationale for both axes.")


def funding(lead):
    st.subheader("Funding & Valuation")
    d = lead.data
    facts({"Funding status": d.get("funding_status") or d.get("funding_stage"), "Raised (EUR)": d.get("funding_total_eur"),
           "Investors": d.get("investors"), "Grants": d.get("grants"), "Capital need": d.get("capital_need"),
           "Round size (EUR)": d.get("round_size_eur"), "Next milestone": d.get("next_milestone")})
    if d.get("funding_events"):
        st.dataframe(d["funding_events"], hide_index=True, width="stretch")
    st.markdown("#### Investment scenario")
    st.caption("Editable analyst assumptions in EUR. Illustrative defaults are not company valuations or investment recommendations.")
    a, b, c, e = st.columns(4)
    key = lead.namespace + lead.id
    investment = a.number_input("Investment amount (EUR)", min_value=1.0, value=800000.0, step=100000.0, key=key+"invest")
    pre = b.number_input("Pre-money valuation (EUR)", min_value=0.0, value=3200000.0, step=100000.0, key=key+"pre")
    dilution = c.number_input("Future dilution (%)", min_value=0.0, max_value=100.0, value=20.0, key=key+"dilution")
    exit_value = e.number_input("Exit equity value (EUR)", min_value=0.0, value=20000000.0, step=1000000.0, key=key+"exit")
    result = investment_scenario(investment, pre, dilution / 100, exit_value)
    for col, (label, value) in zip(st.columns(5), result.items()):
        col.metric(label, f"{value:.1%}" if "ownership" in label.lower() else f"{value:.2f}×" if label == "MOIC" else f"€{value:,.0f}")
    st.caption("Exit equity value = proceeds available to all equity holders after net debt. Pro rata ordinary equity model; preferences, different share classes, fees, taxes and further rounds can change actual proceeds. Not a full cap table.")
    st.markdown("#### Comparable transactions")
    comps = []
    for row in items(d.get("comparable_transactions")):
        if not isinstance(row, dict):
            continue
        metric = row.get("multiple_basis")
        denominator = number(row.get("revenue") if metric == "EV/Revenue" else row.get("ebitda") if metric == "EV/EBITDA" else None)
        value = number(row.get("value"))
        multiple = value / denominator if denominator and value is not None and row.get("value_type") == "Enterprise Value" and row.get("metrics_comparable") is True else None
        comps.append({"Company": row.get("name"), "Transaction": row.get("type"), "Date": row.get("date"), "Value": value,
                      "Currency": row.get("currency"), "Value basis": row.get("value_type"), "Revenue": row.get("revenue"),
                      "EBITDA": row.get("ebitda"), "Multiple": multiple, "Basis": metric, "Source": url(row.get("source"))})
    if comps:
        st.dataframe(comps, hide_index=True, width="stretch", column_config={"Source": st.column_config.LinkColumn()})
    else:
        st.caption("No comparable financings or exits supplied.")


def sector_research(lead):
    d = lead.data
    st.markdown("#### Sector-specific diligence")
    research = d.get("sector_research") or {}
    if not isinstance(research, dict):
        research = {}
    if lead.sector in {"Life Sciences", "Chemistry"}:
        keys = ["Development stage", "Regulatory pathway", "Clinical or technical milestones", "Patent protection", "Next catalyst", "Funding to milestone"]
        st.caption("Focus: regulatory pathway, development milestones and runway to the next catalyst.")
    elif lead.sector in {"Industrial / DeepTech", "ClimateTech"}:
        keys = ["Technology readiness", "Market readiness", "IP", "Commercial pilots", "Technical milestones", "Capital intensity", "Scale-up risk"]
        st.caption("Focus: technology validation, commercial pilots and capital required to scale.")
    else:
        keys = ["ARR", "Growth", "Product adoption", "Retention", "Scalability", "Unit economics"]
    facts({key: research.get(key.lower().replace(" ", "_")) for key in keys})
    if lead.sector in {"Industrial / DeepTech", "ClimateTech"}:
        with st.expander("Technology × Market Readiness — analyst workspace"):
            st.caption("Analyst assumptions only; not a sourced company rating or an official HTGF classification. Axes: 1 = concept, 5 = validated, 9 = scaled.")
            tech = st.slider("Technology readiness", 1, 9, 1, key=lead.id+"trl")
            market_value = st.slider("Market readiness", 1, 9, 1, key=lead.id+"mrl")
            fig = go.Figure(go.Scatter(x=[tech], y=[market_value], mode="markers", name="Analyst scenario", marker=dict(size=18, color="#ee795b")))
            fig.update_layout(height=300, xaxis=dict(title="Technology readiness (analyst)", range=[.5, 9.5], dtick=1),
                              yaxis=dict(title="Market readiness (analyst)", range=[.5, 9.5], dtick=1))
            st.plotly_chart(fig, width="stretch")
            st.link_button("HTGF Deep-Tech Matrix — conceptual reference", "https://www.htgf.de/deep-tech-matrix/")
