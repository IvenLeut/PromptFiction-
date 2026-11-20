"""Regression tests for the sourcing/foekat_export.py review fixes (offline: injected fetch, no network).

Request budget, no split on surplus FKZ, session re-prime on HTML export, encode errors, required columns,
size-cap detection, hit-count parsing, ExportResult reporting fields (and their survival through the cache),
plus the parsing fixes for BOM, quoted line breaks, NEL bytes, doubled quotes, small negatives and
header-only exports. Fixture rows come from tests/fixtures/sourcing/ (recorded live, see test_sourcing_foekat.py).
"""
import ast
import re
import urllib.parse
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import sourcing.foekat_export as fx
from context.cache import Cache
from context.foekat import SEARCH_URL, FoekatError

FIXTURES = Path(__file__).parent / "fixtures" / "sourcing"
CLOCK = lambda: datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ENC = "iso-8859-15"


def csv_bytes(prefix="03EF"):
    return (FIXTURES / ("foekat_export_%s.csv" % prefix)).read_bytes()


def page(count):
    text = (FIXTURES / "foekat_result_03EF.html").read_bytes().decode(ENC)
    return re.sub(r"\d+ Treffer insgesamt", "%d Treffer insgesamt" % count, text)


def lines_for(prefix):
    lines = csv_bytes(prefix[:4]).split(b"\n")
    return lines[0], [l for l in lines[1:] if l and l[2:].decode(ENC).startswith(prefix)]


class Fetch:
    """POST -> result page with the fixture count for the prefix (or `counts`), GET -> CSV of that prefix.
    `exports[prefix]` may be a list: successive GETs pop from it (simulates an expired then fresh session)."""

    def __init__(self, counts=None, exports=None, csv_error=None, with_reset=False):
        self.counts, self.exports, self.csv_error = counts or {}, exports or {}, csv_error
        self.calls, self.last, self.resets = [], None, 0
        if with_reset:
            self.reset = self._reset

    def _reset(self):
        self.resets += 1

    def __call__(self, method, url, data=None):
        self.calls.append((method, url))
        if method == "POST":
            assert url == SEARCH_URL
            self.last = dict(urllib.parse.parse_qsl(data.decode("ascii"), encoding=ENC))["suche.fkzSuche[0]"].rstrip("%")
            return page(self.counts.get(self.last, len(lines_for(self.last)[1])))
        assert url == fx.CSV_URL
        if self.csv_error is not None:
            raise self.csv_error
        answer = self.exports.get(self.last)
        if isinstance(answer, list):
            answer = answer.pop(0) if answer else None
        if answer is not None:
            return answer
        header, body = lines_for(self.last)
        return header + b"\n" + b"".join(l + b"\n" for l in body)


HTML = "<!DOCTYPE html><html><body>Sitzung abgelaufen</body></html>"


# --- 1. request budget, no split on surplus ----------------------------------------------------------

def test_budget_exhausted_raises_typed_error_with_counts():
    fetch = Fetch(counts={"03EF": 20, "03EFB": 99, "03EFN": 99})   # children keep disagreeing -> depth 2 fan-out
    with pytest.raises(fx.BudgetExhaustedError) as info:
        fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    exc = info.value
    assert isinstance(exc, fx.ExportError)
    assert len(fetch.calls) == exc.requests == exc.budget == fx.DEFAULT_BUDGET == 60
    assert exc.queries > 0 and exc.result.requests == 60 and "60 von 60" in str(exc)


def test_budget_is_configurable_and_checked_before_every_call():
    fetch = Fetch()
    with pytest.raises(fx.BudgetExhaustedError):
        fx.export_rows(("03EF", "03EG"), fetch=fetch, cache=None, clock=CLOCK, budget=3)
    assert len(fetch.calls) == 3                                   # the 4th request was never sent
    result = fx.export_rows(("03EF", "03EG"), fetch=Fetch(), cache=None, clock=CLOCK, budget=4)
    assert result.complete and result.requests == 4 and result.budget == 4
    with pytest.raises(ValueError):
        fx.export_rows(fetch=Fetch(), cache=None, budget=0)


def test_cache_hits_cost_no_budget(tmp_path):
    cache = Cache(tmp_path / "c.db")
    fx.export_rows(fetch=Fetch(), cache=cache, clock=CLOCK)
    again = fx.export_rows(fetch=lambda *a: pytest.fail("network"), cache=cache, clock=CLOCK, budget=1)
    assert again.requests == 0 and len(again.rows) == 45


def test_more_fkz_than_server_count_is_not_split():
    fetch = Fetch(counts={"03EF": 18})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert fetch.calls == [("POST", SEARCH_URL), ("GET", fx.CSV_URL)]
    assert result.complete is False and len(result.rows) == 19 and not result.queries[0].split
    assert any("19 FKZ, Server meldet 18" in w for w in result.warnings)
    assert any("keine Aufteilung" in w for w in result.warnings)


