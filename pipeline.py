"""Processing steps 1-3. Step 4 visualizes their output in app.py."""
import inspect
import logging
from collections.abc import Callable, Sequence
from functools import partial
from models import (
    ContextResult, EnrichedLead, EvaluatedLead, EvaluationScores, PipelineIssue, RawLead, ResearchResult, SearchCriteria,
)
from scoring_input import build_scoring_input

logger = logging.getLogger(__name__)


def discover(criteria: SearchCriteria, *, use_mock: bool = True,
             provider: Callable | None = None) -> list[RawLead]:
    if provider is None:
        if use_mock:
            from mock_data import search as provider
        else:
            from sourcing.engine import search as provider
    found, seen = [], set()
    for candidate in provider(criteria):
        lead = RawLead.model_validate(candidate)
        if lead.is_demo != use_mock:
            raise ValueError("Demo- und Echtdaten dürfen nicht vermischt werden.")
        if (lead.country != "DE" or lead.country_evidence is None
                or lead.industry != criteria.industry or lead.id in seen):
            continue
        seen.add(lead.id)
        found.append(lead)
        if len(found) >= criteria.limit:
            break
    return found


def _validate_input(leads: Sequence[RawLead], use_mock: bool) -> None:
    if any(x.is_demo != use_mock for x in leads):
        raise ValueError("Demo- und Echtdaten dürfen nicht vermischt werden.")
    if any(x.country != "DE" or x.country_evidence is None for x in leads):
        raise ValueError("Nur Leads mit Deutschland-Beleg sind zugelassen.")


def _preserve(before: RawLead, after: RawLead) -> None:
    if after.model_dump(include=set(type(before).model_fields)) != before.model_dump():
        raise ValueError("Ein Modul hat Eingangsdaten verändert.")


def collect_context(leads: Sequence[RawLead], *, use_mock: bool = True,
                    enricher: Callable | None = None) -> ContextResult:
    """Step 2: scrape facts without scores or sorting."""
    _validate_input(leads, use_mock)
    if enricher is None:
        if use_mock:
            from mock_data import enrich as enricher
        else:
            from context.engine import default_lookups, enrich
            from context.web import original_page
            enricher = partial(enrich, load_original=original_page, lookups=default_lookups())
    result = ContextResult()
    for lead in leads:
        try:
            enriched = EnrichedLead.model_validate(enricher(lead))
            _preserve(lead, enriched)
            result.leads.append(enriched)
        except Exception:
            logger.exception("Context failed for %s", lead.id)
            result.issues.append(PipelineIssue(lead_id=lead.id, stage="context",
                                message="Kontext fehlgeschlagen. Details im Server-Log."))
    return result


def evaluate_context(leads: Sequence[EnrichedLead], *, use_mock: bool = True,
                     evaluator: Callable | None = None) -> ResearchResult:
    """Step 3: calculations and ranking."""
    _validate_input(leads, use_mock)
    if evaluator is None:
        if use_mock:
            from mock_data import evaluate as evaluator
        else:
            from evaluation.engine import evaluate as evaluator
    result = ResearchResult()
    for lead in leads:
        try:
            if use_mock:
                evaluated = EvaluatedLead.model_validate(evaluator(lead))
            else:
                scoring = build_scoring_input(lead, as_of=lead.scoring_input.as_of if lead.scoring_input else None)
                if scoring.country.status != "usable":
                    result.issues.append(PipelineIssue(
                        lead_id=lead.id, stage="evaluation", message="Kein nutzbarer Deutschland-Beleg am Stichtag.",
                    ))
                    continue
                vc = scoring.vc_status
                if vc.value == "confirmed" or vc.status == "conflicting":
                    result.issues.append(PipelineIssue(lead_id=lead.id, stage="evaluation",
                                                       message="VC-Finanzierung gefunden oder widersprüchlich gemeldet."))
                    continue
                # An unknown VC status ("missing"/"ambiguous") is the normal case for pre-founding research
                # projects. Such leads are scored; the open question travels in research_questions/open_questions.
                param = inspect.signature(evaluator).parameters.get("lead")
                takes_lead = param is not None and param.kind is inspect.Parameter.KEYWORD_ONLY
                scores = EvaluationScores.model_validate(evaluator(scoring, lead=lead) if takes_lead else evaluator(scoring))
                lead = lead.model_copy(update={"scoring_input": scoring})
                evaluated = EvaluatedLead(**lead.model_dump(), **scores.model_dump())
            _preserve(lead, evaluated)
            result.leads.append(evaluated)
        except Exception:
            logger.exception("Evaluation failed for %s", lead.id)
            result.issues.append(PipelineIssue(lead_id=lead.id, stage="evaluation",
                                message="Bewertung fehlgeschlagen. Details im Server-Log."))
    result.leads.sort(key=lambda x: (x.overall_score is None, -(x.overall_score or 0), x.id))
    return result


def run_pipeline(criteria: SearchCriteria, *, use_mock: bool = True,
                 provider: Callable | None = None, enricher: Callable | None = None,
                 evaluator: Callable | None = None, on_progress: Callable | None = None):
    """One category request executes steps 1–3 and returns the dashboard contract.

    Providers are replaceable independently. A failed lead is reported in issues;
    a failed discovery raises to the caller rather than returning invented data.
    """
    from models import AnalysisRun
    if use_mock:
        from demo_portfolio import demo_search, demo_enrich, demo_evaluate
        provider = provider or demo_search
        enricher = enricher or demo_enrich
        evaluator = evaluator or demo_evaluate
    progress = on_progress or (lambda percent, message: None)
    progress(0, "Passende deutsche Startups finden")
    raw = discover(criteria, use_mock=use_mock, provider=provider)
    progress(33, "Kontext und Quellen zusammenführen")
    context = collect_context(raw, use_mock=use_mock, enricher=enricher)
    progress(66, "Scores und Investmenthypothesen auswerten")
    result = evaluate_context(context.leads, use_mock=use_mock, evaluator=evaluator)
    result.issues = context.issues + result.issues
    progress(100, "Analyse abgeschlossen")
    return AnalysisRun(criteria=criteria, mode="demo" if use_mock else "live",
                       discovered_count=len(raw), enriched_count=len(context.leads), result=result)
