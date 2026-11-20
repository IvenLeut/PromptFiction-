"""Offline tests for context/wayback.py. Fixtures are real CDX answers recorded on 2026-11-20."""
import json
from datetime import date
from pathlib import Path

import pytest

from context.cache import NoCache
from context.http import FetchError
from context.wayback import cdx_url, normalise_host, slugs, web_history_lookup

FIXTURES = Path(__file__).parent / "fixtures" / "context"


def load(name):
    return json.loads((FIXTURES / ("wayback_%s.json" % name)).read_text())


def fetch_from(responses, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if url not in responses:
            raise AssertionError("unerwartete CDX-Anfrage: " + url)
        data = responses[url]
        if isinstance(data, dict) and "error" in data:
            raise FetchError(data["error"])
        return data
    return fetch


def run(website, name, responses, calls=None):
    return web_history_lookup(website, name, cache=NoCache(), fetch=fetch_from(responses, calls))


# --- slugs / host normalisation -------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("Celonis SE", ["celonis"]),
    ("Proxima Fusion GmbH", ["proxima-fusion", "proximafusion"]),
    ("Münchner Grünstrom UG (haftungsbeschränkt)", ["muenchner-gruenstrom", "muenchnergruenstrom"]),
    ("Quantenfräse GmbH i.G.", ["quantenfraese"]),
    ("Müller & Söhne AG", ["mueller-and-soehne", "muellerandsoehne"]),
    ("  e-Fusion GmbH & Co. KG ", ["e-fusion", "efusion"]),
    ("Straße 1 Labs GmbH", ["strasse-1-labs", "strasse1labs"]),
    ("GmbH", []),
])
def test_slugs(name, expected):
    assert slugs(name) == expected


@pytest.mark.parametrize("website, host", [
    ("https://www.Firma.de/de/start?x=1", "firma.de"),
    ("http://firma.de:8080/", "firma.de"),
    ("firma.de/impressum", "firma.de"),
    ("www.sub.firma.co.uk", "sub.firma.co.uk"),
    (None, None),
    ("", None),
    ("   ", None),
    ("localhost", None),
])
def test_normalise_host(website, host):
    assert normalise_host(website) == host


def test_cdx_url_is_exact_match_without_wildcards():
    url = cdx_url("crunchbase.com/organization/celonis")
    assert url.startswith("https://web.archive.org/cdx/search/cdx?")
    assert "url=crunchbase.com%2Forganization%2Fcelonis" in url
    assert "filter=statuscode%3A200" in url and "limit=1" in url
    assert "*" not in url and "matchType" not in url


# --- recorded live cases --------------------------------------------------------------------

def test_celonis_found_in_crunchbase_and_dealroom():
    fx = load("celonis")
    calls = []
    res = run(fx["website"], fx["name"], fx["responses"], calls)
    assert res.errors == []
    assert len(calls) == 4  # 1 host + 1 slug x 3 profile hosts
    assert res.fields["first_web_capture"] == date(2016, 9, 4)
    assert res.fields["in_databases"] is True
    assert res.fields["first_db_date"] == date(2018, 7, 13)
    assert [str(u) for u in res.fields["database_urls"]] == [
        "https://web.archive.org/web/20180713111743/https://www.crunchbase.com/organization/celonis/",
        "https://web.archive.org/web/20230720162718/https://app.dealroom.co/companies/celonis",
    ]
    web = [e for e in res.evidence if e.field == "first_web_capture"]
    assert len(web) == 1
    assert web[0].finding == "Erste Wayback-Aufnahme: 2016-09-04"
    assert web[0].source == "Wayback CDX" and web[0].source_date == date(2016, 9, 4)
    assert str(web[0].url) == cdx_url("celonis.com")
    assert len(res.signals) == 1
    sig = res.signals[0]
    assert sig.source == "Wayback" and sig.type == "wayback" and sig.date == date(2016, 9, 4)
    assert str(sig.url) == "https://web.archive.org/web/20160904114846/http://www.celonis.com:80/"
    assert sig.evidence == "Erste Archivaufnahme der Website"
    db = [e for e in res.evidence if e.field == "in_databases"]
    assert {str(e.url) for e in db} == set(str(u) for u in res.fields["database_urls"])
    assert any(e.field == "first_db_date" and e.source_date == date(2018, 7, 13) for e in res.evidence)


def test_unknown_name_without_website_is_false():
    fx = load("unknown")
    calls = []
    res = run(None, fx["name"], fx["responses"], calls)
    assert res.errors == []
    assert len(calls) == 6  # no website query; 2 slugs x 3 hosts
    assert res.fields == {"in_databases": False}
    assert res.signals == []
    assert [e.field for e in res.evidence] == ["in_databases"]
    assert "quantenfraese" in res.evidence[0].finding


def test_spin_off_proxima_fusion():
    fx = load("proxima_fusion")
    calls = []
    res = run(fx["website"], fx["name"], fx["responses"], calls)
    assert res.errors == []
    assert len(calls) == 7  # budget fully used, not exceeded
    assert res.fields["first_web_capture"] == date(2025, 7, 13)
    assert res.fields["in_databases"] is True
    assert res.fields["first_db_date"] == date(2024, 10, 5)
    assert "crunchbase.com/organization/proxima-fusion" in str(res.fields["database_urls"][0])


