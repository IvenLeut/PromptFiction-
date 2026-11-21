"""Dedicated startup page; no scoring or sourcing logic.

Tab "Investment briefing" (cockpit branch, Iven/Leonard): fund-fit status, scorecard, key strengths and risks,
business and market, traction and funding, discovery timeline and the analyst decision (analyst_store).
"""
import re
from collections.abc import Callable
from datetime import date
from html import escape

import streamlit as st

from charts import profile_figure, timeline_figure
from dashboard import (
    contact_email, contact_url, db_status, documented_founding, founder_names, review_flags, thesis_html, industry_label, lead_meta, lead_time_months, linkedin_link, priority_line,
    source_link_markdown, stage_label, website_of,
)
from market_view import render_company_research, render_market
from models import EvaluatedLead
from ui_theme import (
    QUESTION_PREVIEW, UNKNOWN, chips, fact, format_date, format_number, format_score, heading, md_escape, readable,
)

# Evidence fields whose document date marks an own event on the signal timeline (others repeat the grant).
_TIMELINE_FIELDS = {"idw": "Press release (idw)", "first_web_capture": "First Wayback capture of the website",
                    "web_capture_before_project": "Website archived before project start",
                    "first_db_date": "First database profile (Wayback)", "founding_statement": "Founding announcement"}
_BACKGROUND = {"tech": "Tech/research", "business": "Business", "beides": "Tech and business"}


def _questions(lead: EvaluatedLead, meta: dict | None = None) -> list[str]:
    """Open questions of the snapshot review flags and of steps 3 and 2, without duplicates."""
    flagged = [f["question"] for f in review_flags(lead, meta) if f.get("question")]
    return list(dict.fromkeys([*flagged, *lead.open_questions, *lead.research_questions]))


def sourced_signals(lead: EvaluatedLead) -> list[tuple[str, str, str | None]]:
    """(label, value, url or None) rows of what step 2 documented for a live lead; demo leads have none.

    Live leads are mostly pre-founding projects: the company profile is "Unknown" almost everywhere,
    while grants, the database check and the first dated signal are filled. This block shows those.
    """
    if lead.is_demo:
        return []
    rows = []
    for grant in lead.grants:
        term = " – ".join(format_date(day) if day else "?" for day in (grant.start, grant.end))
        parts = [grant.programme,
                 format_number(grant.amount_eur, " EUR") if grant.amount_eur is not None else "Amount unknown",
                 f"Term {term}" if grant.start or grant.end else "Term unknown"]
        if grant.reference:
            parts.append(f"FKZ {grant.reference}")
        rows.append(("Public funding", " · ".join(parts), str(grant.url)))
    if lead.in_databases is True:
        since = f", first seen {format_date(lead.first_db_date)}" if lead.first_db_date else ""
        rows.append(("Startup databases", f"Profile found{since}",
                     str(lead.database_urls[0]) if lead.database_urls else None))
    elif lead.in_databases is False:
        rows.append(("Startup databases", db_status(lead)[0][0].upper() + db_status(lead)[0][1:], None))
    else:
        rows.append(("Startup databases", "Not checked", None))
    rows.append(("First dated signal",
                 format_date(lead.first_signal_date) if lead.first_signal_date else UNKNOWN, None))
    rows.append(("Open questions", str(len(_questions(lead))), None))
    return rows


