# Report `scorer` – T2 Scoring-Differenzierung

Stand 21.11.2026, Branch `agents/data-quality-fixes`. Nichts committet.

## Befehl (reproduzierbar)

```bash
S=AGENT_TEAM/reports/scratch/scorer
.venv/bin/python -m context examples/sourcing/shortlist.json $S/d.json --offline --light
.venv/bin/python -m scoring $S/d.json --out $S/sc  --stichtag 2026-11-21
.venv/bin/python -m scoring $S/d.json --out $S/sc2 --stichtag 2026-11-21 && cmp $S/sc/scores.json $S/sc2/scores.json   # identisch
```

`$S/sc_before/` enthält den Lauf vor den Änderungen.

## Vorher / Nachher (733 Leads, offline)

| Kennzahl | vorher | nachher |
|---|---|---|
| gesamt_score min / p10 / Median / p90 / max | 48,7 / 49,3 / 52,8 / 53,7 / 53,7 | 47,5 / 50,4 / 56,2 / 59,1 / 62,0 |
| verschiedene gesamt_score | 6 | 96 |
| team_score min–max (distinct) | 50,0–60,0 (2) | 50,8–67,5 (31) |
| marktpotenzial_score min–max (distinct) | 50,0–50,0 (1) | 44,8–68,8 (37) |
| risiko_score min–max (distinct) | 49,3–54,5 (3) | 48,5–59,4 (12) |
| confidence min / Median / max | 0,07 / 0,14 / 0,14 | 0,19 / 0,31 / 0,39 |
| Forschungstransfer (146) Median | – | 58,1 (50,7–62,0) |
| Gründungsstipendium (587) Median | – | 55,9 (47,5–60,7) |
| Stage | 733 × `pre_gruendung` | 733 × `pre_gruendung` (offline ist keine Rechtsform belegt, das stimmt so) |
| Noise | 733 × `vc_potenzial` | 733 × `vc_potenzial` (kein Projekttitel ist ein Dienstleistungstitel; die Website-Regel greift, sobald der Matcher `website_text` liefert) |
| value_proposition = Platzhalter | 733 | 0 |

Die Confidence bleibt bei allen 733 unter 0,4. Deshalb beginnt jede Hypothese mit „Datenlage zu dünn …“ und nennt danach die belegten Stärken und den Meilenstein. So wirkt kein reiner Katalog-Lead belastbarer, als er ist.

## Top 10 (Stichtag 2026-11-21)

| # | Lead | Gesamt | Team | Markt | Risiko | Conf | Treiber |
|---|---|---|---|---|---|---|---|
| 1 | Linque (03EFBY0316) | 62,0 | 64,3 | 68,8 | 48,5 | 0,33 | Forschungstransfer 1,3 Mio., LMU Informatik, Förderende 12/2026 (Gründungsfenster), Software |
| 2 | KPLMotion (03EFNW0388) | 61,7 | 64,3 | 68,8 | 49,5 | 0,33 | Forschungstransfer, RWTH Embedded Software, Ende 03/2027 |
| 3 | Smarobix (03EFSN0242) | 61,4 | 64,3 | 68,8 | 50,5 | 0,33 | Forschungstransfer, TU Dresden Adaptive Dynamische Systeme, endete 04/2026 |
| 4 | Enerbeat (03EFNI0141) | 60,9 | 64,3 | 66,5 | 49,5 | 0,33 | Forschungstransfer, TU Braunschweig Algorithmik, Ende 09/2027 |
| 5 | Lexgraph (03EGTBE083) | 60,7 | 66,8 | 65,9 | 52,5 | 0,37 | Stipendium (mind. 3 Personen), HU Informatik, Ende 11/2026 |
| 6 | Lyrasense (03EGTBY114) | 60,7 | 66,8 | 65,9 | 52,5 | 0,37 | Stipendium, TUM Data Science in Earth Observation |
| 7 | KlaroCare (03EGTBY184) | 60,7 | 66,8 | 65,9 | 52,5 | 0,37 | Stipendium, TUM Software & Systems Engineering |
| 8 | ArcadiaNetwork (03EGTBY214) | 60,7 | 66,8 | 65,9 | 52,5 | 0,37 | Stipendium, TUM Software & Systems Engineering |
| 9 | HefexLabs (03EGTBY245) | 60,7 | 66,8 | 65,9 | 52,5 | 0,37 | Stipendium, TUM Computer Vision & AI |
| 10 | OptiMigration (03EGTHE034) | 60,7 | 66,8 | 65,9 | 52,5 | 0,37 | Stipendium, TU Darmstadt Wirtschaftsinformatik |

