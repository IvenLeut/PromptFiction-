# Dashboard (`dashboard`), Stand 21.11.2026

Branch `agents/data-quality-fixes`. Nichts committet, nichts gepusht. `scoring/` und `evaluation/engine.py` habe ich
nicht angefasst, `models.py` auch nicht.

## Demo starten

```bash
.venv/bin/python -m streamlit run app.py          # http://localhost:8501, kein Netz nötig
```

- Standard ist **Snapshot (echte Leads)** → „Analyse starten“.
- Direktlinks: `/?view=snapshot` öffnet das Dashboard, `/?startup=foekat-03efmv0034` den Deep Dive zu Ymolution.
- Snapshot neu bauen, etwa nach Scoring-Änderungen: `.venv/bin/python -m demo_snapshot.build_snapshot`
  (`--dossiers PFAD`, `--stichtag`). Das dauert unter 1 s und braucht kein Netz.

## Was gebaut wurde

| Bereich | Inhalt | Dateien |
|---|---|---|
| Snapshot-Modus | Die 52 Online-Dossiers (`scratch/loop1/full_dossiers.json`) laufen durch `pipeline.evaluate_context(use_mock=False)` und werden als `AnalysisRun` gespeichert. `snapshot_meta.json` enthält, wofür der Vertrag kein Feld hat: Detail-Stage, `why_now`, `noise_class`, `earliness_delta_monate` aus `scoring.engine.score_all`, außerdem Backtest (`backtest.json`) und Best Find (geparst aus `best_find.md`). Laden dauert 0,15 s, die Datei ist 2,4 MB groß | `demo_snapshot/__init__.py`, `demo_snapshot/build_snapshot.py`, `demo_snapshot/*.json` |
| Startseite | Datenquelle wählbar: Snapshot (Standard), Demo-Fixtures, Live-Pipeline. Hero im HTGF-Stil | `app.py`, `ui_theme.py` |
| Übersicht | Filter für Branche, Stage, „Nur ohne DB-Profil“ und Top 10/20/50. Score-KPIs. Earliness-Band „11/11 früh erkannt, 21 Monate, n=11 Handauswahl“ und Earliness-KPIs (ohne DB-Profil 45/52, Median-Vorsprung, Website+Team belegt). Backtest-Diagramm pro Firma mit Bias-Hinweisen. **Best Find Ymolution**: Rang/Score/DB-Status als Chips, Signal-Zeitleiste mit Quell-URLs, Team, „Warum jetzt“, offene Punkte, Button zum Deep Dive. Der 3D-Potenzialraum ist erhalten, die Stage-Verteilung nutzt die Detailstufe. Ranking mit Score, Stage, Branche, Website (Link), Gründer, erstem Signal, DB-Check und Vorsprung. „Noise und Abgelehnt“ zeigt Noise-Zähler, zurückgehaltene und zu späte Leads sowie InhalPlus (gestrichen, finanziert, mit Quelle). Der JSON-Export ist erhalten | `dashboard.py`, `charts.py` |
| Deep Dive | Chips für erstes Signal, DB-Check (Prüfart Wayback/Datenbanksuche), Monate Vorsprung und Noise-Filter. „Warum jetzt“. Signal-Zeitleiste als Diagramm und Liste mit Quellen (Förderbeginn/-ende, idw, Wayback, DB-Eintrag, Gründung). Team-Karte mit Person, Rolle, Herkunft/Institution, Profil, Publikationen und OpenAlex-Link. Die bestehenden Tabs (Kennzahlen, Risiken, Quellen & Belege, Marktrecherche) bleiben | `deep_dive.py` |
| Tests | Die bestehenden Dashboard-Tests sind auf die neue Datenquellen-Auswahl angepasst. Neu: Ladezeit unter 3 s, Echtdaten-Prüfung, Parser, Earliness-Helfer, Übersicht mit Filtern und Best-Find-Klick, Rendern **aller 52 Deep Dives** per AppTest, Reproduktion des Builds | `tests/test_dashboard.py`, `tests/test_dashboard_snapshot.py` |

## Farben und Schriften (Quelle: Theme-CSS von htgf.de, gelesen am 21.11.2026)

Aus `wp-content/themes/htgf/assets/css/theme.css` und dem Inline-Preset in `index.html`:

| Rolle | Wert | HTGF-Variable |
|---|---|---|
| Akzent | **#FA6446** | `--htgf--preset--color--berry` |
| Fokus/Markierung | #F5653F | `--htgf--wcag--outline-color` |
| Zweitakzent | #64C2C8 | `--htgf--preset--color--mint` |
| Verlauf (Text) | #E8A339 → #68B0B5 | Inline-Gradient, 45° |
| Flächen | #F0EEEB / #F7F6F5 / #D9D4CC | `fond` / `accent-2` / `grey` |
| Dunkel | #221F19 | `fond-dark` |
| Text | #313131 | Inline-Style |
| Risiko niedrig | #106049 | `--green1` |

