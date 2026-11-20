"""Run context collection on a JSON array of leads."""
import argparse
from functools import partial
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from context.engine import enrich
from context.ollama import extract_quotes
from context.web import original_page
from models import RawLead
from pipeline import collect_context


def main():
    parser = argparse.ArgumentParser(description="Kontext zu einer RawLead-Liste ergänzen")
    parser.add_argument("input", type=Path, help="JSON-Array mit RawLead-Objekten")
    parser.add_argument("output", type=Path, help="Ausgabedatei für ContextResult")
    parser.add_argument("--offline", action="store_true", help="Nur mitgelieferte Signale auswerten")
    parser.add_argument("--limit", type=int, default=5, help="Anzahl in Shortlist-Reihenfolge")
    parser.add_argument("--ollama-model", help="Optionales lokales Modell, z. B. qwen3.5:4b")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit muss positiv sein")
    try:
        leads = TypeAdapter(list[RawLead]).validate_json(args.input.read_text(encoding="utf-8-sig"))
        options = {"load_pages": lambda _: ()} if args.offline else {"load_original": original_page}
        if args.ollama_model:
            options["extract_quotes"] = partial(extract_quotes, args.ollama_model)
        result = collect_context(leads[:args.limit], use_mock=False, enricher=partial(enrich, **options))
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (OSError, ValidationError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
