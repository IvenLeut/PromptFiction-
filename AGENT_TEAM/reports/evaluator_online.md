# Evaluator: Online-Kette nach T1 (Messung)

Stand 21.11.2026, 04:26–04:36 Uhr. Branch `agents/data-quality-fixes`, nichts committet. Keine Änderung an `context/`,
`scoring/` oder `sourcing/`. Neu ist nur `AGENT_TEAM/eval/coverage.py` (Abdeckung und Kriterien-Diagnose).

## Aufbau

- **Eingabe:** `AGENT_TEAM/reports/scratch/eval/online/input.json`, 52 Leads: die Top 50 nach Priorität aus
  `examples/sourcing/shortlist.json` plus SideroGaIn (`03efsn0258`) und `03efbb0063` aus `matcher_live.json`. Alle
  30 Leads aus `labels.csv` sind enthalten.
- **Online-Kontext:**
  `python -m context input.json online/dossiers.json --limit 52` (Matcher mit Brave API, Impressum, OpenAlex,
  Wayback, idw, Förderkatalog; ohne Patents, ohne `--light`/`--offline`). Laufzeit 570 s, also 11 s je Lead, weil
  der Cache aus dem Matcher-Lauf schon warm war. Exit 0, keine Abbrüche.
  - Neue Brave-Anfragen: höchstens wenige, die Matcher-Stichprobe war identisch und kam aus dem Cache.
  - Eine exakte Zahl liefert die CLI nicht.
- **Scoring:** `python -m scoring online/dossiers.json --out online/sc --stichtag 2026-11-21` mit dem aktuellen
  WIP-Stand des `scorer`.
- **Vergleich:** dieselben 52 Leads mit `--offline --light`, danach Scoring nach `online/sc_offline`.
- **Auswertung:** `precision.py` und `coverage.py`. Die JSON-Ergebnisse liegen in `online/precision_*.json` und
  `online/coverage_*.json`.

## 1. Precision@k und Kalibrierung (52 Leads, 30 Agent-Labels: 10 talk / 19 maybe / 1 no)

| | offline/light | **online** |
|---|---|---|
| verschiedene Gesamtscores | 21 | **39** |
| Score-Spanne (Std.-Abw.) | 56,5–62,0 (1,16) | **54,1–67,9 (2,88)** |
| P@10 talk / talk+maybe / Noise (Abdeckung) | 33 % / 100 % / 0 % (60 %) | **40 % / 100 % / 0 % (50 %)** |
| P@30 talk / talk+maybe / Noise (Abdeckung) | 35 % / 100 % / 0 % (57 %) | **35 % / 95 % / 5 % (67 %)** |
| P@10 nur über gelabelte Leads (10 beste gelabelte) | 30 % | **50 %** |
| Basisrate talk (alle 30 Labels) | 33 % | 33 % |
| Spearman(Score, Label) | 0,01 | **0,14** |
| Ø Score talk / maybe / no | 59,0 / 59,1 / 58,3 | 61,1 / 60,1 / 61,5 |

**`--nur-bestaetigt`:** leer. Alle 30 Labels sind noch `agent_vorschlag`; das Team hat keines bestätigt, also gibt
es keine Kennzahl.

**Lesart:**
- Online streut der Score 2,5-mal so stark wie offline, und die Kalibrierung wird positiv (0,01 → 0,14).
- Unter den gelabelten Leads sind die 10 besten zu 50 % talk, die Basisrate liegt bei 33 %. Bei n=30 mit
  ungeprüften Labels ist das ein Hinweis, kein Beweis.
- P@k mit 50–67 % Abdeckung: Von den Top 10 sind 5 nicht gelabelt (BotFellows, SideroGaIn, dentson, Metubiq,
  SpinMagIC). Sie stehen in keinem Label, weil sie außerhalb der Prioritäts-Top-30 liegen.
