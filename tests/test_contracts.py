"""The published JSON schemas in examples/ must match the shared contract models."""
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from models import AnalysisRun, ContextResult
from scoring_models import ScoringInput

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

# file -> (generator expression shown in the failure message, schema factory)
SCHEMAS = {
    "analysis-schema.json": ("models.AnalysisRun.model_json_schema()", AnalysisRun.model_json_schema),
    "context-schema.json": ("models.ContextResult.model_json_schema()", ContextResult.model_json_schema),
    # context/__main__.py exports the scoring input as a list, so the schema describes list[ScoringInput].
    "scoring-input-schema.json": ("TypeAdapter(list[scoring_models.ScoringInput]).json_schema()",
                                  TypeAdapter(list[ScoringInput]).json_schema),
}


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_example_schema_matches_models(name):
    expression, factory = SCHEMAS[name]
    published = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    imports = "from pydantic import TypeAdapter; import json, models, scoring_models"
    assert published == factory(), (
        f"examples/{name} is out of date with the models. If the model change is intended, regenerate it with:\n"
        f"  .venv/bin/python -c \"{imports}; "
        f"open('examples/{name}', 'w', encoding='utf-8').write(json.dumps({expression}, indent=2, ensure_ascii=False) + '\\n')\""
    )
