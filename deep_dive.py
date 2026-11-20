"""Company Deep Dive: sourced facts, model judgments and human decisions."""
from datetime import date, datetime
from html import escape
import re

import streamlit as st

from analyst_store import DECISIONS, save_decision
from scorecard import render_scorecard
from screening import screening_status, source_label
from ui_theme import fact, heading


def source_card(evidence, label="Originalquelle öffnen"):
    st.write(evidence.finding)
    st.caption(f"Quelle: {evidence.source} · Veröffentlicht: {evidence.published_on or 'Unknown'} · Abgerufen: {evidence.retrieved_at:%d.%m.%Y}")
    st.link_button(label, str(evidence.url))


def all_evidence(lead):
    items = list(lead.evidence) + list(lead.traction_evidence)
    if lead.country_evidence:
        items.append(lead.country_evidence)
    for founder in lead.founder_profiles:
        items.extend(founder.evidence)
    for event in lead.funding_events:
        items.extend(event.evidence)
    unique = {}
    for item in items:
        unique[(str(item.url), item.finding, item.published_on)] = item
    return list(unique.values())


def age_label(lead):
    if lead.founded_on:
        delta = date.today().year - lead.founded_on.year
        return f"Gründung {lead.founded_on.isoformat()} · ca. {delta} Jahre"
    if lead.founding_year:
        return f"Gründung {lead.founding_year}" + (f"-{lead.founding_month:02}" if lead.founding_month else " · Monat Unknown")
    return "Unternehmensalter: Unknown"


def arguments(items, legacy, empty):
    if items:
        for argument in items[:3]:
            st.markdown(f"**{argument.statement}**")
            st.write(argument.rationale)
            if not argument.evidence:
                st.caption("KI-Einschätzung · Beleg fehlt, vor Kontakt prüfen.")
            for evidence in argument.evidence:
                source_card(evidence, "Argument belegen")
    elif legacy:
        for text in legacy[:3]:
            st.write(f"• {text}")
        st.caption("Übergebene KI-Einschätzungen; individuelle Belegzuordnung fehlt.")
    else:
        st.caption(empty)


