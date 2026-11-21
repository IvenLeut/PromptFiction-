# Faktencheck (Agent `fact-check`), Stand 21.11.2026

Methode: Seiten per WebFetch/WebSearch abgerufen. Wo eine Seite nicht lud oder die Quelle nur ein Such-Snippet war, steht "unbelegt". Es wurde kein Code geändert.

## Befunde nach Schwere

| Schwere | Befund | Wer korrigiert |
|---|---|---|
| **BLOCKER** | **InhalPlus ist seit 16.10.2026 finanziert**: NBank Capital, 500.000 EUR Pre-Seed, notariell beurkundet 16.10.2026, "erster externer Geldgeber", nächste Runde für 2027 geplant (startupvalley.news, 20.10.2026: https://startupvalley.news/de/inhalplus-fruehgeborenen-nbank-capital/). `best_find.md` schreibt "keine Finanzierungsmeldung gefunden / Wagniskapital noch keines bekannt". Das ist widerlegt. InhalPlus taugt nicht mehr als frühes "Best Find" ohne Einschränkung. | evaluator |
| **BLOCKER** | **Versatile Robotics**: Wegen eines Such-Snippets (Bits & Pretzels: "1,25 Mio. EUR, Pre-Seed, 3 Lead-Investoren") ist unklar, ob schon Kapital geflossen ist. Die Seite lieferte 404, die Angabe ist **unbelegt**. Dagegen steht Englsbergers LinkedIn-Post: "ohne externe Investoren aufgebaut (bootstrapping)". Munich-Startup-DB: "No known external funding". Vor dem Pitch bei der Firma nachfragen. Die Aussage "keine Finanzierung gefunden" ist haltbar, "Finanzierung ausgeschlossen" nicht. | evaluator |
| MAJOR | Versatile Robotics, EXIST-Ende: `best_find.md` nennt "ausgelaufen 31.03.2026" (richtig laut Förderkatalog). Die Behauptung "Anschlusskapital jetzt nötig" hängt aber an der Finanzierungsfrage oben. | evaluator |
| MAJOR | Backtest: Die Headline "12/12" ist rechnerisch korrekt, aber nur auf Basis der Auswahl (siehe Selektionsbias in `backtest.json`). OroraTech (4,1 Monate) stützt sich auf eine Aggregator-Meldung mit `confidence=niedrig`. Mit OroraTech-Werten ab 2019-01 ist das Minimum nicht belastbar. Empfehlung: Headline mit "n=12, Handauswahl" kennzeichnen, OroraTech aus der Headline nehmen oder markieren. | evaluator |
| MINOR | Exzellenzliste in `scoring_config.yaml`: enthält Konstanz (verliert den Titel laut Entscheidung vom 11.03.2026, https://www.forschung-und-lehre.de/politik/zehn-exzellenzstandorte-behalten-ihren-titel-7580). Neue Exzellenzstandorte ab 01.01.2027 fehlen: Freiburg, Jena, Köln, Bochum/Dortmund, Rhein-Main-Universitäten (TU Darmstadt ohnehin in TU9) (https://www.forschung-und-lehre.de/politik/neue-exzellenzstandorte-jubeln-7936). Bei Stichtag 21.11.2026 zählt formal noch die Förderphase 2019 bis 2026. Beides als Konfig-Hinweis dokumentieren. | scorer |
| MINOR | Stipendium: 3.000 EUR/Monat für Promovierte, Coaching 5.000 EUR nicht bestätigt (siehe Tabelle 5). Besser mit dem Richtlinientext (Bundesanzeiger 18.04.2023) belegen. | scorer |
| MINOR | `matcher.md`: "AutonomIQ: Über-uns-Seite aus dem PTW der TU Darmstadt" ist korrekt, aber nur auf `/about`, nicht auf der Startseite. Fundstelle genauer angeben. | matcher |

## 1. Website-Matches

| Behauptung | Urteil | Beleg |
|---|---|---|
| Pulse-of-Production = EXIST-Projekt MTI RWTH Aachen | bestätigt | Seite: "basiert auf Arbeiten des Manufacturing Technology Institute (MTI) der RWTH", Aachen, EXIST-Logo: https://pulse-of-production.de/ |
| M-Shunt.com gehört zum EXIST-Projekt (Bremen, IALB) | **bestätigt, Konflikt aufgelöst** | Seite nennt "EXIST ... Förderkennzeichen 03EFHB0044", Logos IALB/Uni Bremen/BRIDGE: https://www.m-shunt.com/. Förderkatalog 03EFHB0044: Thema "M-Shunt", IALB Bremen, 01.11.2025 bis 30.04.2027. Die Domain ist per whois seit 31.05.2023 registriert, Wayback ab 23.07.2023. Das widerspricht nicht: Die Domain ist älter als das EXIST-Projekt, die Seite verweist aber selbst auf die FKZ. Die Wayback-Einstufung "Namensvetter wegen Alter" ist falsch und sollte das Alter nur als Hinweis behandeln, nicht als Ausschluss. |
| AutonomIQ = TU Darmstadt, PTW | bestätigt | https://autonomiq.de/about: aus TU Darmstadt und AICoM am PTW hervorgegangen, EXIST. Förderkatalog 03EFHE0108: TU Darmstadt PTW, 01.06.2025 bis 28.02.2027. |
| SpinMagIC = Uni Stuttgart EXIST | teilweise bestätigt | Seite nennt EXIST und EPR-Quantensensor, aber **nicht** die Uni Stuttgart (https://www.spinmagic.eu/). Zuordnung stützt sich auf Namen und Thema; Institut nicht belegt. |
| SECARA = ITMC RWTH, EXIST | teilweise bestätigt | Förderkatalog 03EFNW0408: RWTH, Chair of Heterogeneous Catalysis and Technical Chemistry, 01.09.2025 bis 28.02.2027. Seite secara.tech: Polyamid-Depolymerisation, Backer "CAtalaiX, RWTH Aachen", EXIST, CTO technische Chemie. Plausibel, aber ITMC wird nicht genannt (https://secara.tech/). Matcher-Einstufung "wahrscheinlich richtig" ist angemessen. |
| sensai.io = Namensvetter | bestätigt | SEO-/AI-Akademie von Vestigio: https://sensai.io/ |
| suneo.ai = Namensvetter | bestätigt | Slack-KI-Assistent: https://www.suneo.ai/ |
| simba.de = Namensvetter | bestätigt | Simba Computer Systeme GmbH, Buchhaltung/ERP: https://www.simba.de/ |
| boneguide.com = Namensvetter | bestätigt | Regionales Nachrichtenportal: https://boneguide.com/ |
| siderogain.de zum Verkauf | bestätigt | spaceship.com-Angebot, 1.470 USD: https://siderogain.de/ |

## 2. Backtest

Monate nachgerechnet (Tage / 30,4375) aus `backtest.json`: alle 13 Einzelwerte stimmen. Sortierte Werte (n=12): 4,1 / 7,9 / 12,8 / 13,0 / 20,2 / 20,6 / 20,9 / 21,4 / 26,1 / 31,8 / 37,6 / 39,7. Median (20,6+20,9)/2 = 20,75, also "21 Monate" korrekt. Spanne 4–40 korrekt. FMC (39,2) zu Recht ausgeschlossen (HTGF-Seed davor).

| Firma | Behauptung | Urteil | Beleg |
|---|---|---|---|
| Alle (außer s.u.) | FKZ/Startdatum im Förderkatalog | unbelegt (nur Versatile-FKZ stichprobenartig geprüft) | foerderportal.bund.de lieferte nur für einzelne FKZ Inhalt. Versatile 03EFBY0327: 01.10.2024 bis 31.03.2026, 1.064.409 EUR (bestätigt). Das Skript prüft die FKZ gegen den lokalen Export, das ist plausibel, aber nicht extern verifiziert. |
| Tubulis | HTGF-Portfolio, Series A 21.07.2020 | bestätigt | HTGF-Seiten "HTGF Portfolio Company Tubulis" und `htgf-investment-tubulis`: https://www.htgf.de/en/htgf-investment-tubulis/ ; Series A 2020 HTGF-Co-Lead. Einzige Auffälligkeit: Portfolio-Listing trägt Label "Exit", wirkt veraltet. |
| sewts | HTGF, Seed 04.05.2021 | bestätigt | https://www.htgf.de/en/htgf-investment-sewts : APEX, Bayern Kapital, HTGF, "siebenstellig", gegründet 2019. |
| Pixel Photonics | HTGF, Seed 29.03.2022, 1,45 Mio. | bestätigt | https://www.quantonation.com/2022/03/29/pixel-photonics-raised-seed-round/ |
| oculai | HTGF-Lead, 14.03.2023, 2,5 Mio. | bestätigt | https://www.htgf.de/en/seed-financing-oculai/ |
| Ferroelectric Memory Co. | HTGF, 06.07.2018, 4,6 Mio. | bestätigt | https://www.htgf.de/en/ferroelectric-memory-company-receives-growth-financing-from-ecapital-and-htgf/ : gegründet 2016, früherer HTGF-Seed. Korrekt aus der Headline genommen. |
| GEMESYS | Pre-Seed 19.11.2024, 8,6 Mio. | bestätigt | https://tech.eu/2024/11/19/gemesys-secures-8-6m-pre-seed-for-ai-chip-tech/ |
| QuantumDiamonds | Seed 27.11.2023, 7 Mio. | bestätigt (Aufteilung strittig) | tech.eu: 3 Mio. Equity + 4 Mio. Zuschuss; andere Quellen nennen 7 Mio. Equity. Gründung 2022 (Osborne Clarke). |
| KEWAZO | Seed 02.05.2018 | bestätigt | Munich Startup / roboticsandautomationnews; gegründet 2018. Hinweis: EXIST-Start 04/2017 liegt vor der Gründung. |
| inveox | 28.06.2017, 1 Mio. | teilweise bestätigt | Munich Startup bestätigt 1 Mio. von vier Business Angels, Datum nicht verifiziert. |
| OroraTech | 03.01.2019, 540 Tsd. | unbelegt | Nur Aggregator (nordic9). Selbst als `niedrig` markiert. Hat den kleinsten Vorsprung (4,1) und steht trotzdem in der Headline. |
| FibreCoat, Senorics, RYVER.AI | Datum/Betrag | unbelegt (nicht abgerufen) | Pro Firma Quellen in `reference_companies.json`. |
| HTGF-Portfolio: 5 Firmen | Tubulis, sewts, Pixel Photonics, oculai, FMC | bestätigt | siehe oben (alle 5 mit HTGF-Quelle). Die 8 übrigen als `htgf=false` nicht einzeln gegengeprüft. |

## 3. Best Find

| Behauptung | Urteil | Beleg |
|---|---|---|
| Versatile: DLR-Ausgründung aus Institut für Robotik und Mechatronik | bestätigt | Förderkatalog: DLR RM Weßling; https://www.dlr.de/en/rm/transfer/spin-offs/versatile-robotics |
| Patent in CN, US, EU, JP, KR | bestätigt (nach DLR-Seite) | gleiche Seite |
| Gründung 2024; HRB 297629 AG München; GF Englsberger | bestätigt | Impressum https://versatile-robotics.com/imprint/ ; Handelsregister: Eintragung 18.11.2024, Stammkapital 25.000 EUR, Weßling (https://openregister.de/company/DE-HRB-D2601-297629). Damit liegt die GmbH-Eintragung **nach** EXIST-Start 01.10.2024. Das Datum 28.07.2024 der ersten Wayback-Aufnahme bleibt plausibel (Website vor GmbH). |
| Versatile: EXIST 01.10.2024 bis 31.03.2026, 1.064.409 EUR | bestätigt | Förderkatalog 03EFBY0327 |
| Versatile: ESA BIC | bestätigt | DLR-Seite: "ESA BIC Incubator" als Sponsor |
| Versatile: Team (Brandl, Köhler, Prinz) | bestätigt | DLR-Seite |
| Versatile: keine Finanzierung | **unbelegt / strittig** | siehe BLOCKER |
| InhalPlus: Fraunhofer ITEM, gegründet 27.08.2026, HRB 231505, Lizenz | bestätigt (Gründung, Lizenz, Team) | https://www.bionity.com/en/news/1189999/inhalplus-gmbh-founded-to-improve-drug-delivery-to-the-lungs-of-premature-infants.html (HRB nicht gegengeprüft) |
| InhalPlus: Markteinführung 2029; 1,3 Mio. vom IBT | bestätigt | gleiche Quelle. Hinweis: Die 1,3 Mio. gingen an Fraunhofer ITEM als Projektleiter, ob an die GmbH, steht dort nicht. |
| InhalPlus: keine Finanzierung | **widerlegt** | NBank Capital 500.000 EUR, 16.10.2026 |
| Ymolution: Greifswald, gegründet 08.01.2026, HRB 23103 AG Stralsund, GF Reder/Hentschker | bestätigt | https://www.ymolution.com/impressum ; PM Unimedizin Greifswald vom 14.01.2026 |
| Ymolution: EXIST bis 30.06.2026, 853.134 EUR | teilweise bestätigt | Nordkurier: ca. 850.000 EUR Bund. Exakter FKZ-Wert nicht gegengeprüft. |
| Ymolution: keine Finanzierung | bestätigt (nur öffentliche Mittel) | Suche ohne VC/Angel-Treffer; Impressum "Träger Unimedizin Greifswald, EXIST-gefördert". Unimedizin ist **Gesellschafterin**. Das ist eine Beteiligung, keine VC-Runde, sollte aber in der Zeitleiste stehen. |
| Alle drei: nicht in Crunchbase/Dealroom | unbelegt | Wayback-CDX zeigt nur "nicht archiviert". Für InhalPlus führen nordic9 und VCBacked bereits Profile (Pre-Seed 560 Tsd. USD). Die Aussage ist dort also falsch. |
| HTGF-Beteiligung | keine gefunden | Keine Treffer für alle drei. |

## 4. Labels (Stichprobe)

| Label | Urteil | Beleg |
|---|---|---|
| Aiina-Robotics = heute Sitegeist, TUM Althoff, Pre-Seed 4 Mio. 02/2026 | bestätigt (Umbenennung, TUM, Althoff, 4 Mio. Pre-Seed) | Munich Startup https://www.munich-startup.de/startups/sitegeist-robotics/ ; https://www.startbase.com/news/sitegeist-erhaelt-4-mio-e-pre-seed-finanzierung/ . Aiina ist damit **schon finanziert**: `talk` ist als Pitch-Kandidat für "früh" schwach. Label eher `maybe`. |
| SoreAlert = Sorala | bestätigt (Umbenennung, Fraunhofer EMFT, 60-Patienten-Studie, EXIST) | https://www.emft.fraunhofer.de/en/projects-fraunhofer-emft/sensor-patch-prevention-in-nursing-care.html . "Mitgründer/CEO Lorenz Grünerbel" **unbelegt**. Als "geplante Ausgründung" beschreiben, nicht als bestehende Firma. |
| SpaceMast = Adpera | bestätigt | DLR-Institut für Systemleichtbau Braunschweig, Adpera GmbH i.G., Lizenzverhandlungen laufen; Zander Mitgründer. https://www.compositesworld.com/news/dlr-spacemast-completes-first-orbital-deploy-retract-cycle |
| Iso-Flux = GaiaIsotopic | **bestätigt, kann von `maybe` auf belegt** | TU Dortmund: EXIST-FT, "Iso-Flux"-Technologie, ca. 800 Tsd. EUR/18 Monate: https://www.tu-dortmund.de/en/detail/exist-funding-for-photonic-analysis-of-cellular-metabolism-58239/ |
| SIMBA = simfacture (TU Dresden, Fügetechnik) | plausibel bestätigt | TU Dresden: simfacture-Spin-off, Produkt SIMBA, EXIST-FT: https://tu-dresden.de/ing/maschinenwesen/if/fue/simfacture . FKZ 03EFSN0250 nicht explizit zugeordnet. |
| KM, EXIST_P2P | unbelegt, `maybe` korrekt | keine öffentliche Auflösung gefunden |
| DataLingua | maybe plausibel | nur Projektseite uni-hannover |

## 5. Scorer-Annahmen

| Annahme | Urteil | Beleg |
|---|---|---|
| Kinderzuschlag 150 EUR je Kind | bestätigt | BMWE-Onepager 2025: https://exist.de/wp-content/uploads/2025/11/BMWE_Onepager_EXIST-Gruendungsstipendium_2025-DE_web-bf.pdf |
| Sachausgaben Team 30.000 EUR (Einzel 10.000) | bestätigt | gleicher Onepager |
| Stipendium 3.000 EUR/Monat Promovierte | unbelegt (PDF nicht auslesbar) | gleiche Quelle; im Handbuch EGT nachprüfen |
| Coaching 5.000 EUR | unbelegt | gleiche Quelle |
| Forschungstransfer Phase I 18 Monate (bis 36), Phase II 18 Monate, bis 180.000 EUR | bestätigt (Such-Snippets aus BMWE-Infoblatt/Förderdatenbank) | https://www.foerderdatenbank.de/FDB/Content/DE/Foerderprogramm/Bund/BMWi/exist-forschungstransfer-bund.html . Die Config rechnet mit 36 Monaten (`exist_max_laufzeit_monate`): passend zur Phase I + II. |
| TU9 | bestätigt | Aachen, Berlin, Braunschweig, Darmstadt, Dresden, Hannover, KIT, München, Stuttgart sind in der Regex enthalten |
| Exzellenzuniversitäten "2019" | überholt | siehe MINOR oben |
| Hamburg, Bonn, Heidelberg, Tübingen, LMU, TUM, Dresden, RWTH, KIT, BUA behalten den Status | bestätigt | https://www.forschung-und-lehre.de/politik/zehn-exzellenzstandorte-behalten-ihren-titel-7580 |

## Gesamturteil

Websites und Labels sind überwiegend belastbar, der Backtest rechnet sauber. **Nicht freigabefähig ist `best_find.md`**, solange InhalPlus als unfinanziert dargestellt wird (BLOCKER). Bei Versatile Robotics ist die Finanzierungslage unklar (BLOCKER bis zur Rückfrage); Ymolution ist der sauberste Best Find (nur öffentliche Mittel und Unimedizin als Gesellschafterin). Nach Korrektur der Zeitleiste und Streichung von "nicht in Crunchbase/Dealroom" ist das Gate erreichbar.
