"""Step 4: presentation only; scores are supplied by step 3."""
from urllib.parse import quote

import plotly.graph_objects as go
import streamlit as st

from models import EvaluatedLead, ResearchResult


def shortlist(leads, industry="Alle Branchen", top_n=10):
    candidates = [x for x in leads if industry == "Alle Branchen" or x.industry.value == industry]
    return sorted(candidates, key=lambda x: (x.overall_score is None, -(x.overall_score or 0), x.id))[:top_n]


def contact_url(lead: EvaluatedLead) -> str | None:
    if not lead.contact_email:
        return None
    subject = quote(f"Austausch zu {lead.name}", safe="")
    body = quote(f"Hallo,\n\nwir sind auf {lead.name} aufmerksam geworden und würden gerne mehr "
                 "über euer Unternehmen erfahren. Habt ihr Zeit für einen kurzen Austausch?\n\nViele Grüße", safe="")
    return f"mailto:{quote(lead.contact_email, safe='@')}?subject={subject}&body={body}"


def build_figure(leads, selected_id=None):
    complete = [x for x in leads if all(v is not None for v in
                (x.risk_score, x.company_score, x.market_potential_score))]
    fig = go.Figure(go.Scatter3d(
        x=[x.risk_score for x in complete], y=[x.company_score for x in complete],
        z=[x.market_potential_score for x in complete], mode="markers",
        text=[x.name for x in complete], customdata=[x.id for x in complete],
        marker=dict(size=[11 if x.id == selected_id else 8 for x in complete],
                    color=[x.risk_score for x in complete],
                    colorscale=[[0, "#106049"], [.5, "#f5653f"], [1, "#aa2c20"]],
                    cmin=0, cmax=100, opacity=.95, line=dict(color="#ffffff", width=1),
                    colorbar=dict(title="Risiko", thickness=12, len=.65, outlinewidth=0,
                                  tickvals=[0, 50, 100], ticktext=["0 · gering", "50", "100 · hoch"])),
        hovertemplate="<b>%{text}</b><br>Risiko: %{x}/100<br>Unternehmen: %{y}/100<br>Marktpotenzial: %{z}/100<extra></extra>",
    ))
    axis = dict(range=[0, 100], tickvals=[0, 25, 50, 75, 100],
                gridcolor="#dfe3e6", backgroundcolor="#f7f8f9", showbackground=True,
                zerolinecolor="#b8bec4", color="#626971")
    fig.update_layout(height=590, margin=dict(l=0, r=30, t=0, b=0),
        paper_bgcolor="#ffffff", font=dict(family="Arial, sans-serif", color="#221f19", size=13),
        hoverlabel=dict(bgcolor="#221f19", font_color="#ffffff", bordercolor="#221f19"),
        scene=dict(xaxis=dict(**axis, title="Risiko"),
                   yaxis=dict(**axis, title="Unternehmensscore"),
                   zaxis=dict(**axis, title="Marktpotenzial"),
                   aspectmode="cube", camera=dict(eye=dict(x=1.6, y=1.6, z=1.1))),
        uirevision="startup-map")
    return fig, len(leads) - len(complete)


def value(item, suffix=""):
    return "Unbekannt" if item is None else f"{item:,.0f}{suffix}".replace(",", ".")


def back_to_overview():
    st.query_params.pop("startup", None)
    # A fresh table key clears the selection and prevents immediate re-entry.
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


def open_selected_row(event, shown):
    rows = event.selection.rows
    if rows and 0 <= rows[0] < len(shown):
        st.query_params["startup"] = shown[rows[0]].id
        return True
    return False