Am unteren Ende stehen Gründungsstipendien an Hochschulen ohne Technikbezug, deren Förderung vor 18 bis 22 Monaten endete: AthleteCapital (Sporthochschule) 47,5, Prospera 47,6, EDISON (Hochschule der Medien) 48,1. Plausibel sind: Forschungstransfer vor Stipendium, Forschungsinstitut vor Hochschule, Gründungsfenster vor lange beendeter Förderung. Die Plätze 5 bis 10 sind gleichauf, weil ihre Katalogprofile gleich sind. Den Gleichstand bricht die Pipeline (`ranking_key`).

**Reale Beispiele** (`examples/context/scores/`, Stichtag 2026-11-20): siderogain 70,5 (pre_seed), spinmagic 60,7, hochquant 53,4. **kiutra 20,0 `zu_spaet`**: „älter als 36 Monate (gegründet 2018 laut Pressetext, bestätigt durch Rechtsform GmbH und Datenbankeintrag)“.

## Änderungen

1. **Förderkatalog-Felder** (`evaluation/engine.py::to_dossier`): Jeder `foerderung`-Eintrag trägt jetzt `kennzeichen`, `empfaenger`, `ausfuehrende_stelle` und `thema`, gelesen aus dem Signal- bzw. Evidence-Text derselben Katalog-URL. Neues Dossierfeld `website_text` aus der Kontext-Evidence `website_text`, wie mit dem Matcher abgesprochen; Modellzitate zählen nicht.
2. **Neue bzw. erweiterte Kriterien** (`scoring/engine.py`, `scoring_config.yaml` Version 1.1): `forschungsumfeld` (Team, Proxy), `timing` (Markt, Monate bis Förderende), `tech_tiefe` (Markt, Proxy). Hinzu kommen Fallbacks für `komplementaer` (Mindest-Teamgröße aus der Stipendiensumme nach EXIST-Obergrenzen; Forschungstransfer = Forschungsteam), für `skalierbarkeit` und `regulatorik` (Fachgebiet der ausführenden Stelle, Proxy) und feinere `finanzierung`-Stufen. Ein Proxy ist mit Faktor 0,75 gedämpft und zählt halb für die Confidence. Die Fachgebiets-Proxies lesen nur die Katalogseite, nie Selbstbeschreibungen.
3. **kiutra / Alter**: Ein Pressetext-Jahr älter als 36 Monate führt zu `zu_spaet`, wenn eine belegte Kapitalgesellschaft oder `in_databases=true` es bestätigt. Ein Datenbankprofil älter als 36 Monate führt zu `zu_spaet`, wenn es höchstens 24 Monate vor dem ersten eigenen Signal liegt. Die Fremdbezug-Regel (Jahr mehr als 24 Monate vor dem ersten Signal wird ignoriert) gilt weiter und hat Vorrang. Ein unbestätigtes altes Jahr ergibt nur einen offenen Punkt. Begründung in `scoring/SCORING.md`, Abschnitt „Stage“.
4. **Noise**: Die Agentur-Regel verlangt mindestens ein Kernwort, ignoriert verneinte Wörter („keine Agentur“) und hat einen Gegencheck über Produkt-/Forschungswörter. Sie läuft auf `website_text` und dem belegten Beschreibungstext. Neu ist eine Titelregel ohne Website: Ein Projekttitel, der auf „…beratung“, „Consulting“, „…agentur“ oder „…dienstleistung“ endet, gilt als Noise.
5. **Texte**: Ein Platzhalter („„X“ [(ehemals „Y“)] – Projekt im Programm …“) wird erkannt. `value_proposition` und `produktbeschreibung` entstehen dann aus belegten Katalog-Fakten mit „noch nicht belegt“ für Produkt und Nutzen. Die Hypothese nennt die belegten Stärken und „Wenn bis Förderende MM/JJJJ die Gründung gelingt …“. `why_now` nennt „läuft bis“ bzw. „lief bis … – Status prüfen“. Die Längenlimits 200/300/400 sind eingehalten (max. 200/298/400).
6. **Regeneriert**: `examples/context/scores/`, `examples/scoring/` (Stichtag 2026-11-20, Befehle aus `examples/README.md`). `scoring/SCORING.md` ist aktualisiert (Achsen, neuer Abschnitt „Förderkatalog-Auswertung“, Stage, Noise, Texte, Offen).

