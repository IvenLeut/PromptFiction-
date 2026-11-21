"""A restrained research terminal: compact grids, explicit hierarchy, no hero banners."""
from html import escape
import streamlit as st


def theme():
    st.markdown("""<style>
    :root{--ink:#282623;--muted:#68645e;--line:#dedbd5;--paper:#f3f1ed;--peach:#fbd7c3;--rose:#efdce1;--lemon:#f2f3d8;--cyan:#d9f2f2}
    .stApp{background:var(--paper);color:var(--ink)}
    [data-testid="stHeader"],[data-testid="stToolbar"]{display:none!important}
    [data-testid="stSidebar"]{background:#e8e5df;min-width:205px;max-width:220px;border-right:1px solid #d8d4ce}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.65rem}
    [data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:1rem}
    [data-testid="stSidebarUserContent"]{padding:1rem 1.1rem 1.5rem!important}
    [data-testid="stSidebar"] label[data-baseweb="radio"]{padding:10px 8px;border-radius:11px;margin:2px 0;width:100%}
    [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked){background:var(--ink);color:white}
    [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) p{color:white}
    [data-testid="stMainBlockContainer"]{padding:1.25rem 1.5rem 2rem!important;max-width:1800px}
    [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"]{gap:.65rem}
    h1{font-size:1.85rem!important;letter-spacing:-.05rem;font-weight:650!important;padding:.2rem 0 .55rem!important}
    h2{font-size:1.25rem!important}h3{font-size:1.05rem!important;letter-spacing:-.015rem}h4{font-size:1rem!important}
    p{font-size:1rem;line-height:1.5}
    [data-testid="stCaptionContainer"] p{font-size:.8rem;color:var(--muted);line-height:1.5}
    [data-testid="stVerticalBlockBorderWrapper"]{border-radius:16px!important;border-color:var(--line)!important}
    [class*="st-key-card-"]{background:#fffdfa!important;border-radius:16px}
    .st-key-card-snapshot{background:linear-gradient(145deg,var(--peach),var(--rose))!important}
    .st-key-card-focus{background:linear-gradient(155deg,#fffdfa,var(--cyan))!important}
    .st-key-card-research{background:var(--lemon)!important}
    [data-testid="stMetric"]{padding:10px 12px;background:#fffdfa;border:1px solid var(--line);border-radius:12px}
    [data-testid="stMetricValue"]{font-size:1.35rem}[data-testid="stMetricValue"]>div{white-space:normal}
    [data-testid="stMetricLabel"] p{white-space:normal;font-size:.875rem}
    [data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px}
    [data-baseweb="tab-list"]{gap:1.3rem;border-bottom:1px solid var(--line)}
    button[data-baseweb="tab"]{font-size:.875rem;padding:.2rem 0 .6rem}
    button[kind="primary"]{background:var(--ink);border-color:var(--ink);color:white}
    button[kind="primary"]:hover{background:#48443f;border-color:#48443f}
    button,[data-baseweb="select"]>div{border-radius:10px!important}
    .brand{font-size:1.35rem;font-weight:750;letter-spacing:-.05rem;margin:8px 0 3px}.brand span{color:var(--ink)}
    .brand-note{font-size:.75rem;letter-spacing:.09rem;color:var(--muted);margin-bottom:26px}
    .overline{font-size:.75rem;letter-spacing:.1rem;color:var(--muted);text-transform:uppercase}
    .workspace-title{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:0 0 10px;border-bottom:1px solid var(--line);padding-bottom:12px}
    .workspace-title strong{font-size:1rem}.workspace-title span{font-size:.8rem;color:var(--muted)}
    .kpi-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:8px 0 12px}
    .kpi-cell{background:#fffdfa;border:1px solid var(--line);border-radius:14px;padding:13px 16px}
    .kpi-cell:nth-child(1){background:var(--peach)}.kpi-cell:nth-child(2){background:var(--lemon)}.kpi-cell:nth-child(3){background:var(--cyan)}.kpi-cell:nth-child(4){background:var(--rose)}
    .kpi-label{font-size:.875rem;color:#514d47}.kpi-value{font-size:1.6rem;line-height:1.5;font-weight:650;letter-spacing:-.04rem}.kpi-note{font-size:.75rem;color:#5f5b55}
    .mini-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:4px 0 10px}
    .brief-cell{background:#f6f4f0;border:1px solid #e7e2da;padding:13px 14px;border-radius:12px;min-width:0}
    .brief-cell b{display:block;font-size:.8rem;color:#5f5b55;margin-bottom:6px}.brief-cell p{font-size:1rem;line-height:1.5;margin:0;overflow-wrap:anywhere}.brief-cell a{font-size:.8rem;color:var(--ink);text-decoration:underline}
    .decision-callout{background:var(--cyan);padding:14px 16px;border-radius:12px;margin:4px 0 10px}
    .decision-callout b{font-size:.75rem;letter-spacing:.05rem}.decision-callout p{font-size:1rem;margin:6px 0 0}
    .badge{font-size:.8rem;background:#e9e5df;color:var(--ink);border-radius:20px;padding:4px 10px;display:inline-block;margin:0 5px 5px 0}
    .warning-badge{background:var(--peach)}
    .fact-row{display:grid;grid-template-columns:minmax(100px,34%) 1fr;padding:9px 0;border-bottom:1px solid var(--line);font-size:.94rem;gap:12px}.fact-row span{color:var(--muted)}.fact-row strong{font-weight:500;overflow-wrap:anywhere}
    .research-row{display:grid;grid-template-columns:minmax(110px,28%) 1fr;gap:16px;padding:12px 0;border-bottom:1px solid var(--line);font-size:1rem;overflow-wrap:anywhere}.research-row>span{font-size:.875rem;color:var(--muted)}
    .research-row small{display:block;font-size:.75rem;color:var(--muted);margin-top:5px}.research-row a,.source-line a{color:var(--ink);text-decoration:underline}
    .source-line{font-size:.75rem;line-height:1.6;color:var(--muted)}
    .snapshot-number{font-size:2.55rem;line-height:1.3;font-weight:650;letter-spacing:-.08rem;margin:7px 0}
    .snapshot-stat{display:flex;justify-content:space-between;align-items:center;border-top:1px solid #cfc3b9;padding:9px 0;font-size:.875rem;gap:8px}.snapshot-stat strong{font-size:1.05rem}
    .focus-name{font-size:1.2rem;font-weight:650;line-height:1.3;margin:2px 0 8px}
    .section-label{font-size:.875rem;font-weight:650;margin:0 0 4px}
    @media(max-width:1100px){[data-testid="stMainBlockContainer"]{padding-left:1rem!important;padding-right:1rem!important}.research-row{grid-template-columns:1fr;gap:3px}}
    @media(max-width:950px){[data-testid="stHeader"]{display:block!important;background:var(--paper)!important;height:2.5rem!important}[data-testid="stMainBlockContainer"]{padding-top:3rem!important}.mini-grid{grid-template-columns:1fr}.workspace-title{flex-wrap:wrap}}
    @media(max-width:600px){.kpi-strip{grid-template-columns:1fr 1fr}.kpi-cell{padding:10px}.kpi-value{font-size:1.3rem}}
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
        def display(value):
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, list):
                return "; ".join(display(item) for item in value)
            if isinstance(value, dict):
                return str(value["value"]) if "value" in value else "; ".join(f"{key.replace('_', ' ')}: {display(item)}" for key, item in value.items() if known(item))
            return str(value)
        st.markdown(''.join(f'<div class="fact-row"><span>{escape(label)}</span><strong>{escape(display(value))}</strong></div>' for label, value in rows), unsafe_allow_html=True)


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
