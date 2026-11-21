"""Offline tests for context/website_match.py (project name -> company website). No network."""
import json
from pathlib import Path

import pytest

from context import http as ctx_http
from context import website_match as wm
from context.cache import Cache
from context.engine import default_lookups, enrich
from context.lookup import Lookup
from context.web import parse_page
from models import EnrichedLead, RawLead, SourceSignal
from pipeline import collect_context

FIX = Path(__file__).parent / "fixtures" / "context"
CATALOGUE = ("Förderkennzeichen: 03EFBW0275\nProgramm: EXIST-Forschungstransfer\nThema: SpinMagIC\n"
             "Förderempfänger: Universität Stuttgart, Stuttgart, Baden-Württemberg\n"
             "Ausführende Stelle: Universität Stuttgart - Fakultät 5 Informatik, Elektrotechnik und Informationstechnik - "
             "Institut für Intelligente Sensorik und Theoretische Elektrotechnik (IIS), Stuttgart, Baden-Württemberg\n"
             "Laufzeit: 01.09.2024 bis 30.09.2026\nFördersumme: 972.638,00 EUR\nÖffentliche Förderung: Bewilligt")
SPIN = dict(institution="Universität Stuttgart - Fakultät 5 Informatik, Elektrotechnik und Informationstechnik",
            executing="Universität Stuttgart - Institut für Intelligente Sensorik und Theoretische Elektrotechnik (IIS)",
            location="Stuttgart", topic="„SpinMagIC“ – Projekt im Programm EXIST-Forschungstransfer.")


def page(name):
    return (FIX / name).read_text(encoding="utf-8")


def fake_fetch(pages: dict, calls=None):
    """`fetch(url, site)` double: URL -> fixture file; unknown URLs fail like an unreachable host."""
    def fetch(url, site):
        if calls is not None:
            calls.append(url)
        if url not in pages:
            raise OSError("unreachable")
        return url, parse_page(page(pages[url]))   # raises ValueError("Geparkte Domain") for parked fixtures
    return fetch


def fake_search(results: dict):
    def search(query):
        return results.get(query, []), []
    return search


def no_dns(host):
    return False


def no_imprint(url):
    return None


# --- hit -----------------------------------------------------------------------------------------

def test_hit_from_search_is_verified_and_evidenced():
    hit = wm.Candidate(url="https://www.spinmagic.eu/", origin="search:brave", found_at="https://search.brave.com/search?q=x",
                       rank=0, title="SpinMagIC - Home")
    search = fake_search({'"SpinMagIC" Universität Stuttgart': [hit]})
    best, lookup = wm.match_lookup("SpinMagIC", **SPIN, fetch=fake_fetch({"https://www.spinmagic.eu/": "website_match_spinmagic.html"}),
                                   search=search, resolve=no_dns, imprint=no_imprint)
    assert best.kind == "company" and best.url == "https://www.spinmagic.eu/"
    assert lookup.fields["matched_website"] == "https://www.spinmagic.eu/"
    assert lookup.fields["match_confidence"] == best.confidence >= wm.THRESHOLD
    assert {"Projektname im Seitentitel", "Domain = Projektname", "EXIST erwähnt"} <= set(best.reasons)
    assert [(e.field, str(e.url), e.source) for e in lookup.evidence] == [
        ("matched_website", "https://www.spinmagic.eu/", "Website-Abgleich"),
        ("match_confidence", "https://www.spinmagic.eu/", "Website-Abgleich")]
    assert "Fundstelle: https://search.brave.com/search?q=x" in lookup.evidence[0].finding
    assert lookup.errors == []


def test_hit_by_domain_guess_when_search_finds_nothing():
    calls = []
    best, lookup = wm.match_lookup("SpinMagIC", **SPIN, search=fake_search({}),
                                   resolve=lambda host: host == "spinmagic.eu", imprint=no_imprint,
                                   fetch=fake_fetch({"https://spinmagic.eu/": "website_match_spinmagic.html"}, calls))
    assert calls == ["https://spinmagic.eu/"]          # only resolving guesses are fetched
    assert lookup.fields["matched_website"] == "https://spinmagic.eu/" and best.found_at == "DNS: spinmagic.eu"


def test_about_page_confirms_an_unconfirmed_homepage(tmp_path):
    # autonomiq.de (live probe): the homepage only sells the product, "Über uns" names TU Darmstadt and EXIST.
    home = tmp_path / "home.html"
    home.write_text('<title>autonomIQ - Intelligente CAM-Software</title><h1>CAM-Software mit KI</h1>'
                    '<a href="/ueber-uns/">Über uns</a><a href="/preise/">Preise</a>', encoding="utf-8")
    about = tmp_path / "about.html"
    about.write_text("<h1>Über uns</h1><p>autonomIQ ist aus dem PTW der Technischen Universität Darmstadt hervorgegangen "
                     "und wird im EXIST-Forschungstransfer gefördert.</p>", encoding="utf-8")
    calls = []

    def fetch(url, site):
        calls.append(url)
        files = {"https://autonomiq.de/": home, "https://autonomiq.de/ueber-uns/": about}
        return url, parse_page(files[url].read_text(encoding="utf-8"))

    best, lookup = wm.match_lookup("AutonomIQ", institution="TU Darmstadt, Institut für Produktionsmanagement",
                                   location="Darmstadt", search=fake_search({}), resolve=lambda h: h == "autonomiq.de",
                                   imprint=no_imprint, fetch=fetch)
    assert calls == ["https://autonomiq.de/", "https://autonomiq.de/ueber-uns/"]
    assert lookup.fields["matched_website"] == "https://autonomiq.de/" and "EXIST erwähnt" in best.reasons


