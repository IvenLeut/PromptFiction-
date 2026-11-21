"""Offline tests for context/team.py (team composition). No network; fixtures are pseudonymised Brave answers."""
import json
from pathlib import Path

from context import team
from context import website_match as wm
from context.cache import Cache
from context.engine import enrich
from context.lookup import Lookup
from models import FounderProfile, RawLead, SourceSignal

FIX = Path(__file__).parent / "fixtures" / "team"


def hits(name):
    data = json.loads((FIX / name).read_text(encoding="utf-8"))
    return [wm.Candidate(url=h["url"], origin="search:brave_api", found_at="https://search.brave.com/search?q=x", rank=i,
                         title=h["title"], snippet=h["snippet"]) for i, h in enumerate(data["hits"])]


def search_with(results):
    calls = []

    def search(query):
        calls.append(query)
        return results.get(query.split('"')[1] if query.startswith("site:linkedin.com/in") else "open", []), []
    search.calls = calls
    return search


def by_name(profiles):
    return {p.name: p for p in profiles}


# --- LinkedIn rules --------------------------------------------------------------------------------

def test_likers_dropped_founders_kept_with_role_background_education():
    found = team.people_from_linkedin(hits("linkedin_company.json"), "Robofant", [], location="Chemnitz",
                                      website="https://www.robofant.de/")
    people = {p.name: p for p in found}
    assert "Karl Liker" not in people                       # other employer: only liked a company post
    lina = people["Lina Muster"]                             # "（林娜）" stripped
    assert lina.role == "Co-Founder & Head of Engineering (LinkedIn)" and lina.background == "tech"
    assert lina.institution == "Technische Universität Dresden"
    eva = people["Eva Kauf"]
    assert eva.role.startswith("CEO & Co-Founder") and eva.background == "business"
    assert people["Paul Chef"].role == "CEO (LinkedIn)" and people["Paul Chef"].background is None   # CEO alone
    # Without known names, a confirmed current employee without founder role is a team member (post snippet, no role);
    # "Tom Teil" has the lead as current company but nothing confirms him (no place, school, domain): dropped.
    assert people["Max Beispiel"].role == "Teammitglied (LinkedIn)" and "Tom Teil" not in people


def test_unconfirmed_current_employees_are_still_dropped():
    errors = []
    lone = [h for h in hits("linkedin_company.json") if "tom-teil" in h.url]
    assert team.people_from_linkedin(lone, "Robofant", [], location="Chemnitz", errors=errors) == []
    assert errors and "möglicher Namensvetter" in errors[0]


def test_known_names_need_no_confirmation_and_extra_members_are_skipped():
    found = team.people_from_linkedin(hits("linkedin_company.json"), "Robofant", ["Tom Teil", "Eva Kauf"])
    names = {p.name for p in found}
    assert {"Tom Teil", "Eva Kauf", "Lina Muster", "Paul Chef"} <= names     # known + founder roles
    assert "Max Beispiel" not in names                                         # no founder role, names are known


def test_namesakes_rejected_and_confirmed_by_place():
    found = team.people_from_linkedin(hits("linkedin_namesakes.json"), "SECARA", [], location="Aachen")
    assert [p.name for p in found] == ["Fabian Neu"]                         # surname "Secara" and "Secara Consulting" out
    assert found[0].role == "CTO & Co-Founder (LinkedIn)" and found[0].background == "tech"
    us = team.people_from_linkedin(hits("linkedin_namesakes.json"), "AutonomIQ", [], location="Darmstadt")
    assert us == []                                                           # US firm of the same name (Fremont)


# --- texts ---------------------------------------------------------------------------------------

def test_press_caption_gives_four_people_and_roles():
    data = json.loads((FIX / "press_caption.json").read_text(encoding="utf-8"))
    people = team.merge(team.people_from_text(data["text"], data["url"], "Metallgold", "Presse"))
    names = [p.name for p in people]
    assert names[:4] == ["Peter Probe", "Aratrika Beispiel", "Jonas Test", "Rohan Muster"]
    assert "Björn Fremd" not in names                                        # outside the caption brackets
    roles = {p.name: p.role for p in people}
    assert roles["Rohan Muster"] == "CEO (Presse)"
    assert roles["Jonas Test"] == "Mitgründer (Presse)" and by_name_bg(people, "Jonas Test") == "business"
    assert roles["Peter Probe"] == "Teammitglied (Presse)"


def by_name_bg(people, name):
    return next(p.background for p in people if p.name == name)


