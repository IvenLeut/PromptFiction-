"""Verify the project-only path and last-good behaviour around the AI boundary."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from mvp import ai, ai_relay
from mvp.contracts import Dossier, Source
from mvp.team import extract_team


def research():
    return ai.AnalysisInput(company="TestPhoton GmbH", sectors=["Industrial / DeepTech"], evidence=[
        ai.EvidenceLine(id="S1", kind="product", source_url="https://company.invalid/product",
                        excerpt="Messsoftware für Zerspanungsbetriebe", person=""),
        ai.EvidenceLine(id="S2", kind="team", source_url="https://company.invalid/team",
                        excerpt="Ada Muster · CTO & Co-Founder · Studium an der Uni Test", person="Ada Muster"),
        ai.EvidenceLine(id="S3", kind="research_gap", source_url="",
                        excerpt="Entwicklungsnachweis offen", person=""),
    ])


def result():
    evidence = ai.Claim(text="Kurzkommentar", sources=["S1"])
    team = ai.Founder(name="Ada Muster", role=ai.Claim(text="CTO & Co-Founder", sources=["S2"]),
                      education=ai.Claim(text="Studium an der Uni Test", sources=["S2"]),
                      experience=None, identity_sources=["S2"])
    return ai.Result(model="project-model", created_at=datetime.now(timezone.utc), analysis=ai.Insight(
        summary=evidence, thesis=evidence, strengths=[evidence, evidence], risks=[evidence, evidence],
        conclusion=evidence, market=evidence, founders=[team],
    ))


def test_team_source_has_named_company_evidence_and_rejects_private_page():
    team = Source(url="https://company.invalid/team", title="Team", retrieved_at="2026-11-21", sha256="a"*64)
    bad = team.model_copy(update={"url": "https://company.invalid/datenschutz"})
    public = {"url": team.url, "text": "Dr.-Ing. Ada Muster\nCTO & Co-Founder\nAda war Forscherin an einer Universität.",
              "source": team}
    legal = {"url": bad.url, "text": "Ben Beispiel\nCEO\nFirmenfremder Kontakt.", "source": bad}
    dossier = Dossier(id="x", name="Testphoton GmbH", website="https://company.invalid", identity_status="verified")
    extract_team(dossier, [public, legal])
    assert [e.name for e in dossier.team_evidence] == ["Dr.-Ing. Ada Muster"]


def test_ai_requires_supported_team_claims():
    good = result()
    assert ai.validate_insight(good.analysis, research())
    good.analysis.founders[0].education.text = "Harvard MBA"
    with pytest.raises(ValueError, match="steht so nicht"):
        ai.validate_insight(good.analysis, research())
    good = result()
    good.analysis.founders[0].identity_sources = ["S1"]
    with pytest.raises(ValueError, match="Namensbeleg"):
        ai.validate_insight(good.analysis, research())


def test_client_never_uses_generic_key_and_keeps_last_good_response(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "ROOT", tmp_path)
    monkeypatch.setenv("FOUNDERRADAR_MVP_DATA", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "some-other-key")
    monkeypatch.delenv("FOUNDERRADAR_AI_URL", raising=False)
    monkeypatch.delenv("FOUNDERRADAR_JURY_TOKEN", raising=False)
    assert ai.relay_access() is None
    access = ai.RelayAccess("https://jury.invalid", "jury-only")
    def send(url, **kwargs):
        assert url == "https://jury.invalid/v1/founderradar/insights"
        assert kwargs["headers"]["Authorization"] == "Bearer jury-only"
        assert "some-other-key" not in json.dumps(kwargs)
        return SimpleNamespace(status_code=200, content=result().model_dump_json().encode())
    monkeypatch.setattr(ai.requests, "post", send)
    initial = ai.refresh_insight("company", research(), access)
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: SimpleNamespace(status_code=429))
    with pytest.raises(ValueError, match="Kontingent"):
        ai.refresh_insight("company", research(), access)
    assert ai.load_insight("company") == initial


def request(payload, token):
    output = []
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    async def send(event):
        output.append(event)
    scope = {
        "type": "http", "path": "/v1/founderradar/insights", "method": "POST",
        "http_version": "1.1", "scheme": "https", "query_string": b"",
        "headers": [(b"authorization", ("Bearer " + token).encode())],
    }
    asyncio.run(ai_relay.app(scope, receive, send))
    return output[0]["status"], json.loads(output[-1]["body"])


def test_relay_uses_dedicated_key_and_limits_invitation(tmp_path, monkeypatch):
    token = "relay-test-invitation-" + "a"*32
    monkeypatch.setenv("FOUNDERRADAR_JURY_TOKEN", token)
    monkeypatch.setenv("FOUNDERRADAR_JURY_EXPIRES", (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    monkeypatch.setenv("FOUNDERRADAR_PROJECT_OPENAI_KEY", "dedicated-project-key")
    monkeypatch.setenv("FOUNDERRADAR_PROJECT_MODEL", "project-model")
    monkeypatch.setenv("FOUNDERRADAR_AI_BUDGET", "1")
    monkeypatch.setenv("FOUNDERRADAR_RELAY_DB", str(tmp_path / "relay.sqlite3"))
    def provider(data, key, model):
        assert key == "dedicated-project-key" and model == "project-model"
        assert data.company == "TestPhoton GmbH"
        return result()
    monkeypatch.setattr(ai_relay, "provider_result", provider)
    body = research().model_dump_json().encode()
    assert request(body, "invalid")[0] == 401
    assert request(b"{}", token)[0] == 422
    status, payload = request(body, token)
    assert status == 200 and payload["model"] == "project-model" and "dedicated-project-key" not in str(payload)
    assert request(body, token)[0] == 429
    assert list(tmp_path.glob("*.sqlite3"))


def test_provider_uses_only_openai_responses_with_project_model(monkeypatch):
    def post(url, **kwargs):
        assert url == "https://api.openai.com/v1/responses"
        assert kwargs["headers"]["Authorization"] == "Bearer dedicated"
        payload = kwargs["json"]
        assert payload["model"] == "project-model" and payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        return SimpleNamespace(status_code=200, json=lambda: {
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": result().analysis.model_dump_json()}
            ]}],
        })
    monkeypatch.setattr(ai.requests, "post", post)
    assert ai.provider_result(research(), "dedicated", "project-model").model == "project-model"