- Das einzige „no“ (M-Shunt) steht online auf Rang 16 mit 61,5, über dem talk-Schnitt. Grund: Website mit Impressum
  (GmbH), und die Textklassifikation liest „erste_kunden“. Daraus wird `seed` mit niedrigem Risiko. Der Score
  belohnt also Firmenreife, ob der Markt groß genug ist, prüft er nicht.

**Online-Top 10:**

| Rang | Lead | Score | Label |
|---|---|---|---|
| 1 | DyNAtrix | 67,9 | talk |
| 2 | SIMBA | 66,3 | maybe |
| 3 | BotFellows | 66,2 | – |
| 4 | iNSyT | 65,9 | maybe |
| 5 | SideroGaIn | 65,9 | – |
| 6 | dentson | 64,9 | – |
| 7 | Metubiq | 64,8 | – |
| 8 | SpinMagIC | 64,5 | – |
| 9 | **Ymolution** | 63,6 | talk |
| 10 | Pulse-of-Production | 62,6 | maybe |

Fünf der zehn kommen aus Dresden (03EFSN). Das ist der Effekt von `forschungsumfeld`, siehe Abschnitt 3.

## 2. Datenabdeckung (52 Leads)

| Merkmal | offline/light | online |
|---|---|---|
| Website (`website` in scores.json) | 0 % | **34,6 %** (18, alle vom Matcher) |
| Gründer (`name_gruender`) | 0 % | **0 %** |
| Rechtsform/Stage ≠ `pre_gruendung` | 0 % | **28,8 %** (8 pre_seed, 6 seed, 1 in_gruendung) |
| Papers belegt (`forscher_match`) | 0 % | **0 %** |
| Noise ≠ `vc_potenzial` | 0 % | 0 % |
| `in_databases = true` | 0 % | 1,9 % (1 Lead) |
| Confidence (Median) | 0,33 | 0,335 |

Stage online: 37 `pre_gruendung`, 8 `pre_seed`, 6 `seed`, 1 `in_gruendung`. Noise: 52 × `vc_potenzial`.

Evidence im Dossier (Felder mit Fundstelle):
- `managing_directors` bei 15 Leads, `legal_form` 15, `imprint_url` 16, `website_text` 18
- `first_web_capture` 11, `patents` 10, `ip_status` 9, `in_formation` 10, `register_id` 9
- `idw` 21, `project_page` 25

**Lücke 1, die größte: Gründer.** Das Impressum liefert für 15 Leads die Geschäftsführer (z. B. Ymolution: Reder,
Hentschker), im Scoring kommt aber kein Name an. Ohne Namen läuft kein OpenAlex-Abgleich, und `forscher_match` (Team
30 %), `komplementaer` und `vorerfahrung` bleiben neutral. Vorschlag an `scorer`/`matcher`: In
`evaluation/engine.to_dossier` bzw. im Kontext `managing_directors` als Team mit Impressum-URL übernehmen
(öffentliche Geschäftsdaten), danach OpenAlex für diese Namen.

**Lücke 2: Noise-Filter.** Er greift auch online nie, 0 von 52. Für 18 Leads liegt `website_text` vor; unter den Top
52 ist schlicht keine Agentur. Ob die Regeln stimmen, lässt sich erst an der Longlist prüfen.

**Lücke 3: Namensvetter-Regel.** Bei M-Shunt hält Wayback die Website für einen Namensvetter: Die Domain ist von
2023, die Seite nennt aber selbst das FKZ. Den gleichen Befund hat der Faktencheck. Vorschlag: Alter nur als Hinweis
werten, wenn das FKZ oder EXIST auf der Seite steht.

## 3. Diagnose: Welche Kriterien zeigen zu „talk“?

Spearman der Kriterienpunkte mit dem Label (talk=2, maybe=1, no=0) über die 30 gelabelten Leads. Bei
Team/Markt-Kriterien ist ein **positives** Vorzeichen erwünscht, bei Risiko-Kriterien ein **negatives**.

