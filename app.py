"""Product flow: choose category -> run steps 1–3 -> inspect the dashboard."""
import logging

import streamlit as st

from dashboard import render_dashboard
from models import Industry, SearchCriteria
from pipeline import run_pipeline
from ui_theme import apply_theme, brand, landing

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
    st.query_params.clear()
    for key in ("top_filter", "portfolio_top_n"):
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
        st.error("Die konfigurierte Suchquelle ist nicht verfügbar. Bitte den Discovery-Lauf prüfen.")
        st.caption(str(exc))
    except Exception:
        logging.exception("Analysis failed")
        st.error("Die Analyse konnte nicht abgeschlossen werden. Bitte erneut versuchen.")
    else:
        st.session_state.analysis = completed
        st.query_params.clear()
        bump_table_generation()
        st.rerun()


run = st.session_state.get("analysis")
if run is None:
    if st.query_params.get("startup"):
        st.caption("Bitte starte eine Analyse, um die Startup-Details dieser Sitzung zu öffnen.")
    # Widget state is dropped while the dashboard is shown, so the choice is also kept under "live_mode".
    saved_live = st.session_state.get("live_mode", False)
    landing(live=st.session_state.get("live_mode_toggle", saved_live))
    live = st.toggle("Live-Daten", value=saved_live, key="live_mode_toggle",
                     help="Aus: fiktive Demo-Daten. An: konfigurierte Suchquelle und Kontextabfragen.")
    st.session_state.live_mode = live
    with st.form("category_request", border=False):
        st.markdown("#### Welches Technologiefeld möchtest du entdecken?")
        category = st.radio("Kategorie", list(Industry), format_func=lambda x: x.value,
                            horizontal=True, label_visibility="collapsed")
        if live:
            st.caption(f"Deutschland · bis zu {LIVE_LIMIT} Kandidaten pro Kategorie · "
                       "Dauer ca. 10–15 Sekunden pro Lead")
        else:
            st.caption("Deutschland · 30 Demo-Startups pro Kategorie · Top 10 oder 20 im Ergebnis")
        start = st.form_submit_button("Analyse starten", type="primary", width="stretch")
    if start:
        start_analysis(category, live)
    st.stop()

meta, action = st.columns([5, 1])
mode = "LIVE-ANALYSE" if run.mode == "live" else "DEMO-ANALYSE"
meta.caption(f"{run.criteria.industry.value.upper()}  /  DEUTSCHLAND  /  {mode}")
action.button("Neue Analyse", on_click=new_analysis, width="stretch")
render_dashboard(run.result, analysis=run)
