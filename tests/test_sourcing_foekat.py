"""Offline tests for sourcing.foekat_export (step 1: EXIST projects from the Förderkatalog CSV export).

Fixtures in tests/fixtures/sourcing/ were recorded live on 2026-11-20 (search FKZ 03EF%/03EG%, project start
>= 01.01.2024, also finished projects) and trimmed: the CSV exports keep the original ISO-8859-15 bytes, the
`="..."` wrappers, the header and the trailing ';' but only 19 of 146 (03EF) and 26 of 587 (03EG) rows. The
recorded result pages keep the count markup with the hit count changed from 146/587 to 19/26 so that page
and export agree; their table body is removed. The fixture fetch below answers sub-prefix searches
(fallback) from the same rows. Verbund and company-recipient cases do not occur in the real 2024+ data;
they are derived in-test from a real row and marked as such.
"""
import json
import re
import sys
import urllib.parse
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path

import pytest
from pydantic import TypeAdapter

import context.engine
import sourcing.foekat_export as fx
from context.cache import Cache, NoCache
from context.foekat import SEARCH_URL, FoekatError, detail_url
from models import Industry, RawLead, SearchCriteria
from pipeline import collect_context, discover
from scoring_input import build_scoring_input
from sourcing.engine import SourcingError, search

FIXTURES = Path(__file__).parent / "fixtures" / "sourcing"
CLOCK = lambda: datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
FKZ_REGEX = re.compile(r"(?<![A-Za-z0-9])03E[FG][A-Za-z0-9]{3,}")  # the regex step 2 uses (context/engine.py)


def csv_bytes(prefix):
    return (FIXTURES / ("foekat_export_%s.csv" % prefix)).read_bytes()


def result_page(prefix):
    return (FIXTURES / ("foekat_result_%s.html" % prefix)).read_bytes().decode("iso-8859-15")


def lines_for(prefix):
    """Header + the fixture lines whose FKZ starts with `prefix` (any depth)."""
    lines = csv_bytes(prefix[:4]).split(b"\n")
    body = [l for l in lines[1:] if l and l[2:].decode("iso-8859-15").startswith(prefix)]
    return lines[0], body


def page_with(count):
    page = result_page("03EF")
    if count == 0:
        return re.sub(r'aria-label="Suchergebnis\. \d+ Treffer insgesamt[^"]*"', 'aria-label="Suchergebnis. Keine Treffer."', page)
    return re.sub(r"\d+ Treffer insgesamt", "%d Treffer insgesamt" % count, page)


class FixtureFetch:
    """Emulates the catalogue session: POST search -> result page, GET export -> CSV of the last search."""

    def __init__(self, counts=None, exports=None, csv_error=None, post_error=None, page=None):
        self.counts, self.exports = counts or {}, exports or {}
        self.csv_error, self.post_error, self.page = csv_error or {}, post_error, page
        self.calls, self.last = [], None

    def __call__(self, method, url, data=None):
        self.calls.append((method, url))
        if method == "POST":
            if self.post_error:
                raise self.post_error
            form = dict(urllib.parse.parse_qsl(data.decode("ascii"), encoding="iso-8859-15"))
            assert form["suche.lfdVhb"] == "N" and form["suche.detailSuche"] == "true"
            self.last = form["suche.fkzSuche[0]"].rstrip("%")
            if self.page is not None:
                return self.page
            return page_with(self.counts.get(self.last, len(lines_for(self.last)[1])))
        assert url == fx.CSV_URL
        if self.last in self.csv_error:
            raise self.csv_error[self.last]
        if self.last in self.exports:
            return self.exports[self.last]
        header, body = lines_for(self.last)
        return header + b"\n" + b"".join(l + b"\n" for l in body)


def rows_of(prefix="03EF"):
    return [fx.GrantRow.from_dict(r, CLOCK()) for r in fx.parse_export(csv_bytes(prefix))]


def by_name(leads):
    return {lead.name: lead for lead in leads}


