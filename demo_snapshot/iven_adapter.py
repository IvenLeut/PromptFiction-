"""Iven's company search (category "Company Radar", higher risk) in the dashboard's display format.

Source: Iven's reference run `data/mvp/jury-reference.json` (package `mvp/`, rule set `early-stage.2`,
config/early_stage.v2.json). His values are authoritative: this adapter copies scores, criterion points,
stage, risk label, queue and texts 1:1 and never recalculates them. The texts (product description,
investment hypothesis, why-now, first question) come from `mvp.briefs.brief_for(..., live=True)`, exactly
as `mvp/export_jury.py` wrote `Ergebnisse/Longlist.csv`.

Direction: Iven has no numeric risk score. `risk` is his text label (e.g. "Prüfbedarf: Marktvalidierung")
and is shown as a label; `company_score` (Produkt & Technologie) and `market_score` (Kunde & Nutzen) are
"higher is better", like ours. The two rankings come from different rule sets and are never merged.

    python -m demo_snapshot.build_snapshot          # builds both snapshots (ours + iven_companies.json)
    python -m demo_snapshot.iven_adapter            # only this one
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "mvp" / "jury-reference.json"
IVEN_PATH = Path(__file__).resolve().parent / "iven_companies.json"

CATEGORY = "Company Radar"
CATEGORY_LONG = "Company Radar · young GmbH/UG (higher risk)"
# Iven's queue labels stay German in the data (they must match Ergebnisse/Longlist.csv); `en()` renders them.
STATUS = {"ranked": "Bewertbar", "research": "Recherche offen", "excluded": "Außerhalb Suchprofil"}
FACT_LABELS = {
    "register": "Commercial register", "country": "Germany evidence", "project_link": "Funded-project link",
    "founding": "Founding", "technology": "Technical approach", "product": "Product", "buyer": "Customer type",
    "benefit": "Customer benefit", "team": "Team", "validation": "Development evidence", "description": "Description",
    "contact_email": "Company mailbox", "regulation": "Regulation", "seed_round": "Funding round",
    "service_business": "Service business", "late_round": "Later round", "inactive": "Inactive",
}
_LINKEDIN_PROFILE = re.compile(r"https://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/in/[^/?#\s]+/?$", re.I)

# --- English rendering of Iven's engine texts (display only) -----------------------------------------------
# His engine (mvp/) writes German, templated texts. The data stays 1:1 German (reproducibility check,
# Longlist.csv); the dashboard renders it with these exact mappings. Unknown text (e.g. website quotes,
# which are evidence) is returned unchanged.
TEXT_EN = {
    # queue / status, risk label, stage, HTGF fit
    "Bewertbar": "Scorable", "Recherche offen": "Research open", "Außerhalb Suchprofil": "Outside search profile",
    "Entwicklungs- und Marktvalidierung offen": "Development and market validation open",
    "Prüfbedarf: Marktvalidierung": "Needs review: market validation",
    "Prüfbedarf: Regulierung": "Needs review: regulation",
    "Finanzierungsphase offen": "Funding stage open", "Pre-Seed-Hinweis": "Pre-seed indication",
    "Prüfung offen": "Review open",
    "Potenziell passend; Phase/Technologie prüfen": "Potential fit; verify stage/technology",
    # criteria
    "Produkt & Technologie": "Product & technology", "Kunde & Nutzen": "Customer & benefit",
    "Entwicklungsnachweis": "Development evidence",
    "Offen; keine Ersatzpunkte.": "Open; no substitute points.",
    "30: allgemeine Unternehmen; 50: konkreter Kundentyp; +20: beschriebener Nutzen. Kein geschätzter TAM.":
        "30: generic businesses; 50: specific customer type; +20: described benefit. No estimated TAM.",
    "60: konkretes Produkt + technischer Ansatz; 75: Prototyp/PoC; 85: Pilot oder zahlende Kunden.":
        "60: specific product + technical approach; 75: prototype/PoC; 85: pilot or paying customers.",
    "50: eigener Entwicklungsnachweis; 60: zugeordnetes Forschungsprojekt; 70: Pilot/Studie; 85: zahlende Kunden (Selbstauskunft).":
        "50: own development evidence; 60: linked research project; 70: pilot/study; 85: paying customers (self-reported).",
    # reasons, gates, issues
    "Weniger als zwei bewertbare Dimensionen.": "Fewer than two scorable dimensions.",
    "Konkreter technischer Ansatz fehlt.": "No specific technical approach.",
    "Adressierter Kundentyp fehlt.": "No addressed customer type.",
    "Eigenes Produkt noch nicht belegt.": "Own product not yet evidenced.",
    "Zu wenige belegte Screening-Merkmale.": "Too few evidenced screening features.",
    "Unternehmensidentität noch nicht eindeutig belegt.": "Company identity not yet clearly evidenced.",
    "Quellenkonflikt oder Identitätsprüfung offen.": "Source conflict or identity check open.",
    "Branchenzuordnung noch offen.": "Sector assignment still open.",
    "Aktuelle Website-Prüfung fehlgeschlagen; historische Daten sind gekennzeichnet.":
        "Current website check failed; historical data is marked.",
    "Aktuelles Impressum stimmt nicht eindeutig mit gespeicherter Identität überein oder ist nicht erreichbar.":
        "Current imprint does not clearly match the stored identity or is unreachable.",
    "Dienstleistungs-/Agenturgeschäft: eigenes skalierbares Produkt prüfen.":
        "Service/agency business: verify an own scalable product.",
    "Gründungsdatum oder eindeutig passendes Gründungsjahr fehlt.":
        "Founding date or a clearly matching founding year is missing.",
    "Registergericht fehlt im Impressum; ergänzender Registerabgleich offen.":
        "Register court missing in imprint; additional register check open.",
    # next steps
    "Finanzierungsphase, Kapitalbedarf und nächsten Meilenstein klären.":
        "Clarify funding stage, capital need and next milestone.",
    "Technische Differenzierung und Rechte an der Technologie prüfen.":
        "Check technical differentiation and rights to the technology.",
    "Prototyp, technische Tests und Referenzkunden anfordern.":
        "Request prototype, technical tests and reference customers.",
    "Gründerrollen und relevante Erfahrung prüfen.": "Check founder roles and relevant experience.",
    # texts of mvp.briefs
    "Eine zusammenhängende Produktbeschreibung ist noch offen.": "A coherent product description is still open.",
    "Noch keine belastbare Investmenthypothese. Zuerst die ausgewiesenen offenen Punkte klären.":
        "No robust investment hypothesis yet. Resolve the listed open points first.",
    "Welcher Anwender setzt die Lösung bereits ein und welches messbare Ergebnis hat er dabei erreicht?":
        "Which user already deploys the solution, and what measurable result have they achieved?",
    "Welcher konkrete Anwender würde heute für die Lösung bezahlen, und woran misst er den Nutzen?":
        "Which specific user would pay for the solution today, and how do they measure the benefit?",
    "Welcher Primärbeleg klärt den wichtigsten offenen Punkt im Screening?":
        "Which primary source resolves the most important open point in the screening?",
    "Zahlender Kundentyp offen. Den ersten konkreten Anwender identifizieren.":
        "Paying customer type open. Identify the first specific user.",
    # founding basis, source titles
    "GLEIF entity.creationDate; original business age not independently verified":
        "GLEIF entity.creationDate; original business age not independently verified",
    "Datierter Gründungsabschnitt der Unternehmenswebsite; Selbstauskunft, kein Registerdatum.":
        "Dated founding section of the company website; self-reported, not a register date.",
    "GLEIF Identität · Quellenstand": "GLEIF identity · source status",
}
# Short keywords his rules extracted (customer type, approach, validation, team); exact match only.
TERMS_EN = {
    "Unternehmen": "companies", "Hersteller": "manufacturers", "Betriebe": "businesses", "Architekten": "architects",
    "Pilotkunden": "pilot customers", "Prototypen": "prototypes", "Prototyp": "prototype",
    "Algorithmus": "algorithm", "KI-Telefonassistent": "AI phone assistant", "KI-Assistenten": "AI assistants",
    "KI-gestützter": "AI-powered", "3D Maus": "3D mouse", "Software Plattform": "software platform",
    "Zugeordnetes EXIST-Forschungs-/Gründungsprojekt": "Linked EXIST research/founding project",
    "Geschäftsführer": "Managing director", "Geschäftsführerin": "Managing director",
    "GESCHÄFTSFÜHRER": "Managing director", "Gründer": "Founder", "Gründerduo": "Founding duo",
    "IT-Dienstleister": "IT service provider", "individuelle Systeme": "custom systems",
    "Regulatorik": "regulation", "Regulatorische": "regulatory", "regulatorischen": "regulatory",
    "Automatisierung": "automation", "Automatisierungen": "automations", "Automatisierte": "automated",
    "automatisieren": "automate", "Effizienz": "efficiency", "effizient": "efficient", "effiziente": "efficient",
    "Verbesserung": "improvement", "verbessern": "improve", "sparen": "save",
}
FACT_BASIS_EN = {
    "rule_extraction": "rule extraction", "gleif_snapshot": "GLEIF snapshot", "gleif_live": "GLEIF live",
    "company_self_description": "company self-description", "public_business_contact": "public business contact",
    "legal_imprint": "legal imprint", "german_court_and_address": "German court and address",
    "project_name_grant_and_institution": "project name, grant and institution", "company_timeline": "company timeline",
    "institution_link": "institution link", "linked_research_project": "linked research project",
}


def _term(text: str) -> str:
    return TERMS_EN.get(text, text)


_TEMPLATES = [
    (re.compile(r"Wenn sich der Ansatz „(?P<a>.*?)“ für „(?P<b>.*?)“ in einem wiederkehrenden Ablauf bewährt, könnte "
                r"daraus ein bezahlbares Produkt werden\. Entscheidend sind messbarer Nutzen, der Aufwand für die "
                r"Einführung und ein Vergleich mit dem heutigen Prozess\.", re.S),
     lambda m: f"If the approach “{_term(m['a'])}” proves itself for “{_term(m['b'])}” in a recurring workflow, it "
               "could become a product customers pay for. What matters: measurable benefit, adoption effort and a "
               "comparison with today's process."),
    (re.compile(r"Die Firmenquelle nennt „(?P<a>.*?)“\. Im Erstgespräch Einsatz, messbares Ergebnis und einen "
                r"möglichen Übergang zu bezahlter Nutzung prüfen\.", re.S),
     lambda m: f"The company source mentions “{_term(m['a'])}”. In the first call, check the deployment, the "
               "measurable result and a possible path to paid use."),
    (re.compile(r"Die Quellen zeigen ein Produkt für „(?P<b>.*?)“ und den technischen Ansatz „(?P<a>.*?)“\. Für ein "
                r"Erstgespräch zuerst nach einem realen Anwendungsfall und dem Entwicklungsstand fragen\.", re.S),
     lambda m: f"The sources show a product for “{_term(m['b'])}” using the technical approach “{_term(m['a'])}”. "
               "In a first call, ask for a real use case and the development status first."),
    (re.compile(r"Prüfhypothese: Ein eigenes Technologieprodukt adressiert (?P<b>.*?)\. Ein Gespräch lohnt sich, wenn "
                r"technische Differenzierung und wirtschaftlicher Kundennutzen bestätigt werden\.", re.S),
     lambda m: f"Working hypothesis: an own technology product addresses {_term(m['b'])}. A call is worthwhile if "
               "technical differentiation and economic customer benefit are confirmed."),
    (re.compile(r"Offen im aktuellen Screening\. (?P<r>.*)", re.S),
     lambda m: "Open in the current screening. " + en(m["r"])),
    (re.compile(r"Genannte Zielgruppe · (?P<b>.*?)\. Belegstelle: (?P<q>„.*“)", re.S),   # quote stays (evidence)
     lambda m: f"Stated target group · {_term(m['b'])}. Evidence: {m['q']}"),
    (re.compile(r"(?P<a>\d{4}-\d{2}-\d{2}) bis (?P<b>\d{4}-\d{2}-\d{2})"), lambda m: f"{m['a']} to {m['b']}"),
]
_SENTENCE = re.compile(r"(?<=\.)\s+")


def en(text):
    """English rendering of one of Iven's engine texts; unknown text (quotes, names) is returned unchanged."""
    if not isinstance(text, str) or not text:
        return text
    if text in TEXT_EN:
        return TEXT_EN[text]
    if text in TERMS_EN:
        return TERMS_EN[text]
    for pattern, render in _TEMPLATES:
        if m := pattern.fullmatch(text):
            return render(m)
    sentences = _SENTENCE.split(text.strip())
    if len(sentences) > 1 and all(s in TEXT_EN for s in sentences):   # concatenated gate sentences
        return " ".join(TEXT_EN[s] for s in sentences)
    return text


