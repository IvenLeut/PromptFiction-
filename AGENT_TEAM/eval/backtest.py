"""Earliness-Backtest (T3): Wie früh liefert der Förderkatalog ein Signal gegenüber Presse und Datenbanken?

Für jede Firma aus ``reference_companies.json``:

1. EXIST-Vorhaben im Förderkatalog-Export (``sourcing.foekat_export.export_rows``, alle 03EF/03EG ab 2014,
   über den Cache ``.cache/context.db``). Das FKZ muss existieren und der Firmenname im Thema stehen,
   sonst gilt die Firma als nicht erkannt. Datum unseres Signals = Projektbeginn.
2. Was hätte unser Sourcing damals daraus gemacht? ``sourcing.mapping.map_project`` mit Stichtag
   Projektbeginn + 30 Tage liefert Branche und Priorität (0–100) wie im heutigen Lauf.
3. Erste archivierte Crunchbase-/Dealroom-Profilseite über die Wayback-CDX-API
   (``context.wayback.web_history_lookup`` mit den Standard-Slugs, dazu optional ``extra_slugs``).
4. Erste öffentliche Finanzierungsmeldung: handrecherchiert, mit URL in der Referenzdatei.

Vorsprung = Monate vom Projektbeginn bis zum frühesten externen Sichtbarkeitsdatum
(min(Finanzierungsmeldung, erste DB-Profilaufnahme)). "Früh erkannt" = Vorsprung > 0.

Aufruf::

    .venv/bin/python AGENT_TEAM/eval/backtest.py          # Netz nur für fehlende Cache-Einträge
    .venv/bin/python AGENT_TEAM/eval/backtest.py --offline  # nur Cache, fehlende CDX-Antworten = unbekannt

Ergebnis: ``AGENT_TEAM/eval/backtest.json``. Der bestehende Code wird nur importiert, nicht verändert.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context.cache import Cache  # noqa: E402
from context.http import FetchError, cache_key, get_json  # noqa: E402
from context import wayback  # noqa: E402
from sourcing.foekat_export import export_rows  # noqa: E402
from sourcing.mapping import map_project  # noqa: E402
from context.foekat import detail_url  # noqa: E402

HERE = Path(__file__).resolve().parent
REFERENCES = HERE / "reference_companies.json"
OUT = HERE / "backtest.json"
SINCE = date(2014, 1, 1)
DAYS_PER_MONTH = 30.4375

BIAS = [
    "Survivorship: Die Referenzliste enthält nur Firmen, die später bekannt wurden und Geld eingesammelt "
    "haben. Sie misst, wie früh das Signal bei Gewinnern kommt, nicht wie viele EXIST-Projekte Gewinner werden "
    "(Precision). Dafür ist precision.py mit Handlabels da.",
    "Namensbias: Aufgenommen wurden nur Firmen, deren Name im Thema des EXIST-Vorhabens steht. Firmen, deren "
    "Vorhaben anders hieß, findet der Backtest nicht; die Trefferquote N/M ist deshalb nach oben verzerrt. "
    "Gleichzeitig ist das genau der Fall, den die Pipeline ohne Website-Match (T1) heute schon abdeckt.",
    "Katalog-Verzögerung: Als Signaldatum zählt der Projektbeginn. Wann der Eintrag tatsächlich öffentlich im "
    "Förderkatalog stand, ist nicht archiviert (kein Wayback für Detailseiten); realistisch einige Wochen bis "
    "Monate später. Der Vorsprung ist also eine Obergrenze um diese Verzögerung.",
    "Datenbank-Datum: Wayback archiviert Crunchbase/Dealroom lückenhaft; die erste Aufnahme ist eine Obergrenze "
    "für den Profilbeginn. Darum zählt zusätzlich die erste Finanzierungsmeldung, und gewertet wird das frühere "
    "der beiden Daten.",
    "Kleine Stichprobe (n<=13), handrecherchiert, überwiegend TUM/München (Pressedichte). Median statt "
    "Mittelwert; Einzelwerte stehen in companies[].",
    "Kein Replay der Pipeline: Das heutige Sourcing liest nur Vorhaben ab 2024. Der Backtest wendet dieselbe "
    "Abbildung (map_project, Priorität) auf die historischen Katalogzeilen an, aber nicht Kontext und Scoring.",
]


def months(a: date, b: date) -> float:
    return round((b - a).days / DAYS_PER_MONTH, 1)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def cache_only_fetch(cache: Cache):
    def fetch(url):
        hit = cache.get(cache_key(url))
        if hit is None:
            raise FetchError("web.archive.org: nicht im Cache (offline)")
        try:
            return json.loads(hit) if hit else []
        except ValueError as e:
            raise FetchError("web.archive.org: keine JSON-Antwort") from e
    return fetch


def online_fetch(cache: Cache):
    def fetch(url):
        return get_json(url, cache=cache, min_interval=wayback.MIN_INTERVAL, timeout=wayback.TIMEOUT)
    return fetch


def first_db_capture(name: str, extra_slugs: list[str], not_before: date, cache: Cache, offline: bool) -> dict:
    """Earliest archived Crunchbase/Dealroom profile (standard slugs via context.wayback + extra slugs)."""
    fetch = cache_only_fetch(cache) if offline else online_fetch(cache)
    lk = wayback.web_history_lookup(None, name, cache=cache, fetch=fetch, not_before=not_before)
    found: list[tuple[date, str]] = []
    if lk.fields.get("first_db_date"):
        ev = next((e for e in lk.evidence if e.field == "first_db_date"), None)
        found.append((lk.fields["first_db_date"], str(ev.url) if ev else ""))
    errors = list(lk.errors)
    queried = [p + s for s in wayback.slugs(name) for _, p in wayback.PROFILE_HOSTS]
    cutoff = date(not_before.year - 1, not_before.month, min(not_before.day, 28))
    for slug in extra_slugs:
        for _, prefix in wayback.PROFILE_HOSTS:
            target = prefix + slug
            queried.append(target)
            try:
                rows = fetch(wayback.cdx_url(target)) or []
            except FetchError as e:
                errors.append("wayback: %s" % e)
                continue
            hit = wayback._first_capture(rows)
            if hit and hit[0] < cutoff:
                errors.append("wayback: Profil %s älter als das Vorhaben, vermutlich Namensvetter" % target)
            elif hit:
                found.append((hit[0], wayback._archive_url(rows) or target))
    found.sort()
    status = "gefunden" if found else ("unbekannt" if any("nicht im Cache" in e or "HTTP" in e or "Error" in e
                                                           for e in errors) else "nicht_archiviert")
    return {
        "status": status,
        "date": found[0][0].isoformat() if found else None,
        "url": found[0][1] if found else None,
        "queried_profiles": queried,
        "errors": errors,
    }


def run(offline: bool = False, references: Path = REFERENCES, out: Path = OUT) -> dict:
    cache = Cache()
    ref = json.loads(references.read_text(encoding="utf-8"))
    export = export_rows(("03EF", "03EG"), SINCE, cache=cache, budget=120)
    by_fkz = {r.fkz: r for r in export.rows}
    companies = []
    for c in ref["companies"]:
        row = by_fkz.get(c["fkz"].upper())
        entry = {"name": c["name"], "fkz": c["fkz"], "htgf_portfolio": c.get("htgf", False)}
        if c.get("htgf_url"):
            entry["htgf_url"] = c["htgf_url"]
        if row is None or fold(c["name"])[:6] not in fold(row.thema):
            entry.update(detected=False, reason="FKZ fehlt im Export oder Name nicht im Thema")
            companies.append(entry)
            continue
        mapped = map_project([row], as_of=row.start + timedelta(days=30))
        lead, info = mapped if mapped else (None, None)
        signal = {
            "date": row.start.isoformat(), "programme": row.programme, "thema": row.thema,
            "institution": row.executing or row.recipient, "ort": row.executing_ort or row.recipient_ort,
            "amount_eur": float(row.amount) if row.amount is not None else None,
            "url": detail_url(row.fkz),
            "pipeline_priority": info.priority if info else None,
            "pipeline_industry": lead.industry.value if lead else None,
            "pipeline_reason": lead.prioritization_reason if lead else None,
        }
        db = first_db_capture(c["name"], c.get("extra_slugs", []), row.start, cache, offline)
        ff = c["first_funding"]
        ff_date = date.fromisoformat(ff["date"])
        externals = [("finanzierungsmeldung", ff_date, ff["url"])]
        if db["date"]:
            externals.append(("db_profil_wayback", date.fromisoformat(db["date"]), db["url"]))
        kind, first_ext, first_url = min(externals, key=lambda t: t[1])
        lead_m = months(row.start, first_ext)
        entry.update(
            detected=True, signal=signal, first_funding=ff, first_db_capture=db,
            founded=c.get("founded"),
            first_external={"kind": kind, "date": first_ext.isoformat(), "url": first_url},
            lead_months=lead_m,
            lead_months_vs_funding=months(row.start, ff_date),
            lead_months_vs_db=months(row.start, date.fromisoformat(db["date"])) if db["date"] else None,
            early=lead_m > 0,
            # Headline only with a dated, primary-sourced funding event: "obergrenze" (earlier undated round)
            # and "niedrig" (aggregator only) are listed but not counted.
            in_headline=ff.get("confidence") == "hoch",
            headline_note=None if ff.get("confidence") == "hoch" else
            "nicht in der Headline: Finanzierungsdatum mit Konfidenz '%s'" % ff.get("confidence"),
        )
        companies.append(entry)

    scored = [e for e in companies if e.get("detected") and e.get("in_headline")]
    leads = [e["lead_months"] for e in scored]
    early = [e for e in scored if e["early"]]
    total = len([c for c in companies if c.get("in_headline", True)])
    med = statistics.median(leads) if leads else None
    med_db = [e["lead_months_vs_db"] for e in scored if e["lead_months_vs_db"] is not None]
    db_found = [e for e in companies if e.get("detected") and e["first_db_capture"]["status"] == "gefunden"]
    by_prog = {}
    for e in scored:
        by_prog.setdefault(e["fkz"][:4].upper(), []).append(e["lead_months"])
    all_detected = [e["lead_months"] for e in companies if e.get("detected")]
    headline = ("%d/%d früh erkannt, Median %.0f Monate vor erster Finanzierungsmeldung/DB-Eintrag "
                "(Spanne %.0f–%.0f Monate; n=%d, Handauswahl bekannter Ausgründungen, Selektionsbias siehe bias)"
                % (len(early), total, med or 0, min(leads), max(leads), len(scored))) if leads else "keine Daten"
    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": __doc__.split("Aufruf::")[0].strip(),
        "headline": headline,
        "summary": {
            "companies": len(companies),
            "in_headline": total,
            "detected_in_catalogue": len([e for e in companies if e.get("detected")]),
            "early": len(early),
            "median_lead_months": med,
            "mean_lead_months": round(statistics.mean(leads), 1) if leads else None,
            "min_lead_months": min(leads) if leads else None,
            "max_lead_months": max(leads) if leads else None,
            "median_lead_months_by_programme": {k: {"n": len(v), "median": statistics.median(v)}
                                                for k, v in sorted(by_prog.items())},
            "sensitivity_all_detected": {"n": len(all_detected),
                                         "median": statistics.median(all_detected) if all_detected else None,
                                         "note": "inkl. OroraTech (Aggregator) und FMC (Obergrenze)"},
            "db_profile_found_in_wayback": len(db_found),
            "median_lead_months_vs_db_profile": statistics.median(med_db) if med_db else None,
            "htgf_portfolio": len([e for e in companies if e.get("htgf_portfolio")]),
            "pipeline_priority_median": statistics.median(
                [e["signal"]["pipeline_priority"] for e in scored if e["signal"]["pipeline_priority"] is not None]
            ) if scored else None,
            "export_complete": export.complete,
            "export_rows_since_2014": len(export.rows),
            "offline": offline,
        },
        "bias": BIAS,
        "excluded_from_headline": [e["name"] for e in companies if e.get("detected") and not e.get("in_headline")],
        "companies": companies,
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true", help="nur Cache, keine Netzabfragen an Wayback")
    ap.add_argument("--references", type=Path, default=REFERENCES)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    res = run(offline=a.offline, references=a.references, out=a.out)
    print(res["headline"])
    for e in res["companies"]:
        if e.get("detected"):
            print("  %-28s EXIST %s  ext %s (%s)  Vorsprung %5.1f M  Prio %s  DB %s"
                  % (e["name"], e["signal"]["date"], e["first_external"]["date"], e["first_external"]["kind"],
                     e["lead_months"], e["signal"]["pipeline_priority"], e["first_db_capture"]["status"]))
        else:
            print("  %-28s nicht erkannt: %s" % (e["name"], e["reason"]))
    print("->", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
