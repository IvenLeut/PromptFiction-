"""Reproduce Iven's FounderRadar reference run offline and compare it field by field.

Recalculates `data/mvp/jury-reference.json` exactly like "Score jetzt berechnen" in Iven's cockpit
(`mvp.engine.run` in replay mode: saved dossiers, the reference Stichtag, sectors, age window and
limit; no web, no LLM) into a temporary data directory, then compares every company against

  * the reference run (queue, score, score_upper, company/market score, risk, stage, coverage,
    criterion points, hypothesis, htgf_fit, next steps, order) and
  * the jury export `Ergebnisse/Longlist.csv` (same columns as `mvp/export_jury.py`).

`reasons` is reported separately: replay marks dossiers as `snapshot`, so the reason
"Aktuelle Website-Prüfung fehlgeschlagen" of a failed live fetch disappears by design
(Iven's engine, not a scoring difference). Exit code 0 = all companies identical.

    .venv/bin/python -m AGENT_TEAM.eval.check_iven_reproduction
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "data/mvp/jury-reference.json"
LONGLIST = ROOT / "Ergebnisse/Longlist.csv"
FIELDS = ("queue", "score", "score_upper", "company_score", "market_score", "risk", "stage",
          "coverage", "hypothesis", "htgf_fit", "next_steps")
FAILED_FETCH = "Aktuelle Website-Prüfung fehlgeschlagen; historische Daten sind gekennzeichnet."


def replay():
    """Run Iven's engine in replay mode on the reference run; returns (reference, replayed Run)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from mvp.contracts import Run, RunOptions
    reference = Run.model_validate_json(REFERENCE.read_bytes())
    previous = os.environ.get("FOUNDERRADAR_MVP_DATA")
    with tempfile.TemporaryDirectory(prefix="iven-replay-") as tmp:
        os.environ["FOUNDERRADAR_MVP_DATA"] = tmp  # no latest.json -> load_last() uses jury-reference.json
        try:
            from mvp import engine
            o = reference.options
            result = engine.run(RunOptions(mode="replay", as_of=o.as_of, sectors=o.sectors,
                                           max_age_months=o.max_age_months, limit=o.limit))
        finally:
            if previous is None:
                os.environ.pop("FOUNDERRADAR_MVP_DATA", None)
            else:
                os.environ["FOUNDERRADAR_MVP_DATA"] = previous
    return reference, result


def _num(value):
    return "" if value is None else str(value)


def longlist_rows(run, *, live=True):
    """Rows as `mvp.export_jury.export` writes them (no stored AI insights in the repo)."""
    from mvp.briefs import brief_for
    from mvp.scoring import ranked
    labels = {"ranked": "Bewertbar", "research": "Recherche offen"}
    rows = []
    for item in ranked(run.assessments):
        if item.queue not in labels:
            continue
        brief = brief_for(item, live=live)
        rows.append([item.dossier.name, ", ".join(item.dossier.sectors), labels[item.queue], _num(item.score),
                     item.risk, _num(item.market_score), _num(item.company_score), item.stage,
                     brief.summary, brief.thesis])
    return rows


def compare():
    reference, result = replay()
    ref = {a.dossier.id: a for a in reference.assessments}
    new = {a.dossier.id: a for a in result.assessments}
    report = {"companies_reference": len(ref), "companies_replay": len(new), "identical": 0,
              "mismatches": [], "reason_only_differences": [], "order_identical": None,
              "longlist_rows": 0, "longlist_identical": 0, "longlist_mismatches": [],
              "web_requests": result.counts.get("web_requests"), "llm_calls": result.llm_calls,
              "as_of": str(reference.options.as_of), "rule_version": reference.rule_version,
              "source_snapshot_date": reference.source_snapshot_date,
              "counts": {k: result.counts.get(k) for k in ("ranked", "research", "excluded")}}
    for identity, a in ref.items():
        b = new.get(identity)
        if b is None:
            report["mismatches"].append({"id": identity, "name": a.dossier.name, "missing": True})
            continue
        diff = {f: (getattr(a, f), getattr(b, f)) for f in FIELDS if getattr(a, f) != getattr(b, f)}
        pa, pb = [(c.key, c.points) for c in a.criteria], [(c.key, c.points) for c in b.criteria]
        if pa != pb:
            diff["criteria"] = (pa, pb)
        if diff:
            report["mismatches"].append({"id": identity, "name": a.dossier.name, "diff": diff})
        else:
            report["identical"] += 1
        if a.reasons != b.reasons:
            explained = [r for r in a.reasons if r != FAILED_FETCH] == b.reasons
            report["reason_only_differences"].append({"name": a.dossier.name, "explained_by_snapshot": explained})
    report["order_identical"] = [a.dossier.id for a in reference.assessments] == [a.dossier.id for a in result.assessments]
    with LONGLIST.open(encoding="utf-8-sig", newline="") as stream:
        published = list(csv.reader(stream, delimiter=";"))[1:]
    rows = longlist_rows(result)
    report["longlist_rows"] = len(published)
    for i, row in enumerate(published):
        mine = rows[i] if i < len(rows) else None
        if mine == row:
            report["longlist_identical"] += 1
        else:
            report["longlist_mismatches"].append({"row": i + 1, "csv": row, "replay": mine})
    report["ok"] = (report["identical"] == len(ref) == len(new) and report["order_identical"]
                    and report["longlist_identical"] == len(published) == len(rows)
                    and all(x["explained_by_snapshot"] for x in report["reason_only_differences"])
                    and report["web_requests"] == 0 and report["llm_calls"] == 0)
    return report


def main():
    report = compare()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\n{report['identical']}/{report['companies_reference']} Firmen identisch, "
          f"Longlist {report['longlist_identical']}/{report['longlist_rows']} Zeilen identisch, "
          f"Reihenfolge {'identisch' if report['order_identical'] else 'ABWEICHEND'}: "
          f"{'OK' if report['ok'] else 'ABWEICHUNG'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