def test_founders_of_other_companies_in_a_winner_list_are_dropped():
    # Aiina-Robotics pilot: an award page lists "Name, Gründerin <other firm>" for several teams.
    text = ("Marie Probe, Gründerin Bioexotec, Andreas Test, Gründer ReduCO2, Alice Fremd, Zeidler-Forschungs-Stiftung, "
            "Dr. Lena Muster, Gründerin Aiina Robotics, Prof. Hans Jury")
    people = team.people_from_text(text, "https://example.org/award", "Aiina-Robotics", "Presse")
    assert [(p.name, p.role) for p in people] == [("Lena Muster", "Gründerin (Presse)")]


def test_dash_enclosed_team_list():
    # BotFellows idw article: "Die Botfellows – Dr.-Ing. A (CEO), B, C und D – sind seit vielen Jahren ein Team".
    text = "Die Botfellows – Dr.-Ing. Max Probe (CEO), Lars Test, Paul Muster und Jan Beispiel – sind seit Jahren ein Team am Institut."
    people = {p.name: p.role for p in team.people_from_text(text, "https://example.org/idw", "BotFellows", "Presse")}
    assert people == {"Max Probe": "CEO (Presse)", "Lars Test": "Teammitglied (Presse)", "Paul Muster": "Teammitglied (Presse)",
                      "Jan Beispiel": "Teammitglied (Presse)"}


def test_alleingruender_only_when_a_source_says_so():
    text = "Lea Solo, Alleingründerin von Metallgold, entwickelt den Prozess."
    people = team.people_from_text(text, "https://example.org/a", "Metallgold", "Presse")
    assert [p.role for p in people] == ["Alleingründer (Presse)"]
    assert team.people_from_text("Lea Solo, CEO von Metallgold.", "https://example.org/a", "Metallgold", "Presse")[0].role == "CEO (Presse)"


def test_funding_logo_caption_is_no_founder():
    # SpinMagIC: "Founded by:" is the ministry logo caption ("Funded by"), followed by no names.
    text = "SpinMagIC team\nFounded by:\nbased on a resolution of the German Bundestag"
    assert team.people_from_text(text, "https://example.org/", "SpinMagIC", "Website") == []


# --- team_lookup ---------------------------------------------------------------------------------

def test_no_hit_means_no_profiles_and_no_solo(tmp_path):
    profiles, lookup = team.team_lookup("Robofant", search=lambda q: ([], []), cache=Cache(tmp_path / "c.db"))
    assert profiles == [] and not any("solo" in (p.role or "").lower() for p in profiles)


