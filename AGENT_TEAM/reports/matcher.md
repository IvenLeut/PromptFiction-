# T1 Matcher: Projektname → Firmen-Website

Agent `matcher`, 21.11.2026, Branch `agents/data-quality-fixes`. Nichts committet.

## Was gebaut wurde

**`context/website_match.py` (neu)**, Einstieg `match_lookup(name, *, institution, executing, location, topic, reference, founders, cache, …, threshold=0.6) -> (WebsiteMatch | None, Lookup)`.

1. **Kandidaten** mit Fundstelle:
   - **Websuche** nach `"<Name>" <Institut>`, bei Bedarf danach `"<Name>" Start-up` (höchstens 2 Suchen). Reihenfolge: offizielle **Brave Search API**, wenn `BRAVE_API_KEY` gesetzt ist; sonst bzw. als Fallback Brave-HTML, dann DuckDuckgo-HTML. Captcha- und Fehlerantworten werden nicht gecacht. Nach 401/403/429 oder Captcha pausiert die Suchmaschine 90 s (Circuit Breaker).
   - **Links auf Projektquellen**: Hochschul-, idw- oder Presseseiten, die das Projekt nennen (höchstens 2). Externe Links, deren Host den Projekt-Slug trägt, werden Kandidaten.
   - **Domain-Raten**: `slug` bzw. `slug-mit-bindestrich` auf `.de/.com/.io/.ai/.eu/.tech` und `-gmbh.de`. Geladen wird nur, was im DNS auflöst (DNS-Ergebnis gecacht).
2. **Prüfung jeder Kandidatin** über `context.web.fetch` (Same-Site-Schutz, Parking-Erkennung, Seiten-Cache); bei kaputtem Zertifikat ein Versuch per HTTP.
   - **Punkte gibt es für:**
     - Projektname im Seitentitel (+0,3) bzw. im Kopf (+0,25), sonst im Fließtext (+0,1); fehlt er ganz, wird die Kandidatin verworfen
     - Slug in der Domain (+0,25 / +0,1)
     - Bestätigungen: Institut genannt (+0,15), EXIST erwähnt (+0,15), mindestens drei Themenstämme (+0,1), Gründername (+0,15), Link von einer Projektquelle (+0,15), Ort genannt (+0,1)
     - Nennung des Namens im Impressum (+0,15) und Rechtsform direkt am Namen (+0,1)
   - **Abzüge:** Agentur oder Webdesign (−0,3), Shop ohne Bestätigung (−0,2). Platzhalter- und Parking-Seiten werden verworfen.
   - **Namensvetter-Deckel:** Ohne Bestätigung durch Institut, EXIST, Thema, Gründer, Ort oder Projektquelle ist bei **0,45** Schluss. Impressum und Rechtsform belegen nur, dass hinter der Seite *eine* Firma dieses Namens steht (simba.de), und heben den Deckel nicht.
   - **Unterseiten:** Ist die Startseite unbestätigt, aber prominent, werden bis zu 3 Über-uns- oder Team-Seiten nachgeladen (autonomiq.de nennt TU Darmstadt und EXIST nur dort).
   - **Hochschulhosts:** uni-*, tu-*, Fraunhofer, Helmholtz, DLR, KIT und ähnliche werden als `project_page` eingestuft, nie als Firmen-Website.
3. **Entscheidung:** Ab der Schwelle (Standard 0,6, CLI `--match-threshold`) werden `matched_website` und `match_confidence` gesetzt, jeweils mit Evidence (`source="Website-Abgleich"`, URL = Website, Finding = Begründung + Fundstelle). Darunter wird nichts gesetzt; die beste Kandidatin steht in `enrichment_errors`. Eine Projektseite wird als Evidence `field="project_page"` plus Signal `type="projektseite"` abgelegt.
4. **Cache und Grenzen:** Alles läuft über `.cache/context.db`: Suche über `context.http.request`, Seiten über `context.web.fetch`, dazu `dns:` und `website_match:v8:` je Lead, gespeichert nur bei vollständigem Lauf. Grenzen:
   - höchstens 8 geprüfte Startseiten je Lead
   - 6 s Abstand je HTML-Suchmaschine, 1,1 s bei der API
   - Timeout 10 s für die Suche, 4 s für Seiten
   - Backoff bei 429/5xx in `context.http`