def test_fewer_fkz_still_splits_within_budget():
    header, body = lines_for("03EF")
    fetch = Fetch(exports={"03EF": header + b"\n" + b"\n".join(body[:10]) + b"\n"})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete and len(result.rows) == 19 and result.requests == len(fetch.calls) <= 60


# --- 2. expired session ------------------------------------------------------------------------------

def test_html_export_reprimes_session_and_retries_once():
    fetch = Fetch(exports={"03EF": [HTML]}, with_reset=True)      # first export HTML, second the real CSV
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete and len(result.rows) == 19 and fetch.resets == 1
    assert fetch.calls == [("POST", SEARCH_URL), ("GET", fx.CSV_URL)] * 2
    assert result.requests == 5                                     # 4 calls + the re-prime of the session
    assert any("Sitzung erneuert" in w for w in result.warnings)


def test_html_export_twice_raises_after_one_retry():
    fetch = Fetch(exports={"03EF": HTML}, with_reset=True)
    with pytest.raises(fx.NotCsvError):
        fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert fetch.resets == 1 and len(fetch.calls) == 4


def test_retry_also_works_without_reset_hook():
    fetch = Fetch(exports={"03EF": [HTML]})
    assert fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK).complete
    assert len(fetch.calls) == 4


def test_lazy_session_reset_opens_a_fresh_session(monkeypatch):
    opened = []

    class FakeSession:
        def __init__(self):
            opened.append(self)
            self.inner = Fetch(exports={"03EF": [HTML]})
            if len(opened) > 1:
                self.inner = Fetch()

        def fetch(self, method, url, data=None):
            return self.inner(method, url, data)
    monkeypatch.setattr(fx, "Session", FakeSession)
    result = fx.export_rows(("03EF",), cache=None, clock=CLOCK)
    assert result.complete and len(opened) == 2


# --- 3. encode errors --------------------------------------------------------------------------------

def test_text_export_with_unencodable_characters_is_replaced_and_flagged():
    text = csv_bytes().decode(ENC).replace("HoCHQuant", "HoCH…Quant中")
    result = fx.export_rows(("03EF",), fetch=Fetch(exports={"03EF": text}), cache=None, clock=CLOCK)
    assert result.complete and any(r.thema == "HoCH?Quant?" for r in result.rows)
    assert any("ISO-8859-15" in w for w in result.warnings)


# --- 4. required columns -----------------------------------------------------------------------------

@pytest.mark.parametrize("column", ["Laufzeit bis", "Förder- / Auftragssumme (Anteil des Bundes) in EUR", "Staat"])
def test_missing_required_column_raises_naming_it(column):
    raw = csv_bytes()
    header, rest = raw.split(b"\n", 1)
    renamed = header.replace(('="%s"' % column).encode(ENC), b'="Umbenannt"')
    assert renamed != header
    with pytest.raises(fx.MissingColumnError) as info:
        fx.parse_export(renamed + b"\n" + rest)
    assert isinstance(info.value, fx.ExportError) and isinstance(info.value, fx.NotCsvError)
    assert any(column in c for c in info.value.columns) and column in str(info.value)


def test_required_columns_list():
    for column in ("Laufzeit bis", fx.AMOUNT_COL, "Staat (Förderempfänger)", "Staat (Ausführende Stelle)"):
        assert column in fx.REQUIRED


# --- 5. too-large detection --------------------------------------------------------------------------

class SizeLimitExceeded(Exception):
    pass


class Flagged(FoekatError):
    too_large = True


@pytest.mark.parametrize("exc", [
    FoekatError("Antwort größer als 3000000 Bytes"), FoekatError("Antwort groesser als 3000000 Bytes"),
    FoekatError("response too large"), FoekatError("HTTP 413"), Flagged("x"), SizeLimitExceeded("x"),
])
def test_too_large_detection_variants(exc):
    assert fx.is_too_large(exc)
    result = fx.export_rows(("03EG",), fetch=SplitOnTop(exc), cache=None, clock=CLOCK)
    assert result.complete and len(result.rows) == 26 and any("Größengrenze" in w for w in result.warnings)


@pytest.mark.parametrize("exc", [FoekatError("HTTP 502"), FoekatError("URLError"), FoekatError("TimeoutError")])
def test_other_transport_errors_are_not_too_large(exc):
    assert not fx.is_too_large(exc)
    with pytest.raises(fx.ExportNetworkError):
        fx.export_rows(("03EG",), fetch=Fetch(csv_error=exc), cache=None, clock=CLOCK)


class SplitOnTop(Fetch):
    """Raises `exc` for the top-level export only; sub-prefix exports succeed."""

    def __init__(self, exc):
        super().__init__()
        self.exc = exc

    def __call__(self, method, url, data=None):
        if method == "GET" and self.last == "03EG":
            raise self.exc
        return super().__call__(method, url, data)


