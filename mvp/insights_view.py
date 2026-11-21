"""Render sourced AI findings and public professional team cards."""
from html import escape

import streamlit as st

from mvp.ai import InsightJobs, analysis_access, fingerprint, input_for, load_insight
from mvp.briefs import http_url
from mvp.showcase import finding_card


@st.cache_resource
def insight_jobs():
    return InsightJobs()


@st.fragment(run_every=2.0)
def insight_control(item):
    access = analysis_access()
    identity = item.dossier.id
    status, note = insight_jobs().status(identity)
    marker = f"fr-ai-marker-{identity}"
    stored = load_insight(identity)
    if status == "done" and stored and st.session_state.get(marker) != stored.result.created_at:
        st.session_state[marker] = stored.result.created_at
        st.rerun()
    if status == "running":
        st.caption("Projekt-KI prüft die Belege. Der bisherige Stand bleibt geöffnet.")
    elif status == "failed":
        st.warning(note)
    if not access:
        st.caption("Projekt-KI gerade nicht verbunden. Gespeicherte Einsichten bleiben verfügbar.")
        return
    data = input_for(item)
    available = any(line.source_url for line in data.evidence)
    label = "KI-Auswertung aktualisieren" if stored else "KI-Auswertung erstellen"
    if st.button(label, disabled=status == "running" or not available, key=f"project-ai-{identity}"):
        insight_jobs().start(identity, data, access)
        st.rerun()


def claim_html(claim, saved):
    source_map = {line.id: line for line in saved.evidence}
    links = []
    seen = set()
    for identity in claim.sources:
        source = source_map.get(identity)
        if source and http_url(source.source_url) and source.source_url not in seen:
            seen.add(source.source_url)
            url = escape(source.source_url, quote=True)
            links.append(f'<a class="fr-source" href="{url}" target="_blank" rel="noopener noreferrer">Beleg ↗</a>')
    return escape(claim.text) + "".join(links)


def render_claim(claim, saved):
    st.markdown("<p>" + claim_html(claim, saved) + "</p>", unsafe_allow_html=True)


def insight_origin(item, saved):
    same = fingerprint(input_for(item)) == saved.fingerprint
    age = "Aktueller Quellenstand" if same else "Gespeicherter früherer Quellenstand"
    st.caption(f"Projekt-KI · {saved.result.model} · {saved.result.created_at:%d.%m.%Y} · {age}")


def findings(item, brief, saved):
    dossier = item.dossier
    if saved:
        strengths = [claim_html(claim, saved) for claim in saved.result.analysis.strengths]
        risks = [claim_html(claim, saved) for claim in saved.result.analysis.risks]
    else:
        strengths = []
        for key, label in (("technology", "Techniksignal"), ("validation", "Entwicklungsnachweis"),
                           ("buyer", "Zielkundentyp")):
            if key in dossier.facts:
                strengths.append(escape(f"{label} · {dossier.facts[key].value}"))
        strengths = (strengths + ["Weitere Stärke offen.", "Öffentlicher Beleg fehlt."])[:2]
        risks = [escape(reason) for reason in (item.reasons or [item.risk, brief.question])[:2]]
        if len(risks) == 1:
            risks.append(escape(brief.question))
        st.caption("Hinweise aus dem regelbasierten Screening")
    left, right = st.columns(2)
    with left:
        finding_card("2 Hauptstärken", strengths, "good")
    with right:
        finding_card("2 Prüfrisiken", risks, "watch")


def team_cards(item, saved):
    st.subheader("Gründerteam")
    profiles = {observation.name: observation.profile_url for observation in item.dossier.team_evidence
                if observation.profile_url and http_url(observation.profile_url)}
    if saved and saved.result.analysis.founders:
        for person in saved.result.analysis.founders:
            with st.container(border=True):
                st.markdown("**" + escape(person.name) + "**")
                for label, claim in (("Rolle", person.role), ("Ausbildung", person.education), ("Erfahrung", person.experience)):
                    if claim:
                        st.markdown(f"<b>{label}</b> · " + claim_html(claim, saved), unsafe_allow_html=True)
                    else:
                        st.caption(label + " · offen")
                if person.name in profiles:
                    st.link_button("Berufliches Profil öffnen", profiles[person.name])
        st.caption("Angaben aus öffentlich zugänglichen beruflichen Quellenverweisen der Projekt-KI.")
        return
    people = {}
    for observation in item.dossier.team_evidence:
        if observation.name:
            people.setdefault(observation.name, []).append(observation)
    if not people:
        st.info("Für dieses Unternehmen liegen noch keine namentlich belegten Teamprofile vor.")
        return
    for name, observations in people.items():
        with st.container(border=True):
            st.markdown("**" + escape(name) + "**")
            for observation in observations:
                if observation.role:
                    st.write(observation.role)
                if observation.biography:
                    st.caption(observation.biography)
                if http_url(observation.source.url):
                    st.link_button("Teambeleg öffnen", observation.source.url)
            if name in profiles:
                st.link_button("Berufliches Profil öffnen", profiles[name])
    st.caption("Teamangaben aus der Unternehmenswebsite. Die Projekt-KI kann daraus belegte Angaben zu Ausbildung und Erfahrung übernehmen.")