def test_no_api_key_is_a_noop(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    profiles, lookup = team.team_lookup("Robofant", cache=Cache(tmp_path / "c.db"))
    assert profiles == [] and lookup.errors == ["team: kein BRAVE_API_KEY, nur vorhandene Texte ausgewertet"]


def test_query_plan_and_privacy(tmp_path):
    results = {"Robofant": hits("linkedin_company.json")}
    search = search_with(results)
    profiles, lookup = team.team_lookup("Robofant", location="Chemnitz", institution="Fraunhofer IWU", known_names=["Eva Kauf", "Hans Fehlt"],
                                        search=search, cache=Cache(tmp_path / "c.db"))
    assert search.calls[0] == 'site:linkedin.com/in "Robofant"'
    assert search.calls[1] == 'site:linkedin.com/in "Hans Fehlt" "Robofant"'   # one missing known name, no open search
    assert len(search.calls) <= team.MAX_QUERIES
    dumped = json.dumps([p.model_dump(mode="json") for p in profiles] + [e.finding for e in lookup.evidence], ensure_ascii=False)
    for private in ("Location", "Chemnitz, Sachsen", "connections", "@", "+49"):
        assert private not in dumped                                           # no place, contact or connection data
    assert all(str(p.source_url).startswith("https://www.linkedin.com/in/") for p in profiles)
    assert all(p.prior_experience == [] for p in profiles)


def test_short_name_gets_the_place_and_open_search_without_founders(tmp_path):
    search = search_with({})
    team.team_lookup("Robix", location="Stuttgart", institution="Fraunhofer IPA, Stuttgart", search=search, cache=Cache(tmp_path / "c.db"))
    assert search.calls[0] == 'site:linkedin.com/in "Robix" Stuttgart'
    assert search.calls[1].startswith('"Robix" (Gründer OR Gründerteam') and search.calls[1].endswith("Fraunhofer IPA")
    # "KM" (full run: a namesake "Karin ... - KM"): no person search at all for names under 4 characters.
    short = search_with({})
    profiles, lookup = team.team_lookup("KM", location="Stuttgart", search=short, cache=Cache(tmp_path / "c.db"))
    assert short.calls == [] and profiles == [] and "zu kurz" in lookup.errors[0]


def test_page_labels_and_contact_brokers_are_no_people():
    # PoLightFilters (full run): a RocketReach snippet gave the "person" "Legal Notice" as Geschäftsführer.
    assert team.clean_person("Legal Notice") is None
    broker = [wm.Candidate(url="https://rocketreach.co/polightfilters-profile_b69d", origin="search:brave_api", found_at="x",
                           title="PoLightFilters Management Team", snippet="Lena Probe, CEO von PoLightFilters.")]
    assert team.people_from_press(broker, "PoLightFilters") == []


def test_live_result_is_cached_and_deterministic(tmp_path, monkeypatch):
    cache = Cache(tmp_path / "c.db")
    calls = []

    def fake_search(company, known, from_texts, **kw):
        calls.append(company)
        return [team.Person("Lina Muster", "CTO (LinkedIn)", "https://www.linkedin.com/in/lina/", background="tech")], True

    monkeypatch.setattr(team, "_search", fake_search)
    first = team.team_lookup("Robofant", cache=cache)[0]
    second = team.team_lookup("Robofant", cache=cache)[0]
    assert calls == ["Robofant"] and [p.model_dump() for p in first] == [p.model_dump() for p in second]


# --- engine --------------------------------------------------------------------------------------

CATALOGUE = ("Förderkennzeichen: 03EFSN9999\nProgramm: EXIST-Forschungstransfer\nThema: Robofant\n"
             "Förderempfänger: Fraunhofer-Gesellschaft, München, Bayern\n"
             "Ausführende Stelle: Fraunhofer-Institut für Werkzeugmaschinen (IWU), Chemnitz, Sachsen\nLaufzeit: 01.05.2024 bis 30.04.2026")


def lead():
    sig = SourceSignal(source="Förderkatalog", type="exist_projekt", date="2024-05-01", subject_lead_id="foekat-03efsn9999",
                       url="https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFSN9999", evidence=CATALOGUE)
    return RawLead(id="foekat-03efsn9999", name="Robofant", description="„Robofant“ – Projekt.", industry="Industrial / DeepTech",
                   country="DE", location="Chemnitz", source_url=str(sig.url), signals=[sig])


def test_engine_merges_team_into_impressum_profiles_and_runs_openalex_for_new_people():
    seen = {}

    def imprint(website, *, cache):
        found = Lookup()
        found.add("imprint_url", "https://www.robofant.de/impressum", url="https://www.robofant.de/impressum", finding="I", source="Impressum")
        found.add("managing_directors", ["Eva Kauf"], url="https://www.robofant.de/impressum", finding="GF: Eva Kauf", source="Impressum")
        return found

    def website_match(name, **kw):
        found = Lookup()
        found.add("matched_website", "https://www.robofant.de/", url="https://www.robofant.de/", finding="x", source="Website-Abgleich")
        return None, found

    def team_lookup(name, *, website, location, institution, known_names, texts, cache):
        seen["known"] = known_names
        return [FounderProfile(name="Eva Kauf", role="CEO & Co-Founder (LinkedIn)", background="business",
                               source_url="https://www.linkedin.com/in/eva/", match_confidence=0.9),
                FounderProfile(name="Lina Muster", role="CTO (LinkedIn)", background=None,
                               source_url="https://www.linkedin.com/in/lina/", match_confidence=0.8)], Lookup()

    def author(name, *, institution, field_terms, cache):
        seen.setdefault("author", []).append(name)
        if name == "Lina Muster":
            return FounderProfile(name=name, openalex_url="https://openalex.org/A9", works_total=7, match_confidence=0.9), Lookup()
        return None, Lookup()

    looks = {"cache": None, "website_match": website_match, "imprint": imprint, "grants": None, "web_history": None, "classify": None,
             "author": author, "idw": None, "patents": None, "team": team_lookup}
    out = enrich(lead(), load_pages=lambda url: [], lookups=looks)
    assert seen["known"] == ["Eva Kauf"] and seen["author"] == ["Eva Kauf", "Lina Muster"]
    profiles = by_name(out.founder_profiles)
    assert len(out.founder_profiles) == 2                                       # Eva merged, not duplicated
    assert profiles["Eva Kauf"].role == "Geschäftsführung (Impressum); CEO & Co-Founder (LinkedIn)"
    assert profiles["Eva Kauf"].background == "business" and str(profiles["Eva Kauf"].source_url) == "https://www.robofant.de/impressum"
    lina = profiles["Lina Muster"]
    assert lina.background == "tech" and lina.works_total == 7 and str(lina.openalex_url) == "https://openalex.org/A9"
    assert any(e.field == "founder_profiles" and "background tech aus OpenAlex" in e.finding for e in out.evidence)
    assert "team" in out.enrichment_sources
