"""Project name -> company website (plan v4, top risk 1: "Projektname → Firma ist mehrdeutig").

Leads from the Förderkatalog carry a project name ("SpinMagIC"), the executing institute, a place and a
topic, but no website. `match_lookup` finds the most likely company website without API keys:

1. **Candidates** from three sources, each remembered with its *Fundstelle* (where it was found):
   * a web search for ``"<name>" <institution>`` and, if that yields nothing verified, ``"<name>" Start-up``:
     the official Brave Search API when ``BRAVE_API_KEY`` is set (environment or a git-ignored ``.env``;
     header ``X-Subscription-Token``, never in URLs, cache keys, logs or evidence; Fundstelle is the neutral
     ``https://search.brave.com/search?q=...``), otherwise / as fallback the keyless Brave Search HTML and
     DuckDuckGo HTML pages; a captcha / anomaly page counts as "blocked", is not cached, and the next engine
     is tried (an engine is paused for `ENGINE_PAUSE` seconds after 401/403/429/captcha);
   * outbound links on up to `MAX_REFERRERS` search hits that are about the project but are not a
     company site (university news, idw, press): a link whose host contains the project slug;
   * domain guesses from the slug (``spinmagic.de/.com/.io/.ai/.eu/.tech``, hyphenated and ``-gmbh``
     variants); only names that resolve in DNS are fetched.
2. **Verification** of every candidate via `context.web.fetch` (same-site guard, parked-domain check,
   page cache). Scored evidence (see `score_page`): project name in the page title / first lines, slug in
   the host, corroboration by institute, EXIST, place, topic terms, legal form next to the name, the
   Impressum naming the company, and a referrer link. Maluses: agency/web-design pages, shops, parked
   pages (rejected), and *no corroboration at all* (a namesake: confidence capped at `NAMESAKE_CAP`).
   University / research-institute hosts are classified as ``project_page``, never as company website.
3. **Decision:** the best company candidate with ``confidence >= threshold`` (default `THRESHOLD`)
   becomes `matched_website` + `match_confidence`, each with an Evidence entry (URL = the website,
   finding = reasons + Fundstelle). Below the threshold nothing is set; the best attempt is reported
   in `errors`. A project page is reported as Evidence ``field="project_page"`` plus a signal.

Every request goes through the shared cache (`context.http.request` for search engines, `context.web.fetch`
for pages, ``dns:`` and ``website_match:`` keys here). Polite limits: `MIN_INTERVAL` seconds between two
search requests, `MAX_SEARCHES` queries, `MAX_VERIFY` verified pages per lead, timeouts from
`context.web` (4 s per page) and `TIMEOUT` for the search engines, back-off on 429/5xx in `context.http`.
Nothing is raised: failures are returned in `Lookup.errors`.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import socket
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit

from context import http as _http
from context.lookup import SOURCE_PROJECT_PAGE, SOURCE_WEBSITE_MATCH, Lookup
from context.text import LEGAL_FORMS, TRANSLIT
from context.web import FETCH_ERRORS, PARKED_ERROR, fetch as _web_fetch, site_key
from models import SourceSignal

logger = logging.getLogger(__name__)
SOURCE = SOURCE_WEBSITE_MATCH
THRESHOLD = 0.6          # minimum confidence for setting matched_website (CLI: --match-threshold)
NAMESAKE_CAP = 0.45      # a page with the name but without any corroboration is probably a namesake
TIMEOUT = 10             # seconds per search request (pages: context.web.TIMEOUT)
MIN_INTERVAL = 6.0       # seconds between two requests to the same search engine (Brave answers 429 below ~5 s)
MAX_SEARCHES = 2         # queries per lead (each may fall back to a second engine)
MAX_RESULTS = 10         # search hits read per query
MAX_REFERRERS = 3        # non-company hits whose outbound links are scanned
MAX_VERIFY = 8           # candidate homepages fetched per lead
MAX_SUBPAGES = 3         # about/team pages read when the homepage alone does not confirm the project
SUBPAGE_NAMES = {"about", "about-us", "ueber-uns", "über-uns", "uber-uns", "unternehmen", "company", "team", "story",
                 "geschichte", "unsere-geschichte", "mission", "news", "presse", "press"}
MAX_GUESSES = 6          # resolving domain guesses that are verified
CACHE_VERSION = "website_match:v9:"
TOP_LINES = 8            # "prominent": title, navigation and first heading of the parsed page
GUESS_TLDS = (".de", ".com", ".io", ".ai", ".eu", ".tech")

SEARCH_ENGINES = {
    # Official Brave Search API (used only when BRAVE_API_KEY is set). The key travels in a header only: it is
    # never part of the URL, the cache key (context.http.cache_key hashes method, URL and body), logs or evidence.
    "brave_api": "https://api.search.brave.com/res/v1/web/search?q=%s&country=de&search_lang=de&count=10",
    "brave": "https://search.brave.com/search?q=%s&source=web",
    "duckduckgo": "https://html.duckduckgo.com/html/?q=%s&kl=de-de",
}
# Neutral, key-free search URL that is shown as Fundstelle for API hits.
PUBLIC_SEARCH_URL = {"brave_api": "https://search.brave.com/search?q=%s"}
API_KEY_ENVS = ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY")   # first wins; the second is the name used by Brave's own tools
API_STATS = {"requests": 0, "cached": 0}                 # API calls of this process (network vs. cache), for budget reports
API_MIN_INTERVAL = 1.1   # free plan: 1 request/s, about 2,000 per month
API_RETRIES = 2          # context.http backs off 2 s, 4 s on 429/5xx
ENGINE_PAUSE = 90       # seconds an engine is skipped after a 429 / captcha (circuit breaker, per process)
_paused_until: dict[str, float] = {}
BLOCKED = re.compile(r"anomaly-modal|captcha|are you a robot|unusual traffic|bots use|ich bin kein roboter", re.I)

# Hosts that never are the company's own website: profiles, directories, registers, stores, search engines.
PLATFORM_HOSTS = re.compile(
    r"(?:^|\.)(?:linkedin|xing|facebook|instagram|twitter|x|youtube|youtu|tiktok|wikipedia|wikimedia|github|gitlab|"
    r"crunchbase|dealroom|northdata|north-data|firmenwissen|startbase|unternehmensregister|handelsregister|bundesanzeiger|"
    r"foerderportal|exist|bmwk|bmftr|bmbf|presseportal|medium|researchgate|arxiv|google|apple|amazon|ebay|kununu|"
    r"glassdoor|indeed|stepstone|f6s|wellfound|angel|producthunt|pitchbook|cbinsights|tracxn|zoominfo|dnb|"
    r"duckduckgo|bing|brave|yahoo|reddit|pinterest|spotify|podcasts|soundcloud|vimeo|slideshare|issuu|"
    r"springer|sciencedirect|wiley|mdpi|nature|ieee|acm|semanticscholar|openalex|orcid|patents|espacenet|"
    r"idw-online|eu-startups|startup-insider|gruenderszene|businessinsider|handelsblatt|heise|golem|t3n|"
    r"faz|sueddeutsche|spiegel|zeit|welt|tagesspiegel|mdr|ndr|wdr|br|swr|hr|rbb|deutschlandfunk)\.[a-z.]+$", re.I)
# Social profiles: no outbound links worth scanning (and usually closed to automated fetches).
SOCIAL_HOSTS = re.compile(r"(?:^|\.)(?:linkedin|xing|facebook|instagram|twitter|x|youtube|tiktok)\.[a-z.]+$", re.I)
# University and research-institute hosts: a page there is a project page, not a company website.
ACADEMIC_HOSTS = re.compile(
    r"(?:^|\.)(?:uni-[a-z-]+|tu-[a-z-]+|th-[a-z-]+|fh-[a-z-]+|hs-[a-z-]+|h-[a-z]+|hochschule-[a-z-]+|[a-z-]*hochschule[a-z-]*|"
    r"tum|lmu|kit|rwth-aachen|fau|mhh|charite|bih-charite|uniklinik-[a-z-]+|ukaachen|ukbonn|ukw|ukr|mh-hannover|"
    r"fraunhofer|dlr|mpg|helmholtz|helmholtz-[a-z-]+|hzdr|hereon|desy|fz-juelich|ufz|dkfz|mdc-berlin|gfz-potsdam|awi|"
    r"leibniz-[a-z-]+|ipfdd|izw-berlin|zalf|ptb|bam|empa|ethz|epfl|tuwien|tugraz|"
    r"unibw|hu-berlin|fu-berlin|tu-berlin|tu-dresden|tu-darmstadt|tu-braunschweig|uni|ovgu|jku|"
    r"[a-z-]+-university|university-[a-z-]+|[a-z0-9-]*-research|research-[a-z0-9-]+)\.(?:de|eu|at|ch|org|com|edu)$|\.edu$|\.ac\.[a-z]{2}$", re.I)
# A paper / artefact page ("Cite as", BibTeX) is research output, not a company site (tentris.dice-research.org).
PAPER = re.compile(r"@InProceedings|@article\{|\bCite as\b|\bDownload Paper\b|\bBibTeX\b|reproduce the results of the paper", re.I)
AGENCY = re.compile(r"\b(?:Webdesign|Web-Design|Werbeagentur|Digitalagentur|Internetagentur|Kreativagentur|Marketingagentur|"
                    r"SEO[- ]Agentur|Agentur für|Full[- ]Service[- ]Agentur|digital agency|creative agency|marketing agency|"
                    r"web design agency)\b", re.I)
SHOP = re.compile(r"\b(?:In den Warenkorb|Warenkorb|Add to cart|Zur Kasse|Checkout|Versandkostenfrei|Free shipping)\b", re.I)
PARKING = re.compile(r"\b(?:domain (?:may be|is|ist) (?:for sale|available|zu verkaufen)|diese domain (?:steht|kann|ist)|"
                     r"domain kaufen|buy this domain|coming soon|under construction|website im aufbau|in k[üu]rze verf[üu]gbar|"
                     r"default web page|it works!|welcome to nginx|plesk|parkingcrew|bodis|this site can.t be reached|"
                     r"(?:domain )?is parked|domain parking|geparkte domain)\b", re.I)
EXIST = re.compile(r"\bEXIST\b(?:[- ](?:Forschungstransfer|Gründungsstipendium|Gruendungsstipendium|Transfer of Research|"
                   r"Business Start-up Grant|programme|program|Programm|gefördert|funded|funding|Förderung))?", re.I)
SPINOFF = re.compile(r"\b(?:Ausgründung|Spin-?off|Spin-?out|Start-?up|Gründerteam|Gründungsteam|Gründer(?:innen)?|founders?|"
                     r"founding team|gegründet|founded)\b", re.I)
# Words of institute names that say nothing about the project.
GENERIC_TERMS = set("""universitaet university hochschule technische technical institut institute fakultaet faculty lehrstuhl
fachgebiet fachbereich professur department abteilung bereich zentrum center centre forschung research arbeitsgruppe gruppe
deutsches deutsche zentrum fuer und der die das des von the and for of e.v. ev gmbh angewandte wissenschaften sciences
applied medizinische school mathematisch naturwissenschaftliche ingenieurwissenschaften berliner""".split())
HOST_SUFFIXES = ("gmbh", "ug", "tech", "technologies", "technology", "ai", "io", "app", "hq", "labs", "lab", "group",
                 "systems", "solutions", "robotics", "bio", "med", "energy", "online", "de", "com")
HOST_PREFIXES = ("get", "try", "use", "the", "my", "go", "hello", "team", "we")
UNIVERSITY_EN = re.compile(r"(?:Technische )?Universit[äa]t ([A-ZÄÖÜ][\wäöüß-]+)")


@dataclass
class Candidate:
    """A possible website plus where it came from."""
    url: str
    origin: str                 # "search:brave", "search:duckduckgo", "referrer", "domain"
    found_at: str               # Fundstelle: search URL, referrer page or "DNS: <host>"
    rank: int = 99
    title: str = ""
    snippet: str = ""


@dataclass
class WebsiteMatch:
    """Outcome of verifying one candidate."""
    url: str
    kind: str                   # "company", "project_page", "rejected"
    confidence: float
    reasons: list[str] = field(default_factory=list)
    found_at: str = ""
    origin: str = ""
    title: str = ""


@dataclass
class LeadContext:
    """What the matcher knows about a lead (all optional except the name)."""
    name: str
    institution: str | None = None      # Förderempfänger / Ausführende Stelle, first part
    executing: str | None = None        # full Ausführende Stelle (topic terms)
    location: str | None = None
    topic: str | None = None            # description / Thema
    reference: str | None = None        # FKZ
    founders: list[str] = field(default_factory=list)


# --- text helpers ---------------------------------------------------------------------------------

def fold(text: str) -> str:
    """Lower case, umlauts transliterated, accents removed."""
    text = (text or "").lower().translate(TRANSLIT)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def clean_name(name: str) -> str:
    """Project name without programme prefixes ("EXIST_P2P" -> "P2P") and legal forms."""
    name = re.sub(r"^(?:EXIST[-_ ]?(?:FT|Forschungstransfer|Gründungsstipendium)?[-_: ]+)", "", (name or "").strip(), flags=re.I)
    name = LEGAL_FORMS.sub(" ", name)
    return " ".join(name.split()).strip(" -_–")


CAMEL = re.compile(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ][a-zäöüß])")


def spaced_name(name: str) -> str:
    """CamelCase split into words: 'VersatileRobotics' -> 'Versatile Robotics', 'PoLightFilters' -> 'Po Light Filters'.

    Split only when every resulting word is an ordinary capitalised word of 3+ letters, so 'SpinMagIC', 'SideroGaIn',
    'PoLightFilters', 'iNSyT' and 'DyNAtrix' stay whole (their teams write them that way).
    """
    name = clean_name(name)
    out = []
    for token in name.split():
        words = CAMEL.sub(" ", token).split()
        ok = len(words) > 1 and all(re.fullmatch(r"[A-ZÄÖÜ]?[a-zäöüß]{2,}", w) for w in words)
        out.extend(words if ok else [token])
    return " ".join(out)


def name_parts(name: str) -> list[str]:
    """Folded word parts of the project name, CamelCase split (joined they give the slug)."""
    return [p for p in re.split(r"[^a-z0-9]+", fold(spaced_name(name))) if p]


def slug(name: str) -> str:
    """'Pulse-of-Production' -> 'pulseofproduction'."""
    return "".join(name_parts(name))


def name_regex(name: str) -> re.Pattern | None:
    """Whole-word pattern of the folded name; parts may be joined by nothing, space, '-', '_' or '.'."""
    parts = name_parts(name)
    if not parts:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-_.]?".join(re.escape(p) for p in parts) + r"(?![a-z0-9])")


GENERIC_STEMS = {"techno", "produk", "produc", "inform", "system", "entwic", "intell", "manage", "wissen", "scienc",
                 "engine", "ingeni", "innova", "loesun", "soluti", "anwend", "applic", "digita", "intern", "nation",
                 "mathem", "natur", "mechan", "fakult", "physik", "physic", "chemie", "chemis", "medizi", "medici", "biolog", "elektr",
                 "electr", "maschi", "bayern", "sachse", "hessen", "berlin", "bremen", "hambur", "saarla", "thueri", "branden",
                 "nieder", "nordrh", "westfa", "rheinl", "schles", "holste", "mecklen", "vorpom", "anhalt", "wuertt", "baden", "machin", "studie", "studen", "gesell", "verfah", "method", "modern", "zukunf"}


def topic_terms(*texts: str | None, limit: int = 8, name: str = "", exclude: str = "") -> list[str]:
    """Specific words of the topic / executing unit, folded and cut to a 6-letter stem ('Robotik' ~ 'robotics').

    Stems of the project name itself and broad discipline words (GENERIC_STEMS) are left out: they would make
    every page with the name, or every engineering page, look on-topic. Words of `exclude` (institution name and
    place, which have their own criteria) are skipped too.
    """
    own = {p[:6] for p in name_parts(name)} | ({slug(name)[:6]} if name else set())
    skip = {fold(w)[:6] for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", exclude or "")}
    out = []
    for text in texts:
        for word in re.findall(r"[A-Za-zÄÖÜäöüß]{6,}", text or ""):
            stem = fold(word)
            if stem in GENERIC_TERMS or any(stem.startswith(g) for g in ("universit", "hochschul", "institut", "fakult", "lehrstuhl",
                                                                         "forschung", "projekt", "programm", "exist")):
                continue
            stem = stem[:6]
            if stem in GENERIC_STEMS or stem in skip or stem in own or any(p.startswith(stem) or stem.startswith(p) for p in own if len(p) >= 4):
                continue
            if stem not in out:
                out.append(stem)
    return out[:limit]


def institution_terms(institution: str | None) -> list[str]:
    """Folded names a page may use for the institute: full first part, acronym in brackets, 'University of X'."""
    if not institution:
        return []
    first = re.split(r"\s+-\s+|,", institution)[0].strip()
    terms = [first]
    terms += re.findall(r"\(([A-ZÄÖÜ][A-Za-zÄÖÜ]{1,7})\)", institution)
    if (m := UNIVERSITY_EN.search(first)):
        terms += ["University of %s" % m[1], "%s University" % m[1], "Universität %s" % m[1]]
    for org in ("Fraunhofer", "Helmholtz", "Max-Planck", "Leibniz", "DLR", "Charité", "KIT", "RWTH", "TUM", "LMU"):
        if org.lower() in institution.lower():
            terms.append(org)
    return [fold(t) for t in dict.fromkeys(terms) if len(t) >= 3]


def contains(folded_text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", folded_text) is not None


def host_match(url: str, name: str) -> str | None:
    """'strong' if the first host label is the slug (optionally with a common prefix/suffix), 'weak' if it
    contains it (slug of 5+ letters), else None."""
    s = slug(name)
    if not s:
        return None
    label = site_key(url).split(".")[0].replace("-", "")
    if label == s or any(label == s + x for x in HOST_SUFFIXES) or any(label == x + s for x in HOST_PREFIXES):
        return "strong"
    if len(s) >= 5 and s in label:
        return "weak"
    return None


def is_academic(url: str) -> bool:
    return bool(ACADEMIC_HOSTS.search(site_key(url)))


def is_platform(url: str) -> bool:
    return bool(PLATFORM_HOSTS.search(site_key(url)))


def homepage(url: str) -> str:
    parts = urlsplit(url)
    return "%s://%s/" % (parts.scheme or "https", parts.netloc)


# --- search ---------------------------------------------------------------------------------------

def _strip_tags(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def parse_brave(page: str) -> list[tuple[str, str, str]]:
    """Brave Search HTML -> [(url, title, snippet)].

    Brave sometimes hides the target behind a "/go/v1/..." redirect; then only the host shown in the result's
    <cite> is known and the hit's URL is that host's homepage (good enough for a company candidate, not for
    scanning a referrer article).
    """
    out = []
    for block in re.split(r'data-type="web"', page)[1:]:
        link = re.search(r'<a href="(https?://[^"]+)"[^>]*class="[^"]*\bl1\b', block)
        if not link and re.search(r'<a href="/go/', block):
            link = re.search(r'<cite[^>]*>\s*(?:<!--[^>]*-->)*\s*(https?://[A-Za-z0-9.-]+)', block)
        if not link:
            continue
        title = re.search(r'search-snippet-title[^>]*title="([^"]*)"', block)
        snippet = re.search(r'class="(?:generic-snippet|snippet-description)[^"]*"[^>]*>(.*?)</div>\s*</div>', block, re.S)
        out.append((html.unescape(link[1]), html.unescape(title[1]) if title else "", _strip_tags(snippet[1]) if snippet else ""))
    return out


def parse_duckduckgo(page: str) -> list[tuple[str, str, str]]:
    """DuckDuckGo HTML -> [(url, title, snippet)]; resolves the /l/?uddg= redirect."""
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', page, re.S):
        href = html.unescape(m[1])
        if "uddg=" in href:
            href = unquote(parse_qs(urlsplit(href).query).get("uddg", [""])[0])
        if href.startswith("//"):
            href = "https:" + href
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m[3], re.S)
        if href.startswith("http"):
            out.append((href, _strip_tags(m[2]), _strip_tags(snippet[1]) if snippet else ""))
    return out


def parse_brave_api(text: str) -> list[tuple[str, str, str]]:
    """Brave Search API JSON -> [(url, title, snippet)] from `web.results[]`; anything else -> []."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    results = ((data.get("web") or {}).get("results") or []) if isinstance(data, dict) else []
    return [(r["url"], _strip_tags(r.get("title") or ""), _strip_tags(r.get("description") or ""))
            for r in results if isinstance(r, dict) and str(r.get("url", "")).startswith("http")]