def signal_timeline(lead: EvaluatedLead, as_of: date | None = None) -> list[tuple[date, str, str, str | None, bool]]:
    """Dated signals of a live lead, oldest first: (date, label, source, url, is_key_signal).

    Sources: grants (start = our discovery signal, end), dated step-1 signals, press releases and Wayback
    captures from the evidence, the first database entry and the founding date. Deduplicated by date and label.
    """
    events: list[tuple[date, str, str, str | None, bool]] = []
    for grant in lead.grants:
        amount = f", {format_number(grant.amount_eur, ' EUR')}" if grant.amount_eur is not None else ""
        if grant.start:
            events.append((grant.start, f"Funding start {grant.programme}{amount} (early signal)", "Förderkatalog",
                           str(grant.url), True))
        if grant.end:
            ended = as_of is not None and grant.end <= as_of
            events.append((grant.end, f"Funding {'ended' if ended else 'ends'} – follow-on financing due",
                           "Förderkatalog", str(grant.url), False))
    for signal in lead.signals:
        if signal.date and not any(e[0] == signal.date and e[2] == "Förderkatalog" for e in events):
            events.append((signal.date, f"{signal.source}: {signal.type.replace('_', ' ')}", signal.source,
                           str(signal.url), not events))
    for evidence in lead.evidence:
        label = _TIMELINE_FIELDS.get(evidence.field or "")
        if label and evidence.document_date:
            headline = evidence.finding.strip().splitlines()[0][:140] if evidence.field == "idw" else ""
            events.append((evidence.document_date, f"{label}: {headline}" if headline else label,
                           evidence.source, str(evidence.url), False))
    if lead.first_web_capture and not any("Wayback" in e[1] for e in events):
        events.append((lead.first_web_capture, _TIMELINE_FIELDS["first_web_capture"], "Wayback", None, False))
    if lead.first_db_date and not any(e[0] == lead.first_db_date and "database" in e[1] for e in events):
        events.append((lead.first_db_date, "First database profile", "Database",
                       str(lead.database_urls[0]) if lead.database_urls else None, False))
    if lead.founded_on:
        events.append((lead.founded_on, "Founding", "Dossier", None, False))
    unique = {}
    for event in sorted(events, key=lambda e: (e[0], not e[4])):
        unique.setdefault((event[0], event[1]), event)
    return list(unique.values())


def _render_signals_and_team(lead: EvaluatedLead, meta: dict | None, as_of: date | None):
    """Earliness facts, signal timeline and team card of a live lead (HTGF criteria: earliness, team)."""
    extra = lead_meta(lead, meta)
    status, kind = db_status(lead)
    months = lead_time_months(lead, meta, as_of)
    tags = [(f"First signal {format_date(lead.first_signal_date)}" if lead.first_signal_date else "First signal unknown", ""),
            (status, kind)]
    if months is not None:
        tags.append((f"{months} months lead time", "good" if lead.in_databases is not True else ""))
    if extra.get("noise_class"):
        tags.append(("Noise filter: clean" if extra["noise_class"] == "vc_potenzial"
                     else f"Noise: {extra['noise_class']}", "" if extra["noise_class"] == "vc_potenzial" else "warn"))
    flags = review_flags(lead, meta)
    tags += [(f["flag"], "warn") for f in flags]
    st.markdown(chips(tags), unsafe_allow_html=True)
    for f in flags:
        st.warning(md_escape(f"{f['flag']}: {f.get('detail', '')} Quote: “{f.get('quote', '')}”"), icon="⚠️")
        st.markdown(f'<small><a href="{escape(f["url"], quote=True)}" target="_blank" rel="noopener noreferrer">'
                    f'Open source</a> · {escape(f.get("date") or "")} · {escape(f.get("origin") or "")}</small>',
                    unsafe_allow_html=True)
    if extra.get("why_now"):
        st.markdown(f"**Why now:** {md_escape(extra['why_now'])}")
    timeline, team = st.columns([1.4, 1], gap="large")
    with timeline:
        st.subheader("Signal timeline")
        events = signal_timeline(lead, as_of)
        if events:
            st.plotly_chart(timeline_figure(events), width="stretch", theme=None, key="signal_timeline",
                            config={"displayModeBar": False})
            items = []
            for day, label, source, url, key in events:
                link = (f' <a href="{escape(url, quote=True)}" target="_blank" rel="noopener">{escape(source)}</a>'
                        if url else f" <small>{escape(source)}</small>")
                items.append(f'<li class="{"fr-key" if key else ""}"><time>{format_date(day)}</time>'
                             f'<span>{escape(label)}{link}</span></li>')
            st.markdown(f'<ul class="fr-tl">{"".join(items)}</ul>', unsafe_allow_html=True)
        else:
            st.caption("No dated signals documented.")
    with team:
        st.subheader("Team")
        st.markdown(_team_card(lead), unsafe_allow_html=True)
        website = website_of(lead)
        if website:
            st.caption(f"Website: {md_escape(website)}" + (" (assigned in the context step)" if not lead.website else ""))
        if lead.legal_form or lead.register_id:
            st.caption(md_escape(" · ".join(x for x in (lead.legal_form, lead.register_id) if x)))


