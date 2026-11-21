"""Step 4: presentation only; scores are supplied by step 3.

`meta` (optional) carries what the AnalysisRun contract has no field for: in snapshot mode the per-lead
scoring record (detailed stage, why-now, noise class, months of lead time), the earliness backtest and the
best find (demo_snapshot/snapshot_meta.json). Every view also works without it.
"""
import re
import statistics
from datetime import date
from hashlib import sha256
from html import escape
from urllib.parse import quote

import plotly.graph_objects as go
import streamlit as st

from charts import backtest_figure, comparison_figure, stage_figure
from models import AnalysisRun, EvaluatedLead, ResearchResult
from pipeline import industry_unclassified, lead_priority, ranking_key
from ui_theme import (
    FONT, GRID, INK, MUTED, ORANGE, PANEL, RISK_HIGH, RISK_LOW, SCORE_MAX, TABLE_MAX_HEIGHT, TABLE_ROW_HEIGHT,
    TOP_N_OPTIONS, WHITE, ZERO_LINE, chips, format_date, heading, kpi_cards, md_escape, summary_kpis,
)

ALL_INDUSTRIES = "Alle Branchen"
ALL_STAGES = "Alle Stages"
UNCLASSIFIED = "nicht klassifiziert"
_SOURCE_SUFFIX = re.compile(r"\s*\(Quelle:\s*(https?://[^\s)]+)\)\s*$")
# Detailed stage of the scoring record (scoring/engine.py STAGES) as shown in the dashboard.
STAGE_LABELS = {"pre_gruendung": "Pre-Gründung", "in_gruendung": "In Gründung", "pre_seed": "Pre-Seed",
                "seed": "Seed", "zu_spaet": "Zu spät"}


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


# --- Earliness and team helpers (shared with deep_dive.py) ---------------------------------------------

def lead_meta(lead: EvaluatedLead, meta: dict | None) -> dict:
    """Scoring-record extras of one lead from the snapshot meta; {} without."""
    return ((meta or {}).get("leads") or {}).get(lead.id) or {}


def stage_label(lead: EvaluatedLead, meta: dict | None = None) -> str:
    """Detailed stage of the scoring record if known (e.g. "Pre-Gründung"), else the step-3 classification."""
    return STAGE_LABELS.get(lead_meta(lead, meta).get("stage"), lead.stage_classification)


def website_of(lead: EvaluatedLead) -> str | None:
    """Step-1 website or the website matched in step 2."""
    url = lead.website or lead.matched_website
    return str(url) if url else None


def founder_names(lead: EvaluatedLead) -> list[str]:
    """Founders from step 1, else the founder profiles or managing directors found in step 2."""
    names = list(lead.founders) or [p.name for p in lead.founder_profiles] or list(lead.managing_directors)
    return list(dict.fromkeys(names))


def db_checks(lead: EvaluatedLead) -> list[str]:
    """Which database checks ran for this lead: "Wayback" (archived Crunchbase/Dealroom slugs) and/or
    "Datenbanksuche" (search across Crunchbase, Dealroom, PitchBook, Tracxn)."""
    sources = {e.source for e in lead.evidence if e.field in ("in_databases", "first_db_date")}
    checks = []
    if any("Wayback" in s for s in sources):
        checks.append("Wayback")
    if any("Datenbanksuche" in s or "Brave" in s for s in sources):
        checks.append("Datenbanksuche")
    return checks


def db_status(lead: EvaluatedLead) -> tuple[str, str]:
    """(text, kind) of the database check; kind "good" = no profile found, "warn" = profile exists."""
    checks = "/".join(db_checks(lead)) or "Wayback"
    if lead.in_databases is True:
        since = f" seit {format_date(lead.first_db_date)}" if lead.first_db_date else ""
        return f"DB-Profil vorhanden{since}", "warn"
    if lead.in_databases is False:
        return f"kein DB-Profil ({checks})", "good"
    return "DB nicht geprüft", ""


def _months(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day))


