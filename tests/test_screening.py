import pytest
from pydantic import ValidationError

from demo_portfolio import get_demo_result
from models import EnrichedLead, EvaluatedLead, RawLead
from screening import screening_status


def test_unknown_is_not_bootstrapped_or_fit():
    lead = next(x for x in get_demo_result().leads if x.fund_fit_score is None)
    assert lead.funding_status == "Unknown"
    assert lead.fund_fit_score is None and lead.team_score is None
    assert screening_status(lead) == "Check fund criteria"
    eligible = lead.model_copy(update={"eligibility_status": "Eligible"})
    assert screening_status(eligible) == "Check funding"
    excluded = eligible.model_copy(update={"hard_exclusions": ["Standort außerhalb Mandat"]})
    assert screening_status(excluded) == "Excluded"


def test_new_fields_belong_to_correct_stage():
    assert "first_signal_date" in RawLead.model_fields
    assert "funding_status" not in RawLead.model_fields
    assert "founder_profiles" in EnrichedLead.model_fields
    assert "fund_fit_score" not in EnrichedLead.model_fields
    assert "fund_fit_score" in EvaluatedLead.model_fields
    lead = next(x for x in get_demo_result().leads if x.fund_fit_score is None)
    with pytest.raises(ValidationError):
        lead.team_score = 101
    with pytest.raises(ValidationError):
        lead.funding_status = "No funding found"
