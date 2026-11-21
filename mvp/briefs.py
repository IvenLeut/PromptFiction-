"""Source-linked company briefs and an explicitly requested editorial draft."""
from dataclasses import dataclass
from datetime import date
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote, urlencode, urlsplit

from bs4 import BeautifulSoup

from mvp.contracts import MarketObservation
from mvp.web import canonical_host


CATALOG = json.loads(
    (Path(__file__).resolve().parents[1] / "config/company_briefs.json").read_text(encoding="utf-8")
)
CHECKED = "2026-11-21"
MAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", re.ASCII)


@dataclass(frozen=True)
class Brief:
    headline: str
    summary: str
    why: str
    thesis: str
    segment: str
    buyer: str
    adoption: str
    sizing: str
    question: str
    gate: str
    intro: str
    sources: list
    alternatives: list
    signal: tuple
    email: tuple | None
    editorial: bool


def http_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def catalog_entry(dossier):
    entry = CATALOG.get(dossier.id)
    if entry and dossier.website and entry["host"] == canonical_host(dossier.website):
        return entry
    return None


def collect_market_comparisons(dossier, web):
    """Check configured comparison URLs; store only current source observations."""
    entry = catalog_entry(dossier)
    if not entry:
        return
    dossier.market_comparisons = []
    for label, _, url in entry["alternatives"]:
        if not http_url(url):
            continue
        page = web.try_page(url, "market_comparison")
        if not page or canonical_host(page["url"]) != canonical_host(url):
            continue
        soup = BeautifulSoup(page["html"], "html.parser")
        metadata = soup.find("meta", attrs={"name": "description"})
        text = metadata.get("content", "") if metadata else ""
        if not text:
            headline = soup.find("h1")
            text = headline.get_text(" ", strip=True) if headline else page["source"].title
        if text:
            dossier.market_comparisons.append(MarketObservation(
                name=label, text=" ".join(text.split()[:24]), source=page["source"],
            ))


def brief_for(item, *, live=False):
    dossier = item.dossier
    entry = catalog_entry(dossier)
    if entry and not live:
        return Brief(**{key: value for key, value in entry.items() if key != "host"}, editorial=True)

    def value(key, default):
        return dossier.facts[key].value if key in dossier.facts else default

    has_buyer = "buyer" in dossier.facts
    buyer = value("buyer", "Zahlender Kundentyp offen")
    benefit = value("benefit", "Kundennutzen noch zu belegen")
    technology = value("technology", "Technischer Ansatz offen")
    validation = dossier.facts.get("validation")
    sources = [(source.title, source.url) for source in dossier.sources if http_url(source.url)]
    description = dossier.facts.get("description")
    if description:
        sources.sort(key=lambda source: source[1] != description.source_url)
    email = dossier.facts.get("contact_email")
    alternatives = [(observation.name, observation.text, observation.source.url)
                    for observation in dossier.market_comparisons]
    alternatives.append(("Bestehender Kundenprozess",
                         "Werkzeuge, Aufwand und Kosten des heutigen Prozesses im Erstgespräch erfassen.", None))
    if item.queue == "ranked" and validation and validation.basis != "linked_research_project":
        why = (f"Die Firmenquelle nennt „{validation.value}“. Im Erstgespräch Einsatz, messbares Ergebnis "
               "und einen möglichen Übergang zu bezahlter Nutzung prüfen.")
        question = "Welcher Anwender setzt die Lösung bereits ein und welches messbare Ergebnis hat er dabei erreicht?"
    elif item.queue == "ranked":
        why = (f"Die Quellen zeigen ein Produkt für „{buyer}“ und den technischen Ansatz „{technology}“. "
               "Für ein Erstgespräch zuerst nach einem realen Anwendungsfall und dem Entwicklungsstand fragen.")
        question = "Welcher konkrete Anwender würde heute für die Lösung bezahlen, und woran misst er den Nutzen?"
    else:
        why = "Offen im aktuellen Screening. " + (item.reasons[0] if item.reasons else item.risk)
        question = "Welcher Primärbeleg klärt den wichtigsten offenen Punkt im Screening?"

    thesis = (
        f"Wenn sich der Ansatz „{technology}“ für „{buyer}“ in einem wiederkehrenden Ablauf bewährt, "
        "könnte daraus ein bezahlbares Produkt werden. Entscheidend sind messbarer Nutzen, "
        "der Aufwand für die Einführung und ein Vergleich mit dem heutigen Prozess."
        if item.queue == "ranked" else item.hypothesis
    )
    buyer_evidence = dossier.facts.get("buyer")
    benefit_evidence = dossier.facts.get("benefit")
    segment = (f"Genannte Zielgruppe · {buyer}. Belegstelle: „{buyer_evidence.quote}“"
               if buyer_evidence else "Zahlender Kundentyp offen. Den ersten konkreten Anwender identifizieren.")
    metrics = (f"Die Website nennt als Nutzensignal „{benefit}“. Im Gespräch die Ausgangslage, den "
               "gemessenen Effekt und die Zahlungsbereitschaft erfragen."
               if benefit_evidence else "Ein Kundenbeispiel mit messbarem Nutzen und Ausgangswert erfragen.")
    return Brief(
        headline=", ".join(dossier.sectors) or "Unternehmensprofil",
        summary=value("description", "Eine zusammenhängende Produktbeschreibung ist noch offen."),
        why=why,
        thesis=thesis,
        segment=segment,
        buyer=(f"Bei „{buyer}“ Nutzung, Budgetverantwortung und Kaufentscheidung getrennt erfragen."
               if has_buyer else "Budgetverantwortung und Beschaffungsweg sind offen."),
        adoption=metrics,
        sizing="Zugängliche Kunden × realisierbarer Jahreserlös je Kunde. Beide Größen sind noch zu recherchieren.",
        question=question,
        gate=" ".join(item.reasons[:3] if item.queue != "ranked" else item.next_steps[:2]),
        intro=f"Wir würden gerne mehr über den Produktstand bei {dossier.name} und Ihre ersten Kundenerfahrungen erfahren.",
        sources=sources,
        alternatives=alternatives,
        signal=(validation.value, validation.quote, validation.source_url) if validation else
               ("Nachweis offen", "Referenz, Pilotprojekt oder unabhängiger Test gesucht.", None),
        email=(email.value, email.source_url) if email and MAIL.fullmatch(email.value) else None,
        editorial=False,
    )