def _team_card(lead: EvaluatedLead) -> str:
    """HTML cards per person: name, role, origin (institution), profile mix and research link."""
    profiles = {p.name: p for p in lead.founder_profiles}
    people = []
    for name in founder_names(lead):
        profile = profiles.get(name)
        role = (profile.role if profile else None) or ("Managing director" if name in lead.managing_directors else "Role open")
        origin = (profile.institution if profile else None) or "Origin open"
        lines = [f"<b>{escape(name)}</b>", f"<small>{escape(role)}</small>", f"<small>{escape(origin)}</small>"]
        if profile and profile.background:
            lines.append(f"<small>Profile: {escape(_BACKGROUND.get(profile.background, profile.background))}</small>")
        if profile and profile.works_total:
            lines.append(f"<small>{profile.works_total} publications</small>")
        if profile and (profile.openalex_url or profile.source_url):
            url = str(profile.openalex_url or profile.source_url)
            lines.append(f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener">Source</a>')
        label, url, found = linkedin_link(lead, name)
        css = "fr-li" if found else "fr-li fr-li-search"
        lines.append(f'<div class="fr-links"><a class="{css}" href="{escape(url, quote=True)}" target="_blank" '
                     f'rel="noopener noreferrer">{escape(label)}</a></div>')
        people.append('<div class="fr-person">' + "".join(lines) + "</div>")
    if not people:
        institution = next((g.recipient for g in lead.grants if g.recipient), None)
        text = "No person named with evidence yet."
        if institution:
            text += f" Grant recipient: {institution}."
        return f'<div class="fr-person"><small>{escape(text)}</small></div>'
    return '<div class="fr-team">' + "".join(people) + "</div>"


def render_deep_dive(lead: EvaluatedLead, back: Callable[[], None], meta: dict | None = None,
                     as_of: date | None = None, *, namespace: str = "demo", decision: dict | None = None):
    """Profile, signals, team, diligence, sources and contact of one lead."""
    st.button("Back to overview", on_click=back, key="back_to_portfolio")
    heading("Portfolio / Startup Deep Dive", lead.name,
            f"{industry_label(lead)} · {lead.location or 'Location unknown'} · {stage_label(lead, meta)}")
    if priority := priority_line(lead):
        st.caption(md_escape(priority))
    st.markdown("**Product / value proposition**")
    st.write(md_escape(lead.value_proposition))
    metrics = st.columns(4)
    for column, label, score in zip(metrics,
            ["Overall score", "Company score", "Market potential", "Risk · higher = riskier"],
            [lead.overall_score, lead.company_score, lead.market_potential_score, lead.risk_score]):
        column.metric(label, UNKNOWN if score is None else f"{format_score(score)} / 100")
    st.caption("Scores and stage classification from step 3. All values 0–100; lower risk is better.")
    if not lead.is_demo:
        _render_signals_and_team(lead, meta, as_of)
    main, contact = st.columns([2.2, 1], gap="large")
    with main:
        st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Investment hypothesis</div>'
                    f'{thesis_html(lead.investment_thesis)}</div>', unsafe_allow_html=True)
        context = lead.context_v2
        has_market = bool(context and context.market_intelligence)
        tabs = st.tabs(["Company & key figures", "Risks & review", "Sources & evidence", BRIEFING_TAB]
                       + (["Market research"] if has_market else []))
        with tabs[0]:
            _render_overview(lead, meta)
        with tabs[1]:
            _render_diligence(lead, meta)
        with tabs[2]:
            _render_sources(lead, has_market)
        with tabs[3]:
            _render_briefing(lead, namespace, decision)
        if has_market:
            with tabs[4]:
                render_market(context)
    with contact:
        _render_contact(lead)