def render_deep_dive(lead, back, contact_url, value, *, namespace="demo", decision=None):
    st.button("Zurück zur Übersicht", on_click=back, key="back_to_portfolio")
    heading("Company Deep Dive / Investment Briefing", lead.name,
            f"{lead.industry.value} · {lead.location or 'Unknown'} · {lead.stage_classification} · {age_label(lead)}")
    st.write(lead.value_proposition)
    st.markdown(f"**Fund-Fit-Status: {screening_status(lead)}**")
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        st.error("Harter Ausschluss: " + ("; ".join(lead.hard_exclusions) or "Ausschluss laut Evaluation; Begründung fehlt."))
    if decision:
        st.caption(f"Analyst Decision: {decision['decision']} · Gespeichert: {decision['updated_at']}")
    links = st.columns([1, 1, 2])
    if lead.website:
        links[0].link_button("Website", str(lead.website), width="stretch")
    if contact_url(lead):
        links[1].link_button("Kontakt aufnehmen", contact_url(lead), width="stretch")
    links[2].caption("E-Mail-Entwurf im Mailprogramm; kein automatischer Versand.")
    if lead.is_demo:
        st.caption("DEMO · Fiktives Profil. Quellen und Kontakte sind Platzhalter, keine verifizierten Aussagen.")

    why = lead.why_contact_now
    # Display at most two sentences, including for older/unvalidated provider payloads.
    if why:
        why = ' '.join(re.split(r'(?<=[.!?])\s+', why.strip())[:2])
    st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Why Contact Now? / KI-Einschätzung</div>'
                f'<p>{escape(why or "Unknown – noch keine belegte Begründung für eine zeitnahe Kontaktaufnahme vorhanden.")}</p></div>', unsafe_allow_html=True)
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        st.caption("Eine Kontaktthese hebt harte Ausschlusskriterien nicht auf.")
    render_scorecard(lead)

    st.divider()
    st.subheader("Investment Hypothesis")
    st.caption("KI-Schlussfolgerung aus der Evaluation; keine belegte Tatsache.")
    st.write(lead.investment_thesis or "Unknown")
    strengths, risks = st.columns(2, gap="large")
    with strengths:
        st.markdown("#### Key Strengths")
        arguments(lead.key_strengths, lead.score_drivers, "Positive Investmentargumente: Unknown")
    with risks:
        st.markdown("#### Key Risks / Red Flags")
        arguments(lead.key_risks, lead.risks, "Keine Risiken dokumentiert; kein Nachweis von Risikofreiheit.")

    st.divider()
    st.subheader("Founding Team")
    st.caption("Quellenfakten aus Schritt 2. Nicht belegte Rollen und Kompetenzen bleiben Unknown.")
    if not lead.founder_profiles:
        st.write("Gründer: " + (", ".join(lead.founders) or "Unknown"))
        st.caption("Rollen, beruflicher Hintergrund, Kompetenzen und Founder-Market-Fit: Unknown")
    for founder in lead.founder_profiles:
        with st.container(border=True):
            st.markdown(f"**{founder.name}** · {founder.role or 'Rolle Unknown'}")
            fact("Beruflicher Hintergrund", founder.background or "Unknown")
            fact("Relevante Erfahrung", founder.relevant_experience or "Unknown")
            fact("Kompetenzen", founder.distinctive_skills or "Unknown")
            if not founder.evidence:
                st.caption("Noch keine Originalbelege für diese Angaben zugeordnet.")
            for evidence in founder.evidence:
                source_card(evidence, "Team-Quelle")
    fact("Founder-Market-Fit · KI-Einschätzung", lead.team_rationale or lead.score_rationales.get("team_score") or "Unknown")

    st.divider()
    st.subheader("Business & Market")
    st.caption("Strukturierter Recherchekontext; Quellenbelege sind in Discovery Intelligence verlinkt.")
    left, right = st.columns(2)
    with left:
        for label, item in [("Problem", lead.problem_statement), ("Lösung / Produkt", lead.product_mechanics),
                            ("Zielkunden", lead.target_customers), ("Geschäftsmodell", lead.business_model)]:
            fact(label, item or "Unknown")
    with right:
        for label, item in [("Zielmarkt", lead.target_market), ("Wettbewerber", ", ".join(lead.competitors)),
                            ("Differenzierung", lead.differentiation), ("Technologie / IP", lead.technology_advantage)]:
            fact(label, item or "Unknown")
    if not lead.evidence:
        st.caption("Beleglage: Unknown. Kontextangaben vor weitergehender Prüfung verifizieren.")

    st.divider()
    st.subheader("Traction & Funding")
    st.caption("Funding Unknown bedeutet nicht ungefundet. Fehlende Umsätze sind kein Umsatz von null.")
    a, b, c = st.columns(3)
    with a:
        fact("Produktreife", lead.product_maturity if lead.product_maturity != "Unknown" else lead.product_stage or "Unknown")
        fact("Funding-Status", lead.funding_status)
    with b:
        fact("Finanzierung gesamt", value(lead.funding_total_eur, " EUR"))
        fact("Kundenanzahl", value(lead.customer_count))
    with c:
        fact("Jahresumsatz", value(lead.annual_revenue_eur, " EUR"))
        fact("Teamgröße", value(lead.team_size))
    st.write(lead.traction_notes or "Traktion: Unknown")
    if not lead.traction_evidence:
        st.caption("Belegte Kunden / Piloten / Partnerschaften: Unknown")
    for evidence in lead.traction_evidence:
        source_card(evidence, "Traktionsquelle")
    if not lead.funding_events:
        st.caption("Bekannte Finanzierungen und Investoren: Unknown")
    for event in lead.funding_events:
        st.write(f"{event.announced_on or 'Datum Unknown'} · {value(event.amount_eur, ' EUR')} · {', '.join(event.investors) or 'Investoren Unknown'}")
        for evidence in event.evidence:
            source_card(evidence, "Finanzierungsquelle")

    st.divider()
    st.subheader("Discovery Intelligence")
    a, b, c = st.columns(3)
    with a:
        fact("Entdeckungsquelle", source_label(lead))
    with b:
        fact("Frühestes öffentliches Signal", lead.first_signal_date or "Unknown")
    with c:
        fact("Erfasst am", lead.discovered_at.isoformat() if lead.discovered_at else "Unknown")
    st.write(lead.initial_signal or "Ursprüngliches Signal: Unknown")
    st.link_button("Originalfund öffnen", str(lead.source_url))
    evidence_items = all_evidence(lead)
    dated = sorted([x for x in evidence_items if x.published_on], key=lambda x: x.published_on)
    undated = [x for x in evidence_items if x.published_on is None]
    st.markdown("**Chronologische Signal-Timeline**")
    if not dated:
        st.caption("Keine zusätzlichen Signale mit Veröffentlichungsdatum vorhanden.")
    for evidence in dated:
        with st.container(border=True):
            st.caption(str(evidence.published_on))
            source_card(evidence)
    if undated:
        with st.expander(f"Weitere Quellen ohne Veröffentlichungsdatum ({len(undated)})"):
            for evidence in undated:
                source_card(evidence)
    st.caption("Abrufdaten ersetzen keine Veröffentlichungsdaten. Ein frühes Signal allein belegt keine fehlende Finanzierung.")

    st.divider()
    st.subheader("Open Questions")
    if not lead.open_questions:
        st.caption("Unknown – noch keine entscheidungsrelevanten Fragen übergeben.")
    for i, question in enumerate(lead.open_questions, 1):
        st.write(f"{i}. {question}")

    st.divider()
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
    st.download_button("Startup-Dossier exportieren", lead.model_dump_json(indent=2),
                       file_name=f"{lead.id}.json", mime="application/json")
