"""Run context collection on a JSON array of leads."""
import argparse
from datetime import date
from functools import partial
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from context.cache import Cache
from context.engine import default_lookups, enrich
from context.market import research_market
from context.market_sources import gather_market_sources
from context.ollama import extract_quotes
from context.web import original_page
from models import ContextResult
from sourcing.engine import read_context_leads
from pipeline import collect_context
from research_models import MarketIntelligence
from scoring_input import build_scoring_input
from scoring_models import ScoringInput


def _write_scoring(path, leads, as_of=None):
    parameters = [
        build_scoring_input(lead, as_of=as_of if as_of is not None else
                            lead.scoring_input.as_of if lead.scoring_input else None)
        for lead in sorted(leads, key=lambda item: item.id)
    ]
    path.write_bytes(TypeAdapter(list[ScoringInput]).dump_json(parameters, indent=2) + b"\n")


def main():
    parser = argparse.ArgumentParser(description="Kontext zu einer RawLead-Liste ergänzen")
    parser.add_argument("input", type=Path, help="RawLead-Array oder FounderRadar-Screening-Bericht")
    parser.add_argument("output", type=Path, help="Ausgabedatei für ContextResult")
    parser.add_argument("--offline", action="store_true", help="Nur mitgelieferte Signale auswerten")
    parser.add_argument("--limit", type=int, help="Standard: fünf Leads, im Light-Modus die gesamte Liste")
    parser.add_argument("--ollama-model", help="Optionales lokales Modell, z. B. qwen3.5:4b")
    parser.add_argument("--no-lookups", action="store_true",
                        help="Keine Abfragen an Impressum, Förderkatalog, OpenAlex, Wayback (nur Website und Signale)")
    parser.add_argument("--cache", default=None, help="Pfad der Cache-Datenbank (Standard .cache/context.db, 'off' = aus)")
    parser.add_argument("--patents", action="store_true", help="Google-Patents-Abfrage einschalten (max. 6 Anfragen je Lauf, wird schnell gesperrt)")
    parser.add_argument("--no-match", action="store_true",
                        help="Kein Abgleich Projektname -> Firmen-Website für Leads ohne Website (context/website_match.py)")
    parser.add_argument("--match-threshold", type=float, default=None,
                        help="Mindest-Confidence für eine gefundene Website (Standard 0,6)")
    parser.add_argument("--light", action="store_true", help="Longlist mit mitgelieferten Belegen anreichern")
    parser.add_argument("--lead", help="Nur den Lead mit dieser ID recherchieren")
    parser.add_argument("--market-input", type=Path, help="Strukturierte Marktquellen und Annahmen für --lead")
    parser.add_argument("--market-source", action="append", default=[], help="Öffentliche Marktquelle für --lead")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Expliziter Stichtag für das Scoring (JJJJ-MM-TT)")
    parser.add_argument("--scoring-output", type=Path, help="Optionaler Export der Parameter für Schritt 3")
    parser.add_argument("--replay", action="store_true",
                        help="Dossier-Export lokal einlesen und den Scoring-Export neu berechnen")
    args = parser.parse_args()
    if args.match_threshold is not None and not 0 <= args.match_threshold <= 1:
        parser.error("--match-threshold muss zwischen 0 und 1 liegen")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit muss positiv sein")
    if (args.market_input or args.market_source) and not args.lead:
        parser.error("Marktrecherche benötigt --lead")
    if args.market_source and args.offline:
        parser.error("--market-source benötigt einen Online-Abruf")
    if args.replay and (args.market_input or args.market_source or args.lead or args.limit is not None
                        or args.ollama_model or args.scoring_output or args.light):
        parser.error("--replay akzeptiert ein Dossier als Eingabe und optional --as-of")
    if args.scoring_output and args.scoring_output.resolve() == args.output.resolve():
        parser.error("Dossier und Scoring-Export benötigen verschiedene Ausgabedateien")
    try:
        if args.replay:
            saved = ContextResult.model_validate_json(args.input.read_text(encoding="utf-8-sig"))
            _write_scoring(args.output, saved.leads, args.as_of)
            return
        leads = read_context_leads(args.input)
        if args.lead:
            leads = [lead for lead in leads if lead.id == args.lead]
            if len(leads) != 1:
                parser.error("--lead muss genau einen Eingabe-Lead identifizieren")
        options = {"load_pages": lambda _: ()} if args.offline else {"load_original": original_page}
        options["light"] = args.light
        options["as_of"] = args.as_of
        if args.ollama_model:
            options["extract_quotes"] = partial(extract_quotes, args.ollama_model)
        if not args.offline and not args.no_lookups and not args.light:
            options["lookups"] = default_lookups(Cache(args.cache), args.ollama_model, patents=args.patents,
                                                 match=not args.no_match, match_threshold=args.match_threshold)
        limit = args.limit if args.limit is not None else len(leads) if args.light else 5
        result = collect_context(leads[:limit], use_mock=False, enricher=partial(enrich, **options))
        if (args.market_input or args.market_source) and result.leads:
            inputs = MarketIntelligence()
            if args.market_input:
                inputs = MarketIntelligence.model_validate_json(args.market_input.read_text(encoding="utf-8-sig"))
            if args.market_source:
                inputs = gather_market_sources(inputs, args.market_source)
            result.leads[0] = research_market(result.leads[0], inputs)
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        if args.scoring_output:
            _write_scoring(args.scoring_output, result.leads, args.as_of)
    except (OSError, ValidationError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
