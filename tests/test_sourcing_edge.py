"""Edge-case and robustness tests for step-1 sourcing (sourcing/foekat_export.py, sourcing/mapping.py,
sourcing/engine.py, sourcing/__main__.py). All offline: `fetch` is injected, the cache is None or a tmp_path
Cache. Synthetic rows are built from the real recorded header in tests/fixtures/sourcing/ and marked as such.

Regression tests for fixed parser defects (sign of small negatives, Excel quote doubling, UTF-8 BOM,
line breaks/NEL inside wrapped cells, header-only exports) are plain tests.
"""
import json
import random
import re
import urllib.parse
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path

import pytest
from pydantic import TypeAdapter

import sourcing.foekat_export as fx
import sourcing.mapping as mp
from context.cache import Cache, NoCache
from context.foekat import SEARCH_URL, FoekatError, detail_url
from models import Industry, RawLead, SearchCriteria
from pipeline import discover
from sourcing.engine import SourcingError, search

FIXTURES = Path(__file__).parent / "fixtures" / "sourcing"
CLOCK = lambda: datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
ENC = "iso-8859-15"
THEMA = "Thema des geförderten Vorhabens"
AMOUNT = "Förder- / Auftragssumme (Anteil des Bundes) in EUR"


def fixture_bytes(prefix):
    return (FIXTURES / ("foekat_export_%s.csv" % prefix)).read_bytes()


def fixture_page(prefix="03EF"):
    return (FIXTURES / ("foekat_result_%s.html" % prefix)).read_bytes().decode(ENC)


HEADER_LINE = fixture_bytes("03EF").split(b"\n")[0]
HEADER_RAW = [fx.unwrap(c) for c in fx.split_line(HEADER_LINE.decode(ENC))][:-1]   # 26 raw names, with duplicates
FIRST_ROW = fx.parse_export(fixture_bytes("03EF"))[0]                                 # real row 03EFBB0063


def page(count):
    if count == 0:
        return re.sub(r'aria-label="Suchergebnis\. \d+ Treffer insgesamt[^"]*"',
                      'aria-label="Suchergebnis. Keine Treffer."', fixture_page())
    return re.sub(r"\d+ Treffer insgesamt", "%d Treffer insgesamt" % count, fixture_page())


def line(values: list[str]) -> bytes:
    """One export line in the catalogue's notation (every cell wrapped, trailing ';'). Amount stays plain."""
    cells = [v if i == HEADER_RAW.index(AMOUNT) else '="%s"' % v for i, v in enumerate(values)]
    return (";".join(cells) + ";").encode(ENC)


def synth_row(**changes) -> list[str]:
    """Synthetic row: the real first fixture row with some fields replaced (positional, raw header order)."""
    values = []
    owner = None
    for name in HEADER_RAW:
        if name == fx.RECIPIENT_COL:
            owner = "Förderempfänger"
        elif name == fx.EXECUTING_COL:
            owner = "Ausführende Stelle"
        key = "%s (%s)" % (name, owner) if name in ("Gemeindekennziffer", "Stadt/Gemeinde", "Ort", "Bundesland", "Staat") else name
        values.append(changes.get(key, FIRST_ROW[key]))
    return values


def export(*rows: list[str]) -> bytes:
    return HEADER_LINE + b"\n" + b"".join(line(r) + b"\n" for r in rows)


def body_lines(prefix):
    lines = fixture_bytes(prefix[:4]).split(b"\n")
    return [l for l in lines[1:] if l and l[2:].decode(ENC).startswith(prefix)]


class Fetch:
    """Catalogue emulation. Default: the fixture rows whose FKZ starts with the searched prefix, and a hit count
    that equals their number. `counts`/`exports` override per prefix; `count_fn(prefix, n)` overrides all."""

    def __init__(self, counts=None, exports=None, count_fn=None, body=None):
        self.counts, self.exports, self.count_fn, self.body = counts or {}, exports or {}, count_fn, body
        self.calls, self.queries, self.last = [], [], None

    def lines(self, prefix):
        if self.body is not None:
            return [l for l in self.body if l[2:].decode(ENC).startswith(prefix)]
        return body_lines(prefix)

    def __call__(self, method, url, data=None):
        self.calls.append((method, url))
        if method == "POST":
            assert url == SEARCH_URL
            form = dict(urllib.parse.parse_qsl(data.decode("ascii"), encoding=ENC))
            self.last = form["suche.fkzSuche[0]"].rstrip("%")
            self.queries.append(self.last)
            n = len(self.lines(self.last))
            if self.count_fn is not None:
                n = self.count_fn(self.last, n)
            return page(self.counts.get(self.last, n))
        assert url == fx.CSV_URL
        if self.last in self.exports:
            return self.exports[self.last]
        return HEADER_LINE + b"\n" + b"".join(l + b"\n" for l in self.lines(self.last))


def grant(**changes) -> fx.GrantRow:
    base = fx.GrantRow.from_dict(FIRST_ROW, CLOCK())
    return fx.GrantRow(**{**base.__dict__, **changes})


def flags(lead):
    """Step-1 hints: the labelled 'Hinweise: …' line of the signal evidence (flags left prioritization_reason)."""
    line = next(l for l in lead.signals[0].evidence.splitlines() if l.startswith("Hinweise: "))
    return line.removeprefix("Hinweise: ").split(", ")


def dump(leads):
    return TypeAdapter(list[RawLead]).dump_json(leads, indent=2)


def assert_contract(leads):
    for lead in leads:
        RawLead.model_validate(lead.model_dump())
        assert lead.is_demo is False and lead.country == "DE" and lead.country_evidence is not None
        assert lead.founders == [] and lead.contact_email is None and lead.founding_year is None
        assert "Deutschland" in lead.country_evidence.finding
    assert len({l.id for l in leads}) == len(leads)


