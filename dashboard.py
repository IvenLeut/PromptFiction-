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
    TOP_N_OPTIONS, UNKNOWN, WHITE, ZERO_LINE, chips, format_date, heading, kpi_cards, md_escape, summary_kpis,
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


def contact_email(lead: EvaluatedLead) -> str | None:
    """Step-1 contact address, else the company mailbox from the imprint if an evidence entry quotes it verbatim
    (Leonard, 032f20d). Redacted personal addresses ("[E-Mail entfernt]", demo_snapshot) never match."""
    if lead.contact_email:
        return lead.contact_email
    address = lead.imprint_email or ""
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_{}|~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", address):
        return None
    pattern = rf"(?<![\w.%+-]){re.escape(address)}(?![\w@-]|\.[\w-])"
    if any(item.field == "contact_email" and item.verification_status != "assumption"
           and re.search(pattern, item.finding, re.I) for item in lead.evidence):
        return address
    return None


def contact_url(lead: EvaluatedLead) -> str | None:
    """Mailto draft to the founders; None without an e-mail address."""
    address = contact_email(lead)
    if not address:
        return None
    subject = quote(f"Austausch zu {lead.name}", safe="")
    body = quote(f"Hallo,\n\nwir sind auf {lead.name} aufmerksam geworden und würden gerne mehr "
                 "über euer Unternehmen erfahren. Habt ihr Zeit für einen kurzen Austausch?\n\nViele Grüße", safe="")
    return f"mailto:{quote(address, safe='@')}?subject={subject}&body={body}"


# --- Earliness and team helpers (shared with deep_dive.py) ---------------------------------------------

LINKEDIN_SEARCH = "https://www.linkedin.com/search/results/people/?keywords="


def _namekey(name: str) -> str:
    return re.sub(r"[^0-9a-zäöüß]", "", (name or "").lower())


def _is_linkedin_profile(url) -> bool:
    """Public profile URL linkedin.com/in/<slug> (any country subdomain); company pages and posts are not."""
    match = re.match(r"https://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/in/[^/?#\s]+/?$", str(url or ""), re.I)
    return bool(match)


def linkedin_profile(lead: EvaluatedLead, name: str) -> str | None:
    """Public LinkedIn profile of one person as found by context/team.py, else None.

    Read from the founder profile's source URL or from the step-2 evidence (field "founder_profiles",
    finding "<Name>: …", URL linkedin.com/in/…). Nothing is guessed; only a URL found in step 2 is returned."""
    key = _namekey(name)
    for profile in lead.founder_profiles:
        if _namekey(profile.name) == key and _is_linkedin_profile(profile.source_url):
            return str(profile.source_url)
    for item in lead.evidence:
        if (item.field == "founder_profiles" and _is_linkedin_profile(item.url)
                and _namekey(item.finding.split(":", 1)[0]) == key):
            return str(item.url)
    return None


def linkedin_search(name: str, company: str) -> str:
    """LinkedIn people search for "<Name> <Firma>"; only a link, nothing is sent."""
    return LINKEDIN_SEARCH + quote(f"{name} {company}", safe="")


def linkedin_link(lead: EvaluatedLead, name: str) -> tuple[str, str, bool]:
    """(label, url, is_profile): "LinkedIn" with the found profile, else "Auf LinkedIn suchen"."""
    profile = linkedin_profile(lead, name)
    return ("LinkedIn", profile, True) if profile else ("Auf LinkedIn suchen", linkedin_search(name, lead.name), False)


# --- Investment hypothesis as readable parts (text of scoring/engine.py, nothing added) ---------------------

_THESIS_LABELS = {"Wir investieren, weil:": "Warum investieren", "Belegt:": "Belegte Stärken",
                  "Nächster Meilenstein:": "Nächster Meilenstein", "Hauptrisiko:": "Hauptrisiko",
                  "Kein Investment-Case:": "Kein Investment-Case"}
_THESIS_SPLIT = re.compile(r"\s*(?=Wir investieren, weil:|Belegt:|Nächster Meilenstein:|Hauptrisiko:|Kein Investment-Case:|"
                           r"Wenn bis Förderende|Kein Risikofaktor ab|Noch keine Stärke belegt)")