## Tests

`.venv/bin/python -m pytest -q` → **772 passed** (inkl. Tests des Matchers). Neu ist `tests/test_scoring_differentiation.py` mit 33 Tests: Katalogfelder, Institutsklassen, Stipendien-Teamgröße, Timing-Stufen, Fachgebiets-Proxies, keine Proxies aus Selbstbeschreibungen, kiutra-Fälle samt Namensvetter-Schutz und junger Jahreszahl, altes oder fremdes DB-Profil, Titel- und Website-Noise, keine False-Positives auf Deep-Tech-Websites und Katalog-Beispielen, Determinismus. Angepasst wurden mit Begründung: `test_hypothesis_wording` (Confidence 0,03 → 0,04 durch neues Datenlage-Gewicht) und in `test_scoring_sourced_leads.py` Team 60 → 59, Förderpunkte 45/25 → 40/30 sowie die erweiterten `foerderung`-Schlüssel.

## Offene Punkte

- **Matcher**: Die Noise-Website-Regel braucht die Evidence `field="website_text"` (zugesagt, Mapping ist in `to_dossier` drin). `website_description` baut der Matcher nicht. `project_page` wird bisher nicht ausgewertet.
- **Fehlende Felder aus `context/`**: Offline gibt es keine Gründer, Papers, Rechtsform oder `in_databases`. Deshalb ist der Stage-Wert überall `pre_gruendung` und rund die Hälfte des Gewichts bleibt neutral. Mehr Spreizung entsteht erst mit Online-Anreicherung (OpenAlex, Impressum, Wayback) und mit `website_text`.
- Die Gewichte und Proxy-Werte sind nicht kalibriert. Das ist Aufgabe T3/evaluator: Precision@30 gegen Handlabels; die Stellschrauben stehen in `scoring_config.yaml` unter `katalog` und `kriterien`.
- Stipendien-Obergrenzen: 150 EUR Kinderzuschlag und 30.000 EUR Sachmittel sind belegt. 3.000 EUR/Monat für Promovierte und 5.000 EUR Coaching sind in der Konfiguration als Annahme markiert; Prüfung am Richtlinientext steht aus.
- Die Fachgebiets-Regex sind grob (z. B. „Medien“ → ohne Technikbezug, damit landet die Hochschule der Medien unten). Sie wirken nur gedämpft als Proxy und sind in der Konfiguration anpassbar.

## Nachtrag (QA M2 und Faktencheck, 21.11.2026)

- **M2 Evidence ohne URL**: Eine Stage-Regel ohne Beleg sagt jetzt ausdrücklich "… – keine Daten, neutral gesetzt" (733× "pre_gruendung: keine Rechtsform belegt – keine Daten, neutral gesetzt"). Stage- und Noise-Einträge aus Sourcing-Metadaten sagen "laut Sourcing (ohne URL)". Über den 733er-Lauf und beide Beispielordner hinweg haben alle 8.382 Evidence-Einträge ohne URL diese Kennzeichnung, `chk.py` meldet 0 Treffer. Test: `test_every_evidence_without_url_is_marked_neutral_or_sourcing`.
- **Exzellenzliste je Förderphase**: Die Einträge in `katalog.institut_klassen` tragen optional `ab`/`bis`. Konstanz zählt bis 31.12.2026 als Exzellenzuniversität. Ab 01.01.2027 kommen Freiburg, Jena, Köln, Bochum/Dortmund und Frankfurt/Mainz dazu; Darmstadt ist schon TU9. Quellen stehen als Kommentar in der Konfiguration. Zum Stichtag 21.11.2026 ist der 733er-Lauf unverändert; mit Stichtag 2027-01-15 ändert sich das Forschungsumfeld bei 43 Leads. Test: `test_excellence_list_follows_the_funding_phase`.
- **EXIST-Annahmen**: In der Konfiguration ist jetzt markiert, welche Sätze belegt sind (Kinderzuschlag, Sachmittel, mit Quelle) und welche Annahme sind (3.000 EUR Promovierte, 5.000 EUR Coaching). Die Werte sind unverändert.
- Gewichte und Kalibrierung sind nicht angefasst. `examples/context/scores/` und `examples/scoring/` sind neu erzeugt. Zweiter Lauf identisch.

