"""FounderRadar visual system, inspired by the colour world, type and white space of htgf.de.

FounderRadar is its own brand: no HTGF logo, wordmark or imagery. Only the following was taken as
inspiration from the public theme CSS of https://www.htgf.de/de/ (wp-content/themes/htgf/assets/css/theme.css,
read 21.11.2026):
- warm greys `--htgf--preset--color--fond` #F0EEEB, `accent-2` #F7F6F5, `grey` #D9D4CC, `fond-dark` #221F19,
  text #313131, and black pill buttons (`border-radius: 9999px`, weight 500);
- the accent `--htgf--preset--color--berry` #FA6446 (focus outline #F5653F), the secondary `mint` #64C2C8,
  `green1` #106049 and the amber -> mint text gradient (#E8A339 -> #68B0B5);
- generous radii (`border-radius--2` 2rem) and uppercase captions with .05rem letter spacing.

Fonts: htgf.de uses ITC Avant Garde Gothic (headlines) and "ESFace" (body); both are commercial licences.
FounderRadar ships free look-alikes under the SIL Open Font License (assets/fonts/, licences next to them):
Questrial (geometric sans close to Avant Garde) for headlines, Hanken Grotesk (calm grotesque) for text.
They are embedded as data URIs so the demo also renders offline.

Also the single home of display constants and value formatting shared by all views.
.streamlit/config.toml uses the same palette values.
"""
import base64
import re
from datetime import date
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

# Palette (HTGF-inspired warm neutrals, berry accent)
WHITE = "#ffffff"
FOND = "#f0eeeb"           # warm grey panels (htgf fond / accent-1)
FOND_LIGHT = "#f7f6f5"     # lighter panel (htgf accent-2)
STONE = "#d9d4cc"          # borders, "Unbekannt" slice (htgf grey)
INK = "#221f19"            # dark panels, hover labels, thesis box (htgf fond-dark)
TEXT = "#313131"           # body text
CHARCOAL = "#161616"       # company score bars
BLACK = "#000000"          # primary buttons, "Seed" slice
BERRY = "#fa6446"          # accent (htgf berry)
ORANGE = "#f5653f"         # accent for marks and focus (htgf outline colour)
RUST = "#b8452c"           # accent for text on white (contrast 4.9:1), risk bar
AMBER = "#e8a339"          # gradient start
MINT = "#64c2c8"           # secondary accent (htgf mint)
TEAL = MINT                # overall score bar, "Early Growth" slice
TEAL_DARK = "#3f9ea4"      # risk bars in the comparison chart
NEUTRAL = STONE
MUTED = "#6b655d"          # captions, axis labels (warm grey, contrast 5.8:1 on white)
GRID = "#e4e0da"           # 3D grid
GRID_LIGHT = "#ece9e4"     # 2D grid
PANEL = FOND_LIGHT         # 3D background
ZERO_LINE = "#bdb6ab"
RISK_LOW = "#106049"       # risk colour scale: green (htgf green1) -> orange -> red
RISK_HIGH = "#aa2c20"
HEAD_FONT = "Questrial"
BODY_FONT = "Hanken Grotesk"
FONT = f"{BODY_FONT}, Arial, sans-serif"
STAGE_COLORS = {"Pre-Gründung": AMBER, "In Gründung": MINT, "Pre-Seed": ORANGE, "Seed": BLACK,
                "Early Growth": TEAL_DARK, "Zu spät": RUST, "Unbekannt": NEUTRAL}

# Layout
SCORE_MAX = 100
TOP_N_OPTIONS = [10, 20, 50]
COMPARISON_LIMIT = 10      # bars in the direct comparison
QUESTION_PREVIEW = 8       # open questions shown before collapsing the rest
TABLE_ROW_HEIGHT = 44
TABLE_MAX_HEIGHT = 740

UNKNOWN = "Unbekannt"
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def format_score(score: float | None, missing: str = UNKNOWN) -> str:
    """Score with one decimal, e.g. "53.7"; ``missing`` if unknown."""
    return missing if score is None else f"{score:.1f}"


def format_number(amount: float | int | None, suffix: str = "") -> str:
    """Whole number with German thousands separator, e.g. "1.029.852 EUR"."""
    return UNKNOWN if amount is None else f"{amount:,.0f}{suffix}".replace(",", ".")


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>#$~|&])")
_MARKDOWN_LINE_START = re.compile(r"(?m)^([ \t]*)(?:([-+=])|(\d+)([.)]))")


