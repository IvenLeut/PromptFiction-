"""Regression tests for the sourcing/mapping.py review fixes: classification basis, priority, labelled signal
evidence, product-text description, person-name stripping, search() semantics and the CLI options.
Offline: rows are built from the recorded fixture row 03EFBB0063 with fields replaced (marked synthetic)."""
import inspect
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

import context.engine
import sourcing.foekat_export as fx
import sourcing.mapping as mp
from context.cache import Cache, NoCache
from models import Industry, SearchCriteria
from sourcing.engine import search
from test_sourcing_foekat import FixtureFetch, csv_bytes

CLOCK = lambda: datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
AS_OF = date(2026, 11, 20)
NEUTRAL = dict(executing="Lehrstuhl X", recipient="Stiftung Y")
FIRST = fx.parse_export(csv_bytes("03EF"))[0]


def grant(**changes) -> fx.GrantRow:
    base = fx.GrantRow.from_dict(FIRST, CLOCK())
    return fx.GrantRow(**{**base.__dict__, **changes})


def mapped(**changes):
    return mp.map_project([grant(**changes)], AS_OF)


# --- 5. person names (catalogue strings from examples/sourcing/shortlist.json, names pseudonymised) ---

PERSON_CASES = [
    ("Technische Universität Darmstadt Prof. Dr. Erika Muster, FG Entrepreneurship",
     "Technische Universität Darmstadt, FG Entrepreneurship"),
    ("Kirchhoff Institut für Physik - Neuromorphic Quantumphotonics, Prof. Dr. Max Mustermann",
     "Kirchhoff Institut für Physik - Neuromorphic Quantumphotonics"),
    ("Universität Bremen - Fachbereich 03 Mathematik - Informatik - Maschinelles Lernen in der Statistik - Prof. Dr. Jan Beispiel",
     "Universität Bremen - Fachbereich 03 Mathematik - Informatik - Maschinelles Lernen in der Statistik"),
    ("Technische Universität Braunschweig, Institut für Mechanik und Adaptronik, Herr Prof. Dr.-Ing. Erik Bär",
     "Technische Universität Braunschweig, Institut für Mechanik und Adaptronik"),
    ("Technische Hochschule Köln Fakultät für Fakultät für Anlagen, Energie- und Maschinensysteme Prof. Dr. Jörg Musterle",
     "Technische Hochschule Köln Fakultät für Fakultät für Anlagen, Energie- und Maschinensysteme"),
    ("Prof. Dr. Jörn Beispielmann | Direktor HNO-Klinik des Universitätsklinikum Düsseldorf | Medizinische Fakultät der Heinrich-Heine-Universität",
     "Direktor HNO-Klinik des Universitätsklinikum Düsseldorf | Medizinische Fakultät der Heinrich-Heine-Universität"),
    ("Universität Kassel, FB 15 Maschinenbau, Institut für Werkstofftechnik, FG Kunststofftechnik Prof. Dr.-Ing. Hans-Peter Muster",
     "Universität Kassel, FB 15 Maschinenbau, Institut für Werkstofftechnik, FG Kunststofftechnik"),
    ("Universität Augsburg, Lehrstuhl für Experimentalphysik VI, Prof. Dr. Erika Musterfrau",
     "Universität Augsburg, Lehrstuhl für Experimentalphysik VI"),
    ("Universität Leipzig, Biotechnologisch-Biomedizinisches Zentrum Professur für Biochemische Zelltechnologie Professur Dr. Max Muster",
     "Universität Leipzig, Biotechnologisch-Biomedizinisches Zentrum Professur für Biochemische Zelltechnologie"),
    ("Universität Augsburg, Lehr- & Forschungseinheit Mechanical Engineering, Prof. Dr. Lena Beispiel",
     "Universität Augsburg, Lehr- & Forschungseinheit Mechanical Engineering"),
    ("Institut für Photonik (Prof. Dr. Max Mustermann)", "Institut für Photonik"),
    # a chair named after a donor is a designation, not a person
    ("Technische Universität München - Dr. Theo Schöller-Stiftungslehrstuhl für Technologie- und Innovationsmanagement",
     "Technische Universität München - Dr. Theo Schöller-Stiftungslehrstuhl für Technologie- und Innovationsmanagement"),
]


@pytest.mark.parametrize("text, expected", PERSON_CASES)
def test_strip_persons_catalogue_strings(text, expected):
    assert mp.strip_persons(text) == expected


# untitled working-group head: shape of a real catalogue string ("… AG <first> van <last>" closing the field);
# the name is invented, the institute designation is the real one
AG_PERSON = ("Charité - Universitätsmedizin Berlin, Berliner Institut für Gesundheitsforschung in der Charité "
             "AG Erika van Beispiel")