## Kalibrierungsrunde (21.11.2026, nach `evaluator_online.md`)

Vorsicht: 30 Labels, alle `agent_vorschlag`, unbestätigt. Jede Änderung ist fachlich begründet; die Kennzahlen dienen nur zur Kontrolle.

| Änderung | fachliche Begründung |
|---|---|
| Impressum-Geschäftsführung → Team (`to_dossier`): Rolle „Geschäftsführung“, Beleg Impressum-URL, `herkunft: impressum`. Abgleich über den Namen mit `founder_profiles`; die Matcher-Profile mit Rolle „Geschäftsführung (Impressum)“ werden erkannt. Filter gegen Nicht-Namen (Rektor/Präsident, „Commercial Register“, „VAT ID“, „Product Development“, einzelne Wörter) | „We invest in people“: Ohne Namen sind 30 % der Team-Achse (Papers) nicht messbar, und OpenAlex braucht die Namen. Eine einzelne Geschäftsführerin ist kein Beleg für eine Solo-Gründung, deshalb fällt `komplementaer` dann auf die Förderdaten zurück |
| `timing`: gegründet (GmbH/UG/AG/SE, auch i.G.) und Förderende ≤ 12 Monate → 0,9; Gewicht 0,15 → 0,05 | HTGF investiert in die Anschlussfinanzierung nach EXIST. Ein gegründetes Team mit gerade beendeter Förderung ist der Anrufkandidat und darf nicht abgewertet werden. „Förderung endet bald“ ist ein Anlass, kein Qualitätsmerkmal |
| Achsen 0,35/0,35/0,30 → 0,40/0,25/0,35 | Team zuerst. Die Marktachse ist bei EXIST-Leads fast nur Proxy/neutral (Marktvolumen, Traktion, Zielkunde zu 0–3 % belegt). Zurücknehmen, wenn Marktdaten kommen |
| `skalierbarkeit` 0,15 → 0,10 (zu `traktion` 0,25 → 0,35, `marktvolumen` 0,20 → 0,25) | Der Fachgebiets-Proxy belohnt Software pauschal. Traktion und Marktvolumen sind die eigentlichen Marktkriterien und greifen, sobald belegt |
| `datenlage` 0,15 → 0,25 zulasten `tech_reife` 0,35 → 0,25 | Mehrere unabhängige Quellen sind belegte Firmenfakten. `tech_reife` kommt aus der schwächsten Quelle (Textklassifikation, laut Faktencheck rund 2/3 falsch oder schwach) |
| `seed` nur mit Reifegrad auf ≥ 2 Domains oder belegtem Kunden/Piloten; sonst `pre_seed`, und `tech_reife` zählt nur als Proxy (`reifegrad_quellen` aus `to_dossier`, ohne Modellzitate) | M-Shunt: Eine Website-Textstelle („pricing … contact“) ergab „erste_kunden“, daraus `seed` und niedriges Risiko. Eine einzelne unbestätigte Klassifikator-Aussage soll keine Stage setzen. Handgepflegte Dossiers ohne Quellenliste bleiben beim Einzelbeleg |
| `forschungsumfeld` **nicht** erhöht | Prestige-Proxy, schon heute das stärkste Kriterium |

**Messung mit `AGENT_TEAM/eval/precision.py`** (52 Leads, 30 Labels; Scores in `AGENT_TEAM/reports/scratch/scorer/kal/`):

