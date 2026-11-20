"""Offline tests for context.openalex (fixtures recorded live on 2026-11-20, trimmed)."""
import json
from pathlib import Path

import pytest

from context.cache import NoCache
from context.http import FetchError
from context.openalex import _fold, _institution_score, _name_score, author_lookup

FIXTURES = Path(__file__).parent / "fixtures" / "context"


def load(key):
    return json.loads((FIXTURES / f"openalex_{key}.json").read_text())


def fixture_fetch(fx):
    """Route /authors and /works requests to the recorded responses; anything else is an error."""
    calls = []

    def fetch(url):
        calls.append(url)
        if "/authors?" in url:
            return fx["authors"]
        if "/works?" in url and "works" in fx:
            return fx["works"]
        raise AssertionError("unexpected URL " + url)
    fetch.calls = calls
    return fetch


def author(id_, name, works, insts=(), affiliations=(), h_index=10, topics=()):
    def inst(spec):
        display, country = spec
        return {"id": "https://openalex.org/I" + str(abs(hash(display)) % 10**6), "display_name": display, "country_code": country}
    return {
        "id": "https://openalex.org/" + id_, "display_name": name, "works_count": works, "cited_by_count": works * 10,
        "summary_stats": {"h_index": h_index},
        "last_known_institutions": [inst(s) for s in insts],
        "affiliations": [{"institution": inst(s)} for s in list(insts) + list(affiliations)],
        "topics": [{"display_name": t, "count": 5} for t in topics],
    }


def synthetic(results, works_count=None):
    fx = {"authors": {"meta": {"count": len(results)}, "results": results}}
    if works_count is not None:
        fx["works"] = {"meta": {"count": works_count}, "results": []}
    return fx


# --- live fixtures -------------------------------------------------------------------------------

def test_live_professor_with_institution_matches_high():
    fx = load("boetius")
    fetch = fixture_fetch(fx)
    profile, lookup = author_lookup("Antje Boetius", institution="Alfred-Wegener-Institut",
                                    field_terms=["methane", "deep sea"], cache=NoCache(), fetch=fetch)
    assert lookup.errors == []
    assert profile.match_confidence == 0.9
    assert str(profile.openalex_url) == "https://openalex.org/A5002131026"
    assert str(profile.source_url) == "https://openalex.org/A5002131026"
    assert profile.institution.startswith("Alfred-Wegener-Institut")
    assert profile.works_total == 916 and profile.works_in_field == 368
    assert profile.qualifications.startswith("h-Index 93, 916 Arbeiten, Alfred-Wegener-Institut")
    assert lookup.fields["qualifications"] == profile.qualifications
    assert lookup.fields["founder_profiles"] == [profile]
    assert len(fetch.calls) == 2
    assert "search=Antje+Boetius" in fetch.calls[0] and "per-page=10" in fetch.calls[0]
    assert "authorships.author.id%3AA5002131026" in fetch.calls[1] and "search=methane+OR+deep+sea" in fetch.calls[1]
    kinds = [(e.field, e.source) for e in lookup.evidence]
    assert kinds == [("founder_profiles", "OpenAlex")] * 2
    assert "OpenAlex: Antje Boëtius" in lookup.evidence[0].finding
    assert "916 Arbeiten, 368 im Feld methane, deep sea" in lookup.evidence[0].finding


def test_live_common_name_without_institution_is_ambiguous():
    fx = load("mueller")
    fetch = fixture_fetch(fx)
    profile, lookup = author_lookup("Thomas Müller", institution=None, field_terms=["machine learning"],
                                    cache=NoCache(), fetch=fetch)
    assert profile is None
    assert lookup.errors == ["openalex: mehrdeutig (532 Kandidaten)"]
    assert lookup.fields == {} and lookup.evidence == []
    assert len(fetch.calls) == 1  # no works query for a rejected match
    assert "search=Thomas+M%C3%BCller" in fetch.calls[0]


def test_live_german_abbreviation_tu_berlin_matches():
    fx = load("markl")
    profile, lookup = author_lookup("Volker Markl", institution="TU Berlin", field_terms=["database", "data management"],
                                    cache=NoCache(), fetch=fixture_fetch(fx))
    assert lookup.errors == []
    assert profile.match_confidence == 0.9
    assert profile.institution == "Technische Universität Berlin"
    assert profile.works_total == 357 and profile.works_in_field == 181
    # the 1-work "Volker Markl Preface" / "(eds" records do not count as rivals
    assert str(profile.openalex_url) == "https://openalex.org/A5002413906"


