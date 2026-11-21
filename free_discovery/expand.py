"""Incremental discovery beyond technology names. No LLM, new source or paid API.

Runs after a baseline collect run. Existing results are retained, and an interrupted
batch resumes from per-company checkpoints. A fixed hash orders the broader queue.
"""
import argparse,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from .core import assess,dump,hashid,company_key
from .collect import website_probe,cached_pages,export
from .network import Fetcher

VERSION='expand-v2'

def select_new(entities,existing,limit):
    done={c['id'] for c in existing}
    unseen=[c for c in entities if c['id'] not in done]
    def priority(c):
        corporate=bool(re.search(r'\b(?:gmbh|ug|ag|se)\b',c['name'],re.I))
        nonoperating=bool(c.get('administrative_name_flag') or re.search(r'\b(?:holdco|bidco|acquico|propco)\b|real estate|\basset management\b|kirchengemeinde|steuerberatung',c['name'],re.I))
        return (nonoperating,not corporate,len(company_key(c['name']))>35,hashid(c['id']))
    return sorted(unseen,key=priority)[:limit],len(unseen)

def merge_results(existing,updates):
    byid={c['id']:c for c in existing}
    for company in updates:byid[company['id']]=company
    return sorted(byid.values(),key=lambda c:c['id'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','run'])
    p.add_argument('--work',type=Path,default=Path('data/open-discovery'))
    p.add_argument('--out',type=Path,default=Path('data/open-discovery/export'))
    p.add_argument('--new-companies',type=int,default=512)
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--max-domains',type=int,default=6)
    p.add_argument('--max-extra-pages',type=int,default=4)
    p.add_argument('--refresh-matched',action='store_true',help='Reassess previously identified company websites with the improved text reader; cached pages only')
    p.add_argument('--offline',action='store_true')
    a=p.parse_args()
    if a.new_companies<0 or not 1<=a.workers<=8 or a.max_domains<1 or not 0<=a.max_extra_pages<=8:p.error('Invalid research budget')
    manifest=json.loads((a.work/'discovery_manifest.json').read_text(encoding='utf-8'))
    start,end=manifest['start'],manifest['end']
    existing=json.loads((a.work/'results.json').read_text(encoding='utf-8'))
    entities=json.loads((a.work/'all_entities.json').read_text(encoding='utf-8'))
    selected,unseen=select_new(entities,existing,a.new_companies)
    summary={'version':VERSION,'start':start,'end':end,'baseline_researched':len(existing),
        'unseen_entities':unseen,'scheduled_new':len(selected),'refresh_matched':a.refresh_matched,
        'max_domains':a.max_domains,'max_extra_pages':a.max_extra_pages,'selection':'No sector-name requirement; corporate and non-administrative names first, fixed hash order',
        'llm_calls':0,'paid_api_calls':0}
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if a.command=='plan':return
    batch_id=hashid([VERSION,start,end,[c['id'] for c in selected],a.refresh_matched,a.max_domains,a.max_extra_pages])
    checkpoints=a.work/'expansion'/batch_id;checkpoints.mkdir(parents=True,exist_ok=True)
    dump(checkpoints/'manifest.json',summary)
    refresh=[c for c in existing if c.get('page_evidence')] if a.refresh_matched else []
    fetch=Fetcher(a.work/'http',a.offline)
    def task(c,replay=False):
        path=checkpoints/(hashid([c['id'],replay])+'.json')
        if path.exists():return json.loads(path.read_text(encoding='utf-8'))
        if replay:
            pages=cached_pages(c,a.work/'http');errors=c.get('fetch_errors',[])
        else:pages,errors=website_probe(c,fetch,a.max_domains,a.max_extra_pages)
        result=assess(dict(c),pages,start,end)
        result['fetch_errors']=errors
        result['page_evidence']=[{k:v for k,v in page.items() if k not in ('text','website')} for page in pages]
        result['research_version']=VERSION
        dump(path,result)
        return result
    updates=[];jobs_count=len(selected)+len(refresh)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs={pool.submit(task,c,False):c for c in selected}
        jobs.update({pool.submit(task,c,True):c for c in refresh})
        for i,future in enumerate(as_completed(jobs),1):
            company=jobs[future]
            try:updates.append(future.result())
            except Exception as exc:
                updates.append({**company,'status':'review_required','open_questions':['Expansion failed: '+str(exc)],'industries':[]})
            if i%25==0 or i==jobs_count:print('EXPANSION',i,'/',jobs_count,'qualified_in_updates',sum(c.get('status')=='qualified_candidate' for c in updates),flush=True)
    combined=merge_results(existing,updates)
    dump(a.work/'results.json',combined)
    for company in updates:dump(a.work/'companies'/(hashid([company['id'],start,end,'v1'])+'.json'),company)
    before={c['id'] for c in existing if c.get('status')=='qualified_candidate'}
    after={c['id'] for c in combined if c.get('status')=='qualified_candidate'}
    summary.update(completed_new=len(selected),reassessed=len(refresh),total_researched=len(combined),
        added_candidate_ids=sorted(after-before),removed_candidate_ids=sorted(before-after),qualified_unique=len(after))
    dump(a.out/'expansion_report.json',summary);dump(checkpoints/'completed.json',summary)
    manifest['scheduled']=len(combined);manifest['researchable']=len(entities)
    manifest['last_expansion']=batch_id
    dump(a.work/'discovery_manifest.json',manifest);dump(a.out/'discovery_manifest.json',manifest)
    export(combined,a.out,start,end,200)

if __name__=='__main__':main()