**Verdrahtung (`context/engine.py`):**
- `_match_website` läuft für Leads ohne `website` **vor** Impressum, Wayback und OpenAlex. Sein `match_confidence` gewinnt gegen den Förderkatalog-Wert.
- Die gefundene Website speist danach die Website-Seiten (als `subject_lead_id` an den Lead gebunden), Impressum und Wayback.
- Neu ist die Evidence `website_text`: bereinigter Seitentext, bis 5.000 Zeichen, für den Noise-Filter des Scorers (Feldname mit `scorer` abgestimmt).
- `default_lookups(..., match=True, match_threshold=None)`.
- **CLI** `python -m context`: `--no-match`, `--match-threshold`. `--light`, `--offline` und `--no-lookups` laufen ohne Matcher und ohne Netz.

**Brave Search API (Nachtrag):**
- Key setzen mit `export BRAVE_API_KEY=...` (auch `BRAVE_SEARCH_API_KEY` wird akzeptiert, `BRAVE_API_KEY` gewinnt) oder als Zeile in einer lokalen `.env` im Projektordner. `.env` steht in `.gitignore`; ein Test prüft das.
- Der Key geht nur als Header `X-Subscription-Token` raus, nie in URL, Cache-Schlüssel, Log oder Evidence. Als Fundstelle steht die neutrale Adresse `https://search.brave.com/search?q=…`, `origin="search:brave_api"`.
- Kostenloser Tarif: 1 Anfrage/s, ca. 2.000 im Monat. Ein Lead kostet 1–2 Anfragen; 733 Leads liegen also im Monatskontingent.
- Seit 21.11.2026 04:09 ist ein Key in `.env` gesetzt; die Live-Probe unten lief mit API. Offline getestet mit einer JSON-Fixture.
- **Key-Prüfung:** Worktree (ohne `.venv`/`.git`) inklusive `.cache/` und `AGENT_TEAM/` sowie alle 1.783 Zeilen der Cache-DB (`.cache/context.db`, per Python/`sqlite3`) nach dem Key-Wert durchsucht: kein Treffer außer `.env`.

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `context/website_match.py` | neu |
| `context/engine.py` | Matcher vor den Lookups; `website` an Impressum/Wayback; Evidence `website_text`; `default_lookups(match, match_threshold)`; `_site_confirms_project` → Wayback; OpenAlex für Impressum-GF → `founder_profiles` |
| `context/__main__.py` | `--no-match`, `--match-threshold` |
| `context/wayback.py` | `site_confirmed`/`confirmed_years`: keine Namensvetter-Regel, wenn die Website FKZ/EXIST nennt; frühe Aufnahme nur als Evidence `web_capture_before_project` |
| `context/imprint.py` | Nicht-Namen und Vertreter öffentlicher Körperschaften werden nicht zu `managing_directors`; Fließtext nach Namen abgeschnitten; Name vor nachgestellter Rolle; Gastinstitut-Zeilen (c/o, Institut) ohne Rechtsform |
| `context/dbsearch.py` | neu: Startup-Datenbanksuche über Brave-API |
| `context/classify.py` | keine Fördergeber/generischen Phrasen als Partner; Institutsnamen mit „und“ nicht zerschneiden |
| `tests/test_context_dbsearch.py`, `tests/test_context_classify.py`, `tests/test_context_imprint.py` | Regressionstests der Gate-Fälle |
| `context/lookup.py` | `SOURCE_WEBSITE_MATCH = "Website-Abgleich"`, `SOURCE_PROJECT_PAGE = "Projektseite (Hochschule)"` |
| `context/cache.py`, `context/ENRICHMENT.md` | Doku (Cache-Ebene, Modulzeile, Grenzen, API-Key) |
| `models.py` | **`EnrichedLead.matched_website: HttpUrl \| None = None`** am Ende des Modells |
| `examples/context-schema.json`, `examples/analysis-schema.json` | neu generiert (nur das neue Feld) |
| `evaluation/engine.py` | eine Zeile: `"website": lead.website or lead.matched_website` (das Mapping von `website_text` stammt vom `scorer`) |
| `tests/test_context_website_match.py` + 10 Fixtures `tests/fixtures/context/website_match_*` | 30 Offline-Tests |
| `AGENT_TEAM/reports/matcher_live.json`, dieser Bericht | Live-Probe |