def lead_time_months(lead: EvaluatedLead, meta: dict | None = None, as_of: date | None = None) -> int | None:
    """Months from the first signal to the first database entry, without an entry up to the as-of date
    (scoring `earliness_delta_monate`, scoring/SCORING.md). None if a profile exists without a date."""
    extra = lead_meta(lead, meta)
    if extra.get("earliness_delta_monate") is not None:
        return int(extra["earliness_delta_monate"])
    if not lead.first_signal_date:
        return None
    if lead.in_databases is True:
        return _months(lead.first_signal_date, lead.first_db_date) if lead.first_db_date else None
    return _months(lead.first_signal_date, as_of or date.today())


def as_of_date(analysis: AnalysisRun | None, meta: dict | None) -> date:
    """Reference date of the run: snapshot stichtag, else the run's creation date."""
    if meta and meta.get("stichtag"):
        return date.fromisoformat(meta["stichtag"])
    return analysis.created_at.date() if analysis else date.today()


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


def render_dashboard(result: ResearchResult, analysis: AnalysisRun | None = None, meta: dict | None = None):
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
            render_deep_dive(lead, back_to_overview, meta=meta, as_of=as_of_date(analysis, meta))
            return
        st.warning("Dieses Startup ist im aktuellen Suchlauf nicht vorhanden.")
        st.button("Zurück zur Übersicht", on_click=back_to_overview)
        return
    live = bool(analysis and analysis.mode == "live")
    snapshot = bool(meta and meta.get("kind") == "snapshot")
    as_of = as_of_date(analysis, meta)
    shown = _render_header(result, analysis, live, meta)
    if not shown:
        st.info("Kein Lead passt zu den Filtern. Filter zurücksetzen, um wieder alle zu sehen.")
        return
    if live:
        _render_earliness(result, shown, meta, as_of)
    if snapshot and meta.get("best_find"):
        _render_best_find(result.leads, meta, as_of)
    _render_space_and_stages(shown, meta)
    st.divider()
    st.subheader("Stärken und Risiken im Direktvergleich")
    st.caption("Die zehn bestplatzierten Startups der aktuellen Auswahl. Unternehmen und Markt: höher ist besser. Risiko: niedriger ist besser.")
    st.plotly_chart(comparison_figure(shown), width="stretch", theme=None, key="score_comparison",
                    config={"displayModeBar": False})
    st.divider()
    _render_ranking(shown, live, meta, as_of)
    if live:
        _render_noise(result, meta)
    if analysis:
        st.download_button("Analyse als JSON exportieren", analysis.model_dump_json(indent=2),
                           file_name="founder-radar-analysis.json", mime="application/json")
    if snapshot:
        st.caption(f"Eingefrorener echter Lauf vom {format_date(as_of)} (Förderkatalog des Bundes, Website, Impressum, "
                   "OpenAlex, idw, Wayback, Datenbanksuche). Läuft ohne Netz. Die Gewichtung ist noch keine "
                   "abgestimmte Investmentmethodik; Handprüfung vor jedem Kontakt.")
    elif live:
        st.caption("Echtdaten aus dem Förderkatalog des Bundes und öffentlichen Quellen. "
                   "Die Gewichtung ist noch keine abgestimmte Investmentmethodik.")
    else:
        st.caption("Fiktive Demo-Daten. Kontakte und Quellen verwenden example.org. Die Gewichtung ist noch keine abgestimmte Investmentmethodik.")


def _saved(key: str, options: list, default):
    """Value kept across the deep dive (widget state is dropped while it is shown)."""
    value = st.session_state.get(key, default)
    return value if value in options else default


