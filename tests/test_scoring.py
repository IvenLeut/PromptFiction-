import copy
import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scoring import load_config, score_all, score_dossier
from scoring.__main__ import main, validate
from scoring.sources import load_dossiers

LEADS = Path(__file__).parent.parent / "scoring" / "testleads" / "dummy_leads.json"
TAG = "2026-11-20"


@pytest.fixture(scope="module")
def rows():
    return {r["lead_id"]: r for r in score_all(load_dossiers(LEADS), stichtag=TAG)}


def dossier(lead_id):
    return copy.deepcopy(next(d for d in load_dossiers(LEADS) if d["lead_id"] == lead_id))


def test_schema_valid_and_ranges(rows):
    validate(list(rows.values()))
    for r in rows.values():
        if r["status"] == "bewertet":
            for feld in ("risiko_score", "marktpotenzial_score", "team_score", "gesamt_score"):
                assert 0 <= r[feld] <= 100
        assert 0 <= r["confidence"] <= 1
        assert len(r["produktbeschreibung"]) <= 300 and len(r["value_proposition"]) <= 200 and len(r["investmenthypothese"]) <= 400


def test_formula_matches_config(rows):
    g = load_config()["gewichte"]
    r = rows["dummy-software"]
    erwartet = g["team"] * r["team_score"] + g["marktpotenzial"] * r["marktpotenzial_score"] + g["risiko_invers"] * (100 - r["risiko_score"])
    assert r["gesamt_score"] == pytest.approx(erwartet, abs=0.06)


def test_three_cases_and_stages(rows):
    assert rows["dummy-software"]["stage"] == "in_gruendung"
    assert rows["dummy-deeptech"]["stage"] == "pre_gruendung"
    assert rows["dummy-lifesciences"]["stage"] == "pre_seed"
    assert rows["dummy-deeptech"]["gruendung_ist_proxy"] is True
    assert rows["dummy-lifesciences"]["gruendung_ist_proxy"] is False


def test_deterministic():
    a = score_all(load_dossiers(LEADS), stichtag=TAG)
    b = score_all(load_dossiers(LEADS), stichtag=TAG)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_missing_data_is_neutral_and_lowers_confidence(rows):
    r = rows["dummy-nur-pflicht"]
    assert r["team_score"] == 50 and r["marktpotenzial_score"] == 50
    assert r["confidence"] < 0.2 < rows["dummy-software"]["confidence"]
    assert any(e["url"] is None and "keine Daten" in e["aussage"] for e in r["evidence"])


def test_every_counted_subscore_has_url(rows):
    for r in rows.values():
        for e in r["evidence"]:
            belegt = r["teilwerte"].get(e["dimension"], {}).get(e["kriterium"], {}).get("belegt")
            if belegt:
                assert e["url"] and e["url"].startswith("http")
            elif e["dimension"] in ("team", "marktpotenzial", "risiko"):
                assert e["punkte"] == 50 and e["url"] is None


def test_unsourced_claims_do_not_count(rows):
    r = rows["dummy-unbelegte-behauptungen"]
    assert r["team_score"] == 50 and r["marktpotenzial_score"] == 50
    assert r["stage"] == "pre_seed"            # unbelegter Reifegrad "erste_kunden" hebt die Stage nicht auf seed
    assert r["confidence"] < 0.1
    assert "unsicher" in next(e["aussage"] for e in r["evidence"] if e["kriterium"] == "datenlage")
    for text in (r["investmenthypothese"], r["why_now"], json.dumps(r["evidence"], ensure_ascii=False)):
        assert "Großkunde" not in text and "Angebliche" not in text and "40 Papers" not in text


def test_hard_exclusions(rows):
    for lead_id, grund in (("dummy-agentur", "agentur"), ("dummy-finanziert", "bereits_finanziert"),
                           ("dummy-solo-hobby", "hobby"), ("dummy-zu-alt", "zu_spaet")):
        assert rows[lead_id]["gesamt_score"] <= 20 and grund in rows[lead_id]["ausschluss_grund"]
    assert rows["dummy-zu-alt"]["branche"] == "chemie_materialien"


def test_missing_mandatory_goes_back_to_sourcing(rows):
    r = rows["dummy-ohne-beleg"]
    assert r["status"] == "zurueck_an_sourcing" and r["gesamt_score"] is None and r["confidence"] == 0.1