def test_broken_certificate_falls_back_to_http():
    calls = []

    def fetch(url, site):
        calls.append(url)
        if url.startswith("https://"):
            raise OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        return url, parse_page(page("website_match_spinmagic.html"))

    best, lookup = wm.match_lookup("SpinMagIC", **SPIN, search=fake_search({}), resolve=lambda host: host == "spinmagic.de",
                                   imprint=no_imprint, fetch=fetch)
    assert calls == ["https://spinmagic.de/", "http://spinmagic.de/"] and lookup.fields["matched_website"] == "http://spinmagic.de/"


def test_hit_via_referrer_link_on_university_news():
    news = "https://www.uni-musterstadt.de/news/quantoflux"
    hit = wm.Candidate(url=news, origin="search:brave", found_at="https://search.brave.com/search?q=y", rank=0,
                       title="Start-up QuantoFlux bringt Sensor zur Marktreife")
    fetch = fake_fetch({news: "website_match_referrer.html", "https://www.quanto-flux.com/": "website_match_referred_home.html"})
    best, lookup = wm.match_lookup("QuantoFlux", institution="Universität Musterstadt", search=fake_search({'"Quanto Flux" Universität Musterstadt': [hit]}),
                                   fetch=fetch, resolve=no_dns, imprint=no_imprint)
    assert lookup.fields["matched_website"] == "https://www.quanto-flux.com/"
    assert best.found_at == news and any(r.startswith("verlinkt von Projektquelle") for r in best.reasons)
    # The university page itself is reported as project page, never as website.
    assert [(e.field, str(e.url)) for e in lookup.evidence if e.field == "project_page"] == [("project_page", news)]


# --- namesake, parking, project page, no hit ---------------------------------------------------------

def test_namesake_is_capped_below_threshold():
    best, lookup = wm.match_lookup("SIMBA", institution="Technische Universität Dresden - Fakultät Maschinenwesen",
                                   executing="Institut für Fertigungstechnik", location="Dresden", search=fake_search({}),
                                   resolve=lambda host: host == "simba.de", imprint=no_imprint,
                                   fetch=fake_fetch({"https://simba.de/": "website_match_namesake.html"}))
    assert best.kind == "company" and best.confidence <= wm.NAMESAKE_CAP < wm.THRESHOLD
    assert "möglicher Namensvetter" in best.reasons[-1]
    assert "matched_website" not in lookup.fields and "match_confidence" not in lookup.fields
    assert lookup.errors and lookup.errors[0].startswith("website_match: keine Website über Schwelle")


def test_parked_domain_is_rejected():
    best, lookup = wm.match_lookup("SideroGaIn", institution="Helmholtz-Zentrum Dresden - Rossendorf e. V.",
                                   search=fake_search({}), resolve=lambda host: host == "siderogain.de", imprint=no_imprint,
                                   fetch=fake_fetch({"https://siderogain.de/": "website_match_parked.html"}))
    assert best is None and lookup.fields == {}
    assert lookup.errors == ["website_match: keine Kandidatin gefunden"]


def test_parked_page_scored_directly_is_rejected():
    lines = ["Siderogain.de", "Diese Domain steht zum Verkauf", "SideroGaIn"]
    result = wm.score_page(wm.Candidate(url="https://siderogain.de/", origin="domain", found_at=""), lines,
                           wm.LeadContext(name="SideroGaIn"))
    assert result.kind == "rejected" and result.reasons == ["Platzhalter-/Parking-Seite"]


def test_university_project_page_is_not_a_website():
    url = "https://www.hzdr.de/db/Cms?pOid=78488&pNid=3438"
    hit = wm.Candidate(url=url, origin="search:duckduckgo", found_at="https://html.duckduckgo.com/html/?q=z", rank=0,
                       title="HZDR Spin-off Siderogain enters the market")
    best, lookup = wm.match_lookup("SideroGaIn", institution="Helmholtz-Zentrum Dresden - Rossendorf e. V. - Helmholtz-Institut Freiberg",
                                   location="Freiberg", search=fake_search({'"SideroGaIn" Helmholtz-Zentrum Dresden': [hit]}),
                                   resolve=no_dns, imprint=no_imprint, fetch=fake_fetch({url: "website_match_project_page.html"}))
    assert best.kind == "project_page" and best.url == url
    assert "matched_website" not in lookup.fields          # LinkedIn link is a platform, not a candidate
    assert [e.field for e in lookup.evidence] == ["project_page"] and lookup.evidence[0].source == "Projektseite (Hochschule)"
    assert [(s.type, str(s.url)) for s in lookup.signals] == [("projektseite", url)]


