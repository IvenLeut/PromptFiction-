# Runde 1 – Plan und Sinn-Check vorher (`strategist`)

Stand 21.11.2026. Grundlage: Branch `agents/data-quality-fixes` @ 0140411 (Gate 2 bestanden), Daten
`AGENT_TEAM/reports/scratch/gate2/` (52 Online-Leads). Brave-Verbrauch dieser Planung: **15 Anfragen**
(Machbarkeitsprobe). Rohdaten der Probe liegen nur im Scratchpad des Strategen und werden nicht committet.

## Ergebnis in einem Satz

**Gewählte Ebene: Team-Zusammensetzung.** Wir ermitteln, wer im Team ist und welche Rolle jede Person hat
(CEO/CTO/kaufmännisch, Tech oder Business). Quellen sind öffentliche Suchtreffer: Snippets von LinkedIn-Profilen
über die Brave API sowie Presse-, idw- und Hochschul-Teamseiten. **Die Lebensläufe (CVs) bewerten wir nicht.** Die
Probe zeigt, dass Snippets keine Karriere-Historie enthalten, und an die vollen Profile kommt man nur eingeloggt.
Das ist ausgeschlossen.

## 1. Bestandsaufnahme: Was im Score noch neutral oder dünn ist (52 Online-Leads, Gate 2)

| Kriterium | Anteil am Gesamtscore | belegt | davon ohne Proxy | verschiedene Werte | Befund |
|---|---|---|---|---|---|
| team.forscher_match | 0,40·0,30 = **12 %** | 15/52 | 0 | 3 | nur `works_total`-Proxy; setzt einen Namen voraus |
| team.komplementaer | 0,40·0,20 = **8 %** | 52/52 | 12 | **2** | 35× „Forschungsteam, Gründer nicht namentlich belegt“ (Proxy); 12× „Profil-Mix unbekannt“; 0× Mix bekannt |
| team.vorerfahrung | 0,40·0,15 = 6 % | **0/52** | 0 | 1 | Feld `prior_experience` existiert, wird nie befüllt |
| team.vollzeit | 6 % | 52/52 | 52 | **1** | konstant (alle EXIST); trennt nicht |
| team.forschungsumfeld | 8 % | 51/52 | 0 | 5 | trägt die Teamachse allein (Prestige-Proxy, Dresden-Häufung) |
| markt.marktvolumen / wettbewerb | 6,25 % / 1,25 % | 0/52 | – | 1 | neutral |
| markt.traktion | 8,75 % | 2/52 | 2 | 2 | nach dem Müll-Fix (M1) fast leer |
| risiko.ip / regulatorik / tech_reife | 5,25 / 5,25 / 8,75 % | 4 / 9 / 14 | | | dünn, Textklassifikation schwach |

Namen: **35 von 52 Leads haben keine einzige Person**, 5 genau eine, 12 zwei oder mehr. `background`
und `prior_experience` sind bei 0 Profilen gesetzt.

**Größter Hebel für Lead Quality und „Team statt Produkt“:** die Personen selbst. Ohne Namen bleiben
`forscher_match` (12 %), `komplementaer` (8 %) und `vorerfahrung` (6 %) Proxy oder neutral, zusammen 26 % des
Gesamtscores. Außerdem kann die Lead-Karte die HTGF-Frage „Who is behind the project?“ dann nicht beantworten. Die
Teamachse unterscheidet heute fast nur nach Institut. Die Marktachse ist ähnlich leer, aber Marktvolumen und
Wettbewerb lassen sich für Pre-Gründungs-Projekte kaum belegen, und Traktion ist schon nach dem Fix in Gate 2
ausgereizt.

## 2. Machbarkeitsprobe (15 Brave-Anfragen, 8 Leads)

Getestete Leads: Ymolution, SECARA, BotFellows, SideroGaIn, AutonomIQ, VersatileRobotics und Metubiq aus den
Online-Top-15, dazu dentson (ohne Namen und ohne Website). Anfragetypen: 8× `site:linkedin.com/in "<Firma>"`
(einmal mit Kontextwörtern), 3× Name + linkedin, 3× `site:northdata.de "<Name>"`, 1× offene Websuche
„<Firma> Gründer Team <Institut>“. Zusätzlich kostenlos: OpenAlex-Affiliations von 3 Gründern.

