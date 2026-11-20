"""Patents via the Google Patents search XHR (`patents`, `ip_status`).

Data source: ``https://patents.google.com/xhr/query?url=assignee%3D%22<firma>%22%26num%3D10&exp=``,
the JSON endpoint behind the Google Patents search page. It needs no key, but it is fragile:
after roughly a dozen requests within 90 seconds Google answers HTTP 503 and keeps the client
blocked for a while. EPO OPS, Espacenet, Lens and DPMAregister need keys or captchas and are
deliberately not used.

Protection against the block (do not loosen):

* ``MIN_INTERVAL = 15`` seconds between requests to patents.google.com, timeout 20 s, **no retries**
  (a 503 is recorded as ``"patents: HTTP 503 (gesperrt)"`` and the lead is abandoned).
* A process-wide ``Budget`` (default ``MAX_REQUESTS = 6``) caps the total number of live requests
  per run so a batch of 50 leads cannot trigger the block. An exhausted budget yields
  ``([], Lookup(errors=["patents: Budget erschöpft"]))`` without any call. Cached answers are free
  and do not count, so a second run of the same leads is complete and identical.

What is queried and what counts as a hit:

* ``assignee="<company without legal form>"``. ``results.total_num_results`` is fuzzy (``kiutra``
  reports 888 results, three of which are kiutra's), so only results are kept whose ``assignee``
  (any entry) contains the normalised company name (casefold, umlauts folded, legal forms
  stripped).
* If the company has no assignee hit and founders are known, at most two founders are queried as
  ``inventor="<name>"``. Results whose assignee is not a university or research institute are
  preferred; if there are only institutional ones they are kept but marked
  ``quote="Erfinder: <name>; Anmelder: <assignee>"`` so the scoring can see that the IP is not
  (yet) the company's.
* Family members are collapsed where obvious: same title and same priority date -> the granted
  one wins.

``ip_status`` is ``"patent_erteilt"`` if any kept result has a grant date, ``"patent_angemeldet"``
if there are only applications, and **never ``"keine"``**: an empty result is not proof of absence.
Google Patents indexes applications only after publication (18 months after priority), the
assignee string may differ from the company name (holding, university, founder as private
applicant), and the search itself is a fuzzy full-text match. So "nothing found" means "nothing
visible here", and the field stays unset.

Realistic hit rate: low for pre-founding research projects. Patents from a university project are
filed by the university (or its TTO), so the assignee query misses them and the inventor fallback
finds them only with a marked quote. Expect assignee hits mainly for companies that are two or more
years past founding.
"""
from __future__ import annotations

import hashlib
import html
import re
import urllib.parse

from context.cache import Cache
from context.http import FetchError, get_json
from context.lookup import Lookup
from models import Evidence, Patent

ENDPOINT = "https://patents.google.com/xhr/query"
PATENT_URL = "https://patents.google.com/patent/"
SOURCE = "Google Patents"
MIN_INTERVAL = 15.0
TIMEOUT = 20
MAX_REQUESTS = 6
MAX_FOUNDERS = 2
NUM = 10

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "á": "a", "à": "a"})
_LEGAL_FORMS = re.compile(
    r"\b(gmbh\s*&\s*co\.?\s*kg|gmbh|ug|ag|se|kg|ohg|gbr|e\.?\s?v\.?|ltd\.?|inc\.?|llc|corp\.?|co\.?)\b"
    r"|\bi\.\s?gr?\.?(?=\s|$)|\(haftungsbeschr(ä|ae)nkt\)|haftungsbeschr(ä|ae)nkt|in gr(ü|ue)ndung",
    re.IGNORECASE,
)
_INSTITUTION = re.compile(
    r"universit|hochschule|technische|fraunhofer|max[- ]planck|helmholtz|leibniz|institut|"
    r"forschungszentrum|\bkit\b|\btum\b|\brwth\b|\beth\b|charit[eé]|klinikum|college|school|academy|"
    r"\bcnrs\b|\bdlr\b|\bdesy\b|\bcea\b|stiftung|gesellschaft zur f(ö|oe)rderung|society",
    re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")


class Budget:
    """Process-wide counter of live requests to patents.google.com (cache hits are free)."""

    def __init__(self, maximum: int = MAX_REQUESTS):
        self.maximum = maximum
        self.used = 0

    @property
    def left(self) -> int:
        return max(self.maximum - self.used, 0)

    def take(self) -> bool:
        if self.used >= self.maximum:
            return False
        self.used += 1
        return True


BUDGET = Budget()


# --- helpers ---------------------------------------------------------------------------------

def normalise_name(name: str) -> str:
    """Casefold, fold umlauts, strip legal forms and punctuation: 'Müller Fräsen GmbH i.G.' -> 'mueller fraesen'."""
    text = (name or "").casefold().translate(_UMLAUTS)
    text = _LEGAL_FORMS.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def query_url(kind: str, value: str, num: int = NUM) -> str:
    inner = '%s="%s"&num=%d' % (kind, value, num)
    return ENDPOINT + "?" + urllib.parse.urlencode({"url": inner, "exp": ""})


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_as_list(item if isinstance(item, str) else (item or {}).get("name") if isinstance(item, dict) else str(item)))
        return out
    return [str(value)]


def _clean(text) -> str:
    return html.unescape(_TAGS.sub("", str(text or ""))).strip()