**Warum `models.py`:** `website` ist ein Schritt-1-Feld, und `pipeline._preserve` wirft `InputModifiedError`, sobald Schritt 2 es ändert. Die Alternativen wären gewesen, den Vertrag aufzuweichen oder die Website nur in der Evidence zu verstecken; dann sähe das Scoring sie nicht. Ein optionales Feld am Modellende ist rückwärtskompatibel (Standard `None`, alte Dossiers validieren weiter).

## Live-Probe mit Brave API (21.11.2026)

**Stichproben:**
- **A:** die 20 Leads mit höchster Priorität (Rang 1–20, Priorität 80–90, alle 03EF) plus die 4 bekannten Beispiele SpinMagIC, BoneGuide, HoCHQuant, SideroGaIn
- **B:** Rang 21–50; SpinMagIC (Rang 36) und BoneGuide (Rang 43) liegen in beiden
- zusammen **52 verschiedene Leads**

Jede gesetzte Website habe ich von Hand plausibilisiert: Startseite, Unterseiten, Impressum, Abgleich mit der Ausführenden Stelle. Ergebnisse je Lead mit Kandidaten, Begründung, Fundstelle und Prüfnotiz stehen in `matcher_live.json`.

**API-Verbrauch:** 93 Requests für alle Läufe dieser Session (Lauf A 44, B 47, zwei Einzelanfragen nach Regeländerungen). Wiederholläufe kamen vollständig aus dem Cache (45 bzw. 47 Treffer, 0 neue Requests). Ein Lead kostet 1–2 Requests. Ein Volllauf über 733 Leads braucht also etwa 1.300 Requests und passt in das Monatskontingent von ca. 2.000.

| Kennzahl | vorher (ohne Suche, erster Lauf) | nachher (Brave API, finale Regeln) |
|---|---|---|
| Stichprobe | 24 (A) | 52 (A + B) |
| Website gesetzt | 5 (21 %) | **20 (38 %)**, nach den Fixes der Online-Messung; davor 18 |
| davon Top 20 | 4/20 | 5/20 (+ VersatileRobotics) |
| davon Rang 21–50 | – | 15/30 (50 %) (+ LayerPerformance) |
| Precision (von Hand) | 5/5 | **20/20**: 15 sicher, 5 wahrscheinlich (SECARA, Ymolution, Metubiq, MimoSense, LayerPerformance) |
| Fehltreffer vor dem Fix | 2 (sensai.io, simba.de) | 2 (campus-start-ups.nrw, tentris.dice-research.org) |
| nur Hochschul-Projektseite, keine Website | 2 | 13 |

**Gesetzte Websites (20):**

| Lead | Website | Confidence | Bestätigt durch |
|---|---|---|---|
| Pulse-of-Production | pulse-of-production.de | 1,0 | Institut (MTI) |
| M-Shunt | m-shunt.com | 1,0 | EXIST, Bremen |
| AutonomIQ | autonomiq.de | 0,95 | Link von ptw.tu-darmstadt.de |
| SECARA | secara.tech | 0,95 | Ort + Impressum |
| SpinMagIC | spinmagic.eu | 0,9 | Link von eni.uni-stuttgart.de, EXIST |
| DyNAtrix | dynamicmatrices.eu | 0,65 | Startup-Projektseite c/o Leibniz-IPF, EXIST |
| MillionMolecules | millionmolecules.de | 1,0 | EXIST |
| iNSyT | insyt.solutions | 1,0 | EXIST, München |
| SA-Dynamics | sa-dynamics.com | 1,0 | RWTH, EXIST |
| Ymolution | ymolution.com | 1,0 | EXIST, Greifswald |
| SONOJET | sonojet.com | 1,0 | Link von leibniz-gemeinschaft.de |
| Rement | rement.tech | 1,0 | Link von kit.edu |
| BEHtec | behtec.de | 1,0 | Link von traces.uni-stuttgart.de, EXIST |
| Smarobix | smarobix.com | 1,0 | TU Dresden |
| Metubiq | metubiq.de | 0,95 | Kassel + Impressum |
| BotFellows | botfellows.com | 1,0 | Link von iwu.fraunhofer.de |
| MimoSense | mimosense.de | 0,65 | nur Ort Darmstadt |
| Tentris | tentris.io | 1,0 | Paderborn University, EXIST |
| VersatileRobotics | versatile-robotics.com | 1,0 | Link von event.dlr.de, Weßling, GmbH (neu nach Fix) |
| LayerPerformance | layerperformance.com | 1,0 | Aachen + Impressum, GmbH (neu nach Fix; IKV nicht genannt) |

