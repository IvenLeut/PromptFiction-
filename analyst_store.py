"""Local SQLite persistence; demo and live decisions use separate namespaces."""
import os
from pathlib import Path
import sqlite3
from datetime import date, datetime, timezone
import json
from contextlib import contextmanager

DECISIONS = ("Contact", "Watchlist", "Reject")
OUTREACH = ("Not contacted", "Draft prepared", "Contacted", "Replied", "Meeting scheduled")


@contextmanager
def _connect():
    path = Path(os.environ.get("FOUNDERRADAR_DB", str(Path(__file__).parent / "data" / "screening.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("""CREATE TABLE IF NOT EXISTS decisions (
        namespace TEXT NOT NULL, lead_id TEXT NOT NULL, decision TEXT NOT NULL,
        notes TEXT NOT NULL, reason TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace, lead_id))""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(decisions)")}
    for column in ("next_action", "analyst_name", "due_date"):
        if column not in columns:
            connection.execute(f"ALTER TABLE decisions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if "outreach_status" not in columns:
        connection.execute("ALTER TABLE decisions ADD COLUMN outreach_status TEXT NOT NULL DEFAULT 'Not contacted'")
    if "task_status" not in columns:
        connection.execute("ALTER TABLE decisions ADD COLUMN task_status TEXT NOT NULL DEFAULT 'Open'")
    connection.execute("""CREATE TABLE IF NOT EXISTS decision_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL,
        lead_id TEXT NOT NULL, updated_at TEXT NOT NULL, snapshot TEXT NOT NULL)""")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def load_decisions(namespace):
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return {row["lead_id"]: dict(row) for row in conn.execute(
            "SELECT * FROM decisions WHERE namespace = ?", (namespace,))}


def save_decision(namespace, lead_id, decision, notes, reason, next_action="", analyst_name="",
                  due_date=None, outreach_status=None, task_status=None):
    if decision not in (*DECISIONS, "Pending Review"):
        raise ValueError("Unknown decision")
    if not reason.strip():
        raise ValueError("Eine Entscheidungsbegründung ist erforderlich.")
    if due_date:
        date.fromisoformat(due_date)
    if outreach_status is not None and outreach_status not in OUTREACH:
        raise ValueError("Unknown outreach status")
    if task_status is not None and task_status not in {"Open", "Done"}:
        raise ValueError("Unknown task status")
    with _connect() as conn:
        previous = conn.execute("SELECT due_date, outreach_status, task_status FROM decisions WHERE namespace=? AND lead_id=?", (namespace, lead_id)).fetchone()
        # Legacy clients omit new fields: preserve tracking instead of erasing it.
        due_date = due_date if due_date is not None else previous[0] if previous else ""
        outreach_status = outreach_status or (previous[1] if previous else "Not contacted")
        task_status = task_status or (previous[2] if previous else "Open")
        updated_at = datetime.now(timezone.utc).isoformat()
        conn.execute("""INSERT INTO decisions
            (namespace, lead_id, decision, notes, reason, updated_at, next_action, analyst_name, due_date, outreach_status, task_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, lead_id) DO UPDATE SET decision=excluded.decision,
            notes=excluded.notes, reason=excluded.reason, updated_at=excluded.updated_at,
            next_action=excluded.next_action, analyst_name=excluded.analyst_name,
            due_date=excluded.due_date, outreach_status=excluded.outreach_status, task_status=excluded.task_status""",
            (namespace, lead_id, decision, notes, reason.strip(), updated_at,
             next_action, analyst_name, due_date, outreach_status, task_status))
        snapshot = dict(decision=decision, notes=notes, reason=reason.strip(), next_action=next_action,
                        analyst_name=analyst_name, due_date=due_date, outreach_status=outreach_status, task_status=task_status)
        conn.execute("INSERT INTO decision_history(namespace,lead_id,updated_at,snapshot) VALUES (?,?,?,?)",
                     (namespace, lead_id, updated_at, json.dumps(snapshot, ensure_ascii=False)))


def load_history(namespace, lead_id):
    with _connect() as conn:
        return [dict(updated_at=row[0], **json.loads(row[1])) for row in conn.execute(
            "SELECT updated_at,snapshot FROM decision_history WHERE namespace=? AND lead_id=? ORDER BY id DESC", (namespace, lead_id))]


def save_activity(namespace, lead_id, action, owner, due_date, outreach_status, task_status):
    """Planning a follow-up does not imply an investment decision."""
    if not action.strip():
        raise ValueError("A next action is required.")
    saved = load_decisions(namespace).get(lead_id, {})
    save_decision(namespace, lead_id, saved.get("decision", "Pending Review"), saved.get("notes", ""),
                  saved.get("reason") or "Activity planned; no investment decision recorded.",
                  action.strip(), owner, due_date, outreach_status, task_status)
