# Runde 1 – Coder A (`matcher`): Team-Zusammensetzung

Stand 21.11.2026. Nichts committet.

**Status: Pilot und Volllauf (52 Leads) gelaufen.**
- Der erste Pilotdurchlauf hat das Abbruchkriterium gerissen (10 von 12 Zuordnungen richtig). Nach Fix und zweitem
  Durchlauf hat der Lead den Volllauf freigegeben.
- Ergebnis Volllauf:
  - **K1 verfehlt:** 24/52, Ziel 30.
  - **K2 verfehlt:** 5/52, Ziel 10, und alle fünf sind „ohne Business“, keiner hat einen belegten Mix.
  - **K4 gehalten:** Spearman 0,40.
  - **K6:** 100 von 180 Brave-Anfragen.
- Details in den Abschnitten unten.

## Gebaut

**`context/team.py` (neu)**, Einstieg `team_lookup(name, *, website, location, institution, known_names, texts, cache, search)`.

1. **Ohne neue Anfrage:** Personen aus Texten, die schon vorliegen (idw-Artikel, Projektseiten aus dem Cache,
   Website-Text). Erkannte Muster:
   - Bildunterschrift „Das <Firma>-Team (v.l.n.r. …)“
   - Teamliste zwischen Gedankenstrichen „Die <Firma> – A (CEO), B, C und D –“
   - „Gründerteam: …“ / „founders …“
   - Rollensätze: „<Name>, Mitgründer und verantwortlich für …“, „<Name> (CTO)“, „<Name>, der … als CEO von
     <Firma> übernimmt“
   - Zuordnungsregeln für Rollensätze:
     - Sie gelten nur in Sätzen, die die Firma nennen, oder für Personen, die in derselben Quelle in einer Teamliste
       stehen.
     - Eine Rolle bei einer anderen Organisation zählt nicht: „Gründerin Bioexotec“, „CEO der Transfer GmbH“.
2. **Brave-API, höchstens 3 Anfragen je Lead:**
   - **LinkedIn-Firmensuche:** `site:linkedin.com/in "<Firma>"`; bei Namen mit höchstens 6 Zeichen kommt der Ort
     dazu.
     - Gezählt wird nur, wessen Profiltitel „Name - <Firma>“ lautet **und** wer entweder bekannt ist (Impressum)
       oder in der Headline eine Gründerrolle trägt.
     - Unbekannte Personen brauchen zusätzlich eine Bestätigung: Ort, deutsches Bundesland, deutsche Hochschule
       unter „Education:“, das Institut, EXIST oder die Website-Domain.
     - Ohne bekannte Namen werden bestätigte Mitarbeitende zu „Teammitglied“.
     - Liker, Reposter und Profile mit anderem Arbeitgeber werden verworfen; Namensvetter landen in `errors`.
   - **Offene Teamsuche:** `"<Firma>" (Gründer OR Gründerteam OR …) <Institut>`, nur wenn noch kein Gründer bekannt
     ist. Die Snippets werden mit den Textmustern aus Schritt 1 gelesen.
   - **Namenssuche:** `site:linkedin.com/in "<GF>" "<Firma>"` für höchstens einen bekannten GF, der noch fehlt.
3. **Rolle und Hintergrund:**
   - Format wie mit `scorer` vereinbart:
     - Rolle als „<Rolle> (Impressum|LinkedIn|Presse|Website)“; bei mehreren Quellen mit „; “ verbunden.
     - „Teammitglied (…)“ zählt nicht für n.
     - „Alleingründer (…)“ nur, wenn eine Quelle das ausdrücklich sagt.
   - `background` kommt nur aus Rollen- oder Ausbildungswörtern. CEO allein ergibt `None`;
     „kaufmännisch/kommerziell/commercial/BWL/MBA …“ ergibt business; „CTO/Engineering/Robotik/Physik …“ ergibt
     tech.
   - **OpenAlex-Fallback:** ab 5 Arbeiten tech, mit eigener Evidence „background tech aus OpenAlex“.
   - `prior_experience` wird nicht gesetzt.
4. **Datenschutz:**
   - Gespeichert werden nur Name, Rolle, Hintergrund, eine Hochschule und die Profil- bzw. Presse-URL.
   - Nie gespeichert: Ort, Kontaktzahl, E-Mail, Telefon, Post-Texte.
   - Es gibt keine HTTP-Abrufe von linkedin.com.
   - Pilotausgabe geprüft: 0 Ortsangaben, 0 Kontaktzahlen, 0 E-Mails in Team-Evidence und Profilen.
