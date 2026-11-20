"""FounderRadar: category -> pipeline -> investment workspace."""
from datetime import date
from hashlib import sha256
from html import escape
import json
import os

import streamlit as st

from analyst_store import DECISIONS, load_decisions
from cockpit_data import fund_fit
from cockpit_details import company, suggested_action
from cockpit_service import start_analysis, load_workspace, email_draft
from cockpit_style import theme, kpis, fact_rows
from cockpit_context import market_for
from cockpit_visuals import pipeline_scatter, stage_bars
from models import Industry

PAGES = ["Overview", "Dealflow", "Company Deep Dive", "Activities"]


def status(lead, decisions):
    return decisions.get((lead.namespace, lead.id), {}).get("decision", "Pending Review")


def navigate(page):
    st.session_state.navigation = page


def open_company(identity):
    st.session_state.selected_company = identity
    st.session_state.navigation = "Company Deep Dive"
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1
    st.query_params["company"] = identity


def restart():
    for key in list(st.session_state):
        if key != "table_generation":
            del st.session_state[key]
    st.query_params.clear()


def landing():
    st.markdown('<div class="overline">FounderRadar / New analysis</div>', unsafe_allow_html=True)
    st.title("Choose your investment focus")
    st.write("Select a sector. Sourcing, context research and scoring feed the cockpit automatically.")
    mode = os.getenv("FOUNDERRADAR_MODE", "demo").lower()
    st.caption("DEMO WORKSPACE · Fictional companies and example sources." if mode == "demo" else "LIVE WORKSPACE · Connected research pipeline.")
    a, b = st.columns([1.7, 1], gap="large")
    with a, st.container(border=True):
        sector = st.radio("Sector", list(Industry), format_func=lambda x: x.value)
        st.caption("Germany · Up to 30 companies · Early-stage screening")
        if st.button("Start analysis", type="primary", width="stretch"):
            progress = st.progress(0, text="Starting research")
            try:
                run = start_analysis(sector, lambda p, m: progress.progress(p, text=m))
                st.session_state.cockpit_run = run
                st.session_state.navigation = "Overview"
                st.rerun()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception("Analysis failed")
                st.error("Analysis could not finish. Check the connected sourcing service and server log; then retry.")
                if isinstance(exc, NotImplementedError):
                    st.info("The live sourcing provider is not implemented in this repository yet. The automatic handoff is ready; a provider must return leads first.")
    with b:
        st.markdown("#### Your research workspace")
        st.markdown("**01 · Overview**  \nPriorities, score distribution and next actions.\n\n**02 · Dealflow**  \nCompare, filter and shortlist companies.\n\n**03 · Company Deep Dive**  \nBusiness, team, market, capital and sources.\n\n**04 · Activities**  \nOwners, deadlines, outreach and decision history.")


def table(leads, decisions, key, height=360, activities=False, compact=False):
    rows = []
    for lead in leads:
        saved = decisions.get((lead.namespace, lead.id), {})
        row = {"Company": lead.name, "Quality": lead.scores["Quality"],
               "Confidence": None if lead.confidence is None else lead.confidence * 100,
               "Stage": lead.stage, "Decision": status(lead, decisions),
               "HTGF fit": fund_fit(lead)[0], "Sourcing": "Excluded" if lead.excluded else "In scope"}
        if compact:
            row = {k: row[k] for k in ("Company", "Quality")}
            row["Review signal"] = lead.data.get("value_proposition") or lead.data.get("initial_signal") or "Primary evidence needs review"
        if activities:
            row = {"Company": lead.name, "Next action": saved.get("next_action", ""),
                   "Due": saved.get("due_date", ""), "Owner": saved.get("analyst_name", ""),
                   "Task": saved.get("task_status", "Open"), "Outreach": saved.get("outreach_status", "Not contacted"),
                   "Decision": status(lead, decisions)}
        rows.append(row)
    if not rows:
        return
    signature = sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:12]
    selection = st.dataframe(rows, hide_index=True, width="stretch", height=height,
        on_select="rerun", selection_mode="single-row", key=f"{key}-{signature}-{st.session_state.get('table_generation', 0)}",
        column_config={"Company": st.column_config.TextColumn(width=150 if compact else 170),
                       "Next action": st.column_config.TextColumn(width=260),
                       "Review signal": st.column_config.TextColumn(width=270),
                       "Quality": st.column_config.NumberColumn("Quality / 100", format="%.1f", width=85 if compact else 105),
                       "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%", width=115)})
    if selection.selection.rows:
        st.session_state.pending_company = leads[selection.selection.rows[0]].id
        st.rerun()