def english(company: dict) -> dict:
    """A display copy of one company record with Iven's engine texts in English (numbers and IDs untouched)."""
    c = dict(company)
    for key in ("status", "risk", "stage", "htgf_fit", "summary", "thesis", "why", "question", "segment", "gate",
                "hypothesis"):
        c[key] = en(company.get(key))
    c["reasons"] = [en(x) for x in company.get("reasons", [])]
    c["next_steps"] = [en(x) for x in company.get("next_steps", [])]
    c["issues"] = [en(x) for x in company.get("issues", [])]
    c["criteria"] = [dict(x, label=en(x.get("label")), reason=en(x.get("reason")),
                          facts=[FACT_LABELS.get(f, f) for f in x.get("facts", [])]) for x in company.get("criteria", [])]
    c["facts"] = [dict(x, label=FACT_LABELS.get(x["key"], x["label"]), value=en(x.get("value")),
                       basis=FACT_BASIS_EN.get(x.get("basis"), x.get("basis"))) for x in company.get("facts", [])]
    c["founding"] = dict(company["founding"], basis=en(company["founding"].get("basis")))
    c["team"] = [dict(t, role=en(t.get("role"))) for t in company.get("team", [])]
    c["sources"] = [dict(s, title=en(s.get("title"))) for s in company.get("sources", [])]
    return c


