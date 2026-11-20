# Mitarbeit

## Setup

Python 3.11 oder neuer.

```bash
python3 -m venv .venv                                   # Windows: py -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt # Windows: .\.venv\Scripts\python.exe -m pip …
```

Neue Abhängigkeiten nur, wenn sie importiert werden, mit Versionsbereich in `requirements.txt`
(Laufzeit) bzw. `requirements-dev.txt` (Tests).

## Tests

```bash
.venv/bin/python -m pytest -q
```

Tests laufen ohne Netz. Externe Antworten werden einmal mitgeschnitten und gekürzt unter `tests/fixtures/`
abgelegt; im Test wird der Abruf injiziert (`fetch=`) oder `context.http.request` ersetzt
(siehe `context/ENRICHMENT.md`). Aus `examples/` lesen Tests nur die drei Vertragsschemas
(`tests/test_contracts.py`) und `sourcing/sample_dossiers.json`.

## Branches und Commits

- `main` ist der integrierte Stand; gearbeitet wird auf Branches `feature/<thema>` (z. B. `feature/scoring`,
  `feature/foekat-sourcing`) bzw. `chore/<thema>` für Aufräumarbeiten, Integration per Merge nach `main`.
- Commit-Nachrichten auf Englisch im Imperativ, eine Zeile Zusammenfassung
  (z. B. „Add live enrichment lookups so scoring gets sourced inputs“).
- Änderungen am gemeinsamen Vertrag (`models.py`, `scoring_models.py`, `research_models.py`) mit allen
  Modulverantwortlichen abstimmen und die Schemas in `examples/` neu erzeugen (`examples/README.md`).

## Module und Verantwortliche

| Schritt | Module | Doku | Verantwortlich |
| --- | --- | --- | --- |
| 1 Sourcing | `sourcing/` | `sourcing/FOEKAT.md` | Person 1 (Name eintragen) |
| 2 Kontext | `context/`, `research_models.py` | `context/ENRICHMENT.md` | Person 2 (Name eintragen) |
| 3 Scoring | `evaluation/`, `scoring/`, `scoring_input.py`, `scoring_models.py`, `scoring_market.py` | `SCORING_HANDOFF.md`, `scoring/SCORING.md` | Person 3 (Name eintragen) |
| 4 Dashboard | `app.py`, `dashboard.py`, `deep_dive.py`, `charts.py`, `market_view.py`, `ui_theme.py` | README | Person 4 (Name eintragen) |
| gemeinsam | `models.py`, `pipeline.py`, `demo_portfolio.py`, `mock_data.py` | README | alle |
