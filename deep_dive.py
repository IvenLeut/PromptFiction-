"""Dedicated startup page; no scoring or sourcing logic."""
from collections.abc import Callable
from html import escape

import streamlit as st

from analyst_store import DECISIONS, load_decisions, save_decision

from charts import profile_figure
from dashboard import contact_url, industry_label, priority_line, source_link_markdown
from market_view import render_company_research, render_market
from models import EvaluatedLead
from ui_theme import (
    QUESTION_PREVIEW, UNKNOWN, fact, format_date, format_number, format_score, heading, md_escape,
)


def _questions(lead: EvaluatedLead) -> list[str]:
    """Open questions of steps 3 and 2, without duplicates."""
    return list(dict.fromkeys([*lead.open_questions, *lead.research_questions]))


def sourced_signals(lead: EvaluatedLead) -> list[tuple[str, str, str | None]]:
    """(label, value, url or None) rows of what step 2 documented for a live lead; demo leads have none.

    Live leads are mostly pre-founding projects: the company profile is "Unbekannt" almost everywhere,
    while grants, the database check and the first dated signal are filled. This block shows those.
    """
    if lead.is_demo:
        return []
    rows = []
    for grant in lead.grants:
        term = " – ".join(format_date(day) if day else "?" for day in (grant.start, grant.end))
        parts = [grant.programme,
                 format_number(grant.amount_eur, " EUR") if grant.amount_eur is not None else "Summe unbekannt",
                 f"Laufzeit {term}" if grant.start or grant.end else "Laufzeit unbekannt"]
        if grant.reference:
            parts.append(f"FKZ {grant.reference}")
        rows.append(("Öffentliche Förderung", " · ".join(parts), str(grant.url)))
    if lead.in_databases is True:
        since = f", erstmals {format_date(lead.first_db_date)}" if lead.first_db_date else ""
        rows.append(("Startup-Datenbanken", f"Profil gefunden{since}",
                     str(lead.database_urls[0]) if lead.database_urls else None))
    elif lead.in_databases is False:
        rows.append(("Startup-Datenbanken", "Kein Profil in Crunchbase/Dealroom gefunden", None))
    else:
        rows.append(("Startup-Datenbanken", "Nicht geprüft", None))
    rows.append(("Erstes datiertes Signal",
                 format_date(lead.first_signal_date) if lead.first_signal_date else UNKNOWN, None))
    rows.append(("Offene Fragen", str(len(_questions(lead))), None))
    return rows


def render_deep_dive(lead: EvaluatedLead, back: Callable[[], None]):
    """Profile, diligence, sources and contact of one lead."""
    st.button("Zurück zur Übersicht", on_click=back, key="back_to_portfolio")
    heading("Portfolio / Startup Deep Dive", lead.name,
            f"{industry_label(lead)} · {lead.location or 'Standort unbekannt'} · {lead.stage_classification}")
    if priority := priority_line(lead):
        st.caption(md_escape(priority))
    st.markdown("**Produkt / Value Proposition**")
    st.write(md_escape(lead.value_proposition))
    metrics = st.columns(4)
    for column, label, score in zip(metrics,
            ["Gesamt-Score", "Unternehmensscore", "Marktpotenzial", "Risiko · höher = riskanter"],
            [lead.overall_score, lead.company_score, lead.market_potential_score, lead.risk_score]):
        column.metric(label, UNKNOWN if score is None else f"{format_score(score)} / 100")
    st.caption("Scores und Stage-Einordnung aus Schritt 3. Alle Werte: 0–100; niedrigeres Risiko ist besser.")
    main, contact = st.columns([2.2, 1], gap="large")
    with main:
        st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Investmenthypothese</div>'
                    f'<p>{escape(lead.investment_thesis)}</p></div>', unsafe_allow_html=True)
        context = lead.context_v2
        has_market = bool(context and context.market_intelligence)
        tabs = st.tabs(["Unternehmen & Kennzahlen", "Risiken & Prüfung", "Quellen & Belege"]
                       + (["Marktrecherche"] if has_market else []))
        with tabs[0]:
            _render_overview(lead)
        with tabs[1]:
            _render_diligence(lead)
        with tabs[2]:
            _render_sources(lead, has_market)
        if has_market:
            with tabs[3]:
                render_market(context)
    with contact:
        _render_contact(lead)
    _render_decision(lead)


def _render_overview(lead: EvaluatedLead):
    """Score profile, company facts and score drivers."""
    st.plotly_chart(profile_figure(lead), width="stretch", theme=None, key="startup_profile",
                    config={"displayModeBar": False})
    signals = sourced_signals(lead)
    if signals:
        st.subheader("Belegte Signale")
        for label, value, url in signals:
            fact(label, value)
            if url:
                st.markdown(f"[Quelle öffnen]({url})")
    st.subheader("Unternehmensprofil")
    left, right = st.columns(2)
    year = lead.founding_year or (lead.founded_on.year if lead.founded_on else None)
    month = lead.founding_month or (lead.founded_on.month if lead.founded_on else None)
    with left:
        fact("Unternehmen", lead.name)
        fact("Branche", industry_label(lead))
        fact("Gründungsjahr", year or UNKNOWN)
        fact("Gründungsmonat", f"{month:02}" if month else UNKNOWN)
        fact("Teamgröße", format_number(lead.team_size))
    with right:
        fact("Produktstatus", lead.product_stage or UNKNOWN)
        fact("Stage-Einordnung", lead.stage_classification)
        fact("Finanzierung gesamt", format_number(lead.funding_total_eur, " EUR"))
        fact("Finanzierungsphase", lead.funding_stage or UNKNOWN)
        fact("Kunden", format_number(lead.customer_count))
        fact("Jahresumsatz", format_number(lead.annual_revenue_eur, " EUR"))
    st.subheader("Was für das Unternehmen spricht")
    for driver in lead.score_drivers:
        st.markdown(f"• {source_link_markdown(driver)}")
    if not lead.score_drivers:
        st.caption("Noch keine Bewertungstreiber übergeben.")
    if lead.traction_notes:
        st.write(md_escape(lead.traction_notes))
    if lead.context_v2:
        render_company_research(lead.context_v2)