def company_picker(leads, key):
    if not leads:
        return
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    selected = a.selectbox("Open company", leads, format_func=lambda x: x.name, key=key, label_visibility="collapsed")
    b.button("Open deep dive", on_click=open_company, args=(selected.id,), key=key+"open", width="stretch")


def tasks(leads, decisions):
    return [(lead, decisions[(lead.namespace, lead.id)]) for lead in leads
            if decisions.get((lead.namespace, lead.id), {}).get("next_action")]


def overdue(saved):
    return bool(saved.get("due_date") and saved["due_date"] < date.today().isoformat() and saved.get("task_status", "Open") == "Open")


def overview(leads, decisions):
    task_rows = tasks(leads, decisions)
    heading, shortcut = st.columns([4, 1], vertical_alignment="center")
    heading.title("Investment overview")
    count_overdue = sum(overdue(s) for _, s in task_rows)
    shortcut.button(f"Review overdue ({count_overdue})", disabled=not count_overdue, on_click=open_overdue, width="stretch")
    pending = [l for l in leads if status(l, decisions) == "Pending Review" and not l.excluded]
    prioritized = sorted(pending, key=lambda l: (not overdue(decisions.get((l.namespace, l.id), {})), -(l.scores["Quality"] if l.scores["Quality"] is not None else -1)))[:5]
    left, middle, right = st.columns([.85, 1.55, 1.1], gap="medium")
    with left:
        with st.container(border=True, key="card-snapshot"):
            st.subheader("Pipeline snapshot")
            st.markdown(f'<div class="snapshot-number">{len(leads)}</div><div class="source-line">Companies in this analysis</div>' + ''.join(
                f'<div class="snapshot-stat"><span>{label}</span><strong>{value}</strong></div>' for label, value in [
                    ("Awaiting review", len(pending)), ("Contact decisions", sum(status(l, decisions) == "Contact" for l in leads)),
                    ("Open actions", sum(s.get("task_status", "Open") == "Open" for _, s in task_rows))]), unsafe_allow_html=True)
        with st.container(border=True, key="card-research"):
            st.subheader("Research coverage")
            fact_rows({"With sources": f"{sum(bool(l.sources) for l in leads)} / {len(leads)}", "Market dossiers": f"{sum(bool(market_for(l)) for l in leads)} / {len(leads)}"})
            st.caption("Available records, not independently verified facts.")
    with middle, st.container(border=True, key="card-queue"):
        st.subheader("Review queue")
        st.caption("Overdue first, then reported quality · select a company")
        if prioritized:
            table(prioritized, decisions, "priority", height=216, compact=True)
            st.markdown("**Review priorities**")
            for lead in prioritized[:2]:
                saved = decisions.get((lead.namespace, lead.id), {})
                st.caption(lead.name + " · " + (saved.get("next_action") or suggested_action(lead)))
        else:
            st.info("No companies awaiting review in sourcing scope.")
            st.button("Browse all companies", on_click=navigate, args=("Dealflow",))
    with right, st.container(border=True, key="card-focus"):
        st.subheader("Company in focus")
        selected = st.selectbox("Open company", prioritized or leads, format_func=lambda x: x.name, key="priority-pick", label_visibility="collapsed")
        st.caption(selected.data.get("value_proposition") or selected.stage)
        detail = selected.data
        fact_rows({"Stage": selected.stage, "Customers": detail.get("customer_count"), "Team": detail.get("team_size"),
                   "Raised": f"€{detail['funding_total_eur']:,.0f}" if detail.get("funding_total_eur") is not None else None})
        saved = decisions.get((selected.namespace, selected.id), {})
        st.markdown("**Next step**")
        st.caption(saved.get("next_action") or suggested_action(selected))
        st.button("Open deep dive", on_click=open_company, args=(selected.id,), key="priority-pickopen", width="stretch", type="primary")
        draft = email_draft(selected)
        if draft:
            st.link_button("Open email draft", draft, width="stretch")
    left, right = st.columns([2.1, 1], gap="medium")
    with left, st.container(border=True, key="card-quality"):
        st.subheader("Quality & evidence")
        st.caption("Each point is a company · grey = excluded by sourcing")
        st.plotly_chart(pipeline_scatter(leads), width="stretch", config={"displayModeBar": False})
        plotted = sum(l.scores["Quality"] is not None and l.confidence is not None for l in leads)
        st.caption(f"{plotted}/{len(leads)} with both measures. Confidence is supplied by scoring.")
    with right, st.container(border=True, key="card-stages"):
        st.subheader("Stage distribution")
        st.plotly_chart(stage_bars(leads), width="stretch", config={"displayModeBar": False})
    with st.container(border=True, key="card-actions"):
        st.subheader("Next actions")
        active = sorted([(l, s) for l, s in task_rows if s.get("task_status", "Open") == "Open"], key=lambda p: p[1].get("due_date") or "9999")[:4]
        if active:
            table([l for l, _ in active], decisions, "upcoming", height=180, activities=True)
        else:
            st.caption("No open follow-ups. Open a company, record a decision and assign the next action.")
        st.button("Open activity tracker", on_click=navigate, args=("Activities",), width="stretch")


