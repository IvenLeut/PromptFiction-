"""Step-1 CLI: `python -m sourcing foekat --since 2024-01-01 --out shortlist.json`.

Writes a JSON array of RawLead that `python -m context shortlist.json dossiers.json` reads unchanged, sorted
by priority (desc), project start (desc), id. Leads whose industry is only the programme default are included
by default (hint `industry_unclassified` in the signal evidence); `--no-unclassified` drops them. This differs
on purpose from `sourcing.engine.search` (pipeline provider), which excludes them unless
`include_unclassified=True`: the shortlist is the full list of review cases. With the
cache filled, two runs produce byte-identical files (the priority reference date is the export's retrieval
date unless `--as-of` is given).
"""
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from pydantic import TypeAdapter

from context.cache import Cache
from models import Industry, RawLead
from sourcing.engine import since_default
from sourcing.foekat_export import ExportError, export_rows, fetch_export
from sourcing.mapping import build_leads

PROGRAMME_PREFIXES = {"ef": ("03EF",), "eg": ("03EG",), "both": ("03EF", "03EG")}
INDUSTRY_ALIASES = {"ai": Industry.AI, "software": Industry.AI, "climate": Industry.CLIMATE, "health": Industry.HEALTH,
                    "fintech": Industry.FINTECH, "industrial": Industry.INDUSTRIAL, "deeptech": Industry.INDUSTRIAL}


def parse_industry(value: str) -> Industry | None:
    """--industry value (Industry value/name or alias, case-insensitive) -> Industry; 'all' -> None."""
    if value.casefold() == "all":
        return None
    for industry in Industry:
        if value.casefold() in {industry.value.casefold(), industry.name.casefold()}:
            return industry
    if value.casefold() in INDUSTRY_ALIASES:
        return INDUSTRY_ALIASES[value.casefold()]
    raise argparse.ArgumentTypeError("unbekannte Branche %r (all, %s)" % (value, ", ".join(sorted(INDUSTRY_ALIASES))))


def _raw_copies(directory: Path, prefixes, since, cache) -> None:
    """Copy the cached raw exports (original ISO-8859-15 bytes) of the top-level queries; no network."""
    directory.mkdir(parents=True, exist_ok=True)
    for prefix in prefixes:
        def offline(*_):
            raise ExportError("nicht im Cache")
        try:
            export = fetch_export(prefix, since, fetch=offline, cache=cache)
        except ExportError:
            continue
        (directory / ("foekat_%s_%s.csv" % (prefix, since.isoformat()))).write_bytes(export.raw)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; exit code 0 = complete export, 1 = incomplete (leads written, warning), 2 = export error."""
    parser = argparse.ArgumentParser(prog="python -m sourcing", description="Schritt 1: Sourcing")
    sub = parser.add_subparsers(dest="source", required=True)
    p = sub.add_parser("foekat", help="EXIST-Projekte aus dem Förderkatalog des Bundes (CSV-Export)")
    p.add_argument("--since", type=date.fromisoformat, default=None,
                   help="Projektbeginn ab (JJJJ-MM-TT, Standard FOEKAT_SINCE oder 2024-01-01)")
    p.add_argument("--out", type=Path, required=True, help="Ausgabe: JSON-Array mit RawLead")
    p.add_argument("--industry", type=parse_industry, default=None, help="Branche (Standard all)")
    p.add_argument("--limit", type=int, help="Höchstens so viele Leads ausgeben (nach Sortierung)")
    p.add_argument("--cache", default=None, help="Cache-Datenbank (Standard .cache/context.db, 'off' = aus)")
    p.add_argument("--programme", choices=sorted(PROGRAMME_PREFIXES), default="both",
                   help="ef = Forschungstransfer, eg = Gründungsstipendium")
    p.add_argument("--min-priority", type=int, default=None, help="Nur Leads mit Priorität >= Wert (0-100)")
    p.add_argument("--include-unclassified", dest="include_unclassified", action="store_true", default=True,
                   help="Leads ohne Branchentreffer (Programmstandard, Hinweis industry_unclassified) ausgeben "
                        "(Standard der CLI; sourcing.engine.search lässt sie standardmäßig weg)")
    p.add_argument("--no-unclassified", dest="include_unclassified", action="store_false",
                   help="Leads ohne Branchentreffer weglassen")
    p.add_argument("--as-of", type=date.fromisoformat, default=None,
                   help="Stichtag der Priorität (JJJJ-MM-TT, Standard: Abrufdatum des Exports)")
    p.add_argument("--stats", type=Path, help="Optional: Statistik (Programme, Branchenbasis, Priorität, Top 10) als JSON")
    p.add_argument("--raw-dir", type=Path, help="Optional: Roh-Exporte (ISO-8859-15) aus dem Cache hierhin kopieren")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit muss positiv sein")
    if args.min_priority is not None and not 0 <= args.min_priority <= 100:
        parser.error("--min-priority muss zwischen 0 und 100 liegen")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    since = args.since or since_default()
    prefixes = PROGRAMME_PREFIXES[args.programme]
    cache = Cache(args.cache)
    try:
        result = build_leads(export_rows(prefixes, since, cache=cache), as_of=args.as_of)
    except ExportError as exc:
        print("Fehler: %s" % exc, file=sys.stderr)
        return 2
    leads = [lead for lead in result.leads if (args.industry is None or lead.industry == args.industry)
             and (args.include_unclassified or result.info[lead.id].basis != "default")
             and (args.min_priority is None or result.info[lead.id].priority >= args.min_priority)]
    selected = leads
    if args.limit is not None:
        leads = leads[:args.limit]
    args.out.write_bytes(TypeAdapter(list[RawLead]).dump_json(leads, indent=2) + b"\n")
    if args.stats:
        stats = result.stats(args.industry)
        stats["selected"] = {k: v for k, v in result.stats(shown=selected).items()
                             if k in ("leads", "leads_by_programme", "classification_basis", "industry_by_basis",
                                      "priority_histogram", "top10", "flags")}
        export = result.export.as_dict()
        stats.update({k: export[k] for k in ("requests", "budget", "prefixes")})
        stats.update({"since": since.isoformat(), "programme": args.programme, "written": len(leads),
                      "industry_filter": args.industry.value if args.industry else "all",
                      "include_unclassified": args.include_unclassified, "min_priority": args.min_priority})
        args.stats.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.raw_dir:
        _raw_copies(args.raw_dir, prefixes, since, cache)
    if not result.export.complete:
        print("Warnung: Export unvollständig: %s" % "; ".join(result.export.warnings), file=sys.stderr)
    print("%d Leads geschrieben nach %s" % (len(leads), args.out), file=sys.stderr)
    return 0 if result.export.complete else 1


if __name__ == "__main__":
    sys.exit(main())
