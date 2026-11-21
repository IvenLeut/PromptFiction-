"""FounderRadar visual system: charcoal, white and a warm orange accent.

Also the single home of display constants and value formatting shared by all views.
The CSS below and .streamlit/config.toml use the same palette values.
"""
import re
from datetime import date
from html import escape

import streamlit as st

# Palette
WHITE = "#ffffff"
INK = "#221f19"            # body text, hover labels, thesis box
CHARCOAL = "#161616"       # company score bars
BLACK = "#171717"          # "Seed" slice, market bar in the profile chart
ORANGE = "#f5653f"         # accent
RUST = "#b63716"           # risk bar in the profile chart
TEAL = "#94cbd0"           # overall score bar, "Early Growth" slice
TEAL_DARK = "#78bfc5"      # risk bars in the comparison chart
NEUTRAL = "#c9cdd2"        # "Unbekannt" slice
MUTED = "#626971"          # axis labels
GRID = "#dfe3e6"           # 3D grid
GRID_LIGHT = "#ededed"     # 2D grid
PANEL = "#f7f8f9"          # 3D background
ZERO_LINE = "#b8bec4"
RISK_LOW = "#106049"       # risk colour scale: green -> orange -> red
RISK_HIGH = "#aa2c20"
FONT = "Arial, sans-serif"
STAGE_COLORS = {"Pre-Seed": ORANGE, "Seed": BLACK, "Early Growth": TEAL, "Unbekannt": NEUTRAL}

# Layout
SCORE_MAX = 100
TOP_N_OPTIONS = [10, 20]
COMPARISON_LIMIT = 10      # bars in the direct comparison
QUESTION_PREVIEW = 8       # open questions shown before collapsing the rest
TABLE_ROW_HEIGHT = 44
TABLE_MAX_HEIGHT = 740

UNKNOWN = "Unbekannt"


def format_score(score: float | None, missing: str = UNKNOWN) -> str:
    """Score with one decimal, e.g. "53.7"; ``missing`` if unknown."""
    return missing if score is None else f"{score:.1f}"


def format_number(amount: float | int | None, suffix: str = "") -> str:
    """Whole number with German thousands separator, e.g. "1.029.852 EUR"."""
    return UNKNOWN if amount is None else f"{amount:,.0f}{suffix}".replace(",", ".")


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>#$~|&])")
_MARKDOWN_LINE_START = re.compile(r"(?m)^([ \t]*)(?:([-+=])|(\d+)([.)]))")


def md_escape(text: object) -> str:
    """Text from sources as literal Markdown: `_`, `*`, `$`, `[`, `<`, `&` … must not format, link or start LaTeX,
    a line starting with "-", "+", "=" or "1." must not become a list or heading, and line breaks are kept.

    Use it for every sourced string handed to st.write/st.markdown/st.caption/st.warning/st.title;
    `fact()` and `heading()` escape HTML themselves.
    """
    out = _MARKDOWN_SPECIAL.sub(r"\\\1", str(text))
    out = _MARKDOWN_LINE_START.sub(lambda m: m[1] + ("\\" + m[2] if m[2] else m[3] + "\\" + m[4]), out)
    return out.replace("\n", "  \n")


def format_date(day: date) -> str:
    """German date, e.g. "21.11.2026"."""
    return f"{day:%d.%m.%Y}"