def dealflow(leads, decisions):
    st.title("Dealflow")
    view = st.segmented_control("View", ["All companies", "Pending review", "Watchlist", "Decisions", "Sourcing excluded"], default="All companies", key="dealflow-view", label_visibility="collapsed")
    a, b, c = st.columns([2, 1, 1], vertical_alignment="bottom")
    search = a.text_input("Search", placeholder="Company or proposition", key="search")
    stages = b.multiselect("Stage", sorted({l.stage for l in leads}), key="stages")
    with c.popover("More filters", width="stretch"):
        fits = st.multiselect("HTGF fit", ["Potential Fit", "Review Required", "Likely Out of Scope"], key="fits")
        confidence = st.slider("Minimum confidence (%)", 0, 100, 0, key="confidence")
        unknown = st.checkbox("Include unassessed confidence", value=True, key="unknown-confidence")
        statuses = st.multiselect("Decision", ["Pending Review", *DECISIONS], key="statuses")
    shown = [l for l in leads if
             (not search or search.casefold() in f"{l.name} {l.data.get('value_proposition', '')}".casefold())
             and (not stages or l.stage in stages) and (not fits or fund_fit(l)[0] in fits)
             and (not statuses or status(l, decisions) in statuses)
             and ((l.confidence is None and unknown) or (l.confidence is not None and l.confidence * 100 >= confidence))
             and (view != "Watchlist" or status(l, decisions) == "Watchlist")
             and (view != "Pending review" or status(l, decisions) == "Pending Review")
             and (view != "Decisions" or status(l, decisions) != "Pending Review")
             and (view != "Sourcing excluded" or l.excluded)]
    shown.sort(key=lambda l: -(l.scores["Quality"] if l.scores["Quality"] is not None else -1))
    st.caption(f"{len(shown)} / {len(leads)} companies · Select a row to open research · Missing values are unassessed")
    if not shown:
        st.info("No companies in this view. Review the pending queue or reset your filters.")
        st.button("Reset view and filters", on_click=reset_filters)
        return
    table(shown, decisions, "dealflow", height=min(560, len(shown)*35+38))
    company_picker(shown, "dealflow-pick")
    with st.expander("Export this selection"):
        st.download_button("Download source records", json.dumps([l.raw for l in shown], ensure_ascii=False, indent=2), "founderradar-selection.json", "application/json")


def reset_filters():
    for key in ("dealflow-view", "search", "stages", "fits", "confidence", "unknown-confidence", "statuses"):
        st.session_state.pop(key, None)


