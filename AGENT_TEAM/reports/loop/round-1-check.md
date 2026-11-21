# Runde 1 – Prüfbericht (`loop-check`)

Stand 21.11.2026, Basis 0140411. Kein Produktcode geändert.

## 1. Tests und Sanity

| Prüfung | Ergebnis |
|---|---|
| Suite, zwei Läufe | 832 passed, 832 passed |
| Scoring `full_dossiers.json`, Stichtag 2026-11-21, zwei Läufe | byte-identisch, und identisch mit `scratch/loop1/sc/scores.json` |
| Schema | Array von 52 Zeilen gegen `scores.schema.json` valide |
| Evidence ohne URL und ohne Neutral-Markierung | 0 |
| `run_pipeline(use_mock=True)` | läuft (Rückgabe `AnalysisRun`) |
| 733er-Offline-Lauf | kein laufender Prozess; nicht neu ausgeführt, Coder-B-Angabe (byte-identisch) nicht unabhängig bestätigt |
| K1 | 24/52 mit Profil (inkl. Teammitglied) bzw. 21/52 mit `name_gruender`; Ziel 30 verfehlt |
| K2 (messung.py) | 5/52 (iNSyT, Ymolution, Metubiq, BEHtec, LayerPerformance), alle „ohne Business“; Ziel 10 verfehlt |
| K4 | Spearman 0,40 gesamt (n=30), ohne Website 0,21 (vorher 0,26), mit Website 0,32; Ymolution Rang 5, SECARA 15 (vorher 14) |

## 2. Faktencheck Personen (K3)

Quellen: Websuche, Beleg-URLs. LinkedIn-Seiten nicht abgerufen. „unbestätigt“ heißt: im Netz nicht auffindbar, nicht widerlegt.

| Lead | Person | Rolle im Dossier | Zuordnung | Rolle/Hintergrund | Quelle |
|---|---|---|---|---|---|
| **Nicht-Pilot** | | | | | |
| SUNEO | D. B. Ritzer | Teammitglied (LinkedIn), tech | unbestätigt | unbestätigt | KIT-Seite: Dr., Perowskit-Laser, tech plausibel; SUNEO nirgends erwähnt |
| SUNEO | H. Eggers | Gründer (Presse), tech | unbestätigt | unbestätigt | startbase-Seite 403; Suche findet nur KIT-Doktorand Perowskit (Paetzold-Gruppe), kein SUNEO |
| Linque | P. Pertsch | Teammitglied (LinkedIn), tech | ja | ja | LMU-Nanophotonik-Seite „Team Linque“ |
| mechIC | P. Schmitt | Mitgründer (Presse), tech | ja | ja | VDE-Interview, high-tech.nrw (Gründer Philip Schmitt, Lisa Schmitt, Henning Mays) |
| mechIC | S. Wittemeier | Gründer (Presse), None | ja | teilweise | campus-start-ups.nrw: „Gründer“; high-tech.nrw führt ihn nicht unter den Gründern, VDE nennt ihn Teammitglied |
| **Pilot** | | | | | |
| Aiina-Robotics | L.-M. Pätzmann | Gründerin (Presse), tech | ja | Rolle ja, **Hintergrund nein** | Munich Startup, deutsche-startups: Co-Gründerin und CEO (Lead heißt jetzt Sitegeist); Promotion BWL/Wirtschaftsinformatik, `tech` aus OpenAlex ist fragwürdig |
| dentson | A. Ben Achour | Teammitglied (LinkedIn), tech | ja | Rolle zu schwach | Fraunhofer-AHEAD-Onepager, startbase: Co-Founder |
| dentson | L. Hellmund | Teammitglied (LinkedIn), None | unbestätigt | unbestätigt | in keiner öffentlichen Quelle gefunden |
| SpinMagIC | M. Segantini | Teammitglied (LinkedIn), tech | ja | ja | Uni Stuttgart, eni: Physik, Anwendungen/Marktanalyse |
| SpinMagIC | A. Chu | Teammitglied (LinkedIn), tech | ja | ja | Uni Stuttgart: Elektrotechnik, Schaltungsdesign |
| BotFellows | J. Halim | Co-Founder & Head of Engineering (LinkedIn), tech | ja | ja | Suchtreffer de.linkedin.com (Snippet: Co-Founder, Head of Engineering, Botfellows) |
| SideroGaIn | R. Jain | CEO (Presse), tech | ja | ja | idw 876492, hzdr-innovation.de |
| SideroGaIn | P. Boelens | Teammitglied (Presse), tech | ja | ja | idw/HZDR-Teamliste |
| SideroGaIn | A. Ghosh | Teammitglied (Presse), tech | ja | ja | idw/HZDR-Teamliste |
| SideroGaIn | J. Engelhardt | Teammitglied (Presse)/(LinkedIn), None | ja | ja | idw/HZDR; Business-Development-Kontakt |

Nicht geprüft: Anreicherung Bdiwi/BotFellows („CEO (Presse)“).

### Precision

| Gruppe | n | Zuordnung bestätigt richtig | unbestätigt | widerlegt | Precision Zuordnung (bestätigt/n) | Rolle/Hintergrund bestätigt richtig |
|---|---|---|---|---|---|---|
| Pilot | 10 | 9 | 1 (Hellmund) | 0 | 90 % | 7/10 (Pätzmann Hintergrund falsch, Ben Achour Rolle zu schwach, Hellmund offen) |
| Nicht-Pilot | 5 | 3 | 2 (Ritzer, Eggers; beide SUNEO) | 0 | 60 % (3/3 der prüfbaren) | 2/5 bestätigt (Wittemeier nur teilweise) |
| Gesamt | 15 | 12 | 3 | 0 | 80 % streng, 100 % der prüfbaren | 9/15 = 60 % streng |