def test_personal_email_is_dropped(rows):
    assert rows["dummy-software"]["email"] == "info@example.org"
    assert rows["dummy-lifesciences"]["email"] == ""


def test_monotonic():
    """Bessere belegte Fakten dürfen den Gesamtscore nie senken."""
    base = dossier("dummy-deeptech")
    start = score_dossier(base, stichtag=TAG)
    besser = copy.deepcopy(base)
    besser["reifegrad"]["wert"] = "pilot"
    assert score_dossier(besser, stichtag=TAG)["risiko_score"] < start["risiko_score"]
    besser = copy.deepcopy(base)
    besser["team"].append({"name": "Dummy BWL", "hintergrund": "business", "quelle": "https://example.org/team"})
    assert score_dossier(besser, stichtag=TAG)["team_score"] > start["team_score"]
    besser = copy.deepcopy(base)
    besser["partner"].append({"name": "Dummy Kunde", "typ": "kunde", "quelle": "https://example.org/kunde"})
    assert score_dossier(besser, stichtag=TAG)["marktpotenzial_score"] > start["marktpotenzial_score"]


def test_garbage_input_does_not_crash():
    for kaputt in ({}, None, 5, "x", [1], {"name_unternehmen": 5, "team": "x", "signals": [1, {"url": "kein-url", "datum": "gestern"}], "foerderung": [None]},
                   {"name_unternehmen": "X", "markt": {"volumen_eur": "viel"}, "partner": [{"typ": "kunde"}], "team": [{"name": None}]}):
        r = score_dossier(kaputt, stichtag=TAG)
        assert r["status"] == "zurueck_an_sourcing"