### Trifft man die richtige Person?

| Messgröße | Ergebnis |
|---|---|
| Bekannte Impressum-GF in den 6 Leads mit Namen | 13 |
| davon richtiges LinkedIn-Profil gefunden | **9/13 (69 %)**: 5 über die Firmensuche, +2 mit Kontextwörtern, +2 über die Namenssuche |
| Name + linkedin: richtiger Treffer auf Platz 1 | 3/3 |
| Firmensuche: Anteil echter Teammitglieder an allen Treffern | **ca. 15 von 80 (≈ 19 %)**. Der Rest sind Personen, die Firmenposts geliked oder geteilt haben (Posts erscheinen im Profil-Snippet), plus Namensvetter |
| Namensvetter-Totalausfall | SECARA: 10/10 Treffer sind Personen mit dem Nachnamen „Secara“. Erst mit „Aachen recycling“ kamen 2 von 3 GF |
| Weitere Namensvetter | AutonomIQ: US-Firma (Fremont) und ein IT-Produkt gleichen Namens |
| Falsche Zuordnung bei strikter Regel (Firma im Titel „Name – Firma“ bzw. in der Headline **und** Name oder Gründerrolle passt) | **0** |
| Neue Teammitglieder, die bisher fehlten | SideroGaIn **4** (vorher 0; idw/HZDR-Bildunterschrift „Das Siderogain-Team (v.l.n.r. …)“, 2 davon auch auf LinkedIn) · dentson **2** (vorher 0; LinkedIn „– dentson“) · AutonomIQ +1 und Metubiq +1 Mitgründer (aus Post-Snippets „mit meinen Mitgründern …“) · Ymolution +1 Projektmitglied |

### Was liefern die Snippets wirklich? (9 richtig zugeordnete Profile)

| Inhalt | Anteil |
|---|---|
| aktuelle Firma bzw. Headline | 9/9 |
| ausdrückliche Gründerrolle (Co-Founder/CEO/CTO/Mitgründer, auch aus Presse-Snippet) | 3/9 (SECARA-CTO aus der Headline, SECARA-CEO „verantwortlich für die kommerzielle Unternehmensentwicklung“ aus der Presse, AutonomIQ „Mitgründer“) |
| eine Ausbildungsstation („Education: …“) | 7/9, immer nur **eine** Hochschule |
| frühere Stationen | 1/9 (aus einem alten Post: „Group Leader at DLR“) |
| frühere Gründung | **0/9** |
| Industrieerfahrung | **0/9** |
| vollständiger Lebenslauf | **0/9**, nur eingeloggt sichtbar und damit ausgeschlossen |

### Alternativen zu LinkedIn

- **northdata via Brave** (3 Anfragen): 2 Treffer, jeweils nur die aktuelle Firma. Für Erstgründer gibt es keinen
  Hinweis auf frühere Gründungen. Kein Treffer heißt nicht „keine Vorerfahrung“, also kein Signal.
- **OpenAlex-Affiliations** (kostenlos, 3 Personen): nur Forschungseinrichtungen, 0 Industrie-Stationen.
- **Presse, idw und Institutsseiten** (1 Anfrage): die beste Quelle für vollständige Teamlisten samt Rolle
  („hat die Technologie federführend entwickelt“, „Mitgründer und verantwortlich für die kommerzielle Entwicklung“).
  Bei 13 Leads liegt idw-Evidence schon im Dossier, bei 20 Website-Text. Ein Teil lässt sich also ohne neue Anfrage
  aus dem Cache auslesen.

### Nebenbefunde (nicht Teil dieser Runde, für main und Runde 2)

Post-Snippets enthalten Firmensignale:
- SideroGaIn: Eintragung der GmbH im August
- Metubiq: „GmbH i.Gr.“
- dentson: „dentson GmbH … operatives Geschäft“ und **ein öffentlicher Post eines Angel-Investors („why I chose to
  invest in dentson“)**. Dentson steht online auf Rang 12. Vor jeder Demo-Nennung prüfen, ob dentson schon
  finanziert ist.