def test_no_hit():
    best, lookup = wm.match_lookup("Xyzzyqx", search=fake_search({}), resolve=no_dns, imprint=no_imprint, fetch=fake_fetch({}))
    assert best is None and lookup.fields == {} and lookup.evidence == []
    assert lookup.errors == ["website_match: keine Kandidatin gefunden"]


def test_imprint_of_a_namesake_firm_does_not_confirm_the_project():
    # simba.de (live probe): an accounting-software GmbH; its Impressum names "Simba ... GmbH", nothing names the project.
    ctx = wm.LeadContext(name="SIMBA", institution="Technische Universität Dresden - Fakultät Maschinenwesen",
                         executing="Technische Universität Dresden - Institut für Fertigungstechnik", location="Dresden")
    lines = ["Startseite - Simba Computer Systeme GmbH", "Software", "Rechnungswesen", "Buchhaltung", "Start-up-Paket"]
    result = wm.score_page(wm.Candidate(url="https://www.simba.de/", origin="domain", found_at=""), lines, ctx,
                           imprint_text="Impressum\nSimba Computer Systeme GmbH\n90763 Fürth")
    assert "Impressum nennt den Namen" in result.reasons and result.confidence == wm.NAMESAKE_CAP


def test_name_and_discipline_words_are_no_topic_evidence():
    # sensai.io (live probe): an SEO academy; "sensAI" and "Mechanical" must not count as topic terms.
    ctx = wm.LeadContext(name="sensAI", institution="Universität Augsburg, Lehr- & Forschungseinheit Mechanical Engineering",
                         executing="Universität Augsburg, Lehr- & Forschungseinheit Mechanical Engineering", location="Augsburg")
    assert wm.topic_terms(ctx.executing, name="sensAI", exclude="Universität Augsburg Augsburg") == []
    lines = ["Build your own agentic SEO system // SensAI Academy", "Mechanics of search", "Start your journey"]
    result = wm.score_page(wm.Candidate(url="https://sensai.io/", origin="domain", found_at=""), lines, ctx)
    assert result.confidence <= wm.NAMESAKE_CAP


def test_portal_that_only_mentions_the_project_is_not_its_website():
    # campus-start-ups.nrw (API probe): an NRW start-up portal names PoLightFilters, EXIST and Köln in running text.
    ctx = wm.LeadContext(name="PoLightFilters", institution="Universität zu Köln - Department für Chemie", location="Köln")
    lines = ["Campus Start-ups NRW", "Start-ups", "Netzwerk", "Aktuelles", "Über uns", "Kontakt", "Impressum", "News",
             "Das Team PoLightFilters aus Köln erhält eine EXIST-Forschungstransfer-Förderung."]
    result = wm.score_page(wm.Candidate(url="https://www.campus-start-ups.nrw/", origin="search:brave_api", found_at=""), lines, ctx,
                           imprint_text="Impressum PoLightFilters GmbH ist Mitglied")
    assert result.confidence == wm.NAMESAKE_CAP < wm.THRESHOLD
    assert result.reasons[-1].startswith("Name nur erwähnt")


def test_research_group_paper_page_is_a_project_page():
    # tentris.dice-research.org (API probe): a research group's paper page, linked from uni-paderborn.de.
    assert wm.is_academic("https://tentris.dice-research.org/") and not wm.is_academic("https://www.researchly.de/")
    lines = ["ISWC 2020 Paper: Tentris – A Tensor-Based Triple Store", "Download Paper", "Cite as:", "@InProceedings{bigerl2020"]
    result = wm.score_page(wm.Candidate(url="https://tentris.example.org/", origin="referrer", found_at="https://www.uni-paderborn.de/projekt/1"),
                           lines, wm.LeadContext(name="Tentris", institution="Universität Paderborn"))
    assert result.kind == "project_page"


def test_page_without_name_is_rejected_and_agency_is_penalised():
    ctx = wm.LeadContext(name="Iso-Flux", institution="Technische Universität Dortmund")
    other = wm.score_page(wm.Candidate(url="https://isoflux.de/", origin="domain", found_at=""), ["Willkommen", "Wir bauen Häuser"], ctx)
    assert other.kind == "rejected"
    agency = wm.score_page(wm.Candidate(url="https://isoflux.de/", origin="domain", found_at=""),
                           ["Iso-Flux Webdesign", "Ihre Digitalagentur in Dortmund", "Technische Universität Dortmund Kunde"], ctx)
    assert "Malus: Agentur/Webdesign" in agency.reasons and agency.confidence < wm.THRESHOLD


def test_threshold_is_configurable():
    hit = wm.Candidate(url="https://www.spinmagic.eu/", origin="search:brave", found_at="s", rank=0)
    kwargs = dict(**SPIN, fetch=fake_fetch({"https://www.spinmagic.eu/": "website_match_spinmagic.html"}),
                  search=fake_search({'"SpinMagIC" Universität Stuttgart': [hit]}), resolve=no_dns, imprint=no_imprint)
    assert "matched_website" not in wm.match_lookup("SpinMagIC", threshold=0.99, **kwargs)[1].fields


