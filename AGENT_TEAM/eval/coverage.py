"""Datenabdeckung und Kriterien-Diagnose einer scores.json gegen labels.csv (T3, Messung nach T1).

    .venv/bin/python AGENT_TEAM/eval/coverage.py scores.json [labels.csv] [--json out.json] [--ids a,b,c]

Gibt aus: Abdeckung (Gründer, Website, Stage != pre_gruendung, Papers belegt, Noise != vc_potenzial, Confidence),
Verteilung von Score, Stage und Noise, je Kriterium (teilwerte) die Belegquote und die Spearman-Korrelation der
Kriterienpunkte mit dem Label-Ordinal (talk=2, maybe=1, no=0), dazu die Ränge ausgewählter Leads (--ids).
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import statistics
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("eval_precision", Path(__file__).with_name("precision.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def resolve_id(raw: str, known) -> str | None:
    """Map a user-given id to a lead_id: exact, case-insensitive, or with the 'foekat-' prefix added
    ('03EFMV0034', '03efmv0034', 'foekat-03efmv0034' -> 'foekat-03efmv0034'). None if nothing matches."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw in known:
        return raw
    lower = {k.lower(): k for k in known}
    for cand in (raw.lower(), "foekat-" + raw.lower()):
        if cand in lower:
            return lower[cand]
    return None


