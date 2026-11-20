from datetime import date
import json
import sqlite3

import pytest
from pydantic import ValidationError

from context.engine import cached_quotes, enrich
from context.market import research_market
from dashboard import contact_url
from evaluation.engine import evaluate
from models import Evidence, Industry, RawLead, SearchCriteria, SourceSignal
from pipeline import collect_context, evaluate_context, run_pipeline
from research_models import MarketIntelligence, MarketMeasure, Period
from scoring import score_dossier
from scoring.__main__ import main as score_cli
from scoring.sources import load_dossiers
from sourcing.engine import read_context_leads

URL = "https://testwerk.example/"
TODAY = date(2026, 11, 20)


def lead(**changes):
    data = dict(id="a", name="Testwerk GmbH", description="Misst den Stromverbrauch.", industry=Industry.CLIMATE,
                country="DE", source_url=URL, website=URL,
                country_evidence=Evidence(source="Register", url=URL, finding="Firmensitz: Köln, Deutschland."),
                signals=[SourceSignal(source="Firma", type="press", date=date(2026, 2, 1), url=URL, evidence="Meldung")])
    return RawLead(**(data | changes))


def offline(raw, as_of=None):
    return enrich(raw, as_of=as_of, load_pages=lambda _: ())


def report_file(tmp_path):
    data = lead().model_dump(mode="json")
    data.update(location="Köln", founders=["Ada Muster"], email="mail@testwerk.example", founding_year=2025,
                founding_month=2, founded_day=12, founding_country="DE")
    data.pop("contact_email")
    fields = ("name", "website", "founders", "email", "founding_year", "founding_month",
              "founding_country", "country", "location", "industry")
    data["field_evidence"] = {field: [
        Evidence(source="Register", url=URL, finding="mail@testwerk.example" if field == "email" else "Testbeleg",
                 field=field).model_dump(mode="json")] for field in fields}
    data["field_evidence"]["country"] = [data["country_evidence"]]
    path = tmp_path / "screening.json"
    path.write_text(json.dumps({"keyword_version": "test", "confirmed": [data],
                                "criteria": {"industry": Industry.CLIMATE.value, "as_of": TODAY.isoformat()}}))
    return path


def test_screening_file_flows_through_default_provider_context_and_scoring(tmp_path, monkeypatch):
    path = report_file(tmp_path)
    monkeypatch.setenv("FOUNDERRADAR_SCREENING_REPORT", str(path))
    imported, = read_context_leads(path)
    result = run_pipeline(SearchCriteria(industry=Industry.CLIMATE), use_mock=False, enricher=offline)
    scored, = result.result.leads
    assert not result.result.issues and scored.scoring_status == "bewertet"
    assert scored.contact_email == imported.contact_email == "mail@testwerk.example"
    assert scored.founded_day == imported.founded_day == 12
    assert scored.scoring_input.as_of == TODAY
    assert scored.field_evidence == imported.field_evidence
    assert scored.field_evidence["email"][0] in scored.evidence
    with pytest.raises(ValueError, match="Branche"):
        run_pipeline(SearchCriteria(industry=Industry.HEALTH), use_mock=False, enricher=offline)

    payload = json.loads(path.read_text())
    payload["confirmed"][0]["email"] = "other@testwerk.example"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="unbelegt"):
        read_context_leads(path)


def test_cli_reads_both_context_formats_with_the_same_lead_and_cutoff(tmp_path):
    enriched = offline(lead(), TODAY)
    report = tmp_path / "context.json"
    from models import ContextResult
    report.write_text(ContextResult(leads=[enriched]).model_dump_json())
    output = tmp_path / "scores"
    assert score_cli([str(report), "--out", str(output)]) == 0
    row, = json.loads((output / "scores.json").read_text())
    assert row["lead_id"] == "a" and row["status"] == "bewertet" and row["stichtag"] == TODAY.isoformat()
    report.write_text(json.dumps([enriched.scoring_input.model_dump(mode="json")]))
    assert score_cli([str(report), "--out", str(output)]) == 0
    row, = json.loads((output / "scores.json").read_text())
    assert row["lead_id"] == "a" and row["stichtag"] == TODAY.isoformat()


