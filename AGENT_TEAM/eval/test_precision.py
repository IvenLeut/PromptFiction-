"""Offline-Tests für AGENT_TEAM/eval/precision.py (kein Netz, nur tmp-Dateien).

    .venv/bin/python -m pytest -q AGENT_TEAM/eval/test_precision.py
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("eval_precision", Path(__file__).with_name("precision.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def _scores(tmp_path, rows):
    p = tmp_path / "scores.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def _labels(tmp_path, rows, header=("lead_id", "label", "begruendung", "quelle", "quelle_label")):
    p = tmp_path / "labels.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return p


def test_precision_at_k_and_noise(tmp_path):
    s = _scores(tmp_path, [{"lead_id": "a", "gesamt_score": 90}, {"lead_id": "b", "gesamt_score": 80},
                           {"lead_id": "c", "gesamt_score": 70}, {"lead_id": "d", "gesamt_score": 60}])
    l = _labels(tmp_path, [("a", "talk", "", "", "team"), ("b", "no", "", "", "team"),
                           ("c", "maybe", "", "", "team"), ("d", "talk", "", "", "team")])
    labels, _ = P.load_labels(l)
    res = P.evaluate(P.load_scores(s), labels, ks=(2, 4))
    k2, k4 = res["at_k"]
    assert k2["precision_strict"] == 0.5 and k2["noise_share"] == 0.5 and k2["precision_lenient"] == 0.5
    assert k4["precision_strict"] == 0.5 and k4["precision_lenient"] == 0.75 and k4["noise_share"] == 0.25
    assert k4["coverage"] == 1.0


def test_missing_scores_rank_last_and_unlabelled_reduce_coverage(tmp_path):
    s = _scores(tmp_path, [{"lead_id": "x", "gesamt_score": None, "status": "zurueck_an_sourcing"},
                           {"lead_id": "a", "gesamt_score": 50}, {"lead_id": "u", "gesamt_score": 60}])
    labels, _ = P.load_labels(_labels(tmp_path, [("a", "talk", "", "", "team"), ("x", "talk", "", "", "team")]))
    res = P.evaluate(P.load_scores(s), labels, ks=(2,))
    assert [r["lead_id"] for r in res["ranking"]] == ["u", "a", "x"]
    assert res["at_k"][0]["coverage"] == 0.5
    assert res["at_k"][0]["precision_strict"] == 1.0
    assert res["unscored"] == ["x"]


def test_expected_precision_with_ties(tmp_path):
    # all four tied: top-2 in file order would be a,b (both talk) -> 100 %, but expected is the base rate 50 %
    s = _scores(tmp_path, [{"lead_id": i, "gesamt_score": 53.7} for i in "abcd"])
    labels, _ = P.load_labels(_labels(tmp_path, [("a", "talk", "", "", "team"), ("b", "talk", "", "", "team"),
                                                 ("c", "no", "", "", "team"), ("d", "no", "", "", "team")]))
    r = P.evaluate(P.load_scores(s), labels, ks=(2,))["at_k"][0]
    assert r["precision_strict"] == 1.0
    assert r["precision_strict_expected"] == 0.5
    assert r["tie_block_at_boundary"] == 4


def test_spearman_perfect_none_and_ties():
    assert P.spearman([1, 2, 3, 4], [0, 1, 1, 2]) == pytest.approx(0.949, abs=1e-3)
    assert P.spearman([5, 5, 5], [0, 1, 2]) is None          # no score variance
    assert P.spearman([1, 2], [0, 1]) is None                # too few points
    assert P.spearman([1, 2, 3], [2, 1, 0]) == -1.0


def test_calibration_per_label(tmp_path):
    s = _scores(tmp_path, [{"lead_id": "a", "gesamt_score": 80}, {"lead_id": "b", "gesamt_score": 40},
                           {"lead_id": "c", "gesamt_score": 60}])
    labels, _ = P.load_labels(_labels(tmp_path, [("a", "talk", "", "", "team"), ("b", "no", "", "", "team"),
                                                 ("c", "maybe", "", "", "team")]))
    cal = P.evaluate(P.load_scores(s), labels)["calibration"]
    assert cal["spearman_score_vs_label"] == 1.0
    assert cal["per_label"]["talk"]["mean_score"] == 80
    assert cal["per_label"]["no"]["n"] == 1


def test_only_confirmed_and_bad_labels(tmp_path):
    l = _labels(tmp_path, [("a", "talk", "", "", "agent_vorschlag"), ("b", "no", "", "", "team"),
                           ("c", "vielleicht", "", "", "team"), ("d", "", "", "", "team")])
    all_labels, warns = P.load_labels(l)
    assert set(all_labels) == {"a", "b"} and any("vielleicht" in w for w in warns)
    confirmed, _ = P.load_labels(l, only_confirmed=True)
    assert set(confirmed) == {"b"}


def test_label_file_without_quelle_label_counts_as_team(tmp_path):
    l = _labels(tmp_path, [("a", "TALK", "x", "https://e.org")], header=("lead_id", "label", "begruendung", "quelle"))
    labels, _ = P.load_labels(l, only_confirmed=True)
    assert labels["a"]["label"] == "talk"


def test_scores_accept_wrapped_dict_and_extra_fields(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"leads": [{"lead_id": "a", "gesamt_score": "61.5", "neues_feld": 1},
                                       {"gesamt_score": 3}]}), encoding="utf-8")
    rows = P.load_scores(p)
    assert len(rows) == 1 and rows[0]["score"] == 61.5


def test_cli_json_and_template(tmp_path, capsys):
    s = _scores(tmp_path, [{"lead_id": "a", "gesamt_score": 90, "name_unternehmen": "A"},
                           {"lead_id": "b", "gesamt_score": 80, "name_unternehmen": "B"}])
    l = _labels(tmp_path, [("a", "talk", "", "", "team")])
    out, tpl = tmp_path / "res.json", tmp_path / "todo.csv"
    assert P.main([str(s), str(l), "--k", "2", "--json", str(out), "--vorlage", str(tpl)]) == 0
    assert "P@2" in capsys.readouterr().out
    assert json.loads(out.read_text())["at_k"][0]["precision_strict"] == 1.0
    rows = list(csv.DictReader(open(tpl, encoding="utf-8")))
    assert [r["lead_id"] for r in rows] == ["b"] and rows[0]["label"] == ""


def test_shipped_labels_file_is_valid():
    labels, warns = P.load_labels(P.DEFAULT_LABELS)
    assert not warns
    assert len(labels) == 30
    assert all(l["quelle"].startswith("https://") and l["begruendung"] for l in labels.values())
