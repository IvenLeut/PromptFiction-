"""Business-critical regressions for the live MVP; fixtures are explicitly synthetic."""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import pytest
from mvp.contracts import Dossier, Fact, Source, RunOptions
from mvp.context import extract, extract_founding, project_imprint, registry_context
from mvp.scoring import assess, months_before
from mvp.engine import deduplicate, run, load_last, write_json
from mvp.cockpit import csv_export

ROOT=Path(__file__).resolve().parents[1]
AS_OF=date(2026,11,21)
URL='https://demo-company.invalid/'


def source(url=URL, kind='company'):
    return Source(url=url,title='Synthetic test evidence',retrieved_at='2026-11-21T10:00:00Z',sha256='a'*64,kind=kind)


def fact(value,url=URL,basis='rule_extraction'):
    return Fact(value=value,source_url=url,quote=value,basis=basis)


def dossier():
    return Dossier(id='fixture-1',name='TestPhoton GmbH',website=URL,identity_status='verified',refresh_status='fresh',
        earliest_founding=date(2025,3,1),latest_founding=date(2025,3,1),sectors=['Industrial / DeepTech'],sources=[source()],
        facts={'country':fact('DE'),'register':fact('HRB 12345'),'technology':fact('photonics'),'product':fact('our platform'),
               'buyer':fact('manufacturers'),'benefit':fact('reduce energy'),'team':fact('Founder')})


def page(text,url=URL,links=()):
    return {'text':text,'url':url,'links':list(links),'html':'','source':source(url)}


def test_missing_evidence_never_produces_default_50():
    d=dossier();d.facts={k:v for k,v in d.facts.items() if k in {'country','register'}}
    a=assess(d,RunOptions(as_of=AS_OF))
    assert a.score is None and a.coverage==0 and a.queue=='research'
    assert all(c.points is None for c in a.criteria)


def test_score_is_explainable_and_unknown_validation_stays_unknown():
    a=assess(dossier(),RunOptions(as_of=AS_OF))
    assert a.score==48.5 and a.score_upper==73.5 and a.coverage==.8333
    assert a.criteria[2].points is None
    assert a.company_score==60 and a.market_score==70


def test_hardware_is_not_penalized_against_software():
    d=dossier();a=assess(d,RunOptions(as_of=AS_OF))
    d.sectors=['AI / Software']
    assert assess(d,RunOptions(as_of=AS_OF)).score==a.score


@pytest.mark.parametrize('key,value,queue', [('seed_round','Seed round','ranked'),('late_round','closed Series A','excluded'),('inactive','in Liquidation','excluded'),('service_business','Digitalagentur','research')])
def test_htgf_stage_and_service_gates(key,value,queue):
    d=dossier();d.facts[key]=fact(value)
    assert assess(d,RunOptions(as_of=AS_OF)).queue==queue


def test_unsupported_future_sources_do_not_count():
    d=dossier();d.sources[0].retrieved_at='2026-12-01'
    assert assess(d,RunOptions(as_of=AS_OF)).score is None
    d.sources[0].retrieved_at='2026-11-21'
    d.facts['technology'].source_url='https://unrelated.invalid'
    assert assess(d,RunOptions(as_of=AS_OF)).score is None


def test_rolling_age_window_uses_interval_and_includes_boundary():
    d=dossier();d.earliest_founding=d.latest_founding=date(2024,11,21)
    assert assess(d,RunOptions(as_of=AS_OF)).queue=='ranked'
    d.earliest_founding=date(2024,1,1);d.latest_founding=date(2024,12,31)
    assert assess(d,RunOptions(as_of=AS_OF)).queue=='research'
    assert assess(d,RunOptions(as_of=AS_OF,max_age_months=36)).queue=='ranked'
    d.latest_founding=date(2024,11,20)
    assert assess(d,RunOptions(as_of=AS_OF)).queue=='excluded'
    assert months_before(date(2024,2,29),12)==date(2023,2,28)


def test_grant_date_and_copyright_never_become_founding_date():
    d=dossier();d.earliest_founding=d.latest_founding=None
    extract_founding(d,[page('TestPhoton GmbH. EXIST grant started in 2025. Copyright 2025.')])
    assert d.earliest_founding is None
    extract_founding(d,[page('TestPhoton GmbH was founded in 2025.')])
    assert d.earliest_founding==date(2025,1,1) and d.latest_founding==date(2025,12,31)


def test_negated_prototype_not_claimed():
    d=dossier()
    extract(d,[page('There is no prototype. Our platform uses photonics for manufacturers.')])
    assert 'validation' not in d.facts


def test_timeline_formation_is_not_previous_grant_milestone():
    d=dossier();d.earliest_founding=d.latest_founding=None
    p=page('TestPhoton GmbH',URL+'ueber-uns')
    p['html']='<h4>März 2024 – Förderung</h4><p>TestPhoton GmbH: EXIST-Forschungstransfer.</p><h4>Februar 2025 – Gründung</h4><p>Die TestPhoton GmbH wird gegründet.</p>'
    extract_founding(d,[p])
    assert d.earliest_founding==date(2025,2,1) and d.latest_founding==date(2025,2,28)


