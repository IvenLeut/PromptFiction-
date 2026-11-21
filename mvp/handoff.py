"""Export the new workflow through the existing AnalysisRun contract.

Coverage does NOT masquerade as legacy confidence_score. Rich explanations stay
in evaluation_v2; unassessed risk remains null.
"""
from datetime import datetime
from models import AnalysisRun,EvaluatedLead,Industry,SearchCriteria,ResearchResult,PipelineIssue
from research_models import Evidence
from mvp.scoring import months_before


def analysis_run(run,industry:Industry):
    selected=[a for a in run.assessments if industry.value in a.dossier.sectors]
    leads=[];issues=[]
    for a in selected:
        d=a.dossier
        source_map={s.url:s for s in d.sources}
        evidence=[Evidence(source=source_map[f.source_url].title,url=f.source_url,finding=f.value+' | '+f.quote,field=k,
            retrieved_at=datetime.fromisoformat(source_map[f.source_url].retrieved_at.replace('Z','+00:00')),
            verification_status='source_matched') for k,f in d.facts.items() if f.source_url in source_map]
        description=d.facts['description'].value if 'description' in d.facts else 'Produktbeschreibung noch offen.'
        stage='Pre-Seed' if a.stage.startswith('Pre-Seed') else 'Seed' if a.stage.startswith('Seed') else 'Unbekannt'
        leads.append(EvaluatedLead(id=d.id,name=d.name,description=description,industry=industry,country=d.facts['country'].value if 'country' in d.facts else None,
            source_url=d.website or next(iter(source_map)),website=d.website,source_name='Combined discovery / MVP',is_demo=False,
            discovery_source='combined_mvp',country_evidence=next((e for e in evidence if e.field=='country'),None),evidence=evidence,
            founded_on=d.earliest_founding if d.earliest_founding==d.latest_founding else None,
            founding_year=d.earliest_founding.year if d.earliest_founding else None,
            overall_score=a.score,company_score=a.company_score,market_potential_score=a.market_score,risk_score=None,
            stage_classification=stage,value_proposition=description,investment_thesis=a.hypothesis,risks=[a.risk],
            open_questions=a.next_steps+a.reasons,score_drivers=[c.reason for c in a.criteria if c.points is not None],
            eligibility_status='Excluded' if a.queue=='excluded' else 'Unknown',hard_exclusions=a.reasons if a.queue=='excluded' else [],
            fund_fit_rationale=a.htgf_fit,technology_score=a.company_score,
            evaluation_v2={'model':run.rule_version,'score_upper':a.score_upper,'screening_coverage':a.coverage,
                'coverage_meaning':'Share of six evidenced screening fields, not legacy confidence or accuracy.',
                'criteria':[c.model_dump() for c in a.criteria],'queue':a.queue,'project_ids':d.project_ids,
                'founding_interval':[str(d.earliest_founding),str(d.latest_founding)],'input_hash':run.input_hash}))
        if a.queue!='ranked':issues.append(PipelineIssue(lead_id=d.id,stage='evaluation',message='; '.join(a.reasons)))
    return AnalysisRun(criteria=SearchCriteria(industry=industry,limit=run.options.limit),mode='live',
        created_at=datetime.fromisoformat(run.created_at),discovered_count=len(selected),enriched_count=len(selected),
        result=ResearchResult(leads=leads,issues=issues),
        discovery={'cohort':'mvp_companies','as_of':str(run.options.as_of),'founded_from':str(months_before(run.options.as_of,run.options.max_age_months)),
            'counts':{'recent_companies':sum(a.queue=='ranked' for a in selected),'review_required':sum(a.queue=='research' for a in selected)},
            'warnings':run.warnings,'run_id':run.id,'mode':run.options.mode,'rule_version':run.rule_version})