| Kriterium (Gewicht in der Achse) | rho online | Ø talk / Rest | Belegquote | Urteil |
|---|---|---|---|---|
| team.forschungsumfeld (0,20, Proxy) | **+0,47** | 75,9 / 70,3 | 100 % | richtig, trägt die Team-Achse; Vorsicht: Institutsprestige (Dresden-Häufung) |
| achse.team_score | +0,47 | 64,2 / 63,1 | | richtig |
| risiko.datenlage (0,15) | −0,33 | 59 / 72,5 | 100 % | richtig: belegte Leads sind die besseren |
| risiko.finanzierung (0,20) | −0,37 | 22 / 24,2 | 100 % | richtig, Effekt klein |
| risiko.ip (0,15) | −0,22 | 47 / 48,2 | 10 % | richtig, kaum belegt |
| achse.risiko_score | −0,26 | 43,0 / 47,2 | | richtig |
| marktpotenzial.tech_tiefe (0,15, Proxy) | +0,04 | 85,3 / 85,8 | 100 % | trennt nicht |
| marktpotenzial.skalierbarkeit (0,15) | −0,04 | 49,8 / 52,0 | 83 % | trennt nicht, leicht gegenläufig |
| marktpotenzial.traktion / zielkunde | −0,12 | ≈50 | 3 % | fast nie belegt |
| **marktpotenzial.timing (0,15)** | **−0,37** | 92 / 100 | 100 % | **gegenläufig** |
| achse.marktpotenzial_score | **−0,15** | 61,5 / 63,6 | | **gegenläufig** |
| team.vollzeit, komplementaer, forscher_match, vorerfahrung; markt.marktvolumen, wettbewerb | – | konstant | | tragen nichts bei (alle gleich oder neutral) |

**Warum timing gegenläufig ist:** `timing` gibt 100 Punkte, wenn die EXIST-Förderung in ±6 Monaten endet, und nur 60
bzw. 30, wenn sie seit 7–12 bzw. 13–24 Monaten vorbei ist. Die belegten Anrufkandidaten haben aber oft schon
gegründet, und ihre Förderung ist gerade vorbei, z. B. Versatile Robotics (endete 03/2026, 0,6). Wer gegründet hat
und kein EXIST-Geld mehr bekommt, braucht jetzt Kapital; das Kriterium bestraft genau diese Gruppe.

**Simulation** (Achsen aus `teilwerte` neu gewichtet, Rechnung gegen die Ist-Scores geprüft; 30 Agent-Labels,
Überanpassungsgefahr):

| Variante | Spearman | P@10 | P@30 | P@10 nur gelabelte |
|---|---|---|---|---|
| Ist (0,35/0,35/0,30) | 0,14 | 40 % | 35 % | 50 % |
| Achsen 0,40/0,25/0,35 | 0,20 | 40 % | 39 % | 50 % |
| timing-Gewicht 0,15 → 0 | **0,30** | 50 % | 44 % | 50 % |
| timing 0, skalierbarkeit 0,15 → 0,05 | **0,32** | 50 % | 47 % | 60 % |
| datenlage im Risiko 0,15 → 0,30 | 0,16 | 50 % | 39 % | 60 % |
| Kombination: 0,40/0,25/0,35 + timing 0 + datenlage 0,30 | **0,33** | 50 % | 47 % | 60 % |
| nur Team und Risiko (0,5/0/0,5) | 0,37 | 40 % | 50 % | 60 % |

### Vorschläge für `scoring_config.yaml` (umsetzen soll `scorer`, ich habe nichts geändert)

1. **`timing` umbauen und abwerten:** Gewicht 0,15 → 0,05. Ist eine Kapitalgesellschaft belegt (GmbH/UG/i.G.) und
   EXIST seit höchstens 12 Monaten beendet, sollte timing ≥ 0,85 geben statt 0,6. Das „Gründungsfenster“ ist dann
   erreicht, nicht verpasst. Das frei werdende Gewicht geht auf `traktion`, sobald Partner belegt werden.
2. **`skalierbarkeit` 0,15 → 0,10:** trennt nicht und belohnt Software pauschal.
3. **`gewichte`:** team 0,35 → 0,40, marktpotenzial 0,35 → 0,25, risiko_invers 0,30 → 0,35, solange die
   Marktachse fast nur aus Proxys und Neutralwerten besteht (marktvolumen, wettbewerb, zielkunde zu 0–3 % belegt).
   Zurücknehmen, wenn Marktdaten kommen.
