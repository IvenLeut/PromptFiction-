"""Run a frozen combined snapshot through context, scoring and cockpit contracts.

Default: offline, deterministic rules, all five industries, up to 200 per industry.
Use --context live explicitly to fetch additional public sources. No model is
enabled by this command. Capture new context once, then replay scoring offline.
"""
import argparse
import json
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from context.engine import default_lookups, enrich
from context.web import original_page
from models import Industry, SearchCriteria
from pipeline import run_pipeline
from sourcing.combined import DiscoverySnapshot, select


def run_snapshot(snapshot: DiscoverySnapshot, *, cohort='companies', limit=200, context_mode='light'):
    if context_mode not in {'light', 'live'}:
        raise ValueError('Context mode must be light or live')
    options = {'light': True} if context_mode == 'light' else {
        'load_original': original_page, 'lookups': default_lookups()}
    enricher = partial(enrich, as_of=snapshot.as_of, **options)
    runs = []
    for industry in Industry:
        run = run_pipeline(SearchCriteria(industry=industry, limit=limit), use_mock=False,
            provider=partial(select, snapshot, cohort=cohort), enricher=enricher)
        runs.append(run)
    return runs


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, default=Path('data/combined-discovery.json'))
    p.add_argument('--out', type=Path, default=Path('data/analysis'))
    p.add_argument('--cohort', choices=['companies', 'research', 'all'], default='companies')
    p.add_argument('--limit', type=int, default=200)
    p.add_argument('--context', choices=['light', 'live'], default='light')
    a = p.parse_args(argv)
    if not 1 <= a.limit <= 200:
        p.error('--limit must be between 1 and 200 per industry')
    snapshot = DiscoverySnapshot.model_validate_json(a.snapshot.read_bytes())
    runs = run_snapshot(snapshot, cohort=a.cohort, limit=a.limit, context_mode=a.context)
    a.out.mkdir(parents=True, exist_ok=True)
    for industry, run in zip(Industry, runs):
        (a.out / (industry.name.lower() + '.json')).write_text(run.model_dump_json(indent=2) + '\n', encoding='utf-8')
    summary = {'as_of': snapshot.as_of.isoformat(), 'cohort': a.cohort, 'context_mode': a.context,
        'llm_calls': 0, 'sources': snapshot.counts(),
        'industries': {r.criteria.industry.value: {'discovered': r.discovered_count, 'enriched': r.enriched_count,
            'evaluated_records': len(r.result.leads),
            'numeric_scores': sum(l.overall_score is not None for l in r.result.leads),
            'issues': len(r.result.issues)} for r in runs}}
    (a.out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if any(r.result.issues for r in runs) else 0


if __name__ == '__main__':
    raise SystemExit(main())
