"""Run context collection on a JSON array of leads."""
import argparse
from functools import partial
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from context.cache import Cache
from context.engine import default_lookups, enrich
from context.market import research_market
from context.market_sources import gather_market_sources
from context.ollama import extract_quotes
from context.web import original_page
from models import RawLead
from pipeline import collect_context
from research_models import MarketIntelligence


def main():
    parser = argparse.ArgumentParser(description="Kontext zu einer RawLead-Liste ergänzen")
    parser.add_argument("input", type=Path, help="JSON-Array mit RawLead-Objekten")
    parser.add_argument("output", type=Path, help="Ausgabedatei für ContextResult")
    parser.add_argument("--offline", action="store_true", help="Nur mitgelieferte Signale auswerten")
    parser.add_argument("--limit", type=int, help="Standard: fünf Leads, im Light-Modus die gesamte Liste")
    parser.add_argument("--ollama-model", help="Optionales lokales Modell, z. B. qwen3.5:4b")
    parser.add_argument("--no-lookups", action="store_true",
                        help="Keine Abfragen an Impressum, Förderkatalog, OpenAlex, Wayback (nur Website und Signale)")
    parser.add_argument("--cache", default=None, help="Pfad der Cache-Datenbank (Standard .cache/context.db, 'off' = aus)")
    parser.add_argument("--patents", action="store_true", help="Google-Patents-Abfrage einschalten (max. 6 Anfragen je Lauf, wird schnell gesperrt)")
    parser.add_argument("--light", action="store_true", help="Longlist mit mitgelieferten Belegen anreichern")
    parser.add_argument("--lead", help="Nur den Lead mit dieser ID recherchieren")
    parser.add_argument("--market-input", type=Path, help="Strukturierte Marktquellen und Annahmen für --lead")
    parser.add_argument("--market-source", action="append", default=[], help="Öffentliche Marktquelle für --lead")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit muss positiv sein")
    if (args.market_input or args.market_source) and not args.lead:
        parser.error("Marktrecherche benötigt --lead")
    if args.market_source and args.offline:
        parser.error("--market-source benötigt einen Online-Abruf")
    try:
        leads = TypeAdapter(list[RawLead]).validate_json(args.input.read_text(encoding="utf-8-sig"))
        if args.lead:
            leads = [lead for lead in leads if lead.id == args.lead]
            if len(leads) != 1:
                parser.error("--lead muss genau einen Eingabe-Lead identifizieren")
        options = {"load_pages": lambda _: ()} if args.offline else {"load_original": original_page}
        options["light"] = args.light
        if args.ollama_model:
            options["extract_quotes"] = partial(extract_quotes, args.ollama_model)
        if not args.offline and not args.no_lookups and not args.light:
            options["lookups"] = default_lookups(Cache(args.cache), args.ollama_model, patents=args.patents)
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
    except (OSError, ValidationError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