def _render_overview(lead: EvaluatedLead, meta: dict | None = None):
    """Score profile, company facts and score drivers."""
    st.plotly_chart(profile_figure(lead), width="stretch", theme=None, key="startup_profile",
                    config={"displayModeBar": False})
    signals = sourced_signals(lead)
    if signals:
        st.subheader("Documented signals")
        for label, value, url in signals:
            fact(label, value)
            if url:
                st.markdown(f"[Open source]({url})")
    st.subheader("Company profile")
    left, right = st.columns(2)
    founding = documented_founding(lead, meta)
    with left:
        fact("Company", lead.name)
        fact("Industry", industry_label(lead))
        fact("Legal form", lead.legal_form + (" i.G." if lead.in_formation else "") if lead.legal_form else UNKNOWN)
        fact("Founded", founding["text"] if founding else UNKNOWN)
        if founding and founding["url"]:
            st.markdown(f"<small>{escape(founding['source'])} · "
                        f'<a href="{escape(founding["url"], quote=True)}" target="_blank" rel="noopener">Source</a></small>',
                        unsafe_allow_html=True)
        fact("Team size", format_number(lead.team_size))
    with right:
        fact("Product status", readable(lead.product_stage) if lead.product_stage else UNKNOWN)
        fact("Product type", readable(lead.product_type) if lead.product_type else UNKNOWN)
        fact("Stage", stage_label(lead, meta))
        fact("Finanzierung gesamt", format_number(lead.funding_total_eur, " EUR"))
        fact("Funding stage", readable(lead.funding_stage) if lead.funding_stage else UNKNOWN)
        fact("Kunden", format_number(lead.customer_count))
        fact("Jahresumsatz", format_number(lead.annual_revenue_eur, " EUR"))
    st.subheader("What speaks for the company")
    for driver in lead.score_drivers:
        st.markdown(f"• {source_link_markdown(driver)}")
    if not lead.score_drivers:
        st.caption("No score drivers delivered yet.")
    if lead.traction_notes:
        st.write(md_escape(lead.traction_notes))
    if lead.context_v2:
        render_company_research(lead.context_v2)


def _render_diligence(lead: EvaluatedLead, meta: dict | None = None):
    """Risks and questions for the first call; long question lists are collapsed."""
    st.subheader("Key risks")
    for risk in lead.risks:
        st.warning(source_link_markdown(risk), icon="⚠️")
    if not lead.risks:
        st.caption("No risks documented. That does not mean there are none.")
    st.subheader("Questions for the first call")
    questions = _questions(lead, meta)
    for i, question in enumerate(questions[:QUESTION_PREVIEW], 1):
        st.write(f"{i}. {md_escape(question)}")
    if len(questions) > QUESTION_PREVIEW:
        with st.expander(f"{len(questions) - QUESTION_PREVIEW} more questions"):
            for i, question in enumerate(questions[QUESTION_PREVIEW:], QUESTION_PREVIEW + 1):
                st.write(f"{i}. {md_escape(question)}")
    if not questions:
        st.caption("No open questions documented yet.")


def _render_sources(lead: EvaluatedLead, has_market: bool):
    """Original find and all evidence, deduplicated by evidence id."""
    st.subheader("Original find")
    st.write(md_escape(lead.source_name or "Source not named"))
    st.link_button("View original source", str(lead.source_url))
    evidence_items = list(lead.evidence)
    if lead.country_evidence and lead.country_evidence not in evidence_items:
        evidence_items.insert(0, lead.country_evidence)
    if has_market:
        evidence_items.extend(lead.context_v2.market_intelligence.sources)
    unique_evidence = {item.evidence_id: item for item in evidence_items}
    for i, evidence in enumerate(unique_evidence.values(), 1):
        with st.container(border=True):
            st.markdown(f"**{i}. {md_escape(evidence.source)}**")
            st.write(md_escape(evidence.finding))
            document = f" · document dated {format_date(evidence.document_date)}" if evidence.document_date else ""
            st.caption(md_escape(f"{evidence.field or 'General'} · retrieved {format_date(evidence.retrieved_at)}"
                                 f"{document} · {evidence.verification_status} · ID {evidence.evidence_id}"))
            st.link_button("Open evidence", str(evidence.url))


