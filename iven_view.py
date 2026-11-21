"""Category "Höheres Risiko": Iven's registered companies in our dashboard (presentation only).

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

CATEGORY_EARLY = "Frühe Vorhaben (EXIST, vor Gründung)"
CATEGORY_RISK = "Höheres Risiko (gegründete Firmen, Ivens Suche)"
CATEGORIES = [CATEGORY_EARLY, CATEGORY_RISK]
ALL_SECTORS = "Alle Branchen"
ALL_STATUS = "Alle"
TOP_OPTIONS = [10, 20, 34]
QUERY_KEY = "iven"
LINKEDIN_SEARCH = "https://www.linkedin.com/search/results/people/?keywords="
NOT_COMPARABLE = ("Zwei getrennte Rankings: Die frühen Vorhaben bewertet unser Regelwerk (Team, Markt, Risiko, "
                  "Earliness). Ivens Firmen bewertet sein Regelwerk {rule} (Produkt & Technologie 40 %, Kunde & "
                  "Nutzen 35 %, Entwicklungsnachweis 25 %; belegte Untergrenze, offene Kriterien ohne Ersatzpunkte). "
                  "Die Scores sind nicht vergleichbar und werden deshalb nicht gemischt.")
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


def _fmt(value, missing: str = "offen") -> str:
    return missing if value is None else (f"{value:.1f}" if isinstance(value, float) and value % 1 else f"{value:.0f}")


def _date(text: str | None) -> str:
    if not text:
        return "offen"
    y, m, d = text.split("-")
    return f"{d}.{m}.{y}"


def founding_text(company: dict) -> str:
    f = company["founding"]
    if not f["earliest"]:
        return "offen"
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
    return "Auf LinkedIn suchen", LINKEDIN_SEARCH + quote(f"{person['name']} {company['name']}", safe=""), False


def mailto(company: dict) -> str | None:
    if not company.get("email"):
        return None
    subject = quote(f"Austausch zu {company['name']}", safe="")
    body = quote(f"Hallo,\n\nwir sind auf {company['name']} aufmerksam geworden und würden gerne mehr über den "
                 "Produktstand und Ihre ersten Kundenerfahrungen erfahren. Haben Sie Zeit für einen kurzen "
                 "Austausch?\n\nViele Grüße", safe="")
    return f"mailto:{quote(company['email'], safe='@')}?subject={subject}&body={body}"


def category_switch(data: dict | None) -> str:
    """Segmented control between the two categories; EXIST is the default."""
    if not data:
        return CATEGORY_EARLY
    saved = st.session_state.get("portfolio_category", CATEGORY_EARLY)
    labels = {CATEGORY_EARLY: CATEGORY_EARLY, CATEGORY_RISK: f"{CATEGORY_RISK} · {len(data['companies'])}"}
    choice = st.segmented_control("Kategorie", CATEGORIES, key="dashboard_category", format_func=labels.get,
                                  default=saved if saved in CATEGORIES else CATEGORY_EARLY,
                                  help="Zwei getrennte Suchen mit eigenen Regelwerken; die Scores werden nicht gemischt.")
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
    heading(f"Höheres Risiko · gegründete Firmen · Stand {_date(data['source_snapshot_date'])}",
            f"{len(companies)} registrierte Firmen. Ivens Suche.",
            "Bereits gegründete Unternehmen (GLEIF-Register, Förderprojekte, Firmenwebsites) aus den letzten "
            f"{data['max_age_months']} Monaten. Später als unsere EXIST-Vorhaben, daher mehr Konkurrenz um den Deal "
            "und ein höheres Risiko, zu spät zu kommen.")
    st.caption(f"HERKUNFT: {origin(data).upper()} · LAUF {data['run_id']} · STICHTAG {_date(data['as_of'])}")
    st.info(NOT_COMPARABLE.format(rule=data["rule_version"]), icon="ℹ️")

    sectors = [ALL_SECTORS, *sorted({s for c in companies for s in c["sectors"]})]
    statuses = [ALL_STATUS, *sorted({c["status"] for c in companies})]
    risks = [ALL_STATUS, *sorted({c["risk"] for c in companies})]
    a, b, c_, d = st.columns([1.3, 1, 1.3, .8])
    sector = a.selectbox("Branche", sectors, key="iven_filter_sector",
                         index=sectors.index(_saved("iven_sector", sectors, ALL_SECTORS)))
    status = b.selectbox("Status", statuses, key="iven_filter_status",
                         index=statuses.index(_saved("iven_status", statuses, ALL_STATUS)))
    risk = c_.selectbox("Risiko (Ivens Label)", risks, key="iven_filter_risk",
                        index=risks.index(_saved("iven_risk", risks, ALL_STATUS)))
    top_n = d.selectbox("Ranking anzeigen", TOP_OPTIONS, key="iven_filter_top",
                        index=TOP_OPTIONS.index(_saved("iven_top", TOP_OPTIONS, 20)),
                        format_func=lambda x: "Alle" if x == TOP_OPTIONS[-1] else f"Top {x}")
    st.session_state.update(iven_sector=sector, iven_status=status, iven_risk=risk, iven_top=top_n)
    shown = filter_companies(companies, sector, status, risk, top_n)

    scored = [c for c in shown if c["score"] is not None]
    mean_score = _mean(c["score"] for c in scored)
    mean_product = _mean(c["company_score"] for c in scored)
    mean_market = _mean(c["market_score"] for c in scored)
    kpi_cards([
        ("Bewertbar", f"{len(scored)} / {len(shown)}", f"{len(shown) - len(scored)} mit offenen Nachweisen (Score offen)",
         100 * len(scored) / len(shown) if shown else 0),
        ("Ø Screening-Score", _fmt(mean_score, "—"), "Belegte Untergrenze · höher ist besser", mean_score or 0),
        ("Ø Produkt & Technologie", _fmt(mean_product, "—"), "Ivens Unternehmensscore · höher ist besser", mean_product or 0),
        ("Ø Kunde & Nutzen", _fmt(mean_market, "—"), "Ivens Marktpotenzialscore · höher ist besser", mean_market or 0),
    ], dark_first=True)
    st.caption(f"Gesamt: {len(ranked)} bewertbar, {len(companies) - len(ranked)} mit offenen Nachweisen. "
               "Mittelwerte nur über bewertbare Firmen der Auswahl. Risiko ist bei Iven ein Prüf-Label, kein Zahlenwert.")
    if not shown:
        st.info("Keine Firma passt zu den Filtern.")
        return
    st.subheader("Ivens Ranking")
    st.caption("Reihenfolge und Werte exakt wie in Ivens Referenzlauf (Ergebnisse/Longlist.csv). Klick öffnet den Deep Dive.")
    rows = [{"Rang": c["rank"], "Unternehmen": c["name"], "Branchen": ", ".join(c["sectors"]) or "offen",
             "Status": c["status"], "Score": c["score"], "Produkt & Technologie": c["company_score"],
             "Kunde & Nutzen": c["market_score"], "Entwicklungsnachweis": c["validation_score"],
             "Risiko": c["risk"], "Stage": c["stage"], "Gründung": founding_text(c), "Website": c["website"]}
            for c in shown]
    config = {
        "Rang": st.column_config.NumberColumn("#", width="small", format="%d"),
        "Unternehmen": st.column_config.TextColumn("Unternehmen / Deep Dive", width="medium"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=SCORE_MAX, format="%.1f",
                                                 help="Ivens Screening-Score (belegte Untergrenze). Leer = offen."),
        "Produkt & Technologie": st.column_config.NumberColumn("Produkt", format="%.0f"),
        "Kunde & Nutzen": st.column_config.NumberColumn("Markt", format="%.0f"),
        "Entwicklungsnachweis": st.column_config.NumberColumn("Nachweis", format="%.0f"),
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
    st.caption(f"Quelle: {data['reference_file']} ({origin(data)}). Werte unverändert übernommen; "
               "keine Neubewertung im Dashboard. Handprüfung vor jedem Kontakt.")


def back():
    st.query_params.pop(QUERY_KEY, None)
    st.session_state.table_generation = st.session_state.get("table_generation", 0) + 1


def _link(url: str, label: str = "Quelle") -> str:
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'


def render_deep_dive(company: dict, data: dict, early_leads=None):
    """Description, hypothesis, scorecard, open points, evidence with links, team with LinkedIn, contact."""
    st.button("Zurück zur Übersicht", on_click=back, key="iven_back")
    heading(f"Höheres Risiko / Firmen Deep Dive · Rang {company['rank']} bei Iven", company["name"],
            f"{', '.join(company['sectors']) or 'Branche offen'} · {company['stage']} · Gründung {founding_text(company)}")
    tone = "good" if company["queue"] == "ranked" else "warn"
    st.markdown(chips([(company["status"], tone), (company["risk"], "warn"), (company["htgf_fit"], ""),
                       (f"Datenabdeckung {company['coverage'] * 100:.0f} %", "")]), unsafe_allow_html=True)
    st.caption(f"Herkunft: {origin(data)} · Werte unverändert aus Ivens Referenzlauf")
    for lead in also_early(company, early_leads):
        st.info(f"Auch unter „{CATEGORY_EARLY}“ als **{md_escape(lead.name)}** geführt, dort mit unserem eigenen Score. "
                "Die beiden Scores sind nicht vergleichbar.", icon="🔁")
    st.markdown("**Produktbeschreibung**")
    st.write(md_escape(company["summary"]))
    cols = st.columns(5)
    upper = (f"Obergrenze {_fmt(company['score_upper'])}" if company["score_upper"] not in (None, company["score"]) else None)
    cols[0].metric("Screening-Score", f"{_fmt(company['score'])} / 100" if company["score"] is not None else "offen",
                   delta=upper, delta_color="off")
    for column, label, value in zip(cols[1:4], ["Produkt & Technologie", "Kunde & Nutzen", "Entwicklungsnachweis"],
                                    [company["company_score"], company["market_score"], company["validation_score"]]):
        column.metric(label, f"{_fmt(value)} / 100" if value is not None else "offen")
    cols[4].metric("Risiko (Label)", company["risk"].replace("Prüfbedarf: ", "") or "offen",
                   help=f"Ivens Risiko-Label: {company['risk']}. Kein Zahlenwert.")
    st.caption("Ivens Scorecard: Produkt & Technologie 40 %, Kunde & Nutzen 35 %, Entwicklungsnachweis 25 %. "
               "Offene Kriterien erhalten keine Ersatzpunkte; Score = belegte Untergrenze. Höher ist besser.")
    main, contact = st.columns([2.2, 1], gap="large")
    with main:
        st.markdown('<div class="fr-thesis"><div class="fr-eyebrow">Investmenthypothese</div>'
                    f'<p>{escape(company["thesis"])}</p></div>', unsafe_allow_html=True)
        st.markdown(f"**Warum jetzt Kontakt?** {md_escape(company['why'])}")
        st.markdown(f"**Erste Frage:** {md_escape(company['question'])}")
        tabs = st.tabs(["Scorecard", "Offene Punkte & Risiko", "Belege & Quellen", "Team"])
        with tabs[0]:
            for c in company["criteria"]:
                with st.container(border=True):
                    points = f"{c['points']} / 100" if c["points"] is not None else "offen"
                    st.markdown(f"**{md_escape(c['label'])}** · Gewicht {c['weight']} % · **{points}**")
                    st.caption(md_escape(c["reason"]))
                    if c["facts"]:
                        st.caption("Gestützt auf: " + ", ".join(md_escape(f) for f in c["facts"]))
            st.caption(f"Segment: {company['segment']}")
        with tabs[1]:
            st.warning(f"Risiko: {md_escape(company['risk'])}", icon="⚠️")
            fact("HTGF-Fit (Ivens Einschätzung)", company["htgf_fit"])
            if company["reasons"]:
                st.markdown("**Offene Nachweise**")
                for reason in company["reasons"]:
                    st.markdown(f"• {md_escape(reason)}")
            st.markdown("**Nächste Schritte**")
            for step in company["next_steps"]:
                st.markdown(f"• {md_escape(step)}")
        with tabs[2]:
            f = company["founding"]
            if f["basis"]:
                st.caption(f"Gründung: {md_escape(founding_text(company))} · {md_escape(f['basis'])}")
            for item in company["facts"]:
                with st.container(border=True):
                    st.markdown(f"**{md_escape(item['label'])}:** {md_escape(item['value'])}")
                    st.caption(f"„{md_escape(item['quote'])}“ · {md_escape(item['basis'])}")
                    if item["url"].startswith(("https://", "http://")):
                        st.markdown(_link(item["url"], "Beleg öffnen"), unsafe_allow_html=True)
            st.markdown("**Abgerufene Quellen**")
            for s in company["sources"]:
                if s["url"].startswith(("https://", "http://")):
                    st.markdown(f"{_link(s['url'], s['title'] or s['url'])} <small>· abgerufen {escape(s['retrieved_at'][:10])}</small>",
                                unsafe_allow_html=True)
            for m in company["market_comparisons"]:
                st.markdown(f"Vergleich **{md_escape(m['name'])}**: {md_escape(m['text'])} ", unsafe_allow_html=False)
                st.markdown(_link(m["url"]), unsafe_allow_html=True)
        with tabs[3]:
            if not company["team"]:
                team_fact = next((x for x in company["facts"] if x["key"] == "team"), None)
                st.caption("Noch keine Person namentlich belegt." + (f" Website nennt: „{team_fact['quote']}“" if team_fact else ""))
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
            st.subheader("Gründer kontaktieren")
            names = [p["name"] for p in company["team"]]
            st.write(md_escape(", ".join(names) or "Gründer noch nicht namentlich belegt"))
            for i, person in enumerate(company["team"]):
                label, url, found = linkedin(person, company)
                st.link_button(f"{label} · {person['name']}", url, width="stretch", key=f"iven_li_{company['id']}_{i}",
                               help="Profil aus Ivens Team-Recherche." if found else
                                    "Kein Profil belegt: öffnet die LinkedIn-Personensuche nach Name und Firma.")
            if names:
                st.caption("LinkedIn öffnet sich in einem neuen Tab; es wird nichts automatisch gesendet.")
            fact("E-Mail (Firmenpostfach)", company["email"] or "Noch nicht verfügbar")
            if url := mailto(company):
                st.link_button("Kontakt aufnehmen", url, type="primary", width="stretch")
                st.caption("Öffnet einen E-Mail-Entwurf. Kein automatischer Versand.")
            if company["website"]:
                st.link_button("Unternehmenswebsite", company["website"], width="stretch")
            fact("Entdeckt über", "Ivens Firmen-Suche (GLEIF / Förderprojekt / Website)")
        import json
        st.download_button("Firmen-Dossier exportieren", json.dumps(company, ensure_ascii=False, indent=2),
                           file_name=f"{company['id']}.json", mime="application/json", width="stretch",
                           key=f"iven_export_{company['id']}")
