"""Press releases from idw-online.de (Informationsdienst Wissenschaft) as dated, sourced text.

idw is where German universities and research institutes publish their spin-off announcements,
EXIST grants and pilot projects, often months before a company has a website or an imprint. There
is no API, so we use the public HTML search and article pages (verified 2026-11-20):

* Search: ``GET /de/simplesearch?words=<term>&scope=press_release&sort_order=start_datetime&...``
  returns ``Es wurden N Ergebnisse gefunden`` and, newest first, one block per hit with date, link
  (``/de/news<id>``), title, institution and a snippet in which the term is wrapped in
  ``<em class='label'>``. Hyphenated terms return nothing (``EXIST-Forschungstransfer`` -> 0,
  ``EXIST Forschungstransfer`` -> 241), so hyphens are replaced by spaces.
* Article: ``GET /de/news<id>`` carries date, ``<h4>`` title, the institution link and the text up
  to ``<hr/><h5>Wissenschaftliche Ansprechpartner`` (or the next section when that one is missing).
  Everything after that heading is personal contact data and is never returned.

Behaviour: search for the name without legal form; if that yields nothing and the name has several
words, retry once with the most distinctive word plus the institution. Keep at most five of the
newest hits whose title or snippet mentions the name (umlaut-folded, case-insensitive) or at least
two founder surnames; hits whose *title* contains the name rank first, then hits from the lead's own
institution. After fetching, an article whose title lacks the name and whose text mentions it only
once (a round-up such as a trade-fair or prize announcement) is dropped when a better article exists;
otherwise it is kept with ``source="idw (Erwähnung)"`` so that ``context.classify`` only uses the
lines around the mention. Each kept article becomes a ``SourceSignal(type="idw")`` with title and
body, an ``Evidence(field="idw")`` per article, and rule-based evidence sentences for
``founding_statement``, ``grants_mention`` and ``ip_mention`` - taken from every sentence when the
title names the lead, otherwise only from sentences that name the lead or a founder surname. A sentence
with the lead name and "2018 gegründet" / "founded in 2018" additionally yields
``Evidence(field="founding_year_mention")`` and ``fields["founding_year_hint"]`` (consumed by the
engine). No enum decisions are made here; ``context.classify`` and the engine do that from the text.

Limits: at most six requests per lead (one or two searches plus up to five articles), one second
between requests, everything through the cache. Failures end up in ``errors`` as ``"idw: ..."``.
"""
from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse
from datetime import date, datetime

from context.cache import Cache
from context.http import FetchError, request
from context.lookup import Lookup
from models import Evidence, SourceSignal

BASE = "https://idw-online.de"
MAX_REQUESTS = 6
MAX_ARTICLES = 5
MIN_INTERVAL = 1.0
TIMEOUT = 20
MAX_EVIDENCE_CHARS = 8000
SOURCE = "idw"
MENTION_SOURCE = "idw (Erwähnung)"

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})
_LEGAL_FORMS = re.compile(
    r"\b(gmbh\s*&\s*co\.?\s*kg|gmbh|ug|ag|se|kg|ohg|gbr|e\.?\s?v\.?|ltd\.?|inc\.?)\b"
    r"|\bi\.\s?gr?\.?(?=\s|$)|\(haftungsbeschr(ä|ae)nkt\)|haftungsbeschr(ä|ae)nkt|in gr(ü|ue)ndung",
    re.IGNORECASE,
)
_STOPWORDS = {
    "und", "the", "and", "for", "fuer", "von", "der", "die", "das", "des", "mit", "aus", "projekt",
    "project", "gruppe", "group", "team", "labs", "lab", "systems", "system", "technologies",
    "technology", "solutions", "software", "digital", "startup", "start-up", "spin-off", "spinoff",
}

_RE_COUNT = re.compile(r"Es wurden (\d+) Ergebnisse")
_RE_ITEM = re.compile(
    r"<p>(\d\d\.\d\d\.\d{4} \d\d:\d\d)</p>.*?<h6><a href=\"(/de/news\d+)\">(.*?)</a></h6>\s*<p><em>(.*?)</p>"
    r"(?:\s*</em>)?\s*(?:<p>(.*?)</p>)?",
    re.DOTALL,
)
_RE_ART_DATE = re.compile(r"(\d\d\.\d\d\.\d{4} \d\d:\d\d)\s*</em>")
_RE_ART_TITLE = re.compile(r"<h4>(.*?)</h4>", re.DOTALL)
_RE_ART_INST = re.compile(r"<a href=\"/de/institution\d+\">(.*?)</a>", re.DOTALL)
_RE_SUBHEADER = re.compile(r"<h5 class=\"subheader\">.*?</h5>", re.DOTALL)
_BODY_END = re.compile(
    r"<hr\s*/?>\s*<h5>\s*Wissenschaftliche Ansprechpartner"
    r"|<hr\s*/?>\s*<h5>\s*(Originalpublikation|Weitere Informationen|Anhang)"
    r"|<hr class=\"widescreenhide\""
    r"|<hr\s*/?>\s*<p>\s*<strong>Merkmale dieser Pressemitteilung",
    re.DOTALL,
)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_BREAK = re.compile(r"<br\s*/?>|</p>|</h\d>|</li>|</div>|</tr>", re.IGNORECASE)
_RE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„\"(0-9])")
_RE_ABBREV = re.compile(r"\b(Dr|Prof|Dipl|Ing|Mio|Mrd|Nr|ca|bzw|vgl|etc|St|z\. ?B|u\. ?a|d\. ?h)\.$")