5. **Cache und Budget:**
   - Cache: `team:v2:` je Lead (nur vollständige Läufe) und `context.http` je Anfrage.
   - Budget: `MAX_RUN_REQUESTS = 170` neue Anfragen je Prozess, danach keine neuen; der Zähler steht in `team.STATS`.

**Anbindung `context/engine.py`:**
- Neuer Lookup `"team"` in `default_lookups`.
- `_run_team` läuft nach Impressum, idw und Impressum-GF.
  - Bekannte Namen: Schritt-1-Gründer, sonst Impressum-GF.
  - Texte: idw, Website-Seiten der gematchten Website und Projektseiten (`project_page`-Evidence, über den
    Seitencache).
- `_team_profiles` mergt über den Namen in die Impressum-Profile, ohne Duplikate.
  - Bei bestehender Rolle wird nur eine Nicht-„Teammitglied“-Rolle angehängt.
  - `background` und `institution` werden ergänzt, falls sie fehlen.
- Neue Personen (höchstens 3 je Lead) laufen durch `openalex.author_lookup`, ohne Feldbegriffe.

**Tests:** `tests/test_context_team.py`, 15 Tests mit pseudonymisierten Fixtures `tests/fixtures/team/*.json`.
- Liker (Firmenpost im Snippet) wird verworfen.
- Namensvetter: Nachname „Secara“ und „Secara Consulting“ werden verworfen, mit Ort bestätigt wird übernommen;
  eine US-Firma gleichen Namens wird verworfen.
- „CTO & Co-Founder“ ergibt tech/Gründer; „verantwortlich für die kommerzielle Unternehmensentwicklung“ ergibt
  business; CEO allein ergibt `None`.
- Kein Treffer ergibt keine Profile und kein „solo“; „Alleingründer“ nur bei ausdrücklicher Aussage.
- Bildunterschrift ergibt 4 Personen (der CEO des Transferbüros außerhalb der Klammer zählt nicht); Teamliste mit
  Gedankenstrichen; Gewinnerliste mit Gründern anderer Firmen (Pilot-Fehler).
- Logozeile „Founded by:“ ergibt keine Personen.
- Datenschutz: kein Ort, Kontakt oder E-Mail.
- Cache-Determinismus; ohne API-Key passiert nichts.
- Engine-Merge mit Impressum plus OpenAlex für neue Personen.

Ganze Suite: 831 Tests, alle grün. Ein Lauf zeigte einen Fehlschlag in `tests/test_scoring.py`, während `scorer`
parallel editierte; beim erneuten Lauf grün.

## Pilot (10 Gate-Leads: 6 ohne Namen, 4 mit Namen)

Eingabe: `AGENT_TEAM/reports/scratch/loop1/pilot_input.json`, Ausgabe `pilot_dossiers.json` im selben Ordner.
- **Ohne Namen:** Aiina-Robotics, DataLingua, SoreAlert, dentson, SpinMagIC, SideroGaIn
- **Mit Namen:** SECARA, AutonomIQ, Ymolution, BotFellows

### Durchlauf 1 (Regel-Stand v1) – Abbruchkriterium gerissen