def _render_contact(lead: EvaluatedLead):
    """Founder contact, website and dossier export."""
    with st.container(border=True):
        st.subheader("Contact founders")
        names = founder_names(lead)
        st.write(md_escape(", ".join(names) or "Founders not yet known"))
        for i, name in enumerate(names):
            label, url, found = linkedin_link(lead, name)
            st.link_button(f"{label} · {name}", url, width="stretch", key=f"linkedin_{lead.id}_{i}",
                           help="Public profile from the team research (step 2)." if found else
                                "No profile evidenced: opens the LinkedIn people search by name and company.")
        if names:
            st.caption("LinkedIn opens in a new tab; nothing is sent automatically.")
        fact("E-mail", contact_email(lead) or "Not yet available")
        mailto = contact_url(lead)
        if mailto:
            st.link_button("Get in touch", mailto, type="primary", width="stretch")
            st.caption("Opens an e-mail draft. Nothing is sent automatically.")
        if website_of(lead):
            st.link_button("Company website", website_of(lead), width="stretch")
        else:
            st.caption("No website yet.")
        fact("Discovered via", lead.source_name or UNKNOWN)
    st.download_button("Export startup dossier", lead.model_dump_json(indent=2),
                       file_name=f"{lead.id}.json", mime="application/json", width="stretch")
    if lead.is_demo:
        st.caption("Fictional company profile. The market research marks data sources and demo assumptions.")


# --- Investment briefing and analyst decision (cockpit branch) -----------------------------------------

BRIEFING_TAB = "Investment briefing & decision"


def _source_card(evidence, label: str = "Open original source"):
    st.write(md_escape(evidence.finding))
    published = format_date(evidence.published_on) if evidence.published_on else UNKNOWN
    st.caption(md_escape(f"Source: {evidence.source} · Published: {published} · "
                         f"Retrieved: {format_date(evidence.retrieved_at)}"))
    st.link_button(label, str(evidence.url))


def _all_evidence(lead: EvaluatedLead) -> list:
    items = list(lead.evidence) + list(lead.traction_evidence)
    if lead.country_evidence:
        items.append(lead.country_evidence)
    for founder in lead.founder_profiles:
        items.extend(founder.evidence)
    for event in lead.funding_events:
        items.extend(event.evidence)
    return list({(str(item.url), item.finding, item.published_on): item for item in items}.values())


def _arguments(items, legacy, empty: str):
    if items:
        for argument in items[:3]:
            st.markdown(f"**{md_escape(argument.statement)}**")
            st.write(md_escape(argument.rationale))
            if not argument.evidence:
                st.caption("Assessment without linked evidence – verify before contact.")
            for evidence in argument.evidence:
                _source_card(evidence, "Evidence for argument")
    elif legacy:
        for text in legacy[:3]:
            st.markdown(f"• {source_link_markdown(text)}")
        st.caption("From the score drivers or risks of step 3.")
    else:
        st.caption(empty)


