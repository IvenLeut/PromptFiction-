"""Category "Company Radar" (higher risk): Iven's registered companies in our dashboard (presentation only).

Data: demo_snapshot/iven_companies.json (demo_snapshot/iven_adapter.py), values copied 1:1 from Iven's reference
run. Nothing is rescored here. Iven's ranking (rule set early-stage.2) is shown on its own and never merged with
our EXIST ranking: the two rule sets measure different things on different scales.
Deep link: ``?iven=<company id>``.
"""
from __future__ import annotations

import re
from html import escape
from urllib.parse import quote

import streamlit as st

from ui_theme import SCORE_MAX, TABLE_MAX_HEIGHT, TABLE_ROW_HEIGHT, chips, fact, heading, kpi_cards, md_escape

CATEGORY_EARLY = "Spin-off Radar · pre-founding (EXIST)"
CATEGORY_RISK = "Company Radar · young GmbH/UG (higher risk)"
CATEGORIES = [CATEGORY_EARLY, CATEGORY_RISK]
ALL_SECTORS = "All industries"
ALL_STATUS = "All"
TOP_OPTIONS = [10, 20, 34]
QUERY_KEY = "iven"
LINKEDIN_SEARCH = "https://www.linkedin.com/search/results/people/?keywords="
NOT_COMPARABLE = ("Two separate rankings: our rule set scores the early-stage projects (team, market, risk, "
                  "earliness). Rule set {rule} scores the companies (product & technology 40 %, customer & "
                  "benefit 35 %, development evidence 25 %; evidenced lower bound, open criteria get no substitute "
                  "points). The scores are not comparable and are therefore never merged.")
_LEGAL = re.compile(r"\b(gmbh|ug|haftungsbeschränkt|ag|kg|se|e\.?\s?v|i\.\s?g)\b", re.I)


def load() -> dict | None:
    from demo_snapshot.iven_adapter import load_iven
    try:
        return load_iven()
    except Exception:  # broken file: the EXIST view still works
        return None


def origin(data: dict) -> str:
    from demo_snapshot.iven_adapter import origin_line
    return origin_line(data)


def en(text):
    """English rendering of Iven's German engine labels/texts (display only; data stays 1:1)."""
    from demo_snapshot.iven_adapter import en as translate
    return translate(text)


def _fmt(value, missing: str = "open") -> str:
    return missing if value is None else (f"{value:.1f}" if isinstance(value, float) and value % 1 else f"{value:.0f}")


def _date(text: str | None) -> str:
    if not text:
        return "open"
    y, m, d = text.split("-")
    return f"{d}.{m}.{y}"


def founding_text(company: dict) -> str:
    f = company["founding"]
    if not f["earliest"]:
        return "open"
    if f["earliest"] == f["latest"]:
        return _date(f["earliest"])
    if f["earliest"][:7] == f["latest"][:7]:
        return f"{f['earliest'][5:7]}/{f['earliest'][:4]}"
    if f["earliest"][:4] == f["latest"][:4]:
        return f["earliest"][:4]
    return f"{_date(f['earliest'])} – {_date(f['latest'])}"


def name_key(name: str) -> str:
    """Company name without legal form, for the cross-reference to our EXIST leads."""
    return re.sub(r"[^0-9a-zäöüß]", "", _LEGAL.sub("", (name or "").lower()))


def also_early(company: dict, early_leads) -> list:
    """Our EXIST leads with the same company name (e.g. Ymolution appears in both searches)."""
    key = name_key(company["name"])
    return [lead for lead in early_leads or [] if key and name_key(lead.name) == key]


def linkedin(person: dict, company: dict) -> tuple[str, str, bool]:
    """(label, url, is_profile): the profile Iven's team search found, else a people search."""
    if person.get("linkedin"):
        return "LinkedIn", person["linkedin"], True
    return "Search on LinkedIn", LINKEDIN_SEARCH + quote(f"{person['name']} {company['name']}", safe=""), False


def mailto(company: dict) -> str | None:
    if not company.get("email"):
        return None
    subject = quote(f"Intro call: {company['name']}", safe="")
    body = quote(f"Hello,\n\nwe came across {company['name']} and would like to learn more about your product "
                 "status and your first customer experiences. Do you have time for a short call?\n\nBest regards",
                 safe="")
    return f"mailto:{quote(company['email'], safe='@')}?subject={subject}&body={body}"