def _render_diligence(lead: EvaluatedLead):
    """Risks and questions for the first call; long question lists are collapsed."""
    st.subheader("Wesentliche Risiken")
    for risk in lead.risks:
        st.warning(source_link_markdown(risk), icon="⚠️")
    if not lead.risks:
        st.caption("Keine Risiken dokumentiert. Das bedeutet nicht, dass keine bestehen.")
    st.subheader("Fragen für das erste Gespräch")
    questions = _questions(lead)
    for i, question in enumerate(questions[:QUESTION_PREVIEW], 1):
        st.write(f"{i}. {md_escape(question)}")
    if len(questions) > QUESTION_PREVIEW:
        with st.expander(f"{len(questions) - QUESTION_PREVIEW} weitere Fragen"):
            for i, question in enumerate(questions[QUESTION_PREVIEW:], QUESTION_PREVIEW + 1):
                st.write(f"{i}. {md_escape(question)}")
    if not questions:
        st.caption("Noch keine offenen Fragen dokumentiert.")


def _render_sources(lead: EvaluatedLead, has_market: bool):
    """Original find and all evidence, deduplicated by evidence id."""
    st.subheader("Ursprünglicher Fund")
    st.write(md_escape(lead.source_name or "Quelle nicht benannt"))
    st.link_button("Fundquelle ansehen", str(lead.source_url))
    evidence_items = list(lead.evidence)
    if lead.country_evidence and lead.country_evidence not in evidence_items:
        evidence_items.insert(0, lead.country_evidence)
    if has_market:
        evidence_items.extend(lead.context_v2.market_intelligence.sources)
    unique_evidence = {item.evidence_id: item for item in evidence_items}
    for i, evidence in enumerate(unique_evidence.values(), 1):
        with st.container(border=True):
            st.markdown(f"**{i}. {md_escape(evidence.source)}**")
            st.write(md_escape(evidence.finding))
            document = f" · Dokument vom {format_date(evidence.document_date)}" if evidence.document_date else ""
            st.caption(md_escape(f"{evidence.field or 'Allgemein'} · Abgerufen am {format_date(evidence.retrieved_at)}"
                                 f"{document} · {evidence.verification_status} · ID {evidence.evidence_id}"))
            st.link_button("Beleg öffnen", str(evidence.url))


def _render_contact(lead: EvaluatedLead):
    """Founder contact, website and dossier export."""
    with st.container(border=True):
        st.subheader("Gründer kontaktieren")
        st.write(md_escape(", ".join(lead.founders) or "Gründer noch unbekannt"))
        fact("E-Mail", lead.contact_email or "Noch nicht verfügbar")
        mailto = contact_url(lead)
        if mailto:
            st.link_button("Kontakt aufnehmen", mailto, type="primary", width="stretch")
            st.caption("Öffnet einen E-Mail-Entwurf. Kein automatischer Versand.")
        if lead.website:
            st.link_button("Unternehmenswebsite", str(lead.website), width="stretch")
        else:
            st.caption("Noch keine Website vorhanden.")
        fact("Entdeckt über", lead.source_name or UNKNOWN)
    st.download_button("Startup-Dossier exportieren", lead.model_dump_json(indent=2),
                       file_name=f"{lead.id}.json", mime="application/json", width="stretch")
    if lead.is_demo:
        st.caption("Fiktives Unternehmensprofil. Die Marktrecherche kennzeichnet Datenquellen und Demoannahmen.")


def _render_decision(lead):
    namespace = "demo" if lead.is_demo else "live"
    decision = load_decisions(namespace).get(lead.id)
    st.subheader("Analyst Decision")
    st.caption("Manuelle Entscheidung, lokal persistent gespeichert. Contact versendet keine E-Mail.")
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        st.warning("Harter Ausschluss bleibt in der Longlist sichtbar, auch bei abweichender Analystenentscheidung.")
    saved = decision or {}
    with st.form(f"decision_{namespace}_{lead.id}"):
        choice = st.radio("Entscheidung", list(DECISIONS), index=list(DECISIONS).index(saved["decision"]) if saved else None,
                          horizontal=True)
        notes = st.text_area("Analysten-Notizen", saved.get("notes", ""))
        reason = st.text_area("Begründung der Entscheidung", saved.get("reason", ""))
        submitted = st.form_submit_button("Entscheidung speichern", type="primary")
    if submitted:
        if choice is None:
            st.error("Bitte eine Entscheidung auswählen.")
        else:
            try:
                save_decision(namespace, lead.id, choice, notes, reason)
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("Speichern fehlgeschlagen. Bitte Datenbankzugriff prüfen.")
            else:
                st.success("Entscheidung und Notizen dauerhaft gespeichert.")
