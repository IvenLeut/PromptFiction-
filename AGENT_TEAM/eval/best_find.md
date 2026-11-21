# Best-Find-Kandidaten (T3, Vorschlag des Evaluator-Agents)

Stand 21.11.2026, nach dem Faktencheck (`AGENT_TEAM/reports/fact_check.md`) überarbeitet. Alle Kandidaten
stammen aus den 30 höchstpriorisierten Leads von `examples/sourcing/shortlist.json`. Zu jedem Signal gibt es eine
Quelle. Vor dem Pitch muss das Team prüfen: Handelsregister bzw. northdata, HTGF-Portfolio, LinkedIn und eine
direkte Rückfrage zur Finanzierung.

**Was „DB-Check“ heißt:** Die Wayback-CDX-API wurde nach den Crunchbase- und Dealroom-Profil-URLs gefragt, die
`context.wayback.slugs` erzeugt. Das Ergebnis lautet „kein archiviertes Profil in Wayback“, nicht „in keiner
Datenbank“. Bei InhalPlus etwa gab es kein archiviertes Profil, nordic9 und VCBacked führen die Firma aber längst.
Vor dem Pitch bitte von Hand in Crunchbase, Dealroom, PitchBook, nordic9 und Tracxn suchen.

**Gegensuche Finanzierung:** Für jeden Kandidaten wurde ausdrücklich nach Investoren, Pre-Seed und Finanzierung
gesucht (Websuche und Brave Search API). Was dabei herauskam, steht in der Zeile „Finanzierung“.

| Rang | Kandidat | Status |
|---|---|---|
| **1 (Empfehlung)** | **Ymolution** (03EFMV0034) | GmbH, nur öffentliche Mittel plus Unimedizin als Gesellschafterin, sucht laut eigener Website Investoren für 2026 |
| 2 | **SECARA** (03EFNW0408) | GmbH, Industrie-MoU mit Envalior, nur öffentliche Mittel gefunden |
| 3 (offene Prüffrage) | Versatile Robotics (03EFBY0327) | Finanzierung strittig, vor dem Pitch nachfragen |
| gestrichen | InhalPlus (03EFNI0124) | **finanziert**: NBank Capital, 500.000 EUR Pre-Seed am 16.10.2026, für ein Best Find zu spät |

Score-Rang heute (offline/`--light`, Stichtag 21.11.2026): Baseline HEAD fda6207 ergibt 53,7 für alle 139 Leads im
Gleichstandsblock. Im WIP-Scoring des `scorer` steht Ymolution auf 171, SECARA auf 16 und Versatile auf 219 von 733.

---

## 1. Ymolution (FKZ 03EFMV0034): Empfehlung für „Your Best Find“

Ausgründung der Unimedizin Greifswald. Ymolution stellt Nano-Antikörper ohne Tierversuche her, aus synthetischen
Genbibliotheken im bakteriellen System. Rang 30 der Fundliste.

| Datum | Signal | Quelle |
|---|---|---|
| **01.11.2024** | **EXIST-Forschungstransfer startet**, 853.134 EUR, bis 30.06.2026 (unser Signal) | https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFMV0034 |
| 04/2025 | Innovationspreis der BioRegionen Deutschlands, erstes Projekt aus Mecklenburg-Vorpommern | https://www.medizin.uni-greifswald.de/fileadmin/user_upload/Marketing/Pressemitteilungen/PM_Innovationspreis_Ymolution.pdf |
| 08.01.2026 | Ymolution gegründet. **Die Unimedizin Greifswald ist Gesellschafterin**, nach eigener Aussage zum ersten Mal bei einer Ausgründung (PM vom 14.01.2026) | https://www.unimedizin-greifswald.de/fileadmin/user_upload/Marketing/Pressemitteilungen/PM-Ymolution-Gr%C3%BCndung.pdf |
| 29.01.2026 | Erste Wayback-Aufnahme von ymolution.com | https://web.archive.org/web/20260129101905/https://www.ymolution.com/ |
| o. D. | Rund 1,34 Mio. EUR Förderung für Unimedizin und Ymolution (Krebsforschung; laut Such-Snippet, die Seite war nicht abrufbar, Datum und Anteil offen) | https://www.tagesschau.de/inland/regional/mecklenburgvorpommern/millionenfoerderung-fuer-greifswalder-krebsforschung,mvregiogreifswald-6120.html |
| heute | Impressum: Ymolution GmbH, Greifswald, HRB 23103 AG Stralsund, GF Dr. Alexander Reder, Dr. Christian Hentschker | https://www.ymolution.com/impressum |
| heute | Website: „Wir suchen strategische Investoren und institutionelle Partner für die Finanzierungsrunde 2026“ | https://www.ymolution.com/ |
| heute | Finanzierung: keine VC- oder Angel-Meldung gefunden (Gegensuche „Ymolution Investor Finanzierung“), kein archiviertes Crunchbase-/Dealroom-Profil in Wayback | Gegensuche, CDX-Check |

