"""Iven's reference run must be reproducible offline: 34/34 companies and the Longlist identical.

    .venv/bin/python -m pytest -q AGENT_TEAM/eval/test_iven_reproduction.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("check_iven_reproduction",
                                               Path(__file__).with_name("check_iven_reproduction.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def test_replay_reproduces_reference_and_longlist_exactly():
    report = C.compare()
    assert report["companies_reference"] == report["companies_replay"] == 34
    assert report["mismatches"] == []
    assert report["identical"] == 34
    assert report["order_identical"]
    assert report["longlist_rows"] == report["longlist_identical"] == 34
    assert report["counts"] == {"ranked": 8, "research": 26, "excluded": 0}
    assert report["web_requests"] == 0 and report["llm_calls"] == 0
    assert all(x["explained_by_snapshot"] for x in report["reason_only_differences"])
    assert report["ok"]


def test_refactum_matches_iven_handoff_values():
    reference, result = C.replay()
    item = next(a for a in result.assessments if a.dossier.name == "REFACTUM GmbH")
    assert (item.score, item.company_score, item.market_score) == (69.0, 85.0, 50.0)
    assert [c.points for c in item.criteria] == [85, 50, 70]
    assert item.stage == "Finanzierungsphase offen" and item.risk == "Prüfbedarf: Marktvalidierung"
