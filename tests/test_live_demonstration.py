import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from mvp.briefs import brief_for
from mvp.contracts import Run, RunOptions
from mvp.engine import known_company
from mvp.jobs import Jobs
from mvp.live_discovery import find_candidates
from mvp.scoring import assess


def lei(identity, name, created="2026-11-15", register="HRB 12345"):
    return {
        "id": identity, "links": {"self": f"https://api.gleif.org/api/v1/lei-records/{identity}"},
        "attributes": {"entity": {
            "creationDate": created, "status": "ACTIVE", "legalName": {"name": name},
            "legalAddress": {"country": "DE", "city": "Berlin"},
            "registeredAs": register,
        }},
    }


def test_fresh_lei_candidate_without_website_reaches_research_list():
    def fetch(url, *, api):
        query = parse_qs(urlsplit(url).query)
        assert api and query["filter[entity.creationDate]"] == ["2024-11-21..2026-11-22"]
        assert query["page[number]"] == ["2"]
        return {"retrieved_at": "2026-11-21T12:00:00Z", "text": json.dumps({
            "data": [
                lei("new", "Gamma Technologies GmbH"),
                lei("duplicate", "Known Technologies GmbH"),
                lei("old", "Old GmbH", created="2023-01-01"),
                lei("fund", "Test Fonds"),
            ],
            "meta": {"pagination": {"lastPage": 4}},
        })}

    web = SimpleNamespace(record=fetch, company_pages=lambda *args, **kwargs: [])
    options = RunOptions.cockpit_live(as_of=date(2026, 11, 21))
    records, count, next_page = find_candidates(web, options, {"gleif-duplicate"}, page=2, pages=1)
    assert count == 4 and next_page == 3
    assert [record["id"] for record in records] == ["gleif-new"]
    assessment = assess(known_company(records[0], web), options)
    assert assessment.queue == "research" and assessment.score is None
    assert assessment.dossier.website is None and assessment.dossier.sectors == []
    assert "Branchenzuordnung noch offen." in assessment.reasons
    assert assessment.dossier.sources[0].kind == "identity_live"


def test_live_brief_uses_new_observations_instead_of_editorial_catalog():
    path = Path(__file__).resolve().parents[1] / "data/mvp/demo-run.json"
    run = Run.model_validate_json(path.read_bytes())
    item = next(a for a in run.assessments if a.dossier.name == "REFACTUM GmbH")
    assert brief_for(item).editorial
    draft = brief_for(item, live=True)
    assert not draft.editorial
    assert draft.summary == item.dossier.facts["description"].value
    assert draft.why != brief_for(item).why
    item.dossier.facts["description"].value = "Aktualisierter Produkttext aus der Firmenquelle"
    assert brief_for(item, live=True).summary == item.dossier.facts["description"].value
    assert all(name != "Spanflug MAKE" for name, _, _ in draft.alternatives)


def test_initial_job_only_starts_on_a_fresh_copy(monkeypatch, tmp_path):
    monkeypatch.setenv("FOUNDERRADAR_MVP_DATA", str(tmp_path))
    job = Jobs()
    calls = []
    def start(options):
        calls.append(options)
        job.state["status"] = "running"
    monkeypatch.setattr(job, "start", start)
    job.start_initial(RunOptions.cockpit_live())
    job.start_initial(RunOptions.cockpit_live())
    assert len(calls) == 1 and calls[0].live_discovery and calls[0].max_age_months == 24
    job.state["status"] = "idle"
    (tmp_path / "latest.json").write_text("{}", encoding="utf-8")
    job.start_initial(RunOptions.cockpit_live())
    assert len(calls) == 1