# Rule detectors; they run on the umlaut-folded, lower-cased sentence.
_RE_FOUNDING = re.compile(
    r"\bgegruendet\b|\bgruendung (von|der|des|einer|eines)\b|\bausgegruendet\b|\bneu gegruendete",
)
_RE_FOUNDING_CONTEXT = re.compile(r"ausgruendung|spin-?off|start-?up|gmbh|\bug\b|unternehmen|firma")
# "Jedes Jahr werden an der TUM 70 bis 80 Unternehmen gegründet" is a statistic, not the lead's founding.
_RE_FOUNDING_STATS = re.compile(
    r"jedes jahr|jaehrlich|pro jahr|every year|annually|each year|"
    r"\b\d+ (?:bis|to|-) \d+ |mehr als \d+ |more than \d+ |ueber \d+ |rund \d+ |about \d+ ",
)
# "EXIST" in capitals is unambiguous; lower-case "exist" only together with a programme name, so that
# English sentences ("does not exist") do not count.
_RE_GRANT_UPPER = re.compile(r"\bEXIST\b")
_RE_GRANT_FOLDED = re.compile(
    r"\bexist[- ](forschungstransfer|gruendungsstipendium|gruenderstipendium|women|potentiale)"
    r"|gruend(ungs|er)stipendium",
)
_RE_IP = re.compile(r"patent")
_RE_FOUNDING_YEAR = re.compile(
    r"\b(\d{4}) gegruendet\b|\bgegruendet (?:im jahr )?(\d{4})\b|\bgruendung (?:im jahr )?(\d{4})\b|\bfounded in (\d{4})\b",
)


# --- text helpers ------------------------------------------------------------------------------

