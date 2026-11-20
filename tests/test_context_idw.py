"""Offline tests for context/idw.py. Fixtures are real idw-online.de pages recorded on 2026-11-20,
trimmed to the relevant block and with personal contact data removed."""
from datetime import date
from pathlib import Path

import pytest

from context.cache import NoCache
from context.http import FetchError
from context.idw import (MENTION_SOURCE, detect_mentions, distinctive_word, fold, founding_year, idw_lookup,
                         parse_article, parse_search, search_term, search_url, select_items, sentences,
                         strip_legal_form, surnames)

FIXTURES = Path(__file__).parent / "fixtures" / "context"


def load(name):
    return (FIXTURES / ("idw_%s.html" % name)).read_text(encoding="utf-8")


def article_url(news_id):
    return "https://idw-online.de/de/news%d" % news_id


def fetch_from(responses, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if url not in responses:
            raise AssertionError("unerwartete idw-Anfrage: " + url)
        data = responses[url]
        if isinstance(data, Exception):
            raise data
        return data
    return fetch


def run(name, responses, *, institution=None, founders=(), calls=None):
    return idw_lookup(name, institution=institution, founders=list(founders), cache=NoCache(),
                      fetch=fetch_from(responses, calls))


def synthetic_article(title, body, when="01.02.2024 10:00", institution="Testuniversität"):
    return (
        "<p><em>\n%s\n</em></p>\n<h4>%s</h4>\n<h5 class=\"subheader\">Pressestelle <em>Kommunikation</em><br/>"
        "<a href=\"/de/institution999\">%s</a></h5>\n<p>%s</p>\n"
        "<hr/><h5>Wissenschaftliche Ansprechpartner:</h5><p>Dr. Geheim, Tel.: 0000, E-Mail: x@y.z</p>"
        "<hr><p><strong>Merkmale dieser Pressemitteilung:</strong> Journalisten</p>"
    ) % (when, title, institution, body)


def synthetic_search(items):
    """items: list of (date, news_id, title, institution, snippet)."""
    rows = []
    for when, news_id, title, institution, snippet in items:
        rows.append(
            "<div class=\"row\"><div class=\"two columns\"><p>%s</p></div><div class=\"nine columns\">"
            "<h6><a href=\"/de/news%d\">%s</a></h6>\n<p><em>%s</p></em>\n<p>%s</p></div></div><hr>"
            % (when, news_id, title, institution, snippet)
        )
    return "<h5>Es wurden %d Ergebnisse gefunden.</h5><hr>%s<!-- end -->" % (len(items), "".join(rows))


# --- helpers ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, term", [
    ("SpinMagIC GmbH", "SpinMagIC"),
    ("EXIST-Forschungstransfer", "EXIST Forschungstransfer"),
    ("Quantenfräse UG (haftungsbeschränkt) i.G.", "Quantenfräse"),
    ("Side-Ro GaIn GmbH & Co. KG", "Side Ro GaIn"),
    ("  AIRLense  ", "AIRLense"),
])
def test_search_term_strips_legal_forms_and_hyphens(name, term):
    assert search_term(name) == term


def test_search_url_has_no_hyphen_and_expected_parameters():
    url = search_url(search_term("EXIST-Forschungstransfer"))
    assert url.startswith("https://idw-online.de/de/simplesearch?")
    assert "words=EXIST+Forschungstransfer" in url
    assert "scope=press_release" in url and "sort_order=start_datetime" in url
    assert "_form_=Results" in url and "page=1" in url


def test_fold_handles_umlauts_and_case():
    assert fold("Quantenfräse Müller ÖKO") == "quantenfraese mueller oeko"
    assert fold("Straße") == "strasse"
    assert fold("Café") == "cafe"


def test_strip_legal_form_and_distinctive_word():
    assert strip_legal_form("Neue Materialien Lausitz GmbH") == "Neue Materialien Lausitz"
    assert distinctive_word("Neue Materialien Lausitz GmbH") == "Materialien"
    assert distinctive_word("Team Labs GmbH") is None
    assert distinctive_word("SpinMagIC") == "SpinMagIC"