PARSERS = {"brave_api": parse_brave_api, "brave": parse_brave, "duckduckgo": parse_duckduckgo}


def api_key(env=None, dotenv: str | os.PathLike | None = ".env") -> str | None:
    """The Brave API key: environment first (BRAVE_API_KEY, then BRAVE_SEARCH_API_KEY), else a local, git-ignored
    `.env` (KEY=VALUE lines, same order)."""
    env = os.environ if env is None else env
    for name in API_KEY_ENVS:
        if env.get(name, "").strip():
            return env[name].strip()
    found = {}
    try:
        for line in Path(dotenv).read_text(encoding="utf-8").splitlines() if dotenv else ():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            value = value.strip().strip("'\"")
            if sep and name.strip() in API_KEY_ENVS and value:
                found.setdefault(name.strip(), value)
    except OSError:
        pass
    return next((found[n] for n in API_KEY_ENVS if n in found), None)


def default_engines(key: str | None) -> tuple[str, ...]:
    """API first when a key is set; otherwise the keyless HTML engines."""
    return ("brave_api", "brave", "duckduckgo") if key else ("brave", "duckduckgo")


def web_search(query: str, *, cache=None, engines=None, request=None, key: str | None = None) -> tuple[list[Candidate], list[str]]:
    """Run `query` on the first engine that answers; -> (candidates, errors). Blocked pages are not cached.

    `engines` defaults to `default_engines(key)`; `key` defaults to `api_key()`. "brave_api" is skipped without a key.
    """
    request = request or _http.request
    if key is None and (engines is None or "brave_api" in engines):
        key = api_key()
    engines = default_engines(key) if engines is None else engines
    errors = []
    for engine in engines:
        if engine == "brave_api" and not key:
            continue
        url = SEARCH_ENGINES[engine] % quote_plus(query)
        if _paused_until.get(engine, 0) > time.time() and (cache is None or cache.get(_http.cache_key(url)) is None):
            errors.append("website_match: Suche %s pausiert (zuvor gesperrt)" % engine)
            continue
        if engine == "brave_api":
            API_STATS["cached" if cache is not None and cache.get(_http.cache_key(url)) is not None else "requests"] += 1
            headers, interval, retries = {"Accept": "application/json", "X-Subscription-Token": key}, API_MIN_INTERVAL, API_RETRIES
        else:
            headers = {"Accept": "text/html", "Accept-Language": "de-DE,de;q=0.9,en;q=0.5"}
            interval, retries = MIN_INTERVAL, 1
        try:
            text = request(url, cache=cache, timeout=TIMEOUT, min_interval=interval, retries=retries, headers=headers)
        except _http.FetchError as exc:
            errors.append("website_match: Suche %s: %s" % (engine, exc))
            if re.search(r"HTTP (?:401|403|422|429|503)", str(exc)):
                _paused_until[engine] = time.time() + ENGINE_PAUSE
            continue
        hits = PARSERS[engine](text)
        if engine == "brave_api" and not hits and not _api_answer(text):
            if cache is not None:
                cache.set(_http.cache_key(url), None)      # an error body is not a search result
            errors.append("website_match: Suche brave_api: unerwartete Antwort")
            continue
        if not hits and BLOCKED.search(text):
            if cache is not None:
                cache.set(_http.cache_key(url), None)      # never replay a captcha page
            _paused_until[engine] = time.time() + ENGINE_PAUSE
            errors.append("website_match: Suche %s blockiert" % engine)
            continue
        found_at = PUBLIC_SEARCH_URL.get(engine, SEARCH_ENGINES[engine]) % quote_plus(query)
        return [Candidate(url=u, origin="search:" + engine, found_at=found_at, rank=i, title=t, snippet=s)
                for i, (u, t, s) in enumerate(hits[:MAX_RESULTS])], errors
    return [], errors


