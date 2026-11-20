"""Render source-linked research in the startup detail view."""
import plotly.graph_objects as go
import streamlit as st


def _claims(owner, labels):
    for field, label in labels.items():
        claim = getattr(owner, field)
        if claim:
            st.text(f"{label} · {claim.value}")


def render_company_research(context):
    if context.founders:
        st.subheader("Gründerteam")
        for founder in context.founders:
            st.text(founder.name)
            _claims(founder, {"role": "Rolle", "qualifications": "Qualifikation", "previous_companies": "Frühere Unternehmen",
                              "founding_experience": "Gründungserfahrung",
                              "customer_problem_experience": "Erfahrung mit dem Kundenproblem"})
    _claims(context.company, {"headquarters": "Hauptsitz", "company_status": "Unternehmensstatus"})
    if context.company.founding_date:
        date_status = {"documented": "Quelle nennt ein Datum", "reported": "Sourcing-Angabe"}
        st.text(f"Gründung · {context.company.founding_date.value} · "
                f"{date_status.get(context.company.founding_date_status, 'Offen')}")
    elif context.company.founding_date_status == "conflicting":
        st.caption("Die Quellen nennen widersprüchliche Gründungsdaten.")
    _claims(context.product, {
        "customer_problem": "Kundenproblem", "solution": "Lösung", "target_customers": "Zielkunden",
        "economic_buyer": "Wirtschaftlicher Käufer", "business_model": "Geschäftsmodell",
        "advantage": "Wettbewerbsvorteil", "technology": "Technologie", "ip": "Schutzrechte",
        "development_status": "Entwicklungsstand", "next_milestone": "Produktmeilenstein",
    })
    funding = context.funding
    status_labels = {"unknown": "Unbekannt", "vc_backed": "VC-Finanzierung gemeldet",
                     "non_vc_funded": "Förderung oder Eigenfinanzierung dokumentiert",
                     "unfunded": "Unfinanziert gemeldet", "funded": "Finanzierungsart offen",
                     "conflicting": "Widersprüchliche Angaben"}
    vc_labels = {"unknown": "Unbekannt", "confirmed": "Beteiligung gemeldet", "reported_none": "Keine Beteiligung gemeldet",
                 "conflicting": "Widersprüchliche Angaben"}
    st.text(f"Finanzierungsstatus · {status_labels[funding.status]}")
    st.text(f"VC-Beteiligung · {vc_labels[funding.vc_status]}")
    for owner, fields in [
        (context.traction, {"paid_customers": "Zahlende Kunden", "customers_payment_unknown": "Kunden · Zahlstatus offen",
                            "paid_pilots": "Bezahlte Piloten", "unpaid_pilots": "Unbezahlte Piloten",
                            "pilots_payment_unknown": "Piloten · Zahlstatus offen", "lois": "Absichtserklärungen",
                            "commercial_partners": "Kommerzielle Partner", "research_partners": "Forschungspartner"}),
        (funding, {"public_grants": "Öffentliche Förderung", "rounds": "Frühere Runden", "investors": "Investoren"}),
    ]:
        for field, label in fields.items():
            if claims := getattr(owner, field):
                st.text(f"{label} · " + ", ".join(claim.value for claim in claims))
    _claims(context.traction, {"usage": "Produktnutzung", "revenue": "Umsatz", "growth": "Umsatzwachstum"})
    metric_labels = {"revenue": "Jahresumsatz", "revenue_growth": "Umsatzwachstum", "customer_count": "Kundenanzahl"}
    for kind, metrics in context.traction.reported_metrics.items():
        for measure in metrics:
            st.text(f"{metric_labels.get(kind, kind)} {measure.period.end_year} · {_measure(measure)}")
    _claims(funding, {"fundraising_status": "Fundraising", "planned_round": "Geplante Runde",
                      "capital_need": "Kapitalbedarf", "use_of_funds": "Mittelverwendung",
                      "next_milestone": "Finanzierungsmeilenstein", "time_to_milestone": "Zeitraum",
                      "burn_rate": "Burn Rate", "cash_runway": "Cash Runway"})


