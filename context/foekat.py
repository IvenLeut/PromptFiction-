"""Förderkatalog des Bundes (foerderportal.bund.de/foekat): EXIST and other federal grants by FKZ or name.

The catalogue is a Struts application: a session cookie (JSESSIONID, path /foekat) is set by
StartAction.do, searches are POSTed to SucheAction.do and detail pages are only served inside such a
session. Every page is ISO-8859-15, so POST bodies are encoded the same way. `context.http.request`
does not keep cookies, hence the small session helper below; every response still goes through the
cache so a second run never touches the site. Tests inject `fetch(method, url, data) -> text`.
"""
from __future__ import annotations

import hashlib
import html
import http.client
import http.cookiejar
import logging
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from urllib.error import HTTPError, URLError

from context.cache import Cache
from context.http import USER_AGENT
from context.lookup import Lookup
from models import Evidence, Grant, SourceSignal

logger = logging.getLogger(__name__)
SOURCE = "Förderkatalog"
ENCODING = "iso-8859-15"
BASE = "https://foerderportal.bund.de/foekat/jsp/"
START_URL = BASE + "StartAction.do"
SEARCH_URL = BASE + "SucheAction.do"
MAX_BYTES = 3_000_000
ROWS_PER_PAGE = 100
MAX_ROWS = 300          # at most three result pages per query
MAX_DETAILS = 3         # detail pages fetched per lead
AMBIGUOUS = 10          # more hits than this -> narrow with the institution
PROGRAMMES = {"03EF": "EXIST-Forschungstransfer", "03EG": "EXIST-Gründungsstipendium"}
LEGAL_FORMS = re.compile(
    r"(?<![\w.])(gGmbH|GmbH|mbH|UG|AG|SE|KG|OHG|GbR|e\.\s?V\.?|i\.\s?G\.?|i\.\s?Gr\.?|haftungsbeschränkt|Co\.?|&)(?![\w])\.?",
    re.IGNORECASE)
STOPWORDS = {"the", "and", "und", "der", "die", "das", "for", "für", "von", "gmbh", "project", "projekt", "team"}
_last_call = 0.0


class FoekatError(Exception):
    """Transport failure of the catalogue; recorded as `foekat: ...` in Lookup.errors."""


# --- transport ------------------------------------------------------------------------------------

def encode_form(fields: dict) -> bytes:
    """Form body in the catalogue's own charset (an umlaut in the name must arrive as one byte)."""
    return urllib.parse.urlencode(fields, encoding=ENCODING, errors="replace").encode("ascii")


class Session:
    """Cookie-keeping opener: starts the session lazily, 1 request/s, retries on 5xx."""

    def __init__(self, timeout: float = 20, min_interval: float = 1.0, retries: int = 2):
        self.timeout, self.min_interval, self.retries = timeout, min_interval, retries
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", USER_AGENT)]
        self.started = False

    def _throttle(self) -> None:
        global _last_call
        wait = _last_call + self.min_interval - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()

    def _open(self, method: str, url: str, data: bytes | None) -> str:
        last = None
        for attempt in range(self.retries + 1):
            self._throttle()
            req = urllib.request.Request(url, data=data, method=method)
            if data is not None:
                req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=" + ENCODING)
            try:
                with self.opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        raise FoekatError("Antwort größer als %d Bytes" % MAX_BYTES)
                    return body.decode(resp.headers.get_content_charset() or ENCODING, errors="replace")
            except HTTPError as e:
                last = FoekatError("HTTP %d" % e.code)
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last
            except (URLError, TimeoutError, http.client.HTTPException, OSError, UnicodeError) as e:
                last = FoekatError(type(e).__name__)
                if attempt < self.retries:
                    time.sleep(1 + attempt)
                    continue
        raise last or FoekatError("unbekannt")

    def fetch(self, method: str, url: str, data: bytes | None = None) -> str:
        if not self.started:
            self._open("GET", START_URL, None)
            self.started = True
        return self._open(method, url, data)


def _cached_fetch(fetch, cache: Cache | None):
    """Wrap a fetch so identical requests (method + URL + body) come from the cache."""
    def run(method: str, url: str, data: bytes | None = None) -> str:
        key = "foekat:" + hashlib.sha1((method + " " + url + " " + (data or b"").decode("latin-1")).encode("utf-8")).hexdigest()
        if cache is None:
            return fetch(method, url, data)
        return cache.memo(key, lambda: fetch(method, url, data))
    return run


# --- parsing --------------------------------------------------------------------------------------

def _text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment).replace("\xa0", " ")).strip()


