"""Build the offline demo snapshot from a finished online run (no network).

    python -m demo_snapshot.build_snapshot
    python -m demo_snapshot.build_snapshot --dossiers AGENT_TEAM/reports/scratch/gate2/dossiers.json

Steps: the step-2 dossiers (a `ContextResult`) are scored with the same live path as the app
(`pipeline.evaluate_context(use_mock=False)` -> evaluation/engine.py) and stored as an `AnalysisRun`
(`analysis_snapshot.json`). `snapshot_meta.json` adds per-lead fields of the scoring record that the
AnalysisRun contract has no place for (detailed stage, why-now, noise class), the earliness backtest
(`AGENT_TEAM/eval/backtest.json`) and the best find (`AGENT_TEAM/eval/best_find.md`). Re-run after the
scoring changes; the files are plain JSON and can be diffed.

`main` also writes `iven_companies.json` (demo_snapshot/iven_adapter.py): Iven's 34 registered companies
from `data/mvp/jury-reference.json`, shown as the separate category "Company Radar". Never merged with ours.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOSSIERS = ROOT / "AGENT_TEAM" / "reports" / "scratch" / "loop1" / "full_dossiers.json"
BACKTEST = ROOT / "AGENT_TEAM" / "eval" / "backtest.json"
BEST_FIND = ROOT / "AGENT_TEAM" / "eval" / "best_find.md"
REVIEW_FLAGS = Path(__file__).resolve().parent / "review_flags.json"   # hand-checked hints per lead, with source URL
OUT_DIR = Path(__file__).resolve().parent
STICHTAG = "2026-11-21"

# Fields of the scoring record (scoring/scores.schema.json) that the dashboard shows next to the AnalysisRun.
META_FIELDS = ("stage", "why_now", "noise_class", "noise_quelle", "status", "ausschluss_grund",
               "earliness_delta_monate", "team_score", "confidence", "branche")

_URL = re.compile(r"https?://\S+")


def _plain(text: str) -> str:
    """Markdown inline -> plain text (bold, backticks)."""
    return re.sub(r"\*\*|`", "", text).strip()


EN_MARKER = "<!-- best_find_en"


def parse_best_find(markdown: str) -> dict:
    """The recommended candidate (section "## 1. …") and the struck candidates of best_find.md.

    If the file has an English rendering (after the `<!-- best_find_en` marker), only that part is parsed, so the
    dashboard shows English text; otherwise the German source (labels Datum/Team/Warum jetzt anrufen/Offen).
    """
    english = EN_MARKER in markdown
    if english:
        markdown = markdown.split(EN_MARKER, 1)[1]
    sections = re.split(r"(?m)^## ", markdown)
    best = next((s for s in sections if s.startswith("1. ")), "")
    title = best.splitlines()[0] if best else ""
    match = re.match(r"1\.\s+(?P<name>[^(]+?)\s*\(FKZ\s*(?P<fkz>[^)]+)\)", title)
    body = best.split("\n", 1)[1] if "\n" in best else ""
    intro = next((p.strip() for p in body.split("\n\n") if p.strip() and not p.lstrip().startswith("|")), "")
    timeline = []
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3 or cells[0] in ("Datum", "Date", "") or set(cells[0]) <= {"-"}:
            continue
        url = _URL.search(cells[2])
        timeline.append({"when": _plain(cells[0]), "signal": _plain(cells[1]),
                         "source": url[0] if url else None, "source_note": None if url else _plain(cells[2])})

    def labelled(label: str) -> str | None:
        found = re.search(rf"\*\*{label}:\*\*\s*(.+?)(?:\n\*\*|\n\n|$)", body, re.S)
        return " ".join(_plain(found[1]).split()) if found else None

    rejected = []
    for section in sections:
        head = re.match(r"(?:Gestrichen|Struck):\s*(?P<name>[^(]+?)\s*\(FKZ\s*(?P<fkz>[^)]+)\)", section)
        if head:
            text = section.split("\n", 1)[1].strip().split("\n\n")[0]
            url = _URL.search(text)
            rejected.append({"name": head["name"], "fkz": head["fkz"], "reason": " ".join(_plain(text).split()),
                             "source": url[0].rstrip(").,") if url else None})
    return {
        "name": match["name"] if match else None, "fkz": match["fkz"] if match else None,
        "lead_id": f"foekat-{match['fkz'].lower()}" if match else None,
        # Rank sentences in best_find.md go stale with every scoring change; the dashboard shows the live rank.
        "intro": " ".join(s for s in re.split(r"(?<=\.)\s+", " ".join(_plain(intro).split())) if "Rang" not in s and "rank" not in s),
        "timeline": timeline,
        "team": labelled("Team"), "why_now": labelled("Why call now" if english else "Warum jetzt anrufen"),
        "open": labelled("Open" if english else "Offen"), "language": "en" if english else "de",
        "rejected": rejected, "source_file": "AGENT_TEAM/eval/best_find.md",
    }


# English rendering of the six bias notes in AGENT_TEAM/eval/backtest.json (same order; German source unchanged).
BIAS_EN = [
    "Survivorship: the reference list only contains companies that later became known and raised money. It measures "
    "how early the signal appears for winners, not how many EXIST projects become winners (precision) – that is "
    "what precision.py with hand labels is for.",
    "Name bias: only companies whose name appears in the EXIST project title were included. Companies whose project "
    "had a different name are not found, so the hit rate N/M is biased upwards. At the same time this is exactly the "
    "case the pipeline already covers without website matching.",
    "Catalogue delay: the signal date is the project start. When the entry actually became public in the "
    "Förderkatalog is not archived (no Wayback for detail pages); realistically weeks to months later. The lead "
    "time is therefore an upper bound by that delay.",
    "Database date: Wayback archives Crunchbase/Dealroom patchily; the first capture is an upper bound for when the "
    "profile appeared. The first funding announcement is therefore also used, and the earlier of the two counts.",
    "Small sample (n<=13), hand-researched, mostly TUM/Munich (press density). Median instead of mean; individual "
    "values are listed per company.",
    "No pipeline replay: today's sourcing only reads projects from 2024 on. The backtest applies the same mapping "
    "(map_project, priority) to the historical catalogue rows, but not context and scoring.",
]


def backtest_meta(data: dict) -> dict:
    """Headline, key numbers, bias notes and the per-company lead times of backtest.json."""
    summary = data.get("summary", {})
    companies = []
    for company in data.get("companies", []):
        external = company.get("first_external") or {}
        companies.append({"name": company.get("name"), "fkz": company.get("fkz"),
                          "signal_date": (company.get("signal") or {}).get("date"),
                          "signal_url": (company.get("signal") or {}).get("url"),
                          "external_kind": external.get("kind"), "external_date": external.get("date"),
                          "external_url": external.get("url"), "lead_months": company.get("lead_months"),
                          "in_headline": bool(company.get("in_headline")),
                          "htgf_portfolio": bool(company.get("htgf_portfolio"))})
    early, n = summary.get("early"), summary.get("in_headline")
    median, lo, hi = summary.get("median_lead_months"), summary.get("min_lead_months"), summary.get("max_lead_months")
    headline_en = (f"{early}/{n} spotted early, median {round(median)} months before the first funding announcement or "
                   f"database entry (range {round(lo)}–{round(hi)} months; n={n}, hand-picked known spin-offs, "
                   f"see selection bias below)") if None not in (early, n, median, lo, hi) else data.get("headline")
    bias = BIAS_EN if len(data.get("bias", [])) == len(BIAS_EN) else data.get("bias", [])
    return {"headline": headline_en, "generated_at": data.get("generated_at"),
            "n": summary.get("in_headline"), "early": summary.get("early"),
            "median_months": summary.get("median_lead_months"),
            "min_months": summary.get("min_lead_months"), "max_months": summary.get("max_lead_months"),
            "bias": bias, "companies": companies,
            "source_file": "AGENT_TEAM/eval/backtest.json"}


def build(dossiers_path: Path, out_dir: Path = OUT_DIR, stichtag: str = STICHTAG) -> tuple[Path, Path]:
    # Late imports: the module docstring and argparse help work without the pipeline.
    from models import AnalysisRun, ContextResult, Industry, SearchCriteria
    from pipeline import evaluate_context
    from scoring.engine import score_all
    from scoring.sources import load_dossiers

    context = ContextResult.model_validate_json(dossiers_path.read_text(encoding="utf-8"))
    result = evaluate_context(context.leads, use_mock=False)
    result.issues = context.issues + result.issues
    # AnalysisRun.criteria names one category; the snapshot spans all of them, so the most frequent one
    # is recorded and the dashboard shows "All industries" for snapshot runs.
    common = Counter(lead.industry for lead in context.leads).most_common(1)
    industry = common[0][0] if common else Industry.INDUSTRIAL
    created = datetime.fromisoformat(stichtag).replace(hour=12, tzinfo=timezone.utc)
    run = AnalysisRun(criteria=SearchCriteria(industry=industry, limit=min(max(len(context.leads), 1), 200)),
                      mode="live", created_at=created, discovered_count=len(context.leads),
                      enriched_count=len(context.leads), result=result)

    rows = score_all(load_dossiers(dossiers_path), stichtag=stichtag)
    by_id = {row["lead_id"]: {field: row.get(field) for field in META_FIELDS} for row in rows}
    noise = Counter(row.get("noise_class") or "unknown" for row in rows)
    meta = {
        "kind": "snapshot", "stichtag": stichtag,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_file": str(dossiers_path.relative_to(ROOT)) if dossiers_path.is_relative_to(ROOT) else dossiers_path.name,
        "lead_count": len(result.leads), "issue_count": len(result.issues),
        "noise": {"counts": dict(noise), "note": "noise_class from scoring/engine.py (agency/consultancy heuristic)"},
        "leads": by_id,
        "backtest": backtest_meta(json.loads(BACKTEST.read_text(encoding="utf-8"))) if BACKTEST.exists() else None,
        "best_find": parse_best_find(BEST_FIND.read_text(encoding="utf-8")) if BEST_FIND.exists() else None,
        "review_flags": review_flags(REVIEW_FLAGS, set(by_id)),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis_path, meta_path = out_dir / "analysis_snapshot.json", out_dir / "snapshot_meta.json"
    analysis_path.write_text(redact_personal_emails(english_display(run.model_dump_json(indent=1))) + "\n", encoding="utf-8")
    meta_path.write_text(redact_personal_emails(english_display(json.dumps(meta, ensure_ascii=False, indent=1))) + "\n", encoding="utf-8")
    return analysis_path, meta_path


def review_flags(path: Path, lead_ids: set[str]) -> dict:
    """Hand-checked hints (review_flags.json) for leads of this snapshot; each needs a flag text and a source URL."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {lead_id: [f for f in flags if f.get("flag") and str(f.get("url", "")).startswith("https://")]
            for lead_id, flags in data.items() if lead_id in lead_ids and isinstance(flags, list)}