def _api_answer(text: str) -> bool:
    """True for a well-formed API answer (also an empty result list)."""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("type") == "search"


# --- candidates -----------------------------------------------------------------------------------

def domain_guesses(name: str) -> list[str]:
    """Hostnames to try for a project name (slug of at least 4 characters)."""
    parts = name_parts(name)
    joined = "".join(parts)
    if len(joined) < 4:
        return []
    stems = [joined] + (["-".join(parts)] if len(parts) > 1 else [])
    hosts = [s + tld for s in stems for tld in GUESS_TLDS]
    hosts += [joined + "-gmbh.de", joined + "gmbh.de"]
    return list(dict.fromkeys(hosts))


def resolves(host: str, cache=None) -> bool:
    """DNS check (cached under "dns:"), so dead guesses cost no HTTP request."""
    key = "dns:" + host
    hit = cache.get(key) if cache is not None else None
    if isinstance(hit, dict):
        return bool(hit.get("ok"))
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ok = True
    except (OSError, UnicodeError):
        ok = False
    if cache is not None:
        cache.set(key, {"ok": ok})
    return ok


def referrer_links(hit: Candidate, page, name: str) -> list[Candidate]:
    """External links on a page about the project whose host carries the project slug."""
    out = []
    own = site_key(hit.url)
    for href in page.links:
        try:
            link = urljoin(hit.url, href.strip())
        except ValueError:
            continue
        if not link.startswith("http") or site_key(link) == own or is_platform(link):
            continue
        if host_match(link, name):
            out.append(Candidate(url=homepage(link), origin="referrer", found_at=hit.url, title=hit.title))
    return out


