"""Consistent score definitions, with missing reasons surfaced explicitly."""
import streamlit as st

SCORES = [
    ("Overall Quality", "overall_score", "Gesamtattraktivität laut Evaluation; harte Ausschlüsse gelten unabhängig davon."),
    ("Fund Fit", "fund_fit_score", "Passung zu Branche, Standort, Alter und Finanzierungsphase des Fonds."),
    ("Earliness", "earliness_score", "Frühe Entdeckung anhand Gründung, Produktreife, Finanzierung und öffentlicher Signale."),
    ("Team", "team_score", "Nachgewiesene Kompetenzen und Founder-Market-Fit."),
    ("Market Potential", "market_potential_score", "Attraktivität und Potenzial des adressierten Markts."),
    ("Technology / Advantage", "technology_score", "Technologische Differenzierung, IP und Verteidigbarkeit."),
    ("Confidence", "confidence_score", "Verlässlichkeit und Vollständigkeit der Daten; keine Aussage zur Startup-Qualität."),
]


def rationale(lead, field):
    dedicated = {"fund_fit_score": lead.fund_fit_rationale, "team_score": lead.team_rationale,
                 "earliness_score": lead.earliness_rationale}
    return lead.score_rationales.get(field) or dedicated.get(field)


def render_scorecard(lead):
    st.subheader("Investment Scorecard")
    st.caption("KI-Einschätzungen aus Schritt 3 · 0–100, höher ist besser. Confidence misst Datenqualität. Unknown wird nicht als 0 gewertet.")
    columns = st.columns(3)
    for column, (label, field, definition) in zip(columns, SCORES[:3]):
        with column:
            score = getattr(lead, field)
            st.metric(label, "Unknown" if score is None else f"{score:.0f}/100", help=definition)
            st.caption(rationale(lead, field) or ("Bewertungsgrundlage fehlt – prüfen." if score is not None else "Noch nicht bewertet."))
    with st.container(border=True):
        columns = st.columns(2)
        for i, (label, field, definition) in enumerate(SCORES[3:]):
            with columns[i % 2]:
                score = getattr(lead, field)
                st.markdown(f"**{label} · {'Unknown' if score is None else f'{score:.0f}/100'}**")
                if score is not None:
                    st.progress(score / 100)
                st.caption(definition)
                st.caption(rationale(lead, field) or ("Begründung fehlt – prüfen." if score is not None else "Bewertung: Unknown"))
