"""Automatic pipeline handoff. No upload step or silent demo fallback."""
import os
import re
from functools import partial
from pathlib import Path
from urllib.parse import quote, urlencode

import pipeline
from cockpit_data import load_payload
from models import AnalysisRun, Industry, SearchCriteria


def start_analysis(category: Industry, on_progress=None):
    mode = os.getenv("FOUNDERRADAR_MODE", "demo").strip().lower()
    if mode not in {"demo", "live"}:
        raise ValueError("FOUNDERRADAR_MODE must be demo or live.")
    saved_runs = os.getenv("FOUNDERRADAR_ANALYSIS_DIR", "").strip()
    if mode == "live" and saved_runs:
        path = Path(saved_runs) / (category.name.lower() + ".json")
        run = AnalysisRun.model_validate_json(path.read_bytes())
        if run.mode != "live" or run.criteria.industry != category:
            raise ValueError("Saved analysis mode or industry does not match the request")
        if on_progress:
            on_progress(100, "Gespeicherten Analyselauf geladen")
        return run
    context_mode = os.getenv("FOUNDERRADAR_CONTEXT_MODE", "light")
    if context_mode not in {"light", "live"}:
        raise ValueError("FOUNDERRADAR_CONTEXT_MODE must be light or live")
    options = {}
    if mode == "live":
        from context.engine import enrich
        if context_mode == "light":
            options["enricher"] = partial(enrich, light=True)
    model = os.getenv("FOUNDERRADAR_OLLAMA_MODEL", "").strip()
    if mode == "live" and model and context_mode == "live":
        from context.engine import default_lookups, enrich
        from context.web import original_page
        from context.ollama import extract_quotes
        options["enricher"] = partial(enrich, load_original=original_page,
                                     lookups=default_lookups(model=model),
                                     extract_quotes=partial(extract_quotes, model))
    limit = int(os.getenv("FOUNDERRADAR_DISCOVERY_LIMIT", "200" if mode == "live" else "30"))
    return pipeline.run_pipeline(SearchCriteria(industry=category, limit=limit),
                                 use_mock=mode == "demo", on_progress=on_progress, **options)


def load_workspace(run):
    return load_payload(run.model_dump(mode="json"))


def _email(value):
    if not isinstance(value, str) or re.search(r"[\x00-\x1f\x7f]", value):
        return None
    value = value.strip()
    if len(value) > 254 or value.count("@") != 1:
        return None
    local, domain = value.rsplit("@", 1)
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}", local) or local.startswith(".") or local.endswith(".") or ".." in local:
        return None
    if len(domain.split(".")) < 2 or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", x) for x in domain.split(".")):
        return None
    return value


def email_draft(lead):
    address = next((valid for key in ("email", "contact_email") if (valid := _email(lead.data.get(key)))), None)
    if not address:
        return None
    name = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", lead.name).split())
    query = urlencode({"subject": f"Austausch zu {name}",
        "body": f"Guten Tag,\n\nich würde gerne mehr über {name} erfahren und einen kurzen Austausch vereinbaren.\nHaben Sie in den kommenden Tagen Zeit für ein Gespräch?\n\nViele Grüße"}, quote_via=quote)
    return f"mailto:{quote(address, safe='@.')}?{query}"
