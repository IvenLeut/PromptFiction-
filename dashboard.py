"""Step 4: presentation only; scores are supplied by step 3."""
import re
from hashlib import sha256
from urllib.parse import quote

import plotly.graph_objects as go
import streamlit as st

from charts import comparison_figure, stage_figure
from models import AnalysisRun, EvaluatedLead, ResearchResult
from pipeline import industry_unclassified, lead_priority, ranking_key
from ui_theme import (
    FONT, GRID, INK, MUTED, ORANGE, PANEL, RISK_HIGH, RISK_LOW, SCORE_MAX, TABLE_MAX_HEIGHT, TABLE_ROW_HEIGHT,
    TOP_N_OPTIONS, WHITE, ZERO_LINE, heading, md_escape, summary_kpis,
)

ALL_INDUSTRIES = "Alle Branchen"
UNCLASSIFIED = "nicht klassifiziert"
_SOURCE_SUFFIX = re.compile(r"\s*\(Quelle:\s*(https?://[^\s)]+)\)\s*$")


def shortlist(leads: list[EvaluatedLead], industry: str = ALL_INDUSTRIES, top_n: int = 10) -> list[EvaluatedLead]:
    """Best ``top_n`` leads by score; ties are broken by the step-1 priority (``ranking_key``)."""
    candidates = [lead for lead in leads if industry == ALL_INDUSTRIES or lead.industry.value == industry]
    return sorted(candidates, key=ranking_key)[:top_n]


def industry_label(lead: EvaluatedLead) -> str:
    """Industry as shown in every view; "nicht klassifiziert" for programme defaults."""
    return UNCLASSIFIED if industry_unclassified(lead) else lead.industry.value


def priority_line(lead: EvaluatedLead) -> str | None:
    """"Priorität 90 – EXIST-Forschungstransfer; …" from the step-1 reason, or None."""
    reason = (lead.prioritization_reason or "").strip()
    if not reason:
        return None
    priority = lead_priority(lead)
    if not priority or ":" not in reason:
        return reason
    return f"Priorität {priority} – {reason.split(':', 1)[1].strip()}"


def source_link_markdown(text: str) -> str:
    """Sourced text as literal Markdown; a trailing "(Quelle: URL)" becomes a link."""
    match = _SOURCE_SUFFIX.search(text)
    if not match:
        return md_escape(text)
    return f"{md_escape(text[:match.start()])} ([Quelle]({match[1]}))"


def contact_url(lead: EvaluatedLead) -> str | None:
    """Mailto draft to the founders; None without an e-mail address."""
    if not lead.contact_email:
        return None
    subject = quote(f"Austausch zu {lead.name}", safe="")
    body = quote(f"Hallo,\n\nwir sind auf {lead.name} aufmerksam geworden und würden gerne mehr "
                 "über euer Unternehmen erfahren. Habt ihr Zeit für einen kurzen Austausch?\n\nViele Grüße", safe="")
    return f"mailto:{quote(lead.contact_email, safe='@')}?subject={subject}&body={body}"


def build_figure(leads: list[EvaluatedLead], selected_id: str | None = None) -> tuple[go.Figure, int]:
    """3D map of risk, company score and market potential; returns the figure and the number of omitted leads."""
    complete = [lead for lead in leads if all(score is not None for score in
                (lead.risk_score, lead.company_score, lead.market_potential_score))]
    fig = go.Figure(go.Scatter3d(
        x=[lead.risk_score for lead in complete], y=[lead.company_score for lead in complete],
        z=[lead.market_potential_score for lead in complete], mode="markers",
        text=[lead.name for lead in complete], customdata=[lead.id for lead in complete],
        marker=dict(size=[11 if lead.id == selected_id else 8 for lead in complete],
                    color=[lead.risk_score for lead in complete],
                    colorscale=[[0, RISK_LOW], [.5, ORANGE], [1, RISK_HIGH]],
                    cmin=0, cmax=SCORE_MAX, opacity=.95, line=dict(color=WHITE, width=1),
                    colorbar=dict(title="Risiko", thickness=12, len=.65, outlinewidth=0,
                                  tickvals=[0, 50, 100], ticktext=["0 · gering", "50", "100 · hoch"])),
        hovertemplate="<b>%{text}</b><br>Risiko: %{x}/100<br>Unternehmen: %{y}/100<br>Marktpotenzial: %{z}/100<extra></extra>",
    ))
    axis = dict(range=[0, SCORE_MAX], tickvals=[0, 25, 50, 75, 100],
                gridcolor=GRID, backgroundcolor=PANEL, showbackground=True,
                zerolinecolor=ZERO_LINE, color=MUTED)
    fig.update_layout(height=590, margin=dict(l=0, r=30, t=0, b=0),
        paper_bgcolor=WHITE, font=dict(family=FONT, color=INK, size=13),
        hoverlabel=dict(bgcolor=INK, font_color=WHITE, bordercolor=INK),
        scene=dict(xaxis=dict(**axis, title="Risiko"),
                   yaxis=dict(**axis, title="Unternehmensscore"),
                   zaxis=dict(**axis, title="Marktpotenzial"),
                   aspectmode="cube", camera=dict(eye=dict(x=1.6, y=1.6, z=1.1))),
        uirevision="startup-map")
    return fig, len(leads) - len(complete)


def back_to_overview():
    """Leave the deep dive."""
    st.query_params.pop("startup", None)
    # A fresh table key clears the selection and prevents immediate re-entry.
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


def open_selected_row(event, shown: list[EvaluatedLead]) -> bool:
    """Open the deep dive of the selected table row; True if a row was selected."""
    rows = event.selection.rows
    if rows and 0 <= rows[0] < len(shown):
        st.query_params["startup"] = shown[rows[0]].id
        return True
    return False