@pytest.mark.parametrize("text, expected", [
    (AG_PERSON, "Charité - Universitätsmedizin Berlin, Berliner Institut für Gesundheitsforschung in der Charité"),
    ("Universität X - AG Erika Musterfrau - Institut Y", "Universität X - Institut Y"),
    # subject working groups stay (strings from the shortlist)
    ("Freie Universität Berlin - Institut für Informatik - AG Künstliche Intelligenz",) * 2,
    ("Rheinische Friedrich-Wilhelms-Universität Bonn - AG Autonome Intelligente Systeme - Institut für Informatik VI",) * 2,
    ("Universität Bremen - Fachbereich 3 - AG Digitale Transformation im öffentlichen Dienst",) * 2,
    ("Philipps-Universität Marburg - FB 04 Psychologie - AG Kinder- und Jugendpsychologie",) * 2,
    ("Universität X - AG Jan Peter Muster - Institut Y", "Universität X - Institut Y"),
    ("Beispiel AG",) * 2,
    # legal form outside an academic field, English/adjective subject groups (synthetic)
    ("Beispiel AG Corporate Technology, München",) * 2,
    ("Universität X - AG Data Science",) * 2,
    ("Universität X - AG Maschinelles Lernen",) * 2,
    ("Universität X - AG Neue Materialien",) * 2,
])
def test_strip_persons_untitled_working_group_head(text, expected):
    assert mp.strip_persons(text) == expected


def test_untitled_working_group_head_reaches_no_output_field():
    lead, _ = mapped(executing=AG_PERSON, recipient="Charité - Universitätsmedizin Berlin")
    dump = lead.model_dump_json()
    assert "van Beispiel" not in dump and "Erika" not in dump and "Berliner Institut für Gesundheitsforschung in der Charité" in dump


def test_person_names_reach_no_output_field():
    executing = PERSON_CASES[1][0]
    lead, _ = mapped(executing=executing, recipient="Universität Heidelberg")
    dump = lead.model_dump_json()
    assert "Mustermann" not in dump and "Prof." not in dump
    assert "Kirchhoff Institut für Physik - Neuromorphic Quantumphotonics" in lead.signals[0].evidence
    assert "Kirchhoff Institut für Physik" in lead.country_evidence.finding


# --- 1. classification basis and rules --------------------------------------------------------------

@pytest.mark.parametrize("thema, industry, basis", [
    ("MAXCarbon", None, None),                                  # 'carbon' alone inside a name is not climate
    ("MAXCarbon: CO2-Bindung in Beton", Industry.CLIMATE, "thema"),
    ("KlimaPay", Industry.FINTECH, "thema"),                    # pay beats klima in a tie
    ("AI-Wallet", Industry.FINTECH, "thema"),
    ("Leichtbau-Zahnradgetriebe", Industry.INDUSTRIAL, "thema"),
    ("Neuronale Netze für Bildanalyse", Industry.AI, "thema"),
    ("Streamlingo", None, None),
])
def test_classify_rules(thema, industry, basis):
    match = mp.classify([grant(fkz="03EGXX0001", thema=thema, **NEUTRAL)])
    if industry is None:
        assert match.basis == "default" and match.htgf_sector is None
    else:
        assert (match.industry, match.basis) == (industry, basis) and match.htgf_sector


def test_basis_institut_and_default_sector():
    weak = mp.classify([grant(thema="Streamlingo", executing="KIT - Institut für Anthropomatik und Robotik", recipient="KIT")])
    assert weak.basis == "institut" and weak.field == "Ausführende Stelle" and weak.htgf_sector == "industrial_deep_tech"
    lead, info = mapped(fkz="03EGXX0001", thema="SetScout", **NEUTRAL)
    assert info.basis == "default" and lead.htgf_sector is None and lead.industry == Industry.AI
    assert "industry_unclassified" in lead.signals[0].evidence.splitlines()[-1]


# --- 2. priority ------------------------------------------------------------------------------------

def test_priority_weights_and_reason():
    w = mp.PRIORITY_WEIGHTS
    lead, info = mapped(thema="Wasserstoff-Elektrolyse", end=date(2027, 3, 31), amount=Decimal("972638.40"), **NEUTRAL)
    assert info.priority == w["programme_03EF"] + w["end_near_founding"] + w["basis_thema"] + w["amount_500k"] == 90
    assert lead.prioritization_reason == ("Priorität 90: EXIST-Forschungstransfer; Förderung endet 03/2027; "
                                          "Branche ClimateTech aus Projekttitel (wasserstoff, elektrolys); 972.638 EUR.")
    _, running = mapped(fkz="03EGXX0001", thema="X", end=date(2028, 1, 1), amount=Decimal("120000"), **NEUTRAL)
    assert running.priority == w["running"] + w["amount_100k"]
    _, old = mapped(fkz="03EGXX0001", thema="X", end=date(2025, 11, 19), amount=Decimal("1"), **NEUTRAL)
    assert old.priority == 0
    company_lead, company = mapped(fkz="03EFU9XX01", thema="X", recipient="Beispiel GmbH", executing="Beispiel GmbH",
                                   amount=None, end=date(2025, 1, 1))
    assert company.priority == w["programme_03EF"] + w["recipient_company"]
    assert "Empfänger ist ein Unternehmen" in company_lead.prioritization_reason