# --- helpers and search parsing ------------------------------------------------------------------

def test_camel_case_names_are_split_for_guesses_and_queries():
    # Versatile Robotics (online measurement): versatile-robotics.com was missed, the DLR page links to it.
    assert wm.spaced_name("VersatileRobotics") == "Versatile Robotics"
    assert "versatile-robotics.com" in wm.domain_guesses("VersatileRobotics")
    assert wm.name_regex("VersatileRobotics").search("versatile robotics gmbh")
    assert wm.host_match("https://versatile-robotics.com/", "VersatileRobotics") == "strong"
    # Mixed-case brand names stay whole.
    for name in ("SpinMagIC", "SideroGaIn", "PoLightFilters", "iNSyT", "DyNAtrix"):
        assert wm.spaced_name(name) == name

    queries = []
    news = "https://event.dlr.de/hm2025/versatile-robotics/"
    referrer = wm.Candidate(url=news, origin="search:brave_api", found_at="https://search.brave.com/search?q=v", rank=0,
                            title="Versatile Robotics – Humanoide Roboter")
    linkedin = wm.Candidate(url="https://www.linkedin.com/in/someone/", origin="search:brave_api", found_at="s", rank=1,
                            title="Someone - Versatile Robotics | LinkedIn")

    def search(query):
        queries.append(query)
        return [linkedin, referrer], []

    pages = {news: "<title>Versatile Robotics</title><p>Ausgründung des DLR-Instituts für Robotik und Mechatronik.</p>"
                   '<a href="https://versatile-robotics.com/de/">Website</a>',
             "https://versatile-robotics.com/": "<title>Versatile Robotics – Humanoide Roboter</title><h1>Versatile Robotics GmbH</h1>"
                                                 "<p>Weßling bei München</p>"}
    calls = []

    def fetch(url, site):
        calls.append(url)
        if url not in pages:
            raise OSError("unreachable")
        return url, parse_page(pages[url])

    best, lookup = wm.match_lookup("VersatileRobotics", institution="Deutsches Zentrum für Luft- und Raumfahrt e.V. - Institut für Robotik",
                                   location="Weßling", search=search, resolve=no_dns, imprint=no_imprint, fetch=fetch)
    assert queries[0] == '"Versatile Robotics" Deutsches Zentrum für Luft- und Raumfahrt e.V.'
    assert "https://www.linkedin.com/in/someone/" not in calls            # social profiles are not scanned
    assert lookup.fields["matched_website"] == "https://versatile-robotics.com/" and best.found_at == news


def test_is_parked_page_is_rejected():
    result = wm.score_page(wm.Candidate(url="http://versatilerobotics.eu/", origin="domain", found_at=""),
                           ["versatilerobotics.eu is parked", "VersatileRobotics"], wm.LeadContext(name="VersatileRobotics"))
    assert result.kind == "rejected"


def test_name_helpers():
    assert wm.slug("Pulse-of-Production") == "pulseofproduction" and wm.clean_name("EXIST_P2P") == "P2P"
    assert wm.name_regex("Pulse-of-Production").search("pulse of production gmbh")
    assert not wm.name_regex("sensAI").search("biosensai")
    assert wm.host_match("https://www.pulse-of-production.de/", "Pulse-of-Production") == "strong"
    assert wm.host_match("https://getspinmagic.com/", "SpinMagIC") == "strong"
    assert wm.host_match("https://spinmagic-sensors.de/", "SpinMagIC") == "weak"
    assert wm.is_academic("https://www.uni-stuttgart.de/x") and wm.is_academic("https://www.hzdr.de/db")
    assert wm.is_academic("https://www.ipa.fraunhofer.de/") and not wm.is_academic("https://www.spinmagic.eu/")
    assert wm.is_platform("https://de.linkedin.com/company/x") and wm.is_platform("https://idw-online.de/de/news1")
    assert wm.domain_guesses("KM") == [] and "spinmagic.de" in wm.domain_guesses("SpinMagIC")
    assert "tum" in wm.institution_terms("Technische Universität München (TUM)")


def test_parse_brave_and_duckduckgo():
    brave = wm.parse_brave(page("website_match_brave.html"))
    assert [u for u, _, _ in brave] == ["https://www.spinmagic.eu/",
                                        "https://www.uni-stuttgart.de/en/university/news/all/Start-up-brings-quantum-sensor-to-market-maturity/"]
    assert brave[0][1] == "SpinMagIC - Home" and "University of Stuttgart & the ENI" in brave[1][2]
    hidden = ('<div data-type="web"><a href="/go/v1/ARqHD1D" target="_self" class="svelte-14r20fy l1">'
              '<cite class="snippet-url">https://manuals.plus <span>› heim</span></cite>'
              '<div class="title search-snippet-title" title="KPL Handbuch">KPL Handbuch</div></a></div>')
    assert wm.parse_brave(hidden) == [("https://manuals.plus", "KPL Handbuch", "")]
    ddg = wm.parse_duckduckgo(page("website_match_ddg.html"))
    assert [u for u, _, _ in ddg] == ["https://www.spinmagic.eu/", "https://idw-online.de/de/news844315"]
    assert ddg[0][2] == "We bring EPR to people."