# --- amounts and dates ------------------------------------------------------------------------------

@pytest.mark.parametrize("text, value", [
    ("1.234.567,89 €", Decimal("1234567.89")), ("1.234.567,89", Decimal("1234567.89")),
    ("0,00", Decimal("0.00")), ("876.964,00 EUR", Decimal("876964.00")), ("1234,5", Decimal("1234.5")),
    (" 7 ", Decimal("7")), ("1.234", Decimal("1234")), ("-5,00", Decimal("-5.00")),
    ("1.234,00\xa0€", Decimal("1234.00")),
    ("", None), (None, None), ("garbage", None), ("n/a", None), ("12.34,00", None), ("1,2,3", None),
    ("1.234.56", None), ("€", None), ("1 234,00", None), ("1e5", None), ("NaN", None), ("Infinity", None),
])
def test_parse_euro(text, value):
    result = fx.parse_euro(text)
    assert result == value and (value is None or isinstance(result, Decimal))


def test_format_euro_round_trip_and_unknown():
    for text in ("0,00", "1,00", "999,99", "1.000,00", "876.964,00", "1.234.567,89"):
        assert fx.format_euro(fx.parse_euro(text)) == text + " €"
    assert fx.format_euro(None) == "?"
    assert fx.format_euro(Decimal("1234.5")) == "1.234,50 €"


def test_format_euro_keeps_sign_of_small_negative():
    assert fx.format_euro(Decimal("-0.50")) == "-0,50 €"


@pytest.mark.parametrize("text, value", [
    ("01.06.2024", date(2024, 6, 1)), ("31.12.2025", date(2025, 12, 31)), ("29.02.2024", date(2024, 2, 29)),
    ("", None), ("31.02.2024", None), ("29.02.2025", None), ("00.01.2024", None), ("01.13.2024", None),
    ("2024-06-01", None), ("1.6.2024", None), ("unbekannt", None),
])
def test_dates_in_rows(text, value):
    row = fx.GrantRow.from_dict({**FIRST_ROW, "Laufzeit von": text, "Laufzeit bis": text}, CLOCK())
    assert row.start == value and row.end == value


def test_empty_end_date_and_amount_show_placeholders():
    lead = mp.lead_from_rows([grant(end=None, amount=None, amount_text="")])
    evidence = lead.signals[0].evidence
    assert "Laufzeit: 01.06.2024 bis ?" in evidence and "Fördersumme: unbekannt" in evidence.splitlines()
    assert "project_finished" not in flags(lead) and "Fördersumme unbekannt" in lead.prioritization_reason


def test_finished_project_flag_depends_on_retrieval_date():
    finished = mp.lead_from_rows([grant(end=date(2026, 11, 19))])
    running = mp.lead_from_rows([grant(end=date(2026, 11, 20))])
    assert "project_finished" in flags(finished) and "project_finished" not in flags(running)


# --- wrappers, splitting, header ----------------------------------------------------------------------

@pytest.mark.parametrize("cell, value", [
    ('="03EFBB0063"', "03EFBB0063"), ('=""', ""), ('  ="  x  "  ', "x"), ("plain", "plain"), ("", ""),
    (None, ""), ('="a "quoted" b"', 'a "quoted" b'), ('="a; b"', "a; b"), ('="="', "="), ('"x"', '"x"'),
    ('="multi\nline"', "multi\nline"),
])
def test_unwrap(cell, value):
    assert fx.unwrap(cell) == value


def test_split_line_wrappers_with_semicolons_and_quotes():
    assert fx.split_line('="A; B; C";x;="";') == ['="A; B; C"', "x", '=""', ""]
    assert fx.split_line('="say "hi" now";="b"') == ['="say "hi" now"', '="b"']   # quote not before ';'
    assert fx.split_line("a;;b\r") == ["a", "", "b"]
    assert fx.split_line("") == [""]
    assert fx.split_line(";") == ["", ""]


def test_doubled_quote_before_semicolon_inside_wrapper():
    cells = [fx.unwrap(c) for c in fx.split_line('="Projekt ""Alpha""; Beta";="x";')]
    assert cells == ['Projekt "Alpha"; Beta', "x", ""]


def test_thema_with_semicolon_and_quotes_survives_parse():
    raw = export(synth_row(**{THEMA: 'Alpha; Beta "Gamma"'}))
    assert fx.parse_export(raw)[0][THEMA] == 'Alpha; Beta "Gamma"'


def test_duplicate_geo_header_names_are_disambiguated():
    header = fx.clean_header(fx.split_line(HEADER_LINE.decode(ENC)))
    assert len(header) == len(set(header)) == 26
    row = fx.parse_export(export(synth_row(**{"Staat (Förderempfänger)": "Schweiz", "Ort (Ausführende Stelle)": "Basel"})))[0]
    assert row["Staat (Förderempfänger)"] == "Schweiz" and row["Staat (Ausführende Stelle)"] == "Deutschland"
    assert row["Ort (Förderempfänger)"] == "Cottbus" and row["Ort (Ausführende Stelle)"] == "Basel"


def test_geo_column_before_any_owner_keeps_plain_name_and_other_duplicates_last_wins():
    assert fx.clean_header(['="Ort"', '="FKZ"', '="Förderempfänger /Auftragnehmer"', '="Ort"', '=""', ""]) == [
        "Ort", "FKZ", "Förderempfänger /Auftragnehmer", "Ort (Förderempfänger)"]
    # a non-geo duplicate header is not renamed: dict(zip()) keeps the last value (documented here, not a bug)
    raw = ("%s;=\"Ressort\";\n%s;=\"SECOND\";\n" % (HEADER_LINE.decode(ENC).rstrip(";"), line(synth_row()).decode(ENC).rstrip(";"))).encode(ENC)
    assert fx.parse_export(raw)[0]["Ressort"] == "SECOND"


