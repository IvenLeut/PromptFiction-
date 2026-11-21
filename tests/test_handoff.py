"""Cross-step seams: what step 1 writes must be what steps 2, 3 and 4 read.

Step 1 hands structured catalogue facts over as labelled text (RawLead has no fields for them); these tests pin
that text contract end to end, plus the shared readers of step-1 markers in pipeline.py and the admission gate.
"""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import context.engine
import mock_data
import sourcing.foekat_export as fx
import sourcing.mapping as mp
from context.foekat import PROGRAMMES
from context.text import strip_persons
from evaluation.engine import to_dossier
from models import Industry, SearchCriteria, SourceSignal
from pipeline import evaluate_context, industry_unclassified, lead_priority
from scoring import load_config
from scoring_input import admission_issue, build_scoring_input

FIXTURES = Path(__file__).parent / "fixtures" / "sourcing"
CLOCK = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
AS_OF = date(2026, 11, 20)


def catalogue_rows(prefix: str) -> list[fx.GrantRow]:
    raw = (FIXTURES / f"foekat_export_{prefix}.csv").read_bytes()
    return [fx.GrantRow.from_dict(row, CLOCK) for row in fx.parse_export(raw)]


@pytest.mark.parametrize("prefix", sorted(PROGRAMMES))
def test_catalogue_row_survives_steps_1_to_3(prefix):
    for row in catalogue_rows(prefix):
        mapped = mp.map_project([row], AS_OF)
        if mapped is None:      # no German recipient/unit: not a lead
            continue
        lead, info = mapped
        # step 1 -> shared readers
        assert lead_priority(lead) == info.priority
        assert industry_unclassified(lead) is (info.basis == "default")
        # step 1 -> step 2: the labelled signal is read back into one Grant with the same facts
        facts = context.engine.parse_catalogue(lead.signals[0].evidence)
        assert facts["fkz"] == row.fkz and facts["programme"] == PROGRAMMES[prefix] == row.programme
        enriched = context.engine.enrich(lead, light=True, as_of=AS_OF)
        (grant,) = enriched.grants
        assert (grant.reference, grant.programme, grant.start, grant.end) == (row.fkz, PROGRAMMES[prefix], row.start, row.end)
        assert grant.amount_eur == (int(row.amount) if row.amount is not None else None)
        assert str(grant.url) == str(lead.source_url)
        # step 2 -> step 3: ScoringInput reads "Öffentliche Förderung: Bewilligt", the dossier carries the grant
        scoring = build_scoring_input(enriched, as_of=AS_OF)
        assert (scoring.public_grant.status, scoring.public_grant.value) == ("usable", "approved")
        assert admission_issue(scoring) is None
        (funding,) = to_dossier(enriched, load_config())["foerderung"]
        assert (funding["programm"], funding["summe_eur"], funding["quelle"]) == (grant.programme, grant.amount_eur, str(grant.url))
        result = evaluate_context([enriched], use_mock=False)
        assert result.issues == [] and result.leads[0].overall_score is not None


def test_industry_unclassified_reads_every_step1_marker_and_never_demo():
    lead = mock_data.search(SearchCriteria(industry=Industry.AI))[0].model_copy(update={"is_demo": False})
    assert not industry_unclassified(lead)
    for reason in ("Priorität 30: EXIST; Branche nicht klassifiziert (Programmstandard AI / Software).",
                   "EXIST. Flags: early_signal_exist, industry_unclassified"):
        marked = lead.model_copy(update={"prioritization_reason": reason})
        assert industry_unclassified(marked)
        assert not industry_unclassified(marked.model_copy(update={"is_demo": True}))
    signal = SourceSignal(source="Förderkatalog", type="exist_projekt", url="https://example.org/fkz",
                          evidence="Förderkennzeichen: 03EGTEST01\nHinweise: founders_unknown, industry_unclassified")
    assert industry_unclassified(lead.model_copy(update={"signals": [signal]}))


@pytest.mark.parametrize("has_vc, country_evidence, message", [
    (None, True, None), (False, True, None),
    (True, True, "VC-Finanzierung gefunden oder widersprüchlich gemeldet."),
    (None, False, "Kein nutzbarer Deutschland-Beleg am Stichtag."),
])
def test_admission_issue_is_the_one_gate(has_vc, country_evidence, message):
    lead = mock_data.enrich(mock_data.search(SearchCriteria(industry=Industry.AI))[0])
    lead = lead.model_copy(update={"is_demo": False, "has_vc": has_vc,
                                   **({} if country_evidence else {"country_evidence": None})})
    assert admission_issue(build_scoring_input(lead, as_of=AS_OF)) == message


def test_person_rules_are_shared_by_steps_1_and_2():
    unit = "Universität X, Lehrstuhl für Experimentalphysik VI, Prof. Dr. Erika Musterfrau"
    assert mp.strip_persons is strip_persons is context.engine.strip_persons
    assert strip_persons(unit) == "Universität X, Lehrstuhl für Experimentalphysik VI"
    assert strip_persons("Universität X, Institut Y, Univ.-Prof. Dr. Erika Musterfrau") == "Universität X, Institut Y"
    assert strip_persons("Prof. Dr. Erika Musterfrau") == ""    # a field that is only a person is dropped


def test_unit_that_is_only_a_person_reaches_no_field_of_any_step():
    row = catalogue_rows("03EF")[0]
    row = fx.GrantRow(**{**row.__dict__, "executing": "Prof. Dr. Erika Musterfrau", "recipient": "Universität X"})
    lead, _ = mp.map_project([row], AS_OF)
    assert "Musterfrau" not in lead.model_dump_json()
    assert "Ausführende Stelle: ?" in lead.signals[0].evidence
    enriched = context.engine.enrich(lead, light=True, as_of=AS_OF)
    assert "Musterfrau" not in enriched.model_dump_json()
    recipient = enriched.grants[0].recipient
    assert recipient.startswith("Universität X") and "?" not in recipient   # "?" is not read back as a unit
    only_person = fx.GrantRow(**{**row.__dict__, "recipient": "Prof. Dr. Erika Musterfrau", "executing": "Institut Y"})
    signal = mp.map_project([only_person], AS_OF)[0].signals[0]
    assert context.engine.parse_catalogue(signal.evidence)["recipient"] is None
    facts = context.engine.parse_catalogue(
        "Förderkennzeichen: 03EFTEST01\nProgramm: EXIST-Forschungstransfer\nFörderempfänger: Prof. Dr. Erika Musterfrau")
    assert facts["recipient"] is None and not any("Förderempfänger" in line for line in facts["lines"])
