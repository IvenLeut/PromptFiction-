"""Regressions from the live run on Förderkatalog-sourced leads (no website, no founders, one catalogue signal).

Real cases: Procado (03EGTBY182), sensAI (03EFBY0323), ExoAssist (03EFNW0397). Everything offline: the
catalogue row is built by hand, idw/Wayback answers are synthetic and injected via `fetch=`.
"""
from datetime import date
from functools import partial

from context.classify import classify_texts
from context.engine import enrich, field_terms, parse_catalogue
from context.foekat import _grant_from
from context.idw import idw_lookup, search_url
from context.lookup import Lookup
from context.wayback import cdx_url, web_history_lookup
from models import Evidence, Grant, Industry, RawLead, SourceSignal

FK = "https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz="


def catalogue(fkz, programme, thema, recipient, executing, laufzeit, summe):
    return (f"Förderkennzeichen: {fkz}\nProgramm: {programme}\nThema: {thema}\nFörderempfänger: {recipient}\n"
            f"Ausführende Stelle: {executing}\nLaufzeit: {laufzeit}\nFördersumme: {summe}\nÖffentliche Förderung: ja")


def sourced_lead(lead_id, name, fkz, start, text, location):
    url = FK + fkz
    return RawLead(id=lead_id, name=name, description=text, industry=Industry.INDUSTRIAL, country="DE", location=location,
                   source_url=url, source_name="Förderkatalog",
                   signals=[SourceSignal(source="Förderkatalog", type="exist_projekt", url=url, date=start, evidence=text,
                                         subject_lead_id=lead_id)])


PROCADO = catalogue("03EGTBY182", "EXIST-Gründungsstipendium", "Procado", "Technische Universität München, München, Bayern",
                    "Technische Universität München - TUM Venture Labs, München, Bayern", "01.04.2025 bis 31.03.2026",
                    "135.000,00 EUR")
SENSAI = catalogue("03EFBY0323", "EXIST-Forschungstransfer", "sensAI", "Universität Augsburg, Augsburg, Bayern",
                   "Universität Augsburg - Lehrstuhl für Embedded Intelligence, Augsburg, Bayern", "01.10.2024 bis 30.09.2026",
                   "598.747,00 EUR")
EXO = catalogue("03EFNW0397", "EXIST-Forschungstransfer", "ExoAssist", "Technische Hochschule Köln, Köln, Nordrhein-Westfalen",
                "Technische Hochschule Köln - Institut für Produktentwicklung und Konstruktionstechnik - Prof. Dr. Jörg Luderich, "
                "Köln, Nordrhein-Westfalen", "01.03.2025 bis 28.02.2027", "1.180.000,00 EUR")


def procado():
    return sourced_lead("procado", "Procado", "03EGTBY182", date(2025, 4, 1), PROCADO, "München")


def sensai():
    return sourced_lead("sensai", "sensAI", "03EFBY0323", date(2024, 10, 1), SENSAI, "Augsburg")


def exoassist():
    return sourced_lead("exo", "ExoAssist", "03EFNW0397", date(2025, 3, 1), EXO, "Köln")


def no_op(*a, **k):
    return Lookup()


def lookups(**changes):
    base = {"cache": None, "model": None, "imprint": no_op, "grants": lambda *a, **k: ([], Lookup()),
            "web_history": no_op, "idw": no_op, "author": lambda *a, **k: (None, Lookup()), "classify": no_op, "patents": None}
    return base | changes


# --- 1. offline grant -----------------------------------------------------------------------------