def _render_briefing(lead: EvaluatedLead, namespace: str, decision: dict | None):
    """Iven's investment briefing in the HTGF theme; every value is shown as delivered, gaps as "Unknown"."""
    from analyst_store import DECISIONS, save_decision
    from scorecard import render_scorecard
    from screening import screening_status, source_label

    st.markdown(f"**Fund-fit status: {md_escape(screening_status(lead))}**")
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        st.error("Hard exclusion: " + md_escape("; ".join(lead.hard_exclusions) or "Excluded by the evaluation; reason missing."))
    if decision:
        st.caption(md_escape(f"Analyst decision: {decision['decision']} · saved {decision['updated_at']}"))
    why = lead.why_contact_now
    if why:  # at most two sentences, also for older provider payloads
        why = " ".join(re.split(r"(?<=[.!?])\s+", why.strip())[:2])
    st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Why contact now? · Assessment</div>'
                f'<p>{escape(why or "No evidenced reason for prompt contact yet.")}</p></div>',
                unsafe_allow_html=True)
    render_scorecard(lead)
    strengths, risks = st.columns(2, gap="large")
    with strengths:
        st.markdown("#### Strengths")
        _arguments(lead.key_strengths, lead.score_drivers, "No evidenced strengths yet.")
    with risks:
        st.markdown("#### Risks / red flags")
        _arguments(lead.key_risks, lead.risks, "No risks documented; not proof of being risk-free.")
    st.markdown("#### Business & market")
    left, right = st.columns(2)
    with left:
        for label, item in [("Problem", lead.problem_statement), ("Solution / product", lead.product_mechanics),
                            ("Target customers", lead.target_customers), ("Business model", lead.business_model)]:
            fact(label, item or UNKNOWN)
    with right:
        for label, item in [("Target market", lead.target_market), ("Competitors", ", ".join(lead.competitors)),
                            ("Differentiation", lead.differentiation), ("Technology / IP", lead.technology_advantage)]:
            fact(label, item or UNKNOWN)
    st.markdown("#### Traction & funding")
    st.caption("Unknown funding does not mean unfunded. Missing revenue is not zero revenue.")
    a, b, c = st.columns(3)
    with a:
        fact("Product maturity", readable(lead.product_maturity if lead.product_maturity != "Unknown" else lead.product_stage))
        fact("Funding status", readable(lead.funding_status))
    with b:
        fact("Finanzierung gesamt", format_number(lead.funding_total_eur, " EUR"))
        fact("Kunden", format_number(lead.customer_count))
    with c:
        fact("Jahresumsatz", format_number(lead.annual_revenue_eur, " EUR"))
        fact("Team size", format_number(lead.team_size))
    for evidence in lead.traction_evidence:
        _source_card(evidence, "Traction source")
    for event in lead.funding_events:
        st.write(md_escape(f"{format_date(event.announced_on) if event.announced_on else 'Date unknown'} · "
                           f"{format_number(event.amount_eur, ' EUR')} · {', '.join(event.investors) or 'Investors unknown'}"))
        for evidence in event.evidence:
            _source_card(evidence, "Funding source")
    st.markdown("#### Discovery")
    fact("Discovery source", source_label(lead))
    fact("Earliest public signal", format_date(lead.first_signal_date) if lead.first_signal_date else UNKNOWN)
    dated = sorted((x for x in _all_evidence(lead) if x.published_on), key=lambda x: x.published_on)
    with st.expander(f"Evidence with publication date ({len(dated)})"):
        for evidence in dated:
            _source_card(evidence)
        if not dated:
            st.caption("No evidence with a publication date.")

    st.markdown("#### Analyst decision")
    st.caption("Manual decision, stored locally (analyst_store). “Contact” does not send an e-mail.")
    if lead.hard_exclusions or lead.eligibility_status == "Excluded":
        st.warning("A hard exclusion stays visible in the longlist, even if the decision differs.")
    saved = decision or {}
    with st.form(f"decision_{namespace}_{lead.id}"):
        choice = st.radio("Decision", list(DECISIONS),
                          index=list(DECISIONS).index(saved["decision"]) if saved else None, horizontal=True)
        notes = st.text_area("Analyst notes", saved.get("notes", ""))
        reason = st.text_area("Reason for the decision", saved.get("reason", ""))
        submitted = st.form_submit_button("Save decision", type="primary")
    if submitted:
        if choice is None:
            st.error("Please select a decision.")
        else:
            try:
                save_decision(namespace, lead.id, choice, notes, reason)
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("Saving failed. Check database access.")
            else:
                st.success("Decision and notes saved.")