def test_about_page_founding_stat_preserves_year_precision():
    d=dossier();d.earliest_founding=d.latest_founding=None
    extract_founding(d,[page('TestPhoton GmbH\n'+('Text '*100)+'\n2025\nGegründet\n8\nMitarbeitende',URL+'unternehmen')])
    assert d.earliest_founding==date(2025,1,1) and d.latest_founding==date(2025,12,31)


def test_imprint_requires_company_before_legal_suffix():
    bad=page('TTI GmbH (TestPhoton)\n70569 Stuttgart\nLocal Court Stuttgart HRB 19455',URL+'imprint')
    assert project_imprint('TestPhoton',[bad]) is None
    good=page('TestPhoton GmbH\n70569 Stuttgart\nLocal Court Stuttgart\nHRB 12345',URL+'imprint')
    assert project_imprint('TestPhoton GmbH',[good])[0]=='TestPhoton GmbH'


def test_formation_and_register_entry_are_not_interchangeable():
    d=dossier();d.earliest_founding=d.latest_founding=None
    p=page('TestPhoton GmbH HRB 12345 70569 Stuttgart\nEingetragen seit\n17.04.2025\nGründung\nDatum des Gesellschaftsvertrags oder der Satzung, wie es das Register nennt.\n09.04.2025',URL+'register')
    web=SimpleNamespace(try_page=lambda *args:p)
    registry_context(d,web,expected_register='HRB 12345',expected_postcode='70569')
    assert d.earliest_founding==date(2025,4,9)
    d.earliest_founding=None
    registry_context(d,web,expected_register='HRB 98765',expected_postcode='70569')
    assert d.earliest_founding is None


def test_duplicate_conflicting_registers_are_held():
    d=dossier();e=d.model_copy(deep=True);e.id='fixture-2';e.facts['register']=fact('HRB 98765')
    result=deduplicate([d,e]);assert len(result)==2
    assert all(x.issues for x in result)


def test_exact_same_company_combines_project_provenance():
    d=dossier();e=d.model_copy(deep=True);e.id='fixture-2';e.project_ids=['project-1']
    result=deduplicate([d,e]);assert len(result)==1 and result[0].project_ids==['project-1']


def test_csv_formula_injection_is_escaped():
    assert "'=1+1" in csv_export([{'Name':'=1+1','Score':64.7}]).decode('utf-8-sig')


def test_project_rename_requires_explicit_bridge_and_matching_imprint():
    from mvp.resolver import resolve
    from models import RawLead,SourceSignal,Industry
    lead=RawLead(id='foekat-03fake',name='OldPhoton',description='',industry=Industry.INDUSTRIAL,
        source_url='https://grant.invalid/03fake',signals=[SourceSignal(source='Grant',type='exist_projekt',
        url='https://grant.invalid/03fake',evidence='EXIST-Forschungstransfer\nUniversität Stuttgart\nOldPhoton')])
    old=page('The project OldPhoton funded by EXIST. University of Stuttgart. OldPhoton has been founded as NewPhoton GmbH',
             'https://oldphoton.invalid/',links=['https://newphoton.invalid/'])
    new=page('NewPhoton GmbH. Our platform uses photonics for manufacturers. We reduce energy consumption.', 'https://newphoton.invalid/')
    legal=page('NewPhoton GmbH\n70569 Stuttgart\nLocal Court Stuttgart\nHRB 98765','https://newphoton.invalid/imprint')
    web=SimpleNamespace(company_pages=lambda url,limit=4:[old] if 'oldphoton' in url else [new,legal],try_page=lambda *a:None)
    d,audit=resolve(SimpleNamespace(lead=lead),web,[{'url':old['url'],'institution_url':'https://uni.invalid/oldphoton','source':source('https://uni.invalid/oldphoton').model_dump()}])
    assert d.name=='NewPhoton GmbH' and d.project_ids==['foekat-03fake']
    assert d.earliest_founding is None and audit['status']=='resolved'


def test_no_project_merge_from_name_only():
    from mvp.resolver import resolve
    from models import RawLead,Industry,SourceSignal
    lead=RawLead(id='foekat-03fake',name='TestPhoton',description='',industry=Industry.INDUSTRIAL,source_url=URL,
        signals=[SourceSignal(source='Grant',type='exist_projekt',url=URL,evidence='Universität Stuttgart')])
    legal=page('TestPhoton GmbH\n70569 Stuttgart\nLocal Court Stuttgart\nHRB 12345',URL+'imprint')
    web=SimpleNamespace(company_pages=lambda *a,**kw:[page('TestPhoton GmbH. Our technology.'),legal],try_page=lambda *a:None)
    d,audit=resolve(SimpleNamespace(lead=lead),web)
    assert d is None and audit['status']=='unresolved'


def test_refresh_does_not_upgrade_unverified_register_court():
    from mvp.engine import refresh_resolved
    d=dossier();d.identity_status='unresolved';d.issues=['Registergericht fehlt.']
    legal=page('TestPhoton GmbH\n70569 Stuttgart\nHRB 12345',URL+'imprint')
    web=SimpleNamespace(company_pages=lambda *a,**kw:[legal])
    assert refresh_resolved(d,web).identity_status=='unresolved'


