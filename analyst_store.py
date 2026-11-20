"""Local SQLite persistence; demo and live decisions use separate namespaces."""
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

DECISIONS = ("Contact", "Watchlist", "Reject")


def _connect():
    path = Path(os.environ.get("FOUNDERRADAR_DB", str(Path(__file__).parent / "data" / "screening.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("""CREATE TABLE IF NOT EXISTS decisions (
        namespace TEXT NOT NULL, lead_id TEXT NOT NULL, decision TEXT NOT NULL,
        notes TEXT NOT NULL, reason TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace, lead_id))""")
    return connection


def load_decisions(namespace):
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return {row["lead_id"]: dict(row) for row in conn.execute(
            "SELECT * FROM decisions WHERE namespace = ?", (namespace,))}


def save_decision(namespace, lead_id, decision, notes, reason):
    if decision not in DECISIONS:
        raise ValueError("Unknown decision")
    if not reason.strip():
        raise ValueError("Eine Entscheidungsbegründung ist erforderlich.")
    with _connect() as conn:
        conn.execute("""INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, lead_id) DO UPDATE SET decision=excluded.decision,
            notes=excluded.notes, reason=excluded.reason, updated_at=excluded.updated_at""",
            (namespace, lead_id, decision, notes, reason.strip(), datetime.now(timezone.utc).isoformat()))