def test_spin_off_planqc():
    fx = load("planqc")
    res = run(fx["website"], fx["name"], fx["responses"])
    assert res.errors == []
    assert res.fields["first_web_capture"] == date(2022, 7, 6)
    assert res.fields["in_databases"] is True
    assert res.fields["first_db_date"] == date(2024, 4, 21)
    assert len(res.fields["database_urls"]) == 1


# --- synthetic edge cases -------------------------------------------------------------------

HEADER = ["timestamp", "original", "statuscode"]


def responses_for(name, website=None, **by_target):
    """Build a URL->response map; by_target keys are CDX targets, values rows or {'error': ...}."""
    out = {}
    targets = []
    if website:
        targets.append(normalise_host(website))
    for slug in slugs(name):
        targets += ["crunchbase.com/organization/" + slug, "app.dealroom.co/companies/" + slug,
                    "dealroom.co/companies/" + slug]
    for t in targets:
        out[cdx_url(t)] = by_target.get(t.replace(".", "_").replace("/", "__").replace("-", "_"), [])
    return out


def test_any_error_makes_in_databases_none():
    res = run(None, "Testfirma GmbH", responses_for(
        "Testfirma GmbH", crunchbase_com__organization__testfirma={"error": "web.archive.org: HTTP 429"},
    ))
    assert res.fields == {"in_databases": None}
    assert res.errors == ["wayback: HTTP 429"]


def test_found_profile_wins_over_error_elsewhere():
    res = run(None, "Testfirma GmbH", responses_for(
        "Testfirma GmbH",
        crunchbase_com__organization__testfirma={"error": "web.archive.org: HTTP 503"},
        app_dealroom_co__companies__testfirma=[HEADER, ["20210301120000", "https://app.dealroom.co/companies/testfirma", "200"]],
    ))
    assert res.fields["in_databases"] is True
    assert res.fields["first_db_date"] == date(2021, 3, 1)
    assert res.errors == ["wayback: HTTP 503"]


def test_earliest_date_across_profiles_and_slug_variants():
    res = run(None, "Test Firma GmbH", responses_for(
        "Test Firma GmbH",
        crunchbase_com__organization__test_firma=[HEADER, ["20220115000000", "https://www.crunchbase.com/organization/test-firma", "200"]],
        dealroom_co__companies__testfirma=[HEADER, ["20190704000000", "https://dealroom.co/companies/testfirma", "200"]],
    ))
    assert res.fields["first_db_date"] == date(2019, 7, 4)
    assert [str(u) for u in res.fields["database_urls"]] == [
        "https://web.archive.org/web/20190704000000/https://dealroom.co/companies/testfirma",
        "https://web.archive.org/web/20220115000000/https://www.crunchbase.com/organization/test-firma",
    ]
    first = [e for e in res.evidence if e.field == "first_db_date"][0]
    assert "Dealroom" in first.finding and str(first.url).startswith("https://web.archive.org/web/20190704000000/")


def test_website_error_is_recorded_but_databases_still_evaluated():
    res = run("https://www.testfirma.de/", "Testfirma GmbH", responses_for(
        "Testfirma GmbH", website="https://www.testfirma.de/", testfirma_de={"error": "web.archive.org: HTTP 429"},
    ))
    assert "first_web_capture" not in res.fields
    assert res.fields["in_databases"] is False
    assert res.errors == ["wayback: HTTP 429"]


def test_host_normalisation_drives_the_query():
    calls = []
    res = run("HTTP://WWW.Testfirma.DE:443/de/team?x=1#top", "Testfirma GmbH", responses_for(
        "Testfirma GmbH", website="testfirma.de",
        testfirma_de=[HEADER, ["20200202101010", "http://testfirma.de/", "200"]],
    ), calls)
    assert calls[0] == cdx_url("testfirma.de")
    assert res.fields["first_web_capture"] == date(2020, 2, 2)


def test_fetch_raising_arbitrary_exception_never_propagates():
    def fetch(url):
        raise RuntimeError("kaputt")
    res = web_history_lookup("https://testfirma.de/", "Testfirma GmbH", cache=NoCache(), fetch=fetch)
    assert res.fields == {"in_databases": None}
    assert res.errors == ["wayback: kaputt"] * 4
    assert res.signals == []


def test_empty_or_malformed_answers_are_tolerated():
    answers = iter([None, "", [HEADER, ["x", "y", "200"]], {"not": "a list"}])
    calls = []

    def fetch(url):
        calls.append(url)
        return next(answers)
    res = web_history_lookup("https://testfirma.de/", "Testfirma", cache=NoCache(), fetch=fetch)
    assert "first_web_capture" not in res.fields
    assert res.fields["in_databases"] is None            # the dict answer counts as an error
    assert res.errors == ["wayback: unerwartete Antwort für dealroom.co/companies/testfirma"]
    assert len(calls) == 4


def test_website_none_and_empty_name_do_nothing():
    calls = []
    res = run(None, "GmbH i.G.", {}, calls)
    assert calls == []
    assert res.fields == {} and res.evidence == [] and res.errors == []


def test_request_budget_is_capped_at_seven():
    calls = []
    res = run("https://a-b-c.de/", "A B C GmbH", responses_for("A B C GmbH", website="https://a-b-c.de/"), calls)
    assert len(calls) == 7
    assert res.errors == []