def test_live_pipeline_replay_and_resume(tmp_path,monkeypatch):
    import mvp.engine as engine
    monkeypatch.setenv('FOUNDERRADAR_MVP_DATA',str(tmp_path))
    monkeypatch.setattr(engine,'load_last',lambda:None)
    calls=[]
    def company(record,web):
        calls.append(record['id']);d=dossier();d.id=record['id'];d.name=record['name'];d.website=record['website'];return d
    monkeypatch.setattr(engine,'known_company',company)
    web=SimpleNamespace(calls=0,errors=[],refresh=True)
    options=RunOptions(as_of=AS_OF,project_budget=0)
    with pytest.raises(InterruptedError):
        engine.run(options,web=web,cancelled=lambda:len(calls)>=2)
    checkpoint=json.loads((tmp_path/'checkpoint.json').read_text(encoding='utf-8'))
    assert len(checkpoint['completed'])==2
    result=engine.run(options,web=web)
    assert len(calls)==21 and result.counts['companies']==21
    assert json.loads((tmp_path/'checkpoint.json').read_text(encoding='utf-8'))['complete']
    monkeypatch.setattr(engine,'load_last',lambda:result)
    from pydantic import create_model
    ReloadedOptions=create_model('RunOptions',**{k:(v.annotation,...) for k,v in RunOptions.model_fields.items()})
    foreign_options=ReloadedOptions.model_validate(options.model_copy(update={'mode':'replay'}).model_dump(mode='json'))
    assert not isinstance(foreign_options,RunOptions)
    replay=engine.run(foreign_options)
    assert [(a.dossier.id,a.score,a.queue) for a in result.assessments]==[(a.dossier.id,a.score,a.queue) for a in replay.assessments]
    assert replay.counts['web_requests']==0 and replay.llm_calls==0
    from models import AnalysisRun
    outputs=list((tmp_path/'analysis').glob('*.json'))
    assert len(outputs)==5
    parsed=[AnalysisRun.model_validate_json(p.read_bytes()) for p in outputs]
    assert all(l.confidence_score is None and l.risk_score is None for r in parsed for l in r.result.leads)
    assert all(l.evaluation_v2['model']=='early-stage.2' for r in parsed for l in r.result.leads)


def test_atomic_state_write_retries_windows_lock_without_losing_previous(tmp_path,monkeypatch):
    import mvp.engine as engine
    target=tmp_path/'job.json'
    target.write_text('{"status":"done"}',encoding='utf-8')
    original=Path.replace
    attempts=[]
    def locked_once(source,dest):
        attempts.append(1)
        if len(attempts)==1:
            assert json.loads(target.read_text())['status']=='done'
            raise PermissionError('simulated transient Windows sharing lock')
        return original(source,dest)
    monkeypatch.setattr(Path,'replace',locked_once)
    monkeypatch.setattr(engine.time,'sleep',lambda _:None)
    write_json(target,{'status':'running'})
    assert len(attempts)==2 and json.loads(target.read_text())['status']=='running'
    assert not list(tmp_path.glob('*.tmp'))


def test_default_cockpit_navigation_and_persistence(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from mvp.contracts import Run
    monkeypatch.setenv('FOUNDERRADAR_UI','mvp')
    monkeypatch.setenv('FOUNDERRADAR_MVP_DATA',str(tmp_path))
    assessment=assess(dossier(),RunOptions(as_of=AS_OF))
    sample=Run(id='ui-test',options=RunOptions(as_of=AS_OF),input_hash='a'*64,source_snapshot_date='2026-11-21',
        assessments=[assessment],project_audit=[],warnings=[],counts={'ranked':1,'research':0,'excluded':0,'projects_resolved':0,'projects':733,'projects_attempted':0})
    write_json(tmp_path/'latest.json',sample.model_dump(mode='json'))
    app=AppTest.from_file(str(ROOT/'cockpit.py'),default_timeout=30).run()
    assert not app.exception and app.title[0].value=='Frühe Technologieunternehmen finden'
    next(b for b in app.button if b.label=='Unternehmen prüfen').click().run()
    assert not app.exception and app.title[0].value=='Unternehmensanalyse'
    next(x for x in app.selectbox if x.label=='Entscheidung').set_value('Watchlist')
    next(x for x in app.text_area if x.label=='Begründung').set_value('Prototyp im Erstgespräch prüfen')
    next(x for x in app.button if x.label=='Entscheidung und Aufgabe speichern').click().run()
    from analyst_store import load_decisions
    assert load_decisions('live')['fixture-1']['decision']=='Watchlist'
    next(x for x in app.radio if x.label=='Arbeitsbereich').set_value('Longlist').run()
    assert not app.exception and len(app.dataframe[0].value)==1
    next(x for x in app.radio if x.label=='Arbeitsbereich').set_value('Aufgaben').run()
    assert not app.exception and len(app.dataframe[0].value)==1
    next(x for x in app.radio if x.label=='Arbeitsbereich').set_value('Modell & Quellen').run()
    assert not app.exception
