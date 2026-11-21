"""Startup-database check (Dealroom, Crunchbase, PitchBook, Tracxn) via the Brave Search API.

`context/wayback.py` only asks whether an archived Crunchbase/Dealroom page exists for a slug. That misses live
profiles (BotFellows on Dealroom and Tracxn, iNSyT on PitchBook and Tracxn; final gate M3). `database_lookup`
asks the Brave Search API once per lead:

    "<name>" (site:dealroom.co OR site:crunchbase.com OR site:pitchbook.com OR site:tracxn.com)

A hit counts as the lead's profile only if (1) it is a company-profile URL of one of the four databases, (2) the
project name stands in its title, and (3) title/snippet confirm the lead: website domain, place, "Germany",
institute, EXIST, two words shared with the lead's website text, or another hit's snippet "<Name> - <place> based"
(Tracxn lists). Without (3) the hit is a possible namesake (crunchbase.com/organization/insyt is a social app):
reported in `errors`, never `in_databases=True`.

Result (format agreed with `scorer`): `in_databases` True/False with Evidence field="in_databases",
source="Datenbanksuche (Brave)", url = first profile URL (True) or the neutral, key-free search URL (False);
`database_urls` = the confirmed profiles. Without an API key nothing is searched and nothing is set (the Wayback
result stays, the error says "nur Wayback geprüft"). One request per lead, cached in `.cache/context.db`.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus, urlsplit

from context.lookup import SOURCE_DB_SEARCH, Lookup
from context.web import site_key
from context import website_match as wm

SOURCE = SOURCE_DB_SEARCH
DB_PROFILES = {   # host -> (label, path of a company profile)
    "dealroom.co": ("Dealroom", re.compile(r"^/companies/[^/]+/?$")),
    "app.dealroom.co": ("Dealroom", re.compile(r"^/companies/[^/]+/?$")),
    "crunchbase.com": ("Crunchbase", re.compile(r"^/organization/[^/]+/?$")),
    "pitchbook.com": ("PitchBook", re.compile(r"^/profiles/company/[^/]+/?$")),
    "tracxn.com": ("Tracxn", re.compile(r"^/d/companies/[^/]+/[^/]+/?$")),
}
SITES = "(site:dealroom.co OR site:crunchbase.com OR site:pitchbook.com OR site:tracxn.com)"
GERMANY = re.compile(r"\b(?:germany|deutschland)\b")
# Everyday words of profiles and websites ("explore", "through", "applications") say nothing about identity.
COMMON_STEMS = {"company", "compani", "profile", "funding", "investo", "competi", "informa", "platfor", "valuati", "develop",
                "solutio", "through", "explore", "applica", "service", "special", "technic", "technol", "digital", "content",
                "network", "communi", "faster", "insight", "product", "custome", "provide", "provider", "manage", "managem",
                "busines", "innovat", "experie", "support", "contact", "founded", "located", "startup", "people", "global",
                "leading", "quality", "process", "systems", "enables", "offers", "helping", "simple", "smarter", "future",
                "unterne", "loesung", "entwick", "kontakt", "produkt", "kunden", "leistun", "informat", "dienstl"}
HEAD_CHARS = 1500    # website text compared with a profile snippet
MIN_SHARED = 3       # shared content words (7-letter stems) that confirm a profile


def query_for(name: str) -> str:
    return '"%s" %s' % (wm.spaced_name(name), SITES)


def _profile(url: str) -> str | None:
    host = site_key(url)
    entry = DB_PROFILES.get(host) or DB_PROFILES.get(host.split(".", 1)[-1])
    return entry[0] if entry and entry[1].match(urlsplit(url).path) else None


def _words(text: str) -> set[str]:
    return {w[:7] for w in re.findall(r"[a-z]{6,}", wm.fold(text))} - COMMON_STEMS


def database_lookup(name: str, *, website: str | None = None, location: str | None = None, institution: str | None = None,
                    website_text: str = "", cache=None, search=None) -> Lookup:
    """Search the four startup databases for the lead; see module docstring. Never raises."""
    result = Lookup()
    name_re = wm.name_regex(name)
    if name_re is None:
        result.errors.append("dbsearch: kein verwertbarer Name")
        return result
    query = query_for(name)
    if search is None:
        key = wm.api_key()
        if not key:
            result.errors.append("dbsearch: kein BRAVE_API_KEY, Datenbanken nur über Wayback geprüft")
            return result

        def search(q):
            return wm.web_search(q, cache=cache, engines=("brave_api",), key=key)
    try:
        hits, errors = search(query)
    except Exception as exc:  # noqa: BLE001 - contract: never raise
        hits, errors = [], ["dbsearch: %s" % type(exc).__name__]
    if errors and not hits:
        result.errors.extend(e.replace("website_match:", "dbsearch:") for e in errors)
        return result
    place = wm.fold(re.split(r"[\s,(]", location.strip())[0]) if location and location.strip() else ""
    host = site_key(website) if website else ""           # full domain: the bare label is just the name again
    inst_terms = wm.institution_terms(institution)
    # Head of the website only (claim, product lines); the name, its parts and the place are no evidence of identity.
    own_words = _words(website_text[:HEAD_CHARS]) - {p[:7] for p in wm.name_parts(name)} - {wm.slug(name)[:7], place[:7]}
    based = bool(place) and any(re.search(name_re.pattern + r".{0,40}" + re.escape(place), wm.fold(h.snippet)) for h in hits)
    profiles = []
    for hit in hits:
        label = _profile(hit.url)
        if not label or not name_re.search(wm.fold(hit.title)):
            continue
        text = wm.fold(hit.title + " " + hit.snippet)
        reasons = []
        if host and host in (hit.title + " " + hit.snippet).lower():
            reasons.append("Website-Domain %s" % host)
        if place and wm.contains(text, place):
            reasons.append("Ort")
        if GERMANY.search(text):
            reasons.append("Deutschland")
        if any(wm.contains(text, t) for t in inst_terms):
            reasons.append("Institut")
        if wm.EXIST.search(hit.title + " " + hit.snippet):
            reasons.append("EXIST")
        shared = own_words & _words(hit.title + " " + hit.snippet)
        if len(shared) >= MIN_SHARED:
            reasons.append("gleiche Begriffe wie die Website (%s)" % ", ".join(sorted(shared)[:3]))
        if based and label == "Tracxn":
            reasons.append("Tracxn-Liste nennt %s mit Ort" % name)
        if reasons:
            profiles.append((label, hit, reasons))
        else:
            result.errors.append("dbsearch: %s-Profil %s ohne Bezug zum Lead, möglicher Namensvetter" % (label, hit.url))
    search_url = wm.PUBLIC_SEARCH_URL["brave_api"] % quote_plus(query)
    if profiles:
        first = profiles[0]
        finding = "; ".join("%s: %s (%s)" % (label, hit.url, ", ".join(reasons)) for label, hit, reasons in profiles)
        result.add("in_databases", True, url=first[1].url, finding="Profil in Startup-Datenbank gefunden. " + finding, source=SOURCE)
        urls = list(dict.fromkeys(hit.url for _, hit, _ in profiles))
        result.add("database_urls", urls, url=first[1].url, finding=finding, source=SOURCE)
    else:
        result.add("in_databases", False, url=search_url, source=SOURCE,
                   finding="Datenbanksuche (Dealroom, Crunchbase, PitchBook, Tracxn) über Brave: kein Profil zu %s" % name)
    return result
