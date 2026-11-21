"""Calculate indicative EUR values using explicit analyst assumptions."""
import argparse
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from models import ContextResult, Contract, EnrichedLead
from scoring_input import build_scoring_input

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
    round_size_eur: int | Decimal | None = None
    asking_pre_money_eur: int | Decimal | None = None
    scorecard_pre_money_eur: Decimal | None = None
    vc_max_pre_money_eur: Decimal | None = None
    vc_price_headroom_eur: Decimal | None = None
    blocked_reason: str | None = None


def value_lead(lead: EnrichedLead, assumptions: ValuationAssumptions) -> ValuationResult:
    """Compare the asking price with the maximum entry price under the supplied scenario."""
    scoring = build_scoring_input(lead, as_of=lead.scoring_input.as_of if lead.scoring_input else None)

    def euro(parameter):
        if parameter.status != "usable":
            return None
        euros, cent = divmod(parameter.value, 100)
        return Decimal(parameter.value) / 100 if cent else euros

    round_size, asking = scoring.round_size_eur_cents, scoring.asking_pre_money_eur_cents
    result = ValuationResult(lead_id=lead.id, assumptions=assumptions,
                             round_size_eur=euro(round_size), asking_pre_money_eur=euro(asking))
    if scoring.vc_status.status != "usable" or scoring.vc_status.value != "reported_none":
        if assumptions.scorecard or assumptions.vc_method:
            result.blocked_reason = "Für die Bewertung fehlt ein belegter Status ohne bisherige VC-Beteiligung."
        return result
    if scorecard := assumptions.scorecard:
        result.scorecard_pre_money_eur = scorecard.benchmark_pre_money_eur * sum(
            factor.weight * factor.relative_score for factor in scorecard.factors.values()
        )
    def snapshots(parameter):
        return {scoring.evidence[key].source_snapshot_id for key in parameter.evidence_ids} - {None}

    if (assumptions.vc_method and result.round_size_eur and result.asking_pre_money_eur
            and snapshots(round_size) & snapshots(asking)):
        vc = assumptions.vc_method
        max_post_money = vc.exit_equity_value_eur * (1 - vc.future_dilution) / vc.target_moic
        result.vc_max_pre_money_eur = max_post_money - result.round_size_eur
        result.vc_price_headroom_eur = result.vc_max_pre_money_eur - result.asking_pre_money_eur
    elif assumptions.vc_method:
        result.blocked_reason = "Rundengröße und Preisforderung benötigen einen gemeinsamen Beleg."
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