def test_blocked_engine_is_not_cached_and_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(wm, "_paused_until", {})
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)                       # no .env with a key
    cache = Cache(tmp_path / "c.db")
    calls = []

    def request(url, **kw):
        calls.append(url)
        cache.set(ctx_http.cache_key(url), "x")        # what context.http.request would store
        return page("website_match_blocked.html") if "brave" in url else page("website_match_ddg.html")

    hits, errors = wm.web_search('"SpinMagIC"', cache=cache, request=request)
    assert errors == ["website_match: Suche brave blockiert"]
    assert [h.origin for h in hits] == ["search:duckduckgo", "search:duckduckgo"] and hits[0].rank == 0
    assert cache.get(ctx_http.cache_key(calls[0])) is None             # captcha page dropped from the cache
    hits, errors = wm.web_search('"Other"', cache=cache, request=request)
    assert errors == ["website_match: Suche brave pausiert (zuvor gesperrt)"] and len(calls) == 3


def test_http_429_pauses_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(wm, "_paused_until", {})
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    def request(url, **kw):
        if "brave" in url:
            raise ctx_http.FetchError("search.brave.com: HTTP 429")
        return page("website_match_ddg.html")

    hits, errors = wm.web_search("q", request=request)
    assert hits and errors == ["website_match: Suche brave: search.brave.com: HTTP 429"]
    assert wm._paused_until["brave"] > 0


def test_parse_brave_api():
    hits = wm.parse_brave_api(page("website_match_brave_api.json"))
    assert hits == [("https://www.spinmagic.eu/", "SpinMagIC - Home", "We bring EPR to people. Portable quantum sensor."),
                    ("https://www.uni-stuttgart.de/en/university/news/all/Start-up-brings-quantum-sensor-to-market-maturity/",
                     "Start-up brings quantum sensor to market maturity | University of Stuttgart",
                     "The start-up SpinMagIC works in the laboratories of the University of Stuttgart.")]
    assert wm.parse_brave_api("<html>no json</html>") == [] and wm.parse_brave_api('{"type": "search"}') == []


def test_brave_api_is_used_first_and_keeps_the_key_out_of_urls_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(wm, "_paused_until", {})
    key = "test-key-not-real-123"
    cache = Cache(tmp_path / "c.db")
    calls = []

    def request(url, **kw):
        calls.append((url, kw["headers"], kw["min_interval"]))
        return page("website_match_brave_api.json")

    hits, errors = wm.web_search('"SpinMagIC" Universität Stuttgart', cache=cache, request=request, key=key)
    url, headers, interval = calls[0]
    assert len(calls) == 1 and url.startswith("https://api.search.brave.com/res/v1/web/search?q=") and "country=de" in url
    assert headers["X-Subscription-Token"] == key and headers["Accept"] == "application/json" and interval >= 1.1
    assert key not in url and all(key not in h.found_at for h in hits) and errors == []
    assert [h.origin for h in hits] == ["search:brave_api"] * 2
    assert hits[0].found_at == "https://search.brave.com/search?q=%22SpinMagIC%22+Universit%C3%A4t+Stuttgart"
    assert key not in ctx_http.cache_key(url)
    # A match built from these hits carries no key either.
    best, lookup = wm.match_lookup("SpinMagIC", **SPIN, search=lambda q: (hits, []), resolve=no_dns, imprint=no_imprint,
                                   fetch=fake_fetch({"https://www.spinmagic.eu/": "website_match_spinmagic.html"}))
    assert lookup.fields["matched_website"] == "https://www.spinmagic.eu/"
    assert all(key not in e.finding and key not in str(e.url) for e in lookup.evidence)


def test_api_error_answer_is_not_cached_and_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(wm, "_paused_until", {})
    cache = Cache(tmp_path / "c.db")
    calls = []

    def request(url, **kw):
        calls.append(url)
        if "api.search.brave.com" in url:
            cache.set(ctx_http.cache_key(url), "x")
            return '{"type": "ErrorResponse", "error": {"code": "RATE_LIMITED"}}'
        return page("website_match_brave.html")

    hits, errors = wm.web_search("q", cache=cache, request=request, key="k")
    assert errors == ["website_match: Suche brave_api: unerwartete Antwort"] and hits[0].origin == "search:brave"
    assert cache.get(ctx_http.cache_key(calls[0])) is None


def test_no_key_falls_back_to_html_engines(tmp_path, monkeypatch):
    monkeypatch.setattr(wm, "_paused_until", {})
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert wm.api_key() is None and wm.default_engines(None) == ("brave", "duckduckgo")
    calls = []

    def request(url, **kw):
        calls.append(url)
        return page("website_match_brave.html")

    hits, errors = wm.web_search("q", request=request)
    assert [u.split("?")[0] for u in calls] == ["https://search.brave.com/search"] and hits[0].origin == "search:brave"