def test_header_without_required_columns_is_not_csv():
    with pytest.raises(fx.NotCsvError, match="FKZ"):
        fx.parse_export(HEADER_LINE.replace(b'="FKZ"', b'="Kennzeichen"') + b"\n" + line(synth_row()) + b"\n")
    with pytest.raises(fx.NotCsvError):
        fx.parse_export("Fehler: Ihre Sitzung ist abgelaufen.\n".encode(ENC))


def test_latin_15_umlauts_and_euro_sign_in_cells():
    raw = export(synth_row(**{THEMA: "Größenmessung € œ", fx.RECIPIENT_COL: "Universität Göttingen"}))
    assert raw.count(b"\xa4") == 1 and b"\xc3" not in raw          # real ISO-8859-15 bytes, not UTF-8
    row = fx.parse_export(raw)[0]
    assert row[THEMA] == "Größenmessung € œ" and row[fx.RECIPIENT_COL] == "Universität Göttingen"


def test_utf8_body_is_not_silently_accepted_as_clean_text():
    # The catalogue never sends UTF-8; if it did, umlauts would turn into mojibake, not raise.
    raw = HEADER_LINE + b"\n" + ";".join('="%s"' % v for v in synth_row(**{THEMA: "Größe"})).encode("utf-8") + b";\n"
    assert fx.parse_export(raw)[0][THEMA] == "GrÃ¶Ã\x9fe"


def test_utf8_bom_is_dropped():
    rows = fx.parse_export(b"\xef\xbb\xbf" + fixture_bytes("03EF"))
    assert len(rows) == 19 and rows[0]["FKZ"] == "03EFBB0063"


def test_crlf_line_endings_and_blank_lines():
    raw = fixture_bytes("03EF").replace(b"\n", b"\r\n") + b"\r\n\r\n;;;\r\n"
    rows = fx.parse_export(raw)
    assert len(rows) == 19 and rows[0]["FKZ"] == "03EFBB0063" and rows[-1]["Förderart"] == "Direkte Projektförderung"


def test_newline_inside_wrapped_cell_stays_one_row():
    rows = fx.parse_export(fixture_bytes("03EF").replace(b'="HoCHQuant"', b'="HoCH\nQuant"'))
    assert len(rows) == 19 and rows[0][THEMA] == "HoCH\nQuant"


def test_nel_byte_inside_cell_does_not_split_row():
    rows = fx.parse_export(fixture_bytes("03EF").replace(b'="HoCHQuant"', b'="HoCH\x85Quant"'))
    assert len(rows) == 19


def test_fewer_and_more_columns_than_header():
    short = ";".join('="%s"' % v for v in synth_row()[:5]).encode(ENC) + b"\n"
    long = line(synth_row()) + b'="extra1";="extra2";\n'
    rows = fx.parse_export(HEADER_LINE + b"\n" + short + long)
    assert len(rows) == 2 and all(len(r) == 26 for r in rows)
    assert rows[0]["FKZ"] == "03EFBB0063" and rows[0][THEMA] == "" and rows[0]["Laufzeit von"] == ""
    assert rows[1] == fx.parse_export(export(synth_row()))[0]               # extra cells dropped
    padded = fx.GrantRow.from_dict(rows[0], CLOCK())
    assert padded.start is None and padded.amount is None


# --- HTML, empty and malformed exports ----------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "<html><body>Sitzung abgelaufen</body></html>", "  \n<!DOCTYPE html><html></html>",
    "<?xml version='1.0'?><html/>", "Hinweis\n<HTML>Fehler</HTML>",
])
def test_html_error_page_is_not_csv(body):
    with pytest.raises(fx.NotCsvError):
        fx.parse_export(body.encode(ENC))
    with pytest.raises(fx.NotCsvError):
        fx.export_rows(("03EF",), fetch=Fetch(exports={"03EF": body}), cache=None, clock=CLOCK)


def test_empty_and_whitespace_export():
    assert fx.parse_export(b"") == [] and fx.parse_export(b"\n\r\n  \n") == []
    for empty in (b"", b"   \r\n", ""):
        with pytest.raises(fx.EmptyExportError):
            fx.export_rows(("03EF",), fetch=Fetch(exports={"03EF": empty}), cache=None, clock=CLOCK)


def test_header_only_export_parses_to_no_rows():
    assert fx.parse_export(HEADER_LINE + b"\n") == []


def test_header_only_export_with_hits_raises_empty_export():
    fetch = Fetch(count_fn=lambda prefix, n: n or 1, exports={"03EF": HEADER_LINE + b"\n"})
    with pytest.raises(fx.EmptyExportError):
        fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)


def test_text_result_page_bytes_are_decoded():
    class BytesPage(Fetch):
        def __call__(self, method, url, data=None):
            out = super().__call__(method, url, data)
            return out.encode(ENC) if isinstance(out, str) else out.decode(ENC)   # page as bytes, CSV as str
    result = fx.export_rows(("03EF",), fetch=BytesPage(), cache=None, clock=CLOCK)
    assert result.complete and len(result.rows) == 19


def test_parse_hit_count_variants():
    assert fx.parse_hit_count("12.345 Treffer insgesamt") == 12345
    assert fx.parse_hit_count("1 Treffer  insgesamt") == 1
    assert fx.parse_hit_count("Keine Treffer") == 0
    for bad in ("", None, "Treffer insgesamt", "<html>500</html>"):
        with pytest.raises(fx.ResultPageError):
            fx.parse_hit_count(bad)


# --- validation, split fallback -----------------------------------------------------------------------