def _source(s) -> dict:
    return {"title": s.title, "url": s.url, "retrieved_at": s.retrieved_at, "kind": s.kind}


def company_record(rank: int, item, *, live: bool) -> dict:
    """One assessment as a plain display dict. Values are copied, not recomputed."""
    from mvp.briefs import brief_for
    d = item.dossier
    brief = brief_for(item, live=live)
    founding = d.facts.get("founding")
    return {
        "id": d.id, "rank": rank, "name": d.name, "website": d.website, "sectors": list(d.sectors),
        "queue": item.queue, "status": STATUS[item.queue],
        # Iven's numbers 1:1 (None stays None: "unknown is never a numeric default").
        "score": item.score, "score_upper": item.score_upper,
        "company_score": item.company_score, "market_score": item.market_score,
        "validation_score": next((c.points for c in item.criteria if c.key == "validation"), None),
        "risk": item.risk, "stage": item.stage, "coverage": item.coverage, "htgf_fit": item.htgf_fit,
        "criteria": [c.model_dump(mode="json") for c in item.criteria],
        "reasons": list(item.reasons), "next_steps": list(item.next_steps), "hypothesis": item.hypothesis,
        # Texts as in Ergebnisse/Longlist.csv and the profile pages.
        "summary": brief.summary, "thesis": brief.thesis, "why": brief.why, "question": brief.question,
        "segment": brief.segment, "gate": brief.gate,
        "email": brief.email[0] if brief.email else None,
        "founding": {"earliest": str(d.earliest_founding) if d.earliest_founding else None,
                     "latest": str(d.latest_founding) if d.latest_founding else None,
                     "basis": d.founding_basis,
                     "quote": founding.quote if founding else None,
                     "url": founding.source_url if founding else None},
        "identity_status": d.identity_status, "refresh_status": d.refresh_status,
        "project_ids": list(d.project_ids), "issues": list(d.issues),
        "facts": [{"key": k, "label": FACT_LABELS.get(k, k), "value": f.value, "quote": f.quote,
                   "url": f.source_url, "basis": f.basis} for k, f in d.facts.items()],
        "team": [{"name": t.name, "role": t.role, "biography": t.biography, "source_url": t.source.url,
                  "linkedin": t.profile_url if t.profile_url and _LINKEDIN_PROFILE.match(t.profile_url) else None}
                 for t in d.team_evidence],
        "sources": [_source(s) for s in d.sources],
        "market_comparisons": [{"name": m.name, "text": m.text, "url": m.source.url} for m in d.market_comparisons],
    }


