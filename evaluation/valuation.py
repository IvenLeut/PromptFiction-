"""Calculate indicative EUR values using explicit analyst assumptions."""
import argparse
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from models import ContextResult, Contract, EnrichedLead

Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Ratio = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]
FactorName = Literal["team", "market", "technology", "competition", "sales", "capital_need"]
FACTORS = {"team", "market", "technology", "competition", "sales", "capital_need"}


class Factor(Contract):
    weight: Ratio
    relative_score: Decimal = Field(ge=0, allow_inf_nan=False)
    rationale: str = Field(min_length=1)


class ScorecardAssumptions(Contract):
    benchmark_pre_money_eur: Positive
    benchmark_source: str = Field(min_length=1)
    factors: dict[FactorName, Factor]

    @model_validator(mode="after")
    def validate_factors(self):
        if self.factors.keys() != FACTORS or sum(f.weight for f in self.factors.values()) != 1:
            raise ValueError("Scorecard benötigt alle sechs Faktoren mit insgesamt 100 % Gewicht")
        return self


class VCAssumptions(Contract):
    exit_equity_value_eur: Positive
    future_dilution: Annotated[Decimal, Field(ge=0, lt=1, allow_inf_nan=False)]
    target_moic: Positive


class ValuationAssumptions(Contract):
    scorecard: ScorecardAssumptions | None = None
    vc_method: VCAssumptions | None = None


class ValuationResult(Contract):
    lead_id: str
    assumptions: ValuationAssumptions
    round_size_eur: int | None = None
    asking_pre_money_eur: int | None = None
    scorecard_pre_money_eur: Decimal | None = None
    vc_max_pre_money_eur: Decimal | None = None
    vc_price_headroom_eur: Decimal | None = None


def value_lead(lead: EnrichedLead, assumptions: ValuationAssumptions) -> ValuationResult:
    """Compare the asking price with the maximum entry price under the supplied scenario."""
    result = ValuationResult(lead_id=lead.id, assumptions=assumptions,
                             round_size_eur=lead.round_size_eur,
                             asking_pre_money_eur=lead.asking_pre_money_eur)
    eligible = (lead.has_vc is False or lead.vc_status == "reported_none")
    if not eligible or lead.has_vc is True or lead.vc_status in {"confirmed", "conflicting"}:
        return result
    if scorecard := assumptions.scorecard:
        result.scorecard_pre_money_eur = scorecard.benchmark_pre_money_eur * sum(
            factor.weight * factor.relative_score for factor in scorecard.factors.values()
        )
    if assumptions.vc_method and lead.round_size_eur and lead.asking_pre_money_eur:
        vc = assumptions.vc_method
        max_post_money = vc.exit_equity_value_eur * (1 - vc.future_dilution) / vc.target_moic
        result.vc_max_pre_money_eur = max_post_money - lead.round_size_eur
        result.vc_price_headroom_eur = result.vc_max_pre_money_eur - lead.asking_pre_money_eur
    return result


def main():
    parser = argparse.ArgumentParser(description="Euro-Bewertung mit Annahmen je Lead-ID")
    parser.add_argument("dossiers", type=Path)
    parser.add_argument("assumptions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        context = ContextResult.model_validate_json(args.dossiers.read_text(encoding="utf-8-sig"))
        assumptions = TypeAdapter(dict[str, ValuationAssumptions]).validate_json(
            args.assumptions.read_text(encoding="utf-8-sig")
        )
        results = [value_lead(lead, assumptions.get(lead.id, ValuationAssumptions()))
                   for lead in context.leads]
        data = TypeAdapter(list[ValuationResult]).dump_json(results, indent=2)
        args.output.write_bytes(data + b"\n")
    except (OSError, ValidationError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