def test_priority_as_of_is_injectable_and_defaults_to_retrieval_date():
    rows = [grant(end=date(2027, 6, 30))]
    default = mp.map_project(rows)[1]
    assert default.priority == mp.map_project(rows, AS_OF)[1].priority          # retrieved_at = 2026-11-20
    assert mp.map_project(rows, date(2027, 6, 1))[1].priority != mp.map_project(rows, date(2025, 1, 1))[1].priority


def test_run_sorted_by_priority_then_start_then_id_and_reproducible():
    first = mp.run(fetch=FixtureFetch(), cache=None, clock=CLOCK)
    keys = [first.info[l.id].sort_key() for l in first.leads]
    assert keys == sorted(keys) and all(0 <= first.info[l.id].priority <= 100 for l in first.leads)
    later = mp.run(fetch=FixtureFetch(), cache=None, clock=lambda: datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc))
    assert [l.id for l in later.leads] == [l.id for l in first.leads]


# --- 3. signal evidence -----------------------------------------------------------------------------

def test_signal_evidence_labels_and_downstream_parsing():
    lead, _ = mapped()
    signal = lead.signals[0]
    labels = [line.split(":", 1)[0] for line in signal.evidence.splitlines()]
    assert labels == ["Förderkennzeichen", "Programm", "Thema", "Förderempfänger", "Ausführende Stelle", "Laufzeit",
                      "Fördersumme", "Öffentliche Förderung", "Hinweise"]
    assert "Laufzeit: 01.06.2024 bis 30.09.2026" in signal.evidence and "Fördersumme: 876.964,00 EUR" in signal.evidence
    assert (signal.subject_lead_id, signal.type, signal.source, signal.date) == (lead.id, "exist_projekt", "Förderkatalog",
                                                                                date(2024, 6, 1))
    enriched = context.engine.enrich(lead, light=True, as_of=AS_OF)
    assert enriched.scoring_input.public_grant.status == "usable"
    assert enriched.scoring_input.public_grant.value == "approved"
    assert enriched.scoring_input.country.status == "usable"


# --- 4. description ---------------------------------------------------------------------------------

def test_description_is_product_text():
    lead, _ = mapped(thema="EXIST-Forschungstransfer: Ionera - Hochdurchsatzplattform für die chemische und biologische Analytik")
    assert lead.description == "„Ionera“: Hochdurchsatzplattform für die chemische und biologische Analytik – Projekt im Programm EXIST-Forschungstransfer."
    for word in ("Förderempfänger", "Bundesanteil", "Ausführende"):
        assert word not in lead.description
    assert "Hochdurchsatzplattform" in context.engine.field_terms(lead)


# --- edge fixes -------------------------------------------------------------------------------------

def test_empty_thema_is_named_by_fkz():
    lead, _ = mapped(thema="")
    assert lead.name == "03EFBB0063"


def test_no_star_import_and_local_logger():
    source = inspect.getsource(mp)
    assert "import *" not in source and mp.logger.name == "sourcing.mapping"


# --- search() and CLI ------------------------------------------------------------------------------

def test_search_excludes_default_and_applies_limit_after_sorting():
    run = mp.run(fetch=FixtureFetch(), cache=None, clock=CLOCK)
    for industry in Industry:
        found = search(SearchCriteria(industry=industry, limit=200), fetch=FixtureFetch(), cache=NoCache())
        assert all(run.info[l.id].basis != "default" for l in found)
        ranks = [mp.BASIS_ORDER[run.info[l.id].basis] for l in found]
        assert ranks == sorted(ranks)
    every = search(SearchCriteria(industry=Industry.AI, limit=200), fetch=FixtureFetch(), cache=NoCache(),
                   include_unclassified=True)
    assert any(run.info[l.id].basis == "default" for l in every)
    two = search(SearchCriteria(industry=Industry.AI, limit=2), fetch=FixtureFetch(), cache=NoCache(), include_unclassified=True)
    assert [l.id for l in two] == [l.id for l in every[:2]]


def test_cli_min_priority_unclassified_and_stats(tmp_path, monkeypatch):
    from sourcing.__main__ import main
    db = tmp_path / "c.db"
    fx.export_rows(fetch=FixtureFetch(), cache=Cache(db), clock=CLOCK)
    monkeypatch.setattr(fx, "Session", lambda: pytest.fail("network used"))
    out, stats = tmp_path / "o.json", tmp_path / "s.json"
    assert main(["foekat", "--out", str(out), "--cache", str(db), "--stats", str(stats)]) == 0
    data = json.loads(stats.read_text(encoding="utf-8"))
    assert data["written"] == 45 and sum(data["classification_basis"].values()) == 45
    assert sum(data["priority_histogram"].values()) == 45 and len(data["top10"]) == 10
    assert set(data["industry_by_basis"]) == {"thema", "institut", "default"} and data["leads_by_programme"] == {"03EF": 19, "03EG": 26}
    assert main(["foekat", "--out", str(out), "--cache", str(db), "--no-unclassified", "--min-priority", "40"]) == 0
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert 0 < len(kept) < 45
    assert all("industry_unclassified" not in l["signals"][0]["evidence"] for l in kept)
    assert all(int(re.match(r"Priorität (\d+):", l["prioritization_reason"]).group(1)) >= 40 for l in kept)