def test_api_key_from_env_or_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    assert wm.api_key({"BRAVE_API_KEY": " abc "}) == "abc"
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\nexport BRAVE_API_KEY='from-dotenv'\n", encoding="utf-8")
    assert wm.api_key({}, dotenv=env_file) == "from-dotenv"
    assert wm.api_key({}, dotenv=tmp_path / "missing") is None
    assert wm.api_key({"BRAVE_SEARCH_API_KEY": "second"}, dotenv=tmp_path / "missing") == "second"
    assert wm.api_key({"BRAVE_SEARCH_API_KEY": "second", "BRAVE_API_KEY": "first"}) == "first"
    env_file.write_text("BRAVE_SEARCH_API_KEY=b\nBRAVE_API_KEY=a\n", encoding="utf-8")
    assert wm.api_key({}, dotenv=env_file) == "a"
    assert wm.default_engines("k") == ("brave_api", "brave", "duckduckgo")


def test_dotenv_is_git_ignored():
    ignored = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored


def test_live_result_is_cached_per_lead(tmp_path, monkeypatch):
    cache = Cache(tmp_path / "c.db")
    runs = []

    def collect(ctx, **kw):
        runs.append(ctx.name)
        return [wm.WebsiteMatch(url="https://www.spinmagic.eu/", kind="company", confidence=0.9, reasons=["r"], found_at="f")], [], True

    monkeypatch.setattr(wm, "_collect", collect)
    first = wm.match_lookup("SpinMagIC", cache=cache, **SPIN)[1]
    second = wm.match_lookup("SpinMagIC", cache=cache, **SPIN)[1]
    assert runs == ["SpinMagIC"] and first.fields == second.fields == {"matched_website": "https://www.spinmagic.eu/",
                                                                      "match_confidence": 0.9}


# --- engine wiring -------------------------------------------------------------------------------

def lead(**kw):
    sig = SourceSignal(source="Förderkatalog", type="exist_projekt", date="2024-09-01", subject_lead_id="foekat-03efbw0275",
                       url="https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFBW0275", evidence=CATALOGUE)
    return RawLead(**{"id": "foekat-03efbw0275", "name": "SpinMagIC", "description": SPIN["topic"], "industry": "Industrial / DeepTech",
                      "country": "DE", "location": "Stuttgart", "source_url": str(sig.url), "signals": [sig], **kw})


def lookups(calls):
    def website_match(name, *, cache, institution, executing, location, topic, reference, founders):
        calls.append(("match", name, institution, reference))
        found = Lookup()
        found.add("matched_website", "https://www.spinmagic.eu/", url="https://www.spinmagic.eu/", finding="SpinMagIC: Titel", source="Website-Abgleich")
        found.add("match_confidence", 0.9, url="https://www.spinmagic.eu/", finding="SpinMagIC: Titel", source="Website-Abgleich")
        return None, found

    def imprint(website, *, cache):
        calls.append(("imprint", website))
        return Lookup()

    def web_history(website, name, *, cache, not_before=None):
        calls.append(("wayback", website))
        return Lookup()

    def grants(name, *, institution, reference, cache):
        found = Lookup()
        found.add("match_confidence", 1.0, url="https://foerderportal.bund.de/x", finding="FKZ", source="Förderkatalog")
        return [], found

    return {"cache": None, "model": None, "website_match": website_match, "imprint": imprint, "grants": grants,
            "web_history": web_history, "classify": None, "author": None, "idw": None, "patents": None}


def test_engine_runs_matcher_first_and_uses_the_site():
    calls, loaded = [], []

    def load_pages(url):
        loaded.append(url)
        return [SourceSignal(source="Unternehmenswebsite", type="website", url=url, evidence="SpinMagIC - Home\nWe bring EPR to people")]

    out = enrich(lead(), load_pages=load_pages, lookups=lookups(calls))
    assert calls[0] == ("match", "SpinMagIC", "Universität Stuttgart - Fakultät 5 Informatik, Elektrotechnik und Informationstechnik - "
                                             "Institut für Intelligente Sensorik und Theoretische Elektrotechnik (IIS), Stuttgart, Baden-Württemberg",
                        "03EFBW0275")
    assert ("imprint", "https://www.spinmagic.eu/") in calls and ("wayback", "https://www.spinmagic.eu/") in calls
    assert loaded == ["https://www.spinmagic.eu/"]
    assert out.website is None and str(out.matched_website) == "https://www.spinmagic.eu/"
    assert out.match_confidence == 0.9                  # matcher wins over the Förderkatalog's project match
    assert {e.field for e in out.evidence} >= {"matched_website", "match_confidence", "website_text"}
    site = [s for s in out.scoring_sources if s.type == "website"]
    assert site and site[0].subject_lead_id == out.id
    text = next(e for e in out.evidence if e.field == "website_text")
    assert str(text.url) == "https://www.spinmagic.eu/" and "We bring EPR to people" in text.finding
    assert "website_match" in out.enrichment_sources


