"""Deterministic, evidence-gated screening. This is not an investment valuation."""
import calendar
import json
import re
from datetime import date
from pathlib import Path
from mvp.contracts import Assessment, Criterion, Dossier, RunOptions

CONFIG = json.loads((Path(__file__).resolve().parents[1]/'config/early_stage.v2.json').read_text(encoding='utf-8'))


def months_before(day, months):
    index = day.year*12 + day.month-1-months
    year, month = divmod(index, 12)
    return date(year, month+1, min(day.day, calendar.monthrange(year, month+1)[1]))


def assess(d: Dossier, options: RunOptions) -> Assessment:
    valid_sources={s.url for s in d.sources if s.url.startswith(('https://','http://')) and s.sha256 and s.retrieved_at[:10]<=options.as_of.isoformat()}
    facts = {k:v for k,v in d.facts.items() if v.source_url in valid_sources and v.quote.strip()}
    coverage = sum(k in facts for k in CONFIG['coverage_fields']) / len(CONFIG['coverage_fields'])
    reasons = list(d.issues)
    excluded, pending = [], []
    if len(facts)!=len(d.facts):pending.append('Quellenzuordnung fehlt oder Quelle liegt nach dem Bewertungsstichtag.')
    if d.identity_status != 'verified': pending.append('Unternehmensidentität noch nicht eindeutig belegt.')
    if 'country' not in facts or facts['country'].value != 'DE': pending.append('Deutschland-Bezug offen.')
    boundary = months_before(options.as_of, options.max_age_months)
    htgf_boundary = months_before(options.as_of, CONFIG['htgf_max_age_months'])
    if not d.earliest_founding or not d.latest_founding:
        pending.append('Gründungsdatum oder eindeutig passendes Gründungsjahr fehlt.')
    elif d.latest_founding < boundary or d.earliest_founding > options.as_of:
        excluded.append('Gründung außerhalb des gewählten Zeitfensters.')
    elif d.earliest_founding < boundary or d.latest_founding > options.as_of:
        pending.append('Gründungszeitraum überschneidet die Suchgrenze.')
    if not d.sectors:
        pending.append('Branchenzuordnung noch offen.')
    elif not set(d.sectors).intersection(options.sectors):
        excluded.append('Belegte Branche außerhalb der Auswahl.')
    if 'inactive' in facts: excluded.append('Hinweis auf Liquidation oder eingestellten Geschäftsbetrieb.')
    if 'late_round' in facts: excluded.append('Spätere Finanzierungsrunde belegt; außerhalb des Erstinvestment-Profils.')
    if 'service_business' in facts:
        pending.append('Dienstleistungs-/Agenturgeschäft: eigenes skalierbares Produkt prüfen.')
    if d.issues: pending.append('Quellenkonflikt oder Identitätsprüfung offen.')
    if d.refresh_status == 'failed': pending.append('Aktuelle Website-Prüfung fehlgeschlagen; historische Daten sind gekennzeichnet.')
    for key in CONFIG['required_facts']:
        if key not in facts: pending.append({'technology':'Konkreter technischer Ansatz fehlt.', 'product':'Eigenes Produkt noch nicht belegt.', 'buyer':'Adressierter Kundentyp fehlt.'}[key])
    if coverage < CONFIG['minimum_coverage']: pending.append('Zu wenige belegte Screening-Merkmale.')

    product = None
    if 'product' in facts and 'technology' in facts:
        product = 60
        if 'validation' in facts and re.search(r'prototyp|proof', facts['validation'].value, re.I): product = 75
        if 'validation' in facts and re.search(r'pilot|paying|zahlend', facts['validation'].value, re.I): product = 85
    market = None
    if 'buyer' in facts:
        specific = not re.fullmatch(r'Unternehmen|Betriebe|businesses|enterprises', facts['buyer'].value, re.I)
        market = 50 if specific else 30
        if 'benefit' in facts: market += 20
    validation = None
    if 'validation' in facts:
        validation = 60 if facts['validation'].basis == 'linked_research_project' else 50
        if re.search(r'pilot|clinical trial|klinische', facts['validation'].value, re.I): validation = 70
        if re.search(r'paying|zahlend', facts['validation'].value, re.I): validation = 85
    values = {'product': product, 'market': market, 'validation': validation}
    labels = {'product':'Produkt & Technologie', 'market':'Kunde & Nutzen', 'validation':'Entwicklungsnachweis'}
    supports = {'product':['product','technology','validation'], 'market':['buyer','benefit'], 'validation':['validation']}
    explanations = {
      'product': '60: konkretes Produkt + technischer Ansatz; 75: Prototyp/PoC; 85: Pilot oder zahlende Kunden.',
      'market': '30: allgemeine Unternehmen; 50: konkreter Kundentyp; +20: beschriebener Nutzen. Kein geschätzter TAM.',
      'validation': '50: eigener Entwicklungsnachweis; 60: zugeordnetes Forschungsprojekt; 70: Pilot/Studie; 85: zahlende Kunden (Selbstauskunft).'}
    criteria = [Criterion(key=k, label=labels[k], weight=CONFIG['weights'][k], points=values[k],
                         reason=explanations[k] if values[k] is not None else 'Offen; keine Ersatzpunkte.',
                         facts=[f for f in supports[k] if f in facts]) for k in values]
    available = [c for c in criteria if c.points is not None]
    if len(available) < CONFIG['minimum_criteria']: pending.append('Weniger als zwei bewertbare Dimensionen.')
    queue = 'excluded' if excluded else 'research' if pending else 'ranked'
    # Rank by the evidenced lower bound. Re-normalizing away an unknown criterion
    # would otherwise let an unresearched company outrank one with a real result.
    # Unknown is still None, never a claimed zero quality or an invented 50.
    score = round(sum(c.points*c.weight for c in available)/100,1) if queue=='ranked' else None
    score_upper = round(score+sum(c.weight for c in criteria if c.points is None),1) if score is not None else None
    company_score=product
    stage = ('Pre-Seed-Hinweis' if re.search(r'pre',facts['seed_round'].value,re.I) else 'Seed-Hinweis') if 'seed_round' in facts else 'Finanzierungsphase offen'
    risk = 'Prüfbedarf: Regulierung' if 'regulation' in facts else 'Prüfbedarf: Marktvalidierung'
    if 'validation' not in facts: risk = 'Entwicklungs- und Marktvalidierung offen'
    if excluded: risk = 'Außerhalb Suchprofil'
    next_steps = []
    if 'validation' not in facts: next_steps.append('Prototyp, technische Tests und Referenzkunden anfordern.')
    if 'team' not in facts: next_steps.append('Gründerrollen und relevante Erfahrung prüfen.')
    next_steps += ['Finanzierungsphase, Kapitalbedarf und nächsten Meilenstein klären.', 'Technische Differenzierung und Rechte an der Technologie prüfen.']
    htgf_fit = 'Potenziell passend; Phase/Technologie prüfen'
    if 'late_round' in facts or 'inactive' in facts or (d.latest_founding and d.latest_founding < htgf_boundary): htgf_fit='Außerhalb Erstinvestment-Profil'
    elif pending: htgf_fit='Prüfung offen'
    thesis = ('Prüfhypothese: Ein eigenes Technologieprodukt adressiert ' + facts['buyer'].value +
              '. Ein Gespräch lohnt sich, wenn technische Differenzierung und wirtschaftlicher Kundennutzen bestätigt werden.') if queue=='ranked' else 'Noch keine belastbare Investmenthypothese. Zuerst die ausgewiesenen offenen Punkte klären.'
    return Assessment(dossier=d, queue=queue, reasons=excluded+pending+reasons, stage=stage, score=score,score_upper=score_upper,
        company_score=company_score if queue=='ranked' else None, market_score=market if queue=='ranked' else None,
        risk=risk, coverage=round(coverage,4), criteria=criteria, hypothesis=thesis, next_steps=next_steps, htgf_fit=htgf_fit)


def ranked(items):
    return sorted(items, key=lambda a: ({'ranked':0,'research':1,'excluded':2}[a.queue], -(a.score or 0), -a.coverage, a.dossier.id))