**Was die API gebracht hat:**
- **Mehr Treffer:** iNSyT und DyNAtrix findet nur die Suche; ein reiner Domain-Raten-Lauf mit denselben Regeln findet 16 statt 18.
- **Belastbarere Belege:** 6 Websites sind jetzt über einen Link auf einer Hochschul-, Leibniz- oder Fraunhofer-Seite bestätigt; als Fundstelle steht diese Seite. Dazu kommen 13 Projektseiten (Uni Paderborn, Hannover, Köln, Kassel, Fraunhofer EMFT, MPI Marburg …), die als `project_page` belegt sind.
- **Top 20 unverändert bei 4:** Dort hat ein großer Teil der Teams noch keine eigene Website. Es gibt nur Projektseiten (DataLingua, AutoAquaControl, SoreAlert, SIMBA, SpaceMast) oder nichts (B-Hear, KPLMotion, PuraiteSLR, HoCHQuant). Das passt zur Earliness-These: Diese EXIST-Projekte laufen noch vor der Gründung.

**Fehltreffer und Gegenmaßnahmen** (jeweils Regel + Regressionstest):
1. **campus-start-ups.nrw** (0,65 für PoLightFilters, auch mechIC): ein Portal, das das Projekt im Fließtext mit EXIST und Ort nennt. Neue Regel: Ohne Namen im Titel oder Kopf und ohne Slug in der Domain ist bei 0,45 Schluss (`Name nur erwähnt (Verzeichnis/Portal/Presse)`).
2. **tentris.dice-research.org** (0,7): die Paper-Seite einer Forschungsgruppe, verlinkt von uni-paderborn.de. Neue Regeln: `*-research.*`-Hosts gelten als akademisch, Paper- und BibTeX-Seiten als `project_page`. Danach findet der Matcher die echte Firma tentris.io (1,0).
3. Aus dem Lauf ohne Suche: sensai.io und simba.de (siehe Abschnitt Fehlertypen unten).

**Richtig verworfene Namensvetter (Deckel 0,45):** sensai.io/.app/.fit, sensaicorp.com, suneo.ai, simba.de/.io, simbaglobalstartups.com, boneguide.com, km-dieberater.de, versatilerobotics.eu, datalingua.net, seasparkle.app, inhaleplus.mk, dentson.tech, commod-house.com, hydropure.ae.

**Fehlertypen der Nicht-Treffer:**
- Es gibt noch keine Website (häufigster Fall in den Top 20, belegt durch Projektseiten statt Firmen-Website).
- Weiterleitung auf eine andere Domain (sorealert.*, bhear.com), die `context.web.fetch` ablehnt.
- Reine JavaScript-Seiten ohne Text (hochquant.de).
- Kurze oder generische Namen (KM, TSS, REPEAT, EXIST_P2P) liefern nur Namensvetter.
- Unbestätigte Kandidaten unter der Schwelle: dentson.tech hat Impressum und GmbH, nennt aber weder Fraunhofer noch EXIST noch den Ort und bleibt deshalb bei 0,45. Ob das ein Fehlnegativ ist, ist offen.

### Erster Lauf ohne API (Archiv)