def category_switch(data: dict | None) -> str:
    """Segmented control between the two categories; EXIST is the default."""
    if not data:
        return CATEGORY_EARLY
    saved = st.session_state.get("portfolio_category", CATEGORY_EARLY)
    labels = {CATEGORY_EARLY: CATEGORY_EARLY, CATEGORY_RISK: f"{CATEGORY_RISK} · {len(data['companies'])}"}
    choice = st.segmented_control("Category", CATEGORIES, key="dashboard_category", format_func=labels.get,
                                  default=saved if saved in CATEGORIES else CATEGORY_EARLY,
                                  help="Two separate searches with their own rule sets; the scores are never merged.")
    choice = choice or CATEGORY_EARLY
    st.session_state.portfolio_category = choice
    return choice


def filter_companies(companies: list[dict], sector: str = ALL_SECTORS, status: str = ALL_STATUS,
                     risk: str = ALL_STATUS, top_n: int = 34) -> list[dict]:
    """Filters keep Iven's order (his rank); nothing is re-sorted."""
    shown = [c for c in companies
             if (sector == ALL_SECTORS or sector in c["sectors"])
             and (status == ALL_STATUS or c["status"] == status)
             and (risk == ALL_STATUS or c["risk"] == risk)]
    return shown[:top_n]


def _saved(key: str, options: list, default):
    value = st.session_state.get(key, default)
    return value if value in options else default


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def render_overview(data: dict):
    """Heading, provenance, filters, KPI cards and Iven's ranking; a row click opens the deep dive."""
    companies = data["companies"]
    ranked = [c for c in companies if c["queue"] == "ranked"]
    heading(f"Company Radar · young GmbH/UG · as of {_date(data['source_snapshot_date'])}",
            f"{len(companies)} registered companies, higher risk.",
            "Companies already incorporated (GLEIF register, funded projects, company websites) in the last "
            f"{data['max_age_months']} months. Later than our EXIST projects, so more competition for the deal "
            "and a higher risk of arriving too late.")
    st.caption(f"ORIGIN: {origin(data).upper()} · RUN {data['run_id']} · REFERENCE DATE {_date(data['as_of'])}")
    st.info(NOT_COMPARABLE.format(rule=data["rule_version"]), icon="ℹ️")

    # Filter values stay Iven's German labels internally (his data); only the display is English.
    sectors = [ALL_SECTORS, *sorted({s for c in companies for s in c["sectors"]})]
    statuses = [ALL_STATUS, *sorted({c["status"] for c in companies})]
    risks = [ALL_STATUS, *sorted({c["risk"] for c in companies})]
    a, b, c_, d = st.columns([1.3, 1, 1.3, .8])
    sector = a.selectbox("Industry", sectors, key="iven_filter_sector",
                         index=sectors.index(_saved("iven_sector", sectors, ALL_SECTORS)))
    status = b.selectbox("Status", statuses, key="iven_filter_status", format_func=en,
                         index=statuses.index(_saved("iven_status", statuses, ALL_STATUS)))
    risk = c_.selectbox("Risk (review label)", risks, key="iven_filter_risk", format_func=en,
                        index=risks.index(_saved("iven_risk", risks, ALL_STATUS)))
    top_n = d.selectbox("Show ranking", TOP_OPTIONS, key="iven_filter_top",
                        index=TOP_OPTIONS.index(_saved("iven_top", TOP_OPTIONS, 20)),
                        format_func=lambda x: "All" if x == TOP_OPTIONS[-1] else f"Top {x}")
    st.session_state.update(iven_sector=sector, iven_status=status, iven_risk=risk, iven_top=top_n)
    shown = filter_companies(companies, sector, status, risk, top_n)

    scored = [c for c in shown if c["score"] is not None]
    mean_score = _mean(c["score"] for c in scored)
    mean_product = _mean(c["company_score"] for c in scored)
    mean_market = _mean(c["market_score"] for c in scored)
    kpi_cards([
        ("Scorable", f"{len(scored)} / {len(shown)}", f"{len(shown) - len(scored)} with open evidence (score open)",
         100 * len(scored) / len(shown) if shown else 0),
        ("Ø Screening score", _fmt(mean_score, "—"), "Evidenced lower bound · higher is better", mean_score or 0),
        ("Ø Product & technology", _fmt(mean_product, "—"), "Company score · higher is better", mean_product or 0),
        ("Ø Customer & benefit", _fmt(mean_market, "—"), "Market potential score · higher is better", mean_market or 0),
    ], dark_first=True)
    st.caption(f"Total: {len(ranked)} scorable, {len(companies) - len(ranked)} with open evidence. "
               "Averages only over scorable companies in the selection. Risk here is a review label, not a number.")
    if not shown:
        st.info("No company matches the filters.")
        return
    st.subheader("Company Radar ranking")
    st.caption("Order and values exactly as in the Company Radar reference run (Ergebnisse/Longlist.csv). Click a row for the deep dive.")
    rows = [{"Rank": c["rank"], "Company": c["name"], "Industry": ", ".join(c["sectors"]) or "open",
             "Status": en(c["status"]), "Score": c["score"], "Product & technology": c["company_score"],
             "Customer & benefit": c["market_score"], "Development evidence": c["validation_score"],
             "Risk": en(c["risk"]), "Stage": en(c["stage"]), "Founded": founding_text(c), "Website": c["website"]}
            for c in shown]
    config = {
        "Rank": st.column_config.NumberColumn("#", width="small", format="%d"),
        "Company": st.column_config.TextColumn("Company / deep dive", width="medium"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=SCORE_MAX, format="%.1f",
                                                 help="Screening score (evidenced lower bound). Empty = open."),
        "Product & technology": st.column_config.NumberColumn("Product", format="%.0f"),
        "Customer & benefit": st.column_config.NumberColumn("Market", format="%.0f"),
        "Development evidence": st.column_config.NumberColumn("Evidence", format="%.0f"),
        "Website": st.column_config.LinkColumn("Website", display_text=r"https?://(?:www\.)?([^/]+)"),
    }
    key = f"iven_ranking_{len(shown)}_{sector}_{status}_{risk}_{st.session_state.get('table_generation', 0)}"
    event = st.dataframe(rows, hide_index=True, width="stretch", row_height=TABLE_ROW_HEIGHT,
                         height=min(TABLE_MAX_HEIGHT, 40 + len(rows) * TABLE_ROW_HEIGHT),
                         column_config=config, on_select="rerun", selection_mode="single-row", key=key)
    selected = event.selection.rows
    if selected and 0 <= selected[0] < len(shown):
        st.query_params[QUERY_KEY] = shown[selected[0]]["id"]
        st.rerun()
    st.caption(f"Source: {data['reference_file']} ({origin(data)}). Values taken over unchanged; "
               "no rescoring in the dashboard. Manual check before every contact.")


