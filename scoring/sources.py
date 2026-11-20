"""Dossiers laden: JSON-Datei, Ordner mit JSON-Dateien oder SQLite-DB der Sourcing-Pipeline (Plan v4)."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path


def load_dossiers(path):
    path = Path(path)
    if path.is_dir():
        out = []
        for f in sorted(path.glob("*.json")):
            try:
                out.extend(_from_json(f))
            except ValueError as e:  # eine kaputte Datei kostet nicht die anderen
                print("WARNUNG: übersprungen – %s" % e, file=sys.stderr)
        return out
    if path.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
        return from_sqlite(path)
    return _from_json(path)


def _from_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError) as e:
        raise ValueError("%s: nicht lesbar (%s)" % (path, type(e).__name__))
    if isinstance(data, dict):
        data = next((data[k] for k in ("leads", "dossiers") if k in data), [data])
    if not isinstance(data, list):
        raise ValueError("%s: erwartet wird ein Dossier oder eine Liste von Dossiers" % path)
    return data


EXIST_TYPEN = {"exist": "EXIST", "exist_projekt": "EXIST", "exist_forschungstransfer": "EXIST-Forschungstransfer",
               "exist_gruendungsstipendium": "EXIST-Gründungsstipendium", "exist_gründungsstipendium": "EXIST-Gründungsstipendium"}


def _summe_eur(evidence):
    """Genau ein eindeutiger Betrag in deutscher Schreibweise ('650.000 EUR', '1.200.000,00 €', '800000 EUR') -> ganze Euro.

    Mehrere verschiedene Beträge oder jede andere Schreibweise (650,000 / 1 200 000 / 12.50) -> None. Es wird nichts geraten.
    """
    s = str(evidence or "")
    if re.search(r"(?:EUR|€)\s*\d", s):  # Betrag hinter dem Währungszeichen: nicht eindeutig lesbar
        return None
    zahlen = re.findall(r"[\d][\d.,' \u00a0]*(?=\s*(?:EUR|€))", s)
    werte = set()
    for z in zahlen:
        z = z.strip()
        if not re.fullmatch(r"(\d{1,3}(\.\d{3})+|\d+)(,\d{2})?", z):
            return None
        werte.add(int(z.split(",")[0].replace(".", "")))
    return werte.pop() if len(werte) == 1 else None


def _bool(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return bool(x)
    s = str(x).strip().lower()
    return True if s in ("1", "true", "ja", "yes") else False if s in ("0", "false", "nein", "no") else None


def from_sqlite(path):
    """Tabellen leads / signals / team (Plan v4, Abschnitt 5) -> Dossiers.

    Fehlende Spalten bleiben None. Reifegrad, IP, Partner, Markt und Produkttyp stehen nicht im
    v4-Schema; ohne sie bleiben die betroffenen Kriterien neutral. Als Beschreibungstext dient nur
    der Textausschnitt des frühesten Signals, mit genau dessen URL als Quelle.
    """
    if not Path(path).is_file():
        raise ValueError("%s: Datei nicht gefunden" % path)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        return _read(con, path)
    except sqlite3.Error as e:
        raise ValueError("%s: keine lesbare SQLite-DB (%s)" % (path, e))
    finally:
        con.close()


def _read(con, path):
    if True:
        tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "leads" not in tabellen:
            raise ValueError("%s: Tabelle 'leads' fehlt" % path)
        signals = [dict(r) for r in con.execute("SELECT * FROM signals")] if "signals" in tabellen else []
        team = [dict(r) for r in con.execute("SELECT * FROM team")] if "team" in tabellen else []
        dossiers = []
        for row in con.execute("SELECT * FROM leads"):
            lead = dict(row)
            name = str(lead.get("name") or "")
            roh_id = lead.get("lead_id")
            lead_id = str(roh_id) if roh_id not in (None, "") else re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            sig = sorted((s for s in signals if lead_id and str(s.get("lead_id")) == lead_id), key=lambda s: (str(s.get("date")), str(s.get("url"))))
            de = next((s for s in sig if s.get("source") in ("foekat", "impressum") and s.get("url") and s.get("evidence")), None)
            foerderung, kennzeichen = [], set()  # EXIST nur bei bekanntem Signal-Typ oder EXIST-Förderkennzeichen (03EF…/03EG…)
            for s in sig:
                typ = str(s.get("type") or "").strip().lower()
                fkz = re.search(r"(?<![A-Za-z0-9])03E([FG])[A-Za-z0-9]+", str(s.get("evidence") or "") + " " + str(s.get("url") or ""))
                programm = EXIST_TYPEN.get(typ) or ({"F": "EXIST-Forschungstransfer", "G": "EXIST-Gründungsstipendium"}[fkz.group(1)] if fkz else None)
                if fkz and fkz.group(0) in kennzeichen:
                    continue  # dieselbe Förderung über mehrere Signale nur einmal
                if programm or s.get("source") == "foekat":
                    kennzeichen.update([fkz.group(0)] if fkz else [])
                    foerderung.append({"programm": programm or "Förderprojekt", "summe_eur": _summe_eur(s.get("evidence")),
                                       "start": s.get("date"), "quelle": s.get("url")})
            erster = next((s for s in sig if s.get("evidence") and s.get("url")), None)
            dossiers.append({
                "lead_id": lead_id or None,
                "name_unternehmen": {"wert": name, "quelle": lead.get("impressum_url") or (erster or {}).get("url")},
                "beschreibung_rohtext": {"wert": str(erster["evidence"]), "quelle": erster["url"]} if erster else None,
                "deutschland_beleg": {"wert": str(de["evidence"]), "quelle": de["url"], "datum": de.get("date")} if de else None,
                "website": lead.get("website") or None,
                "branche": lead.get("htgf_bereich"),
                "rechtsform": {"wert": lead.get("rechtsform"), "quelle": lead.get("impressum_url")} if lead.get("rechtsform") else None,
                "noise_class": lead.get("noise_class"),
                "match_confidence": lead.get("match_confidence"),
                "in_databases": _bool(lead.get("in_databases")),
                "first_db_date": lead.get("first_db_date"),
                "team": [{"name": t.get("name"), "rolle": t.get("rolle"), "institut": t.get("institut"),
                          "openalex": t.get("openalex_url"), "papers_im_feld": t.get("papers_im_feld")}
                         for t in team if lead_id and str(t.get("lead_id")) == lead_id],
                "foerderung": foerderung,
                "signals": [{"typ": s.get("type") or s.get("source"), "url": s.get("url"), "datum": s.get("date")} for s in sig],
                "source_url": (erster or {}).get("url"),
            })
        return dossiers