def test_engine_skips_matcher_for_known_website_light_and_disabled():
    calls = []
    enrich(lead(website="https://example.org/"), load_pages=lambda url: [], lookups=lookups(calls))
    assert not any(c[0] == "match" for c in calls)
    calls.clear()
    enrich(lead(), light=True, lookups=lookups(calls))
    assert calls == []
    off = lookups(calls)
    off["website_match"] = None
    out = enrich(lead(), load_pages=lambda url: [], lookups=off)
    assert not any(c[0] == "match" for c in calls) and out.matched_website is None
    assert not any(e.startswith("website_match") for e in out.enrichment_errors)
    assert default_lookups(None, match=False)["website_match"] is None
    assert callable(default_lookups(None)["website_match"])


def test_pipeline_preserves_step1_fields_with_matched_site():
    calls = []

    def enricher(raw):
        return enrich(raw, load_pages=lambda url: [], lookups=lookups(calls))

    raw = lead(country_evidence={"field": "country", "url": "https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFBW0275",
                                 "finding": "Förderkatalog FKZ 03EFBW0275: Staat Deutschland", "source": "Förderkatalog"})
    result = collect_context([raw], use_mock=False, enricher=enricher)
    assert result.issues == [] and str(result.leads[0].matched_website) == "https://www.spinmagic.eu/"
    assert result.leads[0].website is None


def test_to_dossier_uses_matched_website():
    from evaluation.engine import _config, to_dossier
    out = EnrichedLead.model_validate({**json.loads(lead().model_dump_json()), "matched_website": "https://www.spinmagic.eu/"})
    assert to_dossier(out, _config())["website"] == "https://www.spinmagic.eu/"


def test_cli_flags(monkeypatch, tmp_path):
    import sys

    from context import __main__ as cli
    seen = {}

    def fake_default(cache, model, patents=False, match=True, match_threshold=None):
        seen.update(match=match, threshold=match_threshold)
        return {"cache": None}

    monkeypatch.setattr(cli, "default_lookups", fake_default)
    monkeypatch.setattr(cli, "collect_context", lambda leads, **kw: __import__("models").ContextResult())
    src = tmp_path / "in.json"
    src.write_text("[" + lead().model_dump_json() + "]", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["context", str(src), str(tmp_path / "out.json"), "--no-match", "--match-threshold", "0.7",
                                      "--cache", "off"])
    cli.main()
    assert seen == {"match": False, "threshold": 0.7}
    monkeypatch.setattr(sys, "argv", ["context", str(src), str(tmp_path / "out.json"), "--match-threshold", "2"])
    with pytest.raises(SystemExit):
        cli.main()


# --- online-measurement fixes: wayback conflict, managing directors -------------------------------

def test_wayback_keeps_early_capture_when_site_names_the_project():
    # m-shunt.com (online measurement): first capture 2023, project 2025; the site names 03EFHB0044/EXIST.
    from datetime import date

    from context.cache import NoCache
    from context.wayback import web_history_lookup

    def fetch(url):
        if "m-shunt.com" in url:
            return [["timestamp", "original", "statuscode"], ["20230723141306", "https://m-shunt.com/", "200"]]
        return []

    plain = web_history_lookup("https://www.m-shunt.com/", "M-Shunt", cache=NoCache(), fetch=fetch, not_before=date(2025, 4, 1))
    assert "first_web_capture" not in plain.fields and any("Namensvetter" in e for e in plain.errors)
    vouched = web_history_lookup("https://www.m-shunt.com/", "M-Shunt", cache=NoCache(), fetch=fetch, not_before=date(2025, 4, 1),
                                 site_confirmed="Website nennt FKZ 03EFHB0044")
    # No namesake error; the early capture is evidence only and never dates the lead before the project.
    assert not any("Website" in e and "Namensvetter" in e for e in vouched.errors)
    assert "first_web_capture" not in vouched.fields and not [s for s in vouched.signals if s.type == "wayback"]
    early = [e for e in vouched.evidence if e.field == "web_capture_before_project"]
    assert early and early[0].source_date == date(2023, 7, 23) and "Website nennt FKZ 03EFHB0044" in early[0].finding
    # "EXIST" alone vouches only for a recent domain: a 2010 capture stays a namesake (behtec.de, online run).
    def old_fetch(url):
        return [["timestamp", "original", "statuscode"], ["20100612000000", "https://behtec.de/", "200"]] if "behtec" in url else []
    exist_only = web_history_lookup("https://behtec.de/", "BEHtec", cache=NoCache(), fetch=old_fetch, not_before=date(2024, 6, 1),
                                    site_confirmed="Website nennt EXIST", confirmed_years=3)
    assert any("Namensvetter" in e for e in exist_only.errors) and not exist_only.evidence