def back():
    st.query_params.pop(QUERY_KEY, None)
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


def _link(url: str, label: str = "Source") -> str:
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'


def render_deep_dive(company: dict, data: dict, early_leads=None):
    """Description, hypothesis, scorecard, open points, evidence with links, team with LinkedIn, contact."""
    from demo_snapshot.iven_adapter import english
    raw, company = company, english(company)   # display copy in English; numbers and IDs unchanged
    st.button("Back to overview", on_click=back, key="iven_back")
    heading(f"Company Radar / Deep Dive · Rank {company['rank']}", company["name"],
            f"{', '.join(company['sectors']) or 'Industry open'} · {company['stage']} · Founded {founding_text(company)}")
    tone = "good" if company["queue"] == "ranked" else "warn"
    st.markdown(chips([(company["status"], tone), (company["risk"], "warn"), (company["htgf_fit"], ""),
                       (f"Data coverage {company['coverage'] * 100:.0f} %", "")]), unsafe_allow_html=True)
    st.caption(f"Origin: {origin(data)} · values unchanged from the reference run")
    for lead in also_early(company, early_leads):
        st.info(f"Also listed under “{CATEGORY_EARLY}” as **{md_escape(lead.name)}**, there with our own score. "
                "The two scores are not comparable.", icon="🔁")
    st.markdown("**Product description**")
    st.write(md_escape(company["summary"]))
    cols = st.columns(5)
    upper = (f"Upper bound {_fmt(company['score_upper'])}" if company["score_upper"] not in (None, company["score"]) else None)
    cols[0].metric("Screening score", f"{_fmt(company['score'])} / 100" if company["score"] is not None else "open",
                   delta=upper, delta_color="off")
    for column, label, value in zip(cols[1:4], ["Product & technology", "Customer & benefit", "Development evidence"],
                                    [company["company_score"], company["market_score"], company["validation_score"]]):
        column.metric(label, f"{_fmt(value)} / 100" if value is not None else "open")
    cols[4].metric("Risk (label)", company["risk"].replace("Needs review: ", "") or "open",
                   help=f"Risk label: {company['risk']}. Not a number.")
    st.caption("Company Radar scorecard: product & technology 40 %, customer & benefit 35 %, development evidence 25 %. "
               "Open criteria get no substitute points; score = evidenced lower bound. Higher is better.")
    main, contact = st.columns([2.2, 1], gap="large")
    with main:
        st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Investment hypothesis</div>'
                    f'<p>{escape(company["thesis"])}</p></div>', unsafe_allow_html=True)
        st.markdown(f"**Why contact now?** {md_escape(company['why'])}")
        st.markdown(f"**First question:** {md_escape(company['question'])}")
        tabs = st.tabs(["Scorecard", "Open points & risk", "Evidence & sources", "Team"])
        with tabs[0]:
            for c in company["criteria"]:
                with st.container(border=True):
                    points = f"{c['points']} / 100" if c["points"] is not None else "open"
                    st.markdown(f"**{md_escape(c['label'])}** · weight {c['weight']} % · **{points}**")
                    st.caption(md_escape(c["reason"]))
                    if c["facts"]:
                        st.caption("Based on: " + ", ".join(md_escape(f) for f in c["facts"]))
            st.caption(f"Segment: {company['segment']}")
        with tabs[1]:
            st.warning(f"Risk: {md_escape(company['risk'])}", icon="⚠️")
            fact("HTGF fit (Company Radar assessment)", company["htgf_fit"])
            if company["reasons"]:
                st.markdown("**Open evidence**")
                for reason in company["reasons"]:
                    st.markdown(f"• {md_escape(reason)}")
            st.markdown("**Next steps**")
            for step in company["next_steps"]:
                st.markdown(f"• {md_escape(step)}")
        with tabs[2]:
            f = company["founding"]
            if f["basis"]:
                st.caption(f"Founded: {md_escape(founding_text(company))} · {md_escape(f['basis'])}")
            for item in company["facts"]:
                with st.container(border=True):
                    st.markdown(f"**{md_escape(item['label'])}:** {md_escape(item['value'])}")
                    st.caption(f"“{md_escape(item['quote'])}” · {md_escape(item['basis'])}")
                    if item["url"].startswith(("https://", "http://")):
                        st.markdown(_link(item["url"], "Open evidence"), unsafe_allow_html=True)
            st.markdown("**Retrieved sources**")
            for s in company["sources"]:
                if s["url"].startswith(("https://", "http://")):
                    st.markdown(f"{_link(s['url'], s['title'] or s['url'])} <small>· retrieved {escape(s['retrieved_at'][:10])}</small>",
                                unsafe_allow_html=True)
            for m in company["market_comparisons"]:
                st.markdown(f"Comparison **{md_escape(m['name'])}**: {md_escape(m['text'])} ", unsafe_allow_html=False)
                st.markdown(_link(m["url"]), unsafe_allow_html=True)
        with tabs[3]:
            if not company["team"]:
                team_fact = next((x for x in raw["facts"] if x["key"] == "team"), None)
                st.caption("No person named with evidence yet." + (f" Website mentions: “{team_fact['quote']}”" if team_fact else ""))
            people = []
            for person in company["team"]:
                label, url, found = linkedin(person, company)
                css = "fr-li" if found else "fr-li fr-li-search"
                people.append(f'<div class="fr-person"><b>{escape(person["name"])}</b><small>{escape(person["role"])}</small>'
                              f'<small>{escape(person["biography"])}</small>{_link(person["source_url"])}'
                              f'<div class="fr-links"><a class="{css}" href="{escape(url, quote=True)}" target="_blank" '
                              f'rel="noopener noreferrer">{escape(label)}</a></div></div>')
            if people:
                st.markdown('<div class="fr-team">' + "".join(people) + "</div>", unsafe_allow_html=True)
    with contact:
        with st.container(border=True):
            st.subheader("Contact founders")
            names = [p["name"] for p in company["team"]]
            st.write(md_escape(", ".join(names) or "Founders not yet named with evidence"))
            for i, person in enumerate(company["team"]):
                label, url, found = linkedin(person, company)
                st.link_button(f"{label} · {person['name']}", url, width="stretch", key=f"iven_li_{company['id']}_{i}",
                               help="Profile from the team research." if found else
                                    "No profile evidenced: opens the LinkedIn people search by name and company.")
            if names:
                st.caption("LinkedIn opens in a new tab; nothing is sent automatically.")
            fact("E-mail (company mailbox)", company["email"] or "Not yet available")
            if url := mailto(company):
                st.link_button("Get in touch", url, type="primary", width="stretch")
                st.caption("Opens an e-mail draft. Nothing is sent automatically.")
            if company["website"]:
                st.link_button("Company website", company["website"], width="stretch")
            fact("Discovered via", "Company Radar (GLEIF / funded project / website)")
        import json
        st.download_button("Export company dossier", json.dumps(raw, ensure_ascii=False, indent=2),
                           file_name=f"{company['id']}.json", mime="application/json", width="stretch",
                           key=f"iven_export_{company['id']}")
