"""Legacy Open-Data-only provider, selectable with FOUNDERRADAR_SOURCING=open_data.

Reads only qualified records. Research is a separate reproducible CLI operation,
not a long crawl triggered by a dashboard button. No paid API or LLM required.
"""
import json
import os
from pathlib import Path
from models import RawLead, SearchCriteria

def search(criteria: SearchCriteria) -> list[RawLead]:
    root=Path(os.environ.get('FOUNDERRADAR_DISCOVERY_DIR',Path(__file__).resolve().parents[1]/'data'/'open-discovery'/'export'))
    file=root/(criteria.industry.value.replace(' / ','_').replace('/','_')+'.json')
    if not file.exists():
        raise FileNotFoundError(f'Noch kein Open-Data-Sourcinglauf für {criteria.industry.value}: {file}. Siehe docs/OPEN_DATA_DISCOVERY.md.')
    records=json.loads(file.read_text(encoding='utf-8'))
    leads=[RawLead.model_validate(r) for r in records]
    if any(l.is_demo or l.country!='DE' or l.country_evidence is None or l.industry!=criteria.industry for l in leads):
        raise ValueError('Ungültiger Open-Data-Export: Branche, Länderbeleg oder Demo-Flag falsch')
    if len({l.id for l in leads})!=len(leads):raise ValueError('Doppelte Firmenidentität im Branchenexport')
    return leads[:criteria.limit]