def analyse(rows: list[dict], labels: dict, ids: list[str] | None = None) -> dict:
    n = len(rows)
    bewertet = [r for r in rows if r.get("status") == "bewertet"]

    def share(pred, base=rows):
        return round(sum(1 for r in base if pred(r)) / len(base), 3) if base else None

    def papers(r):
        tw = (r.get("teilwerte") or {}).get("team", {}).get("forscher_match", {})
        return bool(tw.get("belegt"))

    scores = [_num(r.get("gesamt_score")) for r in rows if _num(r.get("gesamt_score")) is not None]
    cov = {
        "n": n, "bewertet": len(bewertet),
        "gruender": share(lambda r: bool((r.get("name_gruender") or "").strip())),
        "website": share(lambda r: bool((r.get("website") or "").strip())),
        "stage_nicht_pre_gruendung": share(lambda r: r.get("stage") not in (None, "", "pre_gruendung")),
        "papers_belegt": share(papers),
        "noise_nicht_vc_potenzial": share(lambda r: r.get("noise_class") not in (None, "", "vc_potenzial")),
        "in_databases_true": share(lambda r: r.get("in_databases") is True),
        "confidence_median": statistics.median([_num(r.get("confidence")) or 0 for r in rows]) if rows else None,
    }
    dist = {
        "gesamt_score": {"min": min(scores), "p25": statistics.quantiles(scores, n=4)[0] if len(scores) > 3 else None,
                         "median": statistics.median(scores),
                         "p75": statistics.quantiles(scores, n=4)[2] if len(scores) > 3 else None,
                         "max": max(scores), "distinct": len(set(scores)),
                         "stdev": round(statistics.pstdev(scores), 2)} if scores else None,
        "stage": dict(collections.Counter(r.get("stage") for r in rows).most_common()),
        "noise_class": dict(collections.Counter(r.get("noise_class") for r in rows).most_common()),
    }
    # criterion diagnostics on labelled rows
    lab_rows = [r for r in rows if r["lead_id"] in labels]
    y = [P.LABELS[labels[r["lead_id"]]["label"]] for r in lab_rows]
    crit = {}
    keys = set()
    for r in lab_rows:
        for dim, ks in (r.get("teilwerte") or {}).items():
            for k in ks:
                keys.add((dim, k))
    for dim, k in sorted(keys):
        pts, beleg = [], 0
        for r in lab_rows:
            v = (r.get("teilwerte") or {}).get(dim, {}).get(k, {})
            pts.append(_num(v.get("punkte")) if v else None)
            beleg += bool(v.get("belegt")) if v else 0
        pairs = [(p, yy) for p, yy in zip(pts, y) if p is not None]
        talk = [p for p, yy in pairs if yy == 2]
        rest = [p for p, yy in pairs if yy < 2]
        gw = next(((r.get("teilwerte") or {}).get(dim, {}).get(k, {}).get("gewicht") for r in lab_rows
                   if (r.get("teilwerte") or {}).get(dim, {}).get(k)), None)
        crit["%s.%s" % (dim, k)] = {
            "gewicht": gw, "belegt_anteil": round(beleg / len(lab_rows), 2) if lab_rows else None,
            "distinct": len({p for p, _ in pairs}),
            "mean_talk": round(statistics.mean(talk), 1) if talk else None,
            "mean_rest": round(statistics.mean(rest), 1) if rest else None,
            "spearman_vs_label": P.spearman([p for p, _ in pairs], [yy for _, yy in pairs]),
        }
    for axis in ("team_score", "marktpotenzial_score", "risiko_score", "confidence", "gesamt_score"):
        pairs = [(_num(r.get(axis)), yy) for r, yy in zip(lab_rows, y) if _num(r.get(axis)) is not None]
        crit["achse." + axis] = {"spearman_vs_label": P.spearman([p for p, _ in pairs], [yy for _, yy in pairs]),
                                 "mean_talk": round(statistics.mean([p for p, yy in pairs if yy == 2]), 2)
                                 if any(yy == 2 for _, yy in pairs) else None,
                                 "mean_rest": round(statistics.mean([p for p, yy in pairs if yy < 2]), 2)
                                 if any(yy < 2 for _, yy in pairs) else None}
    ranked = P.rank([{"lead_id": r["lead_id"], "score": _num(r.get("gesamt_score")), "order": i}
                     for i, r in enumerate(rows)])
    pos = {r["lead_id"]: i + 1 for i, r in enumerate(ranked)}
    by_id = {r["lead_id"]: r for r in rows}
    picks = {}
    for raw in ids or []:
        i = resolve_id(raw, by_id)
        r = by_id.get(i) if i else None
        if r:
            picks[i] = {"rank": pos[i], "of": n, "name": r.get("name_unternehmen"), "gesamt": r.get("gesamt_score"),
                        "team": r.get("team_score"), "markt": r.get("marktpotenzial_score"),
                        "risiko": r.get("risiko_score"), "confidence": r.get("confidence"), "stage": r.get("stage"),
                        "noise": r.get("noise_class"), "website": r.get("website"),
                        "gruender": r.get("name_gruender"), "ausschluss": r.get("ausschluss_grund")}
    return {"coverage": cov, "distribution": dist, "criteria": crit, "picks": picks, "n_labelled": len(lab_rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scores")
    ap.add_argument("labels", nargs="?", default=str(P.DEFAULT_LABELS))
    ap.add_argument("--ids", default="")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rows = json.loads(Path(a.scores).read_text(encoding="utf-8"))
    labels, _ = P.load_labels(a.labels)
    ids = [i for i in a.ids.split(",") if i.strip()]
    known = {r["lead_id"] for r in rows}
    for i in ids:
        if resolve_id(i, known) is None:
            print("Warnung: lead_id %r nicht in %s" % (i, a.scores), file=sys.stderr)
    res = analyse(rows, labels, ids)
    print(json.dumps({k: res[k] for k in ("coverage", "distribution", "picks")}, ensure_ascii=False, indent=1))
    print("Kriterien (Spearman vs. Label, Ø talk vs. Rest, Belegquote):")
    for k, v in sorted(res["criteria"].items(), key=lambda kv: -(kv[1]["spearman_vs_label"] or -9)):
        print("  %-34s rho=%-6s talk=%-6s rest=%-6s belegt=%s" % (k, v["spearman_vs_label"], v.get("mean_talk"),
                                                              v.get("mean_rest"), v.get("belegt_anteil")))
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