def _render_header(result: ResearchResult, analysis: AnalysisRun | None, live: bool,
                   meta: dict | None) -> list[EvaluatedLead]:
    """Heading, counters, filters and KPI cards; returns the shown leads."""
    snapshot = bool(meta and meta.get("kind") == "snapshot")
    if snapshot:
        heading(f"Snapshot · echte Leads · Stand {format_date(as_of_date(analysis, meta))}",
                f"{len(result.leads)} Gründungsvorhaben. Vor allen anderen.",
                "Echte EXIST-Projekte aus dem Förderkatalog, angereichert um Website, Impressum, Forschung und "
                "Datenbank-Check. Rangfolge nach Team, Markt und Risiko; jede Angabe mit Quelle.")
    else:
        category = analysis.criteria.industry.value if analysis else "Tech-Startups"
        heading("Dein Investment-Radar", f"{category}. Potenzial im Blick.",
                "Unternehmensstärke, Marktchance und Risiko. Die wichtigsten Signale deiner ausgewählten Kategorie auf einen Blick.")
    total = len(result.leads)
    source = "SNAPSHOT EINES ECHTEN LAUFS" if snapshot else "FÖRDERKATALOG-DATEN" if live else "DEMO-DATEN"
    st.caption(f"{total} STARTUPS BEWERTET · DEUTSCHLAND · {source}")
    if analysis:
        st.caption(f"{analysis.discovered_count} entdeckt / {analysis.enriched_count} mit Kontext / {total} bewertet")

    industries = [ALL_INDUSTRIES, *sorted({industry_label(x) for x in result.leads})]
    stages = [ALL_STAGES, *sorted({stage_label(x, meta) for x in result.leads})]
    col_industry, col_stage, col_db, col_top = st.columns([1.3, 1.1, 1.1, .8])
    industry = col_industry.selectbox("Branche", industries, key="filter_industry",
                                      index=industries.index(_saved("portfolio_industry", industries, ALL_INDUSTRIES)))
    stage = col_stage.selectbox("Stage", stages, key="filter_stage",
                                index=stages.index(_saved("portfolio_stage", stages, ALL_STAGES)))
    col_db.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
    no_db = col_db.toggle("Nur ohne DB-Profil", key="filter_no_db", value=st.session_state.get("portfolio_no_db", False),
                          help="Nur Leads, für die weder Wayback noch die Datenbanksuche ein Crunchbase-/Dealroom-/"
                               "PitchBook-/Tracxn-Profil gefunden hat.")
    top_n = col_top.selectbox("Ranking anzeigen", TOP_N_OPTIONS, key="top_filter",
                              index=TOP_N_OPTIONS.index(_saved("portfolio_top_n", TOP_N_OPTIONS, TOP_N_OPTIONS[0])),
                              format_func=lambda x: f"Top {x}")
    st.session_state.update(portfolio_industry=industry, portfolio_stage=stage, portfolio_no_db=no_db,
                            portfolio_top_n=top_n)
    candidates = [x for x in result.leads
                  if (industry == ALL_INDUSTRIES or industry_label(x) == industry)
                  and (stage == ALL_STAGES or stage_label(x, meta) == stage)
                  and (not no_db or x.in_databases is False)]
    shown = shortlist(candidates, top_n=top_n)
    if not shown:
        return shown
    summary_kpis(shown)
    st.caption(f"Kennzahlen und Visualisierungen beziehen sich auf die angezeigten Top {len(shown)}"
               f"{' (gefiltert)' if len(candidates) < total else ''}. Mittelwerte berücksichtigen nur bekannte Scores; Skala 0–100.")
    return shown


def _render_earliness(result: ResearchResult, shown: list[EvaluatedLead], meta: dict | None, as_of: date):
    """Earliness band (backtest headline) and KPI cards on signals, database check and team."""
    backtest = (meta or {}).get("backtest")
    if backtest and backtest.get("headline"):
        n, early = backtest.get("n"), backtest.get("early")
        median = backtest.get("median_months")
        st.markdown(
            '<div class="fr-band"><div><div class="fr-eyebrow">Earliness-Backtest</div>'
            f'<strong>{escape(f"{early}/{n}")}</strong><p>früh erkannt</p></div>'
            f'<div><strong>{escape(f"{median:.0f}" if median is not None else "–")} Monate</strong>'
            '<p>Median-Vorsprung des Förderkatalog-Signals vor der ersten Finanzierungsmeldung oder dem ersten '
            f'Datenbankeintrag. n={escape(str(n))}, Handauswahl bekannter Ausgründungen (Selektionsbias, siehe unten).</p></div></div>',
            unsafe_allow_html=True)
    leads = result.leads
    no_profile = sum(1 for x in leads if x.in_databases is False)
    months = [m for m in (lead_time_months(x, meta, as_of) for x in shown) if m is not None]
    with_team = sum(1 for x in leads if website_of(x) and founder_names(x))
    kpi_cards([
        ("Echte Leads bewertet", str(len(leads)), "EXIST-Projekte aus dem Förderkatalog", None),
        ("Ohne DB-Profil", f"{no_profile}/{len(leads)}", "kein Profil in Crunchbase, Dealroom, PitchBook, Tracxn",
         100 * no_profile / len(leads) if leads else None),
        ("Median Vorsprung", f"{statistics.median(months):.0f} Mon." if months else "–",
         "erstes Signal bis DB-Eintrag bzw. Stichtag (angezeigte Leads)", None),
        ("Website und Team belegt", f"{with_team}/{len(leads)}", "Website gefunden und Personen namentlich belegt",
         100 * with_team / len(leads) if leads else None),
    ], dark_first=True)
    if backtest and backtest.get("companies"):
        with st.expander("Backtest im Detail: Wie früh war das Signal bei später bekannten Ausgründungen?"):
            st.plotly_chart(backtest_figure(backtest["companies"]), width="stretch", theme=None,
                            key="backtest_chart", config={"displayModeBar": False})
            st.caption(md_escape(backtest["headline"]))
            for note in backtest.get("bias", []):
                st.caption("• " + md_escape(note))
            st.caption(f"Quelle: {md_escape(backtest.get('source_file', 'AGENT_TEAM/eval/backtest.json'))}")