- Preise: BotFellows, Ymolution; Auszeichnung: AutonomIQ (DTM100)

Die Rohsnippets landen im Cache. Runde 2 kann sie ohne neue Anfrage auswerten.

### Urteil zur Nutzer-Richtung „Team über LinkedIn → CVs bewerten“

- **Teil 1 (Team finden): JA**, mit strikter Zuordnungsregel und ergänzt um Presse, idw und Hochschulseiten.
- **Teil 2 (CVs bewerten): NEIN.** Die Snippets enthalten keine Lebensläufe. `vorerfahrung` bliebe nach der Probe
  bei ≈ 0 % Abdeckung (0/9). Das Ziel ≥ 40 % ist mit erlaubten Mitteln nicht erreichbar. Jeder Versuch würde
  entweder raten oder eingeloggte Seiten brauchen.

## 3. Die Ebene dieser Runde

**Ebene:** Team-Zusammensetzung. Für jeden Lead: namentliche Teammitglieder mit Rolle, Hintergrund (`tech`,
`business`, `beides`), Ausbildung (eine Hochschule) und Beleg-URL. Gefüllt werden die vorhandenen Felder
`FounderProfile.role/background/institution/source_url`; `models.py` bleibt unverändert. Neue Personen laufen danach
durch den bestehenden OpenAlex-Abgleich.

**Hypothese:** Wenn wir wissen, wer im Team ist und wer davon Business- bzw. Tech-Verantwortung trägt, steigt die
**Lead Quality**, weil
1. `komplementaer` (8 % Gesamt) vom Förder-Proxy zum Fakt wird. Teams mit Business-Co-Founder werden dann von
   reinen Forscherteams unterschieden (1,0 vs. 0,5, bis ±3–4 Gesamtpunkte bei einer Spanne von 53–68);
2. die 35 namenlosen Leads überhaupt Personen bekommen. Damit wird `forscher_match` (12 %) messbar;
3. jede Lead-Karte und der Best Find die HTGF-Frage „Who is behind the project?“ mit Quellen beantworten
   („Dr. F. Nagel, CEO, kaufmännisch · Dr. M. Lehnertz, CTO · …“).

**Jurykriterien:**
- primär **Lead Quality** und der Tipp „Team statt Produkt“;
- sekundär **Creativity of Signals**: Teamliste aus idw-Bildunterschriften und Post-Snippets statt Datenbank;
- Scalability bleibt gewahrt: 1–3 Anfragen je Lead, gecacht.

### Erfolgskriterien (alle messbar auf den 52 Gate-Leads, Stichtag 2026-11-21)

| # | Kriterium | Ist | Ziel |
|---|---|---|---|
| K1 | Leads mit ≥ 1 namentlich belegter Person (mit URL) | 17/52 (33 %) | **≥ 30/52 (58 %)** |
| K2 | `komplementaer` belegt, ohne Proxy, mit bekanntem Profil-Mix (`mehrere_mit_mix` oder `mehrere_ohne_business`) | 0/52 | **≥ 10/52** |
| K3 | Precision der neuen Daten, Faktencheck einer Zufallsstichprobe von 20 Personen (Sonnet, im Netz) | – | **≥ 90 %** richtige Zuordnung Person ↔ Firma und **≥ 90 %** richtige Rolle bzw. Hintergrund; 0 private Kontaktdaten; 0 Personen, die nur geliked oder geteilt haben |
| K4 | Keine Verschlechterung | Spearman 0,42; Ymolution 5, SECARA 14 | Spearman **≥ 0,40** (30 unbestätigte Agent-Labels, Zirkularität dazuschreiben). Zusätzlich Spearman getrennt für Leads ohne Website berichten. Ymolution bleibt in den Top 10. Die Best-Find-Karte zeigt das Team mit Rollen aus Quellen |
| K5 | Technik | 807 passed | Suite grün, zwei Läufe byte-identisch (Kontext aus dem Cache, Scoring), Schema 0 Fehler |
| K6 | Kosten | – | **≤ 180 Brave-Anfragen** in der Runde, gezählt und im Log |