# --- verification ---------------------------------------------------------------------------------

def score_page(candidate: Candidate, lines: list[str], ctx: LeadContext, imprint_text: str = "") -> WebsiteMatch:
    """Score one fetched homepage (pure function; the tests drive it with fixture lines)."""
    match = WebsiteMatch(url=candidate.url, kind="company", confidence=0.0, found_at=candidate.found_at,
                         origin=candidate.origin, title=(lines[0] if lines else "")[:160])
    reasons = match.reasons
    text = "\n".join(lines)
    if is_academic(candidate.url) or PAPER.search(text):
        match.kind = "project_page"
    folded = fold(text)
    top = fold("\n".join(lines[:TOP_LINES]))
    name_re = name_regex(ctx.name)
    if name_re is None:
        match.kind, match.reasons = "rejected", ["kein verwertbarer Projektname"]
        return match
    if not lines:
        match.kind = "rejected"
        reasons.append("Seite ohne Text")
        return match
    if PARKING.search(text) and len(lines) < 40:
        match.kind = "rejected"
        reasons.append("Platzhalter-/Parking-Seite")
        return match

    score = 0.0
    hm = host_match(candidate.url, ctx.name)
    imprint_names = bool(imprint_text and name_re.search(fold(imprint_text)))
    if name_re.search(fold(lines[0])):
        score += 0.3
        reasons.append("Projektname im Seitentitel")
    elif name_re.search(top):
        score += 0.25
        reasons.append("Projektname prominent (Kopf/Überschrift)")
    elif name_re.search(folded):
        score += 0.1
        reasons.append("Projektname nur im Fließtext")
    elif not imprint_names:
        match.kind = "rejected"
        reasons.append("Projektname kommt auf der Seite nicht vor")
        return match
    if hm == "strong":
        score += 0.25
        reasons.append("Domain = Projektname")
    elif hm == "weak":
        score += 0.1
        reasons.append("Domain enthält Projektname")

    corroboration = []
    if (inst := next((t for t in institution_terms(ctx.institution) if contains(folded, t)), None)):
        score += 0.15
        corroboration.append("Institut genannt (%s)" % inst)
    if EXIST.search(text):
        score += 0.15
        corroboration.append("EXIST erwähnt")
    terms = [t for t in topic_terms(ctx.executing, ctx.topic, name=ctx.name,
                                                    exclude="%s %s" % (re.split(r"\s+-\s+|,", ctx.institution or "")[0], ctx.location or "")) if re.search(r"(?<![a-z])" + re.escape(t), folded)]
    # Topic stems are weak ("montag" also matches Monday): two add points, only three confirm the project.
    if len(terms) >= 3:
        score += 0.1
        corroboration.append("Themenbegriffe (%s)" % ", ".join(terms[:4]))
    elif len(terms) == 2:
        score += 0.05
        reasons.append("zwei Themenbegriffe (%s)" % ", ".join(terms))
    surnames = [fold(f.split()[-1]) for f in ctx.founders if f.split()]
    if surnames and any(contains(folded, s) for s in surnames):
        score += 0.15
        corroboration.append("Gründername genannt")
    place = fold(re.split(r"[\s,(]", ctx.location.strip())[0]) if ctx.location and ctx.location.strip() else ""
    if place and len(place) >= 3 and contains(fold(text + "\n" + imprint_text), place):
        score += 0.1
        corroboration.append("Ort genannt (%s)" % ctx.location)
    if candidate.origin == "referrer":
        score += 0.15
        corroboration.append("verlinkt von Projektquelle %s" % site_key(candidate.found_at))
    reasons.extend(corroboration)
    # Entity evidence: the site belongs to a firm of that name. It does not say that the firm is *this* project
    # (simba.de is an accounting-software firm), so it never lifts the namesake cap on its own.
    if imprint_names:
        score += 0.15
        reasons.append("Impressum nennt den Namen")
    legal = re.search(name_re.pattern + r"[\s,]*(?:gmbh|ug\b|ag\b|ug \(haftungsbeschrankt\)|i\.\s?g\.|in grundung)",
                      folded + "\n" + fold(imprint_text))
    if legal:
        score += 0.1
        reasons.append("Rechtsform beim Namen")
    if SPINOFF.search(text):
        score += 0.05
        reasons.append("Start-up-/Gründungsbezug")
    if candidate.origin.startswith("search:") and candidate.rank == 0:
        score += 0.05
        reasons.append("erster Suchtreffer")

    if AGENCY.search(text):
        score -= 0.3
        reasons.append("Malus: Agentur/Webdesign")
    if SHOP.search(text) and not corroboration:
        score -= 0.2
        reasons.append("Malus: Online-Shop")
    if not corroboration:
        score = min(score, NAMESAKE_CAP)
        reasons.append("keine Bestätigung durch Institut/EXIST/Thema/Ort: möglicher Namensvetter")
    # A company's own site carries its name in the title/head or in the domain. A page that only mentions the
    # project in running text (campus-start-ups.nrw, a network or press portal) is about it, not its website.
    elif match.kind == "company" and not hm and not (name_re.search(fold(lines[0])) or name_re.search(top)):
        score = min(score, NAMESAKE_CAP)
        reasons.append("Name nur erwähnt (Verzeichnis/Portal/Presse), nicht die Website des Projekts")
    match.confidence = round(max(0.0, min(score, 1.0)), 2)
    return match


