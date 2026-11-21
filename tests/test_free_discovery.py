import unittest,tempfile,json,sys,gzip,hashlib
from pathlib import Path
from free_discovery.core import founding_claims,identity_match,registration_conflict,assess,gleif_row,merge_sources,industries
from free_discovery.collect import export,gleif_collect
from free_discovery.archive_index import block,warc
from free_discovery.imprints import seeds
from free_discovery.expand import select_new,merge_results
from free_discovery.network import parse_html

def company():
 return {'id':'test-1','name':'Testrobot GmbH','city':'Berlin','postal_code':'10115','country':'DE',
  'registration':'HRB 12345','founded_on':'2025-04-01','projects':[],'administrative_name_flag':False,
  'source_url':'https://example.org/entity/1','country_source':'https://example.org/entity/1','source_name':'Fixture'}

class TestDiscovery(unittest.TestCase):
 def test_inline_markup_does_not_break_technology_sentence(self):
  page=parse_html('<p>We develop <strong>software</strong> for automated industrial inspections.</p><p>Founded in 2025.</p>','https://example.org')
  self.assertIn('We develop software for automated industrial inspections.',page['text'])
  self.assertIn('\nFounded in 2025.',page['text'])
 def test_expansion_includes_neutral_names_and_preserves_baseline(self):
  first=company();first['id']='existing'
  neutral={**company(),'id':'neutral','name':'Zoravan GmbH'}
  selected,remaining=select_new([first,neutral],[first],10)
  self.assertEqual([x['id'] for x in selected],['neutral']);self.assertEqual(remaining,1)
  result=merge_results([first],[neutral])
  self.assertEqual({c['id'] for c in result},{'existing','neutral'})
  self.assertEqual(select_new([neutral,first],[first],10),select_new([first,neutral],[first],10))
 def test_url_fragments_do_not_duplicate_research_pages(self):
  page=parse_html('<a href="/about#team">Team</a><a href="/about#mission">Mission</a>','https://example.org')
  self.assertEqual(page['links'],['https://example.org/about'])
 def test_no_date_invention(self):
  self.assertEqual(founding_claims('Copyright 2025. EU project started 2025. First crawl 2025.'),[])
  self.assertEqual(founding_claims('Founded in 2025.')[0]['year'],2025)
 def test_timeline_does_not_use_next_event_as_founding(self):
  claims=founding_claims('2016\nals oldname gegründet\n2025\nzu newname umfirmiert')
  self.assertEqual({c['year'] for c in claims},{2016})
 def test_ai_abbreviation_requires_word_boundary(self):
  self.assertNotIn('AI / Software',industries('Aircraft from Kiel for children'))
  self.assertIn('AI / Software',industries('KI-gestützte Software'))
 def test_office_automation_is_not_industrial_deeptech(self):
  self.assertNotIn('Industrial / DeepTech',industries('We develop software for workflow automation.'))
  self.assertIn('Industrial / DeepTech',industries('We develop automation for factory production.'))
  self.assertNotIn('Industrial / DeepTech',industries('Wir entwickeln Lösungen für unterschiedliche Industrien.'))
 def test_own_ai_integrator_and_customer_sector_list(self):
  page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'Testrobot ist ein deutscher Hersteller KI-gestützter Integrationslösungen. Besonders gute Chancen haben: Biotechnologie, Software-Entwicklung und Medizin.'}
  result=assess(company(),[page],'2024-11-20','2026-11-20')
  self.assertEqual(result['industries'],['AI / Software'])
 def test_audit_hold_can_only_exclude_candidate(self):
  c=company();c['quality_hold']={'reason':'Earlier business history','source_url':'https://example.org/history'}
  page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'We develop robot technology for industrial manufacturing.'}
  self.assertEqual(assess(c,[page],'2024-11-20','2026-11-20')['status'],'review_required')
 def test_identity_requires_register_or_address(self):
  self.assertFalse(identity_match(company(),'Testrobot GmbH develops robots'))
  self.assertTrue(identity_match(company(),'Testrobot GmbH HRB 12345'))
  self.assertFalse(identity_match(company(),'Otherrobot GmbH HRB 12345'))
  self.assertFalse(identity_match(company(),'Testrobot GmbH HRB 123456'))
  self.assertFalse(identity_match(company(),'OtherTestrobot GmbH HRB 12345'))
 def test_lei_issue_date_not_formation(self):
  raw={'id':'XYZ','attributes':{'entity':{'legalName':{'name':'Testrobot GmbH'},'legalAddress':{'country':'DE'},'creationDate':'2010-01-01','status':'ACTIVE'},'registration':{'initialRegistrationDate':'2025-01-01'}},'links':{'self':'https://example.org'}}
  self.assertIsNone(gleif_row(raw,'2024-11-20','2026-11-20'))
 def test_register_conflict_not_overridden_by_same_address(self):
  c=company()
  text=f"{c['name']} {c['postal_code']} {c['city']} HRB 99999"
  self.assertTrue(registration_conflict(c,text))
  self.assertFalse(identity_match(c,text))
 def test_evidence_and_age_conflict(self):
  pages=[{'url':'https://example.org/product','website':'https://example.org','identity_verified':True,'text':'We develop proprietary robot technology for industrial manufacturing.'}]
  self.assertEqual(assess(company(),pages,'2024-11-20','2026-11-20')['status'],'qualified_candidate')
  pages[0]['text']+=' Founded in 2001.'
  self.assertEqual(assess(company(),pages,'2024-11-20','2026-11-20')['status'],'review_required')
 def test_legal_boilerplate_not_innovation(self):
  pages=[{'url':'https://example.org/impressum','website':'https://example.org','identity_verified':True,'text':'We develop proprietary robot technology for industrial manufacturing.'}]
  self.assertEqual(assess(company(),pages,'2024-11-20','2026-11-20')['status'],'review_required')
 def test_unknown_date_not_filled_from_grant(self):
  c=company();c['founded_on']=None;c['projects']=[{'title':'AI project','objective':'Novel software','start':'2025-01-01'}]
  self.assertEqual(assess(c,[],'2024-11-20','2026-11-20')['status'],'review_required')
 def test_existing_business_history_overrides_new_legal_date(self):
  pages=[{'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'Seit 2002 entwickeln wir proprietäre Software für industrielle Automation.'}]
  result=assess(company(),pages,'2024-11-20','2026-11-20')
  self.assertTrue(result['date_conflict']);self.assertEqual(result['status'],'review_required')
 def test_operating_history_is_distinct_from_founder_experience(self):
  page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'Testrobot setzt seit über 20 Jahren digitale Projekte um. We develop robot technology for industrial manufacturing.'}
  self.assertEqual(assess(company(),[page],'2024-11-20','2026-11-20')['status'],'review_required')
  page['text']='Unser Gründer arbeitet seit über 20 Jahren als Ingenieur. We develop robot technology for industrial manufacturing.'
  self.assertEqual(assess(company(),[page],'2024-11-20','2026-11-20')['status'],'qualified_candidate')
 def test_own_product_sentence_preferred_to_generic_explanation(self):
  page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'Software platforms can be developed by companies of every size. We develop proprietary robot technology for industrial manufacturing.'}
  result=assess(company(),[page],'2024-11-20','2026-11-20')
  self.assertTrue(result['innovation_evidence'][0]['quote'].startswith('We develop'))
 def test_operating_history_before_company_subject(self):
  page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'Seit mehr als 15 Jahren sind wir auf Robotik spezialisiert. We develop robot technology for industrial manufacturing.'}
  self.assertTrue(assess(company(),[page],'2024-11-20','2026-11-20')['date_conflict'])
 def test_separate_product_evidence_retains_both_sectors(self):
  page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':'We develop software for municipal planning workflows. We develop battery technology for energy storage systems.'}
  result=assess(company(),[page],'2024-11-20','2026-11-20')
  self.assertEqual(set(result['industries']),{'AI / Software','ClimateTech'})
 def test_marketing_strategy_and_external_platform_not_own_technology(self):
  for text in ['Wir entwickeln Strategien für Marketing und AI sowie Verkaufs-Trainings für Einzelhändler.', 'Integrated into OtherCompany’s digital and AI-supported platform, Testrobot delivers efficient operations.']:
   page={'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':text}
   self.assertEqual(assess(company(),[page],'2024-11-20','2026-11-20')['status'],'review_required')
 def test_acquisition_firm_not_technology_startup_from_ai_word(self):
  text='Wir erwerben profitable B2B-Dienstleistungsunternehmen mit Fondskapital und entwickeln sie langfristig durch KI weiter.'
  pages=[{'url':'https://example.org','website':'https://example.org','identity_verified':True,'text':text}]
  result=assess(company(),pages,'2024-11-20','2026-11-20')
  self.assertTrue(result['administrative_activity_flag']);self.assertEqual(result['status'],'review_required')
 def test_imprint_seed_never_inherits_crawl_as_founding(self):
  doc={'url':'https://example.de/impressum','timestamp':'20251001000000','text':'Testrobot GmbH\n10115 Berlin\nAmtsgericht Berlin\nHRB 12345'}
  rows,audit=seeds([doc],[])
  self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['founded_on'])
  self.assertEqual(audit[0]['status'],'new_imprint_seed')
 def test_ambiguous_imprint_does_not_merge_corporations(self):
  doc={'url':'https://example.de/impressum','text':'Testrobot GmbH\nOtherrobot GmbH\n10115 Berlin\nAmtsgericht Berlin\nHRB 12345'}
  self.assertEqual(seeds([doc],[])[0],[])
 def test_exact_name_city_join(self):
  g=company();g['website_candidates']=[]
  c={**company(),'id':'cordis-1','city':'Munich','projects':[{'title':'x'}],'website_candidates':[]}
  self.assertEqual(len(merge_sources([g],[c])),2)
 def test_gleif_end_date_includes_last_day_but_not_next(self):
  class Fake:
   def get(self,url,params,**kwargs):
    self.params=params
    return {'text':json.dumps({'meta':{'pagination':{'total':2}},'links':{},'data':[
     {'id':'one','attributes':{'entity':{'creationDate':'2026-11-20T18:00:00Z'}}},
     {'id':'two','attributes':{'entity':{'creationDate':'2026-11-21T00:00:00Z'}}}]})}
  fetch=Fake();rows=gleif_collect(fetch,'2024-11-20','2026-11-20')
  self.assertTrue(fetch.params['filter[entity.creationDate]'].endswith('2026-11-21'))
  self.assertEqual([r['id'] for r in rows],['one'])
 def test_commoncrawl_timestamp_is_in_index_prefix(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'cdx-00000.gz-0.gz').write_bytes(gzip.compress(b'de,example)/ 20261001000000 {"url":"https://example.de/"}\n'))
   result=block(root,'unused',('de,example)/','cdx-00000.gz',0,100))
   self.assertEqual(result[0]['timestamp'],'20261001000000')
 def test_warc_does_not_double_decode_origin_gzip_header(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);filename='crawl-data/test.warc.gz';offset=0
   raw=b'WARC/1.0\r\n\r\nHTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n<html><p>Legal company</p></html>'
   data=gzip.compress(raw);name=hashlib.sha256(f'{filename}:{offset}'.encode()).hexdigest()+'.warc.gz'
   (root/name).write_bytes(data)
   result=warc(root,dict(filename=filename,offset=offset,length=len(data),url='https://example.de/',timestamp='20261001000000'))
   self.assertEqual(result['text'],'Legal company')
 def test_export_contract(self):
  c=assess(company(),[{'url':'https://example.org/product','website':'https://example.org','identity_verified':True,'text':'We develop proprietary robot technology for industrial manufacturing.'}],'2024-11-20','2026-11-20')
  with tempfile.TemporaryDirectory() as folder:
   report=export([c],Path(folder),'2024-11-20','2026-11-20',200)
   self.assertEqual(report['qualified_unique'],1)
   rows=json.loads((Path(folder)/'Industrial_DeepTech.json').read_text(encoding='utf-8'))
   self.assertFalse(rows[0]['is_demo']);self.assertEqual(rows[0]['founding_year'],2025)
   if 'models' in sys.modules:
    from models import RawLead
    RawLead.model_validate(rows[0])

if __name__=='__main__':unittest.main()
