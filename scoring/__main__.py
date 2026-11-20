"""CLI: python -m scoring <dossiers.json | context_result.json | ordner | leads.db> [--out DIR] [--stichtag JJJJ-MM-TT] [--config DATEI]"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from .engine import _leer, _stichtag, clip, load_config, score_all
from .sources import load_dossiers

SCHEMA_PATH = Path(__file__).with_name("scores.schema.json")
JSON_SPALTEN = ("evidence", "teilwerte", "offene_punkte")


def _validator(item=False):
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema["items"] if item else schema)


def validate(rows):
    """Wirft, wenn irgendeine Zeile das Schema verletzt."""
    _validator().validate(rows)


def repair(rows, cfg, stichtag):
    """Eine schema-verletzende Zeile wird zu 'zurueck_an_sourcing', statt den ganzen Lauf abzubrechen."""
    v, tag, kaputt = _validator(item=True), _stichtag(stichtag), 0
    for i, r in enumerate(rows):
        fehler = sorted(v.iter_errors(r), key=lambda e: list(e.path))
        if fehler:
            kaputt += 1
            ersatz = _leer(r["lead_id"], None, cfg, tag)
            ersatz["ausschluss_grund"] = clip("Zeile verletzt das Schema: %s" % fehler[0].message, 300)
            ersatz["offene_punkte"] = [ersatz["ausschluss_grund"]]
            rows[i] = ersatz
    rows.sort(key=lambda r: (r["gesamt_score"] is None, -(r["gesamt_score"] or 0), r["lead_id"]))
    return kaputt


def write_outputs(rows, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    shutil.copyfile(SCHEMA_PATH, out / "scores.schema.json")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    spalten = schema["items"]["required"]
    with open(out / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=spalten)
        w.writeheader()
        for r in rows:
            zeile = {}
            for s in spalten:
                v = r[s]
                if s in JSON_SPALTEN:
                    v = json.dumps(v, ensure_ascii=False, sort_keys=True)
                elif v is None:
                    v = ""
                elif isinstance(v, bool):
                    v = "true" if v else "false"
                elif isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
                    v = "'" + v  # Schutz vor Formel-Ausführung in Excel; scores.json enthält den Originalwert
                zeile[s] = v
            w.writerow(zeile)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m scoring", description="Lead-Dossiers bewerten und scores.csv/json schreiben")
    p.add_argument("input", help="JSON-Datei (Dossiers oder ContextResult), Ordner mit JSON-Dateien oder SQLite-DB")
    p.add_argument("--out", default="scoring_out", help="Zielordner (Standard: scoring_out)")
    p.add_argument("--stichtag", help="Bezugsdatum JJJJ-MM-TT für Alter und Earliness (Standard: heute)")
    p.add_argument("--config", help="andere scoring_config.yaml")
    a = p.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except Exception as e:
        p.error("Konfiguration nicht lesbar: %s: %s" % (type(e).__name__, e))
    try:
        rows = score_all(load_dossiers(a.input, cfg), cfg, a.stichtag)
    except (ValueError, OSError) as e:
        p.error(str(e))
    kaputt = repair(rows, cfg, a.stichtag)
    validate(rows)
    try:
        out = write_outputs(rows, a.out)
    except OSError as e:
        p.error("Zielordner nicht beschreibbar: %s" % e)
    bewertet = sum(r["status"] == "bewertet" for r in rows)
    print("%d Leads, %d bewertet, %d zurück an Sourcing -> %s" % (len(rows), bewertet, len(rows) - bewertet, out))
    for r in rows:
        print("  %-28s gesamt=%-5s team=%-5s markt=%-5s risiko=%-5s conf=%-4s %s %s" % (
            r["lead_id"][:28], r["gesamt_score"], r["team_score"], r["marktpotenzial_score"], r["risiko_score"],
            r["confidence"], r["stage"], ("[" + r["ausschluss_grund"] + "]") if r["ausschluss_grund"] else ""))
    if kaputt:
        print("WARNUNG: %d Zeile(n) verletzten das Schema und stehen als zurueck_an_sourcing im Export." % kaputt, file=sys.stderr)
    return 1 if kaputt else 0


if __name__ == "__main__":
    sys.exit(main())