Neue Personen bei 5 von 10 Leads, aber **2 von 12 neuen Zuordnungen falsch** (83 %):
- **Fehler:** Aiina-Robotics bekam „Marie-Nicole Theodoraki (Gründerin Bioexotec)“ und „Andreas Hettmann (Gründer
  ReduCO2“.
  - **Ursache:** Eine Gewinnerliste des TUM IdeAward nennt in *einem* Satz Gründer mehrerer Firmen, und der Satz
    enthält auch „Aiina Robotics“.
  - **Fix:** Folgt dem Rollenwort ein anderer Eigenname als die Firma, wird die Person nicht übernommen.
  - Regressionstest `test_founders_of_other_companies_in_a_winner_list_are_dropped`.
- **Zweiter Befund (Recall):** Für die LinkedIn-Suche wurde „BotFellows“ in „Bot Fellows“ getrennt und fand dann
  andere Personen. LinkedIn-Anfragen nutzen jetzt die Schreibweise aus dem Katalog.
- **Dritter Befund (Recall):** Die idw-Teamliste „Die Botfellows – Dr.-Ing. … (CEO), …, … und … –“ wurde nicht
  gelesen. Neues Muster für Teamlisten zwischen Gedankenstrichen, Test `test_dash_enclosed_team_list`.

### Durchlauf 2 (Regel-Stand v2, gleiche 10 Leads) – beide Kriterien erfüllt

| Kriterium | Schwelle | Ergebnis |
|---|---|---|
| Leads mit neuen Personen | ≥ 4/10 | **5/10**: Aiina-Robotics +1, dentson +2, SpinMagIC +2, BotFellows +1, SideroGaIn +4 |
| richtige Zuordnung (Selbstprüfung) | ≥ 9/10 | **10/10** neue Personen (Prüfung siehe unten) |

| Lead | Person (neu) | Rolle | Hintergrund | Beleg | Prüfung |
|---|---|---|---|---|---|
| Aiina-Robotics | L.-M. Pätzmann | Gründerin (Presse) | tech (OpenAlex) | zeitenvogel.de, TUM IdeAward 2024 („Gründerin Aiina Robotics“) | richtig |
| dentson | A. Ben Achour | Teammitglied (LinkedIn) | tech | LinkedIn-Titel „– dentson“, Ausbildung TU Dresden | richtig (aktuelle Firma) |
| dentson | L. Hellmund | Teammitglied (LinkedIn) | – | LinkedIn-Titel „– dentson“, Ausbildung TU Dresden | richtig (aktuelle Firma) |
| SpinMagIC | M. Segantini | Teammitglied (LinkedIn) | tech | LinkedIn-Titel „– SpinMagIC“ | richtig |
| SpinMagIC | A. Chu | Teammitglied (LinkedIn) | tech | LinkedIn-Titel „– SpinMagIC“, Uni-Stuttgart-Meldung nennt ihn im Gründerteam | richtig |
| BotFellows | J. Halim | Co-Founder & Head of Engineering (LinkedIn) | tech | LinkedIn-Headline; idw-Teamliste | richtig |
| SideroGaIn | R. Jain | CEO (Presse) | tech | idw/HZDR („übernimmt als CEO“) | richtig |
| SideroGaIn | P. Boelens, A. Ghosh, J. Engelhardt | Teammitglied (Presse) | tech / tech / – | HZDR-Bildunterschrift „The Siderogain team (f.l.t.r. …)“ | richtig |

**Angereichert:** BotFellows M. Bdiwi „Geschäftsführung (Impressum); CEO (Presse)“ aus der idw-Teamliste.

**Ohne Wirkung:**
- DataLingua und SoreAlert: keine Person mit Lead als aktueller Firma, kein Presse-Treffer.
- SECARA: Die LinkedIn-Treffer sind Namensvetter, F. Nagel ist nicht gefunden.
- AutonomIQ: US-Namensvetter verworfen.
- Ymolution: ein Treffer ohne Bezug verworfen.

**Offen für den Volllauf:**
- Bei Leads mit bekannten GF bringt die Namenssuche nach nur einem fehlenden GF wenig.
- Business-Profile sind selten: Im Pilot ist kein einziges `business` belegt. K2 (`mehrere_mit_mix` ≥ 10) wird nach
  diesem Stand voraussichtlich verfehlt.
- Die Rollen der Impressum-GF bleiben ohne Hintergrund, wenn weder LinkedIn noch Presse sie nennen.

### Vorläufige K1/K2 (nur 10 Pilot-Leads)

- **K1** (≥ 1 namentlich belegte Person mit URL): vorher 4/10 (SECARA, AutonomIQ, Ymolution, BotFellows, alle über
  Impressum-GF), nachher **8/10**: neu Aiina-Robotics, dentson, SpinMagIC und SideroGaIn. Ohne Person bleiben
  DataLingua und SoreAlert. Hochgerechnet auf die 35 namenlosen Gate-Leads: 4 von 6 Pilot-Leads ohne Namen haben
  jetzt Personen. Damit ist K1 ≥ 30/52 erreichbar, aber nicht sicher.
- **K2:** hochgerechnet unwahrscheinlich. Kein Lead im Pilot hat einen belegten Business-Hintergrund; die
  Mischung ist bei 0/10 bekannt. Die Rollen (CEO, Co-Founder & Head of Engineering) reichen nach der vereinbarten
  Wortliste für tech, aber nicht für business.

**Integration `scorer` (Rückmeldung):** Die Pilot-Dossiers sind eingebunden und mit `AGENT_TEAM/reports/scratch/scorer/loop1/messung.py` gemessen.

| Lead | Ergebnis |
|---|---|
| BotFellows | 4 Gründer; Mix unbekannt, weil P. Eichler ohne Hintergrund ist |
| SideroGaIn | n = 1 (CEO), dazu 3 Teammitglieder; nicht solo |
| dentson, SpinMagIC | nur Teammitglieder, n = 0 |
| Ymolution | beide GF tech über OpenAlex → „ohne Business“ + Prüfpunkt, das einzige K2-Ergebnis im Pilot |

K2 hängt also an Belegen für Business-Hintergrund. Die vereinbarte Wortliste: kaufmännisch, CFO/COO, BWL/MBA in Rolle oder Ausbildung.

## Volllauf (alle 52 Gate-Leads)

- **Lauf:** `python -m context AGENT_TEAM/reports/scratch/eval/online/input.json …/loop1/full_dossiers.json --limit 52`
  mit Brave-API, danach `python -m scoring … --out …/loop1/sc --stichtag 2026-11-21` und
  `AGENT_TEAM/reports/scratch/scorer/loop1/messung.py`.
- **Vergleich:** dieselben Gate-2-Dossiers (`scratch/gate2/dossiers.json`), mit dem aktuellen Scorer neu bewertet
  (`loop1/sc_gate2_now`).
- **Zwei Regeln nach dem ersten Volllauf nachgeschärft** (jeweils Regressionstest, Neulauf ganz aus dem Cache, 0 neue
  Anfragen):
  1. Seitenbeschriftungen („Legal Notice“) sind keine Namen. Kontaktdaten-Broker wie RocketReach zählen nie als
     Quelle; ein Snippet hatte „Legal Notice“ als Geschäftsführer von PoLightFilters und einen CEO von Linque
     geliefert.
  2. Für Namen unter 4 Zeichen (KM, P2P, TSS) gibt es keine Personensuche, weil sie nur Namensvetter liefert
     (Volllauf: „… - KM“, „… - P2P“).

  **Wichtig für den Faktencheck:** Beide Fixes entstanden auf Volllauf-Daten. Die Personenliste unten ist der Stand
  *nach* diesen Fixes.

| Kriterium | vorher (Gate 2, aktueller Scorer) | nachher | Ziel | erfüllt |
|---|---|---|---|---|
| **K1** Leads mit ≥ 1 namentlich belegter Person (mit URL) | 17/52 | **24/52** (46 %) | ≥ 30/52 | **nein** |
| davon Pilot-Leads / neue 42 Leads | 4/10 → 8/10 | 13/42 → **16/42** | | |
| **K2** `komplementaer` belegt, ohne Proxy, Mix bekannt | 0/52 | **5/52** (iNSyT, Ymolution, Metubiq, BEHtec, LayerPerformance) | ≥ 10/52 | **nein** |
| **K4** Spearman gesamt (30 unbestätigte Agent-Labels, zirkulär) | 0,42 | **0,40** | ≥ 0,40 | knapp ja |
| K4 Spearman ohne / mit Website | 0,26 / 0,32 | 0,21 / 0,32 | berichten | – |
| K4 Ymolution / SECARA | Rang 5 / 14 | Rang **5** / 15 | Ymolution in den Top 10 | ja |
| K5 Suite / Determinismus | | 832 passed; zwei Läufe aus dem Cache ergeben **byte-identische** `scores.json`. Die Dossiers unterscheiden sich nur in `context_v2`, und zwar schon vorher (vorhandene Zeit- bzw. ID-Felder, nicht von dieser Runde) | | ja |
| K6 Brave | | **100** (siehe unten) | ≤ 180 | ja |

**Ehrlich zu K2:**
- Alle 5 Treffer sind `mehrere_ohne_business`, also alle GF tech. Der Tech-Hintergrund stammt überwiegend aus dem
  OpenAlex-Fallback (≥ 5 Arbeiten).
- `mehrere_mit_mix` kommt **0-mal** vor. In allen 52 Leads ist kein einziger `business`-Hintergrund belegt:
  - Rollen in den Snippets sind „CEO“, „Co-Founder & Head of Engineering“ oder „Mitgründer“, und CEO allein zählt
    nicht.
  - Ausbildungsangaben nennen nur die Hochschule, nicht das Fach.
  - Die vereinbarte Business-Wortliste (kaufmännisch, CFO/COO, BWL/MBA …) trifft in keinem Snippet.
- K2 habe ich bewusst nicht hochgezogen. K2 ist bei 8 Leads offen („Profil-Mix unbekannt“), z. B. SECARA, AutonomIQ,
  Smarobix, Tentris, BotFellows und mechIC: Ein GF hat dort keinen belegten Hintergrund. Der Plan-Probe nach wäre der
  SECARA-CEO laut Presse kaufmännisch („verantwortlich für die kommerzielle Unternehmensentwicklung“). Diese Quelle
  kam im Lauf aber nicht an, weil die offene Teamsuche nur ohne bekannten Gründer läuft.

**Warum K1 verfehlt wird** (Diagnose der 28 Leads ohne Person, aus dem Cache, ohne neue Anfragen):

| Ursache | Leads |
|---|---|
| LinkedIn-Treffer sind nur Liker oder Leute mit anderem Arbeitgeber | 15 |
| Profiltitel „Name - <Firma>“ vorhanden, aber unbestätigt (Post-Snippet ohne Ort, Hochschule oder Domain) → bewusst verworfen | 6: SoreAlert, PoLightFilters, MillionMolecules, MimoSense; dazu SIMBA und HydroPURE, die echte Namensvetter sind („Simba Computer Systeme“, „HydroPure Solutions“) |
| keine LinkedIn-Treffer | 4 |
| Name zu kurz, keine Suche | 3 (KM, EXIST_P2P, TSS) |

**Möglicher Hebel für NACHBESSERN:** Unbestätigte Personen übernehmen, wenn der Titel *genau* den Leadnamen trägt
(nicht „HydroPure Solutions“) und eine gematchte Website existiert.
- Gewinn: wohl +2 bis +4 Leads (MillionMolecules, MimoSense; ohne Website auch SoreAlert und PoLightFilters).
- Selbst damit läge K1 bei etwa 26–28, unter 30.
- Diese Lockerung kostet Precision. Ich habe sie deshalb **nicht** eingebaut.

**Neu zugeordnete Personen der 42 Nicht-Pilot-Leads:** 5 Personen in 3 Leads, Liste mit Belegen in
`AGENT_TEAM/reports/loop/round-1-persons.json` für den unabhängigen Faktencheck.
- SUNEO: D. B. Ritzer (Teammitglied, LinkedIn), H. Eggers (Gründer, Presse, startbase.de/KIT-Gründerschmiede)
- Linque: P. Pertsch (Teammitglied, LinkedIn)
- mechIC: P. Schmitt (Mitgründer, Presse, news.rub.de), S. Wittemeier (Gründer, Presse, campus-start-ups.nrw)

Die Impressum-Personen der neuen Leads tauchen in der Liste nur auf, wenn LinkedIn oder Presse sie mit einer Rolle
angereichert hat. Das war in diesem Lauf bei keiner der Fall: Ihre LinkedIn-Treffer tragen keine Gründerrolle in der
Headline, und Rollen ohne Gründerbezug hängen wir an bestehende Impressum-Rollen nicht an.

Verteilung über alle 52: Herkunft der Rollen 34× Impressum, 11× Presse, 10× LinkedIn. Hintergrund 39× tech,
14× unbekannt, **0× business**.

## Brave-Verbrauch der Runde

| Schritt | neue Anfragen |
|---|---|
| Format- und Parser-Probe (LinkedIn-Firmensuche BotFellows) | 1 |
| Pilot Durchlauf 1 | 19 |
| Pilot Durchlauf 2 (geänderte Anfragen, Rest aus dem Cache) | 2 |
| Volllauf 52 Leads (Pilot-Leads aus dem Cache) | 78 |
| Neulauf nach den Volllauf-Fixes, Determinismus-Läufe, Diagnose | 0 (alles Cache) |
| **Summe Runde 1** | **100 von 180** |

## Geänderte Dateien

- `context/team.py` (neu)
- `context/engine.py`: Lookup `team`, `_run_team`, `_team_texts`, `_team_profiles`, `_openalex_background`
- `tests/test_context_team.py` (neu)
- `tests/fixtures/team/*.json` (3, pseudonymisiert)
- `AGENT_TEAM/reports/scratch/loop1/` (Pilot-Ein- und Ausgabe)
- dieser Bericht

- `context/ENRICHMENT.md`: Modulzeile `context/team.py` und Grenzen-Zeile
- `AGENT_TEAM/reports/loop/round-1-persons.json` (Faktencheck-Liste; Klarnamen, nicht committen ohne Team-Entscheidung)
- `AGENT_TEAM/reports/scratch/loop1/` (`full_dossiers.json`, `sc/`, `sc_gate2_now/`)