def build_iven(reference: Path = REFERENCE, out: Path = IVEN_PATH) -> Path:
    """Write `iven_companies.json` from Iven's reference run (personal e-mail addresses redacted)."""
    from demo_snapshot.build_snapshot import redact_personal_emails
    from mvp.contracts import Run
    from mvp.scoring import ranked
    run = Run.model_validate_json(reference.read_bytes())
    order = ranked(run.assessments)
    if [a.dossier.id for a in order] != [a.dossier.id for a in run.assessments]:
        raise ValueError("Reference run is not stored in Company Radar rank order.")
    live = run.options.mode == "live"   # mvp/export_jury.py: brief_for(item, live=run.options.mode == "live")
    companies = [company_record(i, item, live=live) for i, item in enumerate(order, 1) if item.queue in ("ranked", "research")]
    payload = {
        "kind": "iven_companies", "category": CATEGORY, "category_long": CATEGORY_LONG,
        "origin": "Company Radar (mvp/, branch feature/founderradar-investment-cockpit)",
        "rule_version": run.rule_version, "schema_version": run.schema_version, "run_id": run.id,
        "as_of": str(run.options.as_of), "source_snapshot_date": run.source_snapshot_date,
        "max_age_months": run.options.max_age_months, "sectors": list(run.options.sectors),
        "input_hash": run.input_hash, "counts": dict(run.counts),
        "reference_file": str(reference.relative_to(ROOT)) if reference.is_relative_to(ROOT) else reference.name,
        "weights": {c.key: c.weight for c in order[0].criteria} if order else {},
        "companies": companies,
    }
    out.write_text(redact_personal_emails(json.dumps(payload, ensure_ascii=False, indent=1)) + "\n", encoding="utf-8")
    return out


@lru_cache(maxsize=1)
def load_iven() -> dict | None:
    """The built display data, or None if `iven_companies.json` is missing. Callers must not mutate it."""
    if not IVEN_PATH.exists():
        return None
    return json.loads(IVEN_PATH.read_text(encoding="utf-8"))


def origin_line(data: dict) -> str:
    """'Company Radar, rule set early-stage.2, as of 21.11.2026'."""
    y, m, d = data["source_snapshot_date"].split("-")
    return f"Company Radar, rule set {data['rule_version']}, as of {d}.{m}.{y}"


if __name__ == "__main__":
    path = build_iven()
    print(f"{path} ({path.stat().st_size // 1024} KB)")