def _render_best_find(leads: list[EvaluatedLead], meta: dict, as_of: date):
    """Hand-checked best find with its dated signals, team and open points (AGENT_TEAM/eval/best_find.md)."""
    best = meta["best_find"]
    ranked = sorted(leads, key=ranking_key)
    lead = next((x for x in ranked if x.id == best.get("lead_id")), None)
    tags = []
    if lead is not None:
        tags = [(f"Rang {ranked.index(lead) + 1} von {len(ranked)}", ""),
                (f"Score {lead.overall_score:.1f}" if lead.overall_score is not None else "Score offen", ""),
                (stage_label(lead, meta), ""), db_status(lead)]
        months = lead_time_months(lead, meta, as_of)
        if months is not None:
            tags.append((f"{months} Monate Vorsprung", "good"))
    items = []
    for row in best.get("timeline", []):
        key = "fr-key" if "unser Signal" in row["signal"] else ""
        link = (f' <a href="{escape(row["source"], quote=True)}" target="_blank" rel="noopener">Quelle</a>'
                if row.get("source") else f' <small>{escape(row.get("source_note") or "")}</small>')
        items.append(f'<li class="{key}"><time>{escape(row["when"])}</time><span>{escape(row["signal"])}{link}</span></li>')
    st.markdown(
        f'<div class="fr-best"><div class="fr-eyebrow">Best Find · handgeprüft</div><h2>{escape(best.get("name") or "")}</h2>'
        f'<div>{chips(tags)}</div><p>{escape(best.get("intro") or "")}</p></div>', unsafe_allow_html=True)
    timeline, story = st.columns([1.5, 1], gap="large")
    with timeline:
        st.markdown("**Signal-Zeitleiste**")
        st.markdown(f'<ul class="fr-tl">{"".join(items)}</ul>', unsafe_allow_html=True)
    with story:
        if best.get("team"):
            st.markdown("**Team**")
            st.write(md_escape(best["team"]))
        if best.get("why_now"):
            st.markdown("**Warum jetzt anrufen**")
            st.write(md_escape(best["why_now"]))
        if best.get("open"):
            st.markdown("**Offen vor dem Pitch**")
            st.write(md_escape(best["open"]))
        if lead is not None and st.button("Deep Dive öffnen", key="best_find_open", type="primary", width="stretch"):
            st.query_params["startup"] = lead.id
            st.rerun()
        st.caption(f"Quelle: {md_escape(best.get('source_file', ''))} (Faktencheck des Agent-Teams). "
                   "Vor einem Pitch Handelsregister, Datenbanken und Finanzierung von Hand prüfen.")
    st.divider()


def _render_space_and_stages(shown: list[EvaluatedLead], meta: dict | None):
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
        st.caption("Stage-Einordnung aus Schritt 3" + (" (Detailstufe des Scorings)" if meta else ""))
        labels = [stage_label(x, meta) for x in shown] if meta else None
        st.plotly_chart(stage_figure(shown, labels), width="stretch", theme=None, key="stage_distribution",
                        config={"displayModeBar": False})
        st.markdown("**Die stärkste Bewertung**")
        best = shown[0]
        if best.overall_score is not None:
            st.markdown(f"### {md_escape(best.name)}")
            st.caption(f"SCORE {best.overall_score:.1f}/100 · {stage_label(best, meta).upper()}")
            st.write(md_escape(best.value_proposition))
            if st.button("Startup kennenlernen", key="featured_startup", width="stretch"):
                st.query_params["startup"] = best.id
                st.rerun()
        else:
            st.caption("Noch kein Gesamt-Score verfügbar.")