def test_parse_catalogue_new_and_old_format():
    new = parse_catalogue(catalogue("03EFBW0275", "EXIST-Forschungstransfer", "SpinMagIC",
                                    "Universität Stuttgart, Stuttgart, Baden-Württemberg",
                                    "Universität Stuttgart - Institut für Intelligente Sensorik, Stuttgart, Baden-Württemberg",
                                    "01.09.2024 bis 30.09.2026", "972.638,00 EUR"))
    old = parse_catalogue("FKZ 03EFBW0275; Programm: EXIST-Forschungstransfer; Thema: SpinMagIC; Förderempfänger: Universität "
                          "Stuttgart; Ausführende Stelle: Universität Stuttgart - IIS; Laufzeit: 01.09.2024–30.09.2026; "
                          "Summe: 972.638,00 €")
    for facts in (new, old):
        assert facts["fkz"] == "03EFBW0275" and facts["programme"] == "EXIST-Forschungstransfer"
        assert facts["start"] == date(2024, 9, 1) and facts["end"] == date(2026, 9, 30) and facts["amount_eur"] == 972638
        assert facts["recipient"].startswith("Universität Stuttgart")
    assert parse_catalogue("FKZ 03EFTEST01 Testwerk") is None      # no labels: nothing to build


def test_light_mode_builds_grant_from_catalogue_signal():
    lead = enrich(procado(), light=True)
    (grant,) = lead.grants
    assert (grant.programme, grant.reference, grant.amount_eur, grant.start, grant.end) == (
        "EXIST-Gründungsstipendium", "03EGTBY182", 135000, date(2025, 4, 1), date(2026, 3, 31))
    assert grant.recipient == "Technische Universität München, München, Bayern" and str(grant.url) == FK + "03EGTBY182"
    assert lead.funding_status == "non_vc_funded"
    (ev,) = [e for e in lead.evidence if e.field == "grants"]
    assert ev.source == "Förderkatalog" and ev.source_date == date(2025, 4, 1) and str(ev.url) == FK + "03EGTBY182"
    assert ev.finding.startswith("Förderkennzeichen: 03EGTBY182\nProgramm: EXIST-Gründungsstipendium")


def test_live_grant_with_same_fkz_wins_and_recipient_is_the_institution_hint():
    calls = []

    def grants(name, *, institution, reference, cache, fetch=None):
        calls.append(("grants", institution, reference))
        return [Grant(programme="EXIST-Gründungsstipendium", reference="03EGTBY182", recipient="TUM (live)", amount_eur=135000,
                      start=date(2025, 4, 1), url=FK + "03EGTBY182&live=1")], Lookup()

    def idw(name, *, institution, founders, cache, fetch=None):
        calls.append(("idw", institution))
        return Lookup()

    lead = enrich(procado(), lookups=lookups(grants=grants, idw=idw))
    assert [g.recipient for g in lead.grants] == ["TUM (live)"]
    assert ("grants", "Technische Universität München", "03EGTBY182") in calls
    assert ("idw", "Technische Universität München") in calls


# --- 2./3. idw namesakes --------------------------------------------------------------------------

def idw_with(*articles, hint=None):
    def idw(name, *, institution, founders, cache, fetch=None):
        result = Lookup()
        for url, when, text, statement in articles:
            result.signals.append(SourceSignal(source="idw", type="idw", url=url, date=when, evidence=text))
            result.evidence.append(Evidence(field="idw", url=url, finding=text.split("\n")[0], source="idw", source_date=when))
            result.evidence.append(Evidence(field="founding_statement", url=url, finding=statement, source="idw", source_date=when))
        if hint:
            result.fields["founding_year_hint"] = hint
        return result
    return idw


def test_procado_founding_year_from_2013_namesake_is_rejected():
    statement = "Die procado Consulting GmbH wurde 2013 gegründet."
    article = ("https://idw-online.de/de/news1", date(2013, 5, 2), "procado Consulting berät Kliniken\n" + statement, statement)
    lead = enrich(procado(), lookups=lookups(idw=idw_with(article, hint=2013)))
    assert lead.founding_year_hint is None
    assert "idw: Gründungsjahr 2013 verworfen (vor erstem Signal)" in lead.enrichment_errors
    assert lead.first_signal_date == date(2025, 4, 1)               # the 2013 article does not date the lead
    assert not any(str(e.url) == article[0] for e in lead.evidence)


