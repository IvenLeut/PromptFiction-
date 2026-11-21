import json
from datetime import date

import pytest

from models import Industry, SearchCriteria, RawLead
from sourcing.combined import combine, select, years_before
from batch_analysis import run_snapshot


def company(ident='gleif-12345678901234567890', founded='2025-04-01', **kw):
    return dict(id=ident, name='Synthetic Robotics GmbH', country='DE', city='Berlin',
        source_url='https://example.org/entity', country_source='https://example.org/entity', source_name='GLEIF',
        status='qualified_candidate', identity_verified=True, founded_on=founded, founding_basis='entity.creationDate',
        industries=['AI / Software', 'Industrial / DeepTech'], website='https://example.org/',
        page_evidence=[dict(retrieved_at='2026-11-20T12:00:00Z')],
        innovation_evidence=[dict(url='https://example.org/product', quote='We develop software and robot technology for manufacturing.')], **kw)


def project(ident='foekat-03ef0001', flags='pre_founding_team, industry_basis_thema', lei=None):
    return dict(id=ident, name='Synthetic Robotics', description='Synthetic test research project',
        industry='Industrial / DeepTech', country='DE', source_url='https://example.org/grant',
        country_evidence=dict(source='Fixture', url='https://example.org/grant', finding='Berlin, DE',
                              retrieved_at='2026-11-20T12:00:00Z'),
        signals=[dict(source='Fixture', type='foerderprojekt', date='2025-02-01',
            url='https://example.org/grant', subject_lead_id=ident,
            evidence='Hinweise: '+flags+ ('\nCompany LEI: '+lei if lei else ''))])


def snapshot(tmp_path, companies=None, projects=None):
    (tmp_path/'qualified.json').write_text(json.dumps([company()] if companies is None else companies), encoding='utf-8')
    (tmp_path/'projects.json').write_text(json.dumps([project()] if projects is None else projects), encoding='utf-8')
    return combine(tmp_path, tmp_path/'projects.json', as_of=date(2026,11,21))


def test_project_date_never_proves_founding(tmp_path):
    s = snapshot(tmp_path)
    assert s.counts()['recent_companies'] == 1
    assert s.counts()['review_required'] == 1
    assert next(c for c in s.candidates if 'foekat' in c.providers).founded_on is None
    result = select(s, SearchCriteria(industry=Industry.INDUSTRIAL))
    assert len(result) == 1 and result[0].id.startswith('gleif-')
    assert result.discovery['cohort'] == 'companies'


def test_similar_name_is_not_an_identity_merge(tmp_path):
    assert len(snapshot(tmp_path).candidates) == 2


def test_explicit_lei_merges_with_provenance_and_rebound_signals(tmp_path):
    s = snapshot(tmp_path, projects=[project(lei='12345678901234567890')])
    assert len(s.candidates) == 1
    c = s.candidates[0]
    assert c.providers == ['foekat', 'open_data']
    assert len(c.source_ids) == 2
    assert all(x.subject_lead_id == c.lead.id for x in c.lead.signals)
    assert c.founded_on == date(2025,4,1)


@pytest.mark.parametrize('day,status', [('2024-11-20','outside_window'), ('2024-11-21','recent_company'),
    ('2026-11-21','recent_company'), ('2026-11-22','outside_window'), (None,'review_required')])
def test_exact_two_year_boundaries(tmp_path, day, status):
    s = snapshot(tmp_path, companies=[company(founded=day)], projects=[])
    assert s.candidates[0].eligibility == status
    assert years_before(date(2024,2,29)) == date(2022,2,28)


def test_conflicting_business_age_stays_in_review(tmp_path):
    s = snapshot(tmp_path, companies=[company(date_conflict=True)], projects=[])
    assert s.candidates[0].eligibility == 'review_required'


@pytest.mark.parametrize('flags', ['industry_basis_institut', 'industry_unclassified'])
def test_institute_does_not_prove_product_industry(tmp_path, flags):
    s = snapshot(tmp_path, companies=[], projects=[project(flags=flags)])
    assert s.candidates[0].industries == []
    assert select(s, SearchCriteria(industry=Industry.INDUSTRIAL), cohort='research') == []


