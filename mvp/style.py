"""Independent FounderRadar design for the local cockpit."""
import streamlit as st


def apply_theme():
    st.markdown("""
<style>
:root{--ink:#171b19;--muted:#52615b;--line:#e4e9e6;--mint:#e9f4ef;--accent:#17624d}
.stApp{background:#fff;color:var(--ink)}
[data-testid="stHeader"]{background:rgba(255,255,255,.94)}
[data-testid="stToolbar"] button:not([data-testid="stExpandSidebarButton"]){display:none!important}
[data-testid="stMainBlockContainer"]{max-width:1240px;padding:3.6rem 2.6rem 3rem}
[data-testid="stSidebar"]{background:#f7f9f8;border-right:1px solid var(--line)}
[data-testid="stSidebarUserContent"]{padding:1.35rem 1rem}
[data-testid="stSidebar"] label p{font-size:.94rem}
[data-testid="stSidebar"] label:has(input:checked){background:var(--mint);border-radius:10px;padding:.35rem .55rem}
[data-testid="stCaptionContainer"] p{color:var(--muted);line-height:1.45}
[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--line);border-radius:18px}
[data-testid="stMetric"]{border:1px solid var(--line);padding:.85rem 1rem;border-radius:16px;background:#fafcfb}
[data-testid="stMetricValue"]{font-size:1.65rem}
[data-testid="stMetricLabel"] p{color:var(--muted)}
h1{font-size:clamp(2.2rem,4.3vw,4rem)!important;letter-spacing:-.055em!important;line-height:1.06!important}
h2,h3{letter-spacing:-.025em!important}
button[kind="primary"],button[kind="primaryFormSubmit"]{background:#17241f;border-color:#17241f;color:#fff;border-radius:100px}
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover{background:#26433a;border-color:#26433a;color:#fff}
a.fr-mail{display:inline-block;border-radius:100px;background:#17241f;color:#fff!important;text-decoration:none!important;
padding:.6rem 1.1rem;font-weight:600}
.fr-brand{font-size:1.35rem;letter-spacing:-.045em;font-weight:750;margin-bottom:.2rem}
.fr-brand span{color:var(--accent)}
.fr-kicker{font-size:.73rem;text-transform:uppercase;letter-spacing:.11em;color:var(--accent);font-weight:700}
.fr-brief{padding:1.15rem 1.4rem;background:#eff7f2;border:1px solid #daeae1;border-radius:18px;overflow-wrap:anywhere}
.fr-brief h3{margin:.2rem 0 .4rem!important}
.fr-brief p,.fr-brief h3{color:#172a22}
.fr-brief p{margin:0;font-size:1rem}
.fr-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,155px),1fr));gap:12px;margin:.2rem 0 .7rem}
.fr-kpi{padding:1rem 1.1rem;border-radius:16px;border:1px solid var(--line);min-width:0}
.fr-kpi span,.fr-kpi small{display:block;color:#425750;font-size:.82rem;overflow-wrap:anywhere}
.fr-kpi strong{display:block;font-size:1.66rem;margin:.15rem 0;line-height:1.22;overflow-wrap:anywhere}
.fr-good{background:#e8f5ee;color:#144639}
.fr-watch{background:#fff3db;color:#654514}
.fr-neutral{background:#f0f4f2;color:#35433e}
.fr-candidate-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.4rem;flex-wrap:wrap}
.fr-candidate-head b{overflow-wrap:anywhere}
.fr-candidate p{font-size:.91rem;margin:.5rem 0 0;overflow-wrap:anywhere}
.fr-pills{display:flex;flex-wrap:wrap;gap:.36rem}
.fr-pill{font-size:.76rem;font-weight:700;padding:.24rem .58rem;border-radius:99px;white-space:nowrap}
.fr-sector{font-size:.81rem;color:var(--muted)}
.fr-findings{padding:.75rem 1rem;border-radius:14px;height:100%;overflow-wrap:anywhere}
.fr-findings h4{padding:0;margin:0 0 .4rem}
.fr-findings ul{margin:0;padding-left:1.15rem;font-size:.91rem}
.fr-findings li+li{margin-top:.32rem}
.fr-source{color:#155845!important;font-size:.76rem;margin-left:.35rem;font-weight:700;text-decoration:underline}
@media(max-width:720px){[data-testid="stMainBlockContainer"]{padding:3.3rem 1rem 2rem}
.fr-brief{padding:.9rem 1rem}[data-testid="stMetric"]{padding:.55rem .65rem}}
@media(max-width:540px){.fr-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
.fr-kpi{padding:.72rem}.fr-kpi strong{font-size:1.2rem}.fr-candidate-head{display:block}.fr-pills{margin:.35rem 0}}
</style>
""", unsafe_allow_html=True)
