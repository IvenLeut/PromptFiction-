# Hinweise zu Drittquellen

## udb-foerderkatalog-scraper (Technologiestiftung Berlin)

Das Sourcing aus dem Förderkatalog (`sourcing/foekat_export.py`) folgt dem Vorgehen von
[technologiestiftung/udb-foerderkatalog-scraper](https://github.com/technologiestiftung/udb-foerderkatalog-scraper),
MIT-Lizenz, Copyright (c) 2026 Technologiestiftung Berlin: CSV-Export statt HTML-Paginierung, Abgleich mit
der vom Server gemeldeten Trefferzahl, Bereinigung des Exports und Dedupe über das Förderkennzeichen.

Übernommen wurde das Vorgehen, kein Quellcode. Der Abgleich mit Commit `bbf54e1` (01.11.2026) fand nur
vom Server vorgegebene Formularfelder und eine einzeilige Regex für „Treffer insgesamt“ als Gemeinsamkeit.
Wird später Code aus dem Projekt übernommen, gehört dessen MIT-Lizenztext in diese Datei.

## Förderkatalog des Bundes

Daten: [Förderkatalog des Bundes](https://foerderportal.bund.de/foekat/), Herausgeber Bundesministerium für
Forschung, Technologie und Raumfahrt, Betrieb DLR-IP. Eine Lizenz oder Nutzungsbedingungen für die Daten
haben wir auf den Seiten nicht gefunden (Stand 20.11.2026); jeder Lead nennt die Quelle und die Detail-URL.