def test_surnames_drop_titles_and_duplicates():
    assert surnames(["Dr. Rohan Jain", "Prof. Dr. Katrin Pollmann", "Rohan Jain", "Li"]) == ["jain", "pollmann"]


def test_sentences_do_not_split_after_abbreviations():
    text = "Das Team um Dr. Matthias Beuting erhält rund 1,4 Mio. Euro. Zweiter Satz.\nDritter Block."
    assert sentences(text) == ["Das Team um Dr. Matthias Beuting erhält rund 1,4 Mio. Euro.", "Zweiter Satz.",
                               "Dritter Block."]


# --- search parsing ---------------------------------------------------------------------------------

def test_parse_search_spinmagic_items():
    count, items = parse_search(load("search_spinmagic"))
    assert count == 5 and len(items) == 5
    assert [i["path"] for i in items] == ["/de/news849480", "/de/news849421", "/de/news844318", "/de/news844315",
                                          "/de/news839134"]
    first = items[0]
    assert first["url"] == "https://idw-online.de/de/news849480"
    assert first["when"].date() == date(2025, 3, 24)
    assert first["institution"] == "Universität Stuttgart"
    assert "The spin-off SpinMagIC will be presenting" in first["snippet"]  # <em class='label'> stripped
    assert items[3]["title"] == "Start-up bringt Quantensensor zur Marktreife: SpinMagIC erhält EXIST-Forschungstransfer-Förderung"
    assert items[4]["institution"] == "Helmholtz-Zentrum Berlin für Materialien und Energie GmbH"


def test_parse_search_zero_hits():
    count, items = parse_search(load("search_none"))
    assert count == 0 and items == []


# --- matching and selection -------------------------------------------------------------------------

def test_select_items_matches_name_with_umlauts_case_insensitive():
    page = synthetic_search([
        ("02.02.2024 10:00", 1, "Ausgründung QUANTENFRAESE startet", "Uni A", "Text ohne Namen."),
        ("01.02.2024 10:00", 2, "Etwas anderes", "Uni A", "Die Quantenfräse GmbH baut Maschinen."),
        ("03.02.2024 10:00", 3, "Gar nichts", "Uni A", "Kein Bezug."),
    ])
    _, items = parse_search(page)
    kept = select_items(items, "Quantenfräse GmbH", [], None)
    assert [i["path"] for i in kept] == ["/de/news1", "/de/news2"]


def test_select_items_matches_two_founder_surnames_but_not_one():
    page = synthetic_search([
        ("02.02.2024 10:00", 1, "Preis für Forschung", "Uni A", "Anna Müller und Jonas Schäfer gründen aus."),
        ("01.02.2024 10:00", 2, "Preis für Forschung", "Uni A", "Anna Müller forscht weiter."),
    ])
    _, items = parse_search(page)
    kept = select_items(items, "Unbekannt Labs", ["Dr. Anna Mueller", "Jonas Schaefer"], None)
    assert [i["path"] for i in kept] == ["/de/news1"]


def test_select_items_keeps_five_newest_and_prefers_institution():
    rows = [("%02d.01.2024 10:00" % d, d, "Testfirma Meldung %d" % d, "Uni B" if d != 3 else "Uni A", "") for d in range(1, 8)]
    _, items = parse_search(synthetic_search(rows))
    kept = select_items(items, "Testfirma GmbH", [], None)
    assert [i["path"] for i in kept] == ["/de/news7", "/de/news6", "/de/news5", "/de/news4", "/de/news3"]
    kept = select_items(items, "Testfirma GmbH", [], "Universität A (Uni A)")
    assert kept[0]["path"] == "/de/news3"
    assert [i["path"] for i in kept[1:]] == ["/de/news7", "/de/news6", "/de/news5", "/de/news4"]


# --- article parsing --------------------------------------------------------------------------------