def test_export_with_more_fkz_than_server_count_is_incomplete():
    fetch = Fetch(counts={"03EF": 18})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete is False and len(result.rows) == 19            # surplus export kept, flagged
    assert any("19 FKZ, Server meldet 18" in w for w in result.warnings)
    assert any("mehr FKZ als Treffer, keine Aufteilung" in w for w in result.warnings)
    assert fetch.queries == ["03EF"]                                       # a split cannot fix a surplus


def test_persistent_mismatch_stops_at_max_split_depth():
    fetch = Fetch(count_fn=lambda prefix, n: n + 1 if n else 0)          # every non-empty query is one short
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK, budget=10_000)
    assert result.complete is False and result.rows == []                # nothing unvalidated survives
    assert max(len(q) for q in fetch.queries) == 4 + fx.MAX_SPLIT_DEPTH
    assert len(fetch.queries) == len(set(fetch.queries)) <= 1 + 36 + 36 ** 2
    assert any("maximale Aufteilungstiefe" in w for w in result.warnings)
    assert all(q.validated is False for q in result.queries if q.server_count)


def test_persistent_mismatch_with_default_budget_raises_budget_exhausted():
    fetch = Fetch(count_fn=lambda prefix, n: n + 1 if n else 0)
    with pytest.raises(fx.BudgetExhaustedError) as caught:
        fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert caught.value.requests == caught.value.budget == fx.DEFAULT_BUDGET


def test_split_fan_out_is_bounded_when_only_top_level_mismatches():
    fetch = Fetch(counts={"03EF": 20})
    fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert len(fetch.queries) == 1 + 36                                    # children validate, no depth 2


def test_duplicate_fkz_across_split_parts_is_deduped():
    header, body = HEADER_LINE, body_lines("03EF")
    foreign = [l for l in body if l.startswith(b'="03EFNW0386"')][0]
    b_lines = body_lines("03EFB") + [foreign]                             # server leaks one 03EFN row into 03EFB
    fetch = Fetch(counts={"03EF": 19, "03EFB": len(b_lines)},
                  exports={"03EF": header + b"\n" + b"\n".join(body[:3]) + b"\n",
                           "03EFB": header + b"\n" + b"\n".join(b_lines) + b"\n"})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    fkzs = [r.fkz for r in result.rows]
    assert result.complete and len(fkzs) == len(set(fkzs)) == 19
    assert not any("abweichenden" in w for w in result.warnings)


def test_duplicate_fkz_with_conflicting_data_keeps_first_and_warns():
    raw = export(synth_row(), synth_row(**{THEMA: "Anders"}))
    fetch = Fetch(counts={"03EF": 1}, exports={"03EF": raw})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete and [r.thema for r in result.rows] == ["HoCHQuant"]
    assert any("mehrfach mit abweichenden" in w for w in result.warnings)
    assert result.queries[0].exported_rows == 2 and result.queries[0].unique_fkz == 1


def test_rows_before_since_or_without_start_or_with_foreign_prefix_are_dropped():
    raw = export(synth_row(), synth_row(FKZ="03EFBB9001", **{"Laufzeit von": "31.12.2023"}),
                 synth_row(FKZ="03EFBB9002", **{"Laufzeit von": ""}),
                 synth_row(FKZ="03EFBB9003", **{"Laufzeit von": "31.02.2024"}),
                 synth_row(FKZ="03EGBB9004"), synth_row(FKZ="03efbb9005", **{"Laufzeit von": "01.01.2024"}))
    fetch = Fetch(counts={"03EF": 6}, exports={"03EF": raw})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert sorted(r.fkz for r in result.rows) == ["03EFBB0063", "03EFBB9005"]   # FKZ upper-cased, since inclusive
    text = " ".join(result.warnings)
    assert "03EFBB9001: Laufzeitbeginn 2023-12-31" in text and "03EFBB9002: Laufzeitbeginn None" in text
    assert "03EFBB9003: Laufzeitbeginn None" in text and "03EGBB9004: FKZ passt nicht" in text


def test_cache_hit_skips_network_and_keeps_retrieval_time(tmp_path):
    cache = Cache(tmp_path / "c.db")
    first = fx.fetch_export("03EF", date(2024, 1, 1), fetch=Fetch(), cache=cache, clock=CLOCK)
    again = fx.fetch_export("03EF", date(2024, 1, 1), fetch=lambda *a: pytest.fail("network"), cache=cache,
                            clock=lambda: datetime(2031, 1, 1, tzinfo=timezone.utc))
    assert again.from_cache and not first.from_cache
    assert (again.raw, again.count, again.retrieved_at) == (first.raw, 19, CLOCK())
    other = fx.fetch_export("03EF", date(2025, 1, 1), fetch=Fetch(), cache=cache, clock=CLOCK)
    assert other.from_cache is False                                       # since is part of the key


def test_network_error_on_csv_and_foreign_exception_types():
    class CsvDown(Fetch):
        def __call__(self, method, url, data=None):
            if method == "GET":
                raise FoekatError("HTTP 502")
            return super().__call__(method, url, data)
    with pytest.raises(fx.ExportNetworkError, match="HTTP 502"):
        fx.export_rows(("03EF",), fetch=CsvDown(), cache=None, clock=CLOCK)
    with pytest.raises(SourcingError, match="nicht erreichbar"):
        search(SearchCriteria(industry=Industry.AI), fetch=CsvDown(), cache=NoCache())


