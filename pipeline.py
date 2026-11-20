"""Processing steps 1-3. Step 4 visualizes their output in app.py."""
import logging
from collections.abc import Callable, Sequence
from models import ContextResult, EnrichedLead, EvaluatedLead, PipelineIssue, RawLead, ResearchResult, SearchCriteria

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
            from context.engine import enrich as enricher
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
            evaluated = EvaluatedLead.model_validate(evaluator(lead))
            _preserve(lead, evaluated)
            result.leads.append(evaluated)
        except Exception:
            logger.exception("Evaluation failed for %s", lead.id)
            result.issues.append(PipelineIssue(lead_id=lead.id, stage="evaluation",
                                message="Bewertung fehlgeschlagen. Details im Server-Log."))
    result.leads.sort(key=lambda x: x.quality_score, reverse=True)
    return result
