from models import EnrichedLead, EvaluatedLead


def evaluate(lead: EnrichedLead) -> EvaluatedLead:
    """Evaluate researched evidence; preserve enriched fields."""
    raise NotImplementedError("Bewertungslogik muss noch implementiert werden.")