def mailto(recipient, subject, body):
    recipient = recipient.strip()
    if recipient and not MAIL.fullmatch(recipient):
        raise ValueError("Bitte eine einzelne gültige E-Mail-Adresse eingeben.")
    if "\r" in subject or "\n" in subject:
        raise ValueError("Der Betreff muss in einer Zeile stehen.")
    body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    query = urlencode({"subject": subject, "body": body}, quote_via=quote)
    return "mailto:" + quote(recipient, safe="@") + "?" + query


def report_html(item, brief, as_of: date, *, insight=None):
    def link(label, url):
        return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>' if http_url(url) else escape(label)

    def block(title, text):
        return f"<h2>{escape(title)}</h2><p>{escape(text)}</p>"

    score = f"{item.score:.1f}/100" if item.score is not None else "Offen"
    sections = "".join(block(title, content) for title, content in (
        ("Kurzbeschreibung", brief.summary), ("Warum jetzt sprechen?", brief.why),
        ("Investmenthypothese", brief.thesis), ("Einstiegsmarkt", brief.segment),
        ("Kaufentscheidung", brief.buyer), ("Markteintritt", brief.adoption),
        ("Marktgröße prüfen", brief.sizing), ("Erstgespräch", brief.question),
        ("Prüfbedarf", brief.gate),
    ))
    sources = "".join(f"<li>{link(label, url)}</li>" for label, url in brief.sources)
    alternatives = "".join(f"<li>{link(name, url)} · {escape(detail)}</li>" for name, detail, url in brief.alternatives)
    if insight:
        ai = insight.result.analysis
        evidence = {line.id: line.source_url for line in insight.evidence}

        def sourced(claim):
            links = " ".join(link(key, evidence[key]) for key in dict.fromkeys(claim.sources) if evidence.get(key))
            return escape(claim.text) + (" · " + links if links else "")

        sections = (
            f"<h2>Projekt-KI · {escape(insight.result.model)}</h2>"
            f"<p><small>Gespeicherter KI-Stand · {insight.result.created_at:%d.%m.%Y}</small></p>"
            f"<h3>Kurzbeschreibung</h3><p>{sourced(ai.summary)}</p>"
            "<h3>Stärken</h3><ul>" + "".join(f"<li>{sourced(point)}</li>" for point in ai.strengths)
            + "</ul><h3>Prüfrisiken</h3><ul>" + "".join(f"<li>{sourced(point)}</li>" for point in ai.risks)
            + f"</ul><h3>Investmenthypothese</h3><p>{sourced(ai.thesis)}</p>"
            f"<h3>Markt</h3><p>{sourced(ai.market)}</p><h3>Fazit</h3><p>{sourced(ai.conclusion)}</p>" + sections
        )
        if ai.founders:
            sections += "<h2>Gründerteam</h2>"
            for person in ai.founders:
                sections += f"<h3>{escape(person.name)}</h3>"
                for label, claim in (("Rolle", person.role), ("Ausbildung", person.education), ("Erfahrung", person.experience)):
                    sections += f"<p><strong>{label}</strong> · {sourced(claim) if claim else 'offen'}</p>"
    elif item.dossier.team_evidence:
        sections += "<h2>Gründerteam</h2>"
        for person in item.dossier.team_evidence:
            if person.name:
                sections += f"<h3>{escape(person.name)}</h3><p>{escape(person.role)}</p>"
                sections += f"<p>{escape(person.biography)} · {link('Firmenquelle', person.source.url)}</p>"
    name = escape(item.dossier.name)
    origin = f"Redaktionell recherchiert am {CHECKED}" if brief.editorial else "Automatisch aus Belegen abgeleitet"
    return f"""<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FounderRadar | {name}</title>
<style>body{{font:16px/1.6 system-ui;color:#171a19;margin:0}}main{{max-width:760px;margin:auto;padding:3rem 1.5rem}}
header{{border-bottom:1px solid #dedede;margin-bottom:2rem}}h1{{font-size:clamp(2.4rem,7vw,4.3rem);line-height:1;letter-spacing:-.06em}}
h2{{font-size:1.18rem;margin:1.55rem 0 .3rem}}p{{margin:.3rem 0 .8rem}}small{{color:#535d59}}a{{color:#1e5e4e}}
.badge{{display:inline-block;background:#e7f4ef;padding:.35rem .7rem;border-radius:1rem}}
@media print{{main{{padding:0}}h2{{break-after:avoid}}}}</style>
<main><header><strong>FounderRadar / Deep Dive</strong><h1>{name}</h1><p>{escape(brief.headline)}</p>
<p class="badge">Screening {score}</p><p><small>Analyse {as_of.isoformat()} · {origin}</small></p></header>
{sections}<h2>Alternativen</h2><ul>{alternatives}</ul><h2>Quellen</h2><ul>{sources}</ul></main></html>"""
