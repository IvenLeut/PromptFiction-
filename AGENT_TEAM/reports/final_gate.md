# Final Gate (`final-gate`), Stand 21.11.2026

Branch `agents/data-quality-fixes`, Basis fda6207, nichts committet. Produktcode habe ich nicht angefasst.
Gemessen wurde der Endstand nach der letzten scorer-Runde: Suite 787 passed, ein Scoring-Kontrolllauf nach dem
Hinweis des Leads war byte-identisch.

## Urteil

**GATE BESTANDEN, mit Auflagen.** Die Branch darf committet und als eigene Branch gepusht werden, wenn beim Commit
die Hygiene-Auflage H1 eingehalten wird. Diese Auflage betrifft nur die Commit-Prozedur, nicht den Code.

**Nicht freigegeben sind** ein Merge in `chore/repo-cleanup` und der Einsatz der Online-Top-10 in der Demo, solange
M1–M3 offen sind. Die Branch ist gegenüber fda6207 klar besser. Keiner der Befunde ist eine Regression; M1 ist ein
alter Fehler, den erst die neuen Website-Texte sichtbar machen.

## 1. Frischmessung

Alles liegt in `AGENT_TEAM/reports/scratch/gate/`. Die Duplikate aus dem Determinismus-Lauf habe ich danach gelöscht,
um Platz zu sparen.

| Prüfung | Ergebnis |
|---|---|
| `pytest -q` (ganze Suite) | **787 passed** (zweimal, 10 s), `AGENT_TEAM/eval/test_precision.py` 10 passed |
| Online-Kontext, 52 Leads (`context input.json gate/dossiers.json --limit 52`) | Exit 0, 5 s, komplett aus dem Cache. Gegenprobe mit gelöschten `website_match:v9`-Einträgen: Die Seiten wurden neu bewertet und die Dossiers sind bis auf `retrieved_at` identisch. Der Matcher ist also unabhängig vom Cache-Stand deterministisch |
| Scoring `--stichtag 2026-11-21`, zweimal | byte-identisch (json, csv) |
| Schema (Draft 2020-12, Array) | 0 Fehler online (52) und offline (733) |
| Evidence ohne URL und ohne Neutral-/Sourcing-Kennzeichnung | 0 |
| Längenlimits VP/Produkt/Hypothese | max. 200 / 298 / 400 |
| Offline 733 (`--offline --light`), zweimal | byte-identisch; 47,1 / 54,1 / 58,2 (min/Median/max), 89 verschiedene Werte, Confidence-Median 0,35, 733× `pre_gruendung`, 733× `vc_potenzial` |
| `pipeline.run_pipeline(SearchCriteria(...), use_mock=True)` | läuft (HealthTech: demo, 30/30) |
| Streamlit | `dashboard`, `deep_dive`, `market_view`, `charts`, `ui_theme`, `pipeline` lassen sich importieren. `app.py` ist ein Skript und läuft nur unter Streamlit; mit `streamlit.testing.AppTest` läuft es ohne Exception |

**Online, 52 Leads** (`precision.py`, `coverage.py`; 30 Labels, alle `agent_vorschlag`, keines bestätigt):

| Kennzahl | evaluator_online (vor Kalibrierung) | **Gate (Endstand)** |
|---|---|---|
| verschiedene Gesamtscores, Spanne, Std.-Abw. | 39; 54,1–67,9; 2,88 | **41; 53,4–69,2; 3,62** |
| Spearman(Score, Label) | 0,14 | **0,41** |
| P@10 talk (Abdeckung) | 40 % (50 %) | **67 % (60 %)**, also 4 von 6 gelabelten |
| P@30 talk / talk+maybe / Noise (Abdeckung) | 35 / 95 / 5 % (67 %) | **47 / 93 / 7 % (50 %)** |
| Website / Gründername / Papers belegt | 34,6 / 0 / 0 % | **38,5 / 30,8 / 26,9 %** |
| Stage | 37 pre_gründung, 8 pre_seed, 6 seed, 1 i.G. | 35 / 16 pre_seed / 0 seed / 1 i.G. |
| Noise ≠ vc_potenzial | 0 | 0 |

**Wie belastbar die Spearman-Zahl ist** (eigene Rechnung):
- Die neuen Achsgewichte bringen fast nichts. Mit den alten Gewichten 0,35/0,35/0,30 ergeben dieselben
  Endstand-Scores 0,407 statt 0,417. Der Zugewinn kommt also aus den Daten (Website, Impressum, OpenAlex), nicht aus
  einer Überanpassung der Achsen.