# Raw enum values of steps 2/3 as shown in the UI (snake_case never reaches the screen).
VALUE_LABELS = {
    "pre_gruendung": "Pre-Gründung", "in_gruendung": "In Gründung", "pre_seed": "Pre-Seed", "seed": "Seed",
    "zu_spaet": "Zu spät", "am_markt": "Am Markt", "pilot": "Pilot", "erste_kunden": "Erste Kunden",
    "prototyp": "Prototyp", "labor_prototyp": "Laborprototyp", "paper": "Forschung / Paper", "idee": "Idee",
    "hardware": "Hardware", "hardware_software": "Hardware + Software", "software": "Software",
    "plattform": "Plattform", "wirkstoff": "Wirkstoff", "b2b": "B2B", "b2c": "B2C", "b2b2c": "B2B2C",
    "patent_erteilt": "Patent erteilt", "patent_angemeldet": "Patent angemeldet",
    "non_vc_funded": "Öffentlich gefördert, kein VC belegt", "vc_backed": "VC-finanziert", "unfunded": "Ohne Finanzierung",
    "funded": "Finanziert", "conflicting": "Widersprüchlich", "confirmed": "Bestätigt", "reported_none": "Kein VC laut Quelle",
    "unknown": "Unbekannt", "Unknown": "Unbekannt", "vc_potenzial": "VC-Potenzial", "agentur": "Agentur",
    "beratung": "Beratung", "studi_projekt": "Studienprojekt", "hobby": "Hobby", "bereits_finanziert": "Bereits finanziert",
    "bewertet": "Bewertet", "zurueck_an_sourcing": "Zurück an Sourcing",
}


def readable(value: object) -> str:
    """Display label for a raw enum value ("am_markt" -> "Am Markt"); other text is returned unchanged."""
    if value is None:
        return UNKNOWN
    text = str(value)
    if text in VALUE_LABELS:
        return VALUE_LABELS[text]
    if re.fullmatch(r"[a-z]+(?:_[a-z]+)+", text):
        return text.replace("_", " ").capitalize()
    return text


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


@lru_cache(maxsize=1)
def _font_faces() -> str:
    """@font-face rules with the bundled OFL fonts as data URIs; empty if the files are missing."""
    rules = []
    for family, file, weights in ((HEAD_FONT, "Questrial-latin.woff2", "400"),
                                  (BODY_FONT, "HankenGrotesk-latin.woff2", "100 900")):
        path = FONT_DIR / file
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            rules.append(f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weights};"
                         f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2');}}")
    return "".join(rules)