# --- 6. hit count ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, count", [
    ("Suchergebnis. 1.234 Treffer insgesamt", 1234), ("1,234 treffer insgesamt", 1234),
    ("12.345.678 TREFFER INSGESAMT", 12345678), ("1 234 Treffer insgesamt", 1234),
    ("7 Treffer Insgesamt", 7), ("keine treffer", 0), ("KEINE TREFFER.", 0),
])
def test_parse_hit_count_separators_and_case(text, count):
    assert fx.parse_hit_count(text) == count


# --- 7. imports and shim -----------------------------------------------------------------------------

def test_no_unused_imports_and_shim_still_works():
    tree = ast.parse(Path(fx.__file__).read_text(encoding="utf-8"))
    imported = {(a.asname or a.name).split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom)) and getattr(node, "module", "") != "__future__"
                for a in node.names}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
           {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    assert imported - used == set()
    assert fx.build_leads and fx.run and fx.Industry and fx.RawLead   # resolved through the mapping shim
    with pytest.raises(AttributeError):
        fx.does_not_exist


# --- 8. reporting fields and caching -----------------------------------------------------------------

def test_result_reports_requests_prefixes_and_retrieval_time(tmp_path):
    cache = Cache(tmp_path / "c.db")
    first = fx.export_rows(fetch=Fetch(), cache=cache, clock=CLOCK)
    assert (first.requests, first.budget, first.complete, first.warnings) == (4, 60, True, [])
    assert first.prefixes == {"03EF": {"server_count": 19, "unique_fkz": 19, "collected_fkz": 19, "kept": 19, "complete": True},
                              "03EG": {"server_count": 26, "unique_fkz": 26, "collected_fkz": 26, "kept": 26, "complete": True}}
    assert first.retrieved_at == CLOCK()
    later = lambda: datetime(2031, 1, 1, tzinfo=timezone.utc)
    cached = fx.export_rows(fetch=lambda *a: pytest.fail("network"), cache=cache, clock=later)
    assert cached.retrieved_at == CLOCK() and cached.requests == 0 and cached.prefixes == first.prefixes
    assert all(q.from_cache and q.retrieved_at == CLOCK() for q in cached.queries)
    d = cached.as_dict()
    assert d["retrieved_at"] == CLOCK().isoformat() and d["requests"] == 0 and d["budget"] == 60
    assert d["prefixes"]["03EG"]["server_count"] == 26 and d["complete"] is True


def test_export_warnings_survive_the_cache(tmp_path):
    cache = Cache(tmp_path / "c.db")
    first = fx.export_rows(("03EF",), fetch=Fetch(exports={"03EF": [HTML]}), cache=cache, clock=CLOCK)
    cached = fx.export_rows(("03EF",), fetch=lambda *a: pytest.fail("network"), cache=cache, clock=CLOCK)
    assert [w for w in cached.warnings if "Sitzung" in w] == [w for w in first.warnings if "Sitzung" in w] != []


# --- additional parsing fixes ------------------------------------------------------------------------

def test_small_negative_amount_keeps_sign():
    assert fx.format_euro(Decimal("-0.50")) == "-0,50 €" and fx.format_euro(Decimal("-0.001")) == "0,00 €"
    assert fx.format_euro(Decimal("-1234.5")) == "-1.234,50 €"


def test_utf8_bom_bytes_are_dropped():
    assert fx.parse_export(b"\xef\xbb\xbf" + csv_bytes())[0]["FKZ"] == "03EFBB0063"


def test_line_break_and_nel_inside_wrapper_keep_one_row():
    for inner in (b"HoCH\nQuant", b"HoCH\r\nQuant", b"HoCH\x85Quant"):
        rows = fx.parse_export(csv_bytes().replace(b'="HoCHQuant"', b'="' + inner + b'"'))
        assert len(rows) == 19 and rows[0]["FKZ"] == "03EFBB0063"
    assert len(fx.parse_export(csv_bytes().replace(b"\n", b"\r\n"))) == 19


def test_doubled_quotes_are_undoubled_and_do_not_end_the_cell():
    assert [fx.unwrap(c) for c in fx.split_line('="Projekt ""Alpha""; Beta";="x";')] == ['Projekt "Alpha"; Beta', "x", ""]
    assert fx.unwrap('="a "quoted" b"') == 'a "quoted" b' and fx.unwrap('=""') == ""


def test_header_only_export_with_hits_is_empty_export(tmp_path):
    header = csv_bytes().split(b"\n")[0] + b"\n"
    cache = Cache(tmp_path / "c.db")
    with pytest.raises(fx.EmptyExportError):
        fx.export_rows(("03EF",), fetch=Fetch(exports={"03EF": header}), cache=cache, clock=CLOCK)
    assert fx.export_rows(("03EF",), fetch=Fetch(), cache=cache, clock=CLOCK).requests == 2   # nothing cached
