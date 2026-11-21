"""FounderRadar company detail, market evidence and outreach actions."""
from datetime import date
from email import policy
from email.message import EmailMessage
from html import escape
import json
import os

import plotly.graph_objects as go
import streamlit as st

from analyst_store import OUTREACH, load_history, save_decision
from mvp.briefs import (
    CHECKED, DEFAULT_MODEL, brief_for, editorial_input, generate_draft,
    http_url, mailto, report_html, saved_draft,
)

OUTREACH_LABELS = dict(zip(OUTREACH, (
    "Noch nicht kontaktiert", "Entwurf vorbereitet", "Kontaktiert", "Antwort erhalten", "Gespräch vereinbart"
)))


def callout(title, message):
    st.markdown(
        f'<section class="fr-brief"><div class="fr-kicker">{escape(title)}</div>'
        f'<p>{escape(message)}</p></section>',
        unsafe_allow_html=True,
    )


def score_chart(item):
    ordered = list(reversed(item.criteria))
    labels = [criterion.label for criterion in ordered]
    contribution = [round((criterion.points or 0) * criterion.weight / 100, 1) for criterion in ordered]
    unknown = [criterion.weight if criterion.points is None else 0 for criterion in ordered]
    unearned = [round(criterion.weight - actual - opened, 1)
                for criterion, actual, opened in zip(ordered, contribution, unknown)]
    figure = go.Figure()
    for name, values, color in (
        ("Belegte Punkte", contribution, "#17624d"),
        ("Offen", unknown, "#a6d4bf"),
        ("Übriges Gewicht", unearned, "#e9eeec"),
    ):
        figure.add_bar(name=name, x=values, y=labels, orientation="h", marker_color=color,
                       hovertemplate="%{y} · %{x:.1f} Punkte<extra>" + name + "</extra>")
    figure.update_layout(
        barmode="stack", height=235, margin=dict(l=5, r=10, t=12, b=32),
        legend=dict(orientation="h", y=-.27, font=dict(size=11)),
        xaxis=dict(title="Punkte im Gesamtscore", range=[0, max([1] + [c.weight for c in ordered]) + 1]),
        yaxis=dict(automargin=True),
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def overview_tab(item, brief, run):
    st.subheader("Kurzbeschreibung")
    st.write(brief.summary)
    if brief.sources:
        label, url = brief.sources[0]
        if http_url(url):
            st.link_button(label, url)
    st.subheader("Investmenthypothese")
    st.write(brief.thesis)
    st.subheader("Was im Erstgespräch geklärt werden muss")
    st.write(brief.question)
    st.caption(brief.gate)
    with st.expander("Gründung, Finanzierungsphase und Prüfstatus"):
        dossier = item.dossier
        st.write(f"Finanzierungsphase · {item.stage}")
        if dossier.earliest_founding:
            interval = str(dossier.earliest_founding)
            if dossier.latest_founding and dossier.latest_founding != dossier.earliest_founding:
                interval += f" bis {dossier.latest_founding}"
            st.write(f"Gründung · {interval}")
        st.caption(dossier.founding_basis or "Gründungsnachweis offen")
        if dossier.project_ids:
            st.write("Projektzuordnung · " + ", ".join(dossier.project_ids))
        for reason in dict.fromkeys(item.reasons):
            st.write("• " + reason)
    st.download_button(
        "FounderRadar Deep Dive herunterladen",
        report_html(item, brief, run.options.as_of),
        file_name=f"FounderRadar-{item.dossier.id}-Deep-Dive.html",
        mime="text/html",
    )


def market_tab(item, brief):
    st.subheader("Einstiegsmarkt")
    st.write(brief.segment)
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("**Wer entscheidet und bezahlt?**")
        st.write(brief.buyer)
    with right, st.container(border=True):
        st.markdown("**Woran der erste Kunde den Nutzen misst**")
        st.write(brief.adoption)
    st.subheader("Wettbewerb und Alternativen")
    for name, comparison, url in brief.alternatives:
        with st.container(border=True):
            st.markdown(f"**{name}**")
            st.write(comparison)
            if http_url(url):
                st.link_button("Vergleichsquelle öffnen", url)
    st.subheader("Marktgröße von unten schätzen")
    st.write(brief.sizing)
    with st.expander("Eigenes Umsatzszenario rechnen"):
        st.caption("Setze deine Annahmen für erreichbare Kunden und jährlichen Nettoerlös ein. Die Werte gelten für dieses Szenario.")
        left, right = st.columns(2)
        segments = left.number_input("Erreichbare zahlende Kunden", min_value=0, step=1,
                                     max_value=10_000_000, key=f"customers-{item.dossier.id}")
        revenue = right.number_input("Nettoerlös je Kunde und Jahr (€)", min_value=0, step=500,
                                     max_value=100_000_000, key=f"revenue-{item.dossier.id}")
        if segments and revenue:
            expected = f"{segments * revenue:,}".replace(",", ".")
            st.metric("Jahreserlös im Szenario", f"{expected} €")
    name, description, url = brief.signal
    with st.container(border=True):
        st.markdown("**Öffentliches Signal · " + name + "**")
        st.write(description)
        if http_url(url):
            st.link_button("Signal prüfen", url)
    with st.expander("Redaktion mit OpenAI"):
        key = st.session_state.get("fr_openai_key") or os.environ.get("OPENAI_API_KEY", "")
        model = st.session_state.get("fr_openai_model") or os.environ.get("FOUNDERRADAR_OPENAI_MODEL", DEFAULT_MODEL)
        st.caption("Der Entwurf nutzt öffentliche Belege. Modelleinstellungen findest du unter Daten & Einrichtung.")
        if st.button("KI-Entwurf aus Belegen erstellen", disabled=not key, key=f"gen-{item.dossier.id}"):
            try:
                with st.spinner("OpenAI erstellt den Entwurf …"):
                    generate_draft(item, brief, key, model)
            except (ValueError, OSError) as error:
                st.error(str(error))
        draft = saved_draft(item, brief, model)
        if draft:
            sources = json.loads(editorial_input(item, brief))["sources"]
            st.caption(f"KI-Entwurf · {model} · Aussagen vor Übernahme mit den Quellen abgleichen")
            for label, section in (
                ("Unternehmen", draft.company), ("Markt", draft.market),
                ("Investmenthypothese", draft.hypothesis), ("Erstgespräch", draft.first_call),
            ):
                st.markdown(f"**{label}**")
                st.text(section.text)
                for reference in dict.fromkeys(section.evidence_ids):
                    source = sources[reference]
                    st.link_button(f"{reference} · {source['title']}", source["url"])


def evidence_tab(item, brief):
    st.subheader("Wie sich der Score zusammensetzt")
    score_chart(item)
    if item.score is not None:
        st.caption(f"{item.score:.1f} belegte Punkte · Obergrenze bei offenen Dimensionen {item.score_upper:.1f}")
    for criterion in item.criteria:
        label = f"{criterion.label} · " + (f"{criterion.points}/100" if criterion.points is not None else "Offen")
        with st.expander(label):
            st.write(criterion.reason)
            for name in criterion.facts:
                fact = item.dossier.facts[name]
                st.caption(fact.quote)
                if http_url(fact.source_url):
                    st.link_button("Beleg öffnen", fact.source_url)
    st.subheader("Quellen")
    rows = [{"Quelle": label, "URL": url, "Herkunft": "Deep Dive", "Abruf": CHECKED}
            for label, url in brief.sources if http_url(url) and brief.editorial]
    rows.extend({"Quelle": s.title, "URL": s.url, "Herkunft": s.kind, "Abruf": s.retrieved_at}
                for s in item.dossier.sources if http_url(s.url))
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch", column_config={"URL": st.column_config.LinkColumn()})
    st.download_button("Score und Belege als JSON", item.model_dump_json(indent=2),
                       file_name=f"{item.dossier.id}.json", mime="application/json")


def draft_email(item, brief, saved):
    identity = item.dossier.id
    with st.container(border=True):
        st.subheader("Erstkontakt vorbereiten")
        address, source = brief.email or ("", None)
        recipient = st.text_input("Empfänger", value=address, max_chars=200, key=f"mail-to-{identity}")
        if http_url(source):
            st.link_button("Quelle der Geschäftsadresse", source)
        elif not address:
            st.caption("Öffentliche Geschäftsadresse noch offen. Adresse ergänzen oder einen Entwurf ohne Empfänger öffnen.")
        subject = st.text_input("Betreff", value=f"Austausch mit {item.dossier.name}", max_chars=170, key=f"mail-subject-{identity}")
        owner = saved.get("analyst_name") or "[Name]"
        default = (f"Guten Tag,\n\n{brief.intro}\n\n"
                   "Hätten Sie Zeit für einen kurzen Austausch in den kommenden Tagen?\n\n"
                   f"Viele Grüße\n{owner}")
        body = st.text_area("Nachricht", value=default, height=175, max_chars=1200, key=f"mail-body-{identity}")
        try:
            href = mailto(recipient, subject, body)
        except ValueError as error:
            st.warning(str(error))
            return
        st.markdown(f'<a class="fr-mail" href="{escape(href, quote=True)}">Im Mailprogramm öffnen ↗</a>',
                    unsafe_allow_html=True)
        st.caption("Klappt mit einem eingerichteten Standard-Mailprogramm. Den Kontaktstatus nach dem Versand unten aktualisieren.")
        message = EmailMessage(policy=policy.SMTP)
        message["X-Unsent"] = "1"
        if recipient.strip():
            message["To"] = recipient.strip()
        message["Subject"] = subject
        message.set_content(body)
        st.download_button("E-Mail-Entwurf als Datei", message.as_bytes(), file_name="FounderRadar-Erstkontakt.eml",
                           mime="message/rfc822")


def decision_form(item, saved, decisions):
    identity = item.dossier.id
    with st.form(f"decision-{identity}"):
        st.subheader("Entscheidung und Wiedervorlage")
        choices = list(decisions)
        decision = st.selectbox("Entscheidung", choices, index=choices.index(saved.get("decision", "Pending Review")),
                                format_func=decisions.get)
        status = st.selectbox("Kontaktstatus", OUTREACH, index=OUTREACH.index(saved.get("outreach_status", OUTREACH[0])),
                              format_func=OUTREACH_LABELS.get)
        reason = st.text_area("Begründung", value=saved.get("reason", ""), max_chars=20000)
        notes = st.text_area("Notizen", value=saved.get("notes", ""), max_chars=20000)
        action = st.text_input("Nächster Schritt", value=saved.get("next_action", item.next_steps[0] if item.next_steps else ""),
                               max_chars=2000)
        owner = st.text_input("Verantwortlich", value=saved.get("analyst_name", ""), max_chars=500)
        due = st.date_input("Fällig am", value=date.fromisoformat(saved["due_date"]) if saved.get("due_date") else None)
        task = st.selectbox("Aufgabenstatus", ["Open", "Done"], index=int(saved.get("task_status") == "Done"),
                            format_func=lambda value: "Offen" if value == "Open" else "Erledigt")
        if st.form_submit_button("Entscheidung und Aufgabe speichern", type="primary"):
            try:
                save_decision("live", identity, decision, notes, reason, action, owner, due.isoformat() if due else "",
                              outreach_status=status, task_status=task)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state.fr_saved_decision = identity
                st.rerun()
    if st.session_state.pop("fr_saved_decision", None) == identity:
        st.success("Entscheidung und Wiedervorlage gespeichert.")
    history = load_history("live", identity)
    if history:
        with st.expander("Änderungsverlauf"):
            st.dataframe(history, hide_index=True, width="stretch")


def company_detail(item, run, saved, statuses, decision_labels, default_contact=False):
    dossier = item.dossier
    brief = brief_for(item)
    st.markdown('<div class="fr-kicker">FounderRadar / Deep Dive</div>', unsafe_allow_html=True)
    st.title(dossier.name)
    st.write(brief.headline)
    provenance = f"Redaktionell recherchiert · {CHECKED}" if brief.editorial else "Aus öffentlichen Belegen abgeleitet"
    st.caption(f"{statuses[item.queue]} · {', '.join(dossier.sectors)} · {provenance}")
    left, middle, right = st.columns(3)
    left.metric("Screening", f"{item.score:.1f}/100" if item.score is not None else "Offen")
    middle.metric("Belegte Merkmale", f"{round(item.coverage * 6)} von 6")
    right.metric("Kontaktstatus", OUTREACH_LABELS.get(saved.get("outreach_status"), OUTREACH_LABELS[OUTREACH[0]]))
    callout("Warum jetzt sprechen?" if item.queue == "ranked" else "Nächster Prüfschritt",
            brief.why if item.queue == "ranked" else brief.gate)
    tabs = st.tabs(["Kurzprofil", "Markt & Wettbewerb", "Score & Quellen", "Kontakt & Aufgaben"],
                   default="Kontakt & Aufgaben" if default_contact else "Kurzprofil",
                   key=f"fr-tabs-{dossier.id}-{int(default_contact)}")
    with tabs[0]:
        overview_tab(item, brief, run)
    with tabs[1]:
        market_tab(item, brief)
    with tabs[2]:
        evidence_tab(item, brief)
    with tabs[3]:
        draft_email(item, brief, saved)
        decision_form(item, saved, decision_labels)