**Team:** Dr. Alexander Reder, Dr. Christian Hentschker, Marc Schaffer, Jan Meiering.
**Warum jetzt anrufen:** Die GmbH gibt es seit Januar 2026, die EXIST-Förderung endete am 30.06.2026, und laut
eigener Website läuft die Investorensuche für 2026. Eine Plattform für Forschungsreagenzien, Diagnostik und
Therapie spricht einen großen Antikörpermarkt an. Greifswald liegt weit weg von den VC-Zentren, also dürfte es
wenig Konkurrenz um den Deal geben.
**Offen:** Paper oder Patent zum Verfahren wurden nicht gefunden. Geschäftsmodell (Service oder Plattform) und
Anteil der Unimedizin klären.

## 2. SECARA (FKZ 03EFNW0408): saubere Alternative

RWTH-Ausgründung aus dem Umfeld von catalaix/ITMC. SECARA recycelt technische Kunststoffe (Polyamide, Polycarbonat)
durch katalytische Depolymerisation zu Monomeren, die sich direkt wieder einsetzen lassen. Rang 14 der Fundliste.

| Datum | Signal | Quelle |
|---|---|---|
| 05/2024 | Aufnahme in den QuinCAT-Inkubator (RWTH-Chemiegebäude); Gründer beginnen 2024 mit dem Firmenaufbau | https://www.wernersiemens-stiftung.ch/en/projects/detail/catalaix/ein-startup-zerlegt-verstaerkte-kunststoffe |
| 01/2025 | Forschungskooperation mit der FH Aachen | https://www.fh-aachen.de/en/faculties/chemistry-biotechnology/institutes-and-workgroups/bioprocess-engineering-and-downstream-processing/news/news-details/secara-and-fh-aachen-launch-research-collaboration-on-advanced-plastic-recycling |
| 07/2025 | Förderung aus dem catalaix-JUMP-Programm | https://www.wernersiemens-stiftung.ch/en/projects/detail/catalaix/ein-startup-zerlegt-verstaerkte-kunststoffe |
| **01.09.2025** | **EXIST-Forschungstransfer startet**, 1.333.283 EUR, bis 28.02.2027 (unser Signal; Lehrstuhl für Heterogene Katalyse und Technische Chemie der RWTH) | https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFNW0408 |
| 02/2026 | Zuschuss „Grüne Gründungen NRW“ über 600 Tsd. EUR (laut LinkedIn-Update auf der Website) | https://secara.tech/ |
| 25.08.2026 | MoU mit Envalior (ehem. Lanxess/DSM Engineering Materials) über PA6 mit Rezyklat für Automobilteile. Dort wird SECARA nur mit öffentlicher Förderung (EFRE/JTF, MUNV, ESF Plus, BMWE) genannt, ohne Investoren | https://www.envalior.com/en-us/insights/press-release/envalior-and-secara-collaborate-to-deliver-circular-pa6-for-automotive-applications-in-line-with-coming-regulations |
| heute | Impressum: SECARA GmbH, Aachen, HRB 29119 AG Aachen, GF Marcus Stephan Lehnertz, Fabian Nagel, Jan Uecker | https://secara.tech/impressum.html |
| heute | Finanzierung: keine VC- oder Angel-Meldung gefunden (Gegensuche „SECARA … Investoren pre-seed / funding round“); weder Website-Domain noch Crunchbase-/Dealroom-Profil in Wayback archiviert | Gegensuche, CDX-Check |

**Team:** Dr. Fabian Nagel (CEO), Dr. Marcus Lehnertz (CTO), Dr. Jan Uecker (COO).
**Warum jetzt anrufen:** Mit Envalior gibt es einen namhaften Industriepartner und eine regulatorische Triebkraft
(Rezyklatquoten der EU-Altfahrzeugverordnung). Bisher fließen nur Zuschüsse, und die EXIST-Förderung endet im
Februar 2027. Für den Bau einer Pilotanlage braucht SECARA Eigenkapital. HTGF-Sektor Industrial/Climate.
**Offen:** Datum der Handelsregistereintragung; ob vor EXIST schon eine Beteiligung bestand; Eigentum am
Prozess-IP (RWTH/catalaix).