def _verify(candidate: Candidate, ctx: LeadContext, fetch, imprint) -> WebsiteMatch:
    try:
        try:
            final_url, page = fetch(candidate.url, site_key(candidate.url))
        except FETCH_ERRORS as exc:
            # Small sites often have a broken certificate (shared hosting): one plain-HTTP attempt.
            if not (candidate.url.startswith("https://") and re.search(r"SSL|CERTIFICATE|certificate", str(exc))):
                raise
            candidate = Candidate(**{**asdict(candidate), "url": "http://" + candidate.url[len("https://"):]})
            final_url, page = fetch(candidate.url, site_key(candidate.url))
    except FETCH_ERRORS as exc:
        reason = "Domain geparkt/zu verkaufen" if str(exc) == PARKED_ERROR else "nicht abrufbar (%s)" % (str(exc) or type(exc).__name__)
        return WebsiteMatch(url=candidate.url, kind="rejected", confidence=0.0, reasons=[reason],
                            found_at=candidate.found_at, origin=candidate.origin)
    lines = list(page.lines)
    candidate = Candidate(**{**asdict(candidate), "url": homepage(final_url) if not is_academic(final_url) else final_url})
    result = score_page(candidate, lines, ctx)
    if result.kind != "company" or result.confidence < NAMESAKE_CAP - 0.2:
        return result
    # Start-ups name their university and EXIST on "Über uns"/"Team", rarely on the homepage (autonomiq.de):
    # an unconfirmed but prominent hit gets up to MAX_SUBPAGES same-site about/team pages appended.
    if not _confirmed(result):
        for url in _subpages(final_url, page.links):
            try:
                _, sub = fetch(url, site_key(url))
            except FETCH_ERRORS:
                continue
            lines += sub.lines
        result = score_page(candidate, lines, ctx)
    # The Impressum decides close cases: it names the legal entity behind the site.
    if imprint is not None and result.confidence >= THRESHOLD - 0.3:
        text = imprint(candidate.url)
        if text:
            result = score_page(candidate, lines, ctx, imprint_text=text)
    return result