- Es gibt aber eine **Zirkularität**. Die Agent-Labels entstanden aus Websuche. Gelabelte Leads mit Website sind zu
  6/10 talk, ohne Website zu 4/20. Der Score belohnt Web-Präsenz, und die Labels belohnen sie ebenfalls.
- Fazit: 0,41 misst teils die Übereinstimmung des öffentlichen Fußabdrucks, nicht die Investmentqualität. Ob sich die
  Gewichte innerhalb der Achsen (timing, datenlage, skalierbarkeit) überangepasst haben, lässt sich ohne bestätigte
  Labels nicht prüfen.

## 2. Online-Top-10 im Detail

| # | Lead | Score | Stage | Website | Gründer (Score-Datei) | Label |
|---|---|---|---|---|---|---|
| 1 | BotFellows (Fraunhofer IWU) | 69,2 | pre_seed | botfellows.com | Bdiwi; Eichler; Krusche | – |
| 2 | DyNAtrix (Leibniz-IPF) | 68,0 | pre_gründung | dynamicmatrices.eu | Elisha Krieg | talk |
| 3 | iNSyT (LMU Physik) | 67,1 | pre_seed | insyt.solutions | Gruber; Englert | maybe |
| 4 | SideroGaIn (HZDR/HIF) | 64,8 | pre_seed | – | – | – |
| 5 | SpinMagIC (Uni Stuttgart) | 64,5 | pre_gründung | spinmagic.eu | – | – |
| 6 | **Ymolution** (Unimedizin Greifswald) | 64,5 | pre_seed | ymolution.com | Alexander Reder (nur einer) | talk |
| 7 | SIMBA (TU Dresden) | 63,4 | pre_gründung | – | – | maybe |
| 8 | Metubiq (Uni Kassel) | 62,9 | in_gründung | metubiq.de | Stelter; Serbes | – |
| 9 | SA-Dynamics (RWTH ITA) | 62,9 | pre_seed | sa-dynamics.com | 4 GF | talk |
| 10 | AutonomIQ (TU Darmstadt PTW) | 62,5 | pre_seed | autonomiq.de | Sarikaya; Hoffmann | talk |

Knapp dahinter: VersatileRobotics auf 11 (62,2) und **SECARA auf 14** (61,0).

**Würde ein HTGF-Partner anrufen? Bei den Firmen ja, bei den Datensätzen noch nicht.**
- Die Auswahl stimmt. Fast alles sind echte Deep-Tech-Ausgründungen mit GmbH oder i.G. und benannten Personen, ohne
  VC-Runde. Kein Agentur- oder Hobby-Treffer.
- Der Text pro Lead taugt aber nicht zum Weiterreichen:
  - **49 von 52 Value Propositions lauten „Problem und Nutzen noch nicht belegt“**, auch wenn die Website es
    erklärt. Ymolution schreibt etwa: „70 % der kommerziellen Antikörper funktionieren nicht …, tierfreie
    Nano-Antikörper, Plattform validiert“.
  - Drei Hypothesen beginnen mit Müll-Partnern (M1).
  - `why_now` behauptet „in Crunchbase/Dealroom nicht gefunden“, und das stimmt für 2 von 3 Stichproben nicht (M3).

**Stichproben im Netz** (Brave API, 5 Anfragen):

| Lead | Befund | Urteil |
|---|---|---|
| BotFellows | GmbH, HRB 36822 AG Chemnitz, GF Bdiwi/Eichler/Krusche (deckt sich mit der Score-Datei, northdata). EXIST-FT 07/2024. Tracxn: „has not raised any funding“. **Dealroom- und Tracxn-Profil vorhanden** | Anrufkandidat. „Nicht in Dealroom“ ist falsch. Der Rang-1-Score stützt sich auf den Müll-Partner „Global Partners (kunde)“ (+4,4 Punkte); ohne ihn läge BotFellows bei etwa 64,8 und damit trotzdem in den Top 5 |
| iNSyT | **EIC Transition, 2,42 Mio. EUR** (06/2026, LMU + Team). PitchBook- und Tracxn-Profil, ohne VC-Runde | starker Anrufkandidat (das Label „maybe“ wirkt zu niedrig). „Nicht in DBs“ ist falsch |
| Metubiq | GmbH i.Gr. c/o Uni Kassel, patentierte Schwingungskompensation für Inline-Weißlichtinterferometrie, Aussteller auf Sensor+Test und preXcon 2026, Innovationspreis Göttingen | Anrufkandidat. Stage `in_gruendung` ist korrekt |