@pytest.fixture
def leads():
    return fx.run(fetch=FixtureFetch(), cache=None, clock=CLOCK).leads


# --- cleaning ---------------------------------------------------------------------------------------

def test_parse_export_header_wrappers_and_geo_columns():
    rows = fx.parse_export(csv_bytes("03EF"))
    assert len(rows) == 19
    header = list(rows[0])
    assert header[0] == "FKZ" and len(header) == 26          # trailing ';' column dropped
    for geo in ("Ort", "Bundesland", "Staat", "Stadt/Gemeinde", "Gemeindekennziffer"):
        assert geo + " (Förderempfänger)" in header and geo + " (Ausführende Stelle)" in header
        assert geo not in header
    first = rows[0]
    assert first["FKZ"] == "03EFBB0063" and first["Thema des geförderten Vorhabens"] == "HoCHQuant"
    assert not any(v.startswith('="') for v in first.values())
    assert first["Projekt"] == ""


def test_iso_8859_15_decoding_umlauts_and_euro():
    rows = rows_of("03EG")
    text = " ".join(r.executing + r.recipient for r in rows)
    assert "Universität" in text and "für" in text and "Fakultät für Maschinenwesen" in text
    assert "Ã" not in text                                    # no mojibake
    assert fx.decode_export(b"\xa4 \xe4\xf6\xfc\xdf") == "€ äöüß"  # 0xA4 is the euro sign in ISO-8859-15
    raw = csv_bytes("03EF").replace(b"HoCHQuant", b"Hoch\xa4Quant")
    assert fx.parse_export(raw)[0]["Thema des geförderten Vorhabens"] == "Hoch€Quant"


def test_semicolon_inside_wrapper_is_not_a_separator():
    assert fx.split_line('="03EFX0001";="A; B";1.234,00;') == ["=\"03EFX0001\"", '="A; B"', "1.234,00", ""]
    assert fx.unwrap('="A; B"') == "A; B" and fx.unwrap(" 876.964,00 ") == "876.964,00"


def test_amounts_and_dates():
    assert fx.parse_euro("1.234.567,89") == Decimal("1234567.89")
    assert fx.parse_euro("876.964,00") == Decimal("876964.00")
    assert fx.parse_euro("") is None and fx.parse_euro("n/a") is None
    assert fx.format_euro(Decimal("1234567.89")) == "1.234.567,89 €"
    by_fkz = {r.fkz: r for r in rows_of("03EF")}
    big = by_fkz["03EFBY0377"]
    assert big.amount == Decimal("2087934.00") and big.amount_text == "2.087.934,00"
    hq = by_fkz["03EFBB0063"]
    assert (hq.start, hq.end) == (date(2024, 6, 1), date(2026, 9, 30))
    assert (hq.recipient_ort, hq.recipient_land, hq.executing_staat) == ("Cottbus", "Brandenburg", "Deutschland")


def test_hit_count_parsing():
    assert fx.parse_hit_count(result_page("03EF")) == 19
    assert fx.parse_hit_count(result_page("03EG")) == 26
    assert fx.parse_hit_count('aria-label="Suchergebnis. 1.234 Treffer insgesamt."') == 1234
    assert fx.parse_hit_count(page_with(0)) == 0
    with pytest.raises(fx.ResultPageError):
        fx.parse_hit_count("<html><body>Wartungsarbeiten</body></html>")


def test_search_form_fields():
    form = fx.search_form("03EG", date(2024, 1, 1))
    assert form["suche.fkzSuche[0]"] == "03EG%" and form["suche.laufzeitVonSuche[0]"] == "01.01.2024"
    assert form["suche.lfdVhb"] == "N" and form["suche.detailSuche"] == "true" and "suche.laufzeitBisSuche[0]" not in form


# --- export, validation, fallback -------------------------------------------------------------------

