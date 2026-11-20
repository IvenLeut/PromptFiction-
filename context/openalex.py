"""OpenAlex author lookup for founder profiles (see context/ENRICHMENT.md).

Endpoints (https://api.openalex.org, no key, generic User-Agent from context.http, no mailto):

1. Author search
   GET /authors?search=<name>&per-page=10&select=id,display_name,works_count,cited_by_count,
       summary_stats,last_known_institutions,affiliations,topics
   `search=` is diacritic-tolerant ("Boetius" finds "Boëtius"); `filter=display_name.search:` returned
   the same candidates in the probe, so only `search=` is used.
2. Works in the product field (only when field terms are given)
   GET /works?filter=authorships.author.id:<A-id>&search=<term1 OR term2 ...>&per-page=1&select=id
   -> meta.count (title/abstract/fulltext match, "deep sea OR methane" is grouped as phrases by the API).

Disambiguation: candidates must match the name (diacritics folded, ue/oe/ae/ss normalised, initials
allowed); then an institution match (token overlap on the distinctive parts, German abbreviations such
as TU/RWTH/KIT/LMU/HPI expanded, ROR/OpenAlex ids compared when the caller passes one), then German
affiliations, then works_count decide. Confidence tiers: 0.9 name + current institution, 0.8 name +
earlier affiliation, 0.6 single candidate with DE affiliation, 0.5 single DE candidate although the
given institution did not match, 0.4 single candidate without DE signal, 0.2 several candidates
without institution signal (-> no profile, error "openalex: mehrdeutig (<n> Kandidaten)").

Rate limit: without an API key OpenAlex bills ~0.001 USD per call against a shared 0.10 USD/day budget
per IP (about 100 calls/day); every call goes through the cache, so a rerun costs nothing.
"""
from __future__ import annotations

import logging
import re
import unicodedata
import urllib.parse

from context.cache import Cache
from context.http import get_json
from context.lookup import Lookup
from models import Evidence, FounderProfile

logger = logging.getLogger(__name__)

API = "https://api.openalex.org"
AUTHOR_SELECT = "id,display_name,works_count,cited_by_count,summary_stats,last_known_institutions,affiliations,topics"
SOURCE = "OpenAlex"
MIN_CONFIDENCE = 0.4
MAX_TERMS = 8

# Tokens that carry no identity (both languages), dropped before comparing institution names.
_STOP = {
    "the", "of", "for", "and", "de", "der", "die", "das", "des", "und", "fur", "am", "an", "in", "im", "zu",
    "university", "universitat", "universitaet", "universitatsmedizin", "uni", "hochschule", "college", "school",
    "institute", "institut", "institution", "institutes", "center", "centre", "zentrum", "research", "forschung",
    "forschungszentrum", "technical", "technische", "technology", "technologie", "technischen", "fachhochschule",
    "applied", "sciences", "angewandte", "wissenschaften", "gmbh", "ev", "e", "v", "germany", "deutschland",
    "association", "gesellschaft", "klinikum", "hospital", "medical", "medizinische", "fakultat", "faculty",
    "department", "lehrstuhl", "chair", "group", "lab", "laboratory",
}
_TECH = {"tu", "technical", "technische", "technischen", "technology", "technologie", "technik", "rwth", "kit"}
# Abbreviation -> distinctive tokens of the long form (names appear in OpenAlex in English or German).
_ABBREV = {
    "tu": set(), "th": set(), "fh": set(), "hs": set(),
    "rwth": {"rwth", "aachen"},
    "kit": {"kit", "karlsruhe"},
    "lmu": {"lmu", "ludwig", "maximilian"},
    "tum": {"tum", "munchen", "munich"},
    "hpi": {"hpi", "hasso", "plattner"},
    "dfki": {"dfki", "artificial", "intelligence", "kunstliche", "intelligenz"},
    "dlr": {"dlr", "aerospace", "luft", "raumfahrt"},
    "dkfz": {"dkfz", "cancer", "krebsforschung"},
    "mpi": {"max", "planck"},
    "mpg": {"max", "planck"},
    "awi": {"awi", "alfred", "wegener"},
    "fu": {"freie", "free"},
    "hu": {"humboldt"},
    "fau": {"erlangen", "nurnberg", "nuremberg"},
    "kth": {"kth", "royal"},
    "eth": {"eth", "zurich", "zurich"},
}
# German/English spellings of the same city or body; folded to one key.
_ALIAS = {
    "munich": "munchen", "cologne": "koln", "nuremberg": "nurnberg", "hanover": "hannover", "brunswick": "braunschweig",
    "freiburg": "freiburg", "gottingen": "gottingen", "vienna": "wien", "zurich": "zurich", "charite": "charite",
    "maxplanck": "planck", "max": "planck", "fraunhofer": "fraunhofer", "helmholtz": "helmholtz",
    "leibniz": "leibniz", "ludwigmaximilians": "ludwig", "maximilians": "maximilian", "maximilians-universitat": "maximilian",
}


