"""Run inside the FounderRadar repository with pytest."""
import json
import pytest
from models import Industry, SearchCriteria, RawLead
from sourcing.open_data import search

def lead(ident='real-fixture'):
    return dict(id=ident,name='Synthetic test fixture GmbH',description='Test data only',
        industry='AI / Software',country='DE',is_demo=False,source_url='https://example.org/',
        country_evidence=dict(source='Test fixture',url='https://example.org/',finding='Berlin, DE'))

def install(tmp_path,monkeypatch,rows):
    monkeypatch.setenv('FOUNDERRADAR_DISCOVERY_DIR',str(tmp_path))
    (tmp_path/'AI_Software.json').write_text(json.dumps(rows),encoding='utf-8')

def test_empty_real_results_stay_empty(tmp_path,monkeypatch):
    install(tmp_path,monkeypatch,[])
    assert search(SearchCriteria(industry=Industry.AI))==[]

def test_limit_and_contract(tmp_path,monkeypatch):
    install(tmp_path,monkeypatch,[lead('one'),lead('two')])
    result=search(SearchCriteria(industry=Industry.AI,limit=1))
    assert len(result)==1 and isinstance(result[0],RawLead)
    assert result[0].id=='one' and not result[0].is_demo

@pytest.mark.parametrize('change',[{'is_demo':True},{'country':'AT'},{'country_evidence':None},{'industry':'HealthTech'}])
def test_reject_invalid_source_export(tmp_path,monkeypatch,change):
    install(tmp_path,monkeypatch,[{**lead(),**change}])
    with pytest.raises(ValueError):search(SearchCriteria(industry=Industry.AI))

def test_no_duplicate_identity(tmp_path,monkeypatch):
    install(tmp_path,monkeypatch,[lead(),lead()])
    with pytest.raises(ValueError):search(SearchCriteria(industry=Industry.AI))

def test_missing_file_is_not_demo(tmp_path,monkeypatch):
    monkeypatch.setenv('FOUNDERRADAR_DISCOVERY_DIR',str(tmp_path))
    with pytest.raises(FileNotFoundError):search(SearchCriteria(industry=Industry.AI))

@pytest.mark.parametrize('mode,override,expected',[('live',None,200),('demo',None,30),('live','75',75)])
def test_cockpit_discovery_limit(monkeypatch,mode,override,expected):
    import cockpit_service
    monkeypatch.setenv('FOUNDERRADAR_MODE',mode)
    monkeypatch.delenv('FOUNDERRADAR_OLLAMA_MODEL',raising=False)
    monkeypatch.delenv('FOUNDERRADAR_DISCOVERY_LIMIT',raising=False)
    if override is not None:monkeypatch.setenv('FOUNDERRADAR_DISCOVERY_LIMIT',override)
    monkeypatch.setattr(cockpit_service.pipeline,'run_pipeline',lambda criteria,**kwargs:criteria.limit)
    assert cockpit_service.start_analysis(Industry.AI)==expected
