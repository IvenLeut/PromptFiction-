"""Processing steps 1-3 (sourcing -> context -> scoring). Step 4 visualizes their output in app.py.

Demo vs. fixtures: `run_pipeline(use_mock=True)` (the app's demo mode) plugs in the 30-lead
portfolio from demo_portfolio.py. The single-step functions `discover`, `collect_context` and
`evaluate_context` fall back to the three tiny fixtures in mock_data.py when called with
`use_mock=True` and no provider; tests/test_pipeline.py pins that behaviour.
"""
import inspect
import logging
import re
from collections.abc import Callable, Sequence
from functools import partial

from models import (
    AnalysisRun, ContextResult, EnrichedLead, EvaluatedLead, EvaluationScores, PipelineIssue, RawLead,
    ResearchResult, SearchCriteria,
)
from scoring_input import build_scoring_input

logger = logging.getLogger(__name__)

_PRIORITY = re.compile(r"\s*Priorität\s+([0-9]+)\s*:")


class MixedDataError(ValueError):
    """Demo and live leads were combined in one run (all steps)."""


class GeographyError(ValueError):
    """A lead without a German base reached step 2 or 3."""


class InputModifiedError(ValueError):
    """A step-2/3 module changed fields it received from the previous step."""


def lead_priority(lead) -> int:
    """Step-1 priority parsed from the leading "Priorität N:" of `prioritization_reason`; 0 if absent, clamped 0-100."""
    match = _PRIORITY.match(getattr(lead, "prioritization_reason", None) or "")
    return min(int(match[1]), 100) if match else 0


def ranking_key(lead) -> tuple[bool, float, int, str]:
    """Step-3 sort key: score desc (missing last), then step-1 priority desc, then id. Also used by the dashboard."""
    return (lead.overall_score is None, -(lead.overall_score or 0), -lead_priority(lead), lead.id)


def discover(criteria: SearchCriteria, *, use_mock: bool = True,
             provider: Callable | None = None) -> list[RawLead]:
    """Step 1: validate the provider's leads, keep German, evidence-backed members of `criteria.industry`.

    Contract: the provider's order is kept as is (sourcing.engine.search already sorts by basis and
    priority and cuts at `criteria.limit`); this function only drops leads (foreign, without country
    evidence, other industry, duplicate id) and never re-orders. `criteria.limit` is applied once more
    as a safety cap for providers that return more; for a provider that already cut at the limit it is
    a no-op, so nothing is cut twice. With such a provider, a lead dropped here leaves a gap (the run
    returns fewer than `limit`); with an uncapped provider later leads fill it.
    """
    if provider is None:
        if use_mock:
            from mock_data import search as provider
        else:
            from sourcing.engine import search as provider
    found, seen = [], set()
    for candidate in provider(criteria):
        lead = RawLead.model_validate(candidate)
        if lead.is_demo != use_mock:
            raise MixedDataError("Demo- und Echtdaten dürfen nicht vermischt werden.")
        if (lead.country != "DE" or lead.country_evidence is None
                or lead.industry != criteria.industry or lead.id in seen):
            continue
        seen.add(lead.id)
        found.append(lead)
        if len(found) >= criteria.limit:
            break
    return found


def _validate_input(leads: Sequence[RawLead], use_mock: bool) -> None:
    """Reject mixed demo/live input and leads without a German base (steps 2 and 3)."""
    if any(x.is_demo != use_mock for x in leads):
        raise MixedDataError("Demo- und Echtdaten dürfen nicht vermischt werden.")
    if any(x.country != "DE" or x.country_evidence is None for x in leads):
        raise GeographyError("Nur Leads mit Deutschland-Beleg sind zugelassen.")


def _preserve(before: RawLead, after: RawLead) -> None:
    """Raise if `after` changed any field that `before` already had."""
    if after.model_dump(include=set(type(before).model_fields)) != before.model_dump():
        raise InputModifiedError("Ein Modul hat Eingangsdaten verändert.")


def collect_context(leads: Sequence[RawLead], *, use_mock: bool = True,
                    enricher: Callable | None = None) -> ContextResult:
    """Step 2: scrape facts without scores or sorting; a failing lead becomes a PipelineIssue."""
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
        except Exception as exc:
            logger.exception("Context failed for %s (%s)", lead.id, type(exc).__name__)
            result.issues.append(PipelineIssue(lead_id=lead.id, stage="context",
                                message="Kontext fehlgeschlagen. Details im Server-Log."))
    return result


def _call_evaluator(evaluator: Callable, scoring, lead: EnrichedLead) -> EvaluationScores:
    """Call the live evaluator; pass the dossier as `lead=` only if it declares a keyword-only `lead` parameter.

    evaluation/engine.py needs the dossier (founder profiles, grants, partners, …) that ScoringInput lacks;
    simpler evaluators taking only the ScoringInput keep working.
    """
    param = inspect.signature(evaluator).parameters.get("lead")
    takes_lead = param is not None and param.kind is inspect.Parameter.KEYWORD_ONLY
    return EvaluationScores.model_validate(evaluator(scoring, lead=lead) if takes_lead else evaluator(scoring))


def evaluate_context(leads: Sequence[EnrichedLead], *, use_mock: bool = True,
                     evaluator: Callable | None = None) -> ResearchResult:
    """Step 3: calculations and ranking (sorted by `ranking_key`).

    Demo: the evaluator receives the EnrichedLead. Live: the ScoringInput is rebuilt from sources
    (SCORING_HANDOFF.md). Held back as an issue before scoring: no usable DE evidence at the as-of date,
    and a VC status that is confirmed or conflicting. An unknown VC status ("missing"/"ambiguous") is the
    normal case for pre-founding research projects and is scored, as is "reported_none".
    """
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
                _preserve(lead, evaluated)
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
                scores = _call_evaluator(evaluator, scoring, lead)
                dossier = lead.model_copy(update={"scoring_input": scoring})
                evaluated = EvaluatedLead(**dossier.model_dump(), **scores.model_dump())
                _preserve(dossier, evaluated)
            result.leads.append(evaluated)
        except Exception as exc:
            logger.exception("Evaluation failed for %s (%s)", lead.id, type(exc).__name__)
            result.issues.append(PipelineIssue(lead_id=lead.id, stage="evaluation",
                                message="Bewertung fehlgeschlagen. Details im Server-Log."))
    result.leads.sort(key=ranking_key)
    return result


def run_pipeline(criteria: SearchCriteria, *, use_mock: bool = True,
                 provider: Callable | None = None, enricher: Callable | None = None,
                 evaluator: Callable | None = None, on_progress: Callable | None = None) -> AnalysisRun:
    """Steps 1-3 for one category request; returns the dashboard contract (AnalysisRun).

    Providers are replaceable independently. Demo mode defaults to demo_portfolio.py. A failed lead is
    reported in issues; a failed discovery raises to the caller rather than returning invented data.
    """
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
