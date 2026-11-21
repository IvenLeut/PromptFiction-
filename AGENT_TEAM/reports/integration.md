# Integration (`integrator`), Stand 21.11.2026

Branch `agents/integration-cockpit` (von main @ 1986db0). Lokal committet, **nicht gepusht**:

| Commit | Inhalt |
|---|---|
| `21c69f1` | Merge `origin/codex/cockpit-interface-fixes` (Leonard, enthält Ivens `feature/founderradar-investment-cockpit`) |
| `71a60a3` | LinkedIn pro Person in Team-Karte und Kontakt-Box |
| `a92a520` | Polish: Gründungsdatum, lesbare Labels, Hypothese, dentson-Prüfhinweis |

## Start

```bash
.venv/bin/python -m streamlit run app.py        # Standard: Snapshot (52 echte Leads, ohne Netz) -> "Analyse starten"
.venv/bin/python -m streamlit run cockpit.py    # Ivens Cockpit eigenständig (Demo, FOUNDERRADAR_MODE=demo|live)
.venv/bin/python -m demo_snapshot.build_snapshot   # Snapshot neu bauen (< 1 s)
```

Direktlinks: `/?view=snapshot`, `/?startup=foekat-03efmv0034` (Ymolution).

## Testergebnis

- `pytest -q`: **902 passed** (vorher main 787 + Ivens/Leonards Tests; neu: 4 Integrationstests)
- `pytest AGENT_TEAM/eval`: **13 passed**
- Byte-identisch zu vorher:
  - Snapshot-Scores aller 52 Leads (Score, Teilscores, Stage, Hypothese, Confidence)
  - Offline-Lauf 733 Leads (`context --offline --light` + `scoring --stichtag 2026-11-21`, Vergleich gegen eine Worktree von 1986db0)
  - `examples/scoring/` und `examples/context/scores/`
- Smoke headless auf Port 8599: `/_stcore/health` = `ok`, `/?view=snapshot` = 200. Danach gestoppt.
- AppTest ohne Exception für:
  - Landing
  - Snapshot-Dashboard (Radar)
  - Ansicht „Screening & Entscheidungen“
  - Ansicht „Investment-Cockpit“, alle vier Seiten (Überblick, Dealflow, Firmenbrief, Aktivitäten)
  - alle **52 Deep Dives**, zusammen 2,8 s
- Screenshots: keine, Playwright ist nicht installiert (optional).

## Aufgabe 1: Merge, was von wem kam

Vorab gelesen: `git log`, die Diffs beider Seiten ab dem Merge-Base e63f778 und die Berichte final_gate, scorer, matcher und dashboard.

### Datenlogik (Basis: unsere Version)

Aus Leonards drei Fix-Commits eingearbeitet:

| Fix (Commit) | Wo bei uns |
|---|---|
| **Stichtag für datierte Fakten und Förderungen** (ab7829b) | `scoring/engine.py`: `dated_fact`/`dated_rows` für alle Fakten, auch unsere neuen (Hinweisjahr, Website-Text, Partner, Team, Förderung). Stichtag-genaue Altersgrenze `beyond_age_limit` mit Monatsende bei `JJJJ-MM`. `deutschland_beleg` darf nicht nach dem Stichtag datiert sein. `evaluation/engine.py::to_dossier(as_of=…)` filtert Evidence, Signale, Förderungen, Partner (Zitat bleibt), Patente und Profile nach Stichtag und Quellbindung und verwirft Nicht-Demo-`assumption`-Belege. Unsere `_is_signal`-Regeln bleiben |
| **Subject-Header normalisieren** (51677db) | `scoring_input.source_binding` (automatisch gemergt), genutzt in context/engine (FKZ-Referenz, Signalfilter) und evaluation |
| **Datenübergaben reparieren** (032f20d) | Quote-Cache mit Modell und vollem Signal im Schlüssel, Treffer per Index (`cached_quotes`). Deep Copies an der Evaluator-Grenze (`pipeline._call_evaluator`, Mock-Pfad). `scoring_status` und `earliness_delta_months` im `EvaluationScores`; Leads mit „zurück an Sourcing“ erscheinen als Pipeline-Hinweis. Cutoff `scoring_input.as_of or screening_as_of or heute`. `founded_day`. `GERMAN_SEAT` im SQLite-Lader. `score_lead` als öffentliche Funktion. Decimal-Marktrechnung. `ValuationResult.blocked_reason`. Screening-Export als Eingabe (`read_context_leads`) |
| **Scoring-CLI wie Pipeline** (032f20d, ab7829b) | `python -m scoring` behandelt Lead-Listen jetzt wie die Pipeline: frischer `ScoringInput` am Stichtag (ohne `--stichtag`: `scoring_input.as_of`), Zulassungsprüfung `admission_issue` (kein DE-Beleg oder VC bestätigt -> `zurueck_an_sourcing`). Eingefrorene `ScoringInput`-Listen werden ebenfalls gelesen. Unsere Beispiele bleiben byte-identisch |

Weitere Auflösungen:

- **`sourcing/engine.py`:** Unser Förderkatalog-Provider bleibt Standard. Leonards Screening-Export-Klassen kamen dazu (`ScreeningReport`, `read_context_leads`). Ist `FOUNDERRADAR_SCREENING_REPORT` gesetzt, liest `search` den Bericht statt des Förderkatalogs.
- **`models.py`:** additiv. Unser `matched_website` und die Kommentarstruktur bleiben. Von Leonard/Iven kamen:
  - `founded_day`, `founding_country`, `field_evidence`, `screening_as_of`, `first_signal_date` (RawLead)
  - Cockpit-Felder: `problem_statement`, `funding_events`, `InvestmentArgument`, `evaluation_v2`, Fund-Fit-Felder u. a.
  - `FounderProfile.background` bleibt `Literal["tech","business","beides"]`; Ivens Code setzt keine anderen Werte.
  - Doppeltes `evidence`-Feld in `EnrichedLead` entfernt (unsere Position bleibt).
- **`context/engine.py`:** unser refaktorierter Ablauf bleibt. Neu: `as_of = as_of or lead.screening_as_of`, `field_evidence` aus dem Screening-Export als Evidence, Signale nach Quellbindung und Stichtag gefiltert (die Snapshots in `scoring_sources` bleiben vollständig), `first_signal_date` aus Schritt 1 hat Vorrang.
- **`pipeline._preserve`:** Leonards Ausnahme übernommen: Kontext darf ein leeres `first_signal_date` füllen, wenn ein datierter Beleg es stützt. Sonst gilt weiter `InputModifiedError`.
- **Schemas/Beispiele neu erzeugt:** `examples/analysis-schema.json`, `context-schema.json`, `market-input-schema.json` und `analysis-demo.json` (Demo-Lauf AI/Software). `scoring-input-schema.json` ist unverändert.
- **Snapshot neu gebaut:** Er ist wegen `evaluation_v2` (voller Scoring-Datensatz je Lead) von 2,4 auf 3,0 MB gewachsen. Ladezeit-Test < 3 s grün.

### Neue Module (vollständig übernommen)

- Module: `cockpit.py`, `cockpit_context.py`, `cockpit_data.py`, `cockpit_details.py`, `cockpit_research.py`, `cockpit_research_v2.py`, `cockpit_service.py`, `cockpit_style.py`, `cockpit_visuals.py`, `analyst_store.py`, `screening.py`, `scorecard.py`, `config/htgf.v1.json`, `docs/COCKPIT.md`
- Tests: `test_analyst`, `test_cockpit`, `test_workspace`, `test_research_display`, `test_screening`, `test_interface_regressions`

### Dashboard (Basis: HTGF-Theme, Snapshot, Earliness/Best Find)

- **Umschalter oben mit drei Ansichten:**
  - **Radar**: Standard, unser Dashboard unverändert.
  - **Screening & Entscheidungen**: Leonards/Ivens Longlist mit Fund Fit, Screening-Status, Hoher Priorität, Suche, Filtern und Sortierung, im HTGF-Stil (KPI-Karten, Pill-Buttons).
  - **Investment-Cockpit**: Ivens Workspace (Überblick, Dealflow, Firmenbrief, Aktivitäten) als `cockpit.render_workspace(run)`. Die Navigation sitzt oben statt in der Sidebar.
- **Cockpit-Styling:** `cockpit_style.theme(embedded=True)` färbt nur die Komponentenklassen mit den HTGF-Tokens. Seitenrahmen, Schriften und Buttons bleiben bei `ui_theme`. `streamlit run cockpit.py` sieht weiter aus wie bisher.
- **Deep Dive:** neuer Tab **„Investment-Briefing & Entscheidung“** (Ivens Inhalt auf Deutsch, HTGF-Stil). Er enthält:
  - Fund-Fit-Status und harte Ausschlüsse
  - „Warum jetzt Kontakt?“
  - Scorecard
  - Stärken und Risiken mit Belegen
  - Business & Markt, Traktion & Finanzierung
  - Entdeckung mit datierten Belegen
  - **Analystenentscheidung** (Formular, `analyst_store`)
- Entscheidungen teilt der Deep Dive mit dem Screening und dem Cockpit (Namespace `demo` bzw. `live`).
- `contact_url` nimmt jetzt auch das Impressums-Postfach, wenn ein Beleg es wörtlich zitiert (Leonards Fix). Redigierte Adressen („[E-Mail entfernt]“) passen nie.
- `app.py`: „Neue Analyse“ räumt auch den Cockpit-State auf. `FOUNDERRADAR_MODE=live` wählt die Live-Quelle vor. Fehler beim Screening-Export werden lesbar angezeigt.

### Bewusst nicht übernommen (mit Grund)

- **Leonards/Ivens `dashboard.py` als Startansicht**: Es hätte unsere Snapshot-, Earliness- und Best-Find-Story ersetzt. Ihr Inhalt läuft vollständig als Ansicht „Screening & Entscheidungen“.
- **Ivens `deep_dive.py` als Hauptlayout**: Unser Deep Dive bleibt Basis. Ivens Abschnitte stehen im neuen Tab. Die Marktrenderer `native_market`, `native_competition` und `transactions` erscheinen nicht doppelt im Deep Dive; sie sind im Cockpit-Firmenbrief erreichbar. Unser Tab „Marktrecherche“ bleibt.
- **`.streamlit/config.toml` ihrer Seite** (beige Palette): Es gilt das HTGF-Theme.
- **SCORING.md-Satz „Agentur-Regel erkennt keine Verneinung“**: Bei uns ist das gelöst (`wort_unverneint`), deshalb gestrichen.
- **Tests angepasst** (nicht gelöscht):
  - `test_cockpit`: erwartete Werte des kalibrierten Scoring-Beispiels (75,7 / 0,75 / 0,55 / 0,03 statt der Werte vor der Kalibrierung)
  - `test_analyst`: wählt zuerst die Demo-Quelle und findet das Radio über das Label
  - `test_dashboard`: Radar bleibt Standard, Tab-Anzahl 4
  - `test_sourcing_foekat`: `first_signal_date` ist ausgenommen, wenn es belegt nachgetragen wurde

## Aufgabe 2: LinkedIn

- **Daten waren schon da:** `context/team.py` legt öffentliche Profile als `founder_profiles.source_url` oder als Evidence (`field="founder_profiles"`, Fundtext „Name: …“, URL `linkedin.com/in/…`) ab. Beides steht im AnalysisRun und im Snapshot (20 Profile bei 16 Leads), es war kein Durchreichen nötig.
- **Logik:** `dashboard.linkedin_profile/linkedin_link` liefert den Button **„LinkedIn“**, wenn ein Profil belegt ist, sonst **„Auf LinkedIn suchen“** (`https://www.linkedin.com/search/results/people/?keywords=<Name>%20<Firma>`).
- **Anzeige:**
  - Team-Karte: Pill-Link mit `target="_blank" rel="noopener noreferrer"`
  - Kontakt-Box: ein `st.link_button` pro Person, öffnet einen neuen Tab. Nichts wird versendet.
- **E-Mails:** Keine privaten Adressen, der Snapshot-Build redigiert sie weiter.

## Aufgabe 3: Schönheitsfehler

- **(a) Ymolution „Gründungsjahr Unbekannt“:** Das Datum ging nicht in der Pipeline verloren, es war nie im Dossier.
  - Das Impressum belegt nur „Ymolution GmbH“ (Rechtsform), kein Datum.
  - Der 08.01.2026 steht nur in der Handrecherche `AGENT_TEAM/eval/best_find.md` (Pressemitteilung der Unimedizin Greifswald).
  - Lösung: Der Deep Dive zeigt **„Gründung“** nur bei belegtem Datum, also aus Schritt 1/2 oder aus der datierten „gegründet“-Zeile der Best-Find-Zeitleiste, dann mit Quelle-Link. Bei Ymolution erscheint 08.01.2026 mit Quelle.
  - Zusätzlich angezeigt: Rechtsform, Produkttyp und die Detail-Stage (vorher stand bei allen 52 nur „Pre-Seed“).
- **(b) Rohwerte:** `ui_theme.readable` übersetzt sie in Labels, etwa `am_markt` -> „Am Markt“, `pre_gruendung` -> „Pre-Gründung“, `non_vc_funded`, `hardware_software`, `patent_erteilt` usw. Das gilt im Deep Dive, im Briefing und in den Cockpit-Faktenzeilen.
- **(c) Hypothese:**
  - Deep Dive: Zeilen „Warum investieren“, „Belegte Stärken“, „Nächster Meilenstein“, „Hauptrisiko“ mit Aufzählung. „(Proxy)“ wird zum kleinen Badge mit Tooltip.
  - Cockpit-Firmenbrief: die Proxy-Kette ist zu einem Schlusshinweis zusammengefasst.
  - Der Text bleibt der des Scorings (`thesis_parts`, Test prüft das).
- **(d) dentson:** Die Daten geben es her. Im Cache liegt der Brave-API-Treffer eines öffentlichen LinkedIn-Profils eines Investors (Seitenstand 29.10.2026): „That question is part of why I chose to invest in dentson.“
  - Neu: `demo_snapshot/review_flags.json` mit Hinweis, Zitat, URL, Datum, Herkunft und Erstgesprächsfrage. Der Snapshot-Build übernimmt es in `snapshot_meta.json`.
  - Anzeige „Möglicherweise Angel-finanziert – prüfen“: als Chip und Warnung im Deep Dive, als Spalte „Prüfhinweis“ im Ranking und als erste Frage für das Gespräch.
  - Der Score ändert sich nicht.

## Offene Punkte

1. **Push/PR** ist nicht gemacht (Vorgabe). Die Branch ist bereit für ein Review.
2. **`demo_snapshot.build_snapshot --stichtag`** wirkt nur auf die Meta-Daten. Das Scoring der AnalysisRun nutzt `scoring_input.as_of` bzw. heute. Heute (21.11.2026) ist das identisch; bei einem späteren Neubau `evaluate_context` einen Stichtag mitgeben.
3. **dentson-Hinweis ist eine Handangabe** aus einem Suchtreffer-Snippet, nicht von der Pipeline erkannt. Vor der Demo-Nennung manuell prüfen. Eine automatische Regel (Investor-Post -> `funding_meldung`) wäre ein eigener Scorer-Schritt.
4. **Ymolution-Gründungsdatum** kommt nur über die Best-Find-Zeitleiste. Damit das Scoring es nutzt, müsste der Kontext-Schritt die Pressemitteilung (PDF) als Quelle lesen.
5. **Cockpit-Texte sind teils englisch** (Ivens Original). Die Seitennamen sind übersetzt, der Rest nicht.
6. **`docs/COCKPIT.md`** nennt noch „`sourcing.engine.search` ist nicht implementiert“. Das ist überholt, denn der Förderkatalog-Provider ist Standard.
7. **Analystenentscheidungen** liegen lokal in `data/screening.sqlite3` (gitignored), ohne Nutzerverwaltung.