**K3: nicht nachgewiesen.** Es gibt keine nachweislich falsche Zuordnung, aber die geforderten 90 % bei Zuordnung und Rolle sind mit der Stichprobe nicht belegbar (Zuordnung 80 % streng, Rolle 60 % streng). Zwei klare Rollenfehler: Pätzmann `tech`, Ben Achour „Teammitglied“. Die Pilot-Zuordnung liegt bei exakt 90 %. Keine Liker, keine Fremdfirmen-Gründer gefunden.

## 3. Leitplanken

- Keine HTTP-Abrufe von linkedin.com in `context/team.py` (nur Brave-Snippets, Zeile 8 dokumentiert; kein Request-Code gefunden).
- Keine Privat-E-Mail, Telefon oder Wohnort in `round-1-persons.json` und `sc/scores.json`. Die E-Mails in `sc/scores.json` sind generische Firmenadressen (info@, contact@), keine Privatadressen.
- Brave-Key: kein `BSA…`-Schlüssel in AGENT_TEAM, examples, context, scoring, evaluation gefunden.
- Hinweis: `round-1-persons.json` enthält Klarnamen und LinkedIn-URLs, nicht committen ohne Team-Entscheidung (steht schon im Hinweis der Datei).

## 4. Regressionen (sc_gate2_now gegen sc, gate2 identisch zu sc_gate2_now)

Score-Änderungen bei Leads **mit** neuen Personen: SideroGaIn +2,7, SpinMagIC +1,3, dentson +1,4, mechIC +2,9, Linque +2,7, SUNEO +2,7. Erklärbar (komplementaer-Proxy zu Teammitglied-Mix, forscher_match).

Änderungen bei Leads **ohne** neue Personen: iNSyT −0,8, Ymolution −0,8, Metubiq −0,8, BEHtec −0,8, LayerPerformance −0,8. Das sind genau die 5 K2-Leads: komplementaer wechselt von 0,6 (Mix unbekannt) auf 0,5 („ohne Business“, weil alle GF `tech`). Erklärbar, aber siehe M1.

Top 10 vorher: DyNAtrix 68,0 · iNSyT 67,1 · BotFellows 64,9 · SideroGaIn 64,8 · Ymolution 64,7 · Metubiq 62,9 · SA-Dynamics 62,9 · Pulse-of-Production 62,9 · AutonomIQ 62,5 · VersatileRobotics 62,2.
Top 10 nachher: DyNAtrix 68,0 · SideroGaIn 67,5 · iNSyT 66,3 · BotFellows 64,9 · Ymolution 63,9 · dentson 63,3 · SpinMagIC 63,2 · SA-Dynamics 62,9 · Pulse-of-Production 62,9 · AutonomIQ 62,5. Metubiq und VersatileRobotics fallen heraus; dentson und SpinMagIC (beide Teammitglieder, beide Teams mit unklarer Gründerrolle) steigen ein.

## Befunde

**BLOCKER:** keine technischen.

**MAJOR**
- M1 (Inhalt, K3): Zwei Personen mit `tech` aus Hintergrundfeldern, die nicht stimmen oder nicht belegt sind: Pätzmann (BWL/Wirtschaftsinformatik-Promotion, `tech` aus OpenAlex-Fallback) und mögliche weitere OpenAlex-Namensdoppelgänger (OpenAlex-Fallback „≥ 5 Arbeiten ⇒ tech“ ist die Fehlerquelle; `context/engine.py`, `context/team.py`). Folge: Fälschlich „ohne Business“ bei K2-Leads (fünf Leads −0,8) beruht nur auf `tech`-Hintergründen aus Rollen und OpenAlex; ein Business-Profil kann ohne LinkedIn-Treffer fehlen. Das widerspricht der Plan-Regel „Abwesenheit nie Malus“. Empfehlung: OpenAlex-Fallback nicht für `mehrere_ohne_business` zählen.
- M2: Rolle „Teammitglied“ untertreibt belegte Gründer (Ben Achour = Co-Founder laut AHEAD/startbase); Hellmund, Ritzer, Eggers in keiner Quelle bestätigbar. Die Aufstiege von dentson und SpinMagIC in die Top 10 stützen sich auf solche Personen.

**MINOR**
- m1: Wittemeier als „Gründer“ nur durch eine Quelle gestützt; andere nennen ihn Teammitglied.
- m2: K4 ohne Website fällt auf 0,21 (Ziel war „nicht schlechter“, gesamt 0,40 hält die Schwelle knapp).
- m3: Aiina-Robotics heißt inzwischen Sitegeist; Dossier nennt den alten Namen.
- m4: 733er-Offline-Lauf und `scoring/__main__` nicht unabhängig neu geprüft.

## Urteil

**Technisch ok** (Suite grün, byte-identisch, Schema ok, Leitplanken eingehalten). **Inhaltlich nicht ok für ÜBERNEHMEN ohne Nachbesserung:** K1 (24 statt 30) und K2 (5 statt 10) verfehlt, K3 nicht nachgewiesen (Zuordnung 80 % streng, Rolle 60 % streng, keine nachweislich falsche Zuordnung).