def test_parse_article_siderogain():
    art = parse_article(load("news876491"))
    assert art["date"] == date(2026, 8, 28)
    assert art["title"] == "Biomoleküle retten Rohstoffe: HZDR-Spin-off Siderogain gegründet"
    assert art["institution"] == "Helmholtz-Zentrum Dresden-Rossendorf"
    body = art["body"]
    assert body.startswith("Mit einem biotechnologischen Verfahren")
    assert "patentierte Technologie" in body
    assert "Freiberger Compound Materials (FCM) GmbH" in body
    assert "Vom Laborversuch zur Pilotanlage\nDie ersten Versuche" in body  # line breaks per block kept
    assert "Simon Schmitt" not in body                                       # press officer subheader dropped
    assert "Wissenschaftliche Ansprechpartner" not in body and "Tel." not in body and "E-Mail" not in body
    assert "Merkmale dieser Pressemitteilung" not in body


def test_parse_article_without_contact_section_cuts_at_next_marker():
    page = "<em>\n01.02.2024 10:00\n</em>\n<h4>Titel &amp; mehr</h4><p>Absatz eins.<br />Absatz zwei.</p>" \
           "<hr/><h5>Weitere Informationen:</h5><p><a href=\"https://x\">x</a></p>"
    art = parse_article(page)
    assert art == {"date": date(2024, 2, 1), "title": "Titel & mehr", "institution": "",
                   "body": "Absatz eins.\nAbsatz zwei."}


def test_parse_article_tolerates_garbage():
    assert parse_article("") == {"date": None, "title": "", "institution": "", "body": ""}
    assert parse_article("<html>nichts</html>")["body"] == ""


# --- mention detectors ------------------------------------------------------------------------------

def test_detect_founding_statement():
    text = ("Die Testfirma GmbH wurde im März gegründet. Das Wetter war schön. "
            "Die Forscher haben zusammen mit Partnern ein Start-up gegründet. "
            "Die Stadt wurde 1200 gegründet.")
    found = detect_mentions(text, "Testfirma GmbH")
    assert found["founding_statement"] == ["Die Testfirma GmbH wurde im März gegründet.",
                                           "Die Forscher haben zusammen mit Partnern ein Start-up gegründet."]
    assert found["grants_mention"] == [] and found["ip_mention"] == []


def test_detect_grants_mention_but_not_english_exist():
    text = ("Testfirma erhält Förderung\nDas Team erhält EXIST-Forschungstransfer. Later a Gründungsstipendium followed. "
            "Such sensors do not exist today. Das exist Forschungstransfer-Programm fördert.")
    found = detect_mentions(text, "Testfirma GmbH")          # title names the lead -> every sentence qualifies
    assert found["grants_mention"] == ["Das Team erhält EXIST-Forschungstransfer.",
                                       "Later a Gründungsstipendium followed.",
                                       "Das exist Forschungstransfer-Programm fördert."]


def test_detect_ip_mention():
    text = "Testfirma: Schutzrechte\nDie Technologie ist patentiert. Ein Verfahren wurde zum Patent angemeldet. The patented method works. Kein Bezug."
    found = detect_mentions(text, "Testfirma")
    assert found["ip_mention"] == ["Die Technologie ist patentiert.", "Ein Verfahren wurde zum Patent angemeldet.",
                                   "The patented method works."]


def test_detect_mentions_in_a_round_up_only_from_sentences_naming_the_lead():
    """Regression (kiutra, idw news718959): a prize round-up about Blickfeld mentioned Kiutra once; Blickfeld's
    patents and founding date must not become kiutra's."""
    text = ("Start-up-Wettbewerb: Weitblick für das autonome Fahren\n"
            "Blickfeld heißt auch das Start-up, das Petit 2017 mit Dr. Mathias Müller an der TUM gegründet hat.\n"
            "Blickfeld hat mehr als 30 Patente angemeldet und beschäftigt bereits rund 70 Mitarbeiterinnen und Mitarbeiter.\n"
            "Kiutra hat eine Magnettechnologie entwickelt, um Quantencomputer zu kühlen, und wurde 2018 gegründet.\n"
            "Jedes Jahr werden an der TUM mehr als 70 technologieorientierte Unternehmen gegründet.")
    found = detect_mentions(text, "kiutra GmbH", ["Alexander Regnat", "Tomek Schulz"])
    assert found["ip_mention"] == []
    assert found["founding_statement"] == [
        "Kiutra hat eine Magnettechnologie entwickelt, um Quantencomputer zu kühlen, und wurde 2018 gegründet."]
    assert founding_year(found["founding_statement"][0], "kiutra GmbH") == 2018
    # a sentence naming only a founder surname qualifies too
    assert detect_mentions("Preise\nRegnat erhielt dafür ein EXIST-Gründerstipendium.", "kiutra", ["Alexander Regnat"])["grants_mention"] \
        == ["Regnat erhielt dafür ein EXIST-Gründerstipendium."]
    # statistics about founding are never a founding statement, even in an article about the lead
    about = detect_mentions("Kiutra gewinnt Preis\nJedes Jahr werden an der TUM 70 bis 80 Unternehmen gegründet.", "kiutra")
    assert about["founding_statement"] == []