# Metric-card rule after the `style_metric_cards` pattern of streamlit-extras (Apache-2.0, see NOTICE.md):
# restyle st.metric via its data-testid instead of custom HTML, adapted to the warm palette.
_CSS = """
:root {--fr-head:'Questrial','Avenir Next','Century Gothic',sans-serif;
       --fr-body:'Hanken Grotesk','Helvetica Neue',Arial,sans-serif;}
.stApp {background:#ffffff;color:#313131;}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] {font-family:var(--fr-body);}
.block-container {max-width:1440px;padding:1.6rem 3.2rem 5rem;}
[data-testid="stHeader"] {background:transparent;}
h1,h2,h3,h4,h5,.fr-head {font-family:var(--fr-head)!important;font-weight:400!important;letter-spacing:-.02em!important;color:#000;}
h1 {font-size:clamp(2.4rem,4.4vw,4.6rem)!important;line-height:1.05!important;}
h2 {font-size:clamp(1.6rem,2.4vw,2.2rem)!important;}
h3 {font-size:1.45rem!important;}
p {line-height:1.6;}
a {color:#000;text-decoration-color:#fa6446;text-underline-offset:3px;}
[data-testid="stCaptionContainer"] {color:#6b655d;}
[data-testid="stSidebar"] {background:#f7f6f5;border-right:1px solid #e4e0da;}
div[data-testid="stMetric"] {padding:1.1rem 1.3rem;background:#f7f6f5;border:0;border-radius:1.5rem;
    border-left:.35rem solid #fa6446!important;}
[data-testid="stMetricLabel"] {color:#6b655d;font-size:.8rem;text-transform:uppercase;letter-spacing:.05rem;}
[data-testid="stMetricValue"] {font-family:var(--fr-head);font-size:2.4rem;letter-spacing:-.03em;color:#000;}
[data-testid="stDataFrame"] {border:1px solid #e4e0da;border-radius:1rem;overflow:hidden;}
[data-testid="stButton"] button,[data-testid="stLinkButton"] a,[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {border-radius:9999px;font-weight:500;min-height:2.9rem;
    padding:0 1.4rem;border:1.25px solid #000;background:#fff;color:#000;transition:all .2s ease;}
[data-testid="stButton"] button[kind="primary"],[data-testid="stLinkButton"] a[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {background:#000;color:#fff;}
[data-testid="stButton"] button:hover,[data-testid="stLinkButton"] a:hover,[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {border-color:#fa6446;color:#000;background:#f0eeeb;}
:focus-visible {outline:2px solid #f5653f!important;outline-offset:2px;}
[data-testid="stExpander"] details {border:1px solid #e4e0da;border-radius:1rem;background:#fff;}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {border-radius:1.5rem;}
[data-baseweb="tab-list"] {gap:.4rem;}
[data-testid="stTabs"] button[role="tab"],[data-baseweb="tab"] {border-radius:9999px!important;padding:.35rem 1rem!important;background:#f7f6f5;}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"],[data-baseweb="tab"][aria-selected="true"] {background:#000;color:#fff;}
[data-baseweb="tab-highlight"],[data-baseweb="tab-border"] {display:none;}
[data-testid="stRadio"] [role="radiogroup"] {gap:.6rem;flex-wrap:wrap;}
[data-testid="stRadio"] [role="radiogroup"] label {border:1px solid #d9d4cc;border-radius:9999px;padding:.7rem 1.2rem!important;
    background:#fff;margin:0;}
[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {background:#f0eeeb;border-color:#000;}
hr {border-color:#e4e0da!important;}
.fr-brand {display:flex;align-items:center;justify-content:space-between;padding:.4rem 0 1.2rem;margin-bottom:1.6rem;
    border-bottom:1px solid #e4e0da;}
.fr-brand .fr-word {font-family:var(--fr-head);font-size:1.55rem;letter-spacing:-.03em;color:#000;display:flex;align-items:center;gap:.55rem;}
.fr-brand .fr-dot {width:.9rem;height:.9rem;border-radius:50%;background:linear-gradient(45deg,#e8a339,#68b0b5);display:inline-block;}
.fr-brand span.fr-tag {font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#6b655d;}
.fr-hero {position:relative;overflow:hidden;padding:2.6rem 2.6rem 2.4rem;border-radius:2rem;background:#f0eeeb;margin-bottom:1.6rem;}
.fr-hero h1 {font-size:clamp(2.8rem,6vw,5.6rem)!important;max-width:1000px;position:relative;z-index:1;margin:0 0 .6rem;}
.fr-hero .fr-intro {position:relative;z-index:1;color:#313131;}
.fr-grad {background-image:linear-gradient(45deg,#e8a339,#68b0b5);-webkit-background-clip:text;background-clip:text;
    -webkit-text-fill-color:transparent;color:transparent;}
.fr-blob {position:absolute;right:-6rem;top:-6rem;width:26rem;height:26rem;border-radius:50%;
    background:radial-gradient(circle at 35% 35%,rgba(232,163,57,.55),rgba(104,176,181,.35) 55%,rgba(240,238,235,0) 72%);
    filter:blur(30px);}
.fr-flow {display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin:0 0 1.8rem;}
.fr-flow div {border-top:1px solid #d9d4cc;padding-top:.9rem;}
.fr-flow b {font-size:.72rem;letter-spacing:.12em;color:#b8452c;display:block;margin-bottom:.4rem;font-weight:600;}
.fr-flow span {font-size:1rem;font-weight:500;}
.fr-summary {display:grid;grid-template-columns:repeat(4,1fr);gap:.8rem;margin:.8rem 0 2rem;}
.fr-kpi {padding:1.3rem 1.4rem;border-radius:1.5rem;background:#f7f6f5;}
.fr-kpi small {display:block;text-transform:uppercase;letter-spacing:.05rem;color:#6b655d;font-size:.74rem;font-weight:500;}
.fr-kpi strong {display:block;font-family:var(--fr-head);font-weight:400;font-size:clamp(2.1rem,3.6vw,3.3rem);
    letter-spacing:-.03em;line-height:1.25;color:#000;}
.fr-kpi p {font-size:.82rem;margin:0;color:#6b655d;}
.fr-kpi .fr-meter {height:4px;background:#e4e0da;margin:.6rem 0;max-width:180px;border-radius:9999px;overflow:hidden;}
.fr-kpi .fr-meter i {display:block;height:100%;background:#fa6446;}
.fr-kpi.fr-dark {background:#221f19;}
.fr-kpi.fr-dark strong {color:#fff;}
.fr-kpi.fr-dark small,.fr-kpi.fr-dark p {color:#d9d4cc;}
.fr-eyebrow {font-size:.76rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:#b8452c;margin-bottom:.55rem;}
.fr-intro {font-size:1.08rem;color:#6b655d;max-width:760px;margin-bottom:1.6rem;}
.fr-thesis {background:#221f19;color:#fff;padding:1.7rem 2rem;border-radius:1.5rem;margin:.6rem 0 1.5rem;}
.fr-thesis .fr-eyebrow {color:#e8a339;}
.fr-thesis p {font-size:1.08rem;line-height:1.7;margin:0;}
.fr-thesis-row {display:grid;grid-template-columns:minmax(120px,22%) 1fr;gap:1rem;padding:.55rem 0;
  border-top:1px solid rgba(255,255,255,.12);}
.fr-thesis-row:first-of-type {border-top:none;}
.fr-thesis-row > span {font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:#d9d4cc;padding-top:.3rem;}
.fr-thesis-row ul {margin:0;padding-left:1.1rem;} .fr-thesis-row li {font-size:1.02rem;line-height:1.6;margin:.1rem 0;}
.fr-thesis-lead {grid-template-columns:1fr;} .fr-thesis-lead p {color:#d9d4cc;font-size:.95rem;}
.fr-proxy {display:inline-block;font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;border:1px solid #64c2c8;
  color:#64c2c8;border-radius:9999px;padding:0 .45rem;margin-left:.35rem;vertical-align:middle;cursor:help;}
@media(max-width:760px){.fr-thesis-row {grid-template-columns:1fr;gap:.2rem;}}
.fr-fact {border-bottom:1px solid #ece9e4;padding:.75rem 0;}
.fr-fact-label {font-size:.82rem;color:#6b655d;margin-bottom:.2rem;}
.fr-fact-value {font-size:1rem;font-weight:500;overflow-wrap:anywhere;}
.fr-band {display:grid;grid-template-columns:1.1fr 2fr;gap:1.6rem;align-items:center;background:#221f19;color:#fff;
    border-radius:2rem;padding:1.8rem 2.2rem;margin:.4rem 0 1.8rem;}
.fr-band strong {font-family:var(--fr-head);font-weight:400;font-size:clamp(2.4rem,4.4vw,4rem);line-height:1;letter-spacing:-.03em;}
.fr-band p {margin:.2rem 0 0;color:#d9d4cc;font-size:.95rem;}
.fr-band .fr-eyebrow {color:#e8a339;margin:0 0 .4rem;}
.fr-chip {display:inline-block;border-radius:9999px;padding:.18rem .7rem;font-size:.78rem;font-weight:500;margin:0 .35rem .35rem 0;
    background:#f0eeeb;color:#313131;border:1px solid #e4e0da;}
.fr-chip.fr-good {background:#e7f1ee;border-color:#b9d6cc;color:#106049;}
.fr-chip.fr-warn {background:#fdeae5;border-color:#f6c3b6;color:#8f2f1c;}
.fr-best {background:#f0eeeb;border-radius:2rem;padding:2rem 2.2rem;margin:.4rem 0 1rem;position:relative;overflow:hidden;}
.fr-best h2 {margin:.1rem 0 .5rem;font-size:clamp(2rem,3.4vw,3rem)!important;}
.fr-best p {max-width:860px;}
.fr-tl {list-style:none;padding:0;margin:.6rem 0 0;border-left:2px solid #d9d4cc;}
.fr-tl li {position:relative;padding:0 0 .95rem 1.3rem;margin:0;}
.fr-tl li:before {content:'';position:absolute;left:-7px;top:.35rem;width:12px;height:12px;border-radius:50%;background:#fff;border:2px solid #000;}
.fr-tl li.fr-key:before {background:#fa6446;border-color:#fa6446;}
.fr-tl time {display:block;font-size:.78rem;letter-spacing:.05rem;text-transform:uppercase;color:#6b655d;}
.fr-tl span {display:block;font-size:.98rem;}
.fr-tl a {font-size:.82rem;}
.fr-team {display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.8rem;margin:.5rem 0 1.2rem;}
.fr-person {background:#f7f6f5;border-radius:1.25rem;padding:1rem 1.1rem;}
.fr-person b {display:block;font-family:var(--fr-head);font-weight:400;font-size:1.15rem;color:#000;}
.fr-person small {display:block;color:#6b655d;font-size:.82rem;margin:.15rem 0;}
.fr-person a {font-size:.82rem;}
.fr-person .fr-links {display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.55rem;}
.fr-person a.fr-li {display:inline-block;border-radius:9999px;padding:.22rem .75rem;font-weight:500;text-decoration:none;
  background:#000;color:#fff;}
.fr-person a.fr-li.fr-li-search {background:transparent;color:#000;border:1px solid #000;}
.fr-person a.fr-li:hover {background:#b8452c;border-color:#b8452c;color:#fff;}
@media(max-width:760px){.block-container{padding:1.2rem 1rem 3rem;} .fr-thesis,.fr-hero,.fr-best{padding:1.3rem;}
  .fr-summary,.fr-flow{grid-template-columns:repeat(2,1fr);} .fr-band{grid-template-columns:1fr;padding:1.4rem;}
  .fr-brand span.fr-tag{display:none;} .fr-blob{opacity:.5;}}
"""


