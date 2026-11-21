# Hinweise zu Drittquellen

Das Repository hat noch keine eigene Lizenz (siehe README, „Lizenz und Namensnennung“).

## Übernommene Verfahren

### udb-foerderkatalog-scraper (Technologiestiftung Berlin)

Das Sourcing aus dem Förderkatalog (`sourcing/foekat_export.py`) folgt dem Vorgehen von
[technologiestiftung/udb-foerderkatalog-scraper](https://github.com/technologiestiftung/udb-foerderkatalog-scraper),
MIT-Lizenz, Copyright (c) 2026 Technologiestiftung Berlin: CSV-Export statt HTML-Paginierung, Abgleich mit
der vom Server gemeldeten Trefferzahl, Bereinigung des Exports und Dedupe über das Förderkennzeichen.

Übernommen wurde das Vorgehen, kein Quellcode. Der Abgleich mit Commit `bbf54e1` (01.11.2026) fand nur
vom Server vorgegebene Formularfelder und eine einzeilige Regex für „Treffer insgesamt“ als Gemeinsamkeit.
Wird später Code aus dem Projekt übernommen, gehört dessen MIT-Lizenztext in diese Datei.

### startup-valuation (simonmak-ascent)

Faktorlisten und Ausgangsgewichte des Scorings (`scoring/`, `scoring/scoring_config.yaml`) stammen aus den
Verfahren Scorecard (Bill Payne), Berkus und Risk Factor Summation in der Umsetzung von
[simonmak-ascent/startup-valuation](https://github.com/simonmak-ascent/startup-valuation), MIT-Lizenz.
Übernommen wurden Faktorlisten und Ausgangsgewichte, kein Quellcode; die Änderungen stehen in
[`scoring/SCORING.md`](scoring/SCORING.md), Abschnitt „Herkunft des Verfahrens“.

### streamlit-extras (arnaudmiribel), Dashboard-Muster

Die KPI-Karten im Deep Dive (`ui_theme.py`, Regel für `div[data-testid="stMetric"]`) folgen dem Muster
`style_metric_cards` aus [arnaudmiribel/streamlit-extras](https://github.com/arnaudmiribel/streamlit-extras)
(`src/streamlit_extras/metric_cards/__init__.py`, Stand Commit `6c1736b`, 30.03.2026), Apache-2.0-Lizenz:
`st.metric` per CSS über den `data-testid`-Selektor als Karte mit farbiger linker Kante umgestalten, statt eigene
HTML-Karten zu bauen. Übernommen wurde das Muster (Selektor, linke Akzentkante), kein Code wörtlich; Farben, Radius
und Abstände sind eigene Werte. Geprüft und verworfen wurden populäre Dashboard-Vorlagen ohne Lizenz
(z. B. `dataprofessor/population-dashboard`, `Sven-Bo/streamlit-sales-dashboard`): ohne Lizenz keine Übernahme.

### Schriften (SIL Open Font License 1.1)

`assets/fonts/`: Questrial (Copyright 2011 The Questrial Project Authors) und Hanken Grotesk (Copyright 2021
The Hanken Grotesk Project Authors), latin-Subset von Google Fonts. Lizenztexte liegen daneben
(`OFL-Questrial.txt`, `OFL-HankenGrotesk.txt`). Sie ersetzen die lizenzpflichtigen Schriften der HTGF-Website
(ITC Avant Garde Gothic, ESFace), deren Farbwelt und Typografie nur als Inspiration dienen; FounderRadar nutzt
kein HTGF-Logo und keine HTGF-Marke.

## Datenquellen

| Quelle | Genutzt in | Nutzungsbedingungen laut Projektdoku |
| --- | --- | --- |
| [Förderkatalog des Bundes](https://foerderportal.bund.de/foekat/) (Herausgeber BMFTR, Betrieb DLR-IP) | `sourcing/`, `context/foekat.py` | Impressum und Datenschutzerklärung enthalten keine Lizenz und keine Nutzungsbedingungen (Stand 20.11.2026), `robots.txt` antwortete 403. Jeder Lead nennt Quelle und Detail-URL. Vor einer Weitergabe außerhalb des Hackathons bei foekat@dlr.de nachfragen ([`sourcing/FOEKAT.md`](sourcing/FOEKAT.md)). |
| Impressum und Seiten der Unternehmenswebsite | `context/imprint.py`, `context/web.py` | nicht dokumentiert; Impressumsangaben sind gesetzliche Pflichtangaben |
| [OpenAlex](https://openalex.org) API | `context/openalex.py` | nicht dokumentiert; ohne Key ca. 100 Anfragen pro Tag und IP ([`context/ENRICHMENT.md`](context/ENRICHMENT.md)) |
| [Wayback Machine](https://web.archive.org) CDX | `context/wayback.py` | nicht dokumentiert |
| [idw – Informationsdienst Wissenschaft](https://idw-online.de) | `context/idw.py` | nicht dokumentiert |
| [Google Patents](https://patents.google.com) (nur mit `--patents`) | `context/patents.py` | nicht dokumentiert; IP-Sperre nach etwa 12 Anfragen |
| Eurostat und Unternehmensseiten (Wettbewerber, HTGF-Referenzrunde) | `context/demo_market.py` (Demo `industrial-16`) | nicht dokumentiert; Quelle steht an jedem Wert |

„Nicht dokumentiert“ heißt: Die Projektdoku nennt keine Bedingungen. Vor einer Nutzung außerhalb des Hackathons
müssen die Verantwortlichen die Bedingungen der jeweiligen Quelle prüfen.

## Bibliotheken

Laufzeitabhängigkeiten (`requirements.txt`): pydantic, Streamlit, Plotly, PyYAML, jsonschema; für Tests pytest.
Es gelten deren eigene Lizenzen; es ist kein Quellcode daraus im Repository.
