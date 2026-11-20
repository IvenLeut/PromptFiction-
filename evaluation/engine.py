from models import EvaluationScores
from scoring_models import ScoringInput


def evaluate(lead: ScoringInput) -> EvaluationScores:
    """Score only reviewed, usable parameters from the versioned handoff."""
    raise NotImplementedError("Bewertungslogik muss noch implementiert werden.")
