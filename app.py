"""UI only: processing lives in pipeline.py."""
import json
import streamlit as st
from models import Industry, SearchCriteria
from pipeline import collect_context, discover, evaluate_context

st.set_page_config(page_title="FounderRadar", page_icon="🔎", layout="wide")
st.title("FounderRadar")
st.caption("Startups entdecken · Kontext sammeln · bewerten · im Dashboard visualisieren")
st.info("Demo-Modus: Alle Startups, Quellen und Scores sind fiktiv. Echte Such- und Scraping-Anbieter sind noch nicht angebunden.")
with st.sidebar:
    st.header("Suchauftrag")
    with st.form("search"):
        industry = st.selectbox("Branche", list(Industry), format_func=lambda x: x.value)
        st.text_input("Land", "Deutschland", disabled=True)
        limit = st.number_input("Maximale Treffer", min_value=1, max_value=200, value=30)
        submitted = st.form_submit_button("1 · Startups finden")
    st.caption("Schritt 1 prüft Branche und Deutschland-Bezug aus der Fundquelle. Early-Stage-Eignung wird erst anhand des Kontexts bewertet.")
if submitted:
    criteria = SearchCriteria(industry=industry, limit=limit)
    st.session_state.raw = discover(criteria)
    st.session_state.criteria = criteria
    st.session_state.pop("context", None)
    st.session_state.pop("evaluation", None)
raw = st.session_state.get("raw")
if raw is None:
    st.write("Wähle eine Branche und starte die Suche in der Seitenleiste.")
    st.stop()
st.caption(f"Aktiver Suchlauf: {st.session_state.criteria.industry.value} · Deutschland")
st.subheader("1 · Longlist")
st.metric("Gefundene Startups", len(raw))
if not raw:
    st.warning("Keine passenden Startups gefunden.")
    st.stop()
st.dataframe([{"Name": x.name, "Branche": x.industry.value, "Standort": x.location,
               "Beschreibung": x.description, "Fundquelle": str(x.source_url)} for x in raw], hide_index=True)
st.subheader("2 · Kontext sammeln")
st.write("Team, Produkt, Gründung, Finanzierung und Traktion mit Quellenbelegen.")
if st.button("Kontext erfassen"):
    with st.spinner("Kontext wird gesammelt …"):
        st.session_state.context = collect_context(raw)
        st.session_state.pop("evaluation", None)
context = st.session_state.get("context")
if context is not None:
    for issue in context.issues:
        st.warning(f"{issue.lead_id}: {issue.message}")
    st.dataframe([{"Name": x.name, "Gründer": ", ".join(x.founders), "Gründung": x.founded_on,
                   "Teamgröße": x.team_size, "Finanzierung EUR": x.funding_total_eur,
                   "Phase": x.funding_stage, "Produktstatus": x.product_stage,
                   "Kunden": x.customer_count, "Jahresumsatz EUR": x.annual_revenue_eur}
                  for x in context.leads], hide_index=True)
    st.caption("Leere Felder sind unbekannt. Demo-Daten enthalten bewusst Lücken.")
st.subheader("3 · Bewertung und Ranking")
if st.button("Bewerten und sortieren", disabled=context is None or not context.leads):
    st.session_state.evaluation = evaluate_context(context.leads)
evaluation = st.session_state.get("evaluation")
st.subheader("4 · Ergebnis-Dashboard")
if evaluation is None:
    st.caption("Nach Schritt 3 erscheinen hier Ranking, Scores, Details und Quellen.")
if evaluation is not None:
    for issue in evaluation.issues:
        st.warning(f"{issue.lead_id}: {issue.message}")
    st.dataframe([{"Startup": x.name, "Qualität": x.quality_score, "Earliness": x.earliness_score,
                   "Konfidenz": x.confidence_score} for x in evaluation.leads], hide_index=True)
    for lead in evaluation.leads:
        with st.expander(lead.name):
            st.write(lead.investment_thesis)
            for evidence in lead.evidence:
                st.write(f"{evidence.source}: {evidence.finding}")
                st.link_button("Quelle öffnen", str(evidence.url))
            for risk in lead.risks:
                st.warning(risk)
payload = {"schema_version": "1.0", "mode": "demo",
           "criteria": st.session_state.criteria.model_dump(mode="json"),
           "raw_leads": [x.model_dump(mode="json") for x in raw],
           "context": context.model_dump(mode="json") if context is not None else None,
           "evaluation": evaluation.model_dump(mode="json") if evaluation is not None else None}
st.download_button("Suchlauf als JSON exportieren", json.dumps(payload, ensure_ascii=False, indent=2),
                   file_name="founder-radar-demo.json", mime="application/json")