def _fold(text: str) -> str:
    """Lowercase ASCII form: ü->u, Boëtius->boetius->boetius, Mueller->muller, Strauß->straus."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("ß", "ss")
    text = re.sub(r"(?<=[a-z])(ue|oe|ae)", lambda m: m.group(1)[0], text)
    return text.replace("ss", "s")


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _fold(text)) if t]


def _name_score(query: str, candidate: str) -> float:
    """1.0 same name, 0.8 initials/middle names differ, 0.0 different person (by last name)."""
    q, c = _tokens(re.sub(r"\b(prof|dr|phd|med|rer|nat|ing|habil|dipl|msc|bsc|ma|ba)\b\.?", " ", query, flags=re.I)), _tokens(candidate)
    if not q or not c:
        return 0.0
    if q[-1] != c[-1] and not (len(q) > 1 and q[-1] in c):
        return 0.0
    rest_c = [t for t in c if t != q[-1]]
    score, matched = 1.0, 0
    for i, token in enumerate(q[:-1]):
        hit = next((x for x in rest_c if x == token or (len(token) <= 2 and x.startswith(token))
                    or (len(x) <= 2 and token.startswith(x))), None)
        if hit is None:
            if i == 0:
                return 0.0  # first name does not appear at all
            score -= 0.2
        else:
            rest_c.remove(hit)
            matched += 1
            if hit != token:
                score -= 0.1
    unknown_extra = [t for t in rest_c if len(t) > 2]  # "Preface", "(eds" -> not the same record
    score -= 0.3 * len(unknown_extra)
    return max(0.0, round(score, 2))


def _distinctive(institution: str) -> tuple[list[frozenset[str]], bool]:
    """Identity token groups of an institution name (an abbreviation expands to one group of alternatives)
    and whether it is a technical university/body."""
    tokens = _tokens(institution)
    out, tech = [], False
    for token in tokens:
        if token in _TECH:
            tech = True
        if token in _ABBREV:
            group = frozenset(_ALIAS.get(_fold(t), _fold(t)) for t in _ABBREV[token])
        elif token in _STOP or len(token) < 2:
            continue
        else:
            group = frozenset({_ALIAS.get(token, token)})
        if group and group not in out:
            out.append(group)
    return out, tech


def _same_token(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and long_.startswith(short)


def _institution_score(given: str, candidate: dict) -> float:
    """0..1 similarity between the caller's institution string and one OpenAlex institution object."""
    given = (given or "").strip()
    if not given:
        return 0.0
    if "ror.org/" in given.lower() or "openalex.org/" in given.lower():  # caller passed an id instead of a name
        tail = given.lower().rstrip("/").rsplit("/", 1)[-1]
        ids = {str(candidate.get(k) or "").lower().rstrip("/").rsplit("/", 1)[-1] for k in ("id", "ror")}
        return 1.0 if tail and tail in ids else 0.0
    want, want_tech = _distinctive(given)
    have, have_tech = _distinctive(candidate.get("display_name") or "")
    if not want or not have:
        return 0.0
    have_tokens = {t for group in have for t in group}
    hits = sum(1 for group in want if any(_same_token(w, h) for w in group for h in have_tokens))
    score = hits / len(want)
    if score and len(want) == 1 and len(have) >= 3:
        score = 0.7  # single shared city token in a long name: plausible but weak
    if score and want_tech and not have_tech:
        score *= 0.4  # "TU Berlin" vs "Freie Universität Berlin"
    return round(score, 2)