def parse_amount(text: str) -> int | None:
    """'972.638,00 €' -> 972638, '1.234.567,89 €' -> 1234567."""
    m = re.search(r"\d[\d.]*(?:,\d+)?", text or "")
    if not m:
        return None
    whole = m.group(0).split(",")[0].replace(".", "")
    return int(whole) if whole.isdigit() else None


def parse_date(text: str) -> date | None:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_count(page: str) -> int:
    if re.search(r"Keine Treffer", page):
        return 0
    m = re.search(r"(\d+)\s+Treffer insgesamt", page)
    return int(m.group(1)) if m else 0


def parse_rows(page: str) -> list[dict]:
    """Rows of the result table (FKZ, Ressort, Förderempfänger, Ausführende Stelle, Thema, Laufzeit, Summe, Projekt)."""
    table = re.search(r'<table[^>]*aria-label="Suchergebnis"[^>]*>(.*?)</table>', page, re.S)
    if not table:
        return []
    body = re.search(r"<tbody>(.*?)</tbody>", table.group(1), re.S)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1) if body else table.group(1), re.S):
        cells = [_text(c) for c in re.findall(r'<td[^>]*class="table_cell"[^>]*>(.*?)</td>', tr, re.S)]
        if len(cells) < 7:
            continue
        link = re.search(r"[?&;]fkz=([^\"'&]+)", tr)
        fkz = html.unescape(urllib.parse.unquote(link.group(1))).strip() if link else cells[0].strip()
        dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", cells[5])
        rows.append({
            "fkz": fkz, "ressort": cells[1], "recipient": cells[2], "executing": cells[3],
            "thema": cells[4], "start": parse_date(dates[0] if dates else ""), "end": parse_date(dates[1] if len(dates) > 1 else ""),
            "amount": parse_amount(cells[6]), "project": cells[7] if len(cells) > 7 else "",
        })
    return rows


def parse_detail(page: str) -> dict:
    """Label -> value of the detail page; Förderempfänger/Ausführende Stelle also carry Ort and Bundesland."""
    out: dict = {}
    for chunk in re.split(r'<div class="detailAnsichtItem"', page)[1:]:
        inner = [_text(v) for v in re.findall(r"<div>(.*?)</div>", chunk, re.S)]
        if len(inner) < 2:
            continue
        label, value = inner[0], inner[1]
        out[label] = value
        extra = dict(zip(inner[2::2], inner[3::2]))
        if "Ort" in extra:
            out[label + " Ort"] = extra["Ort"]
        for key, val in extra.items():
            if key.startswith("Bundesland"):
                out[label + " Bundesland"] = val
    detail = {
        "fkz": out.get("Förderkennzeichen", ""),
        "thema": out.get("Thema des geförderten Vorhabens", ""),
        "amount": parse_amount(out.get("Förder- / Auftragssumme (Anteil des Bundes)", "")),
        "leistungsplan": out.get("Leistungsplansystematik", ""),
        "foerderart": out.get("Förderart", ""),
        "recipient": out.get("Förderempfänger/Auftragnehmer", ""),
        "recipient_ort": out.get("Förderempfänger/Auftragnehmer Ort", ""),
        "recipient_land": out.get("Förderempfänger/Auftragnehmer Bundesland", ""),
        "executing": out.get("Ausführende Stelle", ""),
        "executing_ort": out.get("Ausführende Stelle Ort", ""),
    }
    laufzeit = out.get("Laufzeit", "")
    parts = re.split(r"\s+bis\s+", laufzeit)
    detail["start"] = parse_date(parts[0]) if parts else None
    detail["end"] = parse_date(parts[1]) if len(parts) > 1 else None
    return detail


def programme_for(fkz: str, leistungsplan: str = "") -> str:
    for prefix, name in PROGRAMMES.items():
        if (fkz or "").upper().startswith(prefix):
            return name
    if "EXIST" in (leistungsplan or "").upper():
        return "EXIST"
    if leistungsplan:
        short = re.split(r"\s*[;/]\s*", leistungsplan.strip())[-1].strip()
        return short[:80] or "Bundesförderung"
    return "Bundesförderung"


def is_exist(fkz: str, leistungsplan: str = "") -> bool:
    return (fkz or "").upper()[:4] in PROGRAMMES or "EXIST" in (leistungsplan or "").upper()


def detail_url(fkz: str) -> str:
    return SEARCH_URL + "?actionMode=view&fkz=" + urllib.parse.quote(fkz, safe="")


# --- name handling --------------------------------------------------------------------------------