Zuvor war die schlüssellose Suche gesperrt: Brave-HTML antwortete mit 429, DuckDuckgo nur mit Captcha. 20 von 24 Leads liefen nur mit Domain-Raten. Ergebnis: 5/24 gesetzt, alle richtig. Zwei Zwischenstand-Fehltreffer, beide behoben:
- sensai.io (0,7): Namensstamm und „mechanical“ zählten als Themenbegriffe.
- simba.de (0,75, dann 0,85): Das Impressum zählte als Bestätigung, außerdem „montag“ und „sachse“ als Themenstämme.
- Gegenmaßnahmen: Name, Institut, Ort, Bundesländer und Fachgebietswörter zählen nicht als Themenstämme; Themen bestätigen erst ab drei Stämmen; das Impressum hebt den Namensvetter-Deckel nicht.

siderogain.de ist eine Verkaufsseite (1.470 USD) und wird als Parking verworfen. Für SideroGaIn gibt es keine Firmen-Website, nur die HZDR-Meldung und LinkedIn.

## Nachtrag: Fixes aus der Online-Messung (`evaluator_online.md`)

| # | Befund | Fix | Test |
|---|---|---|---|
| 1 | VersatileRobotics → versatile-robotics.com verpasst | **CamelCase-Trennung** (`spaced_name`): Getrennt wird nur, wenn jedes Teilwort ein normales Wort mit mindestens 3 Buchstaben ist (VersatileRobotics, MillionMolecules, LayerPerformance). SpinMagIC, SideroGaIn, PoLightFilters, iNSyT und DyNAtrix bleiben ganz. Wirkung: Bindestrich-Domains werden mitgeraten (`versatile-robotics.com`), die erste Suche nutzt die getrennte Schreibweise (`"Versatile Robotics" <Institut>`), und der Name trifft auch getrennt geschrieben. Außerdem wird „… is parked“ als Parking erkannt (versatilerobotics.eu). | `test_camel_case_names_are_split_for_guesses_and_queries`, `test_is_parked_page_is_rejected` |
| 2 | Links von Projektseiten (dlr.de) nicht genutzt | Lag an Befund 1: Die DLR-Seite schreibt „Versatile Robotics“ und galt deshalb nicht als Seite über das Projekt. Zusätzlich werden Profile (LinkedIn, XING …) nicht mehr als Projektquelle gescannt, und es werden bis zu 3 statt 2 Projektquellen gelesen. Die verlinkte Seite wird normal geprüft (Fundstelle = Projektseite). | wie 1 |
| 3 | M-Shunt: Wayback hält die Domain (2023) für einen Namensvetter, obwohl die Seite FKZ und EXIST nennt | `context/engine._site_confirms_project` prüft Website- und Impressum-Text auf die FKZ, sonst auf EXIST, und übergibt das als `site_confirmed` an `context/wayback.py`. Nennt die Seite die FKZ, greift die Altersregel nie; nennt sie nur EXIST, gilt die Ausnahme höchstens 3 Jahre vor dem Projekt (behtec.de mit Aufnahme 2010 bleibt ein Namensvetter). Eine solche frühe Aufnahme steht nur als Evidence `web_capture_before_project`, **nicht** als `first_web_capture` und nicht als datiertes Signal. Sonst wäre M-Shunt plötzlich ab 2023 datiert und BEHtec ab 2010; genau das zeigte ein Zwischenstand. | `test_wayback_keeps_early_capture_when_site_names_the_project`, `test_engine_tells_wayback_when_the_site_names_fkz_or_exist` |
| 4 | Gründer 0 %, Papers 0 % | Für Leads ohne Schritt-1-Gründer laufen die Impressum-Geschäftsführer (höchstens 3) durch `author_lookup`. Disambiguiert wird mit dem Institut aus dem Förderkatalog. Sie landen als `founder_profiles` mit `role="Geschäftsführung (Impressum)"`, `source_url` = OpenAlex- bzw. Impressum-URL und `match_confidence`. **Ohne Feldbegriffe:** Die `field_terms` eines Katalog-Leads sind nur der Projektname, und das ergab im Zwischenstand bei allen „0 Papers im Produktfeld“, also einen falschen Abzug von 9 Teampunkten bei 8 Leads. Jetzt bleibt `works_in_field` unbekannt (neutral), und ein Aufruf je Person reicht. Impressum-Parser: Nicht-Namen („Product Development“, „Commercial Register“, „VAT ID“) und Vertreter öffentlicher Körperschaften („Rector …“, Uni-Impressum von MillionMolecules) werden verworfen. | `test_managing_directors_get_openalex_profiles`, `test_no_director_lookup_when_step1_has_founders`, `test_imprint_drops_non_names_and_university_representatives` |