**Best Find:**
- **Ymolution** steht online auf Rang 6 von 52, offline auf 297 von 733 (14-fach gleichauf). Weiterhin nur öffentliche
  Mittel: Neu ist eine Landesförderung über rund 1,34 Mio. EUR von Ende Oktober 2026 (tagesschau/NDR, „vor 3 Wochen“;
  in `best_find.md` steht dazu noch „o. D.“). Kein VC-Treffer.
- **SECARA** steht online auf 14, offline auf 6. Auch hier kein VC-Treffer.
- **Versatile Robotics** steht online auf 11, offline auf 65. Die Finanzierungsfrage ist weiter offen.
- **Pitchfähig ist Ymolution, aber nur mit der handgepflegten Zeitleiste aus `best_find.md`.** Die automatisch
  erzeugte Karte zeigt eine Platzhalter-VP, nur einen der beiden GF und „Nächster Meilenstein: wiederholbarer
  Vertrieb“ bei einer Firma ohne Umsatz.
- Die Ränge in `best_find.md` (171/16/219) sind veraltet.

## 3. Jurykriterien und Definition of Done

| Kriterium | Urteil | Beleg |
|---|---|---|
| Lead Quality | **teilweise** | Top 10 sind echte, unfinanzierte Ausgründungen; 3/3 Stichproben anrufwürdig. Aber: VP-Platzhalter bei 49/52, Müll-Partner bei 3 der Top 7 (M1), falsche DB-Aussage (M3). Noise-Filter greift nie (0 von 52 online + 733 offline), weil in Top 52 keine Agentur ist; nicht widerlegt, aber auch nicht vorgeführt |
| Earliness | **teilweise** | Backtest 11/11, Median 21 Monate (n=11, Handauswahl, offen benannt). `in_databases` prüft nur Wayback-Snapshots von Crunchbase/Dealroom-Slugs; BotFellows und iNSyT haben Dealroom/Tracxn/PitchBook-Profile, das System sagt `false` |
| Creativity of Signals | **erfüllt** | Förderkatalog-FKZ als Frühsignal, Projektname → Website über Hochschul-Verlinkung, Impressum-GF → OpenAlex, FKZ auf der Website als Namensvetter-Beleg |
| Technical Execution | **erfüllt (Pipeline) / teilweise (Demo-Inhalt)** | 787 Tests, deterministisch, schema-valide, Dashboard und Mock-Pipeline laufen. Online-Anreicherung lief aber nur auf 52 Leads; der Best Find steht offline auf Rang 297 von 733, die Engine „findet“ ihn also nur im Online-Teillauf |
| Scalability | **teilweise** | Cache-first, Circuit Breaker, Brave API mit ca. 1–2 Requests/Lead. Ein Volllauf über 733 Leads braucht etwa 1.300 von ca. 2.000 Monatsanfragen; rund 110 sind verbraucht. Machbar, aber nur einmal im Monat im Gratistarif |
| DoD: csv/json/schema, 100 % valide | erfüllt | 0 Schemafehler (52, 733, beide Beispielordner) |
| DoD: 3 Achsen + Gesamt 0–100, Richtung dokumentiert | erfüllt | `scoring/SCORING.md` |
| DoD: jeder Teilwert mit URL oder „neutral“ | erfüllt | 0 Treffer ohne Kennzeichnung |
| DoD: 3 Testfälle, Stage passt | erfüllt | `examples/scoring` (Dummy Software/Deep Tech/Life Sciences), kiutra `zu_spaet` |
| DoD: zweiter Lauf identisch | erfüllt | Online und offline byte-identisch |
| DoD: SCORING.md | erfüllt | aktuell (0,40/0,25/0,35 mit Begründung) |
| Output-Vertrag Gewichte | **Abweichung** | Der Vertrag (`goal/SKILL.md` Abschnitt B, „nicht ändern ohne Rücksprache“) nennt 0,35/0,35/0,30, die Config 0,40/0,25/0,35. Zwar Config statt hart codiert, aber Rücksprache nötig (H2) |

## 4. Befunde

### BLOCKER (nur für den Commit-Vorgang)

**H1 – Commit-Hygiene.**
- `.venv` ist ein Symlink. `.gitignore:9` (`.venv/`) greift nicht für Symlinks; `git check-ignore .venv` meldet
  „nicht ignoriert“. Ein `git add -A` würde einen Symlink auf `/Users/finnlipek/...` committen.