def test_live_unknown_name_returns_none_with_error():
    fx = load("nobody")
    profile, lookup = author_lookup("Xyzzyq Blorfnak", institution="TU Dresden", field_terms=["robotics"],
                                    cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile is None
    assert lookup.errors == ["openalex: kein Treffer für Xyzzyq Blorfnak"]


# --- institution fuzzy matching ------------------------------------------------------------------

@pytest.mark.parametrize("given, display, country, expect", [
    ("TU München", "Technical University of Munich", "DE", True),
    ("TU Berlin", "Technische Universität Berlin", "DE", True),
    ("TU Berlin", "Freie Universität Berlin", "DE", False),
    ("RWTH", "RWTH Aachen University", "DE", True),
    ("RWTH Aachen", "Aachen University of Applied Sciences", "DE", False),
    ("KIT", "Karlsruhe Institute of Technology", "DE", True),
    ("LMU", "Ludwig-Maximilians-Universität München", "DE", True),
    ("Charité", "Charité – Universitätsmedizin Berlin", "DE", True),
    ("Fraunhofer", "Fraunhofer Institute for Production Technology", "DE", True),
    ("Max-Planck-Institut für Kohlenforschung", "Max Planck Institute for Coal Research", "DE", True),
    ("Helmholtz-Zentrum Dresden-Rossendorf", "Helmholtz-Zentrum Dresden-Rossendorf", "DE", True),
    ("Uni Köln", "University of Cologne", "DE", True),
    ("Universität Hamburg", "Universität Hamburg", "DE", True),
    ("Universität Hamburg", "Universität Bremen", "DE", False),
    ("HPI", "Hasso Plattner Institute", "DE", True),
    ("https://ror.org/032e6b942", "Alfred-Wegener-Institut", "DE", True),
])
def test_institution_fuzzy_matching(given, display, country, expect):
    score = _institution_score(given, {"id": "https://openalex.org/I127251866", "ror": "https://ror.org/032e6b942",
                                       "display_name": display, "country_code": country})
    assert (score >= 0.5) is expect, score


def test_name_scores_handle_umlauts_initials_and_extra_tokens():
    assert _fold("Müller") == _fold("Mueller") == _fold("Muller")
    assert _fold("Boëtius") == _fold("Boetius")
    assert _name_score("Thomas Müller", "Thomas Mueller") == 1.0
    assert _name_score("Thomas Müller", "Th. Müller") == 0.9
    assert _name_score("Thomas Müller", "Thomas M. Müller") == 1.0
    assert _name_score("Prof. Dr. Jürgen Straß", "Juergen Strass") == 1.0
    assert _name_score("Volker Markl", "Volker Markl Preface") == 0.7
    assert _name_score("Anna Schmidt", "Peter Schmidt") == 0.0
    assert _name_score("Anna Schmidt", "Anna Schulz") == 0.0


# --- confidence tiers ------------------------------------------------------------------------------

def test_confidence_single_candidate_with_german_affiliation_is_0_6():
    fx = synthetic([author("A1", "Kim Muster", 12, insts=[("Universität Hamburg", "DE")])], works_count=3)
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=["sensor"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile.match_confidence == 0.6 and profile.works_in_field == 3 and lookup.errors == []


def test_confidence_single_candidate_abroad_is_0_4_and_still_returned():
    fx = synthetic([author("A1", "Kim Muster", 12, insts=[("ETH Zurich", "CH")])], works_count=0)
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=["sensor"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile.match_confidence == 0.4 and profile.institution == "ETH Zurich" and profile.works_in_field == 0


def test_confidence_single_candidate_but_given_institution_mismatch_is_0_5():
    fx = synthetic([author("A1", "Kim Muster", 12, insts=[("Universität Hamburg", "DE")])], works_count=1)
    profile, _ = author_lookup("Kim Muster", institution="TU Dresden", field_terms=["x"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile.match_confidence == 0.5


def test_confidence_institution_match_wins_over_bigger_rival_and_de_signal():
    fx = synthetic([
        author("A1", "Kim Muster", 400, insts=[("University of Oxford", "GB")]),
        author("A2", "Kim Muster", 90, insts=[("Universität Hamburg", "DE")]),
        author("A3", "Kim Muster", 7, insts=[("Technische Universität Dresden", "DE")]),
    ], works_count=2)
    profile, lookup = author_lookup("Kim Muster", institution="TU Dresden", field_terms=["x"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert str(profile.openalex_url) == "https://openalex.org/A3"
    assert profile.match_confidence == 0.9 and profile.works_total == 7


def test_confidence_earlier_affiliation_only_is_0_8():
    fx = synthetic([
        author("A1", "Kim Muster", 40, insts=[("Siemens (Germany)", "DE")], affiliations=[("Technische Universität Dresden", "DE")]),
        author("A2", "Kim Muster", 90, insts=[("Universität Hamburg", "DE")]),
    ], works_count=2)
    profile, _ = author_lookup("Kim Muster", institution="TU Dresden", field_terms=["x"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert str(profile.openalex_url) == "https://openalex.org/A1"
    assert profile.match_confidence == 0.8
    assert profile.institution == "Siemens (Germany)"  # last known, not the matched historical one


def test_confidence_several_candidates_without_signal_is_rejected():
    fx = synthetic([
        author("A1", "Kim Muster", 40, insts=[("Universität Hamburg", "DE")]),
        author("A2", "Kim Muster", 90, insts=[("Universität Bremen", "DE")]),
    ])
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=["x"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile is None
    assert lookup.errors == ["openalex: mehrdeutig (2 Kandidaten)"]


def test_two_candidates_at_the_same_institution_are_unsure():
    fx = synthetic([
        author("A1", "Kim Muster", 40, insts=[("Universität Hamburg", "DE")]),
        author("A2", "Kim Muster", 90, insts=[("Universität Hamburg", "DE")]),
    ], works_count=1)
    profile, _ = author_lookup("Kim Muster", institution="Uni Hamburg", field_terms=["x"], cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile is not None and profile.match_confidence == 0.5


def test_name_mismatch_in_results_is_reported():
    fx = synthetic([author("A1", "Peter Muster", 40, insts=[("Universität Hamburg", "DE")])])
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=[], cache=NoCache(), fetch=fixture_fetch(fx))
    assert profile is None
    assert lookup.errors == ["openalex: kein Namenstreffer für Kim Muster (1 Suchergebnisse)"]


# --- works_in_field --------------------------------------------------------------------------------

def test_works_in_field_joins_terms_with_or_and_limits_them():
    fx = synthetic([author("A1", "Kim Muster", 12, insts=[("Universität Hamburg", "DE")])], works_count=5)
    fetch = fixture_fetch(fx)
    terms = ["a", "b", "a", " ", "c", "d", "e", "f", "g", "h", "i", "j"]
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=terms, cache=NoCache(), fetch=fetch)
    assert profile.works_in_field == 5
    assert "search=a+OR+b+OR+c+OR+d+OR+e+OR+f+OR+g+OR+h&per-page=1" in fetch.calls[1]
    assert "filter=authorships.author.id%3AA1" in fetch.calls[1]
    assert lookup.evidence[1].finding == "5 von 12 Arbeiten passen zu: a, b, c, d, e, f, g, h"
    assert str(lookup.evidence[1].url) == fetch.calls[1]


def test_empty_field_terms_skips_works_query_and_reports_topics():
    fx = synthetic([author("A1", "Kim Muster", 12, insts=[("Universität Hamburg", "DE")], topics=["Robotics", "Sensors"])])
    fetch = fixture_fetch(fx)
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=[], cache=NoCache(), fetch=fetch)
    assert profile.works_in_field is None and profile.works_total == 12
    assert len(fetch.calls) == 1
    assert len(lookup.evidence) == 1
    assert "Themen: Robotics, Sensors" in lookup.evidence[0].finding


def test_works_query_failure_keeps_profile_and_records_error():
    fx = synthetic([author("A1", "Kim Muster", 12, insts=[("Universität Hamburg", "DE")])])

    def fetch(url):
        if "/works?" in url:
            raise FetchError("api.openalex.org: HTTP 429")
        return fx["authors"]
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=["x"], cache=NoCache(), fetch=fetch)
    assert profile is not None and profile.works_in_field is None and profile.works_total == 12
    assert lookup.errors == ["openalex works: api.openalex.org: HTTP 429"]


def test_no_h_index_means_no_qualifications():
    result = author("A1", "Kim Muster", 12, insts=[("Universität Hamburg", "DE")], h_index=None)
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=[], cache=NoCache(), fetch=fixture_fetch(synthetic([result])))
    assert profile.qualifications is None and "qualifications" not in lookup.fields


# --- failures --------------------------------------------------------------------------------------

def test_http_error_becomes_error_entry_and_never_raises():
    def fetch(url):
        raise FetchError("api.openalex.org: HTTP 503")
    profile, lookup = author_lookup("Kim Muster", institution="TU Berlin", field_terms=["x"], cache=NoCache(), fetch=fetch)
    assert profile is None
    assert lookup.errors == ["openalex: api.openalex.org: HTTP 503"]


def test_garbage_response_and_empty_name_are_handled():
    profile, lookup = author_lookup("Kim Muster", institution=None, field_terms=[], cache=NoCache(), fetch=lambda url: "not json")
    assert profile is None and lookup.errors and lookup.errors[0].startswith("openalex:")
    profile, lookup = author_lookup("  ", institution=None, field_terms=[], cache=NoCache(), fetch=lambda url: {})
    assert profile is None and lookup.errors == ["openalex: kein Name"]


def test_default_fetch_uses_context_http_with_cache(monkeypatch):
    seen = {}

    def fake_get_json(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return {"meta": {"count": 0}, "results": []}
    monkeypatch.setattr("context.openalex.get_json", fake_get_json)
    cache = NoCache()
    author_lookup("Jürgen Straß", institution=None, field_terms=[], cache=cache)
    assert seen["url"].startswith("https://api.openalex.org/authors?search=J%C3%BCrgen+Stra%C3%9F&per-page=10&select=")
    assert seen["kw"] == {"cache": cache, "min_interval": 0.2}
    assert "mailto" not in seen["url"]