def test_wrong_subject_and_future_funding_cannot_change_scoring():
    initial = lead()
    misleading = [
        SourceSignal(source="Presse", type="press", url="https://magazin.example/", date=date(2026, 4, 1),
                     evidence="Unternehmen: Fremd GmbH\nFinanzierungsstatus: VC-finanziert"),
        SourceSignal(source="Firma", type="press", url=URL, date=date(2090, 4, 1),
                     evidence="Finanzierungsstatus: VC-finanziert"),
    ]
    baseline = evaluate_context([offline(initial)], use_mock=False)
    modified = evaluate_context([offline(initial.model_copy(update={"signals": initial.signals + misleading}))], use_mock=False)
    assert not modified.issues
    assert modified.leads[0].overall_score == baseline.leads[0].overall_score


def test_conflicting_dates_and_age_cutoff_and_missing_score_status():
    initial = lead(founding_year=2020)
    claim = SourceSignal(source="Firma", type="press", url=URL, date=date(2026, 4, 1), evidence="Gründungsdatum: 2025-01-01")
    conflict = offline(initial.model_copy(update={"signals": [*initial.signals, claim]}), TODAY)
    assert conflict.scoring_input.founded.status == "conflicting"
    assert evaluate(conflict).stage_classification != "Early Growth"
    assert evaluate(offline(lead(founding_year=2023, founding_month=11, founded_day=19), TODAY)).stage_classification == "Early Growth"
    assert evaluate(offline(lead(founding_year=2023, founding_month=11, founded_day=20), TODAY)).stage_classification != "Early Growth"
    result = evaluate_context([offline(lead(signals=[]), TODAY)], use_mock=False)
    assert result.leads[0].scoring_status == "zurueck_an_sourcing"
    assert result.leads[0].overall_score is None and result.issues[0].lead_id == "a"


def test_contact_and_lead_identity_and_mutation():
    original = lead()
    proof = Evidence(source="Impressum", url=URL, field="contact_email", finding="Kontakt: mail@testwerk.example.")
    enriched = offline(original, TODAY).model_copy(update={"imprint_email": "mail@testwerk.example", "evidence": [proof]})
    assert contact_url(evaluate(enriched)).startswith("mailto:mail@testwerk.example?")
    assert evaluate(enriched).earliness_delta_months == 9
    with pytest.raises(ValueError, match="verschiedenen Leads"):
        evaluate(enriched.scoring_input, lead=enriched.model_copy(update={"id": "b"}))

    def mutate(raw):
        raw.name = "Fremd GmbH"
        return offline(raw, TODAY)

    result = collect_context([original], use_mock=False, enricher=mutate)
    assert not result.leads and result.issues and original.name == "Testwerk GmbH"


def test_sqlite_requires_a_positive_german_seat(tmp_path):
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as connection:
        connection.executescript("CREATE TABLE leads (lead_id, name); "
                                 "CREATE TABLE signals (lead_id, source, url, date, type, evidence);")
        for identity, text in (("a", "Firmensitz: Köln, Deutschland."),
                               ("b", "Registered office: Vienna, Austria. Customers in Germany.")):
            connection.execute("INSERT INTO leads VALUES (?,?)", (identity, identity))
            connection.execute("INSERT INTO signals VALUES (?, 'impressum', ?, '2026-01-01', 'press', ?)",
                               (identity, URL, text))
    a, b = load_dossiers(db)
    assert score_dossier(a, stichtag=TODAY)["status"] == "bewertet"
    assert score_dossier(b, stichtag=TODAY)["status"] == "zurueck_an_sourcing"


def test_market_uses_identical_floor_and_quotes_keep_same_url_snapshots():
    source = Evidence(source="Fixture", url=URL, finding="Marktdaten", verification_status="source_reviewed")

    def measure(value, unit, currency=None):
        return MarketMeasure(value=value, unit=unit, currency=currency, geography="DE", methodology="Fixture",
                             period=Period(start_year=2025, end_year=2025), data_type="observed",
                             evidence_ids=[source.evidence_id])

    market = MarketIntelligence(sources=[source], sizing_inputs={
        "addressable_companies": measure(100, "Unternehmen"),
        "annual_revenue_per_company": measure(1_000, "pro Unternehmen und Jahr", "EUR"),
        "serviceable_share": measure(.29, "Anteil"),
    })
    enriched = research_market(offline(lead(), TODAY), market)
    assert enriched.context_v2.market_intelligence.sam.value == enriched.scoring_input.sam.value == 29_000

    old, new = [SourceSignal(source="Firma", type="press", url=URL, evidence=text) for text in ("Altes Zitat", "Neues Zitat")]
    extractor = cached_quotes(lambda name, items, fields: [(fields[0], "Altes Zitat", items[0])], None)
    assert extractor("Testwerk", [old, new], ("solution",)) == [("solution", "Altes Zitat", old)]