- `.claude/skills/` (Brave-Skills, 128 KB, lokal) ist ebenfalls unversioniert.
- `AGENT_TEAM/reports/scratch/` ist rund 170 MB groß: viele 14-MB-Dossiers und 6,6-MB-Score-Kopien, dazu echte
  Impressum-Namen.
- **Fix beim Commit (main):** gezielt adden: Code, Tests, Fixtures, `examples/`, `AGENT_TEAM/README.md`,
  `AGENT_TEAM/eval/`, `AGENT_TEAM/reports/*.md` und `matcher_live.json`. Nicht adden: `.venv`, `.claude/`,
  `AGENT_TEAM/reports/scratch/`. Optional `.venv` (ohne Slash) und `AGENT_TEAM/reports/scratch/` in `.gitignore`
  eintragen.

### MAJOR

**M1 – Müll-Partner treiben `traktion`, und die Hypothese übernimmt sie.** Fix: matcher (context/), scorer
(Absicherung).
- **Ausmaß:** 3 der 4 belegten Traktionswerte im Online-Lauf sind falsch, alle in den Top 7. Die Traktion hat das
  höchste Gewicht der Marktachse (0,35).
- **Fälle:**
  - BotFellows: „Trusted by Global Partners“ wird zum Kunden „Global Partners“ (100 Punkte).
  - SpinMagIC: Der EXIST-Förderhinweis („together with the Federal Ministry for Economic Affairs and Climate
    Protection“) ergibt zwei „design_partner“ (80 Punkte).
  - SIMBA: „Fraunhofer-Institut für Software- und Systemtechnik ISST“ wird an „und“ zerschnitten, und
    „Systemtechnik ISST“ gilt als design_partner (80 Punkte).
- **Ursache:** `context/classify.py:199` (Cue `trusted by` ohne Plausibilitätsprüfung der Organisation),
  `:201-202` und `:501-502` (`_collab` → `design_partner`, wenn kein Forschungswort im Fragment steht), `:189`
  (ORG_SPAN trennt an „und/and“, auch innerhalb eines Institutsnamens). Der Fehler ist alt; sichtbar wird er
  erst durch `website_text`.
- **Fix:**
  - context: Fördergeber (Ministerium, Federal Ministry, EU, ESF, BMWK/BMWE, EXIST, Projektträger) und generische
    Wörter (Partners, Customers, Brands) verwerfen; nicht an „und“ trennen, wenn das linke Fragment auf „für“ +
    Substantiv endet.
  - scorer (`scoring/engine.py:510-517`): `traktion` nur bei Partnern mit Rechtsform oder bekannter Organisation
    werten, sonst nur als Proxy.
- **Reproduktion:** Partnerliste in `gate/dossiers.json` bzw. `kriterium=traktion` in `gate/sc/scores.json`.

**M2 – Value Proposition bleibt Platzhalter, obwohl Website-Text vorliegt.** Fix: scorer.
- `scoring/engine.py:992-999` baut die VP bei Katalog-Leads nur aus dem Förderkatalog, und
  `_produktbeschreibung` (`:974-989`) genauso. `website_text` (bei 20 Leads vorhanden) wird ignoriert.
- 49/52 online und 686/733 offline enden auf „noch nicht belegt“.
- **Fix:** Liegt `website_text` oder eine Meta-Beschreibung von der gematchten Website vor, die ersten 1–2
  inhaltlichen Sätze mit URL als VP bzw. Produktbeschreibung nehmen, ohne Navigation, Cookie-Text und
  Förderhinweis.
- **Nebenbefund:** SECARA-VP und -Produktbeschreibung werden mitten im Institutsnamen abgeschnitten
  („Rheinisch-Westfälische Technische…“). Für die Kurzform reicht der Lehrstuhl.

**M3 – Falsche DB-Aussage in `why_now`.** Fix: scorer (Text), matcher (Prüfung).
- `scoring/engine.py:1141` schreibt „in Crunchbase/Dealroom nicht gefunden“, sobald `in_databases_quelle`
  gesetzt ist. Die Prüfung (`context/wayback.py`) fragt aber nur Wayback-Snapshots einzelner Slugs ab.
- Belegt falsch für BotFellows (Dealroom, Tracxn) und iNSyT (PitchBook, Tracxn). Den gleichen Befund hatte der
  Faktencheck schon für InhalPlus (nordic9, VCBacked).
