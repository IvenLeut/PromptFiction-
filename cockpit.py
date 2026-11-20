"""FounderRadar investment cockpit. Run: streamlit run cockpit.py."""
from datetime import date
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

import streamlit as st

from analyst_store import DECISIONS, load_decisions, save_decision
from cockpit_data import CONFIG, fund_fit, items, known, load_payload, url
from cockpit_research import competition, facts, funding, market, sector_research

ROOT = Path(__file__).parent
st.set_page_config(page_title="FounderRadar | Investment Cockpit", page_icon="◉", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
:root {--accent:#e87556;--ink:#182738;}
.stApp {background:#f5f6f8;color:var(--ink);}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stSidebar"] {background:#152536;min-width:230px;max-width:250px;}
[data-testid="stSidebar"] * {color:#e6edf4;}
[data-testid="stSidebar"] input,[data-testid="stSidebar"] textarea {color:#182738;}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {color:#33475a;}
.block-container {padding:2.1rem 2.4rem 3rem;max-width:1700px;}
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {gap:.65rem;}
h1 {font-size:1.9rem!important;font-weight:650!important;letter-spacing:-.04rem;}
h2 {font-size:1.35rem!important;} h3 {font-size:1.08rem!important;}
[data-testid="stMetric"] {padding:14px 16px;background:white;border:1px solid #dce2e8;border-radius:7px;}
[data-testid="stMetricValue"] {font-size:1.55rem;}
[data-testid="stMetricValue"] > div {white-space:normal;overflow:visible;text-overflow:clip;font-size:1.25rem;}
[data-testid="stMetricLabel"] {font-size:.85rem;color:#546477;}
[data-testid="stMetricLabel"] p {white-space:normal;overflow:visible;text-overflow:clip;}
[data-testid="stVerticalBlockBorderWrapper"] {background:white;}
.eyebrow {font-size:.8rem;letter-spacing:.12rem;color:#718095;text-transform:uppercase;margin-bottom:8px;}
.brand {font-size:1.4rem;font-weight:700;letter-spacing:-.05rem;margin:8px 0 0;}
.brand span {color:#f18b6d!important;}
.subbrand {font-size:.8rem;color:#9cabbc!important;margin:0 0 26px;}
.snapshot {border-left:3px solid #e87556;background:#fff5f0;padding:14px 18px;border-radius:3px;margin:10px 0 16px;}
.snapshot b {color:#a34e33;} .snapshot p {margin:5px 0 0;font-size:.95rem;}
.badge {display:inline-block;background:#e8edf2;color:#33475a;padding:4px 9px;border-radius:4px;font-size:.8rem;margin:0 6px 8px 0;}
div[data-testid="stDataFrame"] {border:1px solid #dce2e8;border-radius:6px;}
button[kind="primary"] {background:#db694b;border-color:#db694b;color:white;}
@media(max-width:900px){.block-container{padding:1rem;}h1{font-size:1.6rem!important;}}
</style>""", unsafe_allow_html=True)


def empty(label):
    st.caption(f"{label}: not researched. Import an enriched JSON export to add evidence.")


def status(lead, decisions):
    return decisions.get((lead.namespace, lead.id), {}).get("decision", "Pending Review")


def open_company(identity):
    st.session_state.selected_company = identity
    st.session_state.navigation = "Company Research"
    st.query_params["company"] = identity
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


def score(value, percent=False):
    return "Not assessed" if value is None else f"{value:.0%}" if percent else f"{value:.1f}"


def evidence_view(lead):
    st.subheader("Discovery & Evidence")
    d = lead.data
    st.markdown("#### Discovery timeline")
    timeline = []
    for label, field in (("First public signal", "first_signal_date"), ("Discovered by FounderRadar", "discovered_at"), ("Confirmed incorporation", "founded_on")):
        if d.get(field) and not (field == "founded_on" and d.get("gruendung_ist_proxy")):
            timeline.append({"Date": str(d[field]), "Event": label, "Source": url(d.get("source_url")) if field == "first_signal_date" else None})
    for e in lead.evidence:
        if e["date"] and e["url"]:
            timeline.append({"Date": e["date"], "Event": e["statement"], "Source": e["url"]})
    for event in items(d.get("signals")):
        if isinstance(event, dict) and (event.get("date") or event.get("datum")) and url(event.get("url")):
            timeline.append({"Date": event.get("date") or event.get("datum"), "Event": event.get("evidence") or event.get("zitat") or event.get("type") or event.get("typ"), "Source": url(event.get("url"))})
    timeline = list({json.dumps(row, sort_keys=True): row for row in timeline}.values())
    if timeline:
        st.dataframe(sorted(timeline, key=lambda r: str(r["Date"])), hide_index=True, width="stretch", column_config={"Source": st.column_config.LinkColumn()})
    else:
        empty("Dated public signals")
    if not d.get("discovered_at"):
        st.caption("Engine discovery timestamp unavailable. First public signal is not the engine discovery date.")
    db = d.get("in_databases")
    st.caption("Database coverage: " + ("Unknown; no verified absence." if db is None else "Listed according to sourcing." if db else "Not found in the checked databases according to sourcing; not proof of global absence."))
    if d.get("earliness_delta_monate") is not None:
        st.caption(f"Sourcing interval: {d['earliness_delta_monate']} months from first signal to first database entry or scoring cutoff. Not an engine lead-time measurement.")
    st.markdown("#### Evidence explorer")
    category = st.multiselect("Evidence category", ["Team", "Market", "Risk", "Stage", "Other"], key=lead.id+"categories")
    rows = [e for e in lead.evidence if not category or e["category"] in category]
    st.dataframe(rows, hide_index=True, width="stretch", column_config={"url": st.column_config.LinkColumn("Source"), "points": st.column_config.NumberColumn("Scoring points", help="Original scoring input. Unsourced 50-point inputs are neutral defaults, not measurements.")})
    coverage = len({e["criterion"] for e in lead.evidence if e["url"]})
    total = len({e["criterion"] for e in lead.evidence})
    a, b, c = st.columns(3)
    a.metric("Criteria with source", f"{coverage} / {total}")
    b.metric("Distinct source URLs", len(lead.sources))
    c.metric("Evidence confidence", score(lead.confidence, True))
    dates = [str(e["date"]) for e in lead.evidence if e["date"]]
    st.caption(f"Latest dated evidence: {max(dates) if dates else 'Not supplied'}. URL coverage does not establish independent verification.")
    if d.get("match_confidence") is not None:
        st.write("Entity match confidence supplied by sourcing:", d["match_confidence"])
    for question in items(d.get("open_questions")):
        st.write("• " + str(question))
    with st.expander("Original score inputs and untouched source record"):
        st.json(lead.raw)


def decision_panel(lead, decisions):
    saved = decisions.get((lead.namespace, lead.id), {})
    with st.container(border=True):
        st.subheader("Analyst Decision")
        st.caption("Machine: " + lead.recommendation)
        st.markdown("**" + status(lead, decisions) + "**")
        key = lead.namespace + lead.id
        with st.form("decision-" + key):
            decision = st.radio("Decision", DECISIONS, index=DECISIONS.index(saved.get("decision", "Watchlist")), horizontal=True)
            reason = st.text_area("Reason for decision", value=saved.get("reason", ""), height=85)
            notes = st.text_area("Analyst notes", value=saved.get("notes", ""), height=100)
            action = st.text_input("Next action", value=saved.get("next_action", ""))
            analyst = st.text_input("Analyst name (optional)", value=saved.get("analyst_name", ""))
            submit = st.form_submit_button("Save decision", type="primary", width="stretch")
        if submit:
            try:
                save_decision(lead.namespace, lead.id, decision, notes, reason, action, analyst)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.decision_saved = lead.name
                st.rerun()
        if saved:
            st.caption("Saved " + saved["updated_at"][:19] + " UTC")
        st.caption("Independent analyst judgement. Decisions persist locally; no emails are sent.")


def overview(lead, decisions):
    d = lead.data
    left, right = st.columns([2.6, 1], gap="large")
    with right:
        decision_panel(lead, decisions)
    with left:
        st.markdown("#### Investment view")
        reliable = bool(lead.sources) and (lead.confidence is None or lead.confidence >= .3)
        if reliable:
            st.write(d.get("investment_thesis") or "Investment thesis not supplied.")
        else:
            st.info("Insufficient evidence for an investment briefing. Review the source record and resolve open questions first.")
        why = d.get("why_contact_now")
        if why and reliable:
            # Keep supplied text; cap to two sentences without inventing an argument.
            import re
            summary = " ".join(re.split(r"(?<=[.!?])\s+", str(why))[:2])
            st.markdown(f'<div class="snapshot"><b>Why contact now?</b><p>{escape(summary)}</p></div>', unsafe_allow_html=True)
        else:
            empty("Why contact now")
        cols = st.columns(4)
        cols[0].metric("Quality / 100", score(lead.scores["Quality"]))
        cols[1].metric("HTGF fit", {"Review Required": "Review", "Potential Fit": "Potential", "Likely Out of Scope": "Out of scope"}[fund_fit(lead)[0]])
        if lead.scores["Earliness"] is None and d.get("earliness_delta_monate") is not None:
            cols[2].metric("Sourcing interval", f"{d['earliness_delta_monate']} mo.", help="First public signal to first database entry or scoring cutoff. Not the engine discovery lead time.")
        else:
            cols[2].metric("Earliness / 100", score(lead.scores["Earliness"]))
        cols[3].metric("Confidence", score(lead.confidence, True))
        st.caption(" · ".join(f"{label}: {score(lead.scores[label])}" for label in ("Market", "Team", "Risk")) + " · Scores / 100; higher risk = worse.")
        for warning in lead.warnings:
            st.warning(warning)
        strengths = sorted([e for e in lead.evidence if e["url"] and e["category"] in {"Team", "Market"}], key=lambda e: -(e["points"] or 0))[:3]
        risks = sorted([e for e in lead.evidence if e["url"] and e["category"] == "Risk" and (e["points"] is None or e["points"] >= 50)], key=lambda e: -(e["points"] or 0))[:3]
        a, b = st.columns(2)
        with a:
            st.markdown("#### Reasons to contact")
            if reliable and strengths:
                for e in strengths:
                    st.write("• " + e["statement"])
                    st.link_button("Evidence · " + e["criterion"], e["url"])
            else:
                empty("Evidence-backed contact arguments")
        with b:
            st.markdown("#### Key risks")
            if d.get("ausschluss_grund"):
                st.error(d["ausschluss_grund"])
            if risks:
                for e in risks:
                    st.write("• " + e["statement"])
                    st.link_button("Evidence · " + e["criterion"], e["url"])
            elif d.get("risks"):
                for risk in items(d["risks"])[:3]:
                    st.write("• " + str(risk))
            else:
                empty("Risk assessment")
        with st.expander("HTGF fund fit — criterion-level assessment", expanded=False):
            st.dataframe(fund_fit(lead)[1], hide_index=True, width="stretch")
            st.caption(f"{CONFIG['disclaimer']} Version {CONFIG['version']}. Scope: {CONFIG['scope']}.")
            st.link_button("Official criteria", CONFIG["source"])
    st.divider()
    a, b, c = st.columns(3)
    with a:
        st.markdown("#### Founders")
        profiles = d.get("founder_profiles") or []
        if profiles:
            st.dataframe(profiles, hide_index=True, width="stretch")
        elif d.get("founders"):
            for name in d["founders"]:
                st.write(str(name))
            st.caption("Roles, relevant experience and founder-market fit require further research.")
        else:
            empty("Founder research")
    with b:
        st.markdown("#### Business")
        facts({"Customer problem": d.get("problem_statement") or d.get("customer_problem"),
               "Product": d.get("product_mechanics") or d.get("solution") or d.get("produktbeschreibung"),
               "Target customers": d.get("target_customers"), "Business model": d.get("business_model"),
               "Advantage": d.get("differentiation") or d.get("technology_advantage")})
    with c:
        st.markdown("#### Traction")
        facts({"Product maturity": d.get("product_stage") or d.get("product_maturity"),
               "Customers": d.get("customer_count"), "Pilots / partners": d.get("traction_notes"),
               "Funding": d.get("funding_status") or d.get("funding_stage"), "Next milestone": d.get("next_milestone")})
    sector_research(lead)


def company(lead, decisions):
    d = lead.data
    st.caption("COMPANY RESEARCH / " + lead.sector.upper())
    st.title(lead.name)
    st.write(d.get("value_proposition") or "Value proposition not researched.")
    year = d.get("gruendungsjahr") or d.get("founding_year")
    badges = [lead.sector, d.get("location"), lead.stage, fund_fit(lead)[0], status(lead, decisions)]
    if year:
        badges.append(f"{'Proxy year' if d.get('gruendung_ist_proxy') else 'Founded'}: {year}")
    st.markdown("".join(f'<span class="badge">{escape(str(x))}</span>' for x in badges if x), unsafe_allow_html=True)
    st.caption(f"Data as of {d.get('stichtag') or d.get('updated_at') or 'not supplied'} · {len(lead.sources)} source URLs supplied · {'DEMO — fictional company and sources' if lead.demo else 'Sources not independently verified'}")
    if lead.excluded:
        st.warning("Sourcing exclusion: " + str(d.get("ausschluss_grund") or d.get("noise_class") or d.get("hard_exclusions")) + ". Analyst decision remains independent.")
    a, b, _ = st.columns([1, 2, 3])
    if url(d.get("website")):
        a.link_button("Company website", url(d["website"]))
    email = d.get("email") or d.get("contact_email")
    if email:
        b.write("Contact: " + str(email))
    tabs = st.tabs(["Investment Overview", "Market Intelligence", "Competition", "Funding & Valuation", "Discovery & Evidence"])
    with tabs[0]:
        overview(lead, decisions)
    with tabs[1]:
        market(lead)
    with tabs[2]:
        competition(lead)
    with tabs[3]:
        funding(lead)
    with tabs[4]:
        evidence_view(lead)


def pipeline(leads, decisions, page):
    st.markdown('<div class="eyebrow">FounderRadar / Investment workspace</div>', unsafe_allow_html=True)
    st.title("Investment Pipeline" if page == "Dealflow" else page)
    dates = sorted({str(l.data.get("stichtag") or l.data.get("updated_at")) for l in leads if l.data.get("stichtag") or l.data.get("updated_at")})
    st.caption(f"Data as of {', '.join(dates) if dates else 'not supplied'} · {len(leads)} loaded leads · HTGF initial investment screening")
    for col, label, value in zip(st.columns(4), ["Total Leads", "Potential HTGF Fits", "Pending Review", "Contact Candidates"],
            [len(leads), sum(fund_fit(l)[0] == "Potential Fit" for l in leads), sum(status(l, decisions) == "Pending Review" for l in leads), sum(status(l, decisions) == "Contact" for l in leads)]):
        col.metric(label, value)
    st.caption("KPIs cover the loaded dataset. Contact Candidates are saved analyst Contact decisions.")
    a, b, c = st.columns([2, 1, 1])
    search = a.text_input("Search companies", placeholder="Company, proposition or sector")
    sectors = b.multiselect("Sector", sorted({l.sector for l in leads}))
    stages = c.multiselect("Stage", sorted({l.stage for l in leads}))
    with st.expander("Screening filters and table columns"):
        a, b, c = st.columns(3)
        fit = a.multiselect("HTGF fit", ["Potential Fit", "Review Required", "Likely Out of Scope"])
        statuses = b.multiselect("Analyst status", ["Pending Review", *DECISIONS])
        confidence = c.slider("Minimum confidence (%)", 0, 100, 0)
        include_unknown = st.checkbox("Include unassessed confidence", value=True)
        noise = st.radio("Sourcing relevance", ["All leads", "Relevant only", "Excluded only"], horizontal=True)
        extra = st.checkbox("Show additional columns", value=False)
        sort_by = st.selectbox("Sort by", ["Quality (descending)", "Confidence (descending)", "Company name"])
    shown = []
    for lead in leads:
        current = status(lead, decisions)
        if page == "Watchlist" and current != "Watchlist" or page == "Screening Decisions" and current == "Pending Review":
            continue
        if search.casefold() not in f"{lead.name} {lead.data.get('value_proposition')} {lead.sector}".casefold():
            continue
        if sectors and lead.sector not in sectors or stages and lead.stage not in stages or statuses and current not in statuses:
            continue
        if fit and fund_fit(lead)[0] not in fit:
            continue
        if lead.confidence is None and not include_unknown or lead.confidence is not None and lead.confidence * 100 < confidence:
            continue
        if noise == "Relevant only" and lead.excluded or noise == "Excluded only" and not lead.excluded:
            continue
        shown.append(lead)
    shown.sort(key=lambda l: l.name.casefold() if sort_by == "Company name" else (-(l.confidence if l.confidence is not None else -1) if sort_by.startswith("Confidence") else -(l.scores["Quality"] if l.scores["Quality"] is not None else -1), l.name))
    rows = []
    for lead in shown:
        saved = decisions.get((lead.namespace, lead.id), {})
        row = {"Company": lead.name, "Value Proposition": lead.data.get("value_proposition"), "Sector": lead.sector,
               "Stage": lead.stage, "HTGF Fit": fund_fit(lead)[0], "Quality": lead.scores["Quality"],
               "Confidence": lead.confidence * 100 if lead.confidence is not None else None,
               "Analyst Status": status(lead, decisions), "Sourcing": "Excluded" if lead.excluded else "Not excluded"}
        if extra:
            row.update({"Location": lead.data.get("location"), "First Signal": lead.data.get("first_signal_date"),
                        "Machine Recommendation": lead.recommendation, "Data": "Demo" if lead.demo else "Imported"})
        if page in {"Watchlist", "Screening Decisions"}:
            row.update({"Decision reason": saved.get("reason"), "Next action": saved.get("next_action"), "Analyst": saved.get("analyst_name"), "Updated": saved.get("updated_at")})
        rows.append(row)
    st.markdown(f"#### {len(shown)} companies")
    st.caption("Select a row to open research. Click a column header to sort. Missing numeric values mean Not assessed.")
    signature = sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]
    if not rows:
        st.info("No companies match this view. Adjust filters or save an analyst decision.")
        return
    selection = st.dataframe(rows, hide_index=True, width="stretch", height=min(600, 38 + len(rows) * 36),
                            on_select="rerun", selection_mode="single-row", key=f"dealflow-{signature}-{st.session_state.get('table_generation', 0)}",
                            column_order=["Company", "Quality", "Confidence", "HTGF Fit", "Analyst Status", "Sourcing", "Sector", "Stage", "Value Proposition"] + (["Location", "First Signal", "Machine Recommendation", "Data"] if extra else []) + (["Decision reason", "Next action", "Analyst", "Updated"] if page in {"Watchlist", "Screening Decisions"} else []),
                            column_config={"Value Proposition": st.column_config.TextColumn(width=250),
                            "Quality": st.column_config.NumberColumn("Quality / 100", format="%.1f"),
                            "Confidence": st.column_config.ProgressColumn("Confidence (%)", min_value=0, max_value=100, format="%.0f%%")})
    if selection.selection.rows:
        st.session_state.pending_company = shown[selection.selection.rows[0]].id
        st.rerun()
    pick, button = st.columns([4, 1])
    selected = pick.selectbox("Company profile", shown, format_func=lambda l: l.name)
    button.button("Open research", on_click=open_company, args=(selected.id,), width="stretch")
    st.download_button("Export filtered source records", json.dumps([l.raw for l in shown], ensure_ascii=False, indent=2), "founderradar-selection.json", "application/json")


def main():
    if "pending_company" in st.session_state:
        open_company(st.session_state.pop("pending_company"))
    if "navigation" not in st.session_state:
        st.session_state.navigation = "Company Research" if st.query_params.get("company") else "Dealflow"
    with st.sidebar:
        st.markdown('<div class="brand">Founder<span>Radar</span></div><div class="subbrand">INVESTMENT COCKPIT · 2.0</div>', unsafe_allow_html=True)
        page = st.radio("Workspace", ["Dealflow", "Company Research", "Watchlist", "Screening Decisions"], key="navigation", label_visibility="collapsed")
        st.divider()
        st.caption("DATA WORKSPACE")
        uploaded = st.file_uploader("Import scores / analysis JSON", type=["json"])
        st.caption("JSON imports replace the displayed dataset. Original files and saved decisions are retained.")
        st.divider()
        st.caption("HTGF · Early-stage mandate")
        st.caption("Research supports a decision. Evidence quality remains visible throughout.")
    try:
        if uploaded:
            payload = json.loads(uploaded.getvalue().decode("utf-8-sig"))
            name = uploaded.name
        else:
            path = Path(os.environ.get("FOUNDERRADAR_SCORES", ROOT / "examples/scoring/scores.json"))
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            name = path.name
        leads = load_payload(payload)
    except (ValueError, OSError, UnicodeError) as exc:
        st.error(f"Unable to load data: {exc}")
        st.stop()
    if not leads:
        st.info("No leads in the imported dataset.")
        st.stop()
    decisions = {(ns, identity): row for ns in {l.namespace for l in leads} for identity, row in load_decisions(ns).items()}
    if st.session_state.get("decision_saved"):
        st.success("Decision saved for " + st.session_state.pop("decision_saved"))
    demo_count = sum(l.demo for l in leads)
    if demo_count:
        st.caption(f"DEMO DATA · {demo_count} of {len(leads)} companies are fictional. Example sources are not verified evidence. Dataset: {name}")
    if page == "Company Research":
        ids = [l.id for l in leads]
        requested = st.session_state.get("selected_company") or st.query_params.get("company")
        if requested and requested not in ids:
            st.warning("Selected company is not in this dataset. Select another company.")
        selected = st.sidebar.selectbox("Research company", ids, index=ids.index(requested) if requested in ids else 0, format_func=lambda identity: next(l.name for l in leads if l.id == identity))
        st.session_state.selected_company = selected
        st.query_params["company"] = selected
        company(next(l for l in leads if l.id == selected), decisions)
    else:
        pipeline(leads, decisions, page)


main()
