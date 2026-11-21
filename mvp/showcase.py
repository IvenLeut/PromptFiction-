"""Compact, responsive cockpit components with explicit evidence states."""
from html import escape

import streamlit as st

SECTOR_ICONS = {
    "AI / Software": "🧠",
    "ClimateTech": "🌱",
    "HealthTech": "✚",
    "FinTech": "▥",
    "Industrial / DeepTech": "⚙",
}
STATUS = {
    "ranked": ("Bewertbar", "good"),
    "research": ("Recherche offen", "watch"),
    "excluded": ("Außerhalb Suchprofil", "neutral"),
}


def sector_icon(dossier):
    primary = next((sector for sector in dossier.sectors if sector in SECTOR_ICONS), None)
    return SECTOR_ICONS.get(primary, "◎")


def metrics(cards):
    body = "".join(
        f'<div class="fr-kpi fr-{tone}"><span>{escape(label)}</span>'
        f'<strong>{escape(str(value))}</strong><small>{escape(note)}</small></div>'
        for label, value, note, tone in cards
    )
    st.markdown(f'<div class="fr-kpis">{body}</div>', unsafe_allow_html=True)


def candidate_card(item, label, comment):
    name = escape(item.dossier.name)
    status, tone = STATUS[item.queue]
    industry = escape(" · ".join(item.dossier.sectors) or "Branche offen")
    score = f"{item.score:.1f} / 100" if item.score is not None else "Score offen"
    st.markdown(
        f'<div class="fr-candidate"><div class="fr-candidate-head">'
        f'<b>{sector_icon(item.dossier)} {name}</b><div class="fr-pills">'
        f'<span class="fr-pill fr-{tone}">{status}</span><span class="fr-pill fr-neutral">{score}</span></div></div>'
        f'<span class="fr-sector">{industry}</span><p><b>{escape(label)}</b> {escape(comment)}</p></div>',
        unsafe_allow_html=True,
    )


def finding_card(title, texts, tone):
    content = "".join(f"<li>{text}</li>" for text in texts)
    st.markdown(
        f'<section class="fr-findings fr-{tone}"><h4>{escape(title)}</h4><ul>{content}</ul></section>',
        unsafe_allow_html=True,
    )