- **Fix:** Formulierung wie in `best_find.md`: „kein archiviertes Crunchbase-/Dealroom-Profil (Wayback)“.
  Optional die Brave API als zweite Quelle nutzen: `site:dealroom.co OR site:tracxn.com "<Firma>"`, 1 Request je
  Top-50-Lead.
- Das ist die Earliness-Kernaussage im Pitch. Ein Juror, der Dealroom öffnet, widerlegt sie sofort.

**M4 – Best Find nur im 52er-Teillauf sichtbar.** Fix: Mensch/main entscheidet, ein Agent führt aus.
- Offline steht Ymolution auf Rang 297 von 733, gleichauf mit 13 anderen. Für die Demo-Aussage „die Engine findet
  Ymolution“ braucht es einen Online-Lauf über die Longlist oder mindestens die Top 200 nach Priorität. Bei
  ungefähr 1–2 Brave-Requests je Lead ist das ein bewusster Quota-Einsatz.

### MINOR

- **m1 – Ymolution: zweiter GF fehlt.** Fix: matcher.
  - Das Impressum-Modul hat die englische Startseite statt `/impressum` geparst. „Managing Directors Dr. Alexander
    Reder and Dr. Christian Hentschker“ ergibt nur Reder.
  - Ursache: `context/imprint.py:334` (`_directors` trennt nicht an „and/und“) und die Seitenwahl („first page with
    imprint markers“, `:5`).
  - Gerade beim Best Find fällt das auf.
- **m2 – DyNAtrix: Rechtsform des Gastinstituts.** Fix: matcher, `context/imprint.py:248`.
  - `legal_form = e.V.` stammt aus „c/o Leibniz-Institut für Polymerforschung Dresden e.V.“.
  - Elisha Krieg steht dort als „Project Leader“, im Dossier aber als `Geschäftsführung (Impressum)`.
  - Die Stage ist nicht betroffen (bleibt pre_gründung).
  - Fix: Rechtsform bei „c/o“ und Hochschul- oder Institutsnamen ignorieren; Rolle aus „Represented by: … (Project
    Leader)“ übernehmen.
- **m3 – Widersprüchliche Team-Evidence.** Fix: scorer.
  - Bei Ymolution, VersatileRobotics und DyNAtrix steht in `name_gruender` ein Name, die komplementaer-Evidence
    sagt aber „Gründer noch nicht namentlich belegt“.
  - Außerdem steht „Nächster Meilenstein: wiederholbarer Vertrieb“ bei Firmen ohne Umsatzbeleg, und es heißt
    „1 belegte Partner“ (Grammatik).
- **m4 – `best_find.md` veraltet.** Fix: evaluator.
  - Score-Ränge 171/16/219 durch die aktuellen Werte ersetzen (online 6/14/11 von 52, offline 297/6/65 von 733).
  - Tagesschau-Förderung datieren (Ende 10/2026, 1,34 Mio. EUR Land).
- **m5 – Headline-Zahlen ehrlich angeben.** Fix: evaluator.
  - „P@10 67 %“ heißt 4 von 6 gelabelten Leads; vier Top-10-Leads sind ungelabelt (BotFellows, SideroGaIn,
    SpinMagIC, Metubiq).
  - Spearman 0,41 nur mit dem Zirkularitätshinweis (Abschnitt 1) und mit „30 unbestätigte Agent-Labels“ nennen.
- **m6 – `coverage.py --ids` passt nicht auf das lead_id-Format.** Fix: evaluator.
  - Das Präfix `foekat-` wird nicht ergänzt, `picks` bleibt deshalb leer.
- **m7 – SpinMagIC ohne Gründer, obwohl die Website „Founded by:“ enthält.** Fix: matcher, optional.
  - Pulse-of-Production ist eine GmbH, aber ohne GF.

## 5. Wer was tun kann

**Agents:**

| Befund | Agent |
|---|---|
| M1 (context-Teil), M3-Prüfung, m1, m2, m7 | matcher |
| M1-Absicherung, M2, M3-Text, m3 | scorer |
| m4, m5, m6 | evaluator |
| H1 beim Commit | main |

Danach dieses Gate mit denselben Befehlen wiederholen; die Befehle stehen oben, die Eingabe ist
`AGENT_TEAM/reports/scratch/eval/online/input.json`.

**Nur das menschliche Team:**
1. **Labels bestätigen** (`AGENT_TEAM/eval/labels.csv` → `quelle_label=team`). Die 4 ungelabelten Top-10-Leads
   labeln. iNSyT von „maybe“ prüfen (EIC Transition 2,42 Mio.). Dann `precision.py --nur-bestaetigt`. Erst danach
   sind die Gewichte innerhalb der Achsen kalibriert statt plausibel.