@pytest.mark.parametrize("sentence, year", [
    ("Vier Wissenschaftler vom Lehrstuhl für Topologie korrelierter Systeme haben Kiutra 2018 gegründet.", 2018),
    ("Die kiutra GmbH wurde im Jahr 2018 gegründet.", 2018),
    ("Seit der Gründung 2018 wächst Kiutra stetig.", 2018),
    ("Kiutra was founded in 2018 as a spin-off of TUM.", 2018),
    ("Blickfeld wurde 2017 gegründet.", None),                      # another company
    ("Kiutra wurde gegründet.", None),                              # no year
    ("Kiutra: Die Stadt wurde 1200 gegründet.", None),              # implausible year
])
def test_founding_year_needs_lead_name_and_year(sentence, year):
    assert founding_year(sentence, "kiutra GmbH") == year


# --- recorded live cases ----------------------------------------------------------------------------

def test_spinmagic_title_hits_first_and_round_up_dropped():
    """Articles whose title names the lead are fetched first; the Hannover-Messe round-up (news849480,
    one mention, title without the name) is dropped because better articles exist."""
    responses = {search_url("SpinMagIC"): load("search_spinmagic"),
                 article_url(844315): load("news844315"), article_url(849480): load("news849480")}
    for other in (849421, 844318, 839134):
        responses[article_url(other)] = synthetic_article("SpinMagIC Meldung %d" % other, "Text über SpinMagIC.")
    calls = []
    res = run("SpinMagIC", responses, institution="Universität Stuttgart", founders=["Belal Alnajjar", "Anh Chu"],
              calls=calls)
    assert res.errors == []
    assert len(calls) == 6 and calls[0] == search_url("SpinMagIC")
    assert calls[1:4] == [article_url(i) for i in (844318, 844315, 839134)]      # title names SpinMagIC
    assert res.fields == {}
    assert [str(s.url) for s in res.signals] == [article_url(i) for i in (844318, 844315, 839134, 849421)]
    by_url = {str(s.url): s for s in res.signals}
    s = by_url[article_url(844315)]
    assert s.source == "idw" and s.type == "idw" and s.date == date(2024, 12, 5)
    assert s.evidence.startswith("Start-up bringt Quantensensor zur Marktreife: SpinMagIC erhält EXIST-Forschungstransfer-Förderung\n")
    assert "Belal Alnajjar" in s.evidence and "E-Mail" not in s.evidence and "Telefon" not in s.evidence
    assert len(s.evidence) <= 8000
    titles = [e for e in res.evidence if e.field == "idw"]
    assert len(titles) == 4 and titles[1].source_date == date(2024, 12, 5) and str(titles[1].url) == article_url(844315)
    grants = [e for e in res.evidence if e.field == "grants_mention" and str(e.url) == article_url(844315)]
    assert grants and "EXIST-Forschungstransfer" in grants[0].finding and grants[0].source_date == date(2024, 12, 5)
    assert not any(str(e.url) == article_url(849480) for e in res.evidence)


