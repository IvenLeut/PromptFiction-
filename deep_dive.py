"""Dedicated startup page; no scoring or sourcing logic."""
from html import escape

import streamlit as st

from ui_theme import fact, heading
from charts import profile_figure
from market_view import render_company_research, render_market


def render_deep_dive(lead, back, contact_url, value):
    st.button("Zurück zur Übersicht", on_click=back, key="back_to_portfolio")
    heading("Portfolio / Startup Deep Dive", lead.name,
            f"{lead.industry.value} · {lead.location or 'Standort unbekannt'} · {lead.stage_classification}")
    st.markdown("**Produkt / Value Proposition**")
    st.write(lead.value_proposition)
    metrics = st.columns(4)
    for column, label, score in zip(metrics,
            ["Gesamt-Score", "Unternehmensscore", "Marktpotenzial", "Risiko · höher = riskanter"],
            [lead.overall_score, lead.company_score, lead.market_potential_score, lead.risk_score]):
        column.metric(label, f"{score:.1f} / 100" if score is not None else "Unbekannt")
    st.caption("Scores und Stage-Einordnung aus Schritt 3. Alle Werte: 0–100; niedrigeres Risiko ist besser.")
    main, contact = st.columns([2.2, 1], gap="large")
    with main:
        st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Investmenthypothese</div>'
                    f'<p>{escape(lead.investment_thesis)}</p></div>', unsafe_allow_html=True)
        context = lead.context_v2
        has_market = bool(context and context.market_intelligence)
        tabs = st.tabs(["Unternehmen & Kennzahlen", "Risiken & Prüfung", "Quellen & Belege"]
                       + (["Marktrecherche"] if has_market else []))
        overview, diligence, sources = tabs[:3]
        with overview:
            st.plotly_chart(profile_figure(lead), width="stretch", theme=None, key="startup_profile",
                            config={"displayModeBar": False})
            st.subheader("Unternehmensprofil")
            left, right = st.columns(2)
            year = lead.founding_year or (lead.founded_on.year if lead.founded_on else None)
            month = lead.founding_month or (lead.founded_on.month if lead.founded_on else None)
            with left:
                fact("Unternehmen", lead.name)
                fact("Branche", lead.industry.value)
                fact("Gründungsjahr", year or "Unbekannt")
                fact("Gründungsmonat", f"{month:02}" if month else "Unbekannt")
                fact("Teamgröße", value(lead.team_size))
            with right:
                fact("Produktstatus", lead.product_stage or "Unbekannt")
                fact("Stage-Einordnung", lead.stage_classification)
                if lead.earliness_delta_months is not None:
                    fact("Abstand zum ersten Datenbankeintrag oder Stichtag", f"{lead.earliness_delta_months} Monate")
                fact("Finanzierung gesamt", value(lead.funding_total_eur, " EUR"))
                fact("Finanzierungsphase", lead.funding_stage or "Unbekannt")
                fact("Kunden", value(lead.customer_count))
                fact("Jahresumsatz", value(lead.annual_revenue_eur, " EUR"))
            st.subheader("Was für das Unternehmen spricht")
            for driver in lead.score_drivers:
                st.write(f"• {driver}")
            if not lead.score_drivers:
                st.caption("Noch keine Bewertungstreiber übergeben.")
            if lead.traction_notes:
                st.write(lead.traction_notes)
            if context:
                render_company_research(context)
        with diligence:
            st.subheader("Wesentliche Risiken")
            for risk in lead.risks:
                st.warning(risk, icon="⚠️")
            if not lead.risks:
                st.caption("Keine Risiken dokumentiert. Das bedeutet nicht, dass keine bestehen.")
            st.subheader("Fragen für das erste Gespräch")
            questions = list(dict.fromkeys([*lead.open_questions, *lead.research_questions]))
            for i, question in enumerate(questions, 1):
                st.write(f"{i}. {question}")
            if not questions:
                st.caption("Noch keine offenen Fragen dokumentiert.")
        with sources:
            st.subheader("Ursprünglicher Fund")
            st.write(lead.source_name or "Quelle nicht benannt")
            st.link_button("Fundquelle ansehen", str(lead.source_url))
            evidence_items = list(lead.evidence)
            if lead.country_evidence and lead.country_evidence not in evidence_items:
                evidence_items.insert(0, lead.country_evidence)
            if has_market:
                evidence_items.extend(context.market_intelligence.sources)
            unique_evidence = {item.evidence_id: item for item in evidence_items}
            for i, evidence in enumerate(unique_evidence.values(), 1):
                with st.container(border=True):
                    st.markdown(f"**{i}. {evidence.source}**")
                    st.write(evidence.finding)
                    document = f" · Dokument vom {evidence.document_date:%d.%m.%Y}" if evidence.document_date else ""
                    st.caption(f"{evidence.field or 'Allgemein'} · Abgerufen am {evidence.retrieved_at:%d.%m.%Y}"
                               f"{document} · {evidence.verification_status} · ID {evidence.evidence_id}")
                    st.link_button("Beleg öffnen", str(evidence.url))
        if has_market:
            with tabs[3]:
                render_market(context)
    with contact:
        from dashboard import contact_email

        with st.container(border=True):
            st.subheader("Gründer kontaktieren")
            st.write(", ".join(lead.founders) or "Gründer noch unbekannt")
            fact("E-Mail", contact_email(lead) or "Noch nicht verfügbar")
            mailto = contact_url(lead)
            if mailto:
                st.link_button("Kontakt aufnehmen", mailto, type="primary", width="stretch")
                st.caption("Öffnet einen E-Mail-Entwurf. Kein automatischer Versand.")
            if lead.website:
                st.link_button("Unternehmenswebsite", str(lead.website), width="stretch")
            else:
                st.caption("Noch keine Website vorhanden.")
            fact("Entdeckt über", lead.source_name or "Unbekannt")
        st.download_button("Startup-Dossier exportieren", lead.model_dump_json(indent=2),
                           file_name=f"{lead.id}.json", mime="application/json", width="stretch")
        if lead.is_demo:
            st.caption("Fiktives Unternehmensprofil. Die Marktrecherche kennzeichnet Datenquellen und Demoannahmen.")