2. **Gewichte 0,40/0,25/0,35 freigeben oder zurücknehmen** (Output-Vertrag, Matrix-Team). Messbar bringt der Wechsel
   kaum etwas (0,407 → 0,417).
3. **Best Find von Hand prüfen:** Ymolution (Anteil der Unimedizin, Stand der Investorensuche 2026, Landesförderung
   10/2026), SECARA (HR-Eintragung), Versatile Robotics (Pre-Seed 1,25 Mio. ja/nein). Dazu Crunchbase, Dealroom,
   PitchBook, nordic9 und Tracxn von Hand durchsuchen.
4. **Quota-Entscheid** für einen Online-Lauf über die Longlist (M4).
5. **Merge-Entscheidung** und Abstimmung zu `models.py` (`EnrichedLead.matched_website`, optional, am Modellende,
   rückwärtskompatibel) mit den Besitzern von `pipeline.py` und dem Dashboard.
6. **Datenschutz:** Scores und Scratch enthalten echte Impressum-Namen (öffentliche Geschäftsdaten). Die Beispiele
   im Repo sind pseudonymisiert. Entscheiden, ob Scores mit Klarnamen ins Repo dürfen; bis dahin Scratch nicht
   committen (H1).

---

# Gate 2 (Wiederholung nach der Fix-Runde), 21.11.2026

Geprüft habe ich `origin/agents/data-quality-fixes` @ ff884ff plus die Fix-Runde im Arbeitsbaum, darunter das neue
`context/dbsearch.py`, die Partner-Filter, die Website-VP und `why_now` nach Prüfart. Produktcode habe ich nicht
angefasst, nichts committet. Rohdaten liegen in `AGENT_TEAM/reports/scratch/gate2/` (Duplikate gelöscht).

## Urteil Gate 2

**GATE BESTANDEN, ohne Auflagen für Agents.**
- Alle Befunde aus Gate 1, die Agents beheben konnten (H1, M1–M3, m1–m6), sind erledigt. m7 war kein Fehler.
- Neu gefunden habe ich drei MINOR (n1–n3). Sie sind optional und blockieren weder einen Push noch eine Demo.
- Offen bleiben nur Entscheidungen des Teams (M4, Labels, Gewichte, Merge, Datenschutz).

## Frischmessung

| Prüfung | Ergebnis |
|---|---|
| Suite, zweimal | **807 passed / 807 passed** (10 s); `AGENT_TEAM/eval` 13 passed |
| Online-Kontext, 52 Leads | Exit 0, aus dem Cache (2 s). Ein zweiter Kontextlauf ist ohne Zeitstempel identisch (0 Diff-Zeilen) |
| Scoring zweimal (online), Offline-733 zweimal | jeweils byte-identisch (json, csv) |
| Schema | 0 Fehler (52, 733, `examples/scoring`, `examples/context/scores`) |
| Evidence ohne URL und ohne Kennzeichnung / Längenlimits | 0 / max. 200 · 296 · 400 |
| Offline 733 | 47,1 / 54,1 / 58,2, 89 verschiedene Werte, 733× `pre_gruendung` (unverändert, offline gibt es keinen Website-Text) |
| Beispiele | kiutra `zu_spaet` 20,0; Siderogain `pre_seed` 71,2 |
| Pipeline / Streamlit | `run_pipeline(use_mock=True)`: demo 30/30. Module importierbar. `AppTest(app.py)`: 0 Exceptions, 0 Fehler |

| Online, 52 Leads | Gate 1 | **Gate 2** |
|---|---|---|
| Spearman (30 unbestätigte Agent-Labels) | 0,41 | **0,42** |
| P@10 talk (Abdeckung) | 67 % (4/6) | **71 % (5/7)** |
| P@30 talk / talk+maybe / Noise | 47 / 93 / 7 % | 47 / 93 / 7 % |
| Website / Gründer / Papers belegt | 38,5 / 30,8 / 26,9 % | 38,5 / **32,7** / **28,8** % |
| `in_databases = true` | 1,9 % | **13,5 %** (7) |
| VP-Platzhalter | 49/52 | **31/52**; alle 20 Website-Leads außer BEHtec (Lorem-ipsum-Seite) haben eine VP aus der Website |
| Belegte Traktion (davon Müll) | 4 (3) | **2 (0)** |
| Spanne Gesamtscore | 53,4–69,2 | 53,4–68,0 (40 verschiedene Werte) |