def activities(leads, decisions):
    st.title("Activities")
    rows = tasks(leads, decisions)
    kpis([("Open actions", sum(s.get("task_status", "Open") == "Open" for _, s in rows), "Assigned next steps"),
          ("Overdue", sum(overdue(s) for _, s in rows), "Needs attention"),
          ("Contacted", sum(decisions.get((l.namespace, l.id), {}).get("outreach_status") in {"Contacted", "Replied", "Meeting scheduled"} for l in leads), "Manually confirmed"),
          ("Completed", sum(s.get("task_status") == "Done" for _, s in rows), "Completed next actions")])
    mode = st.segmented_control("Activity view", ["Open actions", "Overdue", "All tracked", "Completed"], default="Open actions", key="activity-view", label_visibility="collapsed")
    tracked = [l for l in leads if (l.namespace, l.id) in decisions]
    shown = [l for l in tracked if mode == "All tracked" or
             (mode == "Overdue" and overdue(decisions[(l.namespace, l.id)])) or
             (mode == "Open actions" and decisions[(l.namespace, l.id)].get("next_action") and decisions[(l.namespace, l.id)].get("task_status", "Open") == "Open") or
             (mode == "Completed" and decisions[(l.namespace, l.id)].get("next_action") and decisions[(l.namespace, l.id)].get("task_status") == "Done")]
    shown.sort(key=lambda l: decisions[(l.namespace, l.id)].get("due_date") or "9999")
    if shown:
        table(shown, decisions, "activities", height=min(530, 38+len(shown)*35), activities=True)
        company_picker(shown, "activity-pick")
    else:
        st.info("No activities in this view. Open a company to set an owner, due date and next action.")
        st.button("Review companies", on_click=navigate, args=("Dealflow",))
    st.caption("Email opens a draft in your mail client. Sending and replies are recorded manually. Changes are retained in each company's activity history.")


def open_overdue():
    st.session_state.navigation = "Activities"
    st.session_state["activity-view"] = "Overdue"


def main():
    st.set_page_config(page_title="FounderRadar | Investment Cockpit", page_icon="◉", layout="wide")
    theme()
    if "pending_company" in st.session_state:
        open_company(st.session_state.pop("pending_company"))
    with st.sidebar:
        st.markdown('<div class="brand">Founder<span>Radar</span></div><div class="brand-note">INVESTMENT WORKSPACE</div>', unsafe_allow_html=True)
    if "cockpit_run" not in st.session_state:
        landing()
        return
    run = st.session_state.cockpit_run
    leads = load_workspace(run)
    decisions = {(ns, identity): row for ns in {l.namespace for l in leads} for identity, row in load_decisions(ns).items()}
    if "navigation" not in st.session_state:
        st.session_state.navigation = "Overview"
    with st.sidebar:
        page = st.radio("Workspace", PAGES, key="navigation", label_visibility="collapsed")
        st.divider()
        st.caption("ACTIVE RESEARCH")
        st.write(run.criteria.industry.value)
        st.caption(f"Germany · {len(leads)} companies\n\n{run.created_at.strftime('%d %b %Y · %H:%M')} UTC")
        st.button("Change sector", on_click=restart, width="stretch")
        st.caption("Demo data · fictional companies" if run.mode == "demo" else "Live pipeline · evidence-led screening")
        with st.expander("Pipeline status"):
            st.caption(f"{run.discovered_count} sourced → {run.enriched_count} enriched → {len(leads)} scored")
            for issue in run.result.issues:
                st.caption(f"{issue.lead_id}: {issue.message}")
            if not run.result.issues:
                st.caption("Analysis completed without reported errors.")
    st.markdown(f'<div class="workspace-title"><strong>{escape(run.criteria.industry.value)}</strong><span>{"DEMO · fictional data" if run.mode == "demo" else "LIVE"} · {len(leads)} companies · Analysis {run.created_at.strftime("%d %b %Y")}</span></div>', unsafe_allow_html=True)
    if st.session_state.get("decision_saved"):
        st.toast("Saved: " + st.session_state.pop("decision_saved"))
    if not leads:
        st.info("The pipeline returned no scored companies. See pipeline status for unresolved research steps.")
        st.button("Choose another sector", on_click=restart)
        return
    if page == "Company Deep Dive":
        ids = [l.id for l in leads]
        requested = st.session_state.get("selected_company") or st.query_params.get("company")
        selected = st.sidebar.selectbox("Company", ids, index=ids.index(requested) if requested in ids else 0, format_func=lambda identity: next(l.name for l in leads if l.id == identity))
        st.session_state.selected_company = selected
        st.query_params["company"] = selected
        company(next(l for l in leads if l.id == selected), decisions)
    else:
        {"Overview": overview, "Dealflow": dealflow, "Activities": activities}[page](leads, decisions)


if __name__ == "__main__":
    main()