**Erneute Online-Kette** für die 16 betroffenen Leads (VersatileRobotics, M-Shunt und die 15 mit Impressum-GF; M-Shunt gehört zu beiden):
- Lauf: `python -m context` mit API, dann `python -m scoring --stichtag 2026-11-21`.
- Vergleich: Alte Dossiers des `evaluator` (`AGENT_TEAM/reports/scratch/eval/online/dossiers.json`) und neue Dossiers wurden **mit demselben aktuellen Scorer** bewertet, damit die WIP-Änderungen des `scorer` nicht mitgemessen werden.
- Rohdaten: `AGENT_TEAM/reports/scratch/matcher/` (`rerun_dossiers.json`, `rerun_effect.json`, `sc/`, `sc_before/`).

| Wirkung | Ergebnis |
|---|---|
| **VersatileRobotics** | Website neu (versatile-robotics.com, 1,0, Fundstelle event.dlr.de), GF Johannes Englsberger mit OpenAlex-Profil (0,9, 59 Arbeiten); Stage `pre_gruendung` → `pre_seed`; Score 56,5 → **59,5** |
| **M-Shunt** | Keine Namensvetter-Meldung mehr. Die Aufnahme von 2023 steht als `web_capture_before_project` („Website nennt FKZ 03EFHB0044“). `first_signal_date` bleibt beim Projektstart (kein Vordatieren). Score unverändert 57,5 |
| **Tentris** | 52,1 → 54,7 (tentris.io statt Paper-Seite) |
| Gründerprofile | 30 Profile aus dem Impressum bei 15 Leads, **24 davon mit OpenAlex-Profil** (Konfidenz 0,4–0,9). MillionMolecules hat zu Recht keines mehr (Uni-Impressum) |
| Gründernamen im Score (`name_gruender`) | 14 → 15 von 16. Die 14 kamen schon vorher über den Impressum-Abgleich des `scorer` in `to_dossier`; neu ist VersatileRobotics |
| Papers im Feld (`forscher_match`) | weiterhin **nicht belegt** (neutral 50), siehe unten |
| Mittelwert Δ Gesamtscore / Team / Confidence | +0,35 / 0,0 / 0,0 |

**Ehrlich zu Papers:** OpenAlex findet jetzt die Personen (24 Profile mit `works_total`). „Papers im Produktfeld“ lässt sich für Katalog-Leads aber nicht verlässlich zählen. Es gibt keine fachlichen Suchbegriffe: Der Projektname ergibt 0. Wörter von Website und Lehrstuhl (deutsch gegen englische Titel, „Support/Performance“ trifft alles) ergeben Zufallszahlen. Der Versuch ist verworfen. **Entscheidung `scorer`:** Für `forscher_match` zählt ersatzweise `works_total` eines OpenAlex-Profils mit `match_confidence` ≥ 0,5. Das geht als gedämpfter Proxy ein (ab 20 Arbeiten 0,8, ab 5 0,65, ab 1 0,55) und ohne Malus; eine unsichere Zuordnung bleibt neutral. `web_capture_before_project` wertet der Scorer bewusst nicht als Signal. Die Score-Zahlen oben stammen aus der Zeit vor diesem Scorer-Stand.

**API-Verbrauch** für diesen Nachtrag: 8 neue Brave-Requests (getrennte Schreibweisen), insgesamt etwa 101. OpenAlex: höchstens 33 Personen × 1 Aufruf, Wiederholläufe aus dem Cache.

## Nachtrag 2: Fix-Runde nach dem Final Gate (`final_gate.md`)