Zirkularität der Labels (Gate 1, Abschnitt 1) gilt weiter. Die Zahlen sind ein Hinweis, keine Kalibrierung.

**Online-Top-10:**
1. DyNAtrix
2. iNSyT
3. BotFellows (64,9, vorher 69,2 mit Müll-Partner)
4. SideroGaIn
5. **Ymolution** (64,7)
6. Metubiq
7. SA-Dynamics
8. Pulse-of-Production
9. AutonomIQ
10. **Versatile Robotics**

SpinMagIC (11) und SIMBA verlieren ihre Müll-Partner und fallen aus den Top 10. **SECARA steht auf 14.**

## Status der Gate-1-Befunde

| Befund | Status | Beleg |
|---|---|---|
| H1 Commit-Hygiene | **erledigt** | `.gitignore:53` `.venv` (ohne Slash), `git check-ignore` greift. Commit ff884ff enthält weder Scratch noch `.venv`/`.claude` (0 Dateien aus `reports/scratch` versioniert); alle drei stehen als ignoriert (`!!`) |
| M1 Müll-Partner | **erledigt** | „Global Partners“, beide Ministerien und die ISST-Bruchstücke sind weg. SIMBA: „Fraunhofer-Institut für Software- und Systemtechnik ISST“ als Forschungspartner (50, vorher 80). SideroGaIn: Freiberger Compound Materials (pilot, 85) bleibt. Test-Probe: „Siemens und Bosch“, „BASF, Covestro und Evonik“, „Klinikum rechts der Isar und Charité“ werden weiter richtig getrennt (siehe aber n3) |
| M2 VP-Platzhalter | **erledigt** (Qualität siehe n1) | 49 → 31. SECARA wird nicht mehr mitten im Wort gekürzt |
| M3 DB-Aussage | **erledigt** | 0 Aussagen „nicht gefunden“ ohne Prüfart; 45× „… nicht gefunden (Datenbanksuche)“; 6 echte Profiltreffer mit URL, `earliness_delta` bei Treffern ohne Datum leer |
| M4 Best Find nur im Teillauf | **offen (Team)** | Offline steht Ymolution weiter auf 297 von 733. Den Longlist-Lauf muss das Team freigeben (Quota: laut matcher etwa 170 Brave-Anfragen im Monat verbraucht, Gate 2 kam auf 4 dazu) |
| m1 Ymolution, 2. GF | **erledigt** | `name_gruender` = Alexander Reder; Christian Hentschker |
| m2 DyNAtrix e.V. | **erledigt** | `legal_form` leer, Rolle „Project Leader (Impressum)“ |
| m3 Team-Widerspruch, Meilenstein | **erledigt** | „nicht namentlich“ bei vorhandenem Namen: 0; „wiederholbarer Vertrieb“: 0 |
| m4 `best_find.md` | **erledigt** (Rundungsdrift) | Ränge und Datum der Landesförderung (29.10.2026) nachgetragen. Gate-2-Ränge sind Ymolution 5, Versatile 10, SECARA 14 (dort steht 6/11/14) |
| m5 Headline-Zahlen | **erledigt** | Lesehinweise in `evaluator.md` und `evaluator_online.md` |
| m6 `coverage.py --ids` | **erledigt** | IDs ohne `foekat-` werden aufgelöst, `picks` ist gefüllt; neuer `test_coverage.py` |
| m7 SpinMagIC „Founded by“ | **kein Fehler** | Geprüft: Auf „Founded by:“ folgt nur die BMWK-Logozeile („based on a resolution of the German Bundestag“). Nebenbefund Pulse-of-Production: GF Philipp Niemietz jetzt da |

## Stichproben

**DB-Treffer (2 von 6, Brave):**
- **Metubiq → PitchBook 969457-15:** richtig. Titel „Metubiq 2026 Company Profile“, „headquartered in Kassel, Germany“.
- **Rement → Crunchbase `organization/rement`:** richtig. Beschreibung „resource recovery technology for concrete
  waste“, dazu das Crunchbase-Personenprofil von CEO Robert Schleinhege.
- Schon in Gate 1 bestätigt: BotFellows (Tracxn) und iNSyT (PitchBook).
- Laut matcher verworfene Namensvetter: insyt (Social-App), autonomiq (US-Firma), BOTfriends. Ein Fehltreffer ist mir
  nicht begegnet.

