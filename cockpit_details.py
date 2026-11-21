"""Company workspace: a short decision brief, then purpose-specific research tabs."""
from datetime import date
from html import escape
import json

import streamlit as st

from analyst_store import DECISIONS, OUTREACH, load_history, save_decision, save_activity
from cockpit_data import CONFIG, fund_fit, items, known, url
from cockpit_research import competition, funding, market, sector_research
from cockpit_service import email_draft
from cockpit_style import brief_grid, fact_rows, kpis
from cockpit_visuals import score_profile, evidence_coverage
from cockpit_context import context_for, market_for, claim_text, measure_label, present
from cockpit_research_v2 import fields as research_fields, traction as research_traction, sources_note


def text(value, fallback="Not researched"):
    if not known(value):
        return fallback
    if isinstance(value, list):
        return "; ".join(str(x) for x in value)
    return str(value)


def score(value, percent=False):
    return "Unassessed" if value is None else f"{value:.0%}" if percent else f"{value:.1f}"


def suggested_action(lead):
    if lead.excluded:
        return "Review the sourcing exclusion before considering outreach."
    questions = items(lead.data.get("open_questions") or lead.data.get("research_questions"))
    if questions:
        return str(questions[0])
    if not lead.sources or lead.confidence is None or lead.confidence < .3:
        return "Verify the company and its primary evidence before making a contact decision."
    if not lead.data.get("founder_profiles"):
        return "Research the founders' roles and relevant experience."
    return "Validate customer traction and decide whether to request an introductory call."


def decision_editor(lead, saved):
    key = lead.namespace + lead.id
    with st.form("decision-" + key):
        st.caption("Machine assessment: " + lead.recommendation)
        decision = st.radio("Decision", DECISIONS, index=DECISIONS.index(saved["decision"]) if saved.get("decision") in DECISIONS else 1, horizontal=True)
        reason = st.text_area("Reason for decision", value=saved.get("reason", ""), height=72)
        action = st.text_input("Next action", value=saved.get("next_action", ""))
        a, b = st.columns(2)
        owner = a.text_input("Owner", value=saved.get("analyst_name", ""))
        due = b.date_input("Due date", value=date.fromisoformat(saved["due_date"]) if saved.get("due_date") else None)
        a, b = st.columns(2)
        outreach = a.selectbox("Outreach status", OUTREACH, index=OUTREACH.index(saved.get("outreach_status", "Not contacted")))
        task = b.selectbox("Task status", ["Open", "Done"], index=int(saved.get("task_status") == "Done"))
        notes = st.text_area("Analyst notes", value=saved.get("notes", ""), height=72)
        submit = st.form_submit_button("Save decision & activity", type="primary", width="stretch")
    if submit:
        try:
            save_decision(lead.namespace, lead.id, decision, notes, reason, action, owner,
                          due_date=due.isoformat() if due else "", outreach_status=outreach, task_status=task)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.decision_saved = lead.name
            st.rerun()
    st.caption("Outreach status is manual. Opening an email draft does not mark a company as contacted.")


def activity_editor(lead, saved):
    with st.form("activity-" + lead.namespace + lead.id):
        st.caption("Plan a follow-up while keeping the investment decision unchanged.")
        action = st.text_input("Action", value=saved.get("next_action", ""))
        owner = st.text_input("Assigned to", value=saved.get("analyst_name", ""))
        due = st.date_input("Deadline", value=date.fromisoformat(saved["due_date"]) if saved.get("due_date") else None)
        outreach = st.selectbox("Contact stage", OUTREACH, index=OUTREACH.index(saved.get("outreach_status", "Not contacted")))
        task = st.selectbox("Progress", ["Open", "Done"], index=int(saved.get("task_status") == "Done"))
        submit = st.form_submit_button("Save next step", type="primary", width="stretch")
    if submit:
        try:
            save_activity(lead.namespace, lead.id, action, owner, due.isoformat() if due else "", outreach, task)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.decision_saved = lead.name
            st.rerun()


