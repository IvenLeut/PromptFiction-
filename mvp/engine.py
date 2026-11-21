"""Three explicit steps: discover/resolve -> evidence dossier -> versioned score.

Reuses the combined pool, open-data identity validation and analyst persistence.
Live mode fetches pages. Replay mode recalculates saved factual dossiers honestly.
"""
import argparse
import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path
from uuid import uuid4
from mvp.contracts import Dossier, Fact, Run, RunOptions, Source
from mvp.context import extract, extract_founding, verify_known_identity
from mvp.resolver import institutional_index, plan_projects, resolve
from mvp.scoring import assess, ranked
from mvp.web import Web, canonical_host
from sourcing.combined import DiscoverySnapshot

ROOT=Path(__file__).resolve().parents[1]


def data_dir():
    return Path(os.getenv('FOUNDERRADAR_MVP_DATA',str(ROOT/'data/mvp')))


def write_json(path, payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        # Windows antivirus/indexers can briefly deny atomic replacement. Keep
        # the previous good document intact and retry only sharing/lock errors.
        for attempt in range(8):
            try:
                temp.replace(path)
                break
            except PermissionError:
                if attempt==7:raise
                time.sleep(min(.05*2**attempt,.4))
    finally:
        temp.unlink(missing_ok=True)


def load_last():
    path=data_dir()/'latest.json'
    if not path.exists():path=ROOT/'data/mvp/demo-run.json'
    return Run.model_validate_json(path.read_bytes()) if path.exists() else None


def known_company(record, web):
    d=Dossier(id=record['id'],name=record['name'],website=record['website'],sectors=record['industries'])
    when=date.fromisoformat(record['founded_on'])
    d.earliest_founding=d.latest_founding=when
    d.founding_basis=record['founding_basis']
    timestamp=max((p['retrieved_at'] for p in record['page_evidence']),default='2026-11-20')
    d.sources.append(Source(url=record['source_url'],title='GLEIF Identität (gespeicherter Quellenstand)',retrieved_at=timestamp,
                            sha256=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest(),kind='identity_snapshot'))
    d.facts['country']=Fact(value='DE',source_url=record['country_source'],quote=record['city']+', DE',basis='gleif_snapshot')
    d.facts['founding']=Fact(value=when.isoformat(),source_url=record['source_url'],quote='entity.creationDate: '+when.isoformat(),basis='gleif_snapshot')
    d.facts['register']=Fact(value=record.get('registration') or '',source_url=record['source_url'],quote=record.get('registration') or '',basis='gleif_snapshot')
    pages=web.company_pages(d.website)
    d.refresh_status='fresh' if pages else 'failed'
    if verify_known_identity(record,pages): d.identity_status='verified'
    else: d.issues.append('Aktuelles Impressum stimmt nicht eindeutig mit gespeicherter Identität überein oder ist nicht erreichbar.')
    extract(d,pages)
    extract_founding(d,pages)
    return d


def deduplicate(dossiers):
    # A verified common website + exact legal name may join two provider IDs;
    # neither a shared university domain nor a name alone is sufficient.
    from free_discovery.core import company_key
    unique={};keys={}
    for d in sorted(dossiers,key=lambda d:(not d.id.startswith('gleif-'),d.id)):
        key=(canonical_host(d.website or ''), company_key(d.name))
        old=unique.get(keys.get(key,'')) if key[0] and d.identity_status=='verified' else None
        if old:
            a,b=old.facts.get('register'),d.facts.get('register')
            import re
            def reg(x):
                m=re.search(r'HR[AB]\s*\d+',x.value if x else '',re.I)
                return re.sub(r'\s','',m.group()).upper() if m else None
            if reg(a) and reg(b) and reg(a)!=reg(b):
                old.issues.append('Widersprüchliche Registerkennungen bei gleicher Website.');d.issues.append('Widersprüchliche Registerkennungen bei gleicher Website.')
            else:
                old.project_ids=sorted(set(old.project_ids+d.project_ids))
                for k,v in d.facts.items(): old.facts.setdefault(k,v)
                old.sources += [s for s in d.sources if s.url not in [x.url for x in old.sources]]
                continue
        unique[d.id]=d
        keys[key]=d.id
    return list(unique.values())


def refresh_resolved(dossier, web):
    """Keep resolved companies across jobs; refresh current context every live run."""
    d=dossier.model_copy(deep=True)
    provenance={'country','founding','register','project_link'}
    d.facts={k:v for k,v in d.facts.items() if k in provenance or v.basis=='linked_research_project'}
    d.issues=[] if d.identity_status=='verified' else list(d.issues)
    pages=web.company_pages(d.website)
    d.refresh_status='fresh' if pages else 'failed'
    import re
    reg=re.search(r'\bHR[AB]\s*\d+\b',d.facts['register'].value,re.I) if d.facts.get('register') else None
    record={'name':d.name,'registration':reg.group() if reg else '', 'city':None,'postal_code':None}
    from mvp.context import project_imprint
    current_legal=project_imprint(d.name,pages)
    d.identity_status='verified' if verify_known_identity(record,pages) and (d.identity_status=='verified' or (current_legal and current_legal[2])) else 'unresolved'
    # Replace previous observations of the refreshed URLs rather than presenting
    # an old hash/timestamp as the source of newly extracted claims.
    urls={p['url'] for p in pages}
    d.sources=[s for s in d.sources if s.url not in urls]
    extract(d,pages);extract_founding(d,pages)
    return d


def run(options: RunOptions, progress=lambda *args:None, *, web=None, cancelled=lambda:False):
    # Streamlit may reload contract classes while a cached worker still exists.
    # Cross that boundary with validated values, never Python class identity.
    options=RunOptions.model_validate(options.model_dump(mode='json') if hasattr(options,'model_dump') else options)
    raw=(ROOT/'data/combined-discovery.json').read_bytes()
    pool=DiscoverySnapshot.model_validate_json(raw)
    projects=[c for c in pool.candidates if 'foekat' in c.providers]
    project_audit=[{'project_id':p.lead.id,'project_name':p.lead.name,'status':'not_processed','reason':'Außerhalb des begrenzten Recherchebudgets dieses Laufs.'} for p in projects]
    warnings=['Quellen decken nur einen Teil deutscher Gründungen ab. Keine Vollständigkeitsbehauptung.',
              'HTGF-Profil ist eine interne Screening-Hilfe nach öffentlichen Kriterien. Keine offizielle HTGF-Bewertung.']
    if options.mode=='replay':
        previous=load_last()
        if not previous:raise ValueError('Noch kein gespeicherter Quellenstand vorhanden. Zuerst einen Live-Lauf starten.')
        dossiers=[a.dossier.model_copy(deep=True) for a in previous.assessments]
        for d in dossiers:d.refresh_status='snapshot'
        project_audit=previous.project_audit
        warnings.append('Neuberechnung aus gespeicherten Fakten; keine aktuelle Webrecherche.')
        requests=0
        input_hash=previous.input_hash
        source_date=previous.source_snapshot_date
    else:
        web=web or Web(data_dir()/'cache',refresh=True)
        checkpoint_path=data_dir()/'checkpoint.json'
        checkpoint={}
        if checkpoint_path.exists():
            saved=json.loads(checkpoint_path.read_text(encoding='utf-8'))
            if not saved.get('complete') and saved.get('options')==options.model_dump(mode='json'):
                checkpoint=saved
                web.refresh=False
                warnings.append('Unterbrochener Lauf fortgesetzt; bereits gespeicherte Quellen werden weiterverwendet.')
        routes=institutional_index(projects,web,progress) if options.project_budget else {}
        planned=plan_projects(projects,routes)
        dossiers=[Dossier.model_validate(x) for x in checkpoint.get('dossiers',[])]
        completed=set(checkpoint.get('completed',[]))
        audits={a['project_id']:a for a in project_audit}
        # Continue the unresolved queue across runs instead of repeatedly probing
        # the same first twelve projects. Re-resolve known matches as well.
        previous=load_last()
        if previous:
            for a in previous.project_audit:
                if a['project_id'] in audits:audits[a['project_id']]=a
        for a in checkpoint.get('project_audit',[]):audits[a['project_id']]=a
        processed={a['project_id'] for a in audits.values() if a['status']=='unresolved' and a.get('resolver_version')==2}
        planned.sort(key=lambda p: (p.lead.id in processed,not bool(routes.get(p.lead.id))))
        planned_ids=checkpoint.get('planned_ids') or [p.lead.id for p in planned[:options.project_budget]]
        project_map={p.lead.id:p for p in projects}
        planned=[project_map[identity] for identity in planned_ids]
        def checkpoint_save(complete=False):
            write_json(checkpoint_path,{'complete':complete,'options':options.model_dump(mode='json'),'planned_ids':planned_ids,
                'completed':sorted(completed),'dossiers':[d.model_dump(mode='json') for d in dossiers],'project_audit':list(audits.values())})
        for i,p in enumerate(planned[:options.project_budget]):
            if p.lead.id in completed:continue
            if cancelled():raise InterruptedError('Analyse angehalten; vorhandene Quellen bleiben im Cache.')
            progress(18+int(30*i/max(1,options.project_budget)),'Projekt zu Firma: '+p.lead.name)
            d,audit=resolve(p,web,routes.get(p.lead.id,[]));audits[p.lead.id]=audit
            if d:dossiers.append(d)
            completed.add(p.lead.id);checkpoint_save()
        if previous:
            for assessment in previous.assessments:
                old=assessment.dossier
                if old.project_ids and old.id not in completed and not set(old.project_ids).intersection(planned_ids):
                    if cancelled():raise InterruptedError('Analyse angehalten; Quellenstand gespeichert.')
                    dossiers.append(refresh_resolved(old,web))
                    completed.add(old.id);checkpoint_save()
        project_audit=list(audits.values())
        records=json.loads((ROOT/'data/open-discovery/export/qualified.json').read_text(encoding='utf-8'))
        for i,record in enumerate(records):
            if record['id'] in completed:continue
            if cancelled():raise InterruptedError('Analyse angehalten; vorhandene Quellen bleiben im Cache.')
            progress(50+int(40*i/max(1,len(records))),'Unternehmensquellen prüfen: '+record['name'])
            dossiers.append(known_company(record,web))
            completed.add(record['id']);checkpoint_save()
        requests=getattr(web,'network_calls',web.calls)
        warnings.extend(f"Quelle nicht abrufbar: {e['url']} ({e['error']})" for e in web.errors)
        input_hash=hashlib.sha256(json.dumps([d.model_dump(mode='json') for d in dossiers],sort_keys=True).encode()).hexdigest()
        source_date=pool.as_of.isoformat()
    progress(94,'Belege prüfen und Scorecard berechnen')
    before=len(dossiers);dossiers=deduplicate(dossiers)
    assessments=ranked([assess(d,options) for d in dossiers])
    result=Run(id=uuid4().hex[:16],options=options.model_dump(mode='json'),input_hash=input_hash,source_snapshot_date=source_date,
        assessments=[a.model_dump(mode='json') for a in assessments],project_audit=project_audit,warnings=warnings,
        counts={'pool':len(pool.candidates),'projects':len(projects),'projects_attempted':sum(a['status']!='not_processed' for a in project_audit),
          'projects_resolved':sum(a['status']=='resolved' for a in project_audit),'projects_this_run':len(planned_ids) if options.mode=='live' else 0,'companies':len(dossiers),'duplicates':before-len(dossiers),
          'ranked':sum(a.queue=='ranked' for a in assessments),'research':sum(a.queue=='research' for a in assessments),
          'excluded':sum(a.queue=='excluded' for a in assessments),'web_requests':requests,
          'cache_hits':getattr(web,'cache_hits',0) if options.mode=='live' else 0})
    write_json(data_dir()/'runs'/f'{result.id}.json',result.model_dump(mode='json'))
    from mvp.handoff import analysis_run
    from models import Industry
    exports={industry.name.lower():analysis_run(result,industry) for industry in Industry}
    for name,export in exports.items():write_json(data_dir()/'analysis'/f'{name}.json',export.model_dump(mode='json'))
    write_json(data_dir()/'latest.json',result.model_dump(mode='json'))
    if options.mode=='live':checkpoint_save(complete=True)
    progress(100,'Analyse gespeichert')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['live','replay'],default='live')
    p.add_argument('--project-budget',type=int,default=12)
    p.add_argument('--as-of',type=date.fromisoformat,default=date.today())
    args=p.parse_args()
    result=run(RunOptions(mode=args.mode,project_budget=args.project_budget,as_of=args.as_of),lambda n,t:print(f'{n}% {t}',flush=True))
    print(json.dumps(result.counts,indent=2))


if __name__=='__main__':main()
