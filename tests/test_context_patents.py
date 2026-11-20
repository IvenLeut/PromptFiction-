"""Offline tests for context/patents.py (Google Patents XHR). No network: responses are injected."""
import json
from pathlib import Path

import pytest

from context.cache import NoCache
from context.http import FetchError
from context import patents as P
from context.patents import Budget, dedupe, normalise_name, patent_lookup, query_url

FIXTURES = Path(__file__).parent / "fixtures" / "context"


def load(name):
    return json.loads((FIXTURES / ("patents_%s.json" % name)).read_text())


def fetch_from(responses, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if url not in responses:
            raise AssertionError("unerwartete Patents-Anfrage: " + url)
        data = responses[url]
        if isinstance(data, dict) and "error" in data:
            raise FetchError(data["error"])
        return data
    return fetch


def run(fx, calls=None, budget=None, founders=None):
    return patent_lookup(fx["company"], fx["founders"] if founders is None else founders,
                         cache=NoCache(), fetch=fetch_from(fx["responses"], calls), budget=budget or Budget(6))


# --- normalisation / URLs -------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("kiutra GmbH", "kiutra"),
    ("Müller Fräsen GmbH i.G.", "mueller fraesen"),
    ("Spinlabs Quantensensorik UG (haftungsbeschränkt)", "spinlabs quantensensorik"),
    ("Quantenfräse Zwölfhausen GmbH i.G.", "quantenfraese zwoelfhausen"),
    ("Kiutra Gmbh", "kiutra"),
    ("Proxima Fusion GmbH & Co. KG", "proxima fusion"),
    ("Straße AG in Gründung", "strasse"),
    ("GmbH", ""),
])
def test_normalise_name(name, expected):
    assert normalise_name(name) == expected


def test_query_url_encodes_inner_query():
    assert query_url("assignee", "kiutra") == \
        "https://patents.google.com/xhr/query?url=assignee%3D%22kiutra%22%26num%3D10&exp="
    assert "inventor%3D%22Lena+M%C3%BCller%22" in query_url("inventor", "Lena Müller")


# --- assignee filtering, mapping, dedupe ----------------------------------------------------

def test_kiutra_assignee_filter_ignores_fuzzy_total():
    fx = load("kiutra")
    calls = []
    pats, look = run(fx, calls)
    assert look.errors == []
    assert len(calls) == 1 and "assignee" in calls[0]  # no inventor fallback once the company matches
    # 888 fuzzy results, 3 returned, 2 are kiutra's and they are one family -> 1 patent
    assert len(pats) == 1
    p = pats[0]
    assert p.status == "patent_erteilt"
    assert p.title == "Kühleinrichtung und Verfahren zum Betreiben einer Kühleinrichtung"
    assert p.quote == "DE102022110585B4, Kiutra Gmbh, angemeldet 2022-04-29, erteilt 2023-11-30"
    assert str(p.url) == "https://patents.google.com/patent/DE102022110585B4"
    assert all("Kyocera" not in (q.quote or "") for q in pats)
    assert look.fields["ip_status"] == "patent_erteilt"
    assert look.fields["patents"] == pats
    ev = [e for e in look.evidence if e.field == "ip_status"]
    assert len(ev) == 1 and ev[0].source == "Google Patents"
    assert str(ev[0].url) == str(p.url) and ev[0].finding == p.quote


def test_dedupe_keeps_granted_member_of_family():
    a = {"publication_number": "DE1A1", "title": "Titel", "priority_date": "2020-01-01", "grant_date": None}
    b = {"publication_number": "DE1B4", "title": "Titel", "priority_date": "2020-01-01", "grant_date": "2022-01-01"}
    c = {"publication_number": "EP2A1", "title": "Titel", "priority_date": "2021-05-05", "grant_date": None}
    d = {"publication_number": "US3A1", "title": None, "priority_date": None, "grant_date": None}
    out = dedupe([a, b, c, d])
    assert [r["publication_number"] for r in out] == ["DE1B4", "EP2A1", "US3A1"]


def test_application_only_maps_to_angemeldet():
    fx = load("kiutra")
    url = next(iter(fx["responses"]))
    results = fx["responses"][url]["results"]["cluster"][0]["result"]
    fx["responses"][url]["results"]["cluster"][0]["result"] = [results[1], results[2]]  # drop the B4
    pats, look = run(fx)
    assert [p.status for p in pats] == ["patent_angemeldet"]
    assert pats[0].quote == "DE102022110585A1, Kiutra Gmbh, angemeldet 2022-04-29"
    assert look.fields["ip_status"] == "patent_angemeldet"


def test_assignee_may_be_a_list():
    fx = load("kiutra")
    url = next(iter(fx["responses"]))
    pat = fx["responses"][url]["results"]["cluster"][0]["result"][0]["patent"]
    pat["assignee"] = ["Technische Universität München", "Kiutra GmbH"]
    pats, _ = run(fx)
    assert len(pats) == 1 and "Kiutra GmbH" in pats[0].quote


# --- inventor fallback ----------------------------------------------------------------------