_PROXY = re.compile(r"\s*\(Proxy\)")
PROXY_HINT = ("Proxy: indirekter Hinweis (z. B. Fachgebiet der ausführenden Stelle oder Publikationen ohne Feldbezug), "
              "im Scoring gedämpft gewichtet. Vor dem Kontakt prüfen.")


def thesis_parts(text: str) -> list[tuple[str | None, list[tuple[str, bool]]]]:
    """Split the scoring hypothesis into (label, [(statement, is_proxy)]) without changing its content.

    "Wir investieren, weil: A (Proxy); B. Hauptrisiko: C (Proxy)." ->
    [("Warum investieren", [("A", True), ("B", False)]), ("Hauptrisiko", [("C", True)])]."""
    parts = []
    for segment in _THESIS_SPLIT.split((text or "").strip()):
        segment = segment.strip()
        if not segment:
            continue
        prefix = next((p for p in _THESIS_LABELS if segment.startswith(p)), None)
        body = segment[len(prefix):].strip() if prefix else segment
        listed = prefix in ("Wir investieren, weil:", "Belegt:")
        items = [x for x in (re.split(r";\s+(?=[A-ZÄÖÜ])", body.rstrip(".")) if listed else [body]) if x.strip()]
        parts.append((_THESIS_LABELS.get(prefix), [(_PROXY.sub("", item).strip(), bool(_PROXY.search(item))) for item in items]))
    return parts


def plain_thesis(text: str | None) -> str | None:
    """Hypothesis as one plain line for compact views: "(Proxy)" chains are folded into one trailing note."""
    if not text:
        return text
    stripped = _PROXY.sub("", text)
    return stripped + (" · Enthält Proxy-Hinweise (indirekt, vor Kontakt prüfen)." if stripped != text else "")


def thesis_html(text: str) -> str:
    """HTML rows for the thesis box; "(Proxy)" becomes a small badge with an explanatory tooltip."""
    badge = f' <span class="fr-proxy" title="{escape(PROXY_HINT, quote=True)}">Proxy</span>'
    rows = []
    for label, items in thesis_parts(text):
        content = "".join(f"<li>{escape(item)}{badge if proxy else ''}</li>" for item, proxy in items)
        content = f"<ul>{content}</ul>" if len(items) > 1 else f"<p>{content[4:-5]}</p>"
        rows.append(f'<div class="fr-thesis-row"><span>{escape(label)}</span>{content}</div>' if label
                    else f'<div class="fr-thesis-row fr-thesis-lead">{content}</div>')
    return "".join(rows)


_GERMAN_DAY = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def documented_founding(lead: EvaluatedLead, meta: dict | None = None) -> dict | None:
    """Founding date with its source, or None. Only documented dates: the step-2 `founded_on`/`founding_year`
    (+ month) or, in snapshot mode, the dated "gegründet" row of the hand-checked best-find timeline
    (AGENT_TEAM/eval/best_find.md, with source URL). A press-text year hint is not a founding date."""
    if lead.founded_on:
        return {"text": format_date(lead.founded_on), "year": lead.founded_on.year, "month": lead.founded_on.month,
                "url": None, "source": "Kontext (Schritt 2)"}
    if lead.founding_year:
        month = lead.founding_month
        return {"text": f"{month:02}/{lead.founding_year}" if month else str(lead.founding_year),
                "year": lead.founding_year, "month": month, "url": None, "source": "Sourcing (Schritt 1)"}
    best = (meta or {}).get("best_find") or {}
    if best.get("lead_id") == lead.id:
        for row in best.get("timeline") or []:
            found = _GERMAN_DAY.search(row.get("when") or "")
            if found and row.get("source") and re.search(r"(?i)gegründet|gründung", row.get("signal") or ""):
                day = date(int(found[3]), int(found[2]), int(found[1]))
                return {"text": format_date(day), "year": day.year, "month": day.month, "url": row["source"],
                        "source": "Handrecherche Best Find (Pressemitteilung)"}
    return None


def review_flags(lead: EvaluatedLead, meta: dict | None) -> list[dict]:
    """Hand-checked hints of the snapshot (demo_snapshot/review_flags.json), e.g. a possible angel investment."""
    return ((meta or {}).get("review_flags") or {}).get(lead.id) or []


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