| | online vorher | online nachher | offline vorher | offline nachher |
|---|---|---|---|---|
| Spearman(Score, Label) | 0,14 | **0,32** | 0,01 | **0,22** |
| P@10 talk (Abdeckung) | 40 % (50 %) | 50 % (40 %) | 33 % (60 %) | 33 % (60 %) |
| P@30 talk / Noise (Abdeckung) | 35 % / 5 % (67 %) | 39 % / 6 % (60 %) | 35 % / 0 % (57 %) | 39 % / 0 % (60 %) |
| Leads mit Gründernamen | 0 | 14 | 0 | 0 |
| Stage online | 37 pre_gründung, 8 pre_seed, **6 seed**, 1 i.G. | 37 / 14 / **0** / 1 | – | – |
| M-Shunt (einziges „no“) | Rang 16, seed | Rang 24, pre_seed | | |

- Alle sechs bisherigen `seed`-Einstufungen hingen an einer einzelnen Textstelle. Das ist gewollt; eine bestätigte zweite Quelle hebt sie wieder.
- Offline über 733 Leads: 47,1 / 54,1 / 58,2 (min / Median / max), 89 verschiedene Werte, Confidence-Median 0,35. Die Spanne ist enger als nach T2 (47,5–62,0), weil der Timing-Abschlag gewollt ist.
- Determinismus: Online- und 733er-Lauf sind beim zweiten Lauf byte-identisch.
- Suite: **784 passed**. Neue Tests in `tests/test_scoring_differentiation.py`:
  - `test_managing_directors_become_team_with_imprint_source`
  - `test_single_imprint_director_is_not_a_solo_founder` (inkl. Matcher-Profil-Dedup und Müllnamen)
  - `test_timing_rewards_founded_teams_at_funding_end`
  - `test_seed_needs_independent_maturity_evidence`
- Angepasst: `test_config_weights_are_checked` (Literal `team: 0.40`), `test_hypothesis_wording` (Confidence 0,09), Spread-Schwelle im Sample-Test (2,5 statt 3).
- Beispiele sind neu erzeugt, SCORING.md ist aktualisiert (Achsen, Formel mit Begründung, Timing, Seed-Regel, Impressum-Team).

**Offen:**
- Die Online-Dossiers stammen noch aus dem Lauf vor der Matcher-Änderung. Die neuen Impressum-Profile mit OpenAlex sind erst nach einem neuen Online-Lauf messbar.
- Die Impressum-Namen des Matchers waren teils Müll (z. B. „Commercial Register“, „VAT ID“, „Rector …“ bei einem Uni-Impressum). Der Scorer filtert sie; besser wäre, wenn context sie gar nicht erst liefert.
- Die Gewichte bleiben vorläufig, bis das Team die Labels bestätigt hat.

**Nachtrag Matcher-Abstimmung:** Der Matcher filtert die Müllnamen jetzt in `context/imprint.py`; der Filter im Scorer bleibt zur Sicherheit. Weil context für Katalog-Leads `works_in_field` bewusst leer lässt, zählt für `forscher_match` ersatzweise `works_total` eines OpenAlex-Profils mit `match_confidence` ≥ 0,5: als gedämpfter Proxy, ohne Malus, unsichere Zuordnung bleibt neutral. Test: `test_total_works_count_as_weak_researcher_proxy`. Behoben ist außerdem ein Fehler im Namensabgleich: Ziffern zählen jetzt mit, damit die Pseudonyme „Person 01/02 …“ nicht zu einer Person verschmelzen; Test `test_name_dedup_keeps_distinct_people`. Die Kennzahlen sind unverändert (online 0,32, offline 0,22), die Beispiele neu erzeugt, beide Läufe deterministisch. Die Suite steht bei **787 passed**. `web_capture_before_project` wertet der Scorer nicht aus; es ist kein Signal, und das ist gewollt.

## Fix-Runde nach dem Final Gate (M1, M2, M3, m3)

Die Gewichte sind **nicht** geändert (0,40/0,25/0,35 wartet auf das Team). Gemessen auf `AGENT_TEAM/reports/scratch/gate/dossiers.json`, Stichtag 2026-11-21: vorher `gate/sc/`, nachher `scratch/scorer/gate_fix/`.