def test_no_ai_no_network_and_end_to_end_compatibility(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('Network/model must not run')
    monkeypatch.setattr('http.client.HTTPConnection.request', forbidden)
    monkeypatch.setattr('http.client.HTTPSConnection.request', forbidden)
    s = snapshot(tmp_path)
    runs = run_snapshot(s)
    assert sum(r.discovered_count for r in runs) == 2  # one firm in two industries
    assert all(not r.result.issues for r in runs)
    for run in runs:
        assert run.discovery['counts']['unique_candidates'] == 2
        for lead in run.result.leads:
            assert lead.evaluation_v2 is not None
            assert lead.scoring_input.as_of == s.as_of
            assert lead.scoring_input.founded.value.day == 1
            assert lead.scoring_input.founded.value.month == 4
            assert 'overall_score' not in RawLead.model_fields
    from cockpit_data import load_payload
    for run in runs:
        load_payload(run.model_dump(mode='json'))


def test_snapshot_and_scores_repeat_deterministically(tmp_path):
    a = snapshot(tmp_path)
    b = snapshot(tmp_path)
    assert a.model_dump_json() == b.model_dump_json()
    first, second = run_snapshot(a), run_snapshot(b)
    assert [[l.evaluation_v2 for l in r.result.leads] for r in first] == [
        [l.evaluation_v2 for l in r.result.leads] for r in second]


def test_missing_source_is_visible_and_never_demo(tmp_path):
    (tmp_path/'projects.json').write_text(json.dumps([project()]), encoding='utf-8')
    s = combine(tmp_path, tmp_path/'projects.json', as_of=date(2026,11,21))
    result = select(s, SearchCriteria(industry=Industry.INDUSTRIAL), cohort='research')
    assert not result.complete and result.warnings
    assert len(result) == 1 and not result[0].is_demo


def test_duplicate_and_foreign_exports_rejected(tmp_path):
    with pytest.raises(ValueError):
        snapshot(tmp_path, companies=[company(),company()])
    c = company()
    c['country'] = 'AT'
    with pytest.raises(ValueError):
        snapshot(tmp_path, companies=[c])


def test_capacity_is_200_per_sector_without_counting_multisector_firms_twice(tmp_path):
    companies = [company(ident=f'gleif-{i:020d}') for i in range(205)]
    s = snapshot(tmp_path, companies=companies, projects=[])
    assert s.counts()['recent_companies'] == 205
    for industry in (Industry.AI, Industry.INDUSTRIAL):
        leads = select(s, SearchCriteria(industry=industry, limit=200))
        assert len(leads) == len({l.id for l in leads}) == 200


def test_description_points_to_company_source_not_identity_api(tmp_path):
    from evaluation.engine import to_dossier
    from scoring import load_config
    from context.engine import enrich
    s = snapshot(tmp_path, projects=[])
    lead = enrich(s.candidates[0].lead, light=True, as_of=s.as_of)
    assert to_dossier(lead, load_config())['beschreibung_rohtext']['quelle'] == 'https://example.org/product'


def test_saved_analysis_can_be_loaded_without_engines(tmp_path, monkeypatch):
    import cockpit_service
    s = snapshot(tmp_path)
    runs = run_snapshot(s)
    for run in runs:
        (tmp_path/(run.criteria.industry.name.lower()+'.json')).write_text(run.model_dump_json(), encoding='utf-8')
    monkeypatch.setenv('FOUNDERRADAR_MODE', 'live')
    monkeypatch.setenv('FOUNDERRADAR_ANALYSIS_DIR', str(tmp_path))
    def forbidden(*a, **kw):
        raise AssertionError('Display must not recompute or crawl')
    monkeypatch.setattr(cockpit_service.pipeline, 'run_pipeline', forbidden)
    assert cockpit_service.start_analysis(Industry.AI) == runs[0]


def test_light_context_ignores_model_configuration(tmp_path, monkeypatch):
    import cockpit_service
    monkeypatch.setenv('FOUNDERRADAR_MODE', 'live')
    monkeypatch.setenv('FOUNDERRADAR_CONTEXT_MODE', 'light')
    monkeypatch.setenv('FOUNDERRADAR_OLLAMA_MODEL', 'must-not-be-called')
    monkeypatch.delenv('FOUNDERRADAR_ANALYSIS_DIR', raising=False)
    monkeypatch.setattr(cockpit_service.pipeline, 'run_pipeline', lambda c, **kw: kw)
    options = cockpit_service.start_analysis(Industry.AI)
    assert options['enricher'].keywords == {'light': True}


def test_pipeline_preserves_sources_and_missing_data_warnings(tmp_path):
    s = snapshot(tmp_path, projects=[])
    runs = run_snapshot(s)
    assert runs[0].discovery['sources']['foekat']['complete'] is None
    assert runs[0].discovery['warnings']