def test_search_wraps_every_export_error_and_empty_incomplete_result():
    criteria = SearchCriteria(industry=Industry.AI)
    with pytest.raises(SourcingError):
        search(criteria, fetch=Fetch(exports={"03EF": "<html>x</html>"}), cache=NoCache())
    with pytest.raises(SourcingError, match="Anfragebudget"):
        search(criteria, prefixes=("03EF",), fetch=Fetch(count_fn=lambda p, n: n + 1 if n else 0), cache=NoCache())
    surplus_all_too_old = Fetch(counts={"03EF": 18})                      # incomplete, every row dropped by since
    with pytest.raises(SourcingError, match="ohne validierte Zeilen"):
        search(criteria, since=date(2099, 1, 1), prefixes=("03EF",), fetch=surplus_all_too_old, cache=NoCache())


def test_search_incomplete_export_with_rows_warns_and_flags(caplog):
    criteria = SearchCriteria(industry=Industry.INDUSTRIAL, limit=50)
    with caplog.at_level("WARNING", logger="sourcing.engine"):
        found = search(criteria, prefixes=("03EF",), fetch=Fetch(counts={"03EF": 18}), cache=NoCache())
    assert found and isinstance(found, list) and found.complete is False
    assert any("mehr FKZ als Treffer" in w for w in found.warnings)
    assert any("unvollständig" in r.getMessage() for r in caplog.records if r.name == "sourcing.engine")


def test_search_complete_export_is_flagged_complete():
    found = search(SearchCriteria(industry=Industry.AI), fetch=Fetch(), cache=NoCache())
    assert found.complete is True and found.warnings == []


def test_lazy_session_is_opened_once_and_only_on_cache_miss(monkeypatch, tmp_path):
    opened = []

    class FakeSession:
        def __init__(self):
            opened.append(self)
            self.inner = Fetch()

        def fetch(self, method, url, data=None):
            return self.inner(method, url, data)
    monkeypatch.setattr(fx, "Session", FakeSession)
    cache = Cache(tmp_path / "c.db")
    assert fx.export_rows(cache=cache, clock=CLOCK).complete and len(opened) == 1
    assert fx.export_rows(cache=cache, clock=CLOCK).fetches == 0 and len(opened) == 1


# --- names, grouping ----------------------------------------------------------------------------------

@pytest.mark.parametrize("thema, expected", [
    ("HAPPY", ("HAPPY", None)), ("KI", ("KI", None)), ("EXIST-Forschungstransfer: ", ("EXIST-Forschungstransfer:", None)),
    ("EXIST-Forschungstransfer:", ("EXIST-Forschungstransfer:", None)), ("  ", ("", None)),
    ("EXIST-Gründungsstipendium: Foo", ("Foo", None)), ("EXIST-Gruendungsstipendium - Foo", ("Foo", None)),
    ("Neo (ehemals Old)", ("Neo", "Old")), ("Neo (vormals Old GmbH)", ("Neo", "Old GmbH")),
    ("Neo (formerly Old)", ("Neo", "Old")), ("Neo ehem. Old", ("Neo", "Old")), ("(ehemals X)", ("(ehemals X)", None)),
    ("EXIST-Forschungstransfer: Neo (ehemals Old)", ("Neo", "Old")),
])
def test_project_name_edge_cases(thema, expected):
    assert mp.project_name(thema) == expected


def test_ehemals_in_prose_thema_is_not_an_alias():
    assert mp.project_name("Lernplattform für ehemals Inhaftierte") == ("Lernplattform für ehemals Inhaftierte", None)


def test_real_programme_prefixed_thema_is_stripped():
    rows = [fx.GrantRow.from_dict(r, CLOCK()) for r in fx.parse_export(fixture_bytes("03EF")) if r["FKZ"] == "03EFVHE091"]
    lead = mp.lead_from_rows(rows)
    assert rows[0].thema == "EXIST-Forschungstransfer: HAPPY" and lead.name == "HAPPY" and lead.id == "foekat-03efvhe091"


def test_empty_thema_does_not_crash_the_run():
    run = mp.build_leads(fx.ExportResult(rows=[grant(thema=""), grant(fkz="03EFBB0064")]))
    assert len(run.leads) + len(run.skipped_non_de) >= 1
    assert all(l.name for l in run.leads)


def test_verbund_same_thema_different_fkz_and_recipients_stay_separate():
    # Synthetic: two FKZ with the same Thema at different recipients, no 'Projekt' value, no shared stem.
    a = grant(fkz="03EFBB1001", recipient="Universität A")
    b = grant(fkz="03EFNW2002", recipient="Hochschule B", recipient_ort="Köln")
    run = mp.build_leads(fx.ExportResult(rows=[a, b]))
    assert sorted(l.id for l in run.leads) == ["foekat-03efbb1001", "foekat-03efnw2002"]
    assert all(l.name == "HoCHQuant" and "verbund" not in flags(l) for l in run.leads)


def test_verbund_by_projekt_value_and_by_suffix_letter():
    a = grant(fkz="03EFBB1001", projekt="Verbund Alpha Beta", recipient="Universität A", amount=Decimal("1.00"))
    b = grant(fkz="03EFNW2002", projekt="VERBUND ALPHA BETA", recipient="Hochschule B", amount=None,
              start=date(2024, 3, 1), end=date(2027, 1, 1))
    run = mp.build_leads(fx.ExportResult(rows=[b, a]))
    lead, = run.leads
    assert lead.id == "foekat-verbund-verbund-alpha-beta" and "verbund" in flags(lead)
    assert [s.evidence.splitlines()[0] for s in lead.signals] == ["Förderkennzeichen: 03EFBB1001", "Förderkennzeichen: 03EFNW2002"]
    assert "Laufzeit: 01.03.2024 bis 01.01.2027" in lead.signals[1].evidence and "; 1 EUR" in lead.prioritization_reason
    assert mp.project_key(grant(fkz="03EFBB1001A")) == mp.project_key(grant(fkz="03EFBB1001")) == "03EFBB1001"
    assert mp.project_key(grant(projekt="N")) == mp.project_key(grant(projekt="nein")) == "03EFBB0063"


