"""Product flow: choose category -> run steps 1–3 -> inspect the dashboard."""
import logging

import streamlit as st

from dashboard import render_dashboard
from models import Industry, SearchCriteria
from pipeline import run_pipeline
from ui_theme import apply_theme, brand, landing

st.set_page_config(page_title="FounderRadar · Venture Intelligence", page_icon="◉", layout="wide", initial_sidebar_state="collapsed")
apply_theme()
brand()


def new_analysis():
    st.session_state.pop("analysis", None)
    st.query_params.clear()
    for key in ("top_filter", "portfolio_top_n", "portfolio_filters", "industry_filter"):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith("cockpit_"):
            st.session_state.pop(key, None)
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


run = st.session_state.get("analysis")
if run is None:
    if st.query_params.get("startup"):
        st.caption("Bitte starte eine Analyse, um die Startup-Details dieser Sitzung zu öffnen.")
    landing()
    with st.form("category_request", border=False):
        st.markdown("#### Welches Technologiefeld möchtest du entdecken?")
        category = st.radio("Kategorie", list(Industry), format_func=lambda x: x.value,
                            horizontal=True, label_visibility="collapsed")
        st.caption("Deutschland · 30 Demo-Startups pro Kategorie · Top 10 oder 20 im Ergebnis")
        start = st.form_submit_button("Analyse starten", type="primary", width="stretch")
    if start:
        progress = st.progress(0, text="Analyse vorbereiten")
        try:
            completed = run_pipeline(SearchCriteria(industry=category, limit=30),
                on_progress=lambda amount, message: progress.progress(amount, text=message))
        except Exception:
            logging.exception("Analysis failed")
            st.error("Die Analyse konnte nicht abgeschlossen werden. Bitte erneut versuchen.")
        else:
            st.session_state.analysis = completed
            st.query_params.clear()
            st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1
            st.rerun()
    st.stop()

meta, action = st.columns([5, 1])
meta.caption(f"{run.criteria.industry.value.upper()}  /  DEUTSCHLAND  /  DEMO-ANALYSE")
action.button("Neue Analyse", on_click=new_analysis, width="stretch")
render_dashboard(run.result, analysis=run)