def _measure(value):
    if value is None:
        return "Offen"
    return f"{value.value:,.2f} {value.currency or ''} {value.unit}".replace(",", " ").strip()


def render_market(context):
    market = context.market_intelligence
    st.caption(f"Recherche aktualisiert am {context.updated_at:%d.%m.%Y}")
    if market.market_definition:
        st.text(market.market_definition.value)
    _claims(market, {"target_segment": "Zielsegment", "target_geography": "Zielgeografie"})
    for column, name in zip(st.columns(3), ("TAM", "SAM", "SOM")):
        measure = getattr(market, name.lower())
        column.metric(name, _measure(measure))
        if measure:
            column.caption(f"{measure.geography} · Bezugsjahr {measure.period.end_year} · "
                           f"{measure.data_type} · {measure.methodology}")
    if market.sizing_inputs:
        with st.expander("Daten und Annahmen zur Marktgröße"):
            for measure in market.sizing_inputs.values():
                st.text(f"{measure.methodology} · {_measure(measure)} · {measure.data_type} · {measure.period.end_year}")
    for title, series_list in (("Historische Daten", market.historical_growth),
                               ("Prognosen und Szenarien", market.forecast_growth)):
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
                                xaxis=dict(title="Jahr", dtick=1))
            st.plotly_chart(chart, width="stretch")
            if series.cagr:
                st.caption(f"CAGR {series.cagr.period.start_year}–{series.cagr.period.end_year} · {_measure(series.cagr)}")
    for label, claims in (("Wachstumstreiber", market.growth_drivers), ("Marktrisiken", market.market_risks)):
        if claims:
            st.subheader(label)
            for claim in claims:
                st.text(claim.value)
    if market.competitors:
        st.subheader("Wettbewerbsumfeld")
        st.dataframe([{"Unternehmen": x.name, "Produkt": x.product, "Zielkunden": x.target_customers,
                       "Differenzierung": x.differentiation, "Vergleichsgrund": x.selection_reason,
                       "Website": str(x.website)} for x in market.competitors],
                     hide_index=True, column_config={"Website": st.column_config.LinkColumn()})
        if market.comparison_dimensions:
            st.caption("Vergleichsdimensionen · " + ", ".join(market.comparison_dimensions))
    if market.comparable_transactions:
        st.subheader("Vergleichstransaktionen")
        st.dataframe([{"Unternehmen": x.company, "Datum": x.date, "Typ": x.transaction_type,
                       "Volumen": _measure(x.transaction_value), "Bewertung": _measure(x.company_valuation),
                       "Vergleichsgrund": x.comparability_reason, "Quelle": str(x.original_source)}
                      for x in market.comparable_transactions], hide_index=True,
                     column_config={"Quelle": st.column_config.LinkColumn()})
    capital = market.capital_requirements
    capital_metrics = {
        "capital_need": "Kapitalbedarf", "time_to_milestone": "Zeitraum bis zum Meilenstein",
        "burn_rate": "Burn Rate", "cash_runway": "Cash Runway", "investment_need": "Investitionsbedarf",
    }
    if any(capital.model_dump(exclude_none=True).values()):
        st.subheader("Kapitalbedarf")
        _claims(capital, {"planned_round": "Geplante Runde", "use_of_funds": "Mittelverwendung",
                          "next_milestone": "Nächster Meilenstein"})
        for field, label in capital_metrics.items():
            if measure := getattr(capital, field):
                st.text(f"{label} · {_measure(measure)} · {measure.data_type} · {measure.methodology}")
    levels = market.sector_metrics
    for label, level, maximum in (("Technology Readiness Level", levels.technology_readiness, 9),
                                  ("Market Certainty Level", levels.market_certainty, 6)):
        if level:
            st.text(f"{label} · {level.level}/{maximum} · {level.rationale}")
    if market.research_gaps:
        st.subheader("Offene Punkte")
        for gap in market.research_gaps:
            st.text(f"• {gap}")
