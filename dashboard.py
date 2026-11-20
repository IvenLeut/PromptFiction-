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
    from charts import stage_figure, comparison_figure
    from deep_dive import render_deep_dive
    from ui_theme import heading, summary_kpis

    for issue in result.issues:
        st.warning(f"{issue.lead_id}: {issue.message}")
    if not result.leads:
        st.info("Für diese Kategorie liegen noch keine bewerteten Startups vor. Starte eine neue Analyse.")
        return
    requested_id = st.query_params.get("startup")
    if requested_id:
        lead = next((x for x in result.leads if x.id == requested_id), None)
        if lead is not None:
            render_deep_dive(lead, back_to_overview, contact_url, value)
            return
        st.warning("Dieses Startup ist im aktuellen Suchlauf nicht vorhanden.")
        st.button("Zurück zur Übersicht", on_click=back_to_overview)
        return

    category = analysis.criteria.industry.value if analysis else "Tech-Startups"
    heading("Dein Investment-Radar", f"{category}. Potenzial im Blick.",
            "Unternehmensstärke, Marktchance und Risiko. Die wichtigsten Signale deiner ausgewählten Kategorie auf einen Blick.")
    left, right = st.columns([4, 1])
    with left:
        total = len(result.leads)
        st.caption(f"{total} STARTUPS BEWERTET · DEUTSCHLAND · DEMO-DATEN")
        if analysis:
            st.caption(f"{analysis.discovered_count} entdeckt / {analysis.enriched_count} mit Kontext / {total} bewertet")
    saved_top = st.session_state.get("portfolio_top_n", 10)
    top_n = right.selectbox("Ranking anzeigen", [10, 20], index=[10, 20].index(saved_top),
                            format_func=lambda x: f"Top {x}", key="top_filter")
    st.session_state.portfolio_top_n = top_n
    shown = shortlist(result.leads, top_n=top_n)
    summary_kpis(shown)
    st.caption(f"Kennzahlen und Visualisierungen beziehen sich auf die angezeigten Top {len(shown)}. Mittelwerte berücksichtigen nur bekannte Scores; Skala 0–100.")

    space, stages = st.columns([2.2, 1], gap="large")
    with space:
        st.subheader("Der Potenzialraum")
        st.caption("X: Risiko · Y: Unternehmensscore · Z: Marktpotenzial")
        fig, omitted = build_figure(shown)
        st.plotly_chart(fig, width="stretch", key="startup_3d", theme=None,
                        config={"displaylogo": False, "scrollZoom": True})
        st.caption("Ziehen zum Drehen · Scrollen zum Zoomen · Hover für Details. Grün: geringeres Risiko, Rot: höheres Risiko.")
        if omitted:
            st.caption(f"{omitted} Startups ohne vollständige Achsenwerte sind nicht im 3D-Diagramm enthalten.")
    with stages:
        st.subheader("Wo stehen die Teams?")
        st.caption("Stage-Einordnung aus Schritt 3")
        st.plotly_chart(stage_figure(shown), width="stretch", theme=None, key="stage_distribution",
                        config={"displayModeBar": False})
        st.markdown("**Die stärkste Bewertung**")
        best = shown[0]
        if best.overall_score is not None:
            st.markdown(f"### {best.name}")
            st.caption(f"SCORE {best.overall_score:.1f}/100 · {best.stage_classification.upper()}")
            st.write(best.value_proposition)
            if st.button("Startup kennenlernen", key="featured_startup", width="stretch"):
                st.query_params["startup"] = best.id
                st.rerun()
        else:
            st.caption("Noch kein Gesamt-Score verfügbar.")
    st.divider()
    st.subheader("Stärken und Risiken im Direktvergleich")
    st.caption("Die zehn bestplatzierten Startups der aktuellen Auswahl. Unternehmen und Markt: höher ist besser. Risiko: niedriger ist besser.")
    st.plotly_chart(comparison_figure(shown), width="stretch", theme=None, key="score_comparison",
                    config={"displayModeBar": False})
    st.divider()
    st.subheader("Deine Investment-Shortlist")
    st.caption("Klicke auf ein Unternehmen für Produkt, Investmenthypothese, Gründerkontakt und Quellen.")
    rows = [{"Rang": i, "Unternehmen": x.name, "Standort": x.location,
             "Stage": x.stage_classification, "Score": x.overall_score,
             "Unternehmensscore": x.company_score, "Marktpotenzial": x.market_potential_score,
             "Risiko": x.risk_score} for i, x in enumerate(shown, 1)]
    signature = sha256("|".join(x.id for x in shown).encode()).hexdigest()[:12]
    table_key = f"ranking_{signature}_{st.session_state.get('table_generation', 0)}"
    config = {
        "Rang": st.column_config.NumberColumn("#", width="small", format="%d"),
        "Unternehmen": st.column_config.TextColumn("Unternehmen / Deep Dive", width="medium"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        "Unternehmensscore": st.column_config.NumberColumn("Unternehmen", format="%.0f"),
        "Marktpotenzial": st.column_config.NumberColumn("Markt", format="%.0f"),
        "Risiko": st.column_config.NumberColumn("Risiko", format="%.0f", help="Ein niedrigerer Risikoscore ist besser."),
    }
    event = st.dataframe(rows, hide_index=True, width="stretch", height=min(740, 40 + len(rows) * 44),
                        row_height=44, column_config=config, on_select="rerun", selection_mode="single-row", key=table_key)
    if open_selected_row(event, shown):
        st.rerun()
    st.caption("Ranking nach dem übergebenen Gesamt-Score. Keine neue Bewertung im Dashboard; unbekannte Scores stehen zuletzt.")
    if analysis:
        st.download_button("Analyse als JSON exportieren", analysis.model_dump_json(indent=2),
                           file_name="founder-radar-analysis.json", mime="application/json")
    st.caption("Fiktive Demo-Daten. Kontakte und Quellen verwenden example.org. Die Gewichtung ist noch keine abgestimmte Investmentmethodik.")