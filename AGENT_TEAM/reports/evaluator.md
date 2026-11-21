# Evaluator (T3): Backtest, Precision@k, Best Find

Stand 21.11.2026, Branch `agents/data-quality-fixes`. Neu angelegt wurde nur `AGENT_TEAM/eval/` (plus Scratch unter
`AGENT_TEAM/reports/scratch/eval/`). `sourcing/`, `context/` und `scoring/` werden importiert, aber nicht geändert.
Netzabrufe (Förderkatalog, Wayback-CDX, OpenAlex) gingen über `.cache/context.db`. Ein zweiter Lauf mit
`--offline` liefert dasselbe Ergebnis.

## Headline-Zahlen für den Pitch

Nach dem Faktencheck (`AGENT_TEAM/reports/fact_check.md`) überarbeitet: Bei der Backtest-Headline zählen nur noch
Daten mit Konfidenz „hoch“. Fünf Labels sind korrigiert. Beim Best Find ist InhalPlus gestrichen (finanziert),
Versatile Robotics steht mit offener Prüffrage, neu empfohlen ist Ymolution, Alternative ist SECARA.

> **So sind die Precision-Zahlen zu lesen (Final Gate, m5)**
> - **Basis:** Alle P@k- und Spearman-Werte beruhen auf **30 unbestätigten Agent-Labels** (10 talk / 19 maybe /
>   1 no, `quelle_label=agent_vorschlag`). Mit `--nur-bestaetigt` gibt es noch keine Zahl.
> - **Abdeckung immer mitnennen:** Gezählt werden nur gelabelte Leads in den Top k.
>   - „P@10 67 %“ im Gate-Endstand heißt 4 von 6 gelabelten Leads; 4 der Top 10 sind ungelabelt (BotFellows,
>     SideroGaIn, SpinMagIC, Metubiq).
>   - „P@30 47 %“ bezieht sich auf 50 % Abdeckung.
> - **Zirkularität:** Die Labels entstanden aus Websuche, und der Score belohnt ebenfalls Web-Präsenz.
>   - Gelabelte Leads mit Website sind öfter „talk“: Gate-Endstand 6/10, ohne Website 4/20; mein Online-Lauf 5/9
>     gegenüber 5/21.
>   - Der Gate-Spearman von 0,41 misst also teils die Übereinstimmung beim öffentlichen Fußabdruck, nicht die
>     Investmentqualität.
>   - Belastbar wird er erst mit Labels, die das Team unabhängig vom Web-Fußabdruck bestätigt.
> - **Backtest:** Der Earliness-Backtest (11/11, Median 21 Monate) hängt nicht von den Labels ab. Er ist eine
>   Handauswahl mit Survivorship- und Namensbias (siehe unten).

1. **Earliness:** **11/11 früh erkannt, Median 21 Monate** (Spanne 8–40) zwischen EXIST-Projektbeginn im
   Förderkatalog und erster öffentlicher Finanzierungsmeldung bzw. erster archivierter Crunchbase-/Dealroom-Seite.
   **n=11 ist eine Handauswahl bekannter Ausgründungen**, 4 davon im HTGF-Portfolio. Nicht in der Headline, aber in
   `backtest.json` aufgeführt: OroraTech (nur Aggregator-Datum, 4,1 Monate) und FMC (frühere HTGF-Runde ohne Datum).
   - Sensitivität: Mit allen 13 bleibt der Median bei 20,9 Monaten.
   - Nach Programm: EXIST-Forschungstransfer (03EF, n=5) Median **32 Monate**, Gründungsstipendium (03EG, n=6)
     Median **17 Monate**.
   - Nur gegen die erste archivierte Profilseite gerechnet (n=6 Headline-Firmen mit Treffer): Median 46 Monate. Diese Zahl nicht als Headline nutzen, weil Wayback spät und lückenhaft archiviert.
   - Zusätzlicher Live-Beleg aus der Shortlist: InhalPlus, EXIST-Start 01.12.2024, erste Finanzierung (NBank Capital)
     16.10.2026, also rund 22 Monate.
2. **Precision@k:** Die Harness steht, Labels für die 30 höchstpriorisierten Leads liegen als Agent-Vorschlag vor
   (10 talk, 19 maybe, 1 no). Mit diesen Vorschlägen:
   - Fundliste Top 30 nach Priorität: **P@30 = 33 % talk, 97 % talk+maybe, 3 % Noise**.
   - Score-Baseline (HEAD fda6207, offline/`--light`): alle 30 bei 53,7, über alle 733 Leads 6 verschiedene Werte.
     Die Rangkorrelation ist **nicht definiert**.
   - WIP-Scoring des `scorer` (neu gerechnet 21.11. abends, gleiche Dossiers): 96 verschiedene Werte, **Spearman
     0,01** (talk Ø 59,0 vs. maybe Ø 59,1). Der Score trennt die Anrufkandidaten nicht von den übrigen. Das
     Algo-Top-30 deckt nur 17 % der Labels ab (P@30 talk 20 % auf 5 gelabelten Leads). Die 25 ungelabelten Leads
     des Algo-Top-30 stehen in der Vorlage, s. u.
3. **Best Find:** Empfehlung **Ymolution** (Unimedizin Greifswald als Gesellschafterin, GmbH seit 08.01.2026, EXIST
   beendet 06/2026, nur öffentliche Mittel, sucht laut eigener Website Investoren für 2026). Alternative **SECARA**
   (RWTH, GmbH HRB 29119, MoU mit Envalior 08/2026, nur Zuschüsse gefunden). **Versatile Robotics** nur mit offener
   Prüffrage, denn 1,25 Mio. EUR Pre-Seed sind laut Snippet möglich, aber unbelegt. **InhalPlus gestrichen** (NBank
   Capital 500 Tsd. EUR am 16.10.2026). Formulierung überall: „kein archiviertes Profil in Wayback“ statt „nicht in
   Crunchbase/Dealroom“. Zeitleisten mit URLs: `AGENT_TEAM/eval/best_find.md`.

## Was gebaut wurde

| Datei | Zweck |
|---|---|
| `AGENT_TEAM/eval/reference_companies.json` | 13 handrecherchierte Ausgründungen: FKZ, erste Finanzierungsmeldung mit URL und Datum, HTGF-Beleg, Konfidenz |
| `AGENT_TEAM/eval/backtest.py` | Holt alle 3.383 EXIST-Vorhaben seit 2014 (`sourcing.foekat_export.export_rows`, vollständig) und prüft FKZ und Name. Bildet die Priorität mit `sourcing.mapping.map_project` nach, prüft DB-Profile mit `context.wayback.web_history_lookup` und rechnet den Vorsprung aus. Aufruf: `.venv/bin/python AGENT_TEAM/eval/backtest.py [--offline]` |
| `AGENT_TEAM/eval/backtest.json` | Ergebnis mit `headline`, `summary`, `bias` und Einzelwerten je Firma inkl. URLs |
| `AGENT_TEAM/eval/precision.py` | Liest `scores.json` (Format `python -m scoring`, robust gegen neue Felder) und `labels.csv`. Gibt P@10/@30 (strict = talk, lenient = talk+maybe), Noise-Anteil, Abdeckung, erwartete Werte bei zufälligem Tie-Break, Spearman (Score vs. talk=2/maybe=1/no=0) und Score je Label-Klasse aus. Optionen `--nur-bestaetigt`, `--json`, `--vorlage` |
| `AGENT_TEAM/eval/labels.csv` | 30 Label-Vorschläge (`quelle_label=agent_vorschlag`), jeweils mit Begründung und Quell-URL |
| `AGENT_TEAM/eval/test_precision.py` | 10 Offline-Tests: `.venv/bin/python -m pytest -q AGENT_TEAM/eval/test_precision.py` (alle grün) |
| `AGENT_TEAM/eval/best_find.md` | 3 Kandidaten plus 3 Ersatzkandidaten mit Signal-Zeitleiste |
| `AGENT_TEAM/reports/scratch/eval/` | Export aller EXIST-Vorhaben seit 2014, Dossiers und Scores (Top 30 und alle 733, jeweils Baseline und WIP), `precision_all_*.json`, `labels_todo_algo_top30_wip.csv` |

Die Harness läuft auf neuen Scores:

```bash
.venv/bin/python -m context examples/sourcing/shortlist.json d.json --offline --light
.venv/bin/python -m scoring d.json --out s --stichtag 2026-11-21
.venv/bin/python AGENT_TEAM/eval/precision.py s/scores.json --json p.json --vorlage todo.csv
```

Die Baseline-Scores stammen aus einer sauberen Kopie von HEAD im Scratchpad, weil `scoring/engine.py` parallel
bearbeitet wird. Ein Lauf des WIP-Scorings auf WIP-Dossiers brach einmal mit `AttributeError` für alle Leads ab;
beim nächsten Lauf war der Fehler weg (vermutlich ein halb gespeicherter Stand). Die WIP-Zahlen oben sind deshalb
eine Momentaufnahme.

## Datenlage und Bias (auch in `backtest.json -> bias`)

- **Survivorship:** In der Referenzliste stehen nur Firmen, die später Geld eingesammelt haben. Der Backtest zeigt,
  dass das Signal bei Gewinnern früh kommt. Er sagt nicht, wie viele EXIST-Projekte Gewinner werden; das misst
  `precision.py`.
- **Namensbias:** Aufgenommen wurden nur Firmen, deren Name im EXIST-Thema steht. „11/11“ ist deshalb nach oben
  verzerrt; anders benannte Vorhaben findet der Backtest gar nicht. Ohne Website-Match (T1) deckt die Pipeline
  genau diesen Fall ab.
- **Katalog-Verzögerung:** Als Signaldatum zählt der Projektbeginn. Wann ein Eintrag öffentlich sichtbar wurde,
  ist nicht archiviert. Der Vorsprung ist um diese Verzögerung (geschätzt Wochen bis Monate) zu hoch.
- **Nur Konfidenz „hoch“ zählt:** In der Headline stehen nur Firmen, deren Finanzierungsdatum eine Primärquelle hat.
  OroraTech (nur Aggregator, 01/2019; die Firmen-PM ist von 05/2020) und FMC (frühere HTGF-Seed-Runde ohne Datum)
  stehen in `backtest.json`, zählen aber nicht. Mit beiden bliebe der Median unverändert bei 20,9 Monaten (Sensitivität in
  `summary.sensitivity_all_detected`).
- **Stichprobe:** n=11 (Handauswahl), Schwerpunkt TUM/München (Pressedichte), nur Deep Tech/HealthTech/AI. Der Plan nennt
  „idw-Ausgründungsmeldungen 2023/24“; idw liefert aber kaum Finanzierungsdaten. Drei Fälle aus dieser Zeit sind
  enthalten (GEMESYS, QuantumDiamonds, RYVER.AI), eine systematische idw-Stichprobe fehlt.
- **Priorisierung:** Das Signal ist früh, unsere heutige Priorität hätte aber 7 der 13 Referenzfirmen (alle 03EG) nur mit 20–30
  eingestuft, also außerhalb der Top 140. Für Gründungsstipendien ist die Priorität zu niedrig. Das ist ein Befund für
  `sourcing/mapping.py` bzw. das Scoring, ich habe dort nichts geändert.
- **Labels:** Alle 30 sind Agent-Vorschläge aus Websuche, also Belegen, nicht aus Gesprächen. Von den 19 „maybe“
  heißen 11 „kein öffentlicher Beleg außer dem Katalog“ (nicht „schlecht“), einer hat eine unsichere Zuordnung
  (SIMBA). Bei 6 ist das Projekt belegt, aber Markt, Differenzierung oder Phase sind offen (u. a. Iso-Flux =
  GaiaIsotopic). Aiina/Sitegeist steht als „maybe“, weil die Firma schon finanziert ist. Nach dem Faktencheck
  korrigiert: Aiina talk→maybe, Iso-Flux mit GaiaIsotopic belegt, Sorala nur als geplante Ausgründung (Firma und CEO
  unbelegt), SIMBA-FKZ unbestätigt, SECARA mit GmbH und Envalior-MoU belegt. Das einzige „no“ (M-Shunt, Einzelbauteil) ist ein
  Urteil.

## Was das Team noch von Hand tun muss

1. **Labels bestätigen:** `AGENT_TEAM/eval/labels.csv` durchgehen, je Zeile `quelle_label` auf `team` setzen bzw. das
   Label ändern. Danach `precision.py … --nur-bestaetigt`. Wichtig sind die Leads mit Namensänderung oder
   unsicherer Zuordnung: Aiina→Sitegeist, SoreAlert→Sorala (geplant), SpaceMast→Adpera, SIMBA↔simfacture?, KM,
   EXIST_P2P.
2. **Algo-Top-30 labeln:** `AGENT_TEAM/reports/scratch/eval/labels_todo_algo_top30_wip.csv` (25 Leads, die das
   WIP-Scoring nach oben stellt) ausfüllen und an `labels.csv` anhängen. Nach dem finalen Scoring-Stand die Vorlage
   mit `--vorlage` neu erzeugen. Erst dann ist P@30 des Algorithmus belastbar (heute 17 % Abdeckung).
3. **Best Find prüfen:** Ymolution und SECARA kurz anrufen bzw. anschreiben: Gibt es schon eine Beteiligung? Wie
   viel hält die Unimedizin an Ymolution? Wann wurde SECARA eingetragen? Bei Versatile Robotics die Pre-Seed-Frage
   klären (1,25 Mio. EUR laut Snippet). Crunchbase/Dealroom/PitchBook/nordic9/Tracxn von Hand durchsuchen (der
   Wayback-Check findet nicht alles, siehe InhalPlus).
4. **Backtest erweitern (optional):** weitere Firmen in `reference_companies.json` eintragen (FKZ, Finanzierungsmeldung
   mit URL), am besten aus einer festen Liste wie „alle HTGF-Seed-Meldungen 2023 mit EXIST-Herkunft“, damit die
   Auswahl nachvollziehbar ist. Danach `backtest.py` neu laufen lassen.
5. **Pitch-Formulierung:** „Bei 11 handverlesenen, belegten Ausgründungen, darunter 4 HTGF-Portfoliofirmen,
   stand das Team im Median 21 Monate vor der ersten Finanzierungsmeldung im Förderkatalog; bei
   EXIST-Forschungstransfer 32 Monate. Survivorship- und Namensbias nennen wir offen.“