ÜBERNEHMEN nur, wenn K1, K3 und K4 erfüllt sind. K2 darf knapp verfehlt werden, wenn K3 hält; dann im Log
begründen. VERWERFEN, wenn K3 nach einer NACHBESSERN-Runde unter 90 % bleibt.

**Pilot-Gate (spart Budget):** Coder A läuft zuerst auf 10 Leads, davon 6 ohne Namen. Gewinnen weniger als 4 von 10
neue Personen, oder liegt die Selbstprüfung von 10 Zuordnungen unter 9 richtigen, wird abgebrochen und an den
Strategen berichtet. Erst danach folgt der Lauf über alle 52 Leads.

### Kosten

- Brave: 1 Firmensuche je Lead (`site:linkedin.com/in "<Firma>"` plus Kontextwort, wenn der Name generisch, kurz
  oder ein häufiger Nachname ist), 1 offene Team-Suche je Lead („<Firma>“ Gründer OR Gründerteam OR founders
  <Institut>), höchstens 1 Namenssuche je bekanntem, noch nicht gefundenem GF (Deckel 2 je Lead).
- Erwartet 110–160 Anfragen für 52 Leads, Deckel 180. Danach bleiben ≈ 1.650.
- OpenAlex für neue Personen: kostenlos, höchstens 3 je Lead.
- Laufzeit: wenige Minuten, Wiederholläufe aus dem Cache.

### Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| **Liker und Reposter** (≈ 80 % der Firmensuch-Treffer) | Eine Person zählt nur, wenn (a) der Profiltitel „Name – <Firma>“ lautet oder die Headline die Firma nennt **und** (b) sie als GF bekannt ist oder eine Gründerrolle trägt (Founder, Co-Founder, Gründer, Mitgründer, CEO, CTO, COO, CFO, Geschäftsführer). Bei Leads ohne bekannte Namen gelten Personen mit aktueller Firma = Lead, aber ohne Gründerrolle, als „Teammitglied“: Sie zählen für Teamgröße und Hintergrund, nicht als Gründer. Erwähnungen nur im Post-Text werden nie als Profil übernommen; Namen aus Post-Text nur mit Rolle und als „laut Post“ |
| **Namensvetter** (SECARA, AutonomIQ) | Firmen-Regex wie in `context/dbsearch.py`. Bestätigung über Ort, Institut, Website-Domain, Produktwort oder EXIST. Ohne Bestätigung landet der Treffer in `errors` und wird nicht übernommen |
| **Abwesenheit als Malus** | Kein LinkedIn-Treffer bedeutet nie „solo“ oder „ohne Business“. `mehrere_ohne_business` nur, wenn alle Impressum- bzw. Register-GF einen belegten Tech-Hintergrund haben. Sonst bleibt der Mix unbekannt |
| **Zirkularität mit den Agent-Labels** (die Labels entstanden aus Websuche; LinkedIn-Präsenz korreliert mit Web-Präsenz) | Spearman nur als „nicht schlechter“-Kriterium (K4), nicht als Erfolgsbeleg. Erfolg misst K1–K3 (Abdeckung + Faktencheck). Spearman getrennt für Leads mit und ohne Website berichten |
| **Rollenwörter falsch gelesen** („CEO“ sagt nichts über Business) | `business` nur bei kaufmännisch/commercial/Business Development/CFO/COO/CBO/Sales/Vertrieb/Marketing oder einer Wirtschafts-Ausbildung (BWL, MBA, Management, Economics). Wirtschaftsingenieur → `beides`. `tech` bei CTO/Engineer/Entwicklung oder einem MINT- bzw. Medizinstudium; ein OpenAlex-Profil mit ≥ 5 Arbeiten zählt ebenfalls. CEO allein → `None` |
| **Datenschutz / LinkedIn-AGB** | Keine HTTP-Abrufe von linkedin.com: nur Titel und Snippet aus der Brave-Antwort. Gespeichert werden nur Name, Rolle, aktuelle Firma, eine Hochschule und die Profil-URL als Beleg. Nicht gespeichert: Ort, Kontaktzahl, Foto, E-Mail, Telefon. Scratch wird nicht committet; Testfixtures pseudonymisiert. Ob Klarnamen ins Repo dürfen, entscheidet weiter das Team (Gate-Punkt 6) |
| Verzerrung zugunsten LinkedIn-aktiver Gründer | Presse-, idw- und Institutsseiten als zweite Quelle; Abwesenheit bleibt neutral (siehe oben) |