def test_company_recipient_variants():
    def company(**kw):
        return mp.recipient_is_company(grant(fkz="03EFU9XX01", **kw))
    assert company(recipient="Beispiel Sensorik GmbH", executing="Beispiel Sensorik GmbH")
    assert company(recipient="Beispiel UG (haftungsbeschränkt)", executing="Beispiel UG")
    assert company(recipient="Beispiel AG", executing="Beispiel AG")
    assert not company(recipient="AGRAR Beispiel e.V.", executing="AGRAR Beispiel e.V.")     # no word match
    assert not company(recipient="Beispiel gGmbH", executing="Beispiel gGmbH")
    assert not company(recipient="Beispiel GmbH", executing="Institut für Beispiel")
    assert not mp.recipient_is_company(grant(fkz="03EGXX0001", recipient="Beispiel GmbH", executing="Beispiel GmbH"))
    lead = mp.lead_from_rows([grant(fkz="03EFU9XX01", recipient="Beispiel GmbH", executing="Beispiel GmbH")])
    assert {"recipient_company", "exist_ft_phase2_candidate"} <= set(flags(lead))
    assert "internal_review_case" not in flags(lead) and lead.founders == [] and lead.founding_year is None


def test_country_evidence_requires_deutschland():
    assert mp.country_evidence(grant(recipient_staat="Schweiz", executing_staat="nicht zuzuordnen")) is None
    ev = mp.country_evidence(grant(recipient_staat="Schweiz", executing_staat="Deutschland"))
    assert ev.field == "country" and str(ev.url) == detail_url("03EFBB0063") and ev.retrieved_at == CLOCK()
    lead = mp.lead_from_rows([grant(fkz="03EFBB1001A", recipient_staat="Schweiz", executing_staat="Schweiz"),
                              grant(fkz="03EFBB1001B")])
    assert "FKZ 03EFBB1001B" in lead.country_evidence.finding                 # evidence from the German partner
    assert mp.lead_from_rows([grant(recipient_staat="", executing_staat="")]) is None


# --- industry classification --------------------------------------------------------------------------

CLASSIFY_CASES = [
    # (Thema, FKZ prefix, industry, htgf_sector, rule) -- realistic Themen; ambiguous ones follow the documented
    # tie-break (most hits within the first field with any hit, then table order); unknown ones the default.
    ("KI-gestützte Diagnostik von Hautkrebs", "03EF", Industry.HEALTH, "life_sciences", "health"),
    ("Wasserstoff-Elektrolyseur mit Feststoffkatalysator", "03EF", Industry.CLIMATE, "climate_tech", "climate"),
    ("Blockchain-basierte Zahlungsabwicklung", "03EG", Industry.FINTECH, "digital_tech", "fintech"),
    ("Recycelbare Polymerwerkstoffe", "03EF", Industry.INDUSTRIAL, "chemie_materialien", "chemistry_materials"),
    ("Laserbasierte Fertigung von Mikrosystemen", "03EF", Industry.INDUSTRIAL, "industrial_deep_tech", "industrial_deeptech"),
    ("Cloud-Software für Handwerksbetriebe", "03EG", Industry.AI, "digital_tech", "software_ai"),
    # ambiguous: one health hit (therap) vs one software hit (software) -> tie -> earlier rule health
    ("Software für Physiotherapie", "03EG", Industry.HEALTH, "life_sciences", "health"),
    # ambiguous: solar + energie (2 climate) beat sensor (1 industrial)
    ("Sensorik für Solarenergie", "03EF", Industry.CLIMATE, "climate_tech", "climate"),
    # ambiguous: digital + daten (2 software) beat material (1 chemistry)
    ("Digitale Daten zu Material", "03EF", Industry.AI, "digital_tech", "software_ai"),
    # unknown: acronym only / plain words -> programme default, unclassified
    ("HYNOVY", "03EF", Industry.INDUSTRIAL, None, "default_03ef"),
    ("SetScout", "03EG", Industry.AI, None, "default_03eg"),
    ("Plattform für nachbarschaftliche Hilfe", "03EG", Industry.AI, None, "default_03eg"),
]


@pytest.mark.parametrize("thema, prefix, industry, sector, rule", CLASSIFY_CASES)
def test_classify_realistic_themen(thema, prefix, industry, sector, rule):
    neutral = dict(executing="Lehrstuhl X", recipient="Stiftung Y")      # no keyword hits outside Thema
    match = mp.classify([grant(fkz=prefix + "XX0001", thema=thema, **neutral)])
    assert (match.industry, match.htgf_sector, match.rule) == (industry, sector, rule)
    lead = mp.lead_from_rows([grant(fkz=prefix + "XX0001", thema=thema, **neutral)])
    assert lead.industry == industry and lead.htgf_sector == sector
    if sector is None:
        assert match.unclassified and "industry_unclassified" in flags(lead) and "nicht klassifiziert" in lead.prioritization_reason
    else:
        assert match.field == "Thema" and "industry_unclassified" not in flags(lead)


def test_classify_falls_back_to_executing_then_recipient_fields():
    m1 = mp.classify([grant(thema="HYNOVY", executing="Institut für Informatik", recipient="Universität")])
    assert (m1.field, m1.rule) == ("Ausführende Stelle", "software_ai")
    m2 = mp.classify([grant(thema="HYNOVY", executing="Lehrstuhl X", recipient="Medizinische Hochschule")])
    assert (m2.field, m2.rule) == ("Förderempfänger", "health")
    m3 = mp.classify([grant(fkz="03EFZZ0001", thema="HYNOVY", executing="", recipient="")])
    assert m3.unclassified and m3.industry == Industry.INDUSTRIAL