def test_round_up_is_kept_and_flagged_when_nothing_better_exists():
    responses = {search_url("SpinMagIC"): load("search_spinmagic"), article_url(849480): load("news849480")}
    for other in (849421, 844318, 844315, 839134):
        responses[article_url(other)] = FetchError("idw-online.de: HTTP 500")
    res = run("SpinMagIC", responses, institution="Universität Stuttgart")
    assert [str(s.url) for s in res.signals] == [article_url(849480)]
    assert res.signals[0].source == MENTION_SOURCE == "idw (Erwähnung)"
    (title,) = [e for e in res.evidence if e.field == "idw"]
    assert title.source == MENTION_SOURCE
    # the round-up's EXIST sentence names no founder and not the lead -> no grants_mention from it
    assert not [e for e in res.evidence if e.field in ("grants_mention", "founding_statement", "ip_mention")]


def test_founding_year_hint_from_article_sentence():
    responses = {search_url("Testfirma"): synthetic_search([("02.02.2024 10:00", 1, "Testfirma gewinnt Preis", "Uni A", "")]),
                 article_url(1): synthetic_article("Testfirma gewinnt Preis",
                                                   "Vier Forschende haben Testfirma 2021 gegründet. Jedes Jahr werden an der Uni 50 Unternehmen gegründet.")}
    res = run("Testfirma GmbH", responses)
    assert res.fields == {"founding_year_hint": 2021}
    hint = [e for e in res.evidence if e.field == "founding_year_mention"]
    assert [h.finding for h in hint] == ["Vier Forschende haben Testfirma 2021 gegründet."]
    assert hint[0].source_date == date(2024, 2, 1) and str(hint[0].url) == article_url(1)
    assert [e.finding for e in res.evidence if e.field == "founding_statement"] == ["Vier Forschende haben Testfirma 2021 gegründet."]


def test_hochquant_single_hit():
    calls = []
    res = run("HoCHQuant", {search_url("HoCHQuant"): load("search_hochquant"), article_url(838372): load("news838372")},
              institution="BTU Cottbus-Senftenberg", calls=calls)
    assert res.errors == [] and len(calls) == 2
    assert len(res.signals) == 1
    sig = res.signals[0]
    assert str(sig.url) == article_url(838372) and sig.date == date(2024, 8, 20)
    assert sig.evidence.startswith("Von der Lausitz auf den Weltmarkt")
    grants = [e.finding for e in res.evidence if e.field == "grants_mention"]
    assert grants == ["Im Rahmen des „EXIST Forschungstransfers“ erhält die BTU dafür rund 900.000 Euro."]
    assert not [e for e in res.evidence if e.field in ("founding_statement", "ip_mention")]


def test_siderogain_detects_founding_grant_and_patent():
    responses = {search_url("SideroGaIn"): load("search_siderogain"), article_url(876491): load("news876491"),
                 article_url(876492): synthetic_article("Siderogain enters the market", "English twin.")}
    calls = []
    res = run("SideroGaIn GmbH", responses, institution="Helmholtz-Zentrum Dresden-Rossendorf",
              founders=["Dr. Rohan Jain"], calls=calls)
    assert res.errors == [] and len(calls) == 3
    sig = [s for s in res.signals if str(s.url) == article_url(876491)][0]
    assert sig.date == date(2026, 8, 28)
    assert "patentierte Technologie" in sig.evidence and "Freiberger Compound Materials" in sig.evidence
    ev = {(e.field, e.finding) for e in res.evidence if str(e.url) == article_url(876491)}
    assert ("founding_statement", "Biomoleküle retten Rohstoffe: HZDR-Spin-off Siderogain gegründet") in ev
    assert any(f == "founding_statement" and fi.startswith("Mit der Gründung von Siderogain") for f, fi in ev)
    assert any(f == "grants_mention" and "EXIST-Forschungstransfers" in fi for f, fi in ev)
    assert any(f == "ip_mention" and fi.startswith("Im Mittelpunkt steht eine patentierte Technologie") for f, fi in ev)
    assert all(e.source_date == date(2026, 8, 28) for e in res.evidence if str(e.url) == article_url(876491))