## 3. Versatile Robotics (FKZ 03EFBY0327): offene Prüffrage, keine Empfehlung

DLR-Ausgründung aus dem Institut für Robotik und Mechatronik. Versatile Robotics entwickelt Regelungssoftware,
mit der Roboter schnell und trotzdem sicher mit Menschen zusammenarbeiten. Priorität 90 (Rang 5 der Fundliste).

| Datum | Signal | Quelle |
|---|---|---|
| 2020 | Paper „Modular Passive Tracking Controller“ (MPTC), RSS 2020, Englsberger et al. (DLR) | https://elib.dlr.de/136932/ |
| o. D. | Patentfamilie „MPTC – Modular, passive tracking controller for robots“, erteilt in CN, US, EU, JP, KR (laut DLR-Seite) | https://www.dlr.de/en/rm/transfer/spin-offs/versatile-robotics |
| 28.07.2024 | Erste Wayback-Aufnahme von versatile-robotics.com (vor dem EXIST-Start) | https://web.archive.org/web/20240728020206/https://versatile-robotics.com/ |
| **01.10.2024** | **EXIST-Forschungstransfer startet**, 1.064.409 EUR, bis 31.03.2026 (unser Signal) | https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFBY0327 |
| 18.11.2024 | Eintragung der Versatile Robotics GmbH, HRB 297629 AG München, Stammkapital 25.000 EUR (nach dem EXIST-Start) | https://openregister.de/company/DE-HRB-D2601-297629 |
| 2025 | Hannover Messe 2025, Munich Business Plan Competition 2025 (Phase 1), ESA BIC | https://www.dlr.de/en/rm/transfer/spin-offs/versatile-robotics |
| heute | Impressum: Versatile Robotics GmbH, Weßling, vertreten durch Dr.-Ing. Johannes Englsberger | https://versatile-robotics.com/imprint/ |
| **strittig** | Finanzierung: Ein Such-Snippet von Bits & Pretzels nennt 1,25 Mio. EUR Pre-Seed mit drei Lead-Investoren, die Seite liefert aber 404. Dagegen stehen ein LinkedIn-Post von Englsberger („ohne externe Investoren aufgebaut“) und die Munich-Startup-Datenbank („No known external funding“) | `AGENT_TEAM/reports/fact_check.md` |

**Prüffrage vor dem Pitch:** Gibt es eine Pre-Seed-Runde (1,25 Mio. EUR)? Falls ja, scheidet Versatile Robotics als
früher Fund aus wie InhalPlus. Falls nein, wäre es fachlich der stärkste Kandidat (erteiltes Patent, DLR-Herkunft,
EXIST seit 03/2026 beendet).

## Gestrichen: InhalPlus (FKZ 03EFNI0124)

Fraunhofer-ITEM-Ausgründung (Aerosoltherapie für Frühgeborene, InhalPlus GmbH gegründet am 27.08.2026). **Am
16.10.2026 beteiligte sich NBank Capital mit 500.000 EUR Pre-Seed** als erster externer Geldgeber
(https://startupvalley.news/de/inhalplus-fruehgeborenen-nbank-capital/). Profile bei nordic9 und VCBacked gibt es
bereits. Damit kommt die Firma für „Best Find“ zu spät. Für den Pitch taugt sie trotzdem als Beleg, dass das Signal
stimmt: EXIST-Start 01.12.2024, erste Finanzierung 16.10.2026, also gut 22 Monate Vorsprung.

---

### Ersatzkandidaten (`talk`, nicht ausgearbeitet, Finanzierung noch nicht gegengeprüft)

- **DyNAtrix** (03EFSN0252, IPF Dresden): Nature Nanotechnology 2023, noch keine Firma gefunden.
  https://idw-online.de/en/news850604
- **SpaceMast / Adpera** (03EFWNI117, DLR Braunschweig): Demo im Orbit erfolgreich, Adpera GmbH i.G., Lizenz in
  Verhandlung. https://www.compositesworld.com/news/dlr-spacemast-completes-first-orbital-deploy-retract-cycle
- **PoLightFilters** (03EFNW0392, Uni Köln): Patent angemeldet, Humboldt-Professur.
  https://uni-koeln.de/en/university/news/news/news-detail/federal-ministry-supports-start-up-project-on-pioneering-filter-technology