def parse_results(data) -> list[dict]:
    """Flatten ``results.cluster[*].result[*].patent`` into plain dicts; tolerant of missing parts."""
    out = []
    results = (data or {}).get("results") or {}
    for cluster in results.get("cluster") or []:
        for item in (cluster or {}).get("result") or []:
            pat = (item or {}).get("patent") or {}
            number = _clean(pat.get("publication_number"))
            if not number:
                continue
            out.append({
                "publication_number": number,
                "title": _clean(pat.get("title")) or None,
                "assignee": [_clean(a) for a in _as_list(pat.get("assignee")) if _clean(a)],
                "inventor": [_clean(i) for i in _as_list(pat.get("inventor")) if _clean(i)],
                "filing_date": _clean(pat.get("filing_date")) or None,
                "grant_date": _clean(pat.get("grant_date")) or None,
                "publication_date": _clean(pat.get("publication_date")) or None,
                "priority_date": _clean(pat.get("priority_date")) or None,
            })
    return out


def total_results(data) -> int | None:
    try:
        return int(((data or {}).get("results") or {}).get("total_num_results"))
    except (TypeError, ValueError):
        return None


def assignee_matches(result: dict, company_norm: str) -> bool:
    if not company_norm:
        return False
    return any(company_norm in normalise_name(a) for a in result.get("assignee") or [])


def inventor_matches(result: dict, founder: str) -> bool:
    """The founder's surname (and first-name initial if present) must appear in the inventor list."""
    parts = normalise_name(founder).split()
    if not parts:
        return False
    surname = parts[-1]
    for inv in result.get("inventor") or []:
        inv_norm = normalise_name(inv)
        if surname in inv_norm.split() and (len(parts) == 1 or any(w.startswith(parts[0][0]) for w in inv_norm.split())):
            return True
    return False


def is_institution(assignees: list[str]) -> bool:
    return any(_INSTITUTION.search(a) for a in assignees)


def dedupe(results: list[dict]) -> list[dict]:
    """Same title + same priority date = same family; keep the granted member, else the first."""
    kept: dict = {}
    order: list = []
    for r in results:
        key = (normalise_name(r.get("title") or ""), r.get("priority_date")) if r.get("title") and r.get("priority_date") else r["publication_number"]
        if key not in kept:
            kept[key] = r
            order.append(key)
        elif r.get("grant_date") and not kept[key].get("grant_date"):
            kept[key] = r
    return [kept[k] for k in order]


def to_patent(result: dict, *, inventor: str | None = None, mark_institution: bool = False) -> Patent:
    assignee = ", ".join(result.get("assignee") or []) or "Anmelder unbekannt"
    quote = "%s, %s, angemeldet %s" % (result["publication_number"], assignee, result.get("filing_date") or "?")
    if result.get("grant_date"):
        quote += ", erteilt %s" % result["grant_date"]
    if mark_institution and inventor:
        quote = "Erfinder: %s; Anmelder: %s (%s)" % (inventor, assignee, quote)
    return Patent(
        status="patent_erteilt" if result.get("grant_date") else "patent_angemeldet",
        title=result.get("title"),
        quote=quote,
        url=PATENT_URL + result["publication_number"],
    )


# --- main entry point ------------------------------------------------------------------------

def patent_lookup(company: str, founders: list[str], *, cache: Cache, fetch=None,
                  budget: Budget | None = None) -> tuple[list[Patent], Lookup]:
    """Return (patents, Lookup) for a company. See module docstring for the rules and limits.

    ``fetch(url) -> dict`` is injectable for tests; the default goes through ``context.http.get_json``
    with the hard throttle and the shared cache. ``budget`` defaults to the module-wide ``BUDGET``.
    ``ip_status`` is never set to "keine": absence of a hit is not proof of absence (see above).
    """
    budget = budget if budget is not None else BUDGET
    look = Lookup()
    patents: list[Patent] = []

    def live(url: str):
        return get_json(url, timeout=TIMEOUT, min_interval=MIN_INTERVAL, cache=cache, retries=0)

    getter = fetch or live

    def call(url: str):
        """Return parsed JSON, or None after recording the error (and stopping the lead on 503/budget)."""
        if fetch is None and cache is not None and cache.get(cache_key(url)) is not None:
            return getter(url)  # cached answer: free, does not consume budget
        if not budget.take():
            look.errors.append("patents: Budget erschöpft")
            return None
        try:
            return getter(url)
        except FetchError as e:
            msg = str(e)
            if "503" in msg:
                look.errors.append("patents: HTTP 503 (gesperrt)")
            else:
                look.errors.append("patents: " + msg)
            return None
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            look.errors.append("patents: %s" % type(e).__name__)
            return None

    company_norm = normalise_name(company)
    if not company_norm:
        look.errors.append("patents: kein Firmenname")
        return patents, look

    data = call(query_url("assignee", company_norm))
    if data is None:
        return patents, look
    hits = [r for r in parse_results(data) if assignee_matches(r, company_norm)]
    hits = dedupe(hits)
    patents = [to_patent(r) for r in hits]

    if not patents:
        for founder in [f for f in founders or [] if f and f.strip()][:MAX_FOUNDERS]:
            data = call(query_url("inventor", founder.strip()))
            if data is None:
                break
            found = dedupe([r for r in parse_results(data) if inventor_matches(r, founder)])
            if not found:
                continue
            own = [r for r in found if not is_institution(r.get("assignee") or [])]
            if own:
                patents.extend(to_patent(r, inventor=founder) for r in own)
            else:
                patents.extend(to_patent(r, inventor=founder, mark_institution=True) for r in found)
            if patents:
                break

    if patents:
        status = "patent_erteilt" if any(p.status == "patent_erteilt" for p in patents) else "patent_angemeldet"
        look.add("ip_status", status, url=str(patents[0].url), finding=patents[0].quote or patents[0].title or "", source=SOURCE)
        look.fields["patents"] = patents
    return patents, look


def cache_key(url: str) -> str:
    """The key ``context.http.request`` uses for a GET without body (used to tell cache hits from live calls)."""
    return "http:" + hashlib.sha1(("GET " + url + " ").encode("utf-8")).hexdigest()