def apply_theme():
    """Inject fonts and the FounderRadar CSS."""
    st.html(f"<style>{_font_faces()}{_CSS}</style>")


def brand():
    """Top bar with the product name (own wordmark, no third-party logo)."""
    st.markdown('<div class="fr-brand"><div class="fr-word"><i class="fr-dot"></i>FounderRadar</div>'
                '<span class="fr-tag">Venture Intelligence · Deutschland</span></div>', unsafe_allow_html=True)


def landing(source: str = "snapshot"):
    """Start-page hero; the caption names the data source of the selected mode."""
    st.markdown('''<div class="fr-hero"><div class="fr-blob"></div>
    <div class="fr-eyebrow">Find the founders before everyone else</div>
    <h1>Gründerteams finden,<br><span class="fr-grad">bevor es alle tun.</span></h1>
    <p class="fr-intro">FounderRadar liest Frühsignale aus öffentlichen Förderprojekten, Hochschul-Ausgründungen,
    Impressum und Forschung, prüft sie gegen Startup-Datenbanken und bewertet jedes Team mit Quellen.</p></div>
    <div class="fr-flow"><div><b>01 / DISCOVER</b><span>Förderkatalog als Frühsignal</span></div>
    <div><b>02 / RESEARCH</b><span>Website, Team, Forschung, DB-Check</span></div>
    <div><b>03 / EVALUATE</b><span>Team, Markt, Risiko, Earliness</span></div>
    <div><b>04 / EXPLORE</b><span>Ranking, Deep Dive, Belege</span></div></div>''', unsafe_allow_html=True)
    captions = {
        "snapshot": "Snapshot: eingefrorener echter Lauf über 52 Förderkatalog-Leads mit Kontext und Scoring. Läuft ohne Netz.",
        "demo": "Demo-Fixtures: interaktiver Prototyp mit fiktiven Daten. Quellen und Kontakte sind Platzhalter.",
        "live": "Live-Pipeline: Förderprojekte aus dem Förderkatalog des Bundes, ergänzt um öffentliche Quellen (Netz nötig).",
    }
    st.caption(captions.get(source, captions["snapshot"]))