def _render_ranking(shown: list[EvaluatedLead], live: bool, meta: dict | None, as_of: date):
    """Selectable ranking table; a click opens the deep dive."""
    st.subheader("Deine Investment-Shortlist")
    st.caption("Klicke auf ein Unternehmen für Signal-Zeitleiste, Team, Investmenthypothese und Quellen.")
    rows = []
    for i, x in enumerate(shown, 1):
        row = {"Rang": i, "Unternehmen": x.name, "Branche": industry_label(x), "Stage": stage_label(x, meta),
               "Score": x.overall_score}
        if live:
            founders = founder_names(x)
            row.update({"Website": website_of(x),
                        "Gründer": ", ".join(founders[:3]) + (f" +{len(founders) - 3}" if len(founders) > 3 else "") or "–",
                        "Erstes Signal": x.first_signal_date, "DB-Check": db_status(x)[0],
                        "Vorsprung": lead_time_months(x, meta, as_of)})
        else:
            row["Standort"] = x.location
        row.update({"Unternehmensscore": x.company_score, "Marktpotenzial": x.market_potential_score,
                    "Risiko": x.risk_score})
        rows.append(row)
    signature = sha256("|".join(x.id for x in shown).encode()).hexdigest()[:12]
    table_key = f"ranking_{signature}_{st.session_state.get('table_generation', 0)}"
    config = {
        "Rang": st.column_config.NumberColumn("#", width="small", format="%d"),
        "Unternehmen": st.column_config.TextColumn("Unternehmen / Deep Dive", width="medium"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=SCORE_MAX, format="%.1f"),
        "Website": st.column_config.LinkColumn("Website", display_text=r"https?://(?:www\.)?([^/]+)"),
        "Erstes Signal": st.column_config.DateColumn("Erstes Signal", format="MM/YYYY"),
        "Vorsprung": st.column_config.NumberColumn("Vorsprung", format="%d Mon.",
                                                   help="Monate vom ersten Signal bis zum ersten Datenbankeintrag, ohne Eintrag bis zum Stichtag."),
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


def _render_noise(result: ResearchResult, meta: dict | None):
    """What the noise filter and the funding check removed or flagged."""
    st.subheader("Noise und Abgelehnt")
    counts = ((meta or {}).get("noise") or {}).get("counts") or {}
    noise = {k: v for k, v in counts.items() if k != "vc_potenzial"}
    late = [x for x in result.leads if x.overall_score is None or x.stage_classification == "Early Growth"]
    rejected = ((meta or {}).get("best_find") or {}).get("rejected") or []
    parts = []
    if counts:
        parts.append(f"Noise-Filter (Agentur/Beratung): {sum(noise.values())} von {sum(counts.values())} Leads markiert")
    parts.append(f"{len(result.issues)} vor dem Scoring zurückgehalten")
    parts.append(f"{len(late)} als zu spät oder ohne Score eingestuft")
    if rejected:
        parts.append(f"{len(rejected)} bei der Handprüfung gestrichen")
    st.caption(" · ".join(parts))
    for item in rejected:
        link = f" ([Quelle]({item['source']}))" if item.get("source") else ""
        st.warning(f"**Gestrichen: {md_escape(item['name'])}** (FKZ {md_escape(item['fkz'])}). "
                   f"{md_escape(item['reason'])}{link}", icon="✋")
    for lead in late:
        reason = next(iter(lead.risks), "Kein Gesamt-Score")
        st.warning(f"**{md_escape(lead.name)}**: {source_link_markdown(reason)}", icon="⏱")
    if counts and not noise:
        st.caption("In diesem Lauf hat die Heuristik keinen Agentur- oder Beratungs-Treffer markiert: Die 52 Leads sind "
                   "nach Förderpriorität vorsortierte EXIST-Projekte. Geprüft wird jeder Lead (scoring/engine.py, noise_class).")
