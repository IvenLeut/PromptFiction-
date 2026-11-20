"""A restrained research terminal: compact grids, explicit hierarchy, no hero banners."""
from html import escape
import streamlit as st


def theme():
    st.markdown("""<style>
    .stApp{background:#f2f5f8;color:#182b40}
    [data-testid="stHeader"]{display:none!important}
    [data-testid="stToolbar"]{display:none}
    [data-testid="stSidebar"]{background:#142639;min-width:205px;max-width:220px}
    [data-testid="stSidebar"] *{color:#dbe5ef}
    [data-testid="stSidebar"] [data-baseweb="select"] *{color:#223b51}
    [data-testid="stSidebar"] button{background:#20384e;border-color:#3b5268;color:white}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.55rem}
    [data-testid="stMainBlockContainer"]{padding:1.1rem 1.7rem 2rem!important;max-width:1800px}
    [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"]{gap:.5rem}
    h1{font-size:1.6rem!important;letter-spacing:-.035rem;font-weight:650!important;padding:.2rem 0 .4rem!important}
    h2{font-size:1.15rem!important}h3{font-size:1rem!important}h4{font-size:.95rem!important}
    p{font-size:.94rem} [data-testid="stCaptionContainer"] p{font-size:.8rem;color:#657789}
    [data-testid="stVerticalBlockBorderWrapper"]{background:white;border-radius:7px}
    [class*="st-key-card-"]{background:white!important;border-radius:7px}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p{color:#a6b9ca!important}
    [data-testid="stMetric"]{padding:8px 12px;background:white;border:1px solid #e0e7ee;border-radius:5px}
    [data-testid="stMetricValue"]{font-size:1.2rem} [data-testid="stMetricValue"]>div{white-space:normal}
    [data-testid="stMetricLabel"] p{white-space:normal;font-size:.8rem}
    [data-testid="stDataFrame"]{border:1px solid #e0e7ee;border-radius:5px}
    [data-baseweb="tab-list"]{gap:1.35rem;border-bottom:1px solid #dbe3eb}
    button[data-baseweb="tab"]{font-size:.9rem;padding:.2rem 0 .55rem}
    button[kind="primary"]{background:#136b75;border-color:#136b75}
    button[kind="primary"]:hover{background:#0f5962;border-color:#0f5962}
    .brand{font-size:1.28rem;font-weight:750;letter-spacing:-.04rem;margin:8px 0 3px}.brand span{color:#f38b68!important}
    .brand-note{font-size:.72rem;letter-spacing:.12rem;color:#8fa7bd!important;margin-bottom:24px}
    .overline{font-size:.72rem;letter-spacing:.1rem;color:#627c92;text-transform:uppercase}
    .workspace-title{display:flex;justify-content:space-between;align-items:center;margin:0 0 12px;border-bottom:1px solid #d9e3ec;padding-bottom:10px}
    .workspace-title strong{font-size:1.05rem}.workspace-title span{font-size:.8rem;color:#5f7588}
    .kpi-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:#dde5ed;border:1px solid #dde5ed;border-radius:7px;overflow:hidden;margin:8px 0 14px}
    .kpi-cell{background:white;padding:8px 14px}.kpi-label{font-size:.78rem;color:#60758a}.kpi-value{font-size:1.4rem;line-height:1.4;font-weight:650}.kpi-note{font-size:.73rem;color:#6a7d8d}
    .mini-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:4px 0 10px}.brief-cell{background:#f5f8fb;border:1px solid #e5ebf1;padding:11px 13px;border-radius:5px;min-width:0}
    .brief-cell b{display:block;font-size:.76rem;text-transform:uppercase;letter-spacing:.04rem;color:#557087;margin-bottom:5px}.brief-cell p{font-size:.88rem;line-height:1.45;margin:0;overflow-wrap:anywhere}.brief-cell a{font-size:.75rem;color:#176c75}
    .decision-callout{background:#eaf4f3;border-left:3px solid #167783;padding:12px 14px;border-radius:4px;margin:4px 0 10px}
    .decision-callout b{font-size:.8rem;color:#155e66}.decision-callout p{font-size:.9rem;margin:5px 0 0}
    .badge{font-size:.75rem;background:#e9eff5;color:#39556c;border-radius:4px;padding:4px 8px;display:inline-block;margin:0 4px 4px 0}
    .warning-badge{background:#fff0e8;color:#9c4b2e}.sector-mark{display:inline-flex;width:42px;height:42px;border-radius:9px;background:#e6f0f1;color:#126875;align-items:center;justify-content:center;font-size:1rem;font-weight:700;margin-right:10px;vertical-align:middle}
    .fact-row{display:grid;grid-template-columns:135px 1fr;padding:8px 0;border-bottom:1px solid #edf1f5;font-size:.88rem;gap:10px}.fact-row span{color:#657d91}.fact-row strong{font-weight:500;overflow-wrap:anywhere}
    .section-label{font-size:.88rem;font-weight:650;margin:0 0 4px;color:#243e54}
    @media(max-width:950px){[data-testid="stHeader"]{display:block!important;background:#f2f5f8!important;height:2.5rem!important}[data-testid="stMainBlockContainer"]{padding:3rem 1rem 2rem!important}.kpi-cell{padding:10px}.mini-grid{grid-template-columns:1fr}}
    @media(max-width:600px){.kpi-strip{grid-template-columns:1fr 1fr}}
    </style>""", unsafe_allow_html=True)


def kpis(values):
    st.markdown('<div class="kpi-strip">'+''.join(
        f'<div class="kpi-cell"><div class="kpi-label">{escape(str(label))}</div><div class="kpi-value">{escape(str(value))}</div><div class="kpi-note">{escape(str(note))}</div></div>'
        for label, value, note in values)+'</div>', unsafe_allow_html=True)


def fact_rows(values):
    from cockpit_data import known
    rows = [(label, value) for label, value in values.items() if known(value)]
    if not rows:
        st.caption("No structured facts supplied by the research pipeline yet.")
    else:
        st.markdown(''.join(f'<div class="fact-row"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>' for label, value in rows), unsafe_allow_html=True)


def brief_grid(cells):
    html = '<div class="mini-grid">'
    for label, value, source in cells:
        link = f'<a href="{escape(source, quote=True)}" target="_blank" rel="noopener noreferrer">Source</a>' if source else ''
        # Briefs are short; the full supplied text remains accessible by expansion.
        value = str(value)
        short = value if len(value) <= 185 else value[:182].rsplit(" ", 1)[0] + "…"
        more = f'<details><summary>Read full text</summary><p>{escape(value)}</p></details>' if short != value else ''
        html += f'<div class="brief-cell"><b>{escape(label)}</b><p>{escape(short)}</p>{more}{link}</div>'
    st.markdown(html+'</div>', unsafe_allow_html=True)