CONFIRMING = ("Institut genannt", "EXIST erwähnt", "Themenbegriffe", "Gründername", "verlinkt von", "Ort genannt")


def _confirmed(result: WebsiteMatch) -> bool:
    return any(r.startswith(CONFIRMING) for r in result.reasons)


def _subpages(base: str, links: list[str]) -> list[str]:
    """Same-site about/team/company pages of a homepage (names as in context.web.PAGE_NAMES), at most MAX_SUBPAGES."""
    site, found = site_key(base), []
    for href in links:
        try:
            link = urljoin(base, href.strip())
            parsed = urlsplit(link)
        except ValueError:
            continue
        section = unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1]).lower()
        if site_key(link) == site and section in SUBPAGE_NAMES:
            clean = parsed._replace(fragment="", query="").geturl()
            if clean not in found and clean.rstrip("/") != base.rstrip("/"):
                found.append(clean)
    return found[:MAX_SUBPAGES]


# --- entry point ----------------------------------------------------------------------------------

def match_lookup(name: str, *, institution: str | None = None, executing: str | None = None, location: str | None = None,
                 topic: str | None = None, reference: str | None = None, founders=(), cache=None, fetch=None,
                 search=None, resolve=None, imprint=None, threshold: float = THRESHOLD,
                 guesses: bool = True) -> tuple[WebsiteMatch | None, Lookup]:
    """Find and verify the company website of a project; see module docstring.

    Injection points (tests): `fetch(url, site) -> (final_url, CompanyPage)`, `search(query) -> (candidates, errors)`,
    `resolve(host) -> bool`, `imprint(url) -> text | None`. Returns the best match (any kind, for reports) and a
    Lookup that only sets `matched_website` / `match_confidence` when a company site reaches `threshold`.
    """
    lookup = Lookup()
    ctx = LeadContext(name=clean_name(name), institution=institution, executing=executing, location=location,
                      topic=topic, reference=reference, founders=list(founders or ()))
    if not slug(ctx.name):
        lookup.errors.append("website_match: kein verwertbarer Projektname")
        return None, lookup
    key = CACHE_VERSION + hashlib.sha1(repr((ctx.name, institution, executing, location, topic, tuple(ctx.founders),
                                             guesses)).encode("utf-8")).hexdigest()
    live = search is None and fetch is None and resolve is None
    hit = cache.get(key) if (cache is not None and live) else None
    if isinstance(hit, dict) and "tried" in hit:
        tried = [WebsiteMatch(**m) for m in hit["tried"]]
        errors = list(hit.get("errors", []))
    else:
        tried, errors, complete = _collect(ctx, cache=cache, fetch=fetch, search=search, resolve=resolve,
                                           imprint=imprint, threshold=threshold, guesses=guesses)
        if cache is not None and live and complete:
            cache.set(key, {"tried": [asdict(m) for m in tried], "errors": errors})
    lookup.errors.extend(errors)
    best = _decide(tried, threshold, lookup, ctx)
    return best, lookup