| Befund | Fix (Datei) | Wirkung im erneuten Online-Lauf (52 Gate-Leads) | Test |
|---|---|---|---|
| **M1** Müll-Partner | `context/classify.py`: Fördergeber (Ministerium/Ministry, Federal, EU, ESF, EXIST, Projektträger, BMWK/BMWE/BMBF …) und generische Phrasen („Global Partners“, „leading brands“) sind nie Partner. Zeilen mit Förderhinweis („supports“, „gefördert“, ESF) liefern keine `gemeinsam mit`-Partner. Kein Trennen an „und/and“ nach einer Wortellipse („Software- und“) oder einem „für/for/of + Substantiv“. | BotFellows: „Global Partners“ (kunde) → –; SpinMagIC: 2× Ministerium (design_partner) → –; SIMBA: 2 Bruchstücke → 1× „Fraunhofer-Institut für Software- und Systemtechnik ISST“ (forschungspartner); SideroGaIn (Freiberger Compound Materials, pilot) bleibt | `test_generic_trusted_by_phrase_is_no_customer`, `test_funding_notice_names_no_design_partner`, `test_institute_name_with_und_is_not_cut` |
| **M3** DB-Prüfung | neu `context/dbsearch.py` + `context/engine._check_databases`: echte Suche über die Brave-API, 1 Anfrage je Lead (`"<Name>" (site:dealroom.co OR site:crunchbase.com OR site:pitchbook.com OR site:tracxn.com)`). Ein Profil zählt nur mit Name im Titel und Bezug zum Lead. Format mit `scorer` abgestimmt (`source="Datenbanksuche (Brave)"`, URL = Profil bzw. neutrale Such-URL). | 6 Leads jetzt `in_databases=True` mit Profil-URL: BotFellows (Tracxn), iNSyT (PitchBook), Metubiq (PitchBook), Smarobix (Tracxn), Tentris (Tracxn), Rement (Crunchbase). 45 geprüft ohne Profil. HydroPURE bleibt beim archivierten Wayback-Profil. Verworfene Namensvetter, z. B. crunchbase insyt (Social-App), assurances-secara, autonomiq (US-Testing-Firma), BOTfriends | `tests/test_context_dbsearch.py` (8 Tests) |
| **m1** Ymolution, 2. GF fehlt | `context/imprint.py` `_split_names`: Fließtext nach dem Namen wird abgeschnitten („… Hentschker explain why …“). | Reder → Reder + Hentschker | `test_director_names_are_cut_before_prose` |
| **m2** DyNAtrix e.V. des Gastinstituts | `_legal_form` ignoriert Zeilen mit „c/o …“ oder Hochschul- bzw. Institutsnamen. Die Rolle kommt aus der Klammer im Impressum (`engine._imprint_role`). | `legal_form` e.V. → –; Rolle „Geschäftsführung (Impressum)“ → „Project Leader (Impressum)“ | `test_host_institute_legal_form_is_ignored`, `test_imprint_role_in_brackets_is_kept` |
| **m7** SpinMagIC „Founded by:“ | **Kein Fehler:** Auf der Seite folgt „Founded by:“ nur „based on a resolution of the German Bundestag“. Das ist die Logozeile des BMWK („Funded by“), es stehen keine Namen dort; auch die Unterseiten nennen keine Gründer. Nebenbefund Pulse-of-Production (GmbH ohne GF) behoben: „Vertreten durch:“ / „Philipp Niemietz Geschäftsführer“ (Rolle nach dem Namen). | Pulse-of-Production: – → Philipp Niemietz | `test_name_before_trailing_role_label` |

- **Manuell geprüft:** alle 6 DB-Treffer. Snippet bzw. Titel nennen Ort, Deutschland, EXIST oder LMU oder dieselben Produktbegriffe wie die Website.
- **Grenze der DB-Suche:** Sie ist bewusst streng; es zählt nur, was der Snippet belegt. Das Dealroom-Profil von BotFellows und das Tracxn-Profil von iNSyT fanden sich im Ergebnis, ihr Snippet bestätigte aber nichts. Sie werden deshalb nicht gezählt; für den Lead reicht ein Profil.
- **API-Verbrauch** dieser Runde: etwa 70 Brave-Requests (52 DB-Suchen Gate-Lauf, 16 DB-Suchen Prüflauf, wenige Matcher-Nachfragen), insgesamt etwa 170 im Monat.
- **Rohdaten:** `AGENT_TEAM/reports/scratch/matcher/gate_fix_dossiers.json`, `gate_fix_sc/`.

