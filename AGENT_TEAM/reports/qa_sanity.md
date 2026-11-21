# QA-Bericht `qa-sanity` (Stand 21.11.2026, Branch agents/data-quality-fixes, Basis fda6207)

Gesamturteil: **BESTANDEN** (kein BLOCKER, kein MAJOR; 3 MINOR). Es wurde kein Produktcode geändert.

## Ergebnisse je Prüfpunkt

1. Tests: `pytest -q` 770 passed, zweimal (auch mit `-p no:randomly`), jeweils ca. 10 s, keine Flakiness. `AGENT_TEAM/eval/test_precision.py` 10 passed.
2. Ende-zu-Ende offline (Scratch `AGENT_TEAM/reports/scratch/qa/`): 733 Zeilen, 0 Schemafehler (Draft 2020-12, `scores.schema.json`). Zweiter Lauf byte-identisch (json, csv, schema). Zahlen aus `scorer.md` reproduziert: min/Median/max 47,5/56,2/62,0, 96 distinct. Auch `examples/context/scores` und `examples/scoring` sind schema-valide.
3. Plausibilität: alle Scores in 0–100; Längenlimits (200/300/400) nirgends überschritten; keine Platzhalter (TODO/lorem/None/nan, "Projekt im Programm"). Alle Evidence-Einträge haben URL, außer der Regelnotiz `stage` ("pre_gruendung: keine Rechtsform belegt", url=None, punkte=None). kiutra in `examples/context/scores`: `zu_spaet`, 20,0. Gewichte kommen aus `scoring_config.yaml`. Stichprobe 10 Leads (seed 7): Begründungen konsistent mit den Zahlen. Unterer Rand: AthleteCapital (Sporthochschule), Prospera, EDISON (Hochschule der Medien) usw.; das liegt an Hochschulklasse und Fachgebiet-Proxy, nicht an einem Wortmuster im Text. Keine offensichtlich falsch platzierten Leads gefunden.
4. Integration: `pipeline.run_pipeline(SearchCriteria(industry=...), use_mock=True)` läuft; `app`, `dashboard`, `deep_dive`, `market_view`, `charts`, `ui_theme` importieren fehlerfrei. `matched_website` ist optional mit Default None, daher rückwärtskompatibel: `examples/context/real_dossiers.json` (4) und `examples/sourcing/sample_dossiers.json` (8) validieren als `EnrichedLead`. `to_dossier` fällt auf `matched_website` zurück (Zeile in evaluation/engine.py "website").
5. Regressionsrisiko: Fuzz mit 3000 Dossiers (je 4 zufällige Felder auf None/[]/{}/""/NaN/ungültiges Datum, kaputte `foerderung`-Einträge): 0 Ausnahmen, 0 verschluckte Fehler ("Dossier nicht lesbar"), 0 Schemaverstöße. Der einmalige `AttributeError` des evaluators ließ sich nicht reproduzieren (Endstand läuft stabil, `score_dossier` fängt zudem alles ab); die Erklärung "halb gespeicherter Stand" ist plausibel.
6. Brave-Key: Key nur aus Env oder `.env` (`context/website_match.py:329-340`), `.env` ist in `.gitignore:12` (per `git check-ignore` bestätigt). Test mit Fake-Key: Key nicht in URL, Cache-Keys, Candidate-Objekten (`found_at` ist die öffentliche `search.brave.com`-URL) und nicht in Fehlermeldungen (HTTP-401-Pfad). Key geht nur im Header `X-Subscription-Token` (Zeile 367).

## Befunde

### BLOCKER
Keine.

### MAJOR
Keine.

### MINOR

**M1 – Offline-Scores sind fast nur Katalogprofil (Gleichstände).** `scoring/engine.py` (Proxy-Kriterien), Reproduktion: Top-10-Liste in `scorer.md`; Plätze 5–10 haben identische Scores (60,7), alle 733 Leads `pre_gruendung`, confidence max 0,39. Ranking hängt stark an Hochschulklasse (TU9/Exzellenz) und Fachgebiet-Regex. Kein Fehler, aber Bias: z. B. "Mindocu" (Psychologie, Würzburg) Markt 65,9, "Prospera" (TH Aschaffenburg) ganz unten. Vorschlag: scorer dokumentiert das im Dashboard-Hinweis; Kalibrierung über Precision@30 (evaluator).

**M2 – Evidence ohne URL.** `scoring/engine.py` (Stage-Evidence `url: None`, `datum: None`, `punkte: None`), Reproduktion: `AGENT_TEAM/reports/scratch/qa/chk.py` auf `sc/scores.json`: 733 Treffer. Schema erlaubt es, die Zeile ist eine Regelnotiz, aber die Vorgabe "jede Evidence mit URL oder als neutral markiert" ist nur implizit (punkte=None) erfüllt. Vorschlag (scorer): Aussage mit "(neutral)" kennzeichnen oder `source_url` des Leads eintragen.

**M3 – Venv außerhalb des Worktrees.** `.venv` im Worktree zeigt auf `/Users/finnlipek/code/PromptFiction-/.venv` (geteilte Umgebung). Geprüft: Python importiert `models`/`scoring` aus dem Worktree, Ergebnisse gelten also für diesen Stand. Nur Hinweis für Reproduktion; kein Coder-Fix nötig (main).

## Hinweise
- Fuzz-Skript und Prüfskript: `AGENT_TEAM/reports/scratch/qa/chk.py`; Läufe `sc/`, `sc2/`, `d.json` im selben Ordner.
- Online-Pfade des Matchers (echte Brave-API, DuckDuckGo) wurden nicht live getestet, nur mit Stub-Requests.