def render_dashboard(result: ResearchResult, analysis=None):
    from hashlib import sha256
    from analyst_store import load_decisions
    from charts import stage_figure, comparison_figure
    from deep_dive import render_deep_dive
    from screening import filter_leads, review_status, high_priority
    from ui_theme import heading

    namespace = "demo" if (analysis and analysis.mode == "demo") or all(x.is_demo for x in result.leads) else "live"
    try:
        decisions = load_decisions(namespace)
    except Exception:
        st.error("Analystenentscheidungen konnten nicht geladen werden. Bitte Datenbankzugriff prüfen.")
        return
    for issue in result.issues:
        st.warning(f"{issue.lead_id}: {issue.message}")
    requested_id = st.query_params.get("startup")
    if requested_id:
        lead = next((x for x in result.leads if x.id == requested_id), None)
        if lead is not None:
            render_deep_dive(lead, back_to_overview, contact_url, value, namespace=namespace,
                             decision=decisions.get(lead.id))
            return
        st.warning("Dieses Startup ist im aktuellen Suchlauf nicht vorhanden.")
        st.button("Zurück zur Übersicht", on_click=back_to_overview)
        return
    heading("FounderRadar / Investment Screening Cockpit", "Früh entdecken. Klar entscheiden.",
            "Priorisierte Startup-Longlist für die erste Kontaktentscheidung. Quellenfakten, KI-Einschätzungen und Analystenentscheidungen bleiben unterscheidbar.")
    if not result.leads:
        st.info("Noch keine bewerteten Startups vorhanden.")
        return
    if namespace == "demo":
        st.caption("DEMO · Fiktive Startups, Bewertung und Quellen. Neue, unbelegte Angaben bleiben Unknown.")
    metrics = st.columns(4)
    metrics[0].metric("Total Leads", len(result.leads))
    metrics[1].metric("High-Priority Leads", sum(high_priority(x, decisions) for x in result.leads))
    metrics[2].metric("Pending Review", sum(review_status(x, decisions) == "Pending Review" for x in result.leads))
    metrics[3].metric("Contact Candidates", sum(review_status(x, decisions) == "Contact" for x in result.leads))
    st.caption("Gesamter Analyselauf · High Priority: bestätigter Fund Fit, Quality ≥75, Fit ≥70, Earliness ≥70; kein Ausschluss/Reject. Contact Candidates: explizite Analystenentscheidung Contact.")
    search = st.text_input("Unternehmen oder Branche suchen", placeholder="Name oder Technologiefeld eingeben …", key="cockpit_search")
    with st.expander("Filter und Priorisierung"):
        a, b, c = st.columns(3)
        locations = a.multiselect("Standort", sorted({x.location or "Unknown" for x in result.leads}), key="cockpit_locations")
        industries = b.multiselect("Branche", sorted({x.industry.value for x in result.leads}), key="cockpit_industries")
        stages = c.multiselect("Stage", sorted({x.stage_classification for x in result.leads}), key="cockpit_stages")
        d, e = st.columns(2)
        fit = d.selectbox("Fund Fit", ["Alle", "Passend", "Ungeklärt", "Ausgeschlossen"], key="cockpit_fit")
        statuses = e.multiselect("Screening Status", ["Pending Review", "Contact", "Watchlist", "Reject", "Excluded"], key="cockpit_statuses")
    left, right = st.columns([3, 1])
    order = left.selectbox("Sortieren nach", ["Priorität", "Quality Score", "Fund Fit", "Earliness", "Entdeckungsdatum"], key="cockpit_sort")
    saved = st.session_state.get("portfolio_top_n", 0)
    top_n = right.selectbox("Ranking anzeigen", [0, 10, 20], index=[0, 10, 20].index(saved) if saved in [0,10,20] else 0,
                            format_func=lambda x: "Alle Startups" if x == 0 else f"Top {x}", key="top_filter")
    st.session_state.portfolio_top_n = top_n
    filtered = filter_leads(result.leads, decisions, search=search, locations=locations, industries=industries,
                            stages=stages, fit=fit, statuses=statuses, sort_by=order)
    shown = filtered[:top_n] if top_n else filtered
    st.caption(f"{len(shown)} angezeigt / {len(filtered)} passend / {len(result.leads)} insgesamt. Ausschlüsse sind sichtbar und werden bei Standardpriorisierung zurückgestellt.")
    if not shown:
        st.info("Keine Unternehmen entsprechen den gewählten Filtern.")
        return
    rows = [{"Unternehmen": x.name, "Value Proposition": x.value_proposition,
             "Branche": x.industry.value, "Standort": x.location or "Unknown",
             "Stage": x.stage_classification,
             "Fund Fit": "Excluded" if x.hard_exclusions or x.eligibility_status == "Excluded" else
                         (f"{x.fund_fit_score:.0f}/100" if x.fund_fit_score is not None else "Unknown"),
             "Quality Score": x.overall_score, "Earliness Score": x.earliness_score,
             "Screening Status": review_status(x, decisions),
             "Priorität": "Hoch" if high_priority(x, decisions) else "—"} for x in shown]
    signature = sha256("|".join(x.id for x in shown).encode()).hexdigest()[:12]
    table_key = f"ranking_{signature}_{st.session_state.get('table_generation', 0)}"
    config = {
        "Unternehmen": st.column_config.TextColumn("Unternehmen / Deep Dive", width="medium"),
        "Value Proposition": st.column_config.TextColumn("Value Proposition", width="medium"),
        "Quality Score": st.column_config.ProgressColumn("Quality", min_value=0, max_value=100, format="%.0f"),
        "Earliness Score": st.column_config.ProgressColumn("Earliness", min_value=0, max_value=100, format="%.0f"),
    }
    event = st.dataframe(rows, hide_index=True, width="stretch", height=min(700, 40 + len(rows) * 44),
                        row_height=44, column_config=config, on_select="rerun", selection_mode="single-row", key=table_key)
    if open_selected_row(event, shown):
        st.rerun()
    st.caption("Zeile anklicken für das Investment Briefing. Quality bezeichnet den bisherigen Gesamt-Score. Unknown-Fit bedeutet ungeprüfte Eignung.")
    with st.expander("Visuelle Portfolioanalyse", expanded=False):
        st.caption("Die Diagramme beziehen sich auf die gefilterte und angezeigte Liste. Fehlende Werte werden nicht als null gezeichnet.")
        space, stage = st.columns([2, 1])
        with space:
            st.subheader("Risiko / Unternehmen / Markt")
            fig, omitted = build_figure(shown)
            st.plotly_chart(fig, width="stretch", key="startup_3d", theme=None,
                            config={"displaylogo": False, "scrollZoom": True})
            if omitted:
                st.caption(f"{omitted} Startups ohne vollständige Achsenwerte ausgelassen.")
        with stage:
            st.subheader("Stage-Verteilung")
            st.plotly_chart(stage_figure(shown), width="stretch", theme=None, key="stage_distribution")
        st.plotly_chart(comparison_figure(shown), width="stretch", theme=None, key="score_comparison")
    if analysis:
        st.download_button("Analyse als JSON exportieren", analysis.model_dump_json(indent=2),
                           file_name="founder-radar-analysis.json", mime="application/json")