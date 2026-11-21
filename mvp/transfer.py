"""Portable backup of the local investment team's working state."""
from datetime import date, datetime
import json
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from analyst_store import _connect


FIELDS = ("decision", "notes", "reason", "next_action", "analyst_name", "due_date", "outreach_status", "task_status")


class DecisionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["Contact", "Watchlist", "Reject", "Pending Review"]
    notes: str = Field(max_length=20000)
    reason: str = Field(max_length=20000)
    next_action: str = Field(max_length=2000)
    analyst_name: str = Field(max_length=500)
    due_date: str
    outreach_status: Literal["Not contacted", "Draft prepared", "Contacted", "Replied", "Meeting scheduled"]
    task_status: Literal["Open", "Done"]


class DecisionRecord(DecisionSnapshot):
    lead_id: str = Field(min_length=1, max_length=200)
    updated_at: datetime


class Transfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["founderradar.workspace.1"] = "founderradar.workspace.1"
    decisions: list[DecisionRecord] = Field(max_length=10000)
    history: list[DecisionRecord] = Field(max_length=30000)


def export_workspace():
    with _connect() as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        decisions = connection.execute("SELECT * FROM decisions WHERE namespace='live'").fetchall()
        history = connection.execute(
            "SELECT lead_id, updated_at, snapshot FROM decision_history WHERE namespace='live' ORDER BY id"
        ).fetchall()
    return Transfer(
        decisions=[DecisionRecord(lead_id=row["lead_id"], updated_at=row["updated_at"],
                                  **{key: row[key] for key in FIELDS}) for row in decisions],
        history=[DecisionRecord(lead_id=row["lead_id"], updated_at=row["updated_at"],
                                **json.loads(row["snapshot"])) for row in history],
    ).model_dump_json(indent=2)


def timestamp(record):
    value = record.updated_at
    if value.utcoffset() is None:
        raise ValueError("In der Sicherung fehlt eine Zeitzone.")
    return value.timestamp()


def import_workspace(raw):
    if len(raw) > 15_000_000:
        raise ValueError("Die Sicherung darf höchstens 15 MB groß sein.")
    backup = Transfer.model_validate_json(raw)
    for record in backup.decisions + backup.history:
        timestamp(record)
        if record.due_date:
            date.fromisoformat(record.due_date)
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = {
            lead_id: datetime.fromisoformat(updated_at).timestamp()
            for lead_id, updated_at in connection.execute("SELECT lead_id, updated_at FROM decisions WHERE namespace='live'")
        }
        restored = 0
        for record in sorted(backup.decisions, key=timestamp):
            if current.get(record.lead_id, float("-inf")) >= timestamp(record):
                continue
            connection.execute(
                """INSERT INTO decisions
                   (namespace,lead_id,updated_at,decision,notes,reason,next_action,analyst_name,due_date,outreach_status,task_status)
                   VALUES ('live',?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(namespace,lead_id) DO UPDATE SET
                   updated_at=excluded.updated_at,decision=excluded.decision,notes=excluded.notes,
                   reason=excluded.reason,next_action=excluded.next_action,analyst_name=excluded.analyst_name,
                   due_date=excluded.due_date,outreach_status=excluded.outreach_status,task_status=excluded.task_status""",
                (record.lead_id, record.updated_at.isoformat(), *(getattr(record, key) for key in FIELDS)),
            )
            current[record.lead_id] = timestamp(record)
            restored += 1
        history_seen = {
            (lead_id, datetime.fromisoformat(updated).timestamp(), tuple(json.loads(snapshot).get(key) for key in FIELDS))
            for lead_id, updated, snapshot in connection.execute(
                "SELECT lead_id,updated_at,snapshot FROM decision_history WHERE namespace='live'"
            )
        }
        for record in backup.history:
            values = tuple(getattr(record, key) for key in FIELDS)
            key = record.lead_id, timestamp(record), values
            if key not in history_seen:
                connection.execute(
                    "INSERT INTO decision_history(namespace,lead_id,updated_at,snapshot) VALUES ('live',?,?,?)",
                    (record.lead_id, record.updated_at.isoformat(), json.dumps(dict(zip(FIELDS, values)), ensure_ascii=False)),
                )
                history_seen.add(key)
    return restored