def test_config_weights_are_checked(tmp_path):
    cfg = Path(__file__).parent.parent / "scoring" / "scoring_config.yaml"
    kaputt = tmp_path / "c.yaml"
    kaputt.write_text(cfg.read_text(encoding="utf-8").replace("team: 0.35", "team: 0.5", 1), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(kaputt)


def test_cli_writes_files(tmp_path):
    assert main([str(LEADS), "--out", str(tmp_path), "--stichtag", TAG]) == 0
    data = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    with open(tmp_path / "scores.csv", encoding="utf-8", newline="") as f:
        zeilen = list(csv.DictReader(f))
    assert len(data) == len(zeilen) == 10 and (tmp_path / "scores.schema.json").exists()
    assert [z["lead_id"] for z in zeilen] == [d["lead_id"] for d in data]
    assert json.loads(zeilen[0]["evidence"]) == data[0]["evidence"]


def test_sqlite_source(tmp_path):
    db = tmp_path / "leads.db"
    con = sqlite3.connect(str(db))
    con.executescript("""
        CREATE TABLE leads(lead_id, name, website, impressum_url, rechtsform, htgf_bereich, noise_class, confidence,
                           first_signal_date, first_db_date, earliness_delta, in_databases, match_confidence);
        CREATE TABLE signals(lead_id, source, url, date, type, evidence);
        CREATE TABLE team(lead_id, name, rolle, institut, openalex_url);
        INSERT INTO leads VALUES('dbtest','DB-Test (Dummy)',NULL,NULL,NULL,'Life Sciences','vc_potenzial',0.8,'2025-05-01',NULL,NULL,0,0.9);
        INSERT INTO signals VALUES('dbtest','foekat','https://example.com/fk/1','2025-05-01','exist_forschungstransfer',
                                   'EXIST-Forschungstransfer DB-Test, Dummy-Uni Jena, 650.000 EUR');
        INSERT INTO team VALUES('dbtest','Dummy Leiterin','Projektleitung','Dummy-Uni Jena','https://example.net/oa/1');
    """)
    con.commit()
    con.close()
    (r,) = score_all(load_dossiers(db), stichtag=TAG)
    validate([r])
    assert r["status"] == "bewertet" and r["branche"] == "life_sciences" and r["stage"] == "pre_gruendung"
    assert r["name_gruender"] == "Dummy Leiterin" and r["earliness_delta_monate"] == 18
    assert r["teilwerte"]["risiko"]["finanzierung"]["belegt"] and r["teilwerte"]["team"]["vollzeit"]["belegt"]


def test_evaluation_engine_fits_pipeline_contract():
    from evaluation.engine import evaluate
    from models import Industry, SearchCriteria
    from pipeline import run_pipeline
    run = run_pipeline(SearchCriteria(industry=Industry.HEALTH, limit=30), evaluator=evaluate)
    assert not run.result.issues and len(run.result.leads) == 30
    for lead in run.result.leads:
        assert lead.overall_score is not None and 0 <= lead.risk_score <= 100
        assert lead.value_proposition and lead.investment_thesis and lead.open_questions
    again = run_pipeline(SearchCriteria(industry=Industry.HEALTH, limit=30), evaluator=evaluate)
    assert [(x.id, x.overall_score) for x in again.result.leads] == [(x.id, x.overall_score) for x in run.result.leads]


U = "https://example.org/x"


def basis(**extra):
    d = {"lead_id": "t", "name_unternehmen": "T", "beschreibung_rohtext": {"wert": "T baut Dinge.", "quelle": U},
         "deutschland_beleg": {"wert": "Berlin", "quelle": U}, "signals": [{"typ": "website", "url": U, "datum": "2026-09-01"}]}
    d.update(extra)
    return d


def kern(r):
    return (r["team_score"], r["marktpotenzial_score"], r["risiko_score"], r["gesamt_score"], r["confidence"], r["stage"],
            r["noise_class"], r["gruendungsjahr"], r["investmenthypothese"], r["why_now"], r["value_proposition"])


@pytest.mark.parametrize("unbelegt", [
    {"team": [{"name": "N", "rolle": "CEO", "hintergrund": "business", "papers_im_feld": 40, "vorerfahrung": ["fruehere_gruendung"]},
              {"name": "O", "hintergrund": "tech", "papers_im_feld": 25}],
     "signals": [{"typ": "website", "url": U, "datum": "2026-09-01"}, {"typ": "impressum", "url": U + "/impressum", "datum": "2026-09-01"}]},
    {"foerderung": [{"programm": "Angebliche Förderung", "summe_eur": 5000000, "start": "2019-01-01", "ende": "2027-03-01"},
                    {"programm": "EXIST-Gründungsstipendium"}],
     "signals": [{"typ": "website", "url": U, "datum": "2026-09-01"}, {"typ": "exist_projekt", "url": U, "datum": "2026-09-01"}]},
    {"funding_meldung": True}, {"repo_art": "kurs"}, {"website_text": "leistungen referenzen agentur"}, {"team": [{"name": "Solo"}]},
    {"rechtsform": "GmbH"}, {"gruendungsdatum": "2020-01-01"}, {"reifegrad": "erste_kunden"}, {"ip": "patent_erteilt"},
    {"problem": "Krebs ist unheilbar", "loesung": "Unsere Pille heilt Krebs", "nutzen": "100 Mrd. EUR Umsatz"},
    {"produkt_typ": "software", "markt": {"zielkunde": "NASA", "modell": "b2b", "volumen_eur": 9e10}, "regulierter_markt": False},
    {"mix_tech_business": True, "team": [{"name": "A"}, {"name": "B"}]},
    {"partner": [{"name": "Großkunde", "typ": "kunde"}], "wettbewerber": [{"name": "W"}]},
    {"vollzeit_signal": True}, {"email": "info@example.org", "website": U},
])
def test_unsourced_fields_change_nothing(unbelegt):
    """Review-Befunde 1-5: Ohne eigene Quelle darf kein Feld Score, Stage, Ausschluss oder Text bewegen."""
    mit = score_dossier(basis(**unbelegt), stichtag=TAG)
    ohne = score_dossier(basis(signals=unbelegt.get("signals", basis()["signals"])), stichtag=TAG)
    assert kern(mit) == kern(ohne)
    assert mit["email"] == "" and mit["name_gruender"] == ""
    assert all(e["url"] is None for e in mit["evidence"] if e["kriterium"] != "datenlage")


def test_branche_label_does_not_move_scores():
    a, b = score_dossier(basis(branche="life_sciences"), stichtag=TAG), score_dossier(basis(branche="digital_tech"), stichtag=TAG)
    assert a["branche"] == "life_sciences" and kern(a) == kern(b)


def test_existenzkredit_is_not_exist():
    r = score_dossier(basis(foerderung=[{"programm": "Existenzgründerkredit der Hausbank", "quelle": U, "start": "2026-01-01"}]), stichtag=TAG)
    assert not r["teilwerte"]["team"]["vollzeit"]["belegt"] and r["gruendungsjahr"] is None


def test_hypothesis_wording(rows):
    leer = score_dossier(basis(), stichtag=TAG)["investmenthypothese"]
    assert leer == "Datenlage zu dünn für eine Hypothese (Confidence 0.03). Hauptrisiko: Dünne Datenlage: nur eine unabhängige Quelle."
    assert all("Technologierisiko" not in r["investmenthypothese"] for r in rows.values())
    assert "Nächster Meilenstein: ein Prototyp beim Anwender." in rows["dummy-deeptech"]["investmenthypothese"]
    assert rows["dummy-agentur"]["investmenthypothese"].startswith("Kein Investment-Case")
    assert "Wir investieren" not in rows["dummy-finanziert"]["investmenthypothese"]
    gut = score_dossier(basis(regulierter_markt={"wert": False, "quelle": U},
                              signals=[{"url": "https://a.example.org/1", "datum": "2026-01-01"}, {"url": "https://b.example.com/1", "datum": "2026-01-01"},
                                       {"url": "https://c.example.net/1", "datum": "2026-01-01"}]), stichtag=TAG)
    assert "Kein Risikofaktor ab 50 Punkten belegt" in gut["investmenthypothese"]


def test_fuzz_never_crashes_and_stays_schema_valid():
    import itertools
    import random
    rnd = random.Random(7)
    muell = [None, 5, True, -1, 10 ** 400, float("nan"), float("inf"), "", "x", "https://[a.b/c", "https://a.de/x\njunk", [], {}, [None, 5, "x", {}],
             {"wert": [1]}, {"wert": {"a": 1}, "quelle": U}, {"wert": "software", "quelle": U}, {"wert": "1700-01-01", "quelle": U},
             {"wert": "2999-01-01", "quelle": U}, "量子", [{"name": 5, "quelle": U, "typ": [1], "summe_eur": 10 ** 400, "programm": "EXIST", "start": "2030-01-01"}]]
    felder = ["lead_id", "name_unternehmen", "beschreibung_rohtext", "deutschland_beleg", "website", "email", "branche", "rechtsform",
              "gruendungsdatum", "team", "reifegrad", "produkt_typ", "regulierter_markt", "markt", "partner", "wettbewerber", "ip",
              "foerderung", "in_databases", "first_db_date", "match_confidence", "signals", "source_url", "noise_class", "funding_meldung",
              "website_text", "repo_art", "mix_tech_business", "vollzeit_signal"]
    faelle = [basis(**{f: m}) for f, m in itertools.product(felder, muell)]
    faelle += [basis(markt={k: m}) for k in ("zielkunde", "modell", "volumen_eur") for m in muell]
    faelle += [{f: rnd.choice(muell) for f in felder} for _ in range(300)]
    rows = score_all(faelle + [None, 5, "x"], stichtag=TAG)
    assert len(rows) == len(faelle) + 3 and len({r["lead_id"] for r in rows}) == len(rows)
    validate(rows)


def test_bad_row_does_not_kill_cli(tmp_path, capsys):
    quelle = tmp_path / "in.json"
    quelle.write_text(json.dumps([basis(), basis(lead_id="u", website="https://a.de/x\njunk"), basis(lead_id=""), basis(lead_id="")]), encoding="utf-8")
    assert main([str(quelle), "--out", str(tmp_path / "o"), "--stichtag", TAG]) == 0
    data = json.loads((tmp_path / "o" / "scores.json").read_text(encoding="utf-8"))
    assert len(data) == 4 and sorted(r["lead_id"] for r in data) == ["t", "t-dup2", "t-dup3", "u"]
    assert sorted(r["lead_id"] for r in score_all([basis(), basis(), basis(lead_id="t-dup2")], stichtag=TAG)) == ["t", "t-dup2", "t-dup3"]
    with pytest.raises(SystemExit):
        main([str(quelle), "--out", str(tmp_path / "o"), "--stichtag", "2026"])
    with pytest.raises(SystemExit):
        main([str(tmp_path / "gibt-es-nicht.db"), "--out", str(tmp_path / "o")])
    with pytest.raises(SystemExit):
        main([str(quelle), "--out", str(tmp_path / "o"), "--stichtag", "morgen"])


def test_dates_and_rounding():
    from scoring.engine import parse_date, r1
    assert parse_date("20261120") is None and parse_date("2026/11/20") is None and parse_date("12345-01-01") is None
    assert str(parse_date("01.05.2025")) == "2025-05-01" and str(parse_date("2025-05")) == "2025-05-01"
    assert r1(36.25) == 36.3 and r1(0.3625 * 100) == 36.3
    zukunft = score_dossier(basis(signals=[{"url": U, "datum": "2031-01-01"}]), stichtag=TAG)
    assert zukunft["status"] == "zurueck_an_sourcing"


def test_sqlite_loader_edge_cases(tmp_path):
    from scoring.sources import _bool, _summe_eur
    assert _summe_eur("Summe 1.200.000,00 EUR") == 1200000 and _summe_eur("650.000 EUR") == 650000 and _summe_eur("800000 €") == 800000
    assert _summe_eur("keine Angabe") is None
    for unklar in ("650,000 EUR", "1 200 000 EUR", "650'000 EUR", "12.50 EUR", "bis zu 3.000 EUR monatlich, gesamt 150.000 EUR"):
        assert _summe_eur(unklar) is None, unklar
    assert _summe_eur("150.000 EUR bewilligt, insgesamt 150.000,00 €") == 150000
    assert _bool("0") is False and _bool("1") is True and _bool(0) is False and _bool(None) is None and _bool("vielleicht") is None
    db = tmp_path / "x.db"
    con = sqlite3.connect(str(db))
    con.executescript("""
        CREATE TABLE leads(name, in_databases);
        INSERT INTO leads VALUES(NULL, '0'); INSERT INTO leads VALUES('量子', '0'); INSERT INTO leads VALUES('', NULL);
    """)
    con.commit()
    con.close()
    rows = score_all(load_dossiers(db), stichtag=TAG)
    validate(rows)
    assert len(rows) == 3 and all(r["status"] == "zurueck_an_sourcing" for r in rows)


def test_adapter_translates_only_exact_and_sourced_values():
    from datetime import datetime, timezone
    from evaluation.engine import evaluate
    from models import EnrichedLead, Evidence, Industry
    ev = Evidence(source="Demo", url="https://example.org/a", finding="Sitz in Berlin", field="country",
                  retrieved_at=datetime(2026, 11, 20, tzinfo=timezone.utc))
    def lead(**extra):
        from models import SourceSignal
        sig = SourceSignal(source="Sourcing", type="fund", url="https://example.org/a", date=datetime(2026, 9, 1).date(), evidence="Fund")
        return EnrichedLead(**dict(dict(id="a", name="A", description="A baut Dinge.", industry=Industry.AI, country="DE",
                                        source_url="https://example.org/a", country_evidence=ev, evidence=[ev], signals=[sig]), **extra))
    basis_lead = evaluate(lead())
    assert basis_lead.overall_score is not None and basis_lead.stage_classification == "Pre-Seed"
    for extra in ({"product_stage": "Marktforschung läuft"}, {"product_stage": "Pilot abgeschlossen, Konzept für Serie"},
                  {"product_stage": "Pilot"}, {"funding_stage": "Vor Series A, bootstrapped"}, {"funding_stage": "Series A"},
                  {"funding_total_eur": 9e6}, {"customer_count": 12}, {"founders": ["Solo"]}):
        r = evaluate(lead(**extra))
        assert (r.risk_score, r.market_potential_score, r.stage_classification) == (
            basis_lead.risk_score, basis_lead.market_potential_score, basis_lead.stage_classification), extra
        assert r.overall_score > 20
    prod = Evidence(source="Demo", url="https://example.org/a/p", finding="Pilot läuft", field="product_stage", retrieved_at=ev.retrieved_at)
    assert evaluate(lead(product_stage="Pilot", evidence=[ev, prod])).risk_score < basis_lead.risk_score
    assert evaluate(lead(founding_year=2023)).stage_classification == "Pre-Seed"
    assert evaluate(lead(founding_year=2022)).stage_classification == "Early Growth"
    from datetime import date
    assert evaluate(lead(founded_on=date(2020, 1, 1))).stage_classification == "Pre-Seed"      # Schritt-2-Feld ohne Evidence zählt nicht
    spaet = Evidence(source="Demo", url="https://example.org/a/f", finding="Runde", field="last_funding_on", retrieved_at=ev.retrieved_at)
    assert evaluate(lead(funding_stage="Series A", evidence=[ev, spaet])).overall_score > 20      # falsches Evidence-Feld schaltet nichts frei
    echt = Evidence(source="Demo", url="https://example.org/a/f", finding="Series A", field="funding_stage", retrieved_at=ev.retrieved_at)
    assert evaluate(lead(funding_stage="Series A", evidence=[ev, echt])).overall_score <= 20


def test_round_two_findings(tmp_path):
    q = {"quelle": U}
    # Jahr ohne Monat: kein erfundener Monat, Alter wird nicht überschätzt
    r = score_dossier(basis(gruendungsdatum={"wert": "2023", **q}, rechtsform={"wert": "GmbH", **q}), stichtag=TAG)
    assert (r["gruendungsjahr"], r["gruendungsmonat"], r["stage"]) == (2023, None, "pre_seed")
    assert score_dossier(basis(gruendungsdatum={"wert": "2022", **q}), stichtag=TAG)["stage"] == "zu_spaet"
    # Earliness
    assert score_dossier(basis(first_db_date="2024-01-01"), stichtag=TAG)["earliness_delta_monate"] == 0
    assert score_dossier(basis(first_db_date="2027-06-01"), stichtag=TAG)["earliness_delta_monate"] == 2
    # Rechtsform nur aus der bekannten Liste
    for rf, stage in (("unbekannt", "pre_gruendung"), ("e.V.", "pre_gruendung"), ("GbR", "pre_gruendung"), ("Ski. GmbH", "pre_seed"),
                      ("UG (haftungsbeschränkt) i.G.", "in_gruendung"), ("GmbH in Gründung", "in_gruendung")):
        assert score_dossier(basis(rechtsform={"wert": rf, **q}), stichtag=TAG)["stage"] == stage, rf
    # Agentur-Regel zählt nur ganze Wörter
    for harmlos in ("Wir bieten Dienstleistungen rund um Quantensensoren.", "Produktportfolio und Referenzen", "Kundenberatung per Consulting-Hotline"):
        assert score_dossier(basis(website_text={"wert": harmlos, **q}), stichtag=TAG)["noise_class"] == "vc_potenzial", harmlos
    # Solo-Forscher mit Substanz ist kein Hobby
    solo = basis(rechtsform={"wert": "keine", **q}, team=[{"name": "F", "papers_im_feld": 14, **q}])
    assert score_dossier(solo, stichtag=TAG)["noise_class"] == "vc_potenzial"
    assert score_dossier(basis(rechtsform={"wert": "keine", **q}, team=[{"name": "F", **q}]), stichtag=TAG)["noise_class"] == "hobby"
    # EXIST nur als Programmname, nicht in der Zukunft, dieselbe Quelle nur einmal
    for programm, start, erwartet in (("kein EXIST", "2026-01-01", False), ("EXIST-Antrag abgelehnt", "2026-01-01", False),
                                      ("EXIST_Forschungstransfer", "2026-01-01", True), ("EXIST-Gründungsstipendium", "2028-01-01", False)):
        r = score_dossier(basis(foerderung=[{"programm": programm, "start": start, **q}]), stichtag=TAG)
        assert r["teilwerte"]["team"]["vollzeit"]["belegt"] is erwartet, programm
    doppelt = score_dossier(basis(foerderung=[{"programm": "X", "summe_eur": 100000, **q}] * 3), stichtag=TAG)
    assert "100.000 EUR" in json.dumps(doppelt["evidence"], ensure_ascii=False)
    # Reihenfolge im Input ändert nichts
    a = dossier("dummy-lifesciences")
    b = copy.deepcopy(a)
    for feld in ("team", "signals", "partner", "foerderung"):
        b[feld] = list(reversed(b[feld]))
    assert score_dossier(a, stichtag=TAG) == score_dossier(b, stichtag=TAG)
    # Kaputte Zeichen, Nicht-String-Schlüssel, Abkürzungen, Semikolon im Namen
    assert score_dossier({1: 2, "a": 3}, stichtag=TAG)["status"] == "zurueck_an_sourcing"
    r = score_dossier(basis(lead_id="x\ud83d", name_unternehmen="=SUMME(A1)\ud83d",
                            beschreibung_rohtext={"wert": "Das Team um Dr. Muster baut z. B. Sensoren. Zweiter Satz.", **q},
                            team=[{"name": "A;B", "rolle": "Postdoctoral researcher", **q}, {"name": "C", "rolle": "CTO", **q}]), stichtag=TAG)
    assert r["value_proposition"] == "Das Team um Dr. Muster baut z. B. Sensoren." and r["name_gruender"] == "C"
    quelle = tmp_path / "in.json"
    quelle.write_text(json.dumps([basis(lead_id="x\ud83d", name_unternehmen="=SUMME(A1)"), basis(lead_id="y", name_unternehmen="@x")]), encoding="utf-8")
    assert main([str(quelle), "--out", str(tmp_path), "--stichtag", TAG]) == 0
    with open(tmp_path / "scores.csv", encoding="utf-8", newline="") as f:
        assert sorted(z["name_unternehmen"] for z in csv.DictReader(f)) == ["'=SUMME(A1)", "'@x"]
    assert not is_url_ok("https://-.-") and not is_url_ok("https://x.y/<script>") and is_url_ok("https://example.org/a?b=1")


def is_url_ok(u):
    from scoring.engine import is_url
    return is_url(u)


def test_sqlite_loader_does_not_invent_exist(tmp_path):
    db = tmp_path / "k.db"
    con = sqlite3.connect(str(db))
    con.executescript("""
        CREATE TABLE leads(lead_id, name); CREATE TABLE signals(lead_id, source, url, date, type, evidence);
        INSERT INTO leads VALUES('k', 'Kredit (Dummy)');
        INSERT INTO signals VALUES('k', 'kfw', 'https://example.org/k', '2025-05-01', 'existenzgruender_kredit', 'Kredit 50.000 EUR');
        INSERT INTO leads VALUES('f', 'Foekat (Dummy)');
        INSERT INTO signals VALUES('f', 'foekat', 'https://example.org/f1', '2025-05-01', 'foerderprojekt', 'FKZ 03EF9999X, 100.000 EUR');
        INSERT INTO signals VALUES('f', 'foekat', 'https://example.org/f1', '2025-05-01', 'foerderprojekt', 'FKZ 03EF9999X, 100.000 EUR');
    """)
    con.commit()
    con.close()
    k, f = (next(d for d in load_dossiers(db) if d["lead_id"] == i) for i in ("k", "f"))
    assert k["foerderung"] == []
    assert f["foerderung"][0]["programm"] == "EXIST-Forschungstransfer"
    r = score_dossier(f, stichtag=TAG)
    assert "100.000 EUR" in json.dumps(r["evidence"], ensure_ascii=False) and r["teilwerte"]["team"]["vollzeit"]["belegt"]


def test_round_three_findings(tmp_path):
    q = {"quelle": U}
    # Beschreibung braucht ihre eigene Quelle; source_url ist kein Ersatz
    r = score_dossier(basis(beschreibung_rohtext="T baut Dinge.", source_url="https://other.de/y"), stichtag=TAG)
    assert r["status"] == "zurueck_an_sourcing" and r["produktbeschreibung"] == ""
    # Zwei verschiedene Förderungen auf derselben Katalog-URL bleiben beide erhalten, unabhängig von der Reihenfolge
    zwei = [{"programm": "ZIM", "summe_eur": 200000, "start": "2025-01-01", **q},
            {"programm": "EXIST-Forschungstransfer", "summe_eur": 800000, "start": "2025-06-01", **q}]
    a, b = score_dossier(basis(foerderung=zwei), stichtag=TAG), score_dossier(basis(foerderung=zwei[::-1]), stichtag=TAG)
    assert a == b and a["teilwerte"]["team"]["vollzeit"]["belegt"] and "1,0 Mio. EUR" in json.dumps(a["evidence"], ensure_ascii=False)
    eine = score_dossier(basis(foerderung=zwei[:1]), stichtag=TAG)
    assert a["confidence"] >= eine["confidence"]
    # Aus Jahr oder Monat wird kein Tag erfunden
    assert score_dossier(basis(signals=[{"url": U, "datum": "2025"}]), stichtag=TAG)["status"] == "zurueck_an_sourcing"
    assert score_dossier(basis(first_db_date="2026"), stichtag=TAG)["earliness_delta_monate"] == 2
    jahr = score_dossier(basis(reifegrad={"wert": "pilot", "datum": "2025", **q}), stichtag=TAG)
    assert next(e for e in jahr["evidence"] if e["kriterium"] == "tech_reife")["datum"] is None
    # Rechtsform: Verneinungen, Pläne und Nicht-Firmen zählen nicht; Schreibweisen werden erkannt
    for rf, stage in (("noch keine GmbH", "pre_gruendung"), ("GmbH geplant", "pre_gruendung"), ("UG-Gründung geplant", "pre_gruendung"),
                      ("AG Müller (Arbeitsgruppe)", "pre_gruendung"), ("GmbH i.Gr.", "in_gruendung"), ("Muster GmbH i. G", "in_gruendung"),
                      ("gmbh", "pre_seed"), ("Muster GMBH", "pre_seed"), ("Muster UG (haftungsbeschränkt)", "pre_seed"), ("Muster AG", "pre_seed")):
        assert score_dossier(basis(rechtsform={"wert": rf, **q}), stichtag=TAG)["stage"] == stage, rf
    # EXIST ohne Enddatum zählt nicht ewig
    alt = score_dossier(basis(foerderung=[{"programm": "EXIST-Forschungstransfer", "start": "2015-01-01", **q}]), stichtag=TAG)
    assert not alt["teilwerte"]["team"]["vollzeit"]["belegt"] and alt["gruendungsjahr"] is None
    # Satzgrenzen und Rollen
    r = score_dossier(basis(beschreibung_rohtext={"wert": "Gegründet am 3. Mai 2024 in Berlin von der Fa. Muster. Zweiter Satz.", **q},
                            team=[{"name": "A", "rolle": "Kein Gründer", **q}, {"name": "B", "rolle": "ehem. Geschäftsführer", **q},
                                  {"name": "C", "rolle": "Gründerin", **q}]), stichtag=TAG)
    assert r["value_proposition"] == "Gegründet am 3. Mai 2024 in Berlin von der Fa. Muster." and r["name_gruender"] == "C"
    # Lader: Betrag hinter dem Währungszeichen ist nicht eindeutig; eine Förderung über mehrere URLs zählt einmal
    from scoring.sources import _summe_eur
    assert _summe_eur("Preisgeld 500 €; Fördersumme € 1.200.000") is None
    db = tmp_path / "m.db"
    con = sqlite3.connect(str(db))
    con.executescript("""
        CREATE TABLE leads(lead_id, name); CREATE TABLE signals(lead_id, source, url, date, type, evidence);
        INSERT INTO leads VALUES('m', 'Mehrfach (Dummy)'); INSERT INTO leads VALUES('x', CAST(x'ff41' AS TEXT));
        INSERT INTO signals VALUES('m', 'foekat', 'https://example.org/a', '2025-05-01', 'exist_forschungstransfer', 'FKZ 03EF1111A, 650.000 EUR');
        INSERT INTO signals VALUES('m', 'foekat', 'https://example.org/b', '2025-05-02', 'foerderprojekt', 'FKZ 03EF1111A, 650.000 EUR');
        INSERT INTO signals VALUES('m', 'idw', 'https://example.net/c', '2025-06-01', 'exist', 'Förderkennzeichen 03EF1111A');
    """)
    con.commit()
    con.close()
    rows = {r["lead_id"]: r for r in score_all(load_dossiers(db), stichtag=TAG)}
    assert len(rows) == 2 and "650.000 EUR" in json.dumps(rows["m"]["evidence"], ensure_ascii=False)
    # Ordner: kaputte Datei und BOM
    ordner = tmp_path / "d"
    ordner.mkdir()
    (ordner / "a.json").write_text("{kaputt", encoding="utf-8")
    (ordner / "b.json").write_text(json.dumps([basis()]), encoding="utf-8-sig")
    assert len(load_dossiers(ordner)) == 1
    with pytest.raises(SystemExit):
        main([str(ordner), "--out", str(tmp_path / "o"), "--config", str(tmp_path / "fehlt.yaml")])
