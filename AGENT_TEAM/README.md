# AGENT TEAM – Datenqualität (parallele Arbeitsbranch)

Dieser Ordner und die Branch `agents/data-quality-fixes` gehören dem Agent-Team. Sie laufen parallel zu
`chore/repo-cleanup` und werden erst nach Absprache mit dem Team gemergt.

Basis: `chore/repo-cleanup` @ fda6207 (21.11.2026).

## Ziele (aus dem Status-Check vom 21.11.2026)

| # | Problem | Owner-Agent | Dateien |
|---|---|---|---|
| T1 | Projektname → Website/Firma fehlt; ohne Website kein Impressum, keine Gründer, kein Noise-Filter | `matcher` | `context/website_match.py` (neu), Verdrahtung in `context/engine.py` + CLI |
| T2 | Scoring unterscheidet nicht: 733 Leads bei 48,7–53,7; Noise-Filter greift nie; kiutra (gegr. 2018, in DBs) als `seed` statt `zu_spaet`; Value Proposition generisch | `scorer` | `scoring/engine.py`, `scoring/scoring_config.yaml`, Scoring-Tests |
| T3 | Keine Kalibrierung / Precision@30 / Backtest | `evaluator` | `AGENT_TEAM/eval/` (neu) |

Datenschutz (Pseudonymisierung der Beispieldaten) ist für diese Runde bewusst ausgeklammert.

## Ablauf

1. Coder-Agents (Opus) arbeiten parallel in getrennten Dateien, jeweils mit Offline-Fixtures und Tests.
2. Prüf-Agents: Tests & Sanity (Sonnet), Faktencheck der gefundenen Websites (Sonnet), Final Gate gegen die
   HTGF-Jurykriterien (Opus). Befunde gehen zurück an die Coder, bis das Gate besteht.
3. Ergebnisse und Protokolle: `AGENT_TEAM/reports/`.