def kpi_cards(cards: list[tuple[str, str, str, float | None]], dark_first: bool = False):
    """KPI row; each card is (label, value, hint, meter 0-100 or None). Values are escaped."""
    html = []
    for i, (label, value, hint, meter) in enumerate(cards):
        bar = f'<div class="fr-meter"><i style="width:{max(0, min(meter, 100)):.0f}%"></i></div>' if meter is not None else ""
        css = "fr-kpi fr-dark" if dark_first and i == 0 else "fr-kpi"
        html.append(f'<div class="{css}"><small>{escape(label)}</small><strong>{escape(value)}</strong>{bar}'
                    f'<p>{escape(hint)}</p></div>')
    st.markdown('<div class="fr-summary">' + ''.join(html) + '</div>', unsafe_allow_html=True)


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
        cards.append((label, format_score(score, missing="—"), hint, score or 0))
    kpi_cards(cards)


def chips(items: list[tuple[str, str]]) -> str:
    """HTML for small pills; items are (text, kind) with kind in "", "good", "warn". Text is escaped."""
    return "".join(f'<span class="fr-chip{" fr-" + kind if kind else ""}">{escape(text)}</span>' for text, kind in items)


def heading(kicker: str, title: str, description: str):
    """Eyebrow, page title and intro paragraph."""
    st.markdown(f'<div class="fr-eyebrow">{escape(kicker)}</div>', unsafe_allow_html=True)
    st.title(md_escape(title))
    st.markdown(f'<div class="fr-intro">{escape(description)}</div>', unsafe_allow_html=True)


def fact(label: str, item: object):
    """One labelled value in a fact list."""
    st.markdown(f'<div class="fr-fact"><div class="fr-fact-label">{escape(label)}</div>'
                f'<div class="fr-fact-value">{escape(str(item))}</div></div>', unsafe_allow_html=True)