def decision_namespace(result: ResearchResult, analysis: AnalysisRun | None) -> str:
    """analyst_store namespace: demo decisions never mix with live/snapshot ones (same rule as cockpit_data)."""
    return "demo" if (analysis and analysis.mode == "demo") or all(x.is_demo for x in result.leads) else "live"


def render_dashboard(result: ResearchResult, analysis: AnalysisRun | None = None, meta: dict | None = None):
    """Overview or, with ``?startup=<id>``, the deep dive of one lead.

    The overview has three views: "Radar" (scores, earliness, best find, ranking; the default), "Screening"
    (fund fit, analyst status and filters from the cockpit branch) and "Investment-Cockpit" (cockpit.py:
    overview, dealflow, company brief, activities). All three read the same run; decisions are shared."""
    # deep_dive imports helpers from this module, so it is imported here, not at module level.
    from deep_dive import render_deep_dive

    render_issues(result)
    if not result.leads:
        st.info("Für diese Kategorie liegen noch keine bewerteten Startups vor. Starte eine neue Analyse.")
        return
    namespace = decision_namespace(result, analysis)
    requested_id = st.query_params.get("startup")
    if requested_id:
        lead = next((x for x in result.leads if x.id == requested_id), None)
        if lead is not None:
            render_deep_dive(lead, back_to_overview, meta=meta, as_of=as_of_date(analysis, meta),
                             namespace=namespace, decision=_load_decisions(namespace).get(lead.id))
            return
        st.warning("Dieses Startup ist im aktuellen Suchlauf nicht vorhanden.")
        st.button("Zurück zur Übersicht", on_click=back_to_overview)
        return
    view = st.segmented_control("Ansicht", VIEWS, key="dashboard_view", label_visibility="collapsed",
                                default=_saved("portfolio_view", VIEWS, VIEWS[0])) or VIEWS[0]
    st.session_state.portfolio_view = view
    if view == VIEWS[1]:
        _render_screening(result, analysis, meta, namespace)
        return
    if view == VIEWS[2]:
        if analysis is None:
            st.info("Das Investment-Cockpit braucht einen vollständigen Analyselauf.")
            return
        from cockpit import render_workspace
        render_workspace(analysis)
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


VIEWS = ["Radar", "Screening & Entscheidungen", "Investment-Cockpit"]


def _load_decisions(namespace: str) -> dict:
    """Analyst decisions (analyst_store); {} with a warning if the local database is not readable."""
    from analyst_store import load_decisions
    try:
        return load_decisions(namespace)
    except Exception:
        st.warning("Analystenentscheidungen konnten nicht geladen werden. Datenbankzugriff prüfen (FOUNDERRADAR_DB).")
        return {}