def test_token_keywords_only_match_whole_tokens():
    assert mp.classify([grant(thema="SherpAI", executing="X", recipient="Y")]).rule == "software_ai"   # CamelCase split
    assert mp.classify([grant(thema="Kinematik", executing="X", recipient="Y")]).unclassified           # 'ki' inside a word
    assert mp.classify([grant(thema="Bankettplanung", executing="X", recipient="Y")]).unclassified      # '<bank>' token only


def test_gearbox_is_not_health():
    assert mp.classify([grant(thema="Leichtbau-Zahnradgetriebe", executing="X", recipient="Y")]).industry != Industry.HEALTH


def test_neural_networks_are_not_health():
    thema = "Neuronale Netze für die Qualitätsprüfung von Schweißnähten"
    assert mp.classify([grant(thema=thema, executing="X", recipient="Y")]).industry != Industry.HEALTH


# --- whole run: contract, ids, determinism ------------------------------------------------------------

def run_leads(fetch=None):
    return mp.run(fetch=fetch or Fetch(), cache=None, clock=CLOCK).leads


def test_every_lead_satisfies_raw_lead_contract():
    leads = run_leads()
    assert len(leads) == 45
    assert_contract(leads)
    TypeAdapter(list[RawLead]).validate_json(dump(leads))


def test_ids_stable_across_runs_and_independent_of_row_order():
    base = dump(run_leads())
    assert dump(run_leads()) == base
    body = body_lines("03EF") + body_lines("03EG")
    for seed in (1, 2, 3):
        shuffled = body[:]
        random.Random(seed).shuffle(shuffled)
        assert dump(run_leads(Fetch(body=shuffled))) == base
    rows = mp.export_rows(fetch=Fetch(), cache=None, clock=CLOCK).rows
    reordered = mp.build_leads(fx.ExportResult(rows=list(reversed(rows))))
    assert dump(reordered.leads) == base


def test_stats_counts_are_consistent():
    run = mp.run(fetch=Fetch(), cache=None, clock=CLOCK)
    stats = run.stats(Industry.HEALTH)
    assert stats["leads"] == sum(1 for l in run.leads if l.industry == Industry.HEALTH)
    assert stats["leads_before_industry_filter"] == 45 and stats["programmes"] == {"03EF": 19, "03EG": 26}
    assert set(stats["industry"]) == {i.value for i in Industry}
    assert json.loads(json.dumps(stats, ensure_ascii=False)) == stats


# --- engine.search and pipeline.discover --------------------------------------------------------------

def test_search_filters_by_industry():
    # search() returns only keyword-classified leads of the industry: basis "thema" first, then "institut",
    # each in run order (priority desc, start desc, id); default-classified leads only on request.
    result = mp.run(fetch=Fetch(), cache=None, clock=CLOCK)
    basis = {l.id: result.info[l.id].basis for l in result.leads}
    for industry in Industry:
        found = search(SearchCriteria(industry=industry, limit=200), fetch=Fetch(), cache=NoCache(), since=date(2024, 1, 1))
        assert [l.id for l in found] == [l.id for b in ("thema", "institut") for l in result.leads
                                         if l.industry == industry and basis[l.id] == b]
        assert all(l.industry == industry for l in found)
        every = search(SearchCriteria(industry=industry, limit=200), fetch=Fetch(), cache=NoCache(),
                       since=date(2024, 1, 1), include_unclassified=True)
        assert {l.id for l in every} == {l.id for l in result.leads if l.industry == industry}


def test_search_limit_is_applied_by_discover_not_by_search():
    # Changed: search() now cuts at criteria.limit itself, after sorting by priority; discover keeps that order.
    criteria = SearchCriteria(industry=Industry.AI, limit=3)
    full = search(criteria.model_copy(update={"limit": 200}), fetch=Fetch(), cache=NoCache(), include_unclassified=True)
    assert len(full) > 3
    limited = search(criteria, fetch=Fetch(), cache=NoCache(), include_unclassified=True)
    assert [l.id for l in limited] == [l.id for l in full[:3]]
    found = discover(criteria, use_mock=False, provider=partial(search, fetch=Fetch(), cache=NoCache(),
                                                                include_unclassified=True))
    assert [l.id for l in found] == [l.id for l in full[:3]]
    one = discover(SearchCriteria(industry=Industry.HEALTH, limit=1), use_mock=False,
                   provider=partial(search, fetch=Fetch(), cache=NoCache()))
    assert len(one) == 1 and one[0].is_demo is False


def test_since_env_and_argument(monkeypatch):
    monkeypatch.setenv("FOEKAT_SINCE", "2026-01-01")
    found = search(SearchCriteria(industry=Industry.AI), fetch=Fetch(count_fn=lambda p, n: n), cache=NoCache())
    assert found and all(min(s.date for s in l.signals) >= date(2026, 1, 1) for l in found)


def test_discover_rejects_mixing_with_demo_mode():
    with pytest.raises(ValueError, match="Demo"):
        discover(SearchCriteria(industry=Industry.AI), use_mock=True, provider=partial(search, fetch=Fetch(), cache=NoCache()))


# --- CLI ----------------------------------------------------------------------------------------------

@pytest.fixture
def offline_db(tmp_path, monkeypatch):
    db = tmp_path / "c.db"
    fx.export_rows(fetch=Fetch(), cache=Cache(db), clock=CLOCK)
    monkeypatch.setattr(fx, "Session", lambda: pytest.fail("network used"))
    return db


def cli(*args):
    from sourcing.__main__ import main
    return main(["foekat", *map(str, args)])


def read_leads(path):
    return TypeAdapter(list[RawLead]).validate_json(path.read_text(encoding="utf-8"))