4. **`risiko.datenlage` 0,15 → 0,25** (zulasten von `tech_reife`, dessen Wert aus der schwachen Textklassifikation
   kommt). Belegte Firmenfakten sind der beste Prädiktor, den wir haben.
5. **`forschungsumfeld` nicht erhöhen:** Es ist das stärkste Kriterium (+0,47), aber ein Proxy für Prestige. Fünf
   der Online-Top-10 kommen aus Dresden. Lieber beobachten, als es weiter zu verstärken.
6. **Gründer übernehmen** (s. Lücke 1): Das bringt mehr als jede Gewichtsänderung, weil dadurch 30 % der Team-Achse
   überhaupt erst messbar werden.

Alle Simulationen beruhen auf 30 **unbestätigten** Labels (10 talk). Vor dem Umsetzen sollte das Team die Labels
bestätigen und die 5 ungelabelten Top-10-Leads labeln. Danach mit
`precision.py online/sc/scores.json --nur-bestaetigt` neu messen.

## 4. Best-Find-Kandidaten im Online-Ranking

| Lead | offline Rang (von 52) | **online Rang** | Score online | Stage online | Grund |
|---|---|---|---|---|---|
| Ymolution | 42 | **9** | 63,6 | seed | Website gefunden, GmbH im Impressum, Risiko 53 → 32. „seed“ beruht auf Reifegrad `erste_kunden` aus der Textklassifikation (nicht geprüft) |
| SECARA | 5 | **15** | 61,6 | seed | Website, GmbH, Reifegrad `pilot` (Envalior-MoU) |
| Versatile Robotics | 47 | **48** | 57,5 | pre_gruendung | **Matcher-Fehltreffer:** versatile-robotics.com nicht gefunden (beste Kandidatin versatilerobotics.eu, 0,45, Namensvetter-Deckel). Der CamelCase-Name „VersatileRobotics“ wird beim Domain-Raten nicht zu „versatile-robotics“ getrennt, und die DLR-Seite mit dem Link gilt als Projektseite. Hinweis an `matcher` |
| InhalPlus (gestrichen, finanziert) | 27 | 34 | 59,1 | pre_gruendung | keine Website über der Schwelle; NBank-Runde dem Scoring unbekannt |
| Aiina/Sitegeist (finanziert) | 4 | 21 | 60,5 | pre_gruendung | Matcher findet die umbenannte Firma nicht |

Ymolution springt durch T1 von Rang 42 auf 9. Am Best Find selbst zeigt sich so, dass die Online-Kette wirkt.

## Was das Team tun muss

1. Labels bestätigen (`quelle_label=team`) und die 5 ungelabelten Online-Top-10-Leads labeln (BotFellows,
   SideroGaIn, dentson, Metubiq, SpinMagIC). Danach `precision.py --nur-bestaetigt`.
2. `scorer`: Vorschläge 1–4 prüfen, Gründer-Mapping (Lücke 1) mit `matcher` abstimmen.
3. `matcher`: CamelCase-Trennung beim Domain-Raten (VersatileRobotics → versatile-robotics); Links von Projektseiten
   wie dlr.de als Kandidaten zulassen. Namensvetter-Regel bei FKZ auf der Seite lockern (M-Shunt).

## Dateien

- `AGENT_TEAM/eval/coverage.py`: Abdeckung, Verteilung, Kriterien-Spearman, Ränge ausgewählter Leads.
  Aufruf: `coverage.py scores.json [labels.csv] --ids a,b --json out.json`
- `AGENT_TEAM/reports/scratch/eval/online/`:
  - `input.json`, `dossiers.json`, `context_run.log`
  - `sc/` (online), `sc_offline/`
  - `precision_online.json`, `precision_offline.json`
  - `coverage_sc.json`, `coverage_sc_offline.json`