def _collect(ctx: LeadContext, *, cache, fetch, search, resolve, imprint, threshold, guesses):
    """Gather and verify candidates; -> (verified matches, errors, complete)."""
    errors: list[str] = []
    complete = True
    if fetch is None:
        def fetch(url, site):
            return _web_fetch(url, site, cache=cache)
    if search is None:
        def search(query):
            return web_search(query, cache=cache)
    if resolve is None:
        def resolve(host):
            return resolves(host, cache)
    if imprint is None:
        def imprint(url):
            from context.imprint import imprint_lookup
            found = imprint_lookup(url, cache=cache, fetch=fetch)
            return next((s.evidence for s in found.signals if s.type == "impressum"), None)

    tried: list[WebsiteMatch] = []
    seen: set[str] = set()
    budget = [MAX_VERIFY]

    def verify(candidate: Candidate) -> WebsiteMatch | None:
        site = site_key(candidate.url)
        if not site or site in seen or budget[0] <= 0:
            return None
        seen.add(site)
        budget[0] -= 1
        result = _verify(candidate, ctx, fetch, imprint)
        tried.append(result)
        return result

    def good():
        return any(m.kind == "company" and m.confidence >= threshold for m in tried)

    first = re.split(r"\s+-\s+|,", ctx.institution or "")[0].strip()
    # A CamelCase project name is usually written with spaces by the team ("Versatile Robotics"): the first query
    # uses that spelling, the second the catalogue spelling.
    spaced = spaced_name(ctx.name)
    queries = ['"%s" %s' % (spaced, first) if first else '"%s"' % spaced, '"%s" Start-up' % ctx.name][:MAX_SEARCHES]
    referrers = 0
    for query in queries:
        try:
            hits, errs = search(query)
        except Exception as exc:  # noqa: BLE001 - injected or network search must not kill the lead
            hits, errs = [], ["website_match: Suche %s" % type(exc).__name__]
        errors.extend(errs)
        if errs and not hits:
            complete = False
        name_re = name_regex(ctx.name)
        for hit in hits:
            about = name_re is not None and bool(name_re.search(fold(hit.title + " " + hit.snippet + " " + hit.url)))
            if is_platform(hit.url) or is_academic(hit.url):
                if (about and referrers < MAX_REFERRERS and urlsplit(hit.url).path.strip("/")
                        and not SOCIAL_HOSTS.search(site_key(hit.url))):
                    referrers += 1
                    try:
                        _, page = fetch(hit.url, site_key(hit.url))
                    except FETCH_ERRORS:
                        page = None
                    if page is not None:
                        for link in referrer_links(hit, page, ctx.name):
                            verify(link)
                        if is_academic(hit.url):
                            seen.discard(site_key(hit.url))
                            tried.append(score_page(hit, list(page.lines), ctx))
                continue
            if about or host_match(hit.url, ctx.name):
                verify(Candidate(**{**asdict(hit), "url": homepage(hit.url)}))
        if good():
            break
    if guesses and not good():
        resolving = [h for h in domain_guesses(ctx.name) if resolve(h)][:MAX_GUESSES]
        for host in resolving:
            verify(Candidate(url="https://%s/" % host, origin="domain", found_at="DNS: %s" % host))
            if good():
                break
    return tried, errors, complete


