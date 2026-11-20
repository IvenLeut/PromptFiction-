"""Step 1 sourcing from the Förderkatalog des Bundes: EXIST projects via the catalogue's CSV export.

Approach after technologiestiftung/udb-foerderkatalog-scraper
(https://github.com/technologiestiftung/udb-foerderkatalog-scraper, MIT licence, (c) 2026 Technologiestiftung
Berlin): instead of paginating the HTML result list we run one detail search per programme and download the
catalogue's own CSV export of that result list, validate its row count against the hit count the server
prints on the result page and clean the cells. Re-implemented here in our style (no code vendored).

Request sequence (verified live on 2026-11-20, see sourcing/FOEKAT.md):
  1. GET  StartAction.do                              -> session cookie JSESSIONID (context.foekat.Session)
  2. POST SucheAction.do  actionMode=searchlist, suche.detailSuche=true, suche.fkzSuche[0]=03EF%,
          suche.laufzeitVonSuche[0]=01.01.2024 (= project start >= date), suche.lfdVhb=N (also finished
          projects), suche.nurVerbund=N, suche.ZeSt=ZE    -> HTML result page "<n> Treffer insgesamt"
  3. GET  SucheAction.do?actionMode=print&presentationType=csv -> CSV of the session's last result list

Every (search, export) pair is cached as one unit in `context.cache.Cache` together with its retrieval
time, so a rerun is byte-identical and touches no network. Tests inject `fetch(method, url, data)`
returning text (the result page) or bytes/text (the CSV).

Fallback: if the export has fewer/more distinct FKZ than the server reports (or exceeds the transport size
cap) the query is split by the next FKZ character (03EF -> 03EFA..03EFZ, 03EF0..03EF9), recursively, and
merged with a dedupe by FKZ. The scraper splits by calendar year instead, but on the live form
`laufzeitBisSuche` filters the project *end* (end <= date), so a von/bis year window only returns projects
that start and end within the same year and is not a partition of multi-year EXIST projects; an FKZ
prefix is. An unrepairable mismatch returns only validated rows and sets `complete=False` plus a warning.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from context.cache import Cache
from context.foekat import ENCODING, SEARCH_URL, FoekatError, Session, encode_form, parse_date

logger = logging.getLogger(__name__)

SOURCE_NAME = "Förderkatalog des Bundes"
SIGNAL_SOURCE = "Förderkatalog"            # same source label as the step-2 lookup (context.foekat.SOURCE)
SIGNAL_TYPE = "exist_projekt"              # step 2 never quotes/classifies this type (context/classify.py NO_QUOTE_TYPES)
CSV_URL = SEARCH_URL + "?actionMode=print&presentationType=csv"
PROGRAMMES = {"03EF": ("EXIST-Forschungstransfer", "exist_forschungstransfer"),
              "03EG": ("EXIST-Gründungsstipendium", "exist_gruendungsstipendium")}
DEFAULT_SINCE = date(2024, 1, 1)
CACHE_VERSION = "foekat-export:v1:"
SPLIT_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_SPLIT_DEPTH = 2
SIZE_ERROR = "Antwort größer als"          # context.foekat.Session size cap message (MAX_BYTES exceeded)
_SIZE_PATTERN = re.compile(r"gr(?:ö|oe)(?:ß|ss)er\s+als|too\s+large|zu\s+gro(?:ß|ss)|max(?:imum)?[_ ]?bytes", re.I)
DEFAULT_BUDGET = 60                        # network requests per export_rows call
ACADEMIC = re.compile(r"hochschul|universit|institut|akademie|academy|school|college|leibniz|fraunhofer|max-planck|"
                      r"helmholtz|forschung|research|zentrum|center|centre|klinik|charité|wissenschaft", re.I)
LEGAL_FORM = re.compile(r"(?<![\w])(GmbH|UG|AG|SE|KG|OHG|GbR|mbH)(?![\w])")  # gGmbH excluded on purpose


# --- errors ---------------------------------------------------------------------------------------

class ExportError(Exception):
    """Any failure of the catalogue export; step 1 raises instead of returning invented or partial data."""


class ExportNetworkError(ExportError):
    """Transport failure (HTTP error, timeout, connection) of the catalogue."""


class NotCsvError(ExportError):
    """The export URL answered with an HTML page (e.g. session expired) or an unknown table."""


class EmptyExportError(ExportError):
    """The server reported hits but the export contained no data rows."""


class ResultPageError(ExportError):
    """The search answered with a page that carries neither a hit count nor 'Keine Treffer'."""


class MissingColumnError(NotCsvError):
    """The export lacks a required column (form/format changed); `columns` names the missing ones."""

    def __init__(self, columns: list[str]):
        super().__init__("Unbekanntes Exportformat, Spalten fehlen: %s" % ", ".join(columns))
        self.columns = list(columns)


class BudgetExhaustedError(ExportError):
    """The request budget of one export_rows call is used up (runaway split fallback)."""

    def __init__(self, requests: int, budget: int, queries: int, rows: int):
        super().__init__("Anfragebudget erschöpft: %d von %d Anfragen, %d Abfragen, %d Zeilen bis dahin"
                         % (requests, budget, queries, rows))
        self.requests, self.budget, self.queries, self.rows = requests, budget, queries, rows


class _TooLarge(ExportError):
    def __init__(self, count: int):
        super().__init__("Export größer als die Transportgrenze")
        self.count = count


# --- cleaning -------------------------------------------------------------------------------------

_WRAPPER = re.compile(r'^="(.*)"$', re.S)
_DOUBLED = re.compile(r'(?:[^"]|"")*', re.S)   # Excel quote doubling: every quote inside the wrapper is doubled
_GEO = ("Gemeindekennziffer", "Stadt/Gemeinde", "Ort", "Bundesland", "Staat")
RECIPIENT_COL = "Förderempfänger /Auftragnehmer"
EXECUTING_COL = "Ausführende Stelle"
AMOUNT_COL = "Förder- / Auftragssumme (Anteil des Bundes) in EUR"
REQUIRED = ("FKZ", "Thema des geförderten Vorhabens", "Laufzeit von", "Laufzeit bis", AMOUNT_COL, RECIPIENT_COL,
            EXECUTING_COL, "Staat (Förderempfänger)", "Staat (Ausführende Stelle)")


def unwrap(cell: str) -> str:
    """Excel text wrapper '="03EFBB0063"' -> '03EFBB0063'; plain cells are only trimmed."""
    cell = (cell or "").strip()
    m = _WRAPPER.match(cell)
    if not m:
        return cell
    inner = m.group(1)
    if '""' in inner and _DOUBLED.fullmatch(inner):
        inner = inner.replace('""', '"')
    return inner.strip()


def parse_euro(text: str) -> Decimal | None:
    """German number '1.234.567,89' -> Decimal('1234567.89'); empty/invalid -> None."""
    raw = (text or "").replace("€", "").replace("EUR", "").strip()
    if not re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?", raw):
        return None
    try:
        return Decimal(raw.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def format_euro(value: Decimal | None) -> str:
    """Decimal('876964.00') -> '876.964,00 €' (the catalogue's own notation)."""
    if value is None:
        return "?"
    text = "%.2f" % value
    sign = "-" if text.startswith("-") and text.strip("-0.") else ""   # '-0.00' is zero, '-0.50' keeps its sign
    whole, _, cents = text.lstrip("-").partition(".")
    return "%s%s,%s €" % (sign, format(int(whole), ",").replace(",", "."), cents)


# A cell is '="..."' with Excel-doubled quotes (may span lines), else '="..."' up to the first quote before
# ';'/line end (single line, undoubled quotes), else plain text up to ';' or the line end.
_CELL = re.compile(r'="(?:[^"]|"")*"(?=;|\n|$)|="[^\n]*?"(?=;|\n|$)|[^;\n]*', re.S)


def split_records(text: str) -> list[list[str]]:
    """Split export text into records of raw cells: rows end at '\n' or '\r\n' only (never at NEL/U+2028
    or other str.splitlines() breaks) and never inside an '="..."' wrapper; cells end at ';'."""
    text = text.replace("\r\n", "\n")
    records, cells, pos, end = [], [], 0, len(text)
    while True:
        m = _CELL.match(text, pos)
        cells.append(m.group(0))
        pos = m.end()
        if pos >= end:
            break
        if text[pos] == ";":
            pos += 1
            continue
        records.append(cells)       # text[pos] == "\n"
        cells, pos = [], pos + 1
        if pos >= end:
            return records
    records.append(cells)
    return records


def split_line(line: str) -> list[str]:
    """Split one export line at ';' but never inside an '="..."' wrapper (a Thema may contain ';')."""
    return [cell for record in split_records(line.rstrip("\r")) for cell in record]


def decode_export(raw: bytes) -> str:
    """Export bytes are ISO-8859-15 (0xA4 = '€', not '¤'); a stray UTF-8 BOM is dropped."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode(ENCODING)
    return text[1:] if text.startswith("\ufeff") else text


def clean_header(cells: list[str]) -> list[str]:
    """Unwrap header cells and make the geo columns unambiguous.

    The export lists Gemeindekennziffer/Stadt/Gemeinde/Ort/Bundesland/Staat twice: after
    'Förderempfänger /Auftragnehmer' for the recipient and after 'Ausführende Stelle' for the executing unit.
    """
    header, owner = [], None
    for cell in cells:
        name = unwrap(cell)
        if name == RECIPIENT_COL:
            owner = "Förderempfänger"
        elif name == EXECUTING_COL:
            owner = "Ausführende Stelle"
        if name in _GEO and owner:
            name = "%s (%s)" % (name, owner)
        header.append(name)
    while header and not header[-1]:
        header.pop()                        # every line ends with ';' -> one empty trailing column
    return header


def parse_export(raw: bytes) -> list[dict]:
    """CSV export bytes -> list of cleaned dict rows (column names after `clean_header`)."""
    text = decode_export(raw)
    head = text.lstrip()[:512].lower()
    if head.startswith("<") or "<html" in head or "<!doctype" in head:
        raise NotCsvError("Export lieferte HTML statt CSV (Sitzung abgelaufen oder Formular geändert)")
    lines = [cells for cells in split_records(text) if any(c.strip() for c in cells)]
    if not lines:
        return []
    header = clean_header(lines[0])
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise MissingColumnError(missing)
    rows = []
    for line in lines[1:]:
        cells = [unwrap(c) for c in line][:len(header)]
        cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells)))
    return rows


@dataclass(frozen=True)
class GrantRow:
    """One cleaned catalogue row (verbatim strings plus parsed dates/amount)."""
    fkz: str
    thema: str
    recipient: str
    recipient_ort: str
    recipient_land: str
    recipient_staat: str
    executing: str
    executing_ort: str
    executing_land: str
    executing_staat: str
    start: date | None
    end: date | None
    amount: Decimal | None
    amount_text: str
    ressort: str
    lps_code: str
    lps_text: str
    foerderart: str
    projekt: str
    retrieved_at: datetime

    @classmethod
    def from_dict(cls, row: dict, retrieved_at: datetime) -> "GrantRow":
        g = lambda key: row.get(key, "").strip()
        return cls(
            fkz=g("FKZ").upper(), thema=g("Thema des geförderten Vorhabens"),
            recipient=g(RECIPIENT_COL), recipient_ort=g("Ort (Förderempfänger)"),
            recipient_land=g("Bundesland (Förderempfänger)"), recipient_staat=g("Staat (Förderempfänger)"),
            executing=g(EXECUTING_COL), executing_ort=g("Ort (Ausführende Stelle)"),
            executing_land=g("Bundesland (Ausführende Stelle)"), executing_staat=g("Staat (Ausführende Stelle)"),
            start=parse_date(g("Laufzeit von")), end=parse_date(g("Laufzeit bis")),
            amount=parse_euro(g(AMOUNT_COL)), amount_text=g(AMOUNT_COL),
            ressort=g("Ressort"), lps_code=g("Leistungsplansystematik"), lps_text=g("Klartext Leistungsplansystematik"),
            foerderart=g("Förderart"), projekt=g("Projekt"), retrieved_at=retrieved_at,
        )

    @property
    def prefix(self) -> str:
        return self.fkz[:4]

    @property
    def programme(self) -> str:
        return PROGRAMMES.get(self.prefix, ("EXIST", "exist"))[0]


# --- transport + cache ----------------------------------------------------------------------------

_HITS = re.compile(r"(\d{1,3}(?:[.,  ]\d{3})+|\d+)\s+Treffer\s+insgesamt", re.I)
_NO_HITS = re.compile(r"Keine\s+Treffer", re.I)


def parse_hit_count(page: str) -> int:
    """'Suchergebnis. 1.234 Treffer insgesamt' -> 1234; 'Keine Treffer' -> 0; anything else raises.

    Case-insensitive; '.', ',' and (narrow) no-break spaces are accepted as thousands separators."""
    m = _HITS.search(page or "")
    if m:
        return int(re.sub(r"\D", "", m.group(1)))
    if _NO_HITS.search(page or ""):
        return 0
    raise ResultPageError("Ergebnisseite ohne Trefferzahl (Formular geändert oder Fehlerseite)")


def search_form(prefix: str, since: date) -> dict:
    """Detail search: FKZ prefix, project start >= since, running and finished projects ('Nur lfd. Vorhaben: Nein')."""
    return {"actionMode": "searchlist", "suche.detailSuche": "true", "suche.fkzSuche[0]": prefix + "%",
            "suche.laufzeitVonSuche[0]": since.strftime("%d.%m.%Y"), "suche.lfdVhb": "N",
            "suche.nurVerbund": "N", "suche.ZeSt": "ZE"}


@dataclass
class Export:
    prefix: str
    count: int
    raw: bytes
    retrieved_at: datetime
    from_cache: bool
    warnings: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def is_too_large(exc: BaseException) -> bool:
    """Does `exc` mean "response exceeds the transport size cap"? context.foekat.Session signals this only by
    the message 'Antwort größer als <n> Bytes'; also accept an explicit attribute (`too_large`), an HTTP 413
    status, a size-named exception type and English/transliterated wordings, so a reworded message or a
    dedicated exception class in a later context.foekat still triggers the split instead of a network error."""
    if getattr(exc, "too_large", False) is True:
        return True
    if any(getattr(exc, attr, None) == 413 for attr in ("code", "status", "status_code")):
        return True
    names = [cls.__name__.lower() for cls in type(exc).__mro__]
    if any("toolarge" in n or "toobig" in n or "sizelimit" in n or "sizeerror" in n for n in names):
        return True
    text = str(exc)
    return text.startswith(SIZE_ERROR) or bool(_SIZE_PATTERN.search(text)) or text.strip() == "HTTP 413"


def _as_bytes(body, prefix: str, warnings: list[str]) -> bytes:
    """CSV body as ISO-8859-15 bytes. A text body (the Session decodes with the server's charset) may hold
    characters ISO-8859-15 cannot represent; they become '?' and the export is flagged instead of crashing."""
    if isinstance(body, bytes):
        return body
    try:
        return body.encode(ENCODING)
    except UnicodeEncodeError:
        warnings.append("%s%%: Export enthält Zeichen außerhalb ISO-8859-15, durch '?' ersetzt" % prefix)
        return body.encode(ENCODING, errors="replace")


def _search_and_export(prefix: str, form: dict, fetch, warnings: list[str]) -> tuple[int, bytes]:
    try:
        page = fetch("POST", SEARCH_URL, encode_form(form))
        if isinstance(page, bytes):
            page = page.decode(ENCODING, errors="replace")
        count = parse_hit_count(page)
        raw = b""
        if count:
            try:
                body = fetch("GET", CSV_URL, None)
            except ExportError:
                raise
            except Exception as exc:
                if is_too_large(exc):
                    raise _TooLarge(count) from exc
                raise
            raw = _as_bytes(body, prefix, warnings)
    except FoekatError as exc:
        raise ExportNetworkError("Förderkatalog nicht erreichbar (%s, Abfrage %s%%)" % (exc, prefix)) from exc
    if count and not raw.strip():
        raise EmptyExportError("Server meldet %d Treffer für %s%%, der Export ist leer" % (count, prefix))
    if count and not parse_export(raw):  # raises NotCsvError before anything is cached
        raise EmptyExportError("Server meldet %d Treffer für %s%%, der Export hat nur die Kopfzeile" % (count, prefix))
    return count, raw


def fetch_export(prefix: str, since: date, *, fetch, cache: Cache | None, clock=_now) -> Export:
    """Search + CSV export for one FKZ prefix, cached as one unit with its retrieval time.

    If the export answers with HTML or an unknown table (typically an expired session), the session is
    re-primed once (`fetch.reset()` when the fetch has one, e.g. the lazy catalogue session) and search +
    export are repeated once; a second failure raises."""
    form = search_form(prefix, since)
    key = CACHE_VERSION + hashlib.sha1(json.dumps(form, sort_keys=True).encode("utf-8")).hexdigest()
    hit = cache.get(key) if cache is not None else None
    if hit is not None:
        return Export(prefix, int(hit["count"]), base64.b64decode(hit["csv_b64"]),
                      datetime.fromisoformat(hit["retrieved_at"]), True, list(hit.get("warnings", [])))
    warnings: list[str] = []
    try:
        count, raw = _search_and_export(prefix, form, fetch, warnings)
    except NotCsvError as first:
        reset = getattr(fetch, "reset", None)
        if callable(reset):
            reset()
        logger.info("Förderkatalog %s%%: %s; Sitzung neu, Wiederholung", prefix, first)
        warnings = ["%s%%: Export lieferte kein CSV (%s); Sitzung erneuert und wiederholt" % (prefix, first)]
        count, raw = _search_and_export(prefix, form, fetch, warnings)
    retrieved = clock()
    if cache is not None:
        cache.set(key, {"form": form, "count": count, "csv_b64": base64.b64encode(raw).decode("ascii"),
                        "retrieved_at": retrieved.isoformat(), "warnings": warnings})
    logger.info("Förderkatalog %s%%: %d Treffer, %d Bytes Export", prefix, count, len(raw))
    return Export(prefix, count, raw, retrieved, False, warnings)


# --- validated collection with fallback -----------------------------------------------------------

@dataclass
class QueryStat:
    query: str
    server_count: int | None
    exported_rows: int
    unique_fkz: int
    validated: bool
    split: bool = False
    retrieved_at: datetime | None = None
    from_cache: bool = False

    def as_dict(self) -> dict:
        return {"query": self.query + "%", "server_count": self.server_count, "exported_rows": self.exported_rows,
                "unique_fkz": self.unique_fkz, "validated": self.validated, "split": self.split,
                "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None}


@dataclass
class ExportResult:
    rows: list[GrantRow] = field(default_factory=list)
    complete: bool = True
    warnings: list[str] = field(default_factory=list)
    queries: list[QueryStat] = field(default_factory=list)
    fetches: int = 0                # network exports (0 when everything came from the cache)
    requests: int = 0               # network requests made by this call (search, export, session re-prime)
    budget: int = DEFAULT_BUDGET    # request cap of this call
    retrieved_at: datetime | None = None   # oldest retrieval time of the data used (the original one if cached)
    prefixes: dict[str, dict] = field(default_factory=dict)  # top prefix -> server count vs unique FKZ

    def as_dict(self) -> dict:
        return {"complete": self.complete, "rows": len(self.rows), "requests": self.requests, "budget": self.budget,
                "fetches": self.fetches,
                "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
                "prefixes": {p: dict(v) for p, v in self.prefixes.items()},
                "queries": [q.as_dict() for q in self.queries], "warnings": list(self.warnings)}


class _Metered:
    """Counts network requests against the result's budget; checked before every call."""

    def __init__(self, fetch, result: ExportResult):
        self.fetch, self.result = fetch, result

    def _spend(self) -> None:
        r = self.result
        if r.requests >= r.budget:
            exc = BudgetExhaustedError(r.requests, r.budget, len(r.queries),
                                       sum(q.unique_fkz for q in r.queries if q.validated))
            exc.result = r
            raise exc
        r.requests += 1

    def __call__(self, method, url, data=None):
        self._spend()
        return self.fetch(method, url, data)

    def reset(self) -> None:
        inner = getattr(self.fetch, "reset", None)
        if callable(inner):
            self._spend()           # the fresh session's StartAction request
            inner()


def _dedupe(rows: list[GrantRow], result: ExportResult) -> list[GrantRow]:
    by_fkz: dict[str, GrantRow] = {}
    for row in rows:
        seen = by_fkz.get(row.fkz)
        if seen is None:
            by_fkz[row.fkz] = row
        elif (seen.thema, seen.start, seen.amount_text) != (row.thema, row.start, row.amount_text):
            result.warnings.append("FKZ %s mehrfach mit abweichenden Angaben; erste Zeile behalten" % row.fkz)
    return list(by_fkz.values())


def _collect(prefix: str, since: date, depth: int, result: ExportResult, *, fetch, cache, clock) -> tuple[list[GrantRow], bool]:
    retrieved, from_cache = None, False
    try:
        export = fetch_export(prefix, since, fetch=fetch, cache=cache, clock=clock)
        result.fetches += 0 if export.from_cache else 1
        result.warnings.extend(export.warnings)
        retrieved, from_cache = export.retrieved_at, export.from_cache
        if result.retrieved_at is None or retrieved < result.retrieved_at:
            result.retrieved_at = retrieved
        parsed = parse_export(export.raw) if export.count else []
        rows = _dedupe([GrantRow.from_dict(r, export.retrieved_at) for r in parsed], result)
        exported, count = len(parsed), export.count
    except _TooLarge as big:
        rows, exported, count = [], 0, big.count
        result.warnings.append("%s%%: Export überschreitet die Größengrenze (%d Treffer)" % (prefix, count))
    stat = QueryStat(prefix, count, exported, len(rows), len(rows) == count, retrieved_at=retrieved,
                     from_cache=from_cache)
    result.queries.append(stat)
    if stat.validated:
        return rows, True
    if exported:
        result.warnings.append("%s%%: Export enthält %d FKZ, Server meldet %d Treffer" % (prefix, len(rows), count))
    if exported and len(rows) > count:
        # more distinct FKZ than hits: a split can only reproduce the surplus, so keep the export as is
        result.warnings.append("%s%%: mehr FKZ als Treffer, keine Aufteilung; Export ungeprüft übernommen, "
                               "Ergebnis unvollständig" % prefix)
        return rows, False
    if depth >= MAX_SPLIT_DEPTH:
        result.warnings.append("%s%%: nicht reparierbar (maximale Aufteilungstiefe), %d Zeilen verworfen" % (prefix, len(rows)))
        return [], False
    stat.split = True
    merged, ok = [], True
    for char in SPLIT_ALPHABET:
        child_rows, child_ok = _collect(prefix + char, since, depth + 1, result, fetch=fetch, cache=cache, clock=clock)
        merged.extend(child_rows)
        ok = ok and child_ok
    merged = _dedupe(merged, result)
    if ok and len(merged) == count:
        result.warnings.append("%s%%: durch Aufteilung nach FKZ-Präfix repariert (%d Treffer)" % (prefix, count))
        return merged, True
    result.warnings.append("%s%%: Aufteilung ergibt %d von %d Treffern; Ergebnis unvollständig" % (prefix, len(merged), count))
    return merged, False


def _lazy_session():
    """One catalogue session for the whole run, opened only when the cache misses; `reset()` drops it so the
    next request opens a fresh session (new JSESSIONID via StartAction.do)."""
    holder = []

    def fetch(method, url, data=None):
        if not holder:
            holder.append(Session())
        return holder[0].fetch(method, url, data)

    fetch.reset = holder.clear
    return fetch


def export_rows(prefixes=("03EF", "03EG"), since: date = DEFAULT_SINCE, *, fetch=None, cache: Cache | None = None,
                clock=_now, budget: int = DEFAULT_BUDGET) -> ExportResult:
    """All validated catalogue rows for the FKZ prefixes with project start >= since.

    At most `budget` network requests are made (cache hits are free); BudgetExhaustedError when exceeded.
    Raises ExportError subclasses on network errors, HTML-instead-of-CSV, missing columns and empty exports.
    """
    if budget < 1:
        raise ValueError("budget muss mindestens 1 sein")
    result = ExportResult(budget=budget)
    run = _Metered(fetch or _lazy_session(), result)
    rows: list[GrantRow] = []
    for prefix in prefixes:
        first = len(result.queries)
        found, ok = _collect(prefix, since, 0, result, fetch=run, cache=cache, clock=clock)
        result.complete = result.complete and ok
        kept = 0
        for row in found:
            if not row.fkz.startswith(prefix):
                result.warnings.append("%s: FKZ passt nicht zum Präfix %s, verworfen" % (row.fkz, prefix))
            elif row.start is None or row.start < since:
                result.warnings.append("%s: Laufzeitbeginn %s vor %s, verworfen" % (row.fkz, row.start, since))
            else:
                rows.append(row)
                kept += 1
        top = result.queries[first]
        result.prefixes[prefix] = {"server_count": top.server_count, "unique_fkz": top.unique_fkz,
                                   "collected_fkz": len(found), "kept": kept, "complete": ok}
    result.rows = _dedupe(rows, result)
    for warning in result.warnings:
        logger.warning("Förderkatalog: %s", warning)
    return result


def __getattr__(name):
    """Backwards compatibility: mapping names moved to sourcing/mapping.py."""
    import sourcing.mapping as mapping
    if hasattr(mapping, name):
        return getattr(mapping, name)
    raise AttributeError(name)