def _render_screening(result: ResearchResult, analysis: AnalysisRun | None, meta: dict | None, namespace: str):
    """Screening longlist of the cockpit branch (Iven/Leonard): fund fit, analyst status, search and filters.

    High priority is a presentation threshold (screening.high_priority), not a new score."""
    from screening import filter_leads, high_priority, review_status

    decisions = _load_decisions(namespace)
    heading("Screening / Entscheidungen", "Früh entdecken. Klar entscheiden.",
            "Priorisierte Longlist für die erste Kontaktentscheidung. Quellenfakten, Einschätzungen aus dem Scoring "
            "und Analystenentscheidungen bleiben unterscheidbar.")
    kpi_cards([("Leads gesamt", str(len(result.leads)), "im Analyselauf", None),
               ("Hohe Priorität", str(sum(high_priority(x, decisions) for x in result.leads)), "Schwellen siehe unten", None),
               ("Offen zur Prüfung", str(sum(review_status(x, decisions) == "Pending Review" for x in result.leads)),
                "ohne Analystenentscheidung", None),
               ("Kontakt-Kandidaten", str(sum(review_status(x, decisions) == "Contact" for x in result.leads)),
                "Entscheidung „Contact“", None)], dark_first=True)
    st.caption("Hohe Priorität: bestätigter Fund Fit, Quality ≥ 75, Fit ≥ 70, Earliness ≥ 70; kein Ausschluss/Reject. "
               "Kontakt-Kandidaten: ausdrückliche Analystenentscheidung „Contact“ (im Deep Dive).")
    search = st.text_input("Unternehmen oder Branche suchen", placeholder="Name oder Technologiefeld eingeben …",
                           key="cockpit_search")
    with st.expander("Filter und Priorisierung"):
        a, b, c = st.columns(3)
        locations = a.multiselect("Standort", sorted({x.location or UNKNOWN for x in result.leads}), key="cockpit_locations")
        industries = b.multiselect("Branche", sorted({x.industry.value for x in result.leads}), key="cockpit_industries")
        stages = c.multiselect("Stage", sorted({x.stage_classification for x in result.leads}), key="cockpit_stages")
        d, e = st.columns(2)
        fit = d.selectbox("Fund Fit", ["Alle", "Passend", "Ungeklärt", "Ausgeschlossen"], key="cockpit_fit")
        statuses = e.multiselect("Screening-Status", ["Pending Review", "Contact", "Watchlist", "Reject", "Excluded"],
                                 key="cockpit_statuses")
    left, right = st.columns([3, 1])
    order = left.selectbox("Sortieren nach", ["Priorität", "Quality Score", "Fund Fit", "Earliness", "Entdeckungsdatum"],
                           key="cockpit_sort")
    top_n = right.selectbox("Anzeigen", [0, 10, 20], key="cockpit_top",
                            format_func=lambda x: "Alle Startups" if x == 0 else f"Top {x}")
    filtered = filter_leads(result.leads, decisions, search=search, locations=locations, industries=industries,
                            stages=stages, fit=fit, statuses=statuses, sort_by=order)
    shown = filtered[:top_n] if top_n else filtered
    st.caption(f"{len(shown)} angezeigt / {len(filtered)} passend / {len(result.leads)} insgesamt. Ausschlüsse bleiben "
               "sichtbar und werden bei Standardpriorisierung zurückgestellt.")
    if not shown:
        st.info("Keine Unternehmen entsprechen den gewählten Filtern.")
        return
    rows = [{"Unternehmen": x.name, "Value Proposition": x.value_proposition, "Branche": industry_label(x),
             "Standort": x.location or UNKNOWN, "Stage": stage_label(x, meta),
             "Fund Fit": "Ausgeschlossen" if x.hard_exclusions or x.eligibility_status == "Excluded" else
                         (f"{x.fund_fit_score:.0f}/100" if x.fund_fit_score is not None else UNKNOWN),
             "Quality Score": x.overall_score, "Earliness Score": x.earliness_score,
             "Screening-Status": review_status(x, decisions),
             "Priorität": "Hoch" if high_priority(x, decisions) else "—"} for x in shown]
    signature = sha256("|".join(x.id for x in shown).encode()).hexdigest()[:12]
    config = {
        "Unternehmen": st.column_config.TextColumn("Unternehmen / Deep Dive", width="medium"),
        "Value Proposition": st.column_config.TextColumn("Value Proposition", width="medium"),
        "Quality Score": st.column_config.ProgressColumn("Quality", min_value=0, max_value=SCORE_MAX, format="%.0f"),
        "Earliness Score": st.column_config.ProgressColumn("Earliness", min_value=0, max_value=SCORE_MAX, format="%.0f"),
    }
    event = st.dataframe(rows, hide_index=True, width="stretch", height=min(TABLE_MAX_HEIGHT, 40 + len(rows) * TABLE_ROW_HEIGHT),
                         row_height=TABLE_ROW_HEIGHT, column_config=config, on_select="rerun", selection_mode="single-row",
                         key=f"screening_{signature}_{st.session_state.get('table_generation', 0)}")
    if open_selected_row(event, shown):
        st.rerun()
    st.caption("Zeile anklicken für den Deep Dive mit Analystenentscheidung. Quality ist der Gesamt-Score aus Schritt 3; "
               "Unbekannt beim Fund Fit heißt: Eignung noch nicht geprüft.")


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
                        "Vorsprung": lead_time_months(x, meta, as_of),
                        "Prüfhinweis": "; ".join(f["flag"] for f in review_flags(x, meta)) or None})
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