def _institutions(author: dict) -> list[tuple[dict, bool]]:
    """(institution object, is_current) for last known institutions and all affiliations."""
    out, seen = [], set()
    for inst in author.get("last_known_institutions") or []:
        if inst.get("id") not in seen:
            seen.add(inst.get("id"))
            out.append((inst, True))
    for aff in author.get("affiliations") or []:
        inst = aff.get("institution") or {}
        if inst.get("id") not in seen:
            seen.add(inst.get("id"))
            out.append((inst, False))
    return out


def _rank(name: str, institution: str | None, results: list[dict]) -> list[dict]:
    """Attach name/institution scores and sort best-first."""
    ranked = []
    for author in results:
        ns = _name_score(name, author.get("display_name") or "")
        if ns < 0.6:
            continue
        insts = _institutions(author)
        best, best_current, best_inst = 0.0, False, None
        for inst, current in insts:
            s = _institution_score(institution, inst) if institution else 0.0
            if s > best or (s == best and current and not best_current and s > 0):
                best, best_current, best_inst = s, current, inst
        german = any((inst.get("country_code") or "").upper() == "DE" for inst, _ in insts)
        ranked.append({
            "author": author, "name_score": ns, "inst_score": best, "inst_current": best_current,
            "matched_institution": best_inst, "german": german, "works": int(author.get("works_count") or 0),
            "has_institution": bool(insts),
        })
    ranked.sort(key=lambda r: (r["inst_score"] >= 0.5, r["inst_score"], r["name_score"] >= 0.9, r["german"], r["works"]), reverse=True)
    return ranked


def _confidence(ranked: list[dict], institution: str | None) -> tuple[float, int]:
    """Confidence of the top candidate and the number of serious contenders."""
    top = ranked[0]
    serious = [r for r in ranked if r["has_institution"] or r["works"] >= 3] or ranked
    n = len(serious)
    if top["inst_score"] >= 0.5 and top["name_score"] >= 0.8:
        rivals = [r for r in serious[1:] if r["inst_score"] >= top["inst_score"]]
        base = 0.9 if top["inst_current"] else 0.8
        if top["inst_score"] < 1.0:
            base -= 0.1
        return (base if not rivals else 0.5), n
    if n == 1:
        if top["german"]:
            return (0.5 if institution else 0.6), n
        return (0.4 if top["name_score"] >= 0.8 else 0.3), n
    return 0.2, n


def _fmt_terms(terms: list[str]) -> str:
    return ", ".join(terms)


