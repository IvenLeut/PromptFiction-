"""Local SQLite persistence; demo and live decisions use separate namespaces."""
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

DECISIONS = ("Contact", "Watchlist", "Reject")
OUTREACH = ("Not contacted", "Draft prepared", "Contacted", "Replied", "Meeting scheduled")
TRACKING_DEFAULTS = {
    "next_action": "", "analyst_name": "", "due_date": "",
    "outreach_status": "Not contacted", "task_status": "Open",
}


def db_path():
    return Path(os.environ.get("FOUNDERRADAR_DB", str(Path(__file__).parent / "data" / "screening.sqlite3")))


@contextmanager
def _connect(*, write=False):
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=15)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE TABLE IF NOT EXISTS decisions (
            namespace TEXT NOT NULL, lead_id TEXT NOT NULL, decision TEXT NOT NULL,
            notes TEXT NOT NULL, reason TEXT NOT NULL, updated_at TEXT NOT NULL,
            next_action TEXT NOT NULL DEFAULT '', analyst_name TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL DEFAULT '', outreach_status TEXT NOT NULL DEFAULT 'Not contacted',
            task_status TEXT NOT NULL DEFAULT 'Open',
            PRIMARY KEY (namespace, lead_id))""")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(decisions)")}
        for column, default in TRACKING_DEFAULTS.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE decisions ADD COLUMN {column} TEXT NOT NULL DEFAULT '{default}'")
        conn.execute("""CREATE TABLE IF NOT EXISTS decision_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL,
            lead_id TEXT NOT NULL, updated_at TEXT NOT NULL, snapshot TEXT NOT NULL)""")
        if not write:
            conn.commit()
        yield conn


def load_decisions(namespace):
    with _connect() as conn:
        return {row["lead_id"]: dict(row) for row in conn.execute(
            "SELECT * FROM decisions WHERE namespace = ?", (namespace,))}


def _previous(conn, namespace, lead_id):
    result = conn.execute("SELECT * FROM decisions WHERE namespace=? AND lead_id=?", (namespace, lead_id)).fetchone()
    return dict(result) if result else TRACKING_DEFAULTS


def _save(conn, namespace, lead_id, decision, notes, reason, next_action, analyst_name,
          due_date, outreach_status, task_status, previous):
    if due_date:
        date.fromisoformat(due_date)
    if outreach_status is not None and outreach_status not in OUTREACH:
        raise ValueError("Unknown outreach status")
    if task_status is not None and task_status not in {"Open", "Done"}:
        raise ValueError("Unknown task status")
    snapshot = dict(
        decision=decision, notes=notes, reason=reason.strip(), next_action=next_action,
        analyst_name=analyst_name, due_date=previous["due_date"] if due_date is None else due_date,
        outreach_status=previous["outreach_status"] if outreach_status is None else outreach_status,
        task_status=previous["task_status"] if task_status is None else task_status,
    )
    updated_at = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO decisions
        (namespace, lead_id, decision, notes, reason, updated_at, next_action, analyst_name, due_date, outreach_status, task_status)
        VALUES (:namespace, :lead_id, :decision, :notes, :reason, :updated_at, :next_action, :analyst_name, :due_date, :outreach_status, :task_status)
        ON CONFLICT(namespace, lead_id) DO UPDATE SET decision=excluded.decision,
        notes=excluded.notes, reason=excluded.reason, updated_at=excluded.updated_at,
        next_action=excluded.next_action, analyst_name=excluded.analyst_name, due_date=excluded.due_date,
        outreach_status=excluded.outreach_status, task_status=excluded.task_status""",
        dict(snapshot, namespace=namespace, lead_id=lead_id, updated_at=updated_at))
    conn.execute("INSERT INTO decision_history(namespace,lead_id,updated_at,snapshot) VALUES (?,?,?,?)",
                 (namespace, lead_id, updated_at, json.dumps(snapshot, ensure_ascii=False)))


def save_decision(namespace, lead_id, decision, notes, reason, next_action="", analyst_name="",
                  due_date=None, outreach_status=None, task_status=None):
    if decision not in (*DECISIONS, "Pending Review"):
        raise ValueError("Unknown decision")
    if not reason.strip():
        raise ValueError("Eine Entscheidungsbegründung ist erforderlich.")
    with _connect(write=True) as conn:
        _save(conn, namespace, lead_id, decision, notes, reason, next_action, analyst_name,
              due_date, outreach_status, task_status, _previous(conn, namespace, lead_id))


def load_history(namespace, lead_id):
    with _connect() as conn:
        return [dict(updated_at=row[0], **json.loads(row[1])) for row in conn.execute(
            "SELECT updated_at,snapshot FROM decision_history WHERE namespace=? AND lead_id=? ORDER BY id DESC", (namespace, lead_id))]


def save_activity(namespace, lead_id, action, owner, due_date, outreach_status, task_status):
    """Planning a follow-up does not imply an investment decision."""
    if not action.strip():
        raise ValueError("A next action is required.")
    with _connect(write=True) as conn:
        saved = _previous(conn, namespace, lead_id)
        _save(conn, namespace, lead_id, saved.get("decision", "Pending Review"), saved.get("notes", ""),
              saved.get("reason") or "Activity planned; no investment decision recorded.",
              action.strip(), owner, due_date, outreach_status, task_status, saved)