def _decide(tried: list[WebsiteMatch], threshold: float, lookup: Lookup, ctx: LeadContext) -> WebsiteMatch | None:
    companies = sorted((m for m in tried if m.kind == "company"), key=lambda m: (-m.confidence, m.url))
    pages = sorted((m for m in tried if m.kind == "project_page" and m.confidence > 0), key=lambda m: (-m.confidence, m.url))
    best = companies[0] if companies else None
    if best and best.confidence >= threshold:
        finding = "%s: %s. Fundstelle: %s" % (ctx.name, "; ".join(best.reasons), best.found_at)
        lookup.add("matched_website", best.url, url=best.url, finding=finding, source=SOURCE)
        lookup.add("match_confidence", best.confidence, url=best.url, finding=finding, source=SOURCE)
        if len(companies) > 1 and companies[1].confidence >= threshold:
            lookup.errors.append("website_match: weitere Kandidatin %s (%.2f), Zuordnung prüfen"
                                 % (companies[1].url, companies[1].confidence))
    elif best:
        lookup.errors.append("website_match: keine Website über Schwelle %.2f (beste: %s, %.2f: %s)"
                             % (threshold, best.url, best.confidence, "; ".join(best.reasons)))
    else:
        lookup.errors.append("website_match: keine Kandidatin gefunden")
    if pages:
        page = pages[0]
        finding = "%s: Projektseite einer Hochschule/Forschungseinrichtung (%s)" % (ctx.name, "; ".join(page.reasons))
        lookup.evidence.append(_evidence("project_page", page.url, finding))
        lookup.signals.append(SourceSignal(source=SOURCE_PROJECT_PAGE, type="projektseite", url=page.url,
                                           evidence=finding[:1000]))
        if not best or best.confidence < threshold:
            return page if not best or page.confidence > best.confidence else best
    return best


def _evidence(field_name: str, url: str, finding: str):
    from models import Evidence
    return Evidence(field=field_name, url=url, finding=finding[:1000], source=SOURCE_PROJECT_PAGE)


def lead_context(lead, facts: dict | None = None) -> dict:
    """Keyword arguments of `match_lookup` for a RawLead plus its parsed catalogue facts (context.engine.parse_catalogue)."""
    facts = facts or {}
    recipient = (facts.get("recipient") or "").strip()
    executing = (facts.get("executing") or "").strip()
    institution = executing or recipient or None
    return {"institution": institution, "executing": executing or None, "location": lead.location,
            "topic": lead.description, "reference": facts.get("fkz"), "founders": list(lead.founders)}