def brief(lead, saved):
    d = lead.data
    fit = fund_fit(lead)[0]
    operational_kpis(lead)
    st.caption(f"Quality {score(lead.scores['Quality'])}/100 · Risk {score(lead.scores['Risk'])}/100 · Evidence confidence {score(lead.confidence, True)} · {fit}")
    left, right = st.columns([2, 1], gap="medium")
    with left, st.container(border=True, key="card-brief"):
        st.subheader("Investment brief")
        reliable = bool(lead.sources) and (lead.confidence is None or lead.confidence >= .3)
        founders = d.get("founder_profiles") or []
        team = "; ".join(f"{p.get('name', '')}: {p.get('relevant_experience') or p.get('background') or p.get('qualifications') or 'experience not researched'}" for p in founders if isinstance(p, dict))
        market_evidence = next((e for e in lead.evidence if e["category"] == "Market" and e["url"]), None)
        risk_evidence = next((e for e in lead.evidence if e["category"] == "Risk" and e["url"] and (e["points"] is None or e["points"] >= 50)), None)
        risk = d.get("ausschluss_grund") or d.get("hard_exclusions") or (risk_evidence["statement"] if risk_evidence else None) or d.get("risks")
        from dashboard import plain_thesis
        brief_grid([
            ("Why this company?", text(plain_thesis(d.get("investment_thesis"))) if reliable else "Insufficient evidence for an investment thesis.", None),
            ("Main risk", text(risk, "No supported risk assessment supplied."), risk_evidence["url"] if risk_evidence and risk == risk_evidence["statement"] else None),
            ("Why this team?", team or (text(d.get("founders")) + ". Relevant experience needs verification." if d.get("founders") else "Founder background not researched."), None),
            ("Why this market?", market_evidence["statement"] if market_evidence else text(d.get("target_market") or d.get("market"), "Market opportunity not researched."), market_evidence["url"] if market_evidence else None),
            ("Why now?", text(d.get("why_contact_now"), "No evidence-backed timing argument supplied.") if reliable else "Resolve the evidence gaps before outreach.", None),
            ("Next diligence step", suggested_action(lead), None)])
        if lead.warnings:
            with st.expander(f"Scoring caveats ({len(lead.warnings)})"):
                for warning in lead.warnings:
                    st.caption(warning)
        with st.expander("Supporting assessment"):
            fact_rows({"Investment rationale": plain_thesis(d.get("investment_thesis")), "Score drivers": d.get("score_drivers"),
                       "Strengths": d.get("strengths"), "Risks": d.get("risks"),
                       "Timing rationale": d.get("why_contact_now"), "Earliness score": d.get("earliness_score"),
                       "Company score": d.get("company_score"), "Technology score": d.get("technology_score"),
                       "Fund-fit score": d.get("fund_fit_score"), "Stage reasoning": d.get("stage_reasoning"),
                       "Fund-fit rationale": d.get("fund_fit_rationale"), "Team rationale": d.get("team_rationale"),
                       "Earliness rationale": d.get("earliness_rationale")})
            for key, label in (("key_strengths", "Strength"), ("key_risks", "Risk")):
                for argument in items(d.get(key)):
                    if isinstance(argument, dict):
                        st.write(f"**{label}:** {argument.get('statement', '')}")
                        st.caption(argument.get("rationale", ""))
                    else:
                        st.write(f"**{label}:** {argument}")
            if d.get("score_rationales"):
                fact_rows({k.replace("_", " ").title(): v for k, v in d["score_rationales"].items()})
    with right, st.container(border=True, key="card-next"):
        st.subheader("Decision & next step")
        st.markdown(f'<div class="decision-callout"><b>{"SAVED ACTION" if saved.get("next_action") else "SUGGESTED RESEARCH"}</b><p>{escape(saved.get("next_action") or suggested_action(lead))}</p></div>', unsafe_allow_html=True)
        fact_rows({"Decision": saved.get("decision", "Pending Review"), "Owner": saved.get("analyst_name") or "Unassigned",
                   "Outreach": saved.get("outreach_status", "Not contacted"), "Due date": saved.get("due_date") or "Not scheduled",
                   "Task": saved.get("task_status", "Open") if saved.get("next_action") else "Not assigned"})
        if saved.get("reason"):
            st.caption("Decision rationale: " + saved["reason"])
        st.caption("Use Plan next step above to assign or complete a follow-up.")
    left, right = st.columns(2)
    with left, st.container(border=True, key="card-scores"):
        st.subheader("Score breakdown")
        if any(lead.scores[k] is not None for k in ("Quality", "Market", "Team")):
            st.plotly_chart(score_profile(lead), width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No supported score dimensions available.")
        missing = [k for k in ("Quality", "Market", "Team") if lead.scores[k] is None]
        if missing:
            st.caption("Unassessed: " + ", ".join(missing))
    with right, st.container(border=True, key="card-evidence"):
        st.subheader("Evidence coverage")
        if lead.evidence:
            st.plotly_chart(evidence_coverage(lead), width="stretch", config={"displayModeBar": False})
        else:
            st.caption("No evidence records supplied.")
        st.caption("Counts evidence records, not independent confirmations. A URL alone is not verification.")


def operational_kpis(lead):
    d = lead.data
    measures = d.get("_operating_measures") or {}
    revenue = measures.get("annual_revenue_eur")
    revenue_note = f"Reported annual revenue · {revenue['period']['end_year']}" if revenue else "Reported annual figure · period unavailable"
    values = [("Annual revenue", "annual_revenue_eur", True, revenue_note),
              ("Customers", "customer_count", False, "Reported customer count"),
              ("Capital raised", "funding_total_eur", True, "Total reported funding"),
              ("Team size", "team_size", False, "Reported people")]
    conflicts = {row["Field"] for row in d.get("_research_conflicts", [])}
    available = [(label, f"€{d[key]:,.0f}" if currency else str(d[key]),
                  note + (" · Review differing values" if key.replace("_", " ").title() in conflicts else ""))
                 for label, key, currency, note in values if isinstance(d.get(key), (int, float))]
    if available:
        kpis(available)
        sources_note(lead, measures.values())
        if d.get("annual_revenue_eur") is not None and not revenue:
            st.caption("Revenue reference period not supplied. Annual revenue is not necessarily recurring revenue.")


def business(lead):
    d, context = lead.data, context_for(lead)
    a, b, c = st.tabs(["Business & product", "Founders & team", "Traction & milestones"])
    with a:
        left, right = st.columns([1.4, 1])
        with left, st.container(border=True):
            st.subheader("Business model")
            if url(d.get("website")):
                st.link_button("Company website", url(d["website"]))
            product = context.get("product") or {}
            labels = {"customer_problem": "Customer problem", "solution": "Product & solution", "target_customers": "Target customers",
                      "economic_buyer": "Economic buyer", "business_model": "Business model", "advantage": "Advantage",
                      "technology": "Technology", "ip": "IP / patents", "maturity": "Product maturity",
                      "development_status": "Development status", "next_milestone": "Next milestone"}
            research_fields(lead, product, labels)
            fallback = {"customer_problem": d.get("problem_statement") or d.get("customer_problem"),
                        "solution": d.get("product_mechanics") or d.get("solution") or d.get("produktbeschreibung") or d.get("value_proposition"),
                        "target_customers": d.get("target_customers"), "business_model": d.get("business_model"),
                        "economic_buyer": d.get("economic_buyer"), "advantage": d.get("differentiation"),
                        "technology": d.get("technology_advantage") or d.get("technology"), "ip": d.get("ip"),
                        "maturity": d.get("product_stage"), "development_status": d.get("development_status"), "next_milestone": d.get("next_milestone")}
            additional = {labels[k]: v for k, v in fallback.items() if present(v) and not present(product.get(k))}
            if additional:
                fact_rows(additional)
        with right, st.container(border=True):
            st.subheader("Company profile")
            research_fields(lead, context.get("company") or {}, {"headquarters": "Headquarters", "reported_location": "Reported location", "founding_date": "Founding date", "company_status": "Company status"})
            fact_rows({"Sector": lead.sector, "Location": d.get("location"), "Founded": d.get("founded_on"),
                       "Founding date basis": d.get("founding_date_status"), "Team size": d.get("team_size"), "Stage": lead.stage})
            sector_research(lead)
    with b:
        fact_rows({"Team size": d.get("team_size")})
        profiles = d.get("founder_profiles") or []
        researched = {p["name"]: p for p in context.get("founders", [])}
        if profiles:
            columns = st.columns(2)
            for index, profile in enumerate(profiles):
                with columns[index % 2], st.container(border=True):
                    st.subheader(profile.get("name", "Founder"))
                    details = researched.get(profile.get("name"), {})
                    research_fields(lead, details, {"role": "Role", "qualifications": "Qualifications", "previous_companies": "Previous companies", "founding_experience": "Founding experience", "customer_problem_experience": "Problem expertise"})
                    remaining = {k.replace("_", " ").title(): v for k, v in profile.items() if k not in {"name", "evidence"} and present(v) and not present(details.get(k))}
                    if remaining:
                        fact_rows(remaining)
                    if not remaining and not any(present(v) for k, v in details.items() if k != "name"):
                        st.caption("Name supplied. Role and experience remain to be researched.")
                    for evidence in profile.get("evidence", []):
                        if url(evidence.get("url")):
                            st.link_button(evidence.get("source") or "Founder source", url(evidence["url"]))
        else:
            fact_rows({"Founders": d.get("founders"), "Team size": d.get("team_size")})
            st.caption("Next step: verify roles, relevant experience and founder-market fit.")
    with c:
        operational_kpis(lead)
        research_traction(lead)
        fact_rows({"Product maturity": d.get("product_stage") or d.get("product_maturity"), "Customers": d.get("customer_count"),
                   "Revenue (EUR)": d.get("annual_revenue_eur"), "Pilots / partners": d.get("traction_notes"),
                   "Sales": d.get("sales"), "Next milestone": d.get("next_milestone")})
        evidence = d.get("traction_evidence") or []
        if evidence:
            st.dataframe(evidence, hide_index=True, width="stretch", column_config={"url": st.column_config.LinkColumn("Source")})
        if not evidence and not any(present(v) for v in (context.get("traction") or {}).values()):
            st.caption("Customer payment status and recurring revenue need direct verification.")


def evidence_view(lead):
    d = lead.data
    a, b, c = st.tabs(["Source explorer", "Discovery timeline", "Activity history"])
    with a:
        category = st.multiselect("Evidence category", ["Team", "Market", "Risk", "Stage", "Other"], key=lead.namespace+lead.id+"categories")
        rows = [e for e in lead.evidence if not category or e["category"] in category]
        if rows:
            st.caption(f"{len(rows)} evidence records · {len(lead.sources)} distinct source URLs")
            st.dataframe(rows, hide_index=True, width="stretch", column_order=["category", "criterion", "statement", "url", "source", "date", "points", "verification", "evidence_id"],
                         column_config={"url": st.column_config.LinkColumn("Source"), "statement": st.column_config.TextColumn(width=400)})
        else:
            st.caption("No evidence records in this selection.")
        dates = [str(e["date"]) for e in lead.evidence if e["date"]]
        st.caption("Latest dated evidence: " + (max(dates) if dates else "not supplied") + ". Analysis time is not the publication date of the evidence.")
        if d.get("match_confidence") is not None:
            st.caption("Entity-match confidence supplied by sourcing: " + str(d["match_confidence"]))
        for question in items(d.get("open_questions") or d.get("research_questions")):
            st.write("• " + str(question))
        with st.expander("Untouched source record"):
            st.json(lead.raw)
    with b:
        timeline = []
        for label, field in (("First public signal", "first_signal_date"), ("Discovered by FounderRadar", "discovered_at"), ("Confirmed incorporation", "founded_on")):
            if d.get(field) and not (field == "founded_on" and d.get("gruendung_ist_proxy")):
                timeline.append({"Date": str(d[field]), "Event": label, "Source": url(d.get("source_url")) if field == "first_signal_date" else None})
        timeline.extend({"Date": e["date"], "Event": e["statement"], "Source": e["url"]} for e in lead.evidence if e["date"] and e["url"])
        for signal in items(d.get("signals")):
            if isinstance(signal, dict) and (signal.get("date") or signal.get("datum")) and url(signal.get("url")):
                timeline.append({"Date": signal.get("date") or signal.get("datum"), "Event": signal.get("evidence") or signal.get("zitat") or signal.get("type"), "Source": url(signal["url"])})
        if timeline:
            unique = list({json.dumps(row, sort_keys=True): row for row in timeline}.values())
            st.dataframe(sorted(unique, key=lambda x: str(x["Date"])), hide_index=True, width="stretch", column_config={"Source": st.column_config.LinkColumn()})
        else:
            st.caption("No dated public signals supplied.")
        if not d.get("discovered_at"):
            st.caption("Engine discovery time unavailable. A public signal date does not establish when FounderRadar discovered the company.")
        db = d.get("in_databases")
        st.caption("Database coverage: " + ("Unknown; absence is not verified." if db is None else "Listed according to sourcing." if db else "Not found in the checked databases; not proof of global absence."))
        if d.get("earliness_delta_monate") is not None:
            st.caption(f"Sourcing interval: {d['earliness_delta_monate']} months to first database entry or scoring cutoff. Not measured engine lead time.")
    with c:
        history = load_history(lead.namespace, lead.id)
        if history:
            st.dataframe(history, hide_index=True, width="stretch", column_order=["updated_at", "decision", "next_action", "due_date", "task_status", "outreach_status", "analyst_name", "reason", "notes"])
        else:
            st.caption("No changes recorded yet. Use Record decision to save your assessment and next step.")
        st.caption("Local change history; timestamps in UTC. Email delivery and replies require manual confirmation.")


def company(lead, decisions):
    d = lead.data
    saved = decisions.get((lead.namespace, lead.id), {})
    st.title(lead.name)
    st.caption(text(d.get("value_proposition"), "Value proposition not researched."))
    badges = [lead.sector, d.get("location"), lead.stage, saved.get("decision", "Pending Review")]
    year = d.get("gruendungsjahr") or d.get("founding_year")
    if year:
        badges.append(f"{'Proxy year' if d.get('gruendung_ist_proxy') else 'Founded'} {year}")
    st.markdown("".join(f'<span class="badge">{escape(str(x))}</span>' for x in badges if x), unsafe_allow_html=True)
    a, task, b, c = st.columns([1, 1, 1.2, 1.8], vertical_alignment="center")
    with a.popover("Record decision", width="stretch"):
        decision_editor(lead, saved)
    with task.popover("Plan next step", width="stretch"):
        activity_editor(lead, saved)
    draft = email_draft(lead)
    if draft:
        b.link_button("Open email draft", draft, width="stretch")
    elif url(d.get("website")):
        b.link_button("Find contact on website", url(d["website"]), width="stretch")
    else:
        b.button("No contact supplied", disabled=True, width="stretch")
    c.caption((str(d.get("email") or d.get("contact_email")) + " · supplied contact, unverified") if draft else "Email address unavailable · verify a contact before outreach")
    if lead.demo and not st.session_state.get("cockpit_run"):
        st.caption("DEMO · fictional company and sources")
    if lead.excluded:
        st.warning("Sourcing exclusion: " + text(d.get("ausschluss_grund") or d.get("hard_exclusions") or d.get("noise_class")))
    if d.get("founding_date_status") == "conflicting":
        st.warning("Conflicting founding dates in the supplied sources. Company age remains unassessed until resolved.")
    if d.get("_research_conflicts"):
        with st.expander("Different values in the supplied records · review required"):
            st.caption("The original summary values are retained. The detailed research is shown alongside them; reconcile dates and definitions before relying on either value.")
            st.dataframe(d["_research_conflicts"], hide_index=True, width="stretch")
    tabs = st.tabs(["Investment brief", "Company & team", "Market & competition", "Capital & fit", "Evidence & activity"])
    with tabs[0]:
        brief(lead, saved)
    with tabs[1]:
        business(lead)
    with tabs[2]:
        sizing, landscape = st.tabs(["Market opportunity", "Competitive landscape"])
        with sizing:
            market(lead)
        with landscape:
            competition(lead)
    with tabs[3]:
        fit, capital = st.tabs(["Fund fit", "Funding & scenarios"])
        with fit:
            st.subheader(fund_fit(lead)[0])
            st.dataframe(fund_fit(lead)[1], hide_index=True, width="stretch")
            st.caption(f"{CONFIG['disclaimer']} Version {CONFIG['version']}. Scope: {CONFIG['scope']}.")
            st.link_button("Official fund criteria", CONFIG["source"])
        with capital:
            funding(lead)
    with tabs[4]:
        evidence_view(lead)
