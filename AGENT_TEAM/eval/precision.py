"""Precision@k-Harness (T3): Algo-Ranking aus ``scores.json`` gegen Handlabels.

Eingaben:

* ``scores.json`` im Format von ``python -m scoring`` (Liste von Objekten mit ``lead_id``, ``gesamt_score``,
  ``status``, ``confidence``; zusätzliche Felder werden ignoriert, damit die Harness auch neue Scores liest).
* ``labels.csv`` mit den Spalten ``lead_id,label,begruendung,quelle`` (optional ``name``, ``quelle_label``).
  ``label`` ist ``talk`` (würden wir anrufen), ``maybe`` oder ``no``. ``quelle_label`` ist ``agent_vorschlag``
  oder ``team`` (bestätigt); mit ``--nur-bestaetigt`` zählen nur Team-Labels.

Ranking: ``gesamt_score`` absteigend, fehlende Scores zuletzt, bei Gleichstand die Reihenfolge der Datei
(stabil). Weil Gleichstände bei dünnen Leads häufig sind, gibt die Harness zusätzlich die *erwartete*
Precision bei zufälligem Tie-Break an: Der Gleichstandsblock an der Grenze k geht anteilig ein.

Kennzahlen je k (Standard 10 und 30):

* ``precision_strict``  Anteil ``talk`` unter den gelabelten Leads in den Top k
* ``precision_lenient`` Anteil ``talk`` + ``maybe``
* ``noise_share``        Anteil ``no``
* ``coverage``           Anteil gelabelter Leads in den Top k (unter 1 heißt: Zahlen nur bedingt belastbar)
* ``*_expected``         dieselben Werte bei zufälligem Tie-Break

Kalibrierung: Spearman-Rangkorrelation (mit Durchschnittsrängen) zwischen ``gesamt_score`` und Label-Ordinal
(talk=2, maybe=1, no=0) sowie Mittelwert/Spanne des Scores je Label-Klasse. Sind alle Scores gleich, ist die
Korrelation nicht definiert (``null``) – das ist selbst ein Befund.

Aufruf::

    .venv/bin/python AGENT_TEAM/eval/precision.py scores.json [AGENT_TEAM/eval/labels.csv] [--k 10 30]
        [--nur-bestaetigt] [--json out.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

LABELS = {"talk": 2, "maybe": 1, "no": 0}
DEFAULT_LABELS = Path(__file__).resolve().parent / "labels.csv"


def load_scores(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("leads") or data.get("scores") or []
    out = []
    for i, row in enumerate(data):
        if not isinstance(row, dict) or not row.get("lead_id"):
            continue
        s = row.get("gesamt_score")
        try:
            s = float(s) if s is not None and s != "" else None
        except (TypeError, ValueError):
            s = None
        if s is not None and math.isnan(s):
            s = None
        out.append({"lead_id": str(row["lead_id"]), "score": s, "order": i,
                    "status": row.get("status"), "confidence": row.get("confidence"),
                    "name": row.get("name_unternehmen")})
    return out


def load_labels(path: str | Path, only_confirmed: bool = False) -> tuple[dict, list[str]]:
    labels, warnings = {}, []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            lid = (row.get("lead_id") or "").strip()
            lab = (row.get("label") or "").strip().lower()
            if not lid:
                continue
            if lab == "":
                continue  # Vorlage: noch nicht gelabelt
            if lab not in LABELS:
                warnings.append("Zeile %d: unbekanntes Label %r ignoriert" % (n, lab))
                continue
            src = (row.get("quelle_label") or "team").strip().lower()
            if only_confirmed and src != "team":
                continue
            if lid in labels:
                warnings.append("Zeile %d: lead_id %s doppelt, letzte gilt" % (n, lid))
            labels[lid] = {"label": lab, "quelle_label": src, "begruendung": row.get("begruendung", ""),
                           "quelle": row.get("quelle", "")}
    return labels, warnings


def rank(scores: list[dict]) -> list[dict]:
    return sorted(scores, key=lambda r: (r["score"] is None, -(r["score"] or 0.0), r["order"]))


def _avg_ranks(values: list[float]) -> list[float]:
    idx = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and values[idx[j + 1]] == values[idx[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for t in range(i, j + 1):
            ranks[idx[t]] = avg
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(x) != len(y):
        return None
    rx, ry = _avg_ranks(x), _avg_ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return round(sxy / math.sqrt(sxx * syy), 3)


def _shares(rows: list[dict], labels: dict, weights: list[float] | None = None) -> dict:
    weights = weights or [1.0] * len(rows)
    tot = talk = maybe = no = 0.0
    for r, w in zip(rows, weights):
        lab = labels.get(r["lead_id"])
        if not lab:
            continue
        tot += w
        talk += w * (lab["label"] == "talk")
        maybe += w * (lab["label"] == "maybe")
        no += w * (lab["label"] == "no")
    if tot == 0:
        return {"precision_strict": None, "precision_lenient": None, "noise_share": None}
    return {"precision_strict": round(talk / tot, 3), "precision_lenient": round((talk + maybe) / tot, 3),
            "noise_share": round(no / tot, 3)}


def at_k(ranked: list[dict], labels: dict, k: int) -> dict:
    k_eff = min(k, len(ranked))
    top = ranked[:k_eff]
    res = {"k": k, "k_effective": k_eff,
           "labelled": sum(1 for r in top if r["lead_id"] in labels)}
    res["coverage"] = round(res["labelled"] / k_eff, 3) if k_eff else None
    res.update(_shares(top, labels))
    # expected values under random tie-breaking at the boundary
    if k_eff and k_eff < len(ranked):
        boundary = ranked[k_eff - 1]["score"]
        tied = [r for r in ranked if r["score"] == boundary]
        above = [r for r in ranked[:k_eff] if r["score"] != boundary]
        slots = k_eff - len(above)
        frac = slots / len(tied) if tied else 0.0
        exp = _shares(above + tied, labels, [1.0] * len(above) + [frac] * len(tied))
        res["tie_block_at_boundary"] = len(tied)
    else:
        exp = {key: res[key] for key in ("precision_strict", "precision_lenient", "noise_share")}
        res["tie_block_at_boundary"] = 0
    res.update({key + "_expected": v for key, v in exp.items()})
    return res


def evaluate(scores: list[dict], labels: dict, ks=(10, 30)) -> dict:
    ranked = rank(scores)
    distinct = len({r["score"] for r in ranked if r["score"] is not None})
    pairs = [(r["score"], LABELS[labels[r["lead_id"]]["label"]]) for r in ranked
             if r["score"] is not None and r["lead_id"] in labels]
    per_class = {}
    for name, val in LABELS.items():
        vals = [s for s, v in pairs if v == val]
        per_class[name] = {"n": len(vals), "mean_score": round(sum(vals) / len(vals), 2) if vals else None,
                           "min": min(vals) if vals else None, "max": max(vals) if vals else None}
    base = _shares(ranked, labels)
    unscored = [r["lead_id"] for r in ranked if r["score"] is None]
    missing = sorted(set(labels) - {r["lead_id"] for r in ranked})
    return {
        "n_scores": len(ranked), "n_labels": len(labels),
        "n_labelled_and_scored": len(pairs),
        "distinct_scores": distinct,
        "unscored": unscored,
        "labels_without_score": missing,
        "label_sources": {src: sum(1 for l in labels.values() if l["quelle_label"] == src)
                          for src in sorted({l["quelle_label"] for l in labels.values()})},
        "base_rate": base,
        "at_k": [at_k(ranked, labels, k) for k in ks],
        "calibration": {"spearman_score_vs_label": spearman([p[0] for p in pairs], [p[1] for p in pairs]),
                        "per_label": per_class},
        "ranking": [{"rank": i + 1, "lead_id": r["lead_id"], "score": r["score"],
                     "label": labels.get(r["lead_id"], {}).get("label")} for i, r in enumerate(ranked)],
    }


FIELDS = ["lead_id", "name", "label", "begruendung", "quelle", "quelle_label"]


def write_template(path: str | Path, rows: list[dict]) -> None:
    """Empty label rows (label to be filled in by the team) for the given ranked leads."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"lead_id": r["lead_id"], "name": r.get("name") or "", "label": "", "begruendung": "",
                        "quelle": "", "quelle_label": "team"})