## 4. Bauauftrag

### Coder A (`matcher`, Opus): nur `context/` und eigene Tests

Dateien: neu `context/team.py`, Anbindung in `context/engine.py`, Doku `context/ENRICHMENT.md`. Tests in
`tests/test_context_team.py` mit Fixtures `tests/fixtures/team/*.json` (Brave-Antworten, Namen pseudonymisiert).

1. **Ohne neue Anfrage zuerst:** Teamlisten aus vorhandenen Texten lesen (idw-Evidence, Projektseite,
   `website_text`, Team- und Über-uns-Seiten aus dem Cache). Muster: „Das <Firma>-Team (v.l.n.r. …)“,
   „Gründerteam: …“, „founders: …“, „<Name>, Mitgründer und …“, „<Name> (CEO)“.
2. `team_lookup(name, *, website, location, institution, known_names, website_text, cache, search)`:
   - Anfragen wie unter „Kosten“; Suche über `website_match.web_search(..., engines=("brave_api",))` und den Cache
     (Schlüssel versioniert, z. B. `team:v1`). Wirft nie eine Exception, ohne API-Key passiert nichts.
   - Zuordnungsregeln wie in der Risikotabelle (Titelformat, Firmen-Regex, Namensvetter-Bestätigung, Gründerrolle
     oder bekannter Name).
   - Rolle und Hintergrund nach der Wortliste oben, Ausbildung nur aus „Education: …“.
   - Ergebnis als `founder_profiles` mit `role` (z. B. „CTO & Co-Founder (LinkedIn)“, „Teammitglied (LinkedIn)“,
     „Gründer (Presse)“), `background`, `institution`, `source_url` = Profil- bzw. Presse-URL, `match_confidence`.
   - Bestehende Impressum-Profile werden über den Namen angereichert, nicht dupliziert.
   - Neue Personen (höchstens 3 je Lead) laufen durch `openalex.author_lookup`.
   - Zähler für Brave-Anfragen ins Log bzw. `enrichment_errors`.
3. `prior_experience` wird in dieser Runde **nicht** gesetzt.
4. **Tests (Pflicht):**
   - Liker-Profil mit Firmenpost im Snippet → verworfen
   - Namensvetter „Secara“ als Nachname → verworfen; mit Ortsbestätigung → übernommen
   - US-Firma gleichen Namens → verworfen
   - „CTO & Co-Founder at X“ → tech, Gründer
   - „verantwortlich für die kommerzielle Unternehmensentwicklung“ → business
   - CEO allein → `background None`
   - kein Treffer → keine Profile, kein „solo“
   - idw-Bildunterschrift → 4 Personen
   - keine Ort-, Kontakt- oder E-Mail-Felder im Ergebnis
   - Cache-Determinismus
   - ohne API-Key: no-op
5. **Live:** erst das Pilot-Gate (10 Leads), dann alle 52 Leads. Ausgabe nach `AGENT_TEAM/reports/scratch/round1/`.

### Coder B (`scorer`, Opus): nur `scoring/` und `evaluation/engine.py` und eigene Tests

1. `evaluation/engine.py::to_dossier`: Herkunft je Person übernehmen (`herkunft`: impressum / linkedin / presse) und
   unterscheiden, ob jemand Gründer oder Teammitglied ist. `hintergrund` wird schon durchgereicht.
2. `scoring/engine.py::k_komplementaer`:
   - Gründer aus LinkedIn bzw. Presse (mit Gründerrolle) zählen wie Impressum-GF. Teammitglieder ohne Gründerrolle
     zählen nur für den Mix, nicht für n.
   - `nur_impressum`-Sonderfall erweitern: Eine Person mit Gründerrolle, von der die Presse sagt „einer von drei
     Gründern“, ist kein Solo-Gründer.
   - `mehrere_ohne_business` nur bei vollständig belegtem Tech-Hintergrund aller GF.
   - Aussage mit Namen und Rollen, Beleg-URL der Person mit dem Business-Profil.