def test_airlense_grant_sentence_keeps_title_abbreviation():
    responses = {search_url("AIRLense"): load("search_airlense"), article_url(881180): load("news881180"),
                 article_url(881181): synthetic_article("AIRLense english", "Hydrogen leaks.")}
    res = run("AIRLense", responses, institution="Universität Duisburg-Essen", founders=["Matthias Beuting"])
    assert res.errors == []
    sig = [s for s in res.signals if str(s.url) == article_url(881180)][0]
    assert sig.date == date(2026, 11, 19)
    grants = [e.finding for e in res.evidence if e.field == "grants_mention" and str(e.url) == article_url(881180)]
    assert grants and grants[0].startswith("Dazu erhält das Team um Dr. Matthias Beuting")
    assert "1,4 Mio. Euro" in grants[0]


def test_no_hits_single_word_name():
    calls = []
    res = run("Xyzzyqwvfoo", {search_url("Xyzzyqwvfoo"): load("search_none")}, calls=calls)
    assert res.errors == ["idw: keine Treffer"]
    assert res.signals == [] and res.evidence == [] and res.fields == {}
    assert len(calls) == 1


def test_no_hits_multiword_retries_with_distinctive_word_and_institution():
    calls = []
    responses = {search_url("Neue Materialien Lausitz"): load("search_none"),
                 search_url("Materialien BTU Cottbus Senftenberg"): load("search_hochquant")}
    res = run("Neue Materialien Lausitz GmbH", responses, institution="BTU Cottbus-Senftenberg", calls=calls)
    assert calls == list(responses)                     # retry happened, no article matched
    assert res.errors == ["idw: keine Treffer"] and res.signals == []


def test_retry_hit_matched_via_founders():
    responses = {search_url("Neue Materialien Lausitz"): load("search_none"),
                 search_url("Materialien BTU Cottbus Senftenberg"): synthetic_search([
                     ("20.08.2024 11:01", 42, "Materialien aus der Lausitz", "BTU Cottbus-Senftenberg",
                      "Prof. Peer Schmidt und Dr. Jana Nowak starten."),
                 ]),
                 article_url(42): synthetic_article("Materialien aus der Lausitz", "Peer Schmidt und Jana Nowak.")}
    res = run("Neue Materialien Lausitz GmbH", responses, institution="BTU Cottbus-Senftenberg",
              founders=["Peer Schmidt", "Jana Nowak"])
    assert res.errors == [] and len(res.signals) == 1 and str(res.signals[0].url) == article_url(42)


# --- errors -----------------------------------------------------------------------------------------

def test_http_error_on_search():
    res = run("SpinMagIC", {search_url("SpinMagIC"): FetchError("idw-online.de: HTTP 503")})
    assert res.errors == ["idw: HTTP 503"] and res.signals == []


def test_http_error_on_one_article_keeps_the_others():
    responses = {search_url("SideroGaIn"): load("search_siderogain"),
                 article_url(876492): FetchError("idw-online.de: HTTP 500"),
                 article_url(876491): load("news876491")}
    res = run("SideroGaIn", responses)
    assert res.errors == ["idw: HTTP 500"]
    assert [str(s.url) for s in res.signals] == [article_url(876491)]


def test_arbitrary_exception_never_propagates():
    def fetch(url):
        raise RuntimeError("kaputt")
    res = idw_lookup("SpinMagIC", institution=None, founders=[], cache=NoCache(), fetch=fetch)
    assert res.errors == ["idw: kaputt"] and res.signals == []


def test_empty_name_does_nothing():
    calls = []
    res = run("GmbH i.G.", {}, calls=calls)
    assert calls == [] and res.errors == [] and res.signals == []


def test_request_budget_is_capped_at_six():
    rows = [("%02d.01.2024 10:00" % d, d, "Testfirma %d" % d, "Uni", "") for d in range(1, 8)]
    responses = {search_url("Testfirma"): synthetic_search(rows)}
    for d in range(1, 8):
        responses[article_url(d)] = synthetic_article("Testfirma %d" % d, "Text.")
    calls = []
    res = run("Testfirma GmbH", responses, calls=calls)
    assert len(calls) == 6 and len(res.signals) == 5 and res.errors == []