def apply_theme():
    """Inject the FounderRadar CSS."""
    st.markdown('''<style>
    .stApp {background:#ffffff;color:#221f19;}
    .block-container {max-width:1480px;padding:2rem 3.5rem 4rem;}
    [data-testid="stHeader"] {background:transparent;}
    h1,h2,h3 {letter-spacing:-.035em!important;font-weight:650!important;}
    h1 {font-size:clamp(2.3rem,4vw,4.2rem)!important;line-height:1.08!important;}
    h2 {font-size:1.9rem!important;}
    p {line-height:1.6;}
    [data-testid="stSidebar"] {background:#f4f5f6;border-right:1px solid #e4e6e8;}
    [data-testid="stMetric"] {padding:1.15rem 1.35rem;border:0;
        border-left:1px solid #e4e6e8;border-radius:0;background:white;}
    [data-testid="stMetricLabel"] {color:#626971;font-size:.875rem;}
    [data-testid="stMetricValue"] {font-size:3.2rem;letter-spacing:-.06em;}
    [data-testid="stDataFrame"] {border:1px solid #e4e6e8;border-radius:8px;overflow:hidden;}
    [data-testid="stButton"] button,[data-testid="stLinkButton"] a {
        border-radius:30px;font-weight:600;min-height:2.9rem;}
    [data-testid="stButton"] button:hover,[data-testid="stLinkButton"] a:hover {
        border-color:#f5653f;color:#b63716;}
    .fr-brand {display:flex;align-items:center;justify-content:space-between;font-size:1.5rem;font-weight:800;letter-spacing:-.06em;
        padding-bottom:1.3rem;margin-bottom:2rem;border-bottom:1px solid #dedede;}
    .fr-brand span {font-size:.75rem;letter-spacing:.13em;font-weight:500;color:#626971;}
    .fr-brand b {color:#d64724;}
    .fr-hero {position:relative;overflow:hidden;padding:2.5rem 0 2rem;}
    .fr-hero h1 {font-size:clamp(2.8rem,5vw,5rem)!important;max-width:950px;position:relative;z-index:1;}
    .fr-hero em {font-family:Georgia,serif;font-weight:400;letter-spacing:-.05em;}
    .fr-orbit {position:absolute;right:4%;top:2rem;width:230px;height:230px;
        border:32px solid #f9ded4;border-radius:50%;transform:rotate(-32deg);opacity:.65;}
    .fr-orbit:after {content:'';position:absolute;width:285px;height:75px;border:2px solid #a8d7d9;
        border-radius:50%;top:42px;left:-60px;transform:rotate(22deg);}
    .fr-flow {display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin:1rem 0 2rem;}
    .fr-flow div {border-top:1px solid #d9dce0;padding-top:1rem;}
    .fr-flow b {font-size:.75rem;letter-spacing:.12em;color:#b63716;display:block;margin-bottom:.5rem;}
    .fr-flow span {font-size:1rem;font-weight:600;}
    .fr-summary {display:grid;grid-template-columns:repeat(4,1fr);margin:1rem 0 2.5rem;border-top:1px solid #dedede;border-bottom:1px solid #dedede;}
    .fr-kpi {padding:1.7rem 1rem;border-right:1px solid #dedede;}
    .fr-kpi:last-child{border-right:0;}
    .fr-kpi small {display:block;text-transform:uppercase;letter-spacing:.1em;color:#626971;font-size:.75rem;}
    .fr-kpi strong {display:block;font-size:clamp(2.3rem,4vw,3.8rem);letter-spacing:-.07em;line-height:1.3;color:#161616;}
    .fr-kpi p {font-size:.8rem;margin:0;color:#626971;}
    .fr-kpi .fr-meter {height:4px;background:#eceeef;margin:.7rem 0;max-width:180px;}
    .fr-kpi .fr-meter i {display:block;height:100%;background:#f5653f;}
    [data-testid="stRadio"] [role="radiogroup"] {gap:.75rem;}
    [data-testid="stRadio"] [role="radiogroup"] label {border:1px solid #d9dce0;border-radius:12px;padding:1rem 1.2rem!important;flex:1;}
    [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {background:#fff2ec;border-color:#f5653f;}
    .fr-eyebrow {font-size:.8rem;font-weight:700;letter-spacing:.13em;
        text-transform:uppercase;color:#b63716;margin-bottom:.65rem;}
    .fr-intro {font-size:1.05rem;color:#626971;max-width:740px;margin-bottom:1.8rem;}
    .fr-thesis {background:#221f19;color:#fff;padding:1.8rem 2rem;border-radius:8px;
        border-top:4px solid #f5653f;margin:.6rem 0 1.5rem;}
    .fr-thesis .fr-eyebrow {color:#ffaf98;}
    .fr-thesis p {font-size:1.1rem;line-height:1.75;margin:0;}
    .fr-fact {border-bottom:1px solid #e4e6e8;padding:.8rem 0;}
    .fr-fact-label {font-size:.85rem;color:#626971;margin-bottom:.25rem;}
    .fr-fact-value {font-size:1rem;font-weight:600;overflow-wrap:anywhere;}
    @media(max-width:700px){.block-container{padding:1.5rem 1rem;} .fr-thesis{padding:1.2rem;}
    .fr-summary,.fr-flow{grid-template-columns:repeat(2,1fr);} .fr-orbit{opacity:.25;right:-100px;}
    .fr-brand span{display:none;} .fr-kpi strong{font-size:2.8rem;}}
    </style>''', unsafe_allow_html=True)


