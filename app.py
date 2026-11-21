"""Product flow: choose a data source (snapshot, demo, live) -> run steps 1–3 or load the snapshot -> dashboard."""
import logging
import os

import streamlit as st

from dashboard import render_dashboard
from models import Industry, SearchCriteria
from pipeline import run_pipeline
from ui_theme import apply_theme, brand, landing

SOURCES = {"snapshot": "Snapshot (echte Leads)", "demo": "Demo-Fixtures (fiktiv)", "live": "Live-Pipeline (Netz)"}

DEMO_LIMIT = 30
LIVE_LIMIT = 10  # each live lead takes ~10–15 s of network lookups

st.set_page_config(page_title="FounderRadar · Venture Intelligence", page_icon="◉", layout="wide", initial_sidebar_state="collapsed")
apply_theme()
brand()


def bump_table_generation():
    """A fresh ranking-table key clears any stale row selection."""
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


def new_analysis():
    """Back to the start page with a fresh ranking state."""
    st.session_state.pop("analysis", None)
    st.session_state.pop("analysis_meta", None)
    st.query_params.clear()
    for key in ("top_filter", "portfolio_top_n", "portfolio_industry", "portfolio_stage", "portfolio_no_db",
                "portfolio_filters", "industry_filter"):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith("cockpit_"):   # investment cockpit (cockpit.py) state of the previous run
            st.session_state.pop(key, None)
    bump_table_generation()


def sourcing_error_type() -> type[Exception] | tuple:
    """SourcingError of the live provider; an empty tuple (catches nothing) if it cannot be imported."""
    try:
        from sourcing.engine import SourcingError
    except Exception:
        logging.exception("sourcing.engine not importable")
        return ()
    return SourcingError


def start_analysis(category: Industry, live: bool):
    """Run steps 1–3 with a progress bar; store the run or show a readable error."""
    progress = st.progress(0, text="Analyse vorbereiten")
    criteria = SearchCriteria(industry=category, limit=LIVE_LIMIT if live else DEMO_LIMIT)
    try:
        completed = run_pipeline(criteria, use_mock=not live,
                                 on_progress=lambda amount, message: progress.progress(amount, text=message))
    except sourcing_error_type() as exc:
        logging.exception("Live sourcing failed")
        st.error("Der Förderkatalog konnte gerade nicht abgefragt werden. Bitte später erneut versuchen "
                 "oder die Demo-Daten nutzen.")
        st.caption(str(exc))
    except (NotImplementedError, ValueError) as exc:   # e.g. an unreadable FOUNDERRADAR_SCREENING_REPORT
        st.error(str(exc))
    except Exception:
        logging.exception("Analysis failed")
        st.error("Die Analyse konnte nicht abgeschlossen werden. Bitte erneut versuchen.")
    else:
        st.session_state.analysis = completed
        st.session_state.analysis_meta = None
        st.query_params.clear()
        bump_table_generation()
        st.rerun()


def open_snapshot(keep_query: bool = False):
    """Load the frozen real run (demo_snapshot/); no network, well under a second.

    With ``keep_query`` a deep link (``?startup=<id>``) survives, so links into the snapshot can be shared.
    """
    from demo_snapshot import load_snapshot
    try:
        completed, meta = load_snapshot()
    except Exception:
        logging.exception("Snapshot not loadable")
        st.error("Der Snapshot konnte nicht geladen werden. Neu bauen mit "
                 "`python -m demo_snapshot.build_snapshot` oder Demo-Fixtures wählen.")
        return
    st.session_state.analysis = completed
    st.session_state.analysis_meta = meta
    if not keep_query:
        st.query_params.clear()
    bump_table_generation()
    st.rerun()


run = st.session_state.get("analysis")
if run is None and (st.query_params.get("view") == "snapshot" or st.query_params.get("iven")
                    or (st.query_params.get("startup", "").startswith("foekat-")
                        and st.session_state.get("data_source", "snapshot") == "snapshot")):
    # Shareable demo links: ?view=snapshot opens the snapshot, ?startup=foekat-… a snapshot deep dive.
    st.query_params.pop("view", None)
    open_snapshot(keep_query=True)
if run is None:
    if st.query_params.get("startup"):
        st.caption("Bitte starte eine Analyse, um die Startup-Details dieser Sitzung zu öffnen.")
    # Widget state is dropped while the dashboard is shown, so the choice is also kept under "data_source".
    # FOUNDERRADAR_MODE=live (cockpit branch) preselects the live source; the default stays the snapshot.
    default_source = "live" if os.getenv("FOUNDERRADAR_MODE", "").strip().lower() == "live" else "snapshot"
    saved = st.session_state.get("data_source", default_source)
    landing(st.session_state.get("data_source_radio", saved))
    source = st.radio("Datenquelle", list(SOURCES), index=list(SOURCES).index(saved), format_func=SOURCES.get,
                      horizontal=True, key="data_source_radio",
                      help="Snapshot: eingefrorener echter Lauf (52 Leads, ohne Netz). Demo: fiktive Daten. "
                           "Live: echte Förderprojekte mit Netzwerkabfragen.")
    st.session_state.data_source = source
    with st.form("category_request", border=False):
        if source == "snapshot":
            st.markdown("#### 52 echte Gründungsvorhaben aus dem Förderkatalog")
            st.caption("Alle Branchen · Deutschland · Stand 21.11.2026 · Filter nach Branche, Stage und DB-Profil im Dashboard")
            st.caption("Zusätzlich im Dashboard: „Firmen-Radar“ mit 34 bereits gegründeten jungen Firmen "
                       "(höheres Risiko, eigenes Regelwerk, getrenntes Ranking).")
            category = None
        else:
            st.markdown("#### Welches Technologiefeld möchtest du entdecken?")
            category = st.radio("Kategorie", list(Industry), format_func=lambda x: x.value,
                                horizontal=True, label_visibility="collapsed")
            if source == "live":
                st.caption(f"Deutschland · bis zu {LIVE_LIMIT} Förderkatalog-Leads pro Kategorie · "
                           "Dauer ca. 10–15 Sekunden pro Lead")
            else:
                st.caption("Deutschland · 30 Demo-Startups pro Kategorie · Top 10 oder 20 im Ergebnis")
        start = st.form_submit_button("Analyse starten", type="primary", width="stretch")
    if start:
        if source == "snapshot":
            open_snapshot()
        else:
            start_analysis(category, source == "live")
    st.stop()

meta = st.session_state.get("analysis_meta")
snapshot = bool(meta and meta.get("kind") == "snapshot")
meta_col, action = st.columns([5, 1])
mode = "SNAPSHOT · ECHTE LEADS" if snapshot else "LIVE-ANALYSE" if run.mode == "live" else "DEMO-ANALYSE"
category = "ALLE BRANCHEN" if snapshot else run.criteria.industry.value.upper()
meta_col.caption(f"{category}  /  DEUTSCHLAND  /  {mode}")
action.button("Neue Analyse", on_click=new_analysis, width="stretch")
render_dashboard(run.result, analysis=run, meta=meta)
