"""Offline tests for context/dbsearch.py (Dealroom/Crunchbase/PitchBook/Tracxn via Brave API). No network."""
from context import website_match as wm
from context.dbsearch import database_lookup, query_for
from context.engine import enrich
from context.lookup import Lookup
from models import RawLead, SourceSignal

CATALOGUE = ("Förderkennzeichen: 03EFSN0241\nProgramm: EXIST-Forschungstransfer\nThema: BotFellows\n"
             "Förderempfänger: Fraunhofer-Gesellschaft, München, Bayern\n"
             "Ausführende Stelle: Fraunhofer-Institut für Werkzeugmaschinen und Umformtechnik (IWU), Chemnitz, Sachsen\n"
             "Laufzeit: 01.05.2024 bis 30.04.2026\nFördersumme: 1.000.000,00 EUR")


def hit(url, title, snippet, rank=0):
    return wm.Candidate(url=url, origin="search:brave_api", found_at="https://search.brave.com/search?q=x", rank=rank,
                        title=title, snippet=snippet)


# Shortened from the live Brave API answer for "BotFellows" (21.11.2026).
BOTFELLOWS = [
    hit("https://tracxn.com/d/companies/botfellows/__n0fHxzemz", "Botfellows - 2026 Company Profile, Team & Competitors - Tracxn",
        "Botfellows - Developer of robotic automation software and safety solutions for industrial applications ."),
    hit("https://pitchbook.com/profiles/company/267614-47", "BOTfriends 2026 Company Profile: Valuation, Funding & Investors",
        "Information on valuation, funding, cap tables, investors, and executives for BOTfriends."),
    hit("https://tracxn.com/d/companies/project-empathy/__pXMql", "Project Empathy - 2025 Company Profile - Tracxn",
        "Botfellows - Chemnitz based, 2024 founded, Unfunded company · Atharv Lifestyle - Mumbai based"),
]
WEBSITE = "Home - Botfellows\nModular automation solutions for safe, flexible industrial robotics."


def test_confirmed_profile_sets_in_databases_true():
    result = database_lookup("BotFellows", website="https://botfellows.com/", location="Chemnitz",
                             institution="Fraunhofer-Institut für Werkzeugmaschinen und Umformtechnik (IWU)",
                             website_text=WEBSITE, search=lambda q: (BOTFELLOWS, []))
    assert result.fields["in_databases"] is True
    assert result.fields["database_urls"] == ["https://tracxn.com/d/companies/botfellows/__n0fHxzemz"]
    ev = [e for e in result.evidence if e.field == "in_databases"][0]
    assert ev.source == "Datenbanksuche (Brave)" and str(ev.url) == "https://tracxn.com/d/companies/botfellows/__n0fHxzemz"


def test_namesake_profile_does_not_count():
    # crunchbase.com/organization/insyt is a social app, not the LMU spin-off iNSyT.
    hits = [hit("https://www.crunchbase.com/organization/insyt", "Insyt - Crunchbase Company Profile & Funding",
                "Insyt is a social networking application that lets you connect with your community.")]
    result = database_lookup("iNSyT", website="https://www.insyt.solutions/", location="München",
                             institution="Ludwig-Maximilians-Universität München - Fakultät für Physik",
                             website_text="iNSyT solutions – Observing without Disturbing\nQuantum-Dots Nanoparticles Battery",
                             search=lambda q: (hits, []))
    assert result.fields["in_databases"] is False and "database_urls" not in result.fields
    assert any("möglicher Namensvetter" in e for e in result.errors)
    ev = result.evidence[0]
    assert str(ev.url).startswith("https://search.brave.com/search?q=") and "kein Profil" in ev.finding


def test_exist_in_snippet_confirms_and_name_must_be_in_title():
    hits = [hit("https://pitchbook.com/profiles/company/572385-34", "iNSyT Technologies 2026 Company Profile",
                "LMU Innovation & Entrepreneurship Center, Exist Federal Ministry of Economics and Energy have invested in iNSyT"),
            hit("https://www.crunchbase.com/organization/other", "Other GmbH", "Partner of iNSyT in Germany")]
    result = database_lookup("iNSyT", location="München", search=lambda q: (hits, []))
    assert result.fields["database_urls"] == ["https://pitchbook.com/profiles/company/572385-34"]


def test_no_key_means_no_fields(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    result = database_lookup("BotFellows")
    assert result.fields == {} and result.errors == ["dbsearch: kein BRAVE_API_KEY, Datenbanken nur über Wayback geprüft"]


def test_blocked_search_sets_nothing():
    result = database_lookup("BotFellows", search=lambda q: ([], ["website_match: Suche brave_api: HTTP 429"]))
    assert result.fields == {} and result.errors == ["dbsearch: Suche brave_api: HTTP 429"]


def test_query_uses_spaced_name_and_four_sites():
    q = query_for("VersatileRobotics")
    assert q.startswith('"Versatile Robotics" (') and all(s in q for s in ("dealroom.co", "crunchbase.com", "pitchbook.com", "tracxn.com"))


def _lead():
    sig = SourceSignal(source="Förderkatalog", type="exist_projekt", date="2024-05-01", subject_lead_id="foekat-03efsn0241",
                       url="https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFSN0241", evidence=CATALOGUE)
    return RawLead(id="foekat-03efsn0241", name="BotFellows", description="„BotFellows“ – Projekt.", industry="Industrial / DeepTech",
                   country="DE", location="Chemnitz", source_url=str(sig.url), signals=[sig])


def _lookups(db_result, wayback_result):
    def website_match(name, **kw):
        found = Lookup()
        found.add("matched_website", "https://botfellows.com/", url="https://botfellows.com/", finding="x", source="Website-Abgleich")
        return None, found
    return {"cache": None, "website_match": website_match, "imprint": None, "grants": None, "classify": None, "author": None,
            "idw": None, "patents": None, "web_history": lambda website, name, *, cache, not_before=None: wayback_result,
            "databases": lambda name, **kw: db_result}


def test_engine_db_search_wins_over_wayback_and_its_evidence_comes_first():
    wayback = Lookup()
    wayback.add("in_databases", False, url="https://web.archive.org/cdx/search/cdx?url=x", finding="kein Archiv", source="Wayback CDX")
    db = database_lookup("BotFellows", website="https://botfellows.com/", location="Chemnitz", website_text=WEBSITE,
                         search=lambda q: (BOTFELLOWS, []))
    out = enrich(_lead(), load_pages=lambda url: [], lookups=_lookups(db, wayback))
    assert out.in_databases is True and [str(u) for u in out.database_urls] == ["https://tracxn.com/d/companies/botfellows/__n0fHxzemz"]
    first = next(e for e in out.evidence if e.field == "in_databases")
    assert first.source == "Datenbanksuche (Brave)"
    assert "databases" in out.enrichment_sources


def test_engine_keeps_wayback_profile_when_search_finds_nothing():
    wayback = Lookup()
    wayback.add("in_databases", True, url="https://web.archive.org/web/2024/https://www.crunchbase.com/organization/botfellows",
                finding="archiviertes Profil", source="Wayback CDX")
    db = database_lookup("BotFellows", search=lambda q: ([], []))
    out = enrich(_lead(), load_pages=lambda url: [], lookups=_lookups(db, wayback))
    assert out.in_databases is True
    assert next(e for e in out.evidence if e.field == "in_databases").source == "Wayback CDX"