def author_lookup(name: str, *, institution: str | None, field_terms: list[str], cache: Cache | None,
                  fetch=None) -> tuple[FounderProfile | None, Lookup]:
    """Find the founder in OpenAlex and return a FounderProfile with publication counts, or (None, errors)."""
    lookup = Lookup()
    if fetch is None:
        def fetch(url):
            return get_json(url, cache=cache, min_interval=0.2)
    name = (name or "").strip()
    if not name:
        lookup.errors.append("openalex: kein Name")
        return None, lookup
    terms = list(dict.fromkeys(t.strip() for t in (field_terms or []) if t and t.strip()))[:MAX_TERMS]
    search_url = "%s/authors?%s" % (API, urllib.parse.urlencode({"search": name, "per-page": 10, "select": AUTHOR_SELECT}))
    try:
        data = fetch(search_url)
        results = list((data or {}).get("results") or [])
    except Exception as exc:  # FetchError, ValueError, ... -> never raise
        logger.warning("OpenAlex-Suche fehlgeschlagen für %r: %s", name, exc)
        lookup.errors.append("openalex: %s" % (str(exc) or type(exc).__name__))
        return None, lookup
    if not results:
        lookup.errors.append("openalex: kein Treffer für %s" % name)
        return None, lookup
    ranked = _rank(name, institution, results)
    if not ranked:
        lookup.errors.append("openalex: kein Namenstreffer für %s (%d Suchergebnisse)" % (name, len(results)))
        return None, lookup
    confidence, n_candidates = _confidence(ranked, institution)
    if confidence < MIN_CONFIDENCE:
        total = int(((data or {}).get("meta") or {}).get("count") or 0)
        lookup.errors.append("openalex: mehrdeutig (%d Kandidaten)" % max(n_candidates, total if len(results) >= 10 else 0))
        return None, lookup

    top = ranked[0]
    author = top["author"]
    author_id = str(author.get("id") or "")
    short_id = author_id.rsplit("/", 1)[-1]
    openalex_url = "https://openalex.org/%s" % short_id if short_id else None
    current = (author.get("last_known_institutions") or [{}])[0]
    inst_obj = top["matched_institution"] if top["inst_current"] and top["matched_institution"] else current
    inst_name = (inst_obj or {}).get("display_name") or None
    works_total = int(author.get("works_count") or 0)
    stats = author.get("summary_stats") or {}
    topics = [t.get("display_name") for t in (author.get("topics") or [])[:3] if t.get("display_name")]

    works_in_field, works_url = None, None
    if terms and short_id:
        works_url = "%s/works?%s" % (API, urllib.parse.urlencode({
            "filter": "authorships.author.id:%s" % short_id, "search": " OR ".join(terms), "per-page": 1, "select": "id"}))
        try:
            meta = (fetch(works_url) or {}).get("meta") or {}
            works_in_field = int(meta.get("count")) if meta.get("count") is not None else None
        except Exception as exc:
            logger.warning("OpenAlex-Werke fehlgeschlagen für %s: %s", short_id, exc)
            lookup.errors.append("openalex works: %s" % (str(exc) or type(exc).__name__))

    parts = ["OpenAlex: %s" % author.get("display_name")]
    if inst_name:
        parts.append(inst_name)
    parts.append("%d Arbeiten" % works_total)
    if works_in_field is not None:
        parts.append("%d im Feld %s" % (works_in_field, _fmt_terms(terms)))
    elif topics:
        parts.append("Themen: %s" % ", ".join(topics))
    parts.append("Zuordnung %.0f %%" % (confidence * 100))
    finding = ", ".join(parts)

    qualifications = None
    if stats.get("h_index") is not None and works_total:
        qualifications = "h-Index %d, %d Arbeiten" % (int(stats["h_index"]), works_total)
        if inst_name:
            qualifications += ", %s" % inst_name

    profile = FounderProfile(
        name=name, institution=inst_name, qualifications=qualifications, openalex_url=openalex_url,
        works_total=works_total, works_in_field=works_in_field, match_confidence=round(confidence, 2),
        source_url=openalex_url or search_url,
    )
    lookup.add("founder_profiles", [profile], url=openalex_url or search_url, finding=finding, source=SOURCE)
    if qualifications:
        lookup.fields["qualifications"] = qualifications
    if works_url and works_in_field is not None:
        lookup.evidence.append(Evidence(
            field="founder_profiles", url=works_url, source=SOURCE,
            finding="%d von %d Arbeiten passen zu: %s" % (works_in_field, works_total, _fmt_terms(terms))))
    return profile, lookup
