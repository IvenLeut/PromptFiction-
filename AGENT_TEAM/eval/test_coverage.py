"""Offline-Tests für AGENT_TEAM/eval/coverage.py.

    .venv/bin/python -m pytest -q AGENT_TEAM/eval/test_coverage.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("eval_coverage", Path(__file__).with_name("coverage.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def _row(lid, score, **kw):
    base = {"lead_id": lid, "gesamt_score": score, "status": "bewertet", "stage": "pre_gruendung",
            "noise_class": "vc_potenzial", "name_gruender": "", "website": "", "confidence": 0.3,
            "name_unternehmen": lid, "teilwerte": {"team": {"forscher_match": {"punkte": 50, "gewicht": 0.3,
                                                                                "belegt": False}}}}
    base.update(kw)
    return base


def test_resolve_id_with_and_without_prefix():
    known = {"foekat-03efmv0034", "foekat-verbund-x", "other"}
    assert C.resolve_id("foekat-03efmv0034", known) == "foekat-03efmv0034"
    assert C.resolve_id("03efmv0034", known) == "foekat-03efmv0034"
    assert C.resolve_id("03EFMV0034", known) == "foekat-03efmv0034"
    assert C.resolve_id("FOEKAT-03EFMV0034", known) == "foekat-03efmv0034"
    assert C.resolve_id("other", known) == "other"
    assert C.resolve_id("03efxx9999", known) is None
    assert C.resolve_id("", known) is None


def test_picks_found_without_prefix_and_ranked():
    rows = [_row("foekat-a1", 70, website="https://a.de", name_gruender="X"), _row("foekat-03efmv0034", 60),
            _row("foekat-c3", None)]
    res = C.analyse(rows, {}, ["03EFMV0034", "a1", "missing"])
    assert set(res["picks"]) == {"foekat-03efmv0034", "foekat-a1"}
    assert res["picks"]["foekat-03efmv0034"]["rank"] == 2
    assert res["picks"]["foekat-a1"]["rank"] == 1
    assert res["coverage"]["website"] == round(1 / 3, 3)
    assert res["coverage"]["gruender"] == round(1 / 3, 3)


def test_cli_warns_on_unknown_id(tmp_path, capsys):
    p = tmp_path / "scores.json"
    p.write_text(json.dumps([_row("foekat-03efmv0034", 60), _row("foekat-b", 50)]), encoding="utf-8")
    labels = tmp_path / "labels.csv"
    labels.write_text("lead_id,label,begruendung,quelle\nfoekat-b,talk,x,https://e.org\n", encoding="utf-8")
    out = tmp_path / "res.json"
    assert C.main([str(p), str(labels), "--ids", "03efmv0034,nope", "--json", str(out)]) == 0
    err = capsys.readouterr().err
    assert "nope" in err and "03efmv0034" not in err
    assert "foekat-03efmv0034" in json.loads(out.read_text())["picks"]