| Befund | Fix | vorher → nachher (52 Leads) |
|---|---|---|
| M1 Müll-Partner | Fördergeber, Programme und generische Phrasen werden verworfen, zerschnittene Namen über das Zitat wieder zusammengesetzt. Voll zählt ein Partner nur mit Rechtsform oder bekannter Einrichtung (auch direkt hinter dem Namen im Zitat), sonst als Proxy. `to_dossier` reicht das Partner-Zitat durch | Traktion belegt 4 → 2 (SideroGaIn/FCM GmbH voll, SIMBA „Fraunhofer-Institut für Software- und Systemtechnik ISST“ als Forschungspartner); BotFellows „Global Partners“ und SpinMagIC „Federal Ministry …“ fallen weg |
| M2 VP-Platzhalter | VP und Produktbeschreibung extraktiv aus `website_text`. Ursache, dass es vorher nicht ging: `clean()` hatte die Zeilenumbrüche entfernt. Lange Institutsnamen werden nicht mehr mitten im Wort gekürzt (SECARA) | Platzhalter-Ende 49 → 31 (alle 20 Website-Leads außer BEHtec mit Lorem-ipsum-Seite haben eine VP aus der Website); offline 733: 711, weil offline kein Website-Text vorliegt |
| M3 DB-Aussage | Formulierung nach Art der Prüfung (Wayback / Datenbanksuche / Treffer). Bei einem Treffer ohne Datum ist `earliness_delta_monate` leer plus offener Punkt. `to_dossier` bevorzugt eine Nicht-Wayback-Quelle; Format mit dem Matcher abgestimmt (Evidence `in_databases`, Quelle „Datenbanksuche (Brave)“) | „nicht gefunden“ 48 → 0, jetzt „kein archiviertes Crunchbase-/Dealroom-Profil (Wayback)“ |
| m3 Team/Meilenstein | Hat das Team nur eine Person aus dem Impressum, wird sie in der komplementaer-Aussage genannt; mehrere heißen „Personen in der Geschäftsführung (Impressum)“. „Wiederholbarer Vertrieb“ nur mit belegtem Kunden oder bestätigtem Reifegrad, sonst „ein belegter zahlender Kunde“. Grammatik „1 belegter Partner“ | Widerspruch Name/„nicht namentlich“ 5 → 0; „wiederholbarer Vertrieb“ 7 → 0 |

**Kennzahlen** (`precision.py`, 30 ungeprüfte Labels):

| | Gate vorher | nach Fix |
|---|---|---|
| Spearman | 0,41 | 0,44 |
| P@10 talk | 67 % | 83 % |
| P@30 talk | 47 % | 47 % |

- Top 10 nach Fix: DyNAtrix 68,0 · iNSyT 67,1 · BotFellows 64,9 · SideroGaIn 64,8 · Ymolution 64,5 · Metubiq 62,9 · SA-Dynamics 62,9 · AutonomIQ 62,5 · VersatileRobotics 62,2 · SpinMagIC 61,9.
- BotFellows fällt ohne den Müll-Partner von 69,2 auf 64,9, das entspricht der Schätzung im Gate (≈ 64,8).
- Offline über 733 Leads unverändert: 47,1–58,2, 89 Werte, Spearman 0,22.
- Schema: 0 Fehler, Evidence ohne URL weiterhin 0 ungekennzeichnet.
- Determinismus: Gate- und 733er-Lauf sind beim zweiten Lauf byte-identisch.
- Suite: **807 passed** (inkl. neuer Tests anderer Agents).
- Neue Tests in `tests/test_scoring_differentiation.py` (jetzt 45):
  - `test_funders_and_generic_phrases_are_not_traction`
  - `test_value_proposition_from_website_text`
  - `test_long_institution_name_is_not_cut_mid_word`
  - `test_why_now_names_the_kind_of_database_check`
  - `test_team_texts_agree_and_milestone_needs_customers`
- Angepasst: die `why_now`-Erwartung in `test_scoring_sourced_leads.py` (Wayback-Formulierung).
- Beispiele neu erzeugt.

**Offen:**
- Die echte DB-Suche des Matchers ist erst nach einem neuen Online-Lauf messbar.
- Die Website-VP ist extraktiv und klingt teils nach Werbetext („It’s time to find your answer.“). Die Entscheidung, ob ein Modell umformulieren darf, liegt beim Team.
- SIMBAs Partnerzitat handelt von einem Fraunhofer-Projekt ohne erkennbaren SIMBA-Bezug. Das kann nur die Klassifikation in context lösen (matcher).
