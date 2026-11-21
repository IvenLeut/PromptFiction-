import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from analyst_store import load_decisions, load_history, save_decision
from mvp.briefs import brief_for, generate_draft, mailto, report_html, saved_draft
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


def test_openai_request_sends_public_sources_and_checks_references(refactum, tmp_path, monkeypatch):
    _, item = refactum
    brief = brief_for(item)
    monkeypatch.setenv("FOUNDERRADAR_MVP_DATA", str(tmp_path))
    import mvp.briefs as module

    def response(url, **arguments):
        assert url == "https://api.openai.com/v1/responses"
        request = arguments["json"]
        remote = json.loads(request["input"])
        assert request["store"] is False and request["text"]["format"]["strict"] is True
        assert brief.email[0] not in request["input"] and "api-key-for-fixture" not in request["input"]
        reference = next(iter(remote["sources"]))
        draft = {key: {"text": "Hypothese aus der Quelle prüfen.", "evidence_ids": [reference]}
                 for key in ("company", "market", "hypothesis", "first_call")}
        return StubResponse(draft)

    class StubResponse:
        status_code = 200

        def __init__(self, draft):
            self.draft = draft

        def json(self):
            return {"status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(self.draft)}
            ]}]}

    monkeypatch.setattr(module.requests, "post", response)
    draft = generate_draft(item, brief, "api-key-for-fixture", "test-model")
    assert draft == saved_draft(item, brief, "test-model")
    assert saved_draft(item, brief, "different-model") is None
    draft.company.evidence_ids = ["unknown"]
    monkeypatch.setattr(module.requests, "post", lambda *a, **k: StubResponse(draft.model_dump()))
    with pytest.raises(ValueError, match="gültigen Quellenverweisen"):
        generate_draft(item, brief, "api-key-for-fixture", "test-model")
    assert saved_draft(item, brief, "test-model").company.evidence_ids != ["unknown"]