**Website-VPs (2 von 20 gegen `website_text`):**
- **Ymolution:** „We develop fully synthetic nano-antibodies (VHH): without a single laboratory animal, with
  unmatched precision and in weeks instead of months.“ Das ist ein wörtlicher Satz von ymolution.com/en und eine
  gute VP.
- **iNSyT:** „Applications – Coatings & thin Layers Get insights in dynamics of objects down to the nanoscale …“. Der
  zweite Teil stimmt, davor steht aber ein **Menüpunkt** der Navigation (n1).

## Neue Befunde (alle MINOR, optional)

**n1 – Website-VP übernimmt teils Navigations- oder CTA-Text bzw. nur den Problemsatz.** Fix: scorer,
`scoring/engine.py` (VP-Extraktion aus `website_text`).
- **Fälle:**
  - iNSyT: Menüpunkt „Applications – Coatings & thin Layers“ vor dem Satz.
  - Metubiq: „… explore our core technology.“ (CTA).
  - MillionMolecules: „It's time to find your answer.“
  - SpinMagIC: nur der Problemsatz „Free radicals are a critical indicator …“; der Nutzen steht erst im übernächsten
    Satz („Our cutting-edge quantum sensor enables precise, real-time monitoring …“).
  - Bei SA-Dynamics und SONOJET fehlt der Punkt zwischen Headline und Unterzeile.
- Werbe- oder Cookie-Text kam nicht vor.
- **Fix-Idee:** Zeilen verwerfen, die im Menüblock mehrfach vorkommen oder mit „Applications –/Home/Contact“
  beginnen. CTA-Verben (explore, discover, find out, contact) abwerten. Einen Satz mit „we/our/unser“ + Verb
  bevorzugen.

**n2 – HydroPURE: positive DB-Aussage mit der URL einer negativen Suche.** Fix: scorer (`evaluation/engine.py`).
- `evaluation/engine.py:233-235` nimmt als `in_databases_quelle` die erste Nicht-Wayback-Evidence `in_databases`.
- Bei HydroPURE ist das die Brave-Suche mit dem Ergebnis „kein Profil“. `in_databases = true` stammt aber aus
  Wayback (crunchbase `organization/hydropure`, 2024-10-01).
- Folge: `why_now` = „bereits mit Datenbankprofil gelistet (search.brave.com)“.
- Die Quellen widersprechen sich, und der Wayback-Slug könnte ein Namensvetter sein; der Matcher hatte
  hydropure.ae schon als Namensvetter verworfen.
- **Fix:** Nur Evidence mit positivem Befund (Profil-URL) als Quelle nehmen. Bei einem Widerspruch zwischen Brave
  (kein Profil) und Wayback (Slug-Profil) einen offenen Punkt „Namensvetter prüfen“ setzen.

**n3 – Partner-Splitter verschmilzt nach „für/of + Substantiv“ zu viel.** Fix: matcher,
`context/classify.py:317-330`.
- `_orgs("Fraunhofer-Institut für Lasertechnik ILT und BMW")` liefert einen einzigen Partner, BMW geht verloren.
- `_orgs("Bank of America and Siemens Energy")` liefert ebenfalls einen.
- **Fix:** Nur zusammenhalten, wenn links eine Wortellipse („Software-“) steht oder rechts kein eigenständiger
  Organisationsname folgt (z. B. ein Kürzel oder eine Rechtsform direkt danach).
- Im aktuellen Lauf ohne Wirkung, weil nur 2 Partner belegt sind.

**Kein Befund:**
- Gründer-Rollen sind plausibel („Geschäftsführung (Impressum)“, DyNAtrix „Project Leader (Impressum)“). Keine
  Müllnamen in `name_gruender`.
- Stage passt in allen Top 10, Metubiq ist richtig `in_gruendung`.
- Ein DB-Profil allein setzt kein `zu_spaet`. Das ist richtig, denn Tracxn nennt BotFellows und iNSyT „unfunded“;
  `why_now` sagt „Vorsprung prüfen“.

## Nur das menschliche Team (unverändert)

1. Labels bestätigen und die ungelabelten Top-10-Leads labeln (BotFellows, SideroGaIn, Metubiq).
2. Gewichte 0,40/0,25/0,35 gegen den Output-Vertrag 0,35/0,35/0,30 freigeben oder zurücknehmen.
3. Best Find von Hand prüfen (Ymolution, SECARA, Versatile-Pre-Seed).
4. Quota für den Online-Lauf über die Longlist freigeben (M4).
5. Merge entscheiden und das Feld `models.py` `matched_website` abstimmen.
6. Klarnamen in den Scores (Datenschutz).
