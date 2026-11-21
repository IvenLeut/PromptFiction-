"""Iven's company search (category "Höheres Risiko") in the dashboard's display format.

Source: Iven's reference run `data/mvp/jury-reference.json` (package `mvp/`, rule set `early-stage.2`,
config/early_stage.v2.json). His values are authoritative: this adapter copies scores, criterion points,
stage, risk label, queue and texts 1:1 and never recalculates them. The texts (product description,
investment hypothesis, why-now, first question) come from `mvp.briefs.brief_for(..., live=True)`, exactly
as `mvp/export_jury.py` wrote `Ergebnisse/Longlist.csv`.

Direction: Iven has no numeric risk score. `risk` is his text label (e.g. "Prüfbedarf: Marktvalidierung")
and is shown as a label; `company_score` (Produkt & Technologie) and `market_score` (Kunde & Nutzen) are
"higher is better", like ours. The two rankings come from different rule sets and are never merged.

    python -m demo_snapshot.build_snapshot          # builds both snapshots (ours + iven_companies.json)
    python -m demo_snapshot.iven_adapter            # only this one
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "mvp" / "jury-reference.json"
IVEN_PATH = Path(__file__).resolve().parent / "iven_companies.json"

CATEGORY = "Firmen-Radar"
CATEGORY_LONG = "Firmen-Radar · junge GmbH/UG (höheres Risiko)"
STATUS = {"ranked": "Bewertbar", "research": "Recherche offen", "excluded": "Außerhalb Suchprofil"}
FACT_LABELS = {
    "register": "Handelsregister", "country": "Deutschland-Beleg", "project_link": "Förderprojekt-Bezug",
    "founding": "Gründung", "technology": "Technischer Ansatz", "product": "Produkt", "buyer": "Kundentyp",
    "benefit": "Kundennutzen", "team": "Team", "validation": "Entwicklungsnachweis", "description": "Beschreibung",
    "contact_email": "Firmenpostfach", "regulation": "Regulierung", "seed_round": "Finanzierungsrunde",
    "service_business": "Dienstleistungsgeschäft", "late_round": "Spätere Runde", "inactive": "Inaktiv",
}
_LINKEDIN_PROFILE = re.compile(r"https://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/in/[^/?#\s]+/?$", re.I)


def _source(s) -> dict:
    return {"title": s.title, "url": s.url, "retrieved_at": s.retrieved_at, "kind": s.kind}


def company_record(rank: int, item, *, live: bool) -> dict:
    """One assessment as a plain display dict. Values are copied, not recomputed."""
    from mvp.briefs import brief_for
    d = item.dossier
    brief = brief_for(item, live=live)
    founding = d.facts.get("founding")
    return {
        "id": d.id, "rank": rank, "name": d.name, "website": d.website, "sectors": list(d.sectors),
        "queue": item.queue, "status": STATUS[item.queue],
        # Iven's numbers 1:1 (None stays None: "unknown is never a numeric default").
        "score": item.score, "score_upper": item.score_upper,
        "company_score": item.company_score, "market_score": item.market_score,
        "validation_score": next((c.points for c in item.criteria if c.key == "validation"), None),
        "risk": item.risk, "stage": item.stage, "coverage": item.coverage, "htgf_fit": item.htgf_fit,
        "criteria": [c.model_dump(mode="json") for c in item.criteria],
        "reasons": list(item.reasons), "next_steps": list(item.next_steps), "hypothesis": item.hypothesis,
        # Texts as in Ergebnisse/Longlist.csv and the profile pages.
        "summary": brief.summary, "thesis": brief.thesis, "why": brief.why, "question": brief.question,
        "segment": brief.segment, "gate": brief.gate,
        "email": brief.email[0] if brief.email else None,
        "founding": {"earliest": str(d.earliest_founding) if d.earliest_founding else None,
                     "latest": str(d.latest_founding) if d.latest_founding else None,
                     "basis": d.founding_basis,
                     "quote": founding.quote if founding else None,
                     "url": founding.source_url if founding else None},
        "identity_status": d.identity_status, "refresh_status": d.refresh_status,
        "project_ids": list(d.project_ids), "issues": list(d.issues),
        "facts": [{"key": k, "label": FACT_LABELS.get(k, k), "value": f.value, "quote": f.quote,
                   "url": f.source_url, "basis": f.basis} for k, f in d.facts.items()],
        "team": [{"name": t.name, "role": t.role, "biography": t.biography, "source_url": t.source.url,
                  "linkedin": t.profile_url if t.profile_url and _LINKEDIN_PROFILE.match(t.profile_url) else None}
                 for t in d.team_evidence],
        "sources": [_source(s) for s in d.sources],
        "market_comparisons": [{"name": m.name, "text": m.text, "url": m.source.url} for m in d.market_comparisons],
    }


def build_iven(reference: Path = REFERENCE, out: Path = IVEN_PATH) -> Path:
    """Write `iven_companies.json` from Iven's reference run (personal e-mail addresses redacted)."""
    from demo_snapshot.build_snapshot import redact_personal_emails
    from mvp.contracts import Run
    from mvp.scoring import ranked
    run = Run.model_validate_json(reference.read_bytes())
    order = ranked(run.assessments)
    if [a.dossier.id for a in order] != [a.dossier.id for a in run.assessments]:
        raise ValueError("Referenzlauf ist nicht in der Rangfolge des Firmen-Radars gespeichert.")
    live = run.options.mode == "live"   # mvp/export_jury.py: brief_for(item, live=run.options.mode == "live")
    companies = [company_record(i, item, live=live) for i, item in enumerate(order, 1) if item.queue in ("ranked", "research")]
    payload = {
        "kind": "iven_companies", "category": CATEGORY, "category_long": CATEGORY_LONG,
        "origin": "Firmen-Radar (mvp/, Branch feature/founderradar-investment-cockpit)",
        "rule_version": run.rule_version, "schema_version": run.schema_version, "run_id": run.id,
        "as_of": str(run.options.as_of), "source_snapshot_date": run.source_snapshot_date,
        "max_age_months": run.options.max_age_months, "sectors": list(run.options.sectors),
        "input_hash": run.input_hash, "counts": dict(run.counts),
        "reference_file": str(reference.relative_to(ROOT)) if reference.is_relative_to(ROOT) else reference.name,
        "weights": {c.key: c.weight for c in order[0].criteria} if order else {},
        "companies": companies,
    }
    out.write_text(redact_personal_emails(json.dumps(payload, ensure_ascii=False, indent=1)) + "\n", encoding="utf-8")
    return out


@lru_cache(maxsize=1)
def load_iven() -> dict | None:
    """The built display data, or None if `iven_companies.json` is missing. Callers must not mutate it."""
    if not IVEN_PATH.exists():
        return None
    return json.loads(IVEN_PATH.read_text(encoding="utf-8"))


def origin_line(data: dict) -> str:
    """'Ivens Firmen-Suche, Regelwerk early-stage.2, Stand 21.11.2026'."""
    y, m, d = data["source_snapshot_date"].split("-")
    return f"Firmen-Radar, Regelwerk {data['rule_version']}, Stand {d}.{m}.{y}"


if __name__ == "__main__":
    path = build_iven()
    print(f"{path} ({path.stat().st_size // 1024} KB)")