def test_weak_founding_hint_needs_whole_name_and_an_article_about_the_lead():
    other = ("https://idw-online.de/de/news2", date(2025, 6, 1), "Medizintechnik in Bayern\nDie Procadomed GmbH wurde gegründet.",
             "Die Procadomed GmbH wurde gegründet.")
    assert enrich(procado(), lookups=lookups(idw=idw_with(other))).founding_year_hint is None
    once = ("https://idw-online.de/de/news3", date(2025, 6, 1), "Gründungen an der TUM\nAuch Procado wurde gegründet.",
            "Auch Procado wurde gegründet.")
    assert enrich(procado(), lookups=lookups(idw=idw_with(once))).founding_year_hint is None   # one mention, not in title
    about = ("https://idw-online.de/de/news4", date(2025, 6, 1), "Procado startet\nProcado wurde im Mai gegründet.",
             "Procado wurde im Mai gegründet.")
    assert enrich(procado(), lookups=lookups(idw=idw_with(about))).founding_year_hint == 2025


def synthetic_search(items):
    rows = "".join("<div class=\"row\"><div class=\"two columns\"><p>%s</p></div><div class=\"nine columns\">"
                   "<h6><a href=\"/de/news%d\">%s</a></h6>\n<p><em>%s</p></em>\n<p>%s</p></div></div><hr>" % item for item in items)
    return "<h5>Es wurden %d Ergebnisse gefunden.</h5><hr>%s<!-- end -->" % (len(items), rows)


def synthetic_article(title, body, when):
    return ("<p><em>\n%s\n</em></p>\n<h4>%s</h4>\n<h5 class=\"subheader\">Pressestelle<br/>"
            "<a href=\"/de/institution9\">Uni</a></h5>\n<p>%s</p>\n<hr/><h5>Wissenschaftliche Ansprechpartner:</h5>"
            % (when, title, body))


def sensai_lookups():
    idw_pages = {
        search_url("sensAI"): synthetic_search([
            ("02.03.2019 10:00", 7, "BiosenSAI: Biosensoren aus Augsburg", "Uni", "Das Projekt BiosenSAI misst Glukose."),
            ("05.11.2024 10:00", 8, "Messe-Rückblick", "Uni Augsburg", "Mit dabei: sensAI."),
        ]),
        "https://idw-online.de/de/news7": synthetic_article("BiosenSAI: Biosensoren aus Augsburg",
                                                            "Das Projekt BiosenSAI misst Glukose im Schweiß.", "02.03.2019 10:00"),
        "https://idw-online.de/de/news8": synthetic_article("Messe-Rückblick", "Viele Teams stellten aus. Mit dabei: sensAI.",
                                                            "05.11.2024 10:00"),
    }
    crunchbase = cdx_url("crunchbase.com/organization/sensai")
    cdx = {crunchbase: [["timestamp", "original", "statuscode"],
                        ["20190701000000", "https://www.crunchbase.com/organization/sensai", "200"]]}
    return lookups(idw=partial(idw_lookup, fetch=lambda url: idw_pages[url]),
                   web_history=partial(web_history_lookup, fetch=lambda url: cdx.get(url, [])))


def test_sensai_namesake_profile_and_substring_article_are_not_counted():
    lead = enrich(sensai(), lookups=sensai_lookups())
    assert lead.in_databases is None and lead.first_db_date is None and not lead.database_urls
    assert any(e.startswith("wayback: Profil https://web.archive.org/web/20190701000000/") and "vermutlich Namensvetter" in e
               for e in lead.enrichment_errors)
    assert lead.first_signal_date == date(2024, 10, 1)
    # BiosenSAI (2019) is dropped; the round-up with one whole-word mention stays as "Erwähnung"
    assert [str(s.url) for s in lead.scoring_sources if s.type == "idw"] == ["https://idw-online.de/de/news8"]
    assert {e.field for e in lead.evidence if str(e.url) == "https://idw-online.de/de/news8"} == {"idw_mention"}
    assert not any("news7" in str(e.url) for e in lead.evidence)
    assert [g.amount_eur for g in lead.grants] == [598747]


