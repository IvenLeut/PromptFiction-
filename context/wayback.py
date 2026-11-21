"""Web history via the Wayback Machine CDX API (`first_web_capture`, Crunchbase/Dealroom presence).

Data source: ``https://web.archive.org/cdx/search/cdx`` with ``output=json``, ``filter=statuscode:200``
and ``limit=1``, which returns the earliest successful capture of exactly one URL (no wildcards,
no ``matchType``). Two things are derived from it:

* ``first_web_capture``: the earliest 200 capture of the company website host. Only the host is
  queried (scheme, ``www.``, port and path are stripped), so ``https://www.firma.de/de/start``
  becomes the query ``url=firma.de``. No ``from=`` filter is applied: a domain that was parked or
  owned by someone else before the start-up bought it yields an old first capture, but we cannot
  know that from the CDX index alone, and cutting off at an arbitrary year would hide genuinely
  old companies. Downstream code should compare the date with ``founded_on`` instead of trusting
  it blindly; the capture URL is in the evidence so a human can check what was archived.
* ``in_databases`` / ``first_db_date`` / ``database_urls``: candidate profile URLs on Crunchbase
  and Dealroom are built from the company name (see ``slugs``) and looked up one by one. A profile
  counts as found only if the CDX index has at least one 200 capture of exactly that URL.
  ``in_databases`` is True if any profile was found, False if every query returned an empty index
  and None if any query failed (then we simply do not know).

Caveats, deliberately not worked around:

* Absence of a Wayback capture does **not** prove absence of a profile. The Wayback Machine only
  archives Crunchbase/Dealroom pages that were crawled or saved by someone, both sites block or
  throttle crawlers, and the CDX index lists robots-blocked pages inconsistently (captures appear,
  disappear and reappear). False negatives are therefore expected; a False here means "not seen in
  the archive", not "not in the database". Slug guessing adds a second source of false negatives:
  Crunchbase appends ``-2``/``-3`` or a city for name clashes, which we do not enumerate.
* The CDX API is slow (observed 1.5-2.5 s per query from Germany, occasionally >10 s) and limited
  roughly to one request per second per client; bursts beyond that return HTTP 429 or time out.
  We therefore keep ``min_interval=1.0`` and a generous timeout, and cap the total at seven
  requests per lead (1 website + up to 2 slugs x 3 profile hosts). Every request goes through the
  cache, so a second run of the same lead costs nothing.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import date

from context.cache import Cache
from context.http import FetchError, get_json
from context.lookup import SOURCE_WAYBACK, SOURCE_WAYBACK_CDX, WEB_NAMESAKE_YEARS, Lookup
from context.text import LEGAL_FORMS as _LEGAL_FORMS, TRANSLIT as _UMLAUTS, years_before
from models import Evidence, SourceSignal

logger = logging.getLogger(__name__)

CDX = "https://web.archive.org/cdx/search/cdx"
PROFILE_HOSTS = (
    ("Crunchbase", "crunchbase.com/organization/"),
    ("Dealroom", "app.dealroom.co/companies/"),
    ("Dealroom", "dealroom.co/companies/"),
)
MAX_REQUESTS = 7
MIN_INTERVAL = 1.0
TIMEOUT = 20



def slugs(name: str) -> list[str]:
    """Candidate profile slugs for a company name: lowercase, umlauts transliterated, legal forms
    removed, ``&`` -> ``and``, everything non-alphanumeric collapsed to ``-``; plus the same slug
    with the hyphens removed when that differs (``e-fusion`` -> also ``efusion``)."""
    text = name.strip().lower().translate(_UMLAUTS)
    text = _LEGAL_FORMS.sub(" ", text)
    text = text.replace("&", " and ").replace("+", " plus ")
    base = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not base:
        return []
    out = [base]
    compact = base.replace("-", "")
    if compact != base:
        out.append(compact)
    return out


def normalise_host(website: str | None) -> str | None:
    """``https://www.Firma.de:443/pfad`` -> ``firma.de``; None for empty or unusable input."""
    if not website or not website.strip():
        return None
    raw = website.strip()
    if "://" not in raw:
        raw = "http://" + raw
    host = (urllib.parse.urlsplit(raw).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else None


def cdx_url(target: str) -> str:
    """CDX query for the earliest 200 capture of exactly `target`."""
    return CDX + "?" + urllib.parse.urlencode({
        "url": target, "output": "json", "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200", "limit": "1",
    })


def _first_capture(rows) -> tuple[date, str] | None:
    """Parse a CDX JSON answer (header row + data rows) into (date, archived original URL)."""
    if not isinstance(rows, list):
        return None
    for row in rows[1:] if rows and rows[0] and rows[0][0] == "timestamp" else rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        ts, original = str(row[0]), str(row[1])
        if len(ts) < 8 or not ts[:8].isdigit():
            continue
        try:
            return date(int(ts[:4]), int(ts[4:6]), int(ts[6:8])), original if original else ts
        except ValueError:
            continue
    return None


def _archive_url(rows) -> str | None:
    if not isinstance(rows, list):
        return None
    data = rows[1:] if rows and rows[0] and rows[0][0] == "timestamp" else rows
    for row in data:
        if isinstance(row, list) and len(row) >= 2 and str(row[0])[:8].isdigit():
            return "https://web.archive.org/web/%s/%s" % (row[0], row[1])
    return None


EARLY_CAPTURE_FIELD = "web_capture_before_project"


def web_history_lookup(website: str | None, name: str, *, cache: Cache, fetch=None,
                       not_before: date | None = None, site_confirmed: str | None = None,
                       confirmed_years: int | None = None) -> Lookup:
    """Fill ``first_web_capture``, ``in_databases``, ``first_db_date`` and ``database_urls``.

    ``fetch(url) -> parsed JSON`` can be injected for tests; by default the CDX API is called via
    ``context.http.get_json`` with a one-second interval. Never raises: failures end up in
    ``errors`` as ``"wayback: ..."`` and the affected fields stay unset.

    ``not_before`` is the earliest dated sourcing signal (e.g. the EXIST project start). A profile or
    website whose first capture is more than ``WEB_NAMESAKE_YEARS`` (one year, see context/lookup.py) older than that belongs, most likely, to a
    namesake ("sensai" on Crunchbase in 2019 for a project started in 2024): it is not counted, the
    fields stay unset and an error entry names the URL.

    ``site_confirmed`` (e.g. "Website nennt FKZ 03EFHB0044"): the website itself names the project's
    funding reference or EXIST, so an early capture is the research group's or project's own older site, not a
    namesake. The website rule is then skipped (with ``confirmed_years`` only for captures at most that many
    years before ``not_before``: an EXIST mention does not explain a 2010 capture) and the reason is added to the
    finding. Such an early capture is kept only as Evidence ``field="web_capture_before_project"``: no
    ``first_web_capture``, no dated signal, so it never moves the lead's first signal before the project.
    Crunchbase/Dealroom profiles keep the namesake rule.
    """
    result = Lookup()
    cutoff = years_before(not_before, WEB_NAMESAKE_YEARS) if not_before else None
    if fetch is None:
        def fetch(url):
            return get_json(url, cache=cache, min_interval=MIN_INTERVAL, timeout=TIMEOUT)

    budget = [MAX_REQUESTS]

    def query(target: str):
        """Return (rows, error). rows is a list ([] = no capture) or None on error."""
        if budget[0] <= 0:
            return None, "wayback: Anfragebudget erschöpft"
        budget[0] -= 1
        url = cdx_url(target)
        try:
            rows = fetch(url)
        except FetchError as e:
            return None, "wayback: %s" % str(e).replace("web.archive.org: ", "")
        except Exception as e:  # noqa: BLE001 - never raise out of a lookup
            logger.warning("wayback query %s failed", url, exc_info=True)
            return None, "wayback: %s" % (str(e) or type(e).__name__)
        if rows is None or rows == "":
            rows = []
        if not isinstance(rows, list):
            return None, "wayback: unerwartete Antwort für %s" % target
        return rows, None

    # 1. first capture of the company website
    host = normalise_host(website)
    if host:
        rows, err = query(host)
        if err:
            result.errors.append(err)
        else:
            hit = _first_capture(rows)
            early = bool(hit and cutoff and hit[0] < cutoff)
            vouched = bool(site_confirmed) and (confirmed_years is None or not not_before
                                                 or hit[0] >= years_before(not_before, confirmed_years)) if early else False
            if early and not vouched:
                result.errors.append("wayback: Website %s älter als das Vorhaben, vermutlich Namensvetter"
                                     % (_archive_url(rows) or host))
            elif hit and early:
                # Vouched early capture: the domain is the project's own older site (research group, prototype
                # page). Kept as evidence only, not as first_web_capture: it must not date the lead before the project.
                result.evidence.append(Evidence(
                    field=EARLY_CAPTURE_FIELD, url=cdx_url(host), source=SOURCE_WAYBACK_CDX, source_date=hit[0],
                    finding="Erste Wayback-Aufnahme %s liegt vor dem Vorhaben; kein Namensvetter, weil %s. Nicht als "
                            "Signaldatum gewertet." % (hit[0].isoformat(), site_confirmed)))
            elif hit:
                first, original = hit
                result.add("first_web_capture", first, url=cdx_url(host),
                           finding="Erste Wayback-Aufnahme: %s" % first.isoformat(),
                           source=SOURCE_WAYBACK_CDX, source_date=first)
                result.signals.append(SourceSignal(
                    source=SOURCE_WAYBACK, type="wayback", url=_archive_url(rows), date=first,
                    evidence="Erste Archivaufnahme der Website",
                ))

    # 2. Crunchbase / Dealroom profiles
    candidates = slugs(name)
    found: list[tuple[date, str, str]] = []   # (date, archived URL, label)
    namesakes: list[str] = []                 # profiles archived long before the project existed
    errored = False
    for slug in candidates:
        for label, prefix in PROFILE_HOSTS:
            rows, err = query(prefix + slug)
            if err:
                errored = True
                result.errors.append(err)
                continue
            hit = _first_capture(rows)
            if hit and cutoff and hit[0] < cutoff:
                namesakes.append(_archive_url(rows) or prefix + slug)
            elif hit:
                found.append((hit[0], _archive_url(rows) or "", label))
    for url in namesakes:
        result.errors.append("wayback: Profil %s älter als das Vorhaben, vermutlich Namensvetter" % url)
    if candidates:
        if namesakes and not found:
            result.fields["in_databases"] = None
        elif found:
            found.sort()
            result.fields["in_databases"] = True
            result.fields["database_urls"] = [u for _, u, _ in found]
            result.add("first_db_date", found[0][0], url=found[0][1],
                       finding="Früheste archivierte %s-Profilaufnahme: %s" % (found[0][2], found[0][0].isoformat()),
                       source=SOURCE_WAYBACK_CDX, source_date=found[0][0])
            for d, archived, label in found:
                result.evidence.append(Evidence(
                    field="in_databases", url=archived, source=SOURCE_WAYBACK_CDX, source_date=d,
                    finding="%s-Profil im Webarchiv (Aufnahme %s)" % (label, d.isoformat()),
                ))
        elif errored:
            result.fields["in_databases"] = None
        else:
            result.fields["in_databases"] = False
            result.evidence.append(Evidence(
                field="in_databases", url=cdx_url(PROFILE_HOSTS[0][1] + candidates[0]), source=SOURCE_WAYBACK_CDX,
                finding="Keine archivierte Crunchbase-/Dealroom-Profilseite für %s" % ", ".join(candidates),
            ))
    return result