3. Texte: Die Investmenthypothese bzw. `staerken` nennt einen belegten Business-Co-Founder. Ein fehlendes
   Business-Profil kommt nur dann als offener Punkt („Business-Profil im Team nicht belegt – prüfen“), wenn es
   belegt fehlt.
4. **Nebenher n2** (`evaluation/engine.py:233-235`): `in_databases_quelle` nur aus Evidence mit positivem Befund.
   Widersprechen sich Brave (kein Profil) und Wayback (Slug), entsteht ein offener Punkt „Namensvetter prüfen“.
   Begründung: Die Earliness-Aussage im Pitch muss stimmen, und die Datei wird ohnehin angefasst.
5. **Nebenher n1** (`scoring/engine.py`, VP aus `website_text`): Menüzeilen und CTA-Sätze verwerfen, Sätze mit
   „we/our/wir/unser“ + Verb bevorzugen. Höchstens ein halber Tag; reicht die Zeit nicht, entfällt n1.
6. Keine Gewichtsänderung (0,40/0,25/0,35 wartet aufs Team), `models.py` unverändert, `scoring_config.yaml` nur
   ergänzen (z. B. Rollen-Wortlisten unter `katalog`), keine bestehenden Werte ändern.
7. **Tests (Pflicht):**
   - LinkedIn-Gründer + Impressum-GF ergeben zusammen n ohne Duplikat
   - Mix aus CEO (business, belegt) + CTO → `mehrere_mit_mix`
   - Mix unbekannt bleibt 0,6
   - kein Malus bei fehlenden Daten
   - Teammitglied zählt nicht für n
   - n2-Fall HydroPURE (positive Aussage nur mit Profil-URL)
   - n1-Fälle iNSyT, Metubiq, SpinMagIC
   - Determinismus und Schema
   - `SCORING.md` nachführen

**Reihenfolge:** A und B arbeiten parallel gegen ein vorab vereinbartes Profilformat (Rollen-Suffix und Herkunft
wie oben). B testet mit Fixtures, die Integration erfolgt, sobald A die Pilot-Dossiers hat. Messung danach durch die
Prüfung (Sonnet): `coverage.py` (K1/K2), `precision.py` (K4), Faktencheck von 20 Personen (K3).

## 5. Was ausdrücklich NICHT gebaut wird

- **Keine CV- bzw. Vorerfahrungs-Bewertung**: kein Setzen von `prior_experience`, keine `vorerfahrung`-Logik, kein
  Abruf von linkedin.com-Seiten, kein Login, kein Scraping über Dritte wie RocketReach oder Yasni.
- Keine northdata-Personensuche für frühere Gründungen (Probe: kein Signal bei Erstgründern).
- Keine Auswertung der Firmensignale aus Post-Snippets (Gründung, Investor, Preise). Das ist ein Kandidat für
  Runde 2; die Rohdaten liegen dann im Cache.
- Keine Gewichts- oder Achsenänderung, keine Änderung an `models.py`, kein Longlist-Lauf über 733 Leads (M4 bleibt
  eine Team-Entscheidung).
- **n3** (Partner-Splitter) wird **nicht** mitgenommen: Im aktuellen Lauf hat er keine Wirkung, weil nur 2 Partner
  belegt sind, und er liegt in der Datei des Coders A, der sich auf die Teamebene konzentrieren soll.

## 6. Stoppregel

Nicht ausgelöst. Die Ebene hat einen klaren, messbaren Nutzen: 35 namenlose Leads, `komplementaer` mit nur 2
Werten, eine direkte HTGF-Jury-Frage. Das Budget reicht (≈ 1.815 nach dieser Probe). Ausdrücklich verworfen ist dagegen
die Teilrichtung „CVs bewerten“: Sie würde nur Daten anhäufen, die nicht da sind.