def render_issues(result: ResearchResult):
    """Per-lead problems of the run, collapsed."""
    if result.issues:
        with st.expander(f"Hinweise zum Suchlauf ({len(result.issues)})"):
            for issue in result.issues:
                st.warning(md_escape(f"{issue.lead_id}: {issue.message}"))


def render_dashboard(result: ResearchResult, analysis: AnalysisRun | None = None):
    """Overview or, with ``?startup=<id>``, the deep dive of one lead."""
    # deep_dive imports helpers from this module, so it is imported here, not at module level.
    from deep_dive import render_deep_dive

    render_issues(result)
    if not result.leads:
        st.info("Für diese Kategorie liegen noch keine bewerteten Startups vor. Starte eine neue Analyse.")
        return
    requested_id = st.query_params.get("startup")
    if requested_id:
        lead = next((x for x in result.leads if x.id == requested_id), None)
        if lead is not None:
            render_deep_dive(lead, back_to_overview)
            return
        st.warning("Dieses Startup ist im aktuellen Suchlauf nicht vorhanden.")
        st.button("Zurück zur Übersicht", on_click=back_to_overview)
        return
    live = bool(analysis and analysis.mode == "live")
    shown = _render_header(result, analysis, live)
    _render_space_and_stages(shown)
    st.divider()
    st.subheader("Stärken und Risiken im Direktvergleich")
    st.caption("Die zehn bestplatzierten Startups der aktuellen Auswahl. Unternehmen und Markt: höher ist besser. Risiko: niedriger ist besser.")
    st.plotly_chart(comparison_figure(shown), width="stretch", theme=None, key="score_comparison",
                    config={"displayModeBar": False})
    st.divider()
    _render_ranking(shown)
    if analysis:
        st.download_button("Analyse als JSON exportieren", analysis.model_dump_json(indent=2),
                           file_name="founder-radar-analysis.json", mime="application/json")
    if live:
        st.caption("Echtdaten aus dem Förderkatalog des Bundes und öffentlichen Quellen. "
                   "Die Gewichtung ist noch keine abgestimmte Investmentmethodik.")
    else:
        st.caption("Fiktive Demo-Daten. Kontakte und Quellen verwenden example.org. Die Gewichtung ist noch keine abgestimmte Investmentmethodik.")


def _render_header(result: ResearchResult, analysis: AnalysisRun | None, live: bool) -> list[EvaluatedLead]:
    """Heading, counters, Top-N selector and KPI cards; returns the shown leads."""
    category = analysis.criteria.industry.value if analysis else "Tech-Startups"
    heading("Dein Investment-Radar", f"{category}. Potenzial im Blick.",
            "Unternehmensstärke, Marktchance und Risiko. Die wichtigsten Signale deiner ausgewählten Kategorie auf einen Blick.")
    left, right = st.columns([4, 1])
    with left:
        total = len(result.leads)
        source = "FÖRDERKATALOG-DATEN" if live else "DEMO-DATEN"
        st.caption(f"{total} STARTUPS BEWERTET · DEUTSCHLAND · {source}")
        if analysis:
            st.caption(f"{analysis.discovered_count} entdeckt / {analysis.enriched_count} mit Kontext / {total} bewertet")
    saved_top = st.session_state.get("portfolio_top_n", TOP_N_OPTIONS[0])
    top_n = right.selectbox("Ranking anzeigen", TOP_N_OPTIONS, index=TOP_N_OPTIONS.index(saved_top),
                            format_func=lambda x: f"Top {x}", key="top_filter")
    st.session_state.portfolio_top_n = top_n
    shown = shortlist(result.leads, top_n=top_n)
    summary_kpis(shown)
    st.caption(f"Kennzahlen und Visualisierungen beziehen sich auf die angezeigten Top {len(shown)}. Mittelwerte berücksichtigen nur bekannte Scores; Skala 0–100.")
    return shown


def _render_space_and_stages(shown: list[EvaluatedLead]):
    """3D map, stage donut and the best-rated lead."""
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
            st.markdown(f"### {md_escape(best.name)}")
            st.caption(f"SCORE {best.overall_score:.1f}/100 · {best.stage_classification.upper()}")
            st.write(md_escape(best.value_proposition))
            if st.button("Startup kennenlernen", key="featured_startup", width="stretch"):
                st.query_params["startup"] = best.id
                st.rerun()
        else:
            st.caption("Noch kein Gesamt-Score verfügbar.")


def _render_ranking(shown: list[EvaluatedLead]):
    """Selectable ranking table; a click opens the deep dive."""
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
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=SCORE_MAX, format="%.1f"),
        "Unternehmensscore": st.column_config.NumberColumn("Unternehmen", format="%.0f"),
        "Marktpotenzial": st.column_config.NumberColumn("Markt", format="%.0f"),
        "Risiko": st.column_config.NumberColumn("Risiko", format="%.0f", help="Ein niedrigerer Risikoscore ist besser."),
    }
    event = st.dataframe(rows, hide_index=True, width="stretch",
                         height=min(TABLE_MAX_HEIGHT, 40 + len(rows) * TABLE_ROW_HEIGHT),
                         row_height=TABLE_ROW_HEIGHT, column_config=config, on_select="rerun",
                         selection_mode="single-row", key=table_key)
    if open_selected_row(event, shown):
        st.rerun()
    st.caption("Ranking nach dem übergebenen Gesamt-Score, bei Gleichstand nach der Priorität aus Schritt 1. "
               "Keine neue Bewertung im Dashboard; unbekannte Scores stehen zuletzt.")