- Formen wie bei htgf.de: schwarze Pill-Buttons (`border-radius: 9999px`, Gewicht 500), Karten mit Radius
  1,5–2 rem, Großbuchstaben-Captions mit .05rem Laufweite.
- Für Text auf Weiß nutze ich ein abgedunkeltes Rost (#B8452C) und warmes Grau (#6B655D), damit der Kontrast reicht.
- Schriften: HTGF nutzt ITC Avant Garde Gothic und ESFace, beide lizenzpflichtig. Ersatz sind **Questrial**
  (geometrisch, nah an Avant Garde) für Headlines und **Hanken Grotesk** (ruhige Grotesk) für Text, beide OFL.
  Die Dateien liegen in `assets/fonts/` mit Lizenztext und werden als Data-URI eingebettet, damit sie auch offline
  laden. Der Kommentar steht in `ui_theme.py`.
- Eigene Marke „FounderRadar“: Wortmarke plus Verlaufspunkt, kein HTGF-Logo, keine HTGF-Bilder.

## GitHub-Vorlage

- Gesucht habe ich mit `gh search repos` nach „streamlit dashboard template“, „streamlit plotly dashboard“, „streamlit
  kpi cards“ u. a.
- Die bekannten Vorlagen (`dataprofessor/population-dashboard`, `Sven-Bo/streamlit-sales-dashboard`,
  `amrrs/streamlit-dashboard-template`) haben **keine Lizenz** und wurden deshalb nicht genutzt.
- Übernommen habe ich das Muster `style_metric_cards` aus **arnaudmiribel/streamlit-extras** (Apache-2.0, Commit
  `6c1736b`): `st.metric` per `data-testid` als Karte mit Akzentkante. Der Code wurde vorher gelesen; übernommen
  ist nur das Muster, nicht der Code.
- Ganze Apps passten nicht, weil der Aufbau mit Ranking, Deep Dive und Query-Params schon steht. Eingetragen in
  `NOTICE.md`.

## Testergebnis

- Gesamte Suite: **839 passed** (15 s), dazu `AGENT_TEAM/eval` 13 passed.
- Dashboard: 19 passed (13 bestehende + 6 neue).
- Manueller Start auf Port 8599: `/_stcore/health` antwortet „ok“, `/` liefert 200. Danach gestoppt.
- Screenshots per headless Chrome (CDP): `AGENT_TEAM/reports/dashboard/landing.png`, `overview.png`,
  `deepdive.png`.
- Im headless Chrome zeigt der 3D-Plot „WebGL not supported“. Das liegt am Screenshot-Browser ohne GPU, nicht an
  der App.

## Bekannte Grenzen

- **Der Snapshot friert den Scoring-Stand ein.** scorer ändert `scoring/` noch parallel. Nach dessen letzter Runde
  den Snapshot neu bauen; Test `test_build_snapshot_reproduces_from_dossiers` prüft, dass der Build läuft.
- Die Eingabedatei liegt in `AGENT_TEAM/reports/scratch/` und ist nicht versioniert. Ohne sie wird dieser Test
  übersprungen, und der eingefrorene JSON-Stand bleibt die Quelle.
- **Datenschutz:** `demo_snapshot/*.json` enthält echte Impressum- und Gründernamen (öffentliche Geschäftsdaten).
  Ob das ins Repo darf, entscheidet das Team (Gate, Punkt 6). Bis dahin besser nicht committen oder pseudonymisieren.
- Die Best-Find-Zeitleiste stammt aus der handgepflegten `best_find.md`, nicht aus der Engine. So ist sie in der
  App auch gekennzeichnet („handgeprüft“, Quelle genannt). Die Rangsätze aus der Datei werden verworfen; angezeigt
  wird der aktuelle Rang (5 von 52).
- „Monate Vorsprung“ pro Lead = erstes Signal bis DB-Eintrag, ohne Eintrag bis Stichtag (Scoring-Definition). Das
  ist eine andere Größe als der Backtest-Median (21 Monate bis zur ersten Finanzierungsmeldung/DB-Eintrag); beide
  sind beschriftet.
- „Kein DB-Profil“ ist kein Beweis. Die Prüfart wird immer genannt (Wayback/Datenbanksuche); vor dem Pitch von Hand
  prüfen.
- Der Noise-Filter markiert in diesem Lauf 0 von 52 Leads. Die App sagt das offen; vorgeführt wird nur der
  gestrichene InhalPlus.
- Alle Dashboard-Stages des Snapshots sind „Pre-Seed“ (Mapping in `evaluation/engine.py`). Das Dashboard zeigt
  deshalb die Detailstufe aus dem Scoring (Pre-Gründung / In Gründung / Pre-Seed).
- `AnalysisRun.criteria` kennt nur eine Branche. Der Snapshot trägt die häufigste ein (Industrial), und das
  Dashboard zeigt „Alle Branchen“.
