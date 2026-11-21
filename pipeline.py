"""Processing steps 1-3 (sourcing -> context -> scoring). Step 4 visualizes their output in app.py.

Demo vs. fixtures: `run_pipeline(use_mock=True)` (the app's demo mode) plugs in the 30-lead
portfolio from demo_portfolio.py. The single-step functions `discover`, `collect_context` and
`evaluate_context` fall back to the three tiny fixtures in mock_data.py when called with
`use_mock=True` and no provider; tests/test_pipeline.py pins that behaviour.
"""
import inspect
import logging
import os
import re
from collections.abc import Callable, Sequence
from datetime import date
from functools import partial

from models import (
    AnalysisRun, ContextResult, EnrichedLead, EvaluatedLead, EvaluationScores, PipelineIssue, RawLead,
    ResearchResult, SearchCriteria,
)
from scoring_input import admission_issue, build_scoring_input

logger = logging.getLogger(__name__)

_PRIORITY = re.compile(r"\s*Priorität\s+([0-9]+)\s*:")
# Step 1 (sourcing/mapping.py) marks a programme-default industry with the hint "industry_unclassified" in the
# "Hinweise:" line of each signal's evidence and with the sentence part "Branche nicht klassifiziert" in
# `prioritization_reason`; older runs wrote the hint into the reason ("Flags: …").
_UNCLASSIFIED_MARKERS = ("industry_unclassified", "Branche nicht klassifiziert")


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


def industry_unclassified(lead: RawLead) -> bool:
    """True if step 1 only defaulted `industry` (no keyword hit). Demo leads never are.

    The one reader of the step-1 marker: evaluation/engine.py (no sector label) and the dashboard
    ("nicht klassifiziert") both use it.
    """
    if lead.is_demo:
        return False
    texts = [lead.prioritization_reason or ""] + [signal.evidence or "" for signal in lead.signals]
    return any(marker in text for text in texts for marker in _UNCLASSIFIED_MARKERS)


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

    The result is a plain list: `complete`/`warnings` of sourcing.engine.SourcingLeads (incomplete
    catalogue export) are logged by `search` but do not reach AnalysisRun, because PipelineIssue has
    no "sourcing" stage and no lead-independent form (a contract change the owners have to agree on).
    """
    if provider is None:
        if use_mock:
            from mock_data import search as provider
        else:
            # Default stays our Förderkatalog provider; Iven's discovery engines are opt-in.
            source = os.getenv("FOUNDERRADAR_SOURCING", "foekat")
            if source == "foekat":
                from sourcing.engine import search as provider
            elif source == "combined":
                from sourcing.combined import search as provider
            elif source == "open_data":
                from sourcing.open_data import search as provider
            else:
                raise ValueError("FOUNDERRADAR_SOURCING must be foekat, combined or open_data")
    found, seen = [], set()
    supplied = provider(criteria)
    for candidate in supplied:
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
    if hasattr(supplied, "discovery"):
        from sourcing.engine import SourcingLeads
        result = SourcingLeads(found, complete=supplied.complete, warnings=supplied.warnings)
        result.discovery = supplied.discovery
        result.discovery["selected_ids"] = [lead.id for lead in found]
        return result
    return found


def _validate_input(leads: Sequence[RawLead], use_mock: bool) -> None:
    """Reject mixed demo/live input and leads without a German base (steps 2 and 3)."""
    if any(x.is_demo != use_mock for x in leads):
        raise MixedDataError("Demo- und Echtdaten dürfen nicht vermischt werden.")
    if any(x.country != "DE" or x.country_evidence is None for x in leads):
        raise GeographyError("Nur Leads mit Deutschland-Beleg sind zugelassen.")


def _preserve(before: RawLead, after: RawLead) -> None:
    """Raise if `after` changed any field that `before` already had."""
    fields = set(type(before).model_fields)
    # The merged sourcing contract can carry this date. Context may fill an empty
    # value only when a dated source supports it; existing values stay immutable.
    if (type(before) is RawLead and isinstance(after, EnrichedLead)
            and before.first_signal_date is None and after.first_signal_date is not None
            and any(e.field == "first_signal_date" and e.source_date == after.first_signal_date for e in after.evidence)):
        fields.discard("first_signal_date")
    if after.model_dump(include=fields) != before.model_dump(include=fields):
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
            enriched = EnrichedLead.model_validate(enricher(lead.model_copy(deep=True)))
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
    # Deep copies: an evaluator must not be able to mutate the dossier it is checked against (Leonard, 032f20d).
    scoring, lead = scoring.model_copy(deep=True), lead.model_copy(deep=True)
    return EvaluationScores.model_validate(evaluator(scoring, lead=lead) if takes_lead else evaluator(scoring))


def evaluate_context(leads: Sequence[EnrichedLead], *, use_mock: bool = True,
                     evaluator: Callable | None = None) -> ResearchResult:
    """Step 3: calculations and ranking (sorted by `ranking_key`).

    Demo: the evaluator receives the EnrichedLead. Live: the ScoringInput is rebuilt from sources
    (SCORING_HANDOFF.md). Held back as an issue before scoring (`scoring_input.admission_issue`, the one
    gate): no usable DE evidence at the as-of date, and a VC status that is confirmed or conflicting. An
    unknown VC status ("missing"/"ambiguous") is the normal case for pre-founding research projects and
    is scored, as is "reported_none".
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
                evaluated = EvaluatedLead.model_validate(evaluator(lead.model_copy(deep=True)))
                _preserve(lead, evaluated)
            else:
                cutoff = lead.scoring_input.as_of if lead.scoring_input else None
                scoring = build_scoring_input(lead, as_of=cutoff or lead.screening_as_of or date.today())
                if reason := admission_issue(scoring):
                    result.issues.append(PipelineIssue(lead_id=lead.id, stage="evaluation", message=reason))
                    continue
                scores = _call_evaluator(evaluator, scoring, lead)
                if scores.scoring_status == "zurueck_an_sourcing":
                    result.issues.append(PipelineIssue(lead_id=lead.id, stage="evaluation", message=scores.investment_thesis))
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
                       discovered_count=len(raw), enriched_count=len(context.leads), result=result,
                       discovery=getattr(raw, "discovery", None))