def test_cli_happy_path_json_array(offline_db, tmp_path):
    out = tmp_path / "out.json"
    assert cli("--out", out, "--cache", offline_db) == 0
    assert out.read_bytes().endswith(b"]\n") and out.read_bytes().startswith(b"[")
    leads = read_leads(out)
    assert len(leads) == 45
    assert_contract(leads)


@pytest.mark.parametrize("args, count, industries", [
    (("--industry", "all"), 45, None), (("--industry", "software"), None, {Industry.AI}),
    (("--industry", "HealthTech"), None, {Industry.HEALTH}), (("--industry", "CLIMATE"), None, {Industry.CLIMATE}),
    (("--programme", "eg"), 26, None), (("--programme", "ef"), 19, None),
    (("--limit", "5"), 5, None), (("--limit", "1000"), 45, None),
    (("--programme", "ef", "--industry", "health", "--limit", "1"), 1, {Industry.HEALTH}),
])
def test_cli_filters(offline_db, tmp_path, args, count, industries):
    out = tmp_path / "out.json"
    assert cli("--out", out, "--cache", offline_db, *args) == 0
    leads = read_leads(out)
    if count is not None:
        assert len(leads) == count
    if industries is not None:
        assert leads and {l.industry for l in leads} == industries
    if "--programme" in args:
        prefix = "03EG" if "eg" in args else "03EF"
        assert all(l.id.startswith("foekat-" + prefix.lower()) for l in leads)


def test_cli_stats_file(offline_db, tmp_path):
    out, stats = tmp_path / "out.json", tmp_path / "stats.json"
    assert cli("--out", out, "--cache", offline_db, "--stats", stats, "--industry", "health", "--limit", "2") == 0
    data = json.loads(stats.read_text(encoding="utf-8"))
    assert data["written"] == 2 and data["industry_filter"] == "HealthTech" and data["programme"] == "both"
    assert data["since"] == "2024-01-01" and data["complete"] is True and data["warnings"] == []
    assert data["leads"] >= 2 and data["leads_before_industry_filter"] == 45
    assert [q["query"] for q in data["queries"]] == ["03EF%", "03EG%"]
    assert data["requests"] == 0 and data["budget"] == fx.DEFAULT_BUDGET          # everything from the cache
    assert data["prefixes"]["03EF"]["server_count"] == 19 and data["prefixes"]["03EG"]["complete"] is True


@pytest.mark.parametrize("args", [("--limit", "0"), ("--limit", "-1"), ("--industry", "astrology"),
                                  ("--programme", "xx"), ("--since", "2024-13-01")])
def test_cli_rejects_bad_arguments(offline_db, tmp_path, args):
    with pytest.raises(SystemExit) as exc:
        cli("--out", tmp_path / "x.json", "--cache", offline_db, *args)
    assert exc.value.code == 2 and not (tmp_path / "x.json").exists()


def test_cli_incomplete_export_exits_1_but_writes_validated_leads(tmp_path, monkeypatch, capsys):
    db = tmp_path / "c.db"
    fx.export_rows(("03EF",), fetch=Fetch(counts={"03EF": 20}), cache=Cache(db), clock=CLOCK)   # fills children too
    monkeypatch.setattr(fx, "Session", lambda: pytest.fail("network used"))
    out = tmp_path / "out.json"
    assert cli("--out", out, "--cache", db, "--programme", "ef") == 1
    assert len(read_leads(out)) == 19 and "unvollständig" in capsys.readouterr().err


def test_cli_cache_off_with_broken_network_exits_2(tmp_path, monkeypatch):
    class Broken:
        def fetch(self, *a, **k):
            raise FoekatError("TimeoutError")
    monkeypatch.setattr(fx, "Session", Broken)
    assert cli("--out", tmp_path / "x.json", "--cache", "off") == 2 and not (tmp_path / "x.json").exists()


# --- fuzz ---------------------------------------------------------------------------------------------

def _mangle(rng: random.Random, raw: bytes) -> bytes:
    data = bytearray(raw)
    tokens = [b";", b'="', b'"', b"=", b"\n", b"\r", b"\x85", b"\xa4", b"<html>", b"\xef\xbb\xbf", b'=""', b";;;", b"\x00"]
    for _ in range(rng.randint(1, 12)):
        op = rng.randrange(6)
        pos = rng.randrange(len(data) + 1)
        if op == 0 and data:
            data[min(pos, len(data) - 1)] = rng.randrange(256)
        elif op == 1:
            data[pos:pos] = rng.choice(tokens)
        elif op == 2:
            del data[pos:pos + rng.randint(1, 40)]
        elif op == 3:
            data = data[:pos]
        elif op == 4:
            data[pos:pos] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 8)))
        else:
            lines = bytes(data).split(b"\n")
            rng.shuffle(lines)
            data = bytearray(b"\n".join(lines))
    return bytes(data)


def test_fuzz_parse_export_raises_only_export_errors():
    rng = random.Random(20261120)
    sources = [fixture_bytes("03EF"), fixture_bytes("03EG"), export(synth_row())]
    outcomes = {"rows": 0, "error": 0}
    for _ in range(300):
        raw = _mangle(rng, rng.choice(sources))
        try:
            rows = fx.parse_export(raw)
        except fx.ExportError:
            outcomes["error"] += 1
            continue
        outcomes["rows"] += 1
        assert isinstance(rows, list) and all(isinstance(r, dict) and all(isinstance(v, str) for v in r.values()) for r in rows)
        if rows:
            header = list(rows[0])
            assert all(list(r) == header for r in rows)
            for r in rows:
                fx.GrantRow.from_dict(r, CLOCK())                          # cleaning a parsed row never raises
    assert outcomes["rows"] and outcomes["error"]                           # both paths exercised
