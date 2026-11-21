from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from analyst_store import load_decisions, load_history, save_decision
from mvp.briefs import brief_for, mailto, report_html
from mvp.contracts import Run
from mvp.transfer import export_workspace, import_workspace


@pytest.fixture
def refactum():
    path = Path(__file__).resolve().parents[1] / "data/mvp/demo-run.json"
    run = Run.model_validate_json(path.read_bytes())
    return run, next(item for item in run.assessments if item.dossier.name == "REFACTUM GmbH")


def test_edition_contains_market_briefs_for_all_demo_leads(refactum):
    run, _ = refactum
    ranked = [item for item in run.assessments if item.queue == "ranked"]
    assert len(ranked) == 8
    for item in ranked:
        brief = brief_for(item)
        assert brief.editorial
        assert len(brief.alternatives) >= 2 and len(brief.summary.split()) > 20
        report = report_html(item, brief, run.options.as_of)
        assert "FounderRadar / Deep Dive" in report and brief.sources[0][1] in report


def test_mailto_opens_editable_draft_and_rejects_extra_recipients():
    target = mailto("founder+vc@company.de", "Gespräch & Demo", "Guten Tag,\n\nEin kurzes Gespräch?")
    url = urlsplit(target)
    assert url.path == "founder%2Bvc@company.de"
    assert parse_qs(url.query) == {
        "subject": ["Gespräch & Demo"], "body": ["Guten Tag,\r\n\r\nEin kurzes Gespräch?"],
    }
    assert mailto("", "Erstgespräch", "Hallo").startswith("mailto:?subject=")
    for address in ("a@b.de?bcc=x@y.de", "a@b.de\r\nBcc: x@y.de", "a@b.de,x@y.de"):
        with pytest.raises(ValueError):
            mailto(address, "Betreff", "Inhalt")
    with pytest.raises(ValueError):
        mailto("a@b.de", "Betreff\r\nBcc: x@y.de", "Inhalt")


def test_workspace_round_trip_preserves_newer_decisions_and_history(tmp_path, monkeypatch):
    save_decision("live", "lead", "Contact", "Notiz", "Pilot prüfen", "Anrufen", "Team", "2026-12-01",
                  outreach_status="Draft prepared")
    save_decision("demo", "fixture", "Reject", "", "Beispiel")
    original = export_workspace()
    assert "fixture" not in original
    monkeypatch.setenv("FOUNDERRADAR_DB", str(tmp_path / "receiver.sqlite3"))
    assert import_workspace(original.encode()) == 1
    assert load_decisions("live")["lead"]["outreach_status"] == "Draft prepared"
    save_decision("live", "lead", "Contact", "Neue Notiz", "Pilot prüfen", outreach_status="Replied")
    assert import_workspace(original.encode()) == 0
    assert load_decisions("live")["lead"]["notes"] == "Neue Notiz"
    assert len(load_history("live", "lead")) == 2