def test_export_matches_server_count():
    fetch = FixtureFetch()
    result = fx.export_rows(fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete and not result.warnings
    assert [(q.query, q.server_count, q.exported_rows, q.validated) for q in result.queries] == [
        ("03EF", 19, 19, True), ("03EG", 26, 26, True)]
    assert len(result.rows) == 45 and fetch.calls == [("POST", SEARCH_URL), ("GET", fx.CSV_URL)] * 2


def test_mismatch_triggers_prefix_split_and_dedupe():
    header, body = lines_for("03EF")
    truncated = header + b"\n" + b"\n".join(body[:10]) + b"\n"     # export stops after 10 of 19 rows
    b_header, b_body = lines_for("03EFB")
    duplicated = b_header + b"\n" + b"\n".join(b_body + b_body[:2]) + b"\n"   # child export repeats two FKZ
    fetch = FixtureFetch(exports={"03EF": truncated, "03EFB": duplicated})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete
    assert sorted(r.fkz for r in result.rows) == sorted(r.fkz for r in rows_of("03EF"))
    assert any("repariert" in w for w in result.warnings) and any("10 FKZ, Server meldet 19" in w for w in result.warnings)
    top = result.queries[0]
    assert (top.server_count, top.unique_fkz, top.validated, top.split) == (19, 10, False, True)
    child = next(q for q in result.queries if q.query == "03EFB")
    assert child.exported_rows == child.unique_fkz + 2 and child.validated


def test_too_large_export_is_split():
    fetch = FixtureFetch(csv_error={"03EG": FoekatError("Antwort größer als 3000000 Bytes")})
    result = fx.export_rows(("03EG",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete and len(result.rows) == 26
    assert any("Größengrenze" in w for w in result.warnings)


def test_unrepairable_mismatch_sets_incomplete():
    fetch = FixtureFetch(counts={"03EF": 20})                  # server claims one row more than any split yields
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete is False
    assert len(result.rows) == 19                              # only validated child rows, nothing invented
    assert any("unvollständig" in w for w in result.warnings)
    run = fx.build_leads(result)
    assert run.stats()["complete"] is False and run.stats()["warnings"]


def test_mismatch_at_max_depth_drops_unvalidated_rows(monkeypatch):
    monkeypatch.setattr(fx, "MAX_SPLIT_DEPTH", 0)
    result = fx.export_rows(("03EF",), fetch=FixtureFetch(counts={"03EF": 20}), cache=None, clock=CLOCK)
    assert result.complete is False and result.rows == []
    assert any("nicht reparierbar" in w for w in result.warnings)


def test_empty_export_raises():
    with pytest.raises(fx.EmptyExportError):
        fx.export_rows(("03EF",), fetch=FixtureFetch(exports={"03EF": b""}), cache=None, clock=CLOCK)


def test_html_instead_of_csv_raises_and_is_not_cached(tmp_path):
    cache = Cache(tmp_path / "c.db")
    fetch = FixtureFetch(exports={"03EF": result_page("03EF")})   # session lost: the export URL answers with HTML
    with pytest.raises(fx.NotCsvError):
        fx.export_rows(("03EF",), fetch=fetch, cache=cache, clock=CLOCK)
    assert fx.export_rows(("03EF",), fetch=FixtureFetch(), cache=cache, clock=CLOCK).complete


def test_unknown_result_page_raises():
    with pytest.raises(fx.ResultPageError):
        fx.export_rows(("03EF",), fetch=FixtureFetch(page="<html>Fehler</html>"), cache=None, clock=CLOCK)


def test_network_error_raises_clear_exception():
    with pytest.raises(fx.ExportNetworkError, match="nicht erreichbar"):
        fx.export_rows(fetch=FixtureFetch(post_error=FoekatError("URLError")), cache=None, clock=CLOCK)
    criteria = SearchCriteria(industry=Industry.AI)
    with pytest.raises(SourcingError):
        search(criteria, fetch=FixtureFetch(post_error=FoekatError("HTTP 503")), cache=NoCache())


def test_zero_hits_needs_no_export():
    fetch = FixtureFetch(counts={"03EF": 0})
    result = fx.export_rows(("03EF",), fetch=fetch, cache=None, clock=CLOCK)
    assert result.complete and result.rows == [] and fetch.calls == [("POST", SEARCH_URL)]


# --- mapping ----------------------------------------------------------------------------------------

def test_names_from_thema():
    assert fx.project_name("EXIST-Forschungstransfer: HAPPY") == ("HAPPY", None)
    assert fx.project_name("EXIST - Forschungstransfer: PlantMap") == ("PlantMap", None)
    assert fx.project_name("EXIST_P2P") == ("EXIST_P2P", None)
    assert fx.project_name("u/press (ehemals trykk)") == ("u/press", "trykk")
    assert fx.project_name("Synascale (ehem. SPHAERAM)") == ("Synascale", "SPHAERAM")
    assert fx.project_name("JoulyAI ehemals Minmo") == ("JoulyAI", "Minmo")
    assert fx.project_name("Charge Circle (VrakosGrid)") == ("Charge Circle (VrakosGrid)", None)
    long = "EXIST-Forschungstransfer: Ionera - Hochdurchsatzplattform für die chemische und biologische Analytik"
    assert fx.project_name(long) == ("Ionera", None)


def test_industry_mapping(leads):
    named = by_name(leads)
    expect = {"BoneGuide": (Industry.HEALTH, "life_sciences", "Ausführende Stelle"),
              "Nero Materials": (Industry.INDUSTRIAL, "chemie_materialien", "Thema"),
              "ZORO-Energy": (Industry.CLIMATE, "climate_tech", "Thema"),
              "mercura": (Industry.AI, "digital_tech", "Ausführende Stelle"),
              "AI-Wallet": (Industry.FINTECH, "digital_tech", "Thema"),
              "SpinMagIC": (Industry.INDUSTRIAL, "industrial_deep_tech", "Ausführende Stelle")}
    for name, (industry, sector, field) in expect.items():
        lead = named[name]
        assert (lead.industry, lead.htgf_sector) == (industry, sector), name
        assert "Branche %s per Regel" % industry.value in lead.prioritization_reason and field in lead.prioritization_reason
        assert "industry_unclassified" not in lead.prioritization_reason


def test_industry_default_is_flagged(leads):
    named = by_name(leads)
    for name, industry in (("Refactum", Industry.INDUSTRIAL), ("RetentionFox", Industry.AI)):
        lead = named[name]
        assert lead.industry == industry and lead.htgf_sector is None
        assert "industry_unclassified" in lead.prioritization_reason and "als Standard" in lead.prioritization_reason
    stats = fx.run(fetch=FixtureFetch(), cache=None, clock=CLOCK).stats()
    assert stats["industry_defaulted"] == stats["flags"]["industry_unclassified"] > 0
    assert sum(stats["industry"].values()) == stats["leads"] == 45


def test_raw_lead_contract(leads):
    assert len(leads) == 45 and len({l.id for l in leads}) == 45
    starts = [l.signals[0].date for l in leads]
    assert starts == sorted(starts, reverse=True)              # newest project start first
    for lead in leads:
        fkz = lead.signals[0].evidence.split(";")[0].removeprefix("FKZ ")
        assert lead.id == "foekat-" + fkz.lower()
        assert lead.founders == [] and lead.contact_email is None and lead.website is None and lead.has_vc is None
        assert lead.founding_year is None and lead.founding_month is None and lead.is_demo is False
        assert lead.country == "DE" and lead.source_name == "Förderkatalog des Bundes"
        assert str(lead.country_evidence.url) == str(lead.source_url) == detail_url(fkz)
        assert str(lead.country_evidence.url).startswith("https://foerderportal.bund.de/foekat/")
        assert "Deutschland" in lead.country_evidence.finding and lead.country_evidence.retrieved_at == CLOCK()
        assert "@" not in lead.model_dump_json()
        signal = lead.signals[0]
        assert signal.source == "Förderkatalog" and signal.type == "exist_projekt" and str(signal.url) == detail_url(fkz)
        assert FKZ_REGEX.search(signal.evidence).group(0) == fkz     # step 2 resolves the same grant
        assert "pre_founding_team" in lead.prioritization_reason and "founding_date_unknown" in lead.prioritization_reason
    hq = by_name(leads)["HoCHQuant"]
    assert hq.location == "Cottbus" and hq.signals[0].date == date(2024, 6, 1)
    assert "Summe: 876.964,00 €" in hq.signals[0].evidence and "Laufzeit: 01.06.2024 bis 30.09.2026" in hq.signals[0].evidence
    assert "Programm: EXIST-Forschungstransfer" in hq.signals[0].evidence
    assert hq.prioritization_reason.startswith("EXIST-Forschungstransfer seit 01.06.2024, 876.964,00 €.")
    press = by_name(leads)["u/press"]
    assert "ehemals „trykk“" in press.description and "EXIST-Gründungsstipendium" in press.description


def test_executing_country_unassigned_and_empty_ort(leads):
    named = by_name(leads)
    aeirmed = named["aeirmed"]                                 # executing unit: Staat "nicht zuzuordnen"
    assert aeirmed.country == "DE" and "executing_country_unassigned" in aeirmed.prioritization_reason
    assert "Staat nicht zuzuordnen" in aeirmed.country_evidence.finding
    empty = next(l for l in leads if l.id == "foekat-03egtbe046")  # executing unit without Ort -> recipient Ort
    assert empty.location == "Berlin"


def test_no_german_party_is_skipped():
    row = rows_of("03EF")[0]
    foreign = fx.GrantRow(**{**row.__dict__, "recipient_staat": "Schweiz", "executing_staat": "Schweiz"})
    run = fx.build_leads(fx.ExportResult(rows=[foreign]))
    assert run.leads == [] and run.skipped_non_de == [row.fkz]


def test_verbund_rows_become_one_lead():
    # Derived from a real row: the 2024+ export has no Verbund, so two partner FKZ are simulated.
    row = rows_of("03EF")[0]
    a = fx.GrantRow(**{**row.__dict__, "fkz": row.fkz + "A"})
    b = fx.GrantRow(**{**row.__dict__, "fkz": row.fkz + "B", "amount": Decimal("100000.00"), "recipient": "Partner e.V."})
    run = fx.build_leads(fx.ExportResult(rows=[b, a]))
    assert len(run.leads) == 1
    lead = run.leads[0]
    assert lead.id == "foekat-" + row.fkz.lower() and [s.evidence[:16] for s in lead.signals] == ["FKZ " + row.fkz + "A;", "FKZ " + row.fkz + "B;"]
    assert "verbund" in lead.prioritization_reason and "976.964,00 €" in lead.description
    named = fx.GrantRow(**{**row.__dict__, "fkz": "03EFXX9001", "projekt": "Verbund HoCHQuant"})
    other = fx.GrantRow(**{**row.__dict__, "fkz": "03EFYY9002", "projekt": "Verbund HoCHQuant"})
    assert len(fx.group_projects([named, other])) == 1


def test_company_recipient_flag():
    row = rows_of("03EF")[0]
    company = fx.GrantRow(**{**row.__dict__, "fkz": "03EFU9XX01", "recipient": "Beispiel Sensorik GmbH", "executing": "Beispiel Sensorik GmbH"})
    lead = fx.build_leads(fx.ExportResult(rows=[company])).leads[0]
    assert "recipient_company" in lead.prioritization_reason and "exist_ft_phase2_candidate" in lead.prioritization_reason
    assert "pre_founding_team" not in lead.prioritization_reason
    assert lead.founding_year is None and lead.founders == []
    macromedia = next(r for r in rows_of("03EG") if r.recipient == "Macromedia GmbH")
    skz = next(r for r in rows_of("03EF") if r.recipient == "SKZ - KFE gGmbH")
    assert not fx.recipient_is_company(macromedia) and not fx.recipient_is_company(skz)


# --- integration with steps 2 and 3 -----------------------------------------------------------------

def test_pipeline_discover_accepts_all_leads(leads):
    total = 0
    for industry in Industry:
        provider = partial(search, fetch=FixtureFetch(), cache=NoCache())
        found = discover(SearchCriteria(industry=industry, limit=200), use_mock=False, provider=provider)
        assert [l.id for l in found] == [l.id for l in leads if l.industry == industry]
        total += len(found)
    assert total == 45


def test_context_light_keeps_leads_and_scoring_input_builds(leads):
    enricher = partial(context.engine.enrich, light=True, load_pages=lambda _: ())
    result = collect_context(leads, use_mock=False, enricher=enricher)
    assert result.issues == [] and len(result.leads) == len(leads)
    for raw, enriched in zip(leads, result.leads):
        assert enriched.model_dump(include=set(RawLead.model_fields)) == raw.model_dump()
        scoring = build_scoring_input(enriched, as_of=date(2026, 11, 20))
        assert scoring.lead_id == raw.id and scoring.country.status == "usable"


def test_determinism_and_cache(tmp_path):
    cache = Cache(tmp_path / "c.db")
    first_fetch = FixtureFetch()
    first = fx.run(fetch=first_fetch, cache=cache, clock=CLOCK)
    later = lambda: datetime(2030, 1, 1, tzinfo=timezone.utc)
    second_fetch = FixtureFetch()
    second = fx.run(fetch=second_fetch, cache=cache, clock=later)
    assert second_fetch.calls == [] and second.export.fetches == 0 and first.export.fetches == 2
    dump = lambda run: TypeAdapter(list[RawLead]).dump_json(run.leads, indent=2)
    assert dump(first) == dump(second)
    assert first.stats() == second.stats()


def test_cli_writes_valid_json_array_and_is_deterministic(tmp_path, monkeypatch):
    from sourcing.__main__ import main
    db = tmp_path / "c.db"
    fx.export_rows(fetch=FixtureFetch(), cache=Cache(db), clock=CLOCK)    # fill the cache, then go offline
    monkeypatch.setattr(fx, "Session", lambda: pytest.fail("network used"))
    out1, out2, stats = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "s.json"
    assert main(["foekat", "--since", "2024-01-01", "--out", str(out1), "--cache", str(db), "--stats", str(stats),
                 "--raw-dir", str(tmp_path / "raw")]) == 0
    assert main(["foekat", "--out", str(out2), "--cache", str(db)]) == 0
    assert out1.read_bytes() == out2.read_bytes()
    leads = TypeAdapter(list[RawLead]).validate_json(out1.read_text(encoding="utf-8"))
    assert len(leads) == 45
    data = json.loads(stats.read_text(encoding="utf-8"))
    assert data["complete"] and data["written"] == 45 and data["queries"][0]["server_count"] == 19
    assert (tmp_path / "raw" / "foekat_03EF_2024-01-01.csv").read_bytes() == csv_bytes("03EF")
    out3 = tmp_path / "health.json"
    assert main(["foekat", "--out", str(out3), "--cache", str(db), "--industry", "health", "--limit", "2", "--programme", "ef"]) == 0
    health = json.loads(out3.read_text(encoding="utf-8"))
    assert len(health) == 2 and {l["industry"] for l in health} == {"HealthTech"}
    # step 2 CLI reads the file unchanged
    import context.__main__ as context_cli
    dossiers = tmp_path / "dossiers.json"
    monkeypatch.setattr(sys, "argv", ["context", str(out1), str(dossiers), "--light", "--offline"])
    context_cli.main()
    assert len(json.loads(dossiers.read_text(encoding="utf-8"))["leads"]) == 45


def test_cli_reports_network_failure(tmp_path, monkeypatch):
    from sourcing.__main__ import main

    class Broken:
        def fetch(self, *a, **k):
            raise FoekatError("URLError")
    monkeypatch.setattr(fx, "Session", Broken)
    assert main(["foekat", "--out", str(tmp_path / "x.json"), "--cache", "off"]) == 2
    assert not (tmp_path / "x.json").exists()