def test_inventor_fallback_marks_university_assignee():
    fx = load("inventor")
    calls = []
    pats, look = run(fx, calls)
    assert look.errors == []
    # 1 assignee query + at most 2 founders, and we stop after the first founder with hits
    assert len(calls) == 2 and "inventor" in calls[1] and "Lena" in calls[1]
    assert len(pats) == 1  # DE + WO share title and priority date -> one family
    p = pats[0]
    assert p.status == "patent_angemeldet"
    assert p.quote.startswith("Erfinder: Lena Müller; Anmelder: Technische Universität München")
    assert "DE102021201234A1" in p.quote
    assert look.fields["ip_status"] == "patent_angemeldet"


def test_inventor_fallback_prefers_non_institutional_assignee():
    fx = load("inventor")
    inv_url = [u for u in fx["responses"] if "inventor" in u and "Lena" in u][0]
    results = fx["responses"][inv_url]["results"]["cluster"][0]["result"]
    results[2]["patent"]["inventor"] = "Lena Müller, Chris Brown"  # now a real hit of the founder
    pats, look = run(fx)
    assert [p.status for p in pats] == ["patent_erteilt"]
    assert pats[0].quote == "US9876543B2, FreshPack Inc, angemeldet 2015-01-05, erteilt 2018-01-23"
    assert look.fields["ip_status"] == "patent_erteilt"


def test_inventor_fallback_queries_at_most_two_founders():
    fx = load("inventor")
    inv_url = [u for u in fx["responses"] if "inventor" in u and "Lena" in u][0]
    fx["responses"][inv_url]["results"]["cluster"][0]["result"] = []
    calls = []
    pats, look = run(fx, calls)
    assert pats == [] and look.errors == []
    assert len(calls) == 3  # assignee + 2 founders, never the third
    assert "ip_status" not in look.fields


def test_no_inventor_fallback_without_founders():
    fx = load("inventor")
    calls = []
    pats, look = run(fx, calls, founders=[])
    assert pats == [] and len(calls) == 1


# --- empty result is not "keine" ------------------------------------------------------------

def test_made_up_company_sets_nothing():
    fx = load("nohit")
    pats, look = run(fx)
    assert pats == []
    assert look.errors == []
    assert look.fields == {} and look.evidence == []
    assert look.fields.get("ip_status") != "keine"


def test_empty_company_name():
    pats, look = patent_lookup("GmbH", ["Someone"], cache=NoCache(), fetch=fetch_from({}), budget=Budget(6))
    assert pats == [] and look.errors == ["patents: kein Firmenname"]


# --- budget and 503 -------------------------------------------------------------------------

def test_budget_exhausted_does_not_call():
    fx = load("kiutra")
    calls = []
    budget = Budget(0)
    pats, look = run(fx, calls, budget=budget)
    assert pats == [] and calls == []
    assert look.errors == ["patents: Budget erschöpft"]
    assert "ip_status" not in look.fields


def test_budget_counts_across_leads_and_stops_fallback():
    budget = Budget(2)
    fx1 = load("kiutra")
    pats, look = run(fx1, budget=budget)
    assert len(pats) == 1 and budget.used == 1
    fx2 = load("inventor")
    calls = []
    pats, look = run(fx2, calls, budget=budget)
    # the assignee query consumed the last unit; the inventor fallback is refused without a call
    assert len(calls) == 1 and pats == []
    assert look.errors == ["patents: Budget erschöpft"]
    assert budget.used == 2 and budget.left == 0


def test_http_503_is_recorded_and_lead_abandoned():
    fx = load("inventor")
    for url in list(fx["responses"]):
        fx["responses"][url] = {"error": "patents.google.com: HTTP 503"}
    calls = []
    pats, look = run(fx, calls)
    assert pats == [] and len(calls) == 1
    assert look.errors == ["patents: HTTP 503 (gesperrt)"]
    assert "ip_status" not in look.fields


def test_other_fetch_errors_are_reported_not_raised():
    fx = load("kiutra")
    for url in list(fx["responses"]):
        fx["responses"][url] = {"error": "patents.google.com: TimeoutError"}
    pats, look = run(fx)
    assert pats == [] and look.errors == ["patents: patents.google.com: TimeoutError"]


def test_module_budget_defaults(monkeypatch):
    assert P.MAX_REQUESTS == 6 and P.BUDGET.maximum == 6
    assert P.MIN_INTERVAL >= 15 and P.TIMEOUT == 20


def test_default_fetch_uses_http_with_throttle_and_no_retries(monkeypatch):
    seen = {}

    def fake_get_json(url, **kw):
        seen.update(kw, url=url)
        return {"results": {"total_num_results": 0, "cluster": []}}
    monkeypatch.setattr(P, "get_json", fake_get_json)
    pats, look = patent_lookup("kiutra GmbH", [], cache=NoCache(), budget=Budget(1))
    assert look.errors == []
    assert seen["min_interval"] >= 15 and seen["timeout"] == 20 and seen["retries"] == 0
    assert seen["url"].startswith("https://patents.google.com/xhr/query?")
