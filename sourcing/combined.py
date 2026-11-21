"""Deterministic union of company discovery and EXIST projects; no network or AI.

Project dates are never company founding dates. Only a shared legal identifier
merges records; similar names, shared university domains and cities do not.
The snapshot keeps the review pool separately from the two-year company cohort.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field
from models import Industry, RawLead, SearchCriteria, SourceSignal
from research_models import Contract, Evidence
from sourcing.engine import SourcingError, SourcingLeads


def years_before(day: date, years: int = 2) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


class Candidate(Contract):
    lead: RawLead
    industries: list[Industry]
    source_ids: list[str]
    providers: list[str]
    kind: Literal['company', 'research_project']
    eligibility: Literal['recent_company', 'review_required', 'outside_window']
    founded_on: date | None = None
    founding_basis: str | None = None
    identity_key: str | None = None
    industry_basis: str
    reasons: list[str] = Field(default_factory=list)


class SourceStatus(Contract):
    available: bool
    complete: bool | None = None  # None means completeness was NOT documented.
    count: int = Field(ge=0)
    sha256: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DiscoverySnapshot(Contract):
    schema_version: Literal['1.0'] = '1.0'
    as_of: date
    founded_from: date
    sources: dict[str, SourceStatus]
    candidates: list[Candidate]
    warnings: list[str] = Field(default_factory=list)
    llm_calls: Literal[0] = 0
    national_completeness: Literal[False] = False

    def counts(self) -> dict:
        per_industry = {i.value: sum(c.eligibility == 'recent_company' and i in c.industries
                                   for c in self.candidates) for i in Industry}
        return {
            'unique_candidates': len(self.candidates),
            'recent_companies': sum(c.eligibility == 'recent_company' for c in self.candidates),
            'review_required': sum(c.eligibility == 'review_required' for c in self.candidates),
            'outside_window': sum(c.eligibility == 'outside_window' for c in self.candidates),
            'per_industry': per_industry,
            'target_per_industry': 200,
            'shortfall': {name: max(0, 200 - count) for name, count in per_industry.items()},
        }


def _flags(lead: RawLead) -> set[str]:
    return {flag.strip() for s in lead.signals for line in s.evidence.splitlines()
            if line.startswith('Hinweise:') for flag in line.partition(':')[2].split(',')}


def _identity(lead: RawLead) -> str | None:
    if re.fullmatch(r'gleif-[A-Z0-9]{20}', lead.id):
        return lead.id
    # Explicit labels on the project's own signals only. No recipient inference.
    keys = {m.group(1) for s in lead.signals if s.subject_lead_id in (None, lead.id)
            for m in re.finditer(r'(?m)^Company LEI:\s*([A-Z0-9]{20})\s*$', s.evidence)}
    return 'gleif-' + next(iter(keys)) if len(keys) == 1 else None


def _open_candidates(directory: Path, as_of: date) -> tuple[list[Candidate], SourceStatus]:
    path = directory / 'qualified.json'
    if not path.is_file():
        return [], SourceStatus(available=False, count=0, warnings=['Open-Data-Snapshot fehlt.'])
    content = path.read_bytes()
    records = json.loads(content)
    out = []
    for c in records:
        if (c.get('status') != 'qualified_candidate' or c.get('country') != 'DE'
                or not c.get('identity_verified') or not c.get('innovation_evidence')):
            raise ValueError('Invalid qualified company record: ' + str(c.get('id')))
        sectors = [i for i in Industry if i.value in c.get('industries', [])]
        if not sectors:
            raise ValueError('No supported industry: ' + c['id'])
        evidence = c['innovation_evidence']
        founded = date.fromisoformat(c['founded_on']) if c.get('founded_on') else None
        reasons = ['Technical self-description is not independent proof of innovation.']
        eligibility = 'recent_company'
        if c.get('date_conflict') or c.get('claimed_operating_years'):
            eligibility = 'review_required'
            reasons.append('Conflicting business age; legal incorporation does not prove a new business.')
        elif founded is None:
            eligibility = 'review_required'
            reasons.append('Exact incorporation date missing; a year alone cannot resolve the boundary.')
        elif not years_before(as_of) <= founded <= as_of:
            eligibility = 'outside_window'
        # The discovery timestamp is the recorded website research observation,
        # not a publication date or a GLEIF retrieval timestamp.
        observed = max((p['retrieved_at'] for p in c.get('page_evidence', []) if p.get('retrieved_at')), default=None)
        if observed is None:
            raise ValueError('Recorded research observation missing: ' + c['id'])
        observed_at = datetime.fromisoformat(observed.replace('Z', '+00:00'))
        signals = [SourceSignal(source=c['source_name'], type='entity_identity', url=c['source_url'],
            date=founded, subject_lead_id=c['id'], evidence=(
                f"{c['name']}; legal address {c.get('city')}, DE; creation date {founded or 'unknown'}"
                + (f'\nGründungsdatum: {founded.isoformat()}' if founded else '')
                + '\nDate meaning: legal entity creation event, not publication date.'))]
        signals += [SourceSignal(source='Company website', type='technology_self_description',
            url=e['url'], evidence=e['quote'], subject_lead_id=c['id']) for e in evidence]
        lead = RawLead(id=c['id'], name=c['name'], description=evidence[0]['quote'], industry=sectors[0],
            country='DE', location=c.get('city'), source_url=c['source_url'], source_name=c['source_name'],
            discovery_source='open_data_v1', discovered_at=observed_at,
            initial_signal='Legal identity + matched technical self-description',
            country_evidence=Evidence(source='Recorded discovery snapshot', url=c['country_source'],
                field='country', finding=f"{c['name']}: legal address {c.get('city')}, DE; identity source {c['source_name']}",
                retrieved_at=observed_at, verification_status='source_matched'),
            website=c.get('website'), founding_year=founded.year if founded else None,
            founding_month=founded.month if founded else None, signals=signals,
            prioritization_reason='Recent legal entity; business age and innovation merit require diligence.')
        out.append(Candidate(lead=lead, industries=sectors, source_ids=[lead.id], providers=['open_data'],
            kind='company', eligibility=eligibility, founded_on=founded, founding_basis=c.get('founding_basis'),
            identity_key=_identity(lead), industry_basis='identity_matched_website', reasons=reasons))
    if len({c.lead.id for c in out}) != len(out):
        raise ValueError('Duplicate company IDs in qualified snapshot')
    return out, SourceStatus(available=True, complete=None, count=len(out), sha256=hashlib.sha256(content).hexdigest(),
                            warnings=['Open data covers a subset of German companies; not the complete register.'])


def _project_candidates(path: Path | None, stats_path: Path | None) -> tuple[list[Candidate], SourceStatus]:
    if path is None or not path.is_file():
        return [], SourceStatus(available=False, count=0, warnings=['Förderkatalog-Snapshot fehlt.'])
    content = path.read_bytes()
    out = []
    for record in json.loads(content):
        lead = RawLead.model_validate(record)
        if lead.is_demo or lead.country != 'DE' or lead.country_evidence is None:
            raise ValueError('Invalid live Förderkatalog lead: ' + lead.id)
        flags = _flags(lead)
        basis = 'thema' if 'industry_basis_thema' in flags else 'institut' if 'industry_basis_institut' in flags else 'default'
        out.append(Candidate(lead=lead, industries=[lead.industry] if basis == 'thema' else [],
            source_ids=[lead.id], providers=['foekat'], kind='company' if 'recipient_company' in flags else 'research_project',
            eligibility='review_required', identity_key=_identity(lead), industry_basis=basis,
            reasons=['Project start is not incorporation; company identity and founding date need verification.']
                    + ([] if basis == 'thema' else ['Industry inferred only from institution/programme; requires product evidence.'])))
    if len({c.lead.id for c in out}) != len(out):
        raise ValueError('Duplicate Förderkatalog IDs')
    stats = json.loads(stats_path.read_text(encoding='utf-8')) if stats_path else {}
    complete = stats.get('complete')
    warnings = list(stats.get('warnings', []))
    if complete is None:
        warnings.append('Export completeness is undocumented for this snapshot.')
    return out, SourceStatus(available=True, complete=complete, count=len(out), warnings=warnings,
                            sha256=hashlib.sha256(content).hexdigest())


def combine(open_data_dir: Path, foekat_path: Path | None, *, as_of: date,
            stats_path: Path | None = None) -> DiscoverySnapshot:
    companies, company_status = _open_candidates(open_data_dir, as_of)
    projects, project_status = _project_candidates(foekat_path, stats_path)
    candidates = {c.lead.id: c for c in companies}
    identities = {c.identity_key: c for c in companies if c.identity_key}
    for project in sorted(projects, key=lambda c: c.lead.id):
        match = identities.get(project.identity_key) if project.identity_key else None
        if match is None:
            candidates[project.lead.id] = project
            continue
        match.source_ids += project.source_ids
        match.providers = sorted(set(match.providers + project.providers))
        # Preserve the source's subject ID. A copied signal is rebound only after
        # the explicit legal identity match, while provenance keeps both IDs.
        for signal in project.lead.signals:
            match.lead.signals.append(signal.model_copy(update={'subject_lead_id': match.lead.id}))
        match.reasons.append('EXIST evidence joined by explicit company LEI.')
    if not company_status.available and not project_status.available:
        raise SourcingError('Neither discovery snapshot is available; run discovery first.')
    return DiscoverySnapshot(as_of=as_of, founded_from=years_before(as_of),
        sources={'open_data': company_status, 'foekat': project_status},
        candidates=sorted(candidates.values(), key=lambda c: c.lead.id),
        warnings=company_status.warnings + project_status.warnings)


def select(snapshot: DiscoverySnapshot, criteria: SearchCriteria, *, cohort: str = 'companies') -> SourcingLeads:
    from pipeline import lead_priority
    if cohort not in {'companies', 'research', 'all'}:
        raise ValueError('Cohort must be companies, research or all')
    selected = [c for c in snapshot.candidates if criteria.industry in c.industries
                and c.eligibility != 'outside_window'
                and (cohort == 'all' or (c.eligibility == 'recent_company') == (cohort == 'companies'))]
    selected.sort(key=lambda c: (c.eligibility != 'recent_company', -lead_priority(c.lead), c.lead.id))
    leads = []
    for c in selected[:criteria.limit]:
        lead = c.lead.model_copy(deep=True, update={'industry': criteria.industry})
        # Multi-sector company evidence stays associated with the requested sector.
        if 'open_data' in c.providers:
            from free_discovery.core import industries
            quote = next((s.evidence for s in lead.signals if s.type == 'technology_self_description'
                          and criteria.industry.value in industries(s.evidence)), None)
            if quote:
                lead.description = quote
        leads.append(lead)
    result = SourcingLeads(leads, complete=all(s.available and s.complete is True for s in snapshot.sources.values()),
                          warnings=snapshot.warnings)
    result.discovery = {'as_of': snapshot.as_of.isoformat(), 'founded_from': snapshot.founded_from.isoformat(),
        'cohort': cohort, 'counts': snapshot.counts(), 'sources': {k:v.model_dump(mode='json') for k,v in snapshot.sources.items()},
        'warnings': snapshot.warnings, 'selected_ids': [l.id for l in leads],
        'candidate_metadata': {c.lead.id:c.model_dump(mode='json', exclude={'lead'}) for c in selected[:criteria.limit]}}
    return result


def search(criteria: SearchCriteria) -> SourcingLeads:
    path = Path(os.getenv('FOUNDERRADAR_COMBINED_SNAPSHOT', Path(__file__).resolve().parents[1] / 'data/combined-discovery.json'))
    if not path.is_file():
        raise SourcingError(f'Combined discovery snapshot missing: {path}. Run python -m sourcing.combined --help.')
    snapshot = DiscoverySnapshot.model_validate_json(path.read_bytes())
    return select(snapshot, criteria, cohort=os.getenv('FOUNDERRADAR_COHORT', 'companies'))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--open-data', type=Path, default=Path('data/open-discovery/export'))
    p.add_argument('--foekat', type=Path, required=True)
    p.add_argument('--foekat-stats', type=Path)
    p.add_argument('--as-of', type=date.fromisoformat, required=True)
    p.add_argument('--out', type=Path, default=Path('data/combined-discovery.json'))
    a = p.parse_args(argv)
    snapshot = combine(a.open_data, a.foekat, as_of=a.as_of, stats_path=a.foekat_stats)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = a.out.with_suffix('.tmp')
    temporary.write_text(snapshot.model_dump_json(indent=2) + '\n', encoding='utf-8')
    temporary.replace(a.out)
    print(json.dumps(snapshot.counts(), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