## Bekannte Grenzen

- **Schlüssellose Suche ist für einen Batch nicht tragfähig.** Brave-HTML verträgt etwa eine Anfrage pro Minute, DuckDuckgo sperrt schnell. Mit API-Key ist ein Volllauf über 733 Leads möglich (ca. 1.300 Requests).
- **Stichprobe:** 18 Treffer auf 52 Leads, von Hand geprüft, aber nicht unabhängig. Die Prüfung durch `fact-check` steht noch aus.
- **Projektnamen ≠ Firmennamen:** Gründet das Team unter einem anderen Namen, findet das Domain-Raten nichts. Die Suche findet es nur, wenn eine Projektquelle beide Namen nennt und verlinkt. Kurze generische Namen (KM, SIMBA, P2P) bleiben schwierig; unter 4 Zeichen wird nicht geraten.
- **`match_confidence`** ist nur dann der Website-Wert, wenn eine Website gesetzt wurde. Sonst bleibt der Förderkatalog-Wert (Projekt → Förderzeile, bei exakter FKZ 1,0). Das ist kein Beleg für eine Firma.
- **`enrichment_sources`** führt `website_match` nur bei fehlerfreiem Lauf (bestehende `_run`-Regel). Mit blockierter Suche fehlt der Eintrag auch dann, wenn eine Website gesetzt wurde.
- **Wayback und Matcher** können sich widersprechen. Bei m-shunt.com meldet Wayback eine Erfassung von 2023, also vor dem Projekt, und stuft sie als Namensvetter ein, während der Matcher über EXIST und Bremen bestätigt. Beide Befunde stehen im Dossier; eine Auflösung gibt es nicht.
- **SECARA ist nur über Ort + Impressum + Rechtsform bestätigt**, nicht über das Institut. Solche Fälle sind mit 0,95 eher zu hoch bewertet. Wer strenger sein will, setzt `--match-threshold 0.8` oder verlangt Institut bzw. EXIST.
- **Hochschul-Erkennung** ist eine Host-Liste (`ACADEMIC_HOSTS`). Unbekannte Institutsdomains können als „Firma“ durchgehen; auch dann braucht es den Namen prominent und eine Bestätigung.

## Tests

`.venv/bin/python -m pytest -q`: **807 passed** (ganze Suite einschließlich der parallelen Änderungen von `scorer`/`evaluator`), davon 39 in `tests/test_context_website_match.py`:
- Treffer über die Suche, über Domain-Raten, über einen Projektquellen-Link und über die Über-uns-Seite
- Namensvetter (Restaurant, simba.de-Impressum, sensai.io-Themenstämme)
- Parking (siderogain.de-Fixture, Platzhaltertext)
- Hochschul-Projektseite (HZDR)
- kein Treffer; Agentur-Abzug; einstellbare Schwelle; HTTP-Fallback
- Portal, das das Projekt nur erwähnt (campus-start-ups.nrw); Paper-Seite einer Forschungsgruppe (tentris.dice-research.org)
- Parser für Brave-HTML (auch die `/go/`-Umleitung), DuckDuckgo und Brave-API
- API zuerst, Key nicht in URL, Cache oder Evidence; API-Fehlerantwort wird nicht gecacht
- ohne Key Fallback auf HTML; Key aus der Umgebung bzw. aus `.env`, beide Namen (`BRAVE_API_KEY` vor `BRAVE_SEARCH_API_KEY`); `.env` ist git-ignoriert
- Captcha wird nicht gecacht, Circuit Breaker
- Verdrahtung im Engine, `_preserve` der Pipeline, `to_dossier`, CLI-Flags

Kein Test braucht Netz.
