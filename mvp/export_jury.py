"""Export public screening results as a browsable folder for the jury."""
import argparse
import csv
from html import escape
from pathlib import Path

from mvp.ai import fingerprint, input_for, load_insight
from mvp.briefs import brief_for, report_html
from mvp.engine import load_last
from mvp.scoring import ranked


def export(directory: Path):
    run = load_last()
    if run is None:
        raise SystemExit("Kein gespeicherter Analyselauf vorhanden.")
    directory.mkdir(parents=True, exist_ok=True)
    profiles = directory / "profile"
    profiles.mkdir(exist_ok=True)
    rows = []
    counts = {"ranked": 0, "research": 0}
    labels = {"ranked": "Bewertbar", "research": "Recherche offen"}
    csv_file = directory / "Longlist.csv"
    with csv_file.open("w", encoding="utf-8-sig", newline="") as stream:
        table = csv.writer(stream, delimiter=";")
        table.writerow(("Unternehmen", "Branchen", "Status", "Score", "Risiko", "Marktpotenzialscore",
                        "Unternehmensscore", "Stage", "Produktbeschreibung", "Investmenthypothese"))
        for number, item in enumerate(ranked(run.assessments), start=1):
            if item.queue not in labels:
                continue
            dossier = item.dossier
            counts[item.queue] += 1
            brief = brief_for(item, live=run.options.mode == "live")
            insight = load_insight(dossier.id)
            if insight and insight.fingerprint != fingerprint(input_for(item)):
                insight = None
            filename = f"profile/{number}.html"
            (directory / filename).write_text(report_html(item, brief, run.options.as_of, insight=insight), encoding="utf-8")
            score = f"{item.score:.1f} / 100" if item.score is not None else "Offen"
            analysis = insight.result.analysis if insight else None
            summary = analysis.summary.text if analysis else brief.summary
            thesis = analysis.thesis.text if analysis else brief.thesis
            sectors = ", ".join(dossier.sectors)
            table.writerow((dossier.name, sectors, labels[item.queue], item.score, item.risk,
                            item.market_score, item.company_score, item.stage, summary, thesis))
            badge = " · KI-Auswertung gespeichert" if insight else ""
            rows.append(
                f'<article class="{item.queue}"><div class="score">{score}</div>'
                f'<h2><a href="{filename}">{escape(dossier.name)}</a></h2>'
                f'<small>{escape(sectors)} · {labels[item.queue]}{badge}</small>'
                f'<p>{escape(summary)}</p></article>'
            )
    (directory / "Analyselauf.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    (directory / "ERGEBNISSE.html").write_text(f"""<!doctype html>
<html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FounderRadar | Rechercheergebnisse</title>
<style>
body{{margin:0;background:#f4f7f5;color:#17231e;font:16px/1.55 system-ui,sans-serif}}
main{{max-width:960px;margin:auto;padding:3rem 1.2rem}}header{{margin-bottom:2rem}}
h1{{font-size:clamp(2.2rem,7vw,4rem);line-height:1;letter-spacing:-.055em;margin:.45em 0}}
small{{color:#3d554b}}a{{color:#14634c}}nav a{{margin-right:1.2rem}}
article{{background:white;border:1px solid #dce5df;border-radius:14px;margin:.75rem 0;padding:1rem 1.2rem}}
article.research{{border-left:4px solid #c68e41}}h2{{font-size:1.18rem;margin:0}}
p{{margin:.55rem 0}}.score{{float:right;font-weight:700;color:#14634c;margin-left:1rem}}
.research .score{{color:#794718}}
</style>
<main><header><strong>FounderRadar</strong><h1>Startup-Recherche</h1>
<p>Analyse zum {run.options.as_of:%d.%m.%Y} · {counts["ranked"]} bewertbare Firmen · {counts["research"]} mit offenen Nachweisen</p>
<p>Der Screening-Score wird aus den Belegen berechnet. Gespeicherte KI-Auswertungen sind an den Profilen gekennzeichnet.</p>
<nav><a href="Longlist.csv">Longlist als CSV</a><a href="Analyselauf.json">Analyselauf als JSON</a></nav></header>
{"".join(rows)}</main></html>
""", encoding="utf-8")
    return directory / "ERGEBNISSE.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(export(parser.parse_args().directory))