# Output contract: e-mail only as a generic company mailbox (imprint), never personal addresses.
GENERIC_MAILBOXES = {"info", "contact", "kontakt", "hello", "hallo", "office", "mail", "team", "support",
                     "sales", "press", "presse", "service", "post", "welcome"}
_EMAIL = re.compile(r"(\\n)?([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


# English display copy for fixed German texts the context step wrote into the frozen dossiers
# (first-call questions, website-match reasons). Applied to the serialized snapshot only; source data unchanged.
TEXT_EN = {
    "Welchen Markt adressiert ihr und wie grenzt ihr ihn ab?": "Which market do you address and how do you define it?",
    "Was ist der technische Ansatz und welche Nachweise gibt es?": "What is the technical approach and what evidence exists?",
    "Welche Alternativen nutzen eure Zielkunden heute?": "What alternatives do your target customers use today?",
    "Über welche Kanäle gewinnt ihr Kunden?": "Through which channels do you win customers?",
    "Welchen Kapitalbedarf habt ihr nach dieser Runde?": "How much capital do you need after this round?",
    "Wie groß ist die geplante Runde in Euro?": "How large is the planned round in euros?",
    "Welche Pre-Money-Bewertung fordert ihr in Euro?": "What pre-money valuation are you asking for in euros?",
    "Welche Investoren sind bereits beteiligt?": "Which investors are already on board?",
    "Wer gehört zum Gründungsteam und wer bringt welche Erfahrung mit?": "Who is on the founding team and what experience does each person bring?",
    "Welches konkrete Kundenproblem löst ihr?": "Which concrete customer problem do you solve?",
    "Welche Kundengruppe nutzt das Produkt?": "Which customer group uses the product?",
    "Welche Piloten, Design-Partner oder Absichtserklärungen gibt es?": "Which pilots, design partners or letters of intent exist?",
    "Gibt es Schutzrechte oder Patentanmeldungen?": "Are there IP rights or patent applications?",
    "Welcher Produktstand ist heute nachweisbar?": "Which product stage can be evidenced today?",
    "Welche Rechtsform hat das Vorhaben heute (Impressum nicht gefunden)?": "What legal form does the venture have today (no imprint found)?",
    "Name nur erwähnt (Verzeichnis/Portal/Presse), nicht die Website des Projekts": "name only mentioned (directory/portal/press), not the project's website",
    "keine Bestätigung durch Institut/EXIST/Thema/Ort: möglicher Namensvetter": "no confirmation by institute/EXIST/topic/location: possible name clash",
    "Projektname prominent (Kopf/Überschrift)": "project name prominent (header/heading)",
    "Projektname kommt auf der Seite nicht vor": "project name not on the page",
    "Projektname im Seitentitel": "project name in page title",
    "Projektname nur im Fließtext": "project name only in body text",
    "Platzhalter-/Parking-Seite": "placeholder/parked page",
    "Domain enthält Projektname": "domain contains project name",
    "Domain = Projektname": "domain = project name",
    "Impressum nennt den Namen": "imprint names the company",
    "Rechtsform beim Namen": "legal form next to the name",
    "Start-up-/Gründungsbezug": "start-up/founding reference",
    "Malus: Agentur/Webdesign": "penalty: agency/web design",
    "Malus: Online-Shop": "penalty: online shop",
    "Seite ohne Text": "page without text",
    "erster Suchtreffer": "first search hit",
    "Gründername genannt": "founder name mentioned",
    "EXIST erwähnt": "EXIST mentioned",
    "zwei Themenbegriffe (": "two topic terms (",
    "Themenbegriffe (": "topic terms (",
    "Institut genannt (": "institute mentioned (",
    "Ort genannt (": "location mentioned (",
    "verlinkt von Projektquelle ": "linked from project source ",
    ". Fundstelle: ": ". Found at: ",
}


def english_display(text: str) -> str:
    for de, en in TEXT_EN.items():
        text = text.replace(de, en)
    return text


def redact_personal_emails(text: str) -> str:
    """Replaces non-generic e-mail addresses (e.g. firstname.lastname@…) in serialised JSON."""
    def repl(m):
        if m.group(2).lower() in GENERIC_MAILBOXES:
            return m.group(0)
        return (m.group(1) or "") + "[E-Mail entfernt]"
    return _EMAIL.sub(repl, text)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m demo_snapshot.build_snapshot", description=__doc__.split("\n\n")[0])
    parser.add_argument("--dossiers", type=Path, default=DEFAULT_DOSSIERS, help="ContextResult JSON from step 2")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="Output folder (default: demo_snapshot/)")
    parser.add_argument("--stichtag", default=STICHTAG, help="Reference date YYYY-MM-DD (default: %(default)s)")
    args = parser.parse_args(argv)
    date.fromisoformat(args.stichtag)
    analysis_path, meta_path = build(args.dossiers.resolve(), args.out, args.stichtag)
    print(f"{analysis_path} ({analysis_path.stat().st_size // 1024} KB), {meta_path}")
    # Second, separate dataset: Iven's company search (category "Company Radar"), values copied 1:1.
    from demo_snapshot.iven_adapter import IVEN_PATH, REFERENCE, build_iven
    if REFERENCE.exists():
        iven_path = build_iven(REFERENCE, args.out / IVEN_PATH.name)
        print(f"{iven_path} ({iven_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
