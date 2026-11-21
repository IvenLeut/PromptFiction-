# AGENT TEAM – Kontext-Loop

Jede Runde vertieft den Kontext der Suche um **eine** Ebene (z. B. Team über LinkedIn finden → Lebensläufe der
Gründer bewerten → Vorerfahrung/Track Record → Papers/Patente der Personen → Traction-Signale …). Eine Runde wird
nur übernommen, wenn der Sinn-Check bestätigt, dass sie uns dem Ziel näher bringt.

## Ziel (Maßstab für jeden Sinn-Check)

HTGF-Track „Find the Founders Before Everyone Else“: Gründer früh finden, bevor sie in Datenbanken stehen.
Jurykriterien: **Lead Quality** (würde HTGF anrufen?), **Earliness**, **Creativity of Signals**, **Technical
Execution** (läuft in der Demo), **Scalability**. Tipps: Noise filtern, **Team statt Produkt**, Fokus Deutschland.
Deliverables: Demo + **Best Find**. Output-Vertrag: `~/.claude/skills/goal/SKILL.md`.

## Ablauf einer Runde

1. **Stratege + Sinn-Check vorher** (`strategist`, Opus): liest LOOP-Log, Berichte, aktuelle Messung. Schlägt die
   eine Kontext-Ebene mit dem größten erwarteten Nutzen vor, mit Hypothese („Wenn wir X wissen, steigt Y, weil …“),
   messbarem Erfolgskriterium, Kosten (Brave-Anfragen, Laufzeit), Risiken. **Verwirft** Ideen, die nur Daten
   anhäufen, ohne ein Jurykriterium zu bewegen. Ergebnis: `reports/loop/round-N-plan.md`.
2. **Coder** (Opus, 1–2 Agents, getrennte Dateien): bauen die Ebene mit Offline-Tests und Live-Probe auf den 52
   Gate-Leads (Cache, Brave sparsam).
3. **Prüfung** (Sonnet): Tests/Sanity + Faktencheck einer Stichprobe der neuen Daten im Netz.
4. **Sinn-Check nachher** (`strategist`): Erfolgskriterium erreicht? Bewegt es ein Jurykriterium sichtbar
   (Precision/Spearman auf bestätigten Labels sobald vorhanden, Abdeckung, Best Find, Demo-Aussage)? Urteil
   **ÜBERNEHMEN / NACHBESSERN / VERWERFEN**. Verworfene Ebenen werden zurückgebaut und im Log begründet.
5. **Main**: bei ÜBERNEHMEN commit + push auf `agents/data-quality-fixes`; Eintrag ins Log unten.

## Leitplanken

- Eine Ebene pro Runde; keine Runde ohne messbares Kriterium.
- Nur öffentlich auffindbare, berufliche Informationen über Gründer (Werdegang, Rollen, Publikationen). Keine
  privaten Kontaktdaten, kein Login-Scraping: LinkedIn nur über Suchtreffer/Snippets (Brave), nicht über
  eingeloggte Seiten.
- Brave-Budget: ~2.000 Anfragen/Monat, max. ~250 pro Runde; Verbrauch im Log.
- Nicht anfassen ohne Rückfrage: Gewichte 0,40/0,25/0,35 (wartet auf Team), `models.py` nur additiv.
- Stopp, wenn zwei Runden in Folge VERWORFEN werden, das Brave-Budget unter 300 fällt oder der Stratege keine
  Ebene mit klarem Nutzen mehr findet.

## Log

| Runde | Ebene | Urteil | Wirkung | Brave |
|---|---|---|---|---|
| 0 | Basis: Website-Matching, DB-Prüfung, Kalibrierung (Gate 1+2) | – | siehe `reports/final_gate.md` | ~170 |
| 1 | Team-Zusammensetzung (LinkedIn-Snippets, idw/Presse); CV-Bewertung vorab verworfen (Snippets ohne Werdegang) | NACHBESSERN (nur MAJOR 1: kein Malus aus OpenAlex-Fallback), dann Loop beendet (Deadline) | Personen 17→24/52, Mix 0→5/52 (Ziel 30/10 verfehlt), Precision Zuordnung 80 % streng, Spearman 0,40; `reports/loop/round-1-check.md` | 115 |

**Loop beendet am 21.11.2026** wegen Deadline; Fokus wechselt auf das Demo-Dashboard. Nächste sinnvolle Ebene laut
Stratege: Firmensignale aus LinkedIn-Post-Snippets (Runde 2, nicht gestartet).