def _fold(text: str) -> str:
    """Lowercase ASCII with umlauts folded: 'Grün-Tech' -> 'gruentech', 'Gruentech' -> 'gruentech'."""
    text = (text or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def clean_name(name: str) -> str:
    """Company name without legal forms: 'SpinMagIC GmbH i.G.' -> 'SpinMagIC'."""
    cleaned = LEGAL_FORMS.sub(" ", name or "")
    cleaned = re.sub(r"\(\s*\)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -,.")


def first_word(name: str) -> str | None:
    """The first distinctive word (>= 4 letters, no stopword), or None."""
    for word in re.findall(r"[^\s\-_/]+", clean_name(name)):
        bare = word.strip(".,;:()")
        if len(_fold(bare)) >= 4 and bare.lower() not in STOPWORDS:
            return bare
    return None


def match_confidence(name: str, thema: str, recipient: str = "", executing: str = "") -> float:
    """0.9 name equals Thema, 0.7 name contained in Thema/recipient, 0.5 only the first word matched, 0 none."""
    key = _fold(clean_name(name))
    if not key:
        return 0.0
    folded_thema = _fold(thema)
    if key == folded_thema:
        return 0.9
    if key in folded_thema or key in _fold(recipient) or key in _fold(executing):
        return 0.7
    word = first_word(name)
    if word and (_fold(word) in folded_thema or _fold(word) in _fold(recipient)):
        return 0.5
    return 0.0


# --- lookup ---------------------------------------------------------------------------------------

def _quick_form(term: str) -> dict:
    return {"actionMode": "searchlist", "suche.detailSuche": "false", "suche.schnellSuche": "%" + term + "%",
            "suche.lfdVhb": "N", "suche.listrowpersite": str(ROWS_PER_PAGE)}


def _detail_form(term: str, institution: str) -> dict:
    return {"actionMode": "searchlist", "suche.detailSuche": "true", "suche.themaSuche[0]": "%" + term + "%",
            "suche.ZeSt": "ST", "suche.nameZeStSuche": "%" + institution + "%",
            "suche.lfdVhb": "N", "suche.listrowpersite": str(ROWS_PER_PAGE)}


def _search(fetch, form: dict, *, first_page: str | None = None) -> tuple[int, list[dict]]:
    """Run a search (or continue from an already fetched first page) and follow the pagination up to MAX_ROWS rows."""
    page = first_page if first_page is not None else fetch("POST", SEARCH_URL, encode_form(form))
    count, rows = parse_count(page), parse_rows(page)
    start = ROWS_PER_PAGE + 1
    while count > len(rows) and start <= min(count, MAX_ROWS):
        more = parse_rows(fetch("POST", SEARCH_URL, encode_form({**form, "suche.listrowfrom": str(start)})))
        if not more:
            break
        rows.extend(more)
        start += ROWS_PER_PAGE
    return count, rows


def _grant_from(detail: dict | None, row: dict | None) -> tuple[Grant, dict]:
    """Merge detail page (preferred) and result row into a Grant plus the facts used for the evidence."""
    d, r = detail or {}, row or {}
    pick = lambda k: d.get(k) or r.get(k) or ""
    fkz = pick("fkz")
    recipient, executing = pick("recipient"), pick("executing")
    full = recipient
    if executing and _fold(executing) != _fold(recipient):
        # "Universität Augsburg - Lehrstuhl X" already names the recipient; do not repeat it.
        repeats = bool(recipient) and _fold(executing).startswith(_fold(recipient))
        full = executing if repeats or not recipient else recipient + ", " + executing
    start, end = d.get("start") or r.get("start"), d.get("end") or r.get("end")
    amount = d.get("amount") if d.get("amount") is not None else r.get("amount")
    grant = Grant(programme=programme_for(fkz, d.get("leistungsplan", "")), reference=fkz or None, recipient=full or None,
                  amount_eur=amount, start=start, end=end, url=detail_url(fkz))
    facts = {"fkz": fkz, "thema": pick("thema"), "recipient": recipient, "executing": executing, "start": start, "end": end,
             "amount": amount, "leistungsplan": d.get("leistungsplan", ""), "ort": d.get("executing_ort") or d.get("recipient_ort", "")}
    return grant, facts


def _record(lookup: Lookup, grant: Grant, facts: dict) -> None:
    fmt = lambda x: x.strftime("%d.%m.%Y") if x else "?"
    summe = ("%s €" % format(facts["amount"], ",").replace(",", ".")) if facts["amount"] is not None else "?"
    text = "Thema: %s; Förderempfänger: %s; Ausführende Stelle: %s; Laufzeit: %s bis %s; Summe: %s" % (
        facts["thema"] or "?", facts["recipient"] or "?", facts["executing"] or "?", fmt(facts["start"]), fmt(facts["end"]), summe)
    if facts.get("leistungsplan"):
        text += "; Leistungsplansystematik: " + facts["leistungsplan"]
    url = str(grant.url)
    lookup.signals.append(SourceSignal(source=SOURCE, type="exist_projekt" if is_exist(facts["fkz"], facts["leistungsplan"]) else "foerderprojekt",
                                       url=url, date=facts["start"], evidence=text[:2000]))
    lookup.evidence.append(Evidence(field="grants", url=url, source=SOURCE, source_date=facts["start"],
                                    finding=("%s %s: %s" % (grant.programme, facts["fkz"], text))[:1000]))


def grant_lookup(name: str, *, institution: str | None, reference: str | None, cache, fetch=None) -> tuple[list[Grant], Lookup]:
    """Return the grants of a project/company from the Förderkatalog plus the Lookup with evidence and signals.

    `reference` is an FKZ (exact lookup, confidence 1.0); otherwise the name is searched (quick search,
    narrowed by `institution` when ambiguous) and the best rows (max. 3) are resolved via their detail page.
    Never raises; failures land in Lookup.errors.
    """
    lookup = Lookup()
    grants: list[Grant] = []
    run = _cached_fetch(fetch or Session().fetch, cache)
    try:
        best = 0.0
        if reference:
            ref = reference.strip()
            detail = parse_detail(run("GET", detail_url(ref)))
            if detail.get("fkz"):
                grant, facts = _grant_from(detail, None)
                grants.append(grant)
                _record(lookup, grant, facts)
                best = 1.0
            else:
                lookup.errors.append("foekat: FKZ %s nicht gefunden" % ref)
        if not grants and (name or "").strip():
            term = clean_name(name)
            form = _quick_form(term)
            page = run("POST", SEARCH_URL, encode_form(form)) if term else ""
            count, rows = parse_count(page), parse_rows(page)
            if count == 0:
                word = first_word(name)
                if word and _fold(word) != _fold(term):
                    form = _quick_form(word)
                    page = run("POST", SEARCH_URL, encode_form(form))
                    count, rows = parse_count(page), parse_rows(page)
            narrowed = []
            if count > AMBIGUOUS and institution and institution.strip():
                narrowed_count, narrowed = _search(run, _detail_form(term, institution.strip()))
                if narrowed:
                    count, rows = narrowed_count, narrowed
            if not narrowed and count > len(rows):
                count, rows = _search(run, form, first_page=page)
            scored = [(match_confidence(name, r["thema"], r["recipient"], r["executing"]), i, r) for i, r in enumerate(rows)]
            scored = sorted((t for t in scored if t[0] > 0), key=lambda t: (-t[0], t[1]))
            if count == 0:
                lookup.errors.append("foekat: keine Treffer")
            elif not scored:
                lookup.errors.append("foekat: mehrdeutig (%d Treffer)" % count if count > AMBIGUOUS else "foekat: keine Treffer")
            elif count > AMBIGUOUS and (scored[0][0] < 0.9 or len(scored) > MAX_DETAILS):
                lookup.errors.append("foekat: mehrdeutig (%d Treffer)" % count)
            seen = set()
            for confidence, _, row in scored:
                if len(grants) >= MAX_DETAILS or row["fkz"] in seen:
                    continue
                seen.add(row["fkz"])
                try:
                    detail = parse_detail(run("GET", detail_url(row["fkz"])))
                except FoekatError as exc:
                    lookup.errors.append("foekat: %s" % exc)
                    detail = {}
                grant, facts = _grant_from(detail if detail.get("fkz") else None, row)
                grants.append(grant)
                _record(lookup, grant, facts)
                best = max(best, confidence)
        if grants:
            first = grants[0]
            executing = next((f for f in lookup.signals), None)
            unit = re.search(r"Ausführende Stelle: (.*?); Laufzeit", executing.evidence).group(1) if executing else ""
            if unit and unit != "?":
                lookup.add("institution", unit, url=str(first.url), finding="Ausführende Stelle: " + unit, source=SOURCE, source_date=first.start)
            lookup.add("match_confidence", best, url=str(first.url), source=SOURCE, source_date=first.start,
                       finding="Förderkatalog-Treffer %s für '%s' (Konfidenz %.1f)" % (first.reference, name, best))
    except FoekatError as exc:
        lookup.errors.append("foekat: %s" % exc)
    except Exception as exc:  # never let a parsing surprise abort the dossier
        logger.exception("foekat lookup failed for %r", name)
        lookup.errors.append("foekat: %s" % type(exc).__name__)
    return grants, lookup
