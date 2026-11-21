"""Frozen real run for the offline demo ("Snapshot (echte Leads)").

`analysis_snapshot.json` is an `AnalysisRun` built by `build_snapshot.py` from the 52 online dossiers of the
agent team's loop-1 run; `snapshot_meta.json` holds what the AnalysisRun contract has no field for (scoring stage
detail, why-now text, noise class, backtest headline, best find, rejected leads). Loading needs no network.
"""
import json
from functools import lru_cache
from pathlib import Path

from models import AnalysisRun

SNAPSHOT_DIR = Path(__file__).resolve().parent
ANALYSIS_PATH = SNAPSHOT_DIR / "analysis_snapshot.json"
META_PATH = SNAPSHOT_DIR / "snapshot_meta.json"


class SnapshotMissingError(FileNotFoundError):
    """The snapshot files were not built yet (python -m demo_snapshot.build_snapshot)."""


@lru_cache(maxsize=1)
def load_snapshot() -> tuple[AnalysisRun, dict]:
    """(AnalysisRun, meta) of the frozen run; cached per process. Callers must not mutate the result."""
    if not ANALYSIS_PATH.exists():
        raise SnapshotMissingError(f"{ANALYSIS_PATH} fehlt. Bauen mit: python -m demo_snapshot.build_snapshot")
    run = AnalysisRun.model_validate_json(ANALYSIS_PATH.read_text(encoding="utf-8"))
    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    return run, meta
