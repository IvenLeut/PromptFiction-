"""Resolve grant projects without treating grant dates or universities as companies.

All 733 records are indexed. Institution links and deterministic domain candidates
are discovery hints only. Promotion requires a named legal imprint, a German court
and address, and a separate project/company bridge. Unresolved records are retained.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from free_discovery.core import domain_guesses
from mvp.contracts import Dossier, Fact
from mvp.context import extract, extract_founding, project_imprint, registry_context
from mvp.web import canonical_host, normalized

ROOT=Path(__file__).resolve().parents[1]


def project_text(candidate):
    return '\n'.join(s.evidence for s in candidate.lead.signals)


def institutional_index(projects, web, on_progress=lambda *args: None):
    routes = {p.lead.id: [] for p in projects}
    sources = json.loads((ROOT/'config/project_sources.json').read_text(encoding='utf-8'))
    for n, spec in enumerate(sources):
        on_progress(8+n*2, 'Hochschulverweise abgleichen: '+spec['name'])
        page = web.try_page(spec['url'], 'institution')
        if not page: continue
        soup = BeautifulSoup(page['html'], 'html.parser')
        for project in projects:
            if spec['recipient'].casefold() not in project_text(project).casefold(): continue
            stem = normalized(project.lead.name)
            if len(stem) < 5: continue
            for anchor in soup.select('a[href]'):
                url = urljoin(page['url'], anchor['href'])
                label = normalized(anchor.get_text(' ', strip=True))
                if stem not in label and stem not in normalized(url): continue
                if urlsplit(url).scheme not in ('http','https') or re.search(r'linkedin|facebook|instagram|youtube|twitter',canonical_host(url)): continue
                route = {'url':url, 'institution_url':page['url'], 'source':page['source'].model_dump()}
                if route not in routes[project.lead.id]: routes[project.lead.id].append(route)
    return routes


def plan_projects(projects, routes):
    # Grants that have ended are more likely to have incorporated; this is a
    # retrieval priority, NEVER part of the investment score or founding date.
    return sorted(projects, key=lambda p:(not bool(routes.get(p.lead.id)),
        'project_finished' not in project_text(p), len(normalized(p.lead.name)) < 6, p.lead.id))


def resolve(project, web, routes=()):
    name, identity = project.lead.name, project.lead.id
    audit = {'project_id':identity, 'project_name':name, 'status':'unresolved', 'resolver_version':2, 'attempted_urls':[], 'reason':'Kein eindeutiger Firmenbeleg gefunden.'}
    possibilities=[]
    institution_pages=[]
    for route in routes[:2]:
        host = canonical_host(route['institution_url'])
        if canonical_host(route['url']) != host:
            possibilities.append((route['url'], route))
        else:
            page = web.try_page(route['url'], 'institution')
            if not page: continue
            institution_pages.append(page)
            for url in page['links']:
                if canonical_host(url) != host and normalized(name) in normalized(canonical_host(url)):
                    possibilities.append((url, {**route,'institution_url':page['url'],'source':page['source'].model_dump()}))
    # Finite probes; no scraped search-engine results, paid search key or LLM.
    if len(normalized(name)) >= 6 and not possibilities:
        possibilities += [(u,None) for u in domain_guesses(name)[:2]]
    found=[]
    for url, route in dict((u,(u,r)) for u,r in possibilities).values():
        if url.startswith('http://'):url='https://'+url[7:]
        audit['attempted_urls'].append(url)
        pages=web.company_pages(url, limit=4)
        text='\n'.join(p['text'] for p in pages)
        # Renamed spinouts are common: follow only an explicit project -> new
        # legal name statement AND a corresponding outward link on that page.
        legal_name=name
        bridge_page=None
        rename=re.search(re.escape(name)+r'\s+(?:has been founded as|wurde gegründet als|firmiert (?:jetzt )?als)\s+([\wÄÖÜäöüß &.-]{2,65}?\s+GmbH)',text,re.I)
        if rename:
            legal_name=rename.group(1).strip()
            stem=normalized(re.sub(r'\bGmbH\b','',legal_name))
            bridge_page=next((p for p in pages if rename.group() in p['text']),None)
            target=next((u for p in pages for u in p['links'] if stem in normalized(canonical_host(u)) and canonical_host(u)!=canonical_host(url)),None)
            if target:
                renamed_pages=web.company_pages(target,limit=4)
                pages=renamed_pages+pages
                text='\n'.join(p['text'] for p in pages)
        legal=project_imprint(legal_name,pages)
        if not legal: continue
        company,register,court,imprint=legal
        fkz=identity.removeprefix('foekat-')
        institutional_tokens={t.casefold() for t in re.findall(r'\b[A-ZÄÖÜ][a-zäöüß-]{5,}\b',project_text(project))
            if t.casefold() not in {'forschungstransfer','gründungsstipendium','universität','technische','hochschule','institut','fakultät','forschung','förderempfänger','ausführende','stelle','forschungszentrum','forschungszentren','öffentliche','bewilligt','hinweise','deutsches','zentrum','deutsche','deutschen','baden-württemberg','nordrhein-westfalen','bayern','thema','programm','laufzeit','fördersumme','forschungseinrichtung'}}
        own_link = normalized(name) in normalized(text) and bool(re.search(r'\bEXIST\b',text)) and any(t in text.casefold() for t in institutional_tokens)
        linked = route is not None or bool(re.search(r'\b'+re.escape(fkz)+r'\b',text,re.I)) or own_link
        if not linked:
            audit['reason']='Firma gefunden; Verbindung zum geförderten Projekt noch nicht belegt.'
            continue
        key=normalized(company+' '+register+' '+(court or ''))
        d=Dossier(id='company-'+hashlib.sha256(key.encode()).hexdigest()[:20],name=company,
            website=pages[0]['url'], project_ids=[identity],identity_status='verified',refresh_status='fresh')
        d.facts['register']=Fact(value=register+('; '+court if court else ''),source_url=imprint['url'],quote=register,basis='legal_imprint')
        d.facts['country']=Fact(value='DE',source_url=imprint['url'],quote=register,basis='german_court_and_address')
        d.facts['project_link']=Fact(value=identity,source_url=route['institution_url'] if route else bridge_page['url'] if bridge_page else pages[0]['url'],quote=name,basis='institution_link' if route else 'project_name_grant_and_institution' if own_link else 'exact_grant_reference')
        d=extract(d,pages)
        if route:
            from mvp.contracts import Source
            source=Source.model_validate(route['source'])
            if source.url not in [s.url for s in d.sources]:d.sources.append(source)
        # Grant supports research activity, not a customer, patent, founder salary
        # or company financing amount. Keep the university beneficiary distinct.
        if 'validation' not in d.facts:
            signal=project.lead.signals[0]
            d.facts['validation']=Fact(value='Zugeordnetes EXIST-Forschungs-/Gründungsprojekt',source_url=str(signal.url),quote=fkz.upper(),basis='linked_research_project')
            from mvp.contracts import Source
            d.sources.append(Source(url=str(signal.url),title='Förderkatalog: '+name,
                retrieved_at=project.lead.discovered_at.isoformat() if project.lead.discovered_at else '2026-11-20',
                sha256=hashlib.sha256(signal.evidence.encode()).hexdigest(),kind='grant_snapshot'))
        extract_founding(d,pages)
        postal=re.search(r'\b\d{5}\b',imprint['text'])
        registry=registry_context(d,web,expected_register=register,expected_postcode=postal.group() if postal else '')
        if not court and not registry:
            d.identity_status='unresolved'
            d.issues.append('Registergericht fehlt im Impressum; ergänzender Registerabgleich offen.')
        found.append(d)
    unique={d.id:d for d in found}
    if len(unique)==1:
        d=next(iter(unique.values()))
        audit.update(status='resolved',company_id=d.id,company_name=d.name,reason='Projektverbindung + benanntes Impressum + deutsches Register/Adresse belegt; Alter separat geprüft.')
        return d,audit
    if len(unique)>1:audit['reason']='Mehrere rechtliche Identitäten; keine automatische Zusammenführung.'
    return None,audit