def _fmt(v):
    return "–" if v is None else ("%.0f %%" % (100 * v))


def report(res: dict) -> str:
    lines = ["Scores: %d Leads, %d verschiedene Gesamtscores; Labels: %d (%s); gelabelt+bewertet: %d"
             % (res["n_scores"], res["distinct_scores"], res["n_labels"],
                ", ".join("%s=%d" % kv for kv in res["label_sources"].items()) or "keine",
                res["n_labelled_and_scored"])]
    b = res["base_rate"]
    lines.append("Basisrate (alle gelabelten): talk %s, talk+maybe %s, no %s"
                 % (_fmt(b["precision_strict"]), _fmt(b["precision_lenient"]), _fmt(b["noise_share"])))
    for r in res["at_k"]:
        lines.append("P@%d: talk %s | talk+maybe %s | Noise %s | Abdeckung %s"
                     % (r["k"], _fmt(r["precision_strict"]), _fmt(r["precision_lenient"]),
                        _fmt(r["noise_share"]), _fmt(r["coverage"])))
        if r["tie_block_at_boundary"] > 1:
            lines.append("      erwartet bei zufälligem Tie-Break (%d Leads gleichauf an der Grenze): talk %s | "
                         "talk+maybe %s | Noise %s" % (r["tie_block_at_boundary"], _fmt(r["precision_strict_expected"]),
                                                       _fmt(r["precision_lenient_expected"]),
                                                       _fmt(r["noise_share_expected"])))
    c = res["calibration"]
    rho = c["spearman_score_vs_label"]
    lines.append("Kalibrierung: Spearman(Score, Label) = %s" % ("nicht definiert (keine Score- oder Label-Varianz)"
                                                                 if rho is None else "%.2f" % rho))
    for name, s in c["per_label"].items():
        if s["n"]:
            lines.append("  %-5s n=%2d  Score Ø %.1f  (%.1f–%.1f)" % (name, s["n"], s["mean_score"], s["min"], s["max"]))
    if res["labels_without_score"]:
        lines.append("Labels ohne Score: %s" % ", ".join(res["labels_without_score"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Precision@k und Kalibrierung: scores.json gegen labels.csv")
    ap.add_argument("scores")
    ap.add_argument("labels", nargs="?", default=str(DEFAULT_LABELS))
    ap.add_argument("--k", type=int, nargs="+", default=[10, 30])
    ap.add_argument("--nur-bestaetigt", action="store_true", help="nur Labels mit quelle_label=team")
    ap.add_argument("--json", help="Ergebnis zusätzlich als JSON schreiben")
    ap.add_argument("--vorlage", help="CSV-Vorlage mit den noch ungelabelten Leads der Top max(k) schreiben")
    a = ap.parse_args(argv)
    labels, warnings = load_labels(a.labels, only_confirmed=a.nur_bestaetigt)
    for w in warnings:
        print("Warnung:", w, file=sys.stderr)
    scores = load_scores(a.scores)
    res = evaluate(scores, labels, tuple(a.k))
    if a.vorlage:
        todo = [r for r in rank(scores)[:max(a.k)] if r["lead_id"] not in labels]
        write_template(a.vorlage, todo)
        print("Vorlage: %d ungelabelte Leads -> %s" % (len(todo), a.vorlage))
    res["scores_file"], res["labels_file"], res["only_confirmed"] = a.scores, a.labels, a.nur_bestaetigt
    print(report(res))
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