def test_engine_tells_wayback_when_the_site_names_fkz_or_exist():
    from context.engine import _site_confirms_project
    sig = SourceSignal(source="Unternehmenswebsite", type="website", url="https://www.m-shunt.com/news",
                       evidence="Gefördert unter dem Förderkennzeichen 03EFHB0044 im EXIST-Forschungstransfer")
    assert _site_confirms_project([sig], "https://www.m-shunt.com/", "03EFHB0044") == "Website nennt FKZ 03EFHB0044"
    assert _site_confirms_project([sig], "https://www.m-shunt.com/", None) == "Website nennt EXIST"
    assert _site_confirms_project([sig], "https://other.de/", "03EFHB0044") is None

    calls = []
    looks = lookups(calls)

    def web_history(website, name, *, cache, not_before=None, site_confirmed=None):
        calls.append(("wayback", website, site_confirmed))
        return Lookup()

    looks["web_history"] = web_history
    pages = [SourceSignal(source="Unternehmenswebsite", type="website", url="https://www.spinmagic.eu/",
                          evidence="SpinMagIC - Home\nsupported by EXIST (03EFBW0275)")]
    enrich(lead(), load_pages=lambda url: pages, lookups=looks)
    assert ("wayback", "https://www.spinmagic.eu/", "Website nennt FKZ 03EFBW0275") in calls

    def web_history_years(website, name, *, cache, not_before=None, site_confirmed=None, confirmed_years=None):
        calls.append(("wayback-years", site_confirmed, confirmed_years))
        return Lookup()

    looks["web_history"] = web_history_years
    exist_page = [SourceSignal(source="Unternehmenswebsite", type="website", url="https://www.spinmagic.eu/", evidence="EXIST team")]
    enrich(lead(), load_pages=lambda url: exist_page, lookups=looks)
    assert ("wayback-years", "Website nennt EXIST", 3) in calls


def test_managing_directors_get_openalex_profiles():
    from models import FounderProfile
    calls = []
    looks = lookups(calls)

    def imprint(website, *, cache):
        found = Lookup()
        found.add("imprint_url", "https://www.spinmagic.eu/imprint", url="https://www.spinmagic.eu/imprint", finding="Impressum", source="Impressum")
        found.add("managing_directors", ["Erika Musterfrau", "Max Beispiel"], url="https://www.spinmagic.eu/imprint",
                  finding="Geschäftsführer: Erika Musterfrau, Max Beispiel", source="Impressum")
        return found

    def author(name, *, institution, field_terms, cache):
        calls.append(("author", name, institution))
        assert field_terms == []          # the project name is no product field (it gave "0 Papers im Produktfeld")
        if name == "Erika Musterfrau":
            return FounderProfile(name=name, institution="University of Stuttgart", openalex_url="https://openalex.org/A1",
                                  works_total=12, match_confidence=0.9, source_url="https://openalex.org/A1"), Lookup()
        found = Lookup()
        found.errors.append("openalex: kein Treffer für %s" % name)
        return None, found

    looks.update(imprint=imprint, author=author)
    out = enrich(lead(), load_pages=lambda url: [], lookups=looks)
    assert [c for c in calls if c[0] == "author"] == [("author", "Erika Musterfrau", "Universität Stuttgart"),
                                                       ("author", "Max Beispiel", "Universität Stuttgart")]
    profiles = {p.name: p for p in out.founder_profiles}
    assert profiles["Erika Musterfrau"].works_total == 12 and profiles["Erika Musterfrau"].works_in_field is None
    assert profiles["Erika Musterfrau"].match_confidence == 0.9
    assert profiles["Erika Musterfrau"].role == "Geschäftsführung (Impressum)"
    assert str(profiles["Max Beispiel"].source_url) == "https://www.spinmagic.eu/imprint" and profiles["Max Beispiel"].openalex_url is None
    assert out.managing_directors == ["Erika Musterfrau", "Max Beispiel"] and out.founders == []


def test_no_director_lookup_when_step1_has_founders():
    calls = []
    looks = lookups(calls)
    looks["author"] = lambda name, **kw: (calls.append(("author", name)), (None, Lookup()))[1]
    looks["imprint"] = lambda website, *, cache: Lookup(fields={"managing_directors": ["Erika Musterfrau"]})
    enrich(lead(founders=["Anna Gründerin"]), load_pages=lambda url: [], lookups=looks)
    assert [c for c in calls if c[0] == "author"] == [("author", "Anna Gründerin")]


def test_imprint_drops_non_names_and_university_representatives():
    from context.imprint import parse_imprint
    # Online run 21.11.2026: Ymolution "Product Development", BEHtec "Commercial Register"/"VAT ID", MillionMolecules
    # "Rector Kerstin Krieglstein" (a university imprint).
    assert parse_imprint("Impressum\nIt is legally represented by the Rector Prof. Dr. Kerstin Krieglstein.").get("managing_directors") is None
    assert parse_imprint("Impressum\nGeschäftsführer: Product Development\nManaging Directors: Commercial Register, VAT ID"
                         ).get("managing_directors") is None
    names, _ = parse_imprint("Impressum\nGeschäftsführer: Dr. Erika Musterfrau, Max Beispiel")["managing_directors"]
    assert names == ["Erika Musterfrau", "Max Beispiel"]