def test_wayback_not_before_also_guards_first_web_capture():
    cdx = {cdx_url("sensai.de"): [["timestamp", "original", "statuscode"], ["20150101000000", "http://sensai.de/", "200"]]}
    result = web_history_lookup("https://sensai.de", "sensAI", cache=None, fetch=lambda url: cdx.get(url, []),
                                not_before=date(2024, 10, 1))
    assert "first_web_capture" not in result.fields and not result.signals
    assert any(e.startswith("wayback: Website ") for e in result.errors)
    recent = web_history_lookup("https://sensai.de", "sensAI", cache=None, fetch=lambda url: cdx.get(url, []))
    assert recent.fields["first_web_capture"] == date(2015, 1, 1)       # without not_before: unchanged behaviour


def test_crunchbase_profile_after_project_start_still_counts():
    cdx = {cdx_url("crunchbase.com/organization/sensai"): [["timestamp", "original", "statuscode"],
                                                           ["20250301000000", "https://www.crunchbase.com/organization/sensai", "200"]]}
    result = web_history_lookup(None, "sensAI", cache=None, fetch=lambda url: cdx.get(url, []), not_before=date(2024, 10, 1))
    assert result.fields["in_databases"] is True and result.fields["first_db_date"] == date(2025, 3, 1)


# --- 5. project lead is no partner ----------------------------------------------------------------

def test_exoassist_project_lead_and_own_institute_are_not_partners():
    text = ("ExoAssist: Exoskelett für die Pflege\n"
            "ExoAssist entwickelt gemeinsam mit Prof. Dr. Jörg Luderich ein Exoskelett.\n"
            "Das Team arbeitet zusammen mit Jörg Luderich am Prototyp.\n"
            "In Zusammenarbeit mit dem Institut für Produktentwicklung und Konstruktionstechnik entstehen Tests.\n"
            "Pilotprojekt mit der Uniklinik Köln läuft.")
    article = SourceSignal(source="idw", type="idw", url="https://idw-online.de/de/news9", date=date(2025, 5, 1), evidence=text)
    exclude = ["Technische Hochschule Köln, Köln, Nordrhein-Westfalen",
               "Technische Hochschule Köln - Institut für Produktentwicklung und Konstruktionstechnik - Prof. Dr. Jörg Luderich"]
    result = classify_texts("ExoAssist", [article], model=None, cache=None, exclude_names=exclude)
    assert [(p.name, p.kind) for p in result.fields.get("partners", [])] == [("Uniklinik Köln", "pilot")]

    def idw(name, *, institution, founders, cache, fetch=None):
        return Lookup(signals=[article])

    lead = enrich(exoassist(), lookups=lookups(idw=idw, classify=classify_texts))
    assert [p.name for p in lead.partners] == ["Uniklinik Köln"]


# --- 6./7. catalogue text hygiene -----------------------------------------------------------------

def test_recipient_is_not_repeated_when_executing_unit_starts_with_it():
    grant, _ = _grant_from({"fkz": "03EFBY0323", "recipient": "Universität Augsburg",
                            "executing": "Universität Augsburg - Lehrstuhl für Embedded Intelligence"}, None)
    assert grant.recipient == "Universität Augsburg - Lehrstuhl für Embedded Intelligence"
    grant, _ = _grant_from({"fkz": "03EFBY0323", "recipient": "Universität Augsburg", "executing": "Universität Augsburg"}, None)
    assert grant.recipient == "Universität Augsburg"


def test_field_terms_skip_catalogue_boilerplate():
    terms = {t.lower() for t in field_terms(sensai(), limit=50)}
    assert not terms & {"förderempfänger", "förderkennzeichen", "ausführende", "stelle", "laufzeit", "forschungstransfer",
                        "exist-forschungstransfer", "fördersumme"}
    assert "embedded" in terms and "intelligence" in terms