def fold(text: str) -> str:
    """Lower-case, umlauts transliterated, accents removed, whitespace collapsed."""
    text = text.translate(_UMLAUTS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def strip_legal_form(name: str) -> str:
    cleaned = _LEGAL_FORMS.sub(" ", name or "")
    cleaned = re.sub(r"[,;]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -–")


def search_term(name: str) -> str:
    """Name without legal form, hyphens replaced by spaces (idw returns nothing for hyphenated terms)."""
    return re.sub(r"\s+", " ", strip_legal_form(name).replace("-", " ").replace("/", " ")).strip()


def distinctive_word(name: str) -> str | None:
    """Longest word of the name that is not a stopword and has at least four letters."""
    words = [w for w in re.split(r"[\s\-/]+", strip_legal_form(name)) if w]
    candidates = [w for w in words if len(w) >= 4 and fold(w) not in _STOPWORDS]
    if not candidates:
        return None
    return max(candidates, key=len)


def surnames(founders: list[str]) -> list[str]:
    out = []
    for founder in founders or []:
        parts = [p for p in re.split(r"[\s,]+", founder.strip()) if p and not p.endswith(".")]
        parts = [p for p in parts if fold(p) not in {"prof", "dr", "dipl", "ing", "msc", "phd"}]
        if parts:
            last = fold(parts[-1])
            if len(last) >= 3 and last not in out:
                out.append(last)
    return out


def _clean_html_text(fragment: str) -> str:
    text = _RE_BREAK.sub("\n", fragment)
    text = _RE_TAG.sub("", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t\r\xa0]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _parse_datetime(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        return None


def search_url(term: str) -> str:
    return BASE + "/de/simplesearch?" + urllib.parse.urlencode({
        "words": term, "scope": "press_release", "sort_order": "start_datetime", "_form_": "Results", "page": "1",
    })


# --- parsing -----------------------------------------------------------------------------------

def parse_search(page: str) -> tuple[int | None, list[dict]]:
    """Return (result count, items). Items: path, url, when, title, institution, snippet."""
    m = _RE_COUNT.search(page or "")
    count = int(m.group(1)) if m else None
    items = []
    for hit in _RE_ITEM.finditer(page or ""):
        when, path, title, institution, snippet = hit.groups()
        items.append({
            "path": path,
            "url": BASE + path,
            "when": _parse_datetime(when),
            "title": _clean_html_text(title),
            "institution": _clean_html_text(institution),
            "snippet": _clean_html_text(snippet or ""),
        })
    return count, items


def parse_article(page: str) -> dict:
    """Return date, title, institution and body text of an idw article page.

    The body is the text between the title and the first section break (scientific contacts,
    further information, images or the 'Merkmale' box); contact data after that is dropped."""
    page = page or ""
    m = _RE_ART_DATE.search(page)
    when = _parse_datetime(m.group(1)) if m else None
    t = _RE_ART_TITLE.search(page)
    title = _clean_html_text(t.group(1)) if t else ""
    i = _RE_ART_INST.search(page)
    institution = _clean_html_text(i.group(1)) if i else ""
    body = ""
    if t:
        rest = page[t.end():]
        end = _BODY_END.search(rest)
        if end:
            rest = rest[:end.start()]
        rest = _RE_SUBHEADER.sub("", rest, count=1)
        body = _clean_html_text(rest)
    return {"date": when.date() if when else None, "title": title, "institution": institution, "body": body}


def sentences(text: str) -> list[str]:
    """Split on sentence ends and line breaks, but not after common abbreviations ("Dr.", "Mio.")."""
    out: list[str] = []
    for block in (text or "").split("\n"):
        parts: list[str] = []
        for chunk in _RE_SENTENCE_SPLIT.split(block):
            chunk = chunk.strip()
            if not chunk:
                continue
            if parts and _RE_ABBREV.search(parts[-1]):
                parts[-1] = parts[-1] + " " + chunk
            else:
                parts.append(chunk)
        out.extend(parts)
    return out


def name_pattern(name: str):
    """Whole-word pattern for the folded lead name (without legal form); None for an empty name."""
    name_f = fold(strip_legal_form(name))
    if not name_f:
        return None
    return re.compile(r"(?<![a-z0-9])" + re.escape(name_f) + r"(?![a-z0-9])")


def mentions_lead(folded: str, name_re, names: list[str]) -> bool:
    """True if the folded text names the lead or one of the founder surnames (whole words)."""
    if name_re is not None and name_re.search(folded):
        return True
    return any(re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", folded) for s in names)


def founding_year(sentence: str, name: str) -> int | None:
    """Explicit founding year from a sentence that names the lead ("Kiutra 2018 gegründet", "founded in 2019")."""
    folded = fold(sentence)
    name_re = name_pattern(name)
    if name_re is None or not name_re.search(folded):
        return None
    m = _RE_FOUNDING_YEAR.search(folded)
    if not m:
        return None
    year = int(next(g for g in m.groups() if g))
    return year if 1900 <= year <= date.today().year + 1 else None


def detect_mentions(text: str, name: str, founders: list[str] | None = None,
                    about_lead: bool | None = None) -> dict[str, list[str]]:
    """Rule-based sentence picks: founding statements, EXIST/grant mentions, patent mentions.

    When the article is about the lead (``about_lead``; default: its first line/title names the lead or
    the name occurs at least twice) every sentence qualifies; otherwise only sentences that name the lead
    or a founder surname, so that a round-up about several start-ups cannot lend another company's
    patents or founding date."""
    found = {"founding_statement": [], "grants_mention": [], "ip_mention": []}
    name_re = name_pattern(name)
    names = surnames(founders or [])
    if about_lead is None:
        about_lead = name_re is not None and (bool(name_re.search(fold((text or "").split("\n", 1)[0])))
                                              or len(name_re.findall(fold(text or ""))) >= 2)
    for sentence in sentences(text):
        folded = fold(sentence)
        if not about_lead and not mentions_lead(folded, name_re, names):
            continue
        if _RE_FOUNDING.search(folded) and (mentions_lead(folded, name_re, names) or _RE_FOUNDING_CONTEXT.search(folded)) \
                and not _RE_FOUNDING_STATS.search(folded):
            found["founding_statement"].append(sentence)
        if _RE_GRANT_UPPER.search(sentence) or _RE_GRANT_FOLDED.search(folded):
            found["grants_mention"].append(sentence)
        if _RE_IP.search(folded):
            found["ip_mention"].append(sentence)
    return found


# --- matching ----------------------------------------------------------------------------------

def _matches(item: dict, name_f: str, names: list[str]) -> bool:
    hay = fold(item["title"] + " " + item["snippet"])
    if name_f and name_f in hay:
        return True
    return sum(1 for s in names if s in hay) >= 2


def select_items(items: list[dict], name: str, founders: list[str], institution: str | None,
                 limit: int = MAX_ARTICLES) -> list[dict]:
    """Matching items: title names the lead first, then the lead's institution, then newest; at most ``limit``."""
    name_f = fold(strip_legal_form(name))
    names = surnames(founders)
    kept = [it for it in items if _matches(it, name_f, names)]
    inst_f = fold(institution) if institution else ""

    def from_institution(it) -> bool:
        item_inst = fold(it["institution"])
        return bool(inst_f) and bool(item_inst) and (inst_f in item_inst or item_inst in inst_f)

    def title_has_name(it) -> bool:
        return bool(name_f) and name_f in fold(it["title"])

    kept.sort(key=lambda it: (0 if title_has_name(it) else 1, 0 if from_institution(it) else 1,
                              -((it["when"] or datetime.min) - datetime.min).total_seconds()))
    return kept[:limit]


# --- lookup ------------------------------------------------------------------------------------

def idw_lookup(name: str, *, institution: str | None, founders: list[str], cache: Cache, fetch=None) -> Lookup:
    """Collect idw press releases about ``name`` as signals and evidence. Never raises."""
    result = Lookup()
    if fetch is None:
        def fetch(url):
            return request(url, cache=cache, min_interval=MIN_INTERVAL, timeout=TIMEOUT)

    budget = [MAX_REQUESTS]

    def get(url: str) -> tuple[str | None, str | None]:
        if budget[0] <= 0:
            return None, "idw: Anfragebudget erschöpft"
        budget[0] -= 1
        try:
            text = fetch(url)
        except FetchError as e:
            return None, "idw: %s" % re.sub(r"^[\w.-]*idw-online\.de: ", "", str(e))
        except Exception as e:  # noqa: BLE001 - never raise out of a lookup
            return None, "idw: %s" % (str(e) or type(e).__name__)
        if not isinstance(text, str):
            return None, "idw: unerwartete Antwort"
        return text, None

    term = search_term(name)
    if not term:
        return result

    page, err = get(search_url(term))
    if err:
        result.errors.append(err)
        return result
    count, items = parse_search(page)
    if count == 0 or not items:
        word = distinctive_word(name)
        if word and len(term.split()) > 1 and fold(word) != fold(term):
            retry = (word + " " + search_term(institution)).strip() if institution else word
            page, err = get(search_url(retry))
            if err:
                result.errors.append(err)
                return result
            count, items = parse_search(page)
    if count == 0 or not items:
        result.errors.append("idw: keine Treffer")
        return result

    chosen = select_items(items, name, founders, institution)
    if not chosen:
        result.errors.append("idw: keine Treffer")
        return result

    name_re = name_pattern(name)
    names = surnames(founders)
    articles = []
    for item in chosen:
        page, err = get(item["url"])
        if err:
            result.errors.append(err)
            if "budget" in err:
                break
            continue
        art = parse_article(page)
        title = art["title"] or item["title"]
        when = art["date"] or (item["when"].date() if item["when"] else None)
        text = (title + "\n" + art["body"]).strip()
        if not text:
            result.errors.append("idw: leerer Artikel %s" % item["url"])
            continue
        folded = fold(text)
        in_title = name_re is not None and bool(name_re.search(fold(title)))
        count = len(name_re.findall(folded)) if name_re is not None else 0
        by_founders = sum(1 for s in names if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", folded)) >= 2
        strong = in_title or count >= 2 or (count == 0 and by_founders)
        articles.append((item, title, when, text, in_title, strong))

    if any(strong for *_, strong in articles):
        articles = [a for a in articles if a[-1]]       # drop round-ups when a real article exists
    for item, title, when, text, in_title, strong in articles:
        source = SOURCE if strong else MENTION_SOURCE
        result.signals.append(SourceSignal(source=source, type="idw", url=item["url"], date=when,
                                           evidence=text[:MAX_EVIDENCE_CHARS]))
        result.evidence.append(Evidence(field="idw", url=item["url"], finding=title[:1000],
                                        source=source, source_date=when))
        for field_name, hits in detect_mentions(text, name, founders, about_lead=strong).items():
            for sentence in hits[:3]:
                result.evidence.append(Evidence(field=field_name, url=item["url"], finding=sentence[:1000],
                                                source=source, source_date=when))
        for sentence in sentences(text):
            year = founding_year(sentence, name)
            if year is not None:
                result.evidence.append(Evidence(field="founding_year_mention", url=item["url"],
                                                finding=sentence[:1000], source=source, source_date=when))
                result.fields.setdefault("founding_year_hint", year)
                break
    return result