def brand():
    """Top bar with the product name."""
    st.markdown('<div class="fr-brand"><div>FounderRadar<b>●</b></div><span>VENTURE INTELLIGENCE / GERMANY</span></div>', unsafe_allow_html=True)


def landing(live: bool = False):
    """Start-page hero; the caption names the data source of the selected mode."""
    st.markdown('''<div class="fr-hero"><div class="fr-orbit"></div>
    <div class="fr-eyebrow">Von der Entdeckung zur Investmenthypothese</div>
    <h1>Früh erkennen.<br><em>Fundiert entscheiden.</em></h1>
    <p class="fr-intro">Ein Technologiefeld. Die relevanten Startups. Ein klarer Blick auf
    Unternehmensstärke, Marktpotenzial und Risiko.</p></div>
    <div class="fr-flow"><div><b>01 / DISCOVER</b><span>Kategorie wählen</span></div>
    <div><b>02 / RESEARCH</b><span>Kontext verbinden</span></div>
    <div><b>03 / EVALUATE</b><span>Potenziale bewerten</span></div>
    <div><b>04 / EXPLORE</b><span>Ergebnisse entdecken</span></div></div>''', unsafe_allow_html=True)
    if live:
        st.caption("Live-Modus: Förderprojekte aus dem Förderkatalog des Bundes, ergänzt um öffentliche Quellen.")
    else:
        st.caption("Interaktiver Prototyp mit fiktiven Daten. Quellen und Kontakte sind Demo-Platzhalter.")


def summary_kpis(leads):
    """Four KPI cards with the mean of each known score."""
    def mean(field):
        values = [getattr(x, field) for x in leads if getattr(x, field) is not None]
        return sum(values) / len(values) if values else None
    cards = []
    for label, field, hint in [("Ø Gesamt-Score", "overall_score", "Gesamtbewertung aus Schritt 3"),
                                ("Ø Unternehmensscore", "company_score", "Unternehmensstärke · höher ist besser"),
                                ("Ø Marktpotenzial", "market_potential_score", "Marktchance · höher ist besser"),
                                ("Ø Risiko", "risk_score", "Risikowert · niedriger ist besser")]:
        score = mean(field)
        formatted = format_score(score, missing="—")
        cards.append(f'<div class="fr-kpi"><small>{label}</small><strong>{formatted}</strong>'
                     f'<div class="fr-meter"><i style="width:{score or 0}%"></i></div><p>{hint}</p></div>')
    st.markdown('<div class="fr-summary">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def heading(kicker: str, title: str, description: str):
    """Eyebrow, page title and intro paragraph."""
    st.markdown(f'<div class="fr-eyebrow">{escape(kicker)}</div>', unsafe_allow_html=True)
    st.title(md_escape(title))
    st.markdown(f'<div class="fr-intro">{escape(description)}</div>', unsafe_allow_html=True)


def fact(label: str, item: object):
    """One labelled value in a fact list."""
    st.markdown(f'<div class="fr-fact"><div class="fr-fact-label">{escape(label)}</div>'
                f'<div class="fr-fact-value">{escape(str(item))}</div></div>', unsafe_allow_html=True)
