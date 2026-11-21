"""German management cockpit for the integrated live workflow."""
import csv
import io
import json
from datetime import date
import streamlit as st
from analyst_store import load_decisions,save_decision,load_history
from cockpit_style import theme
from models import Industry
from mvp.contracts import RunOptions
from mvp.engine import load_last
from mvp.jobs import Jobs
from mvp.scoring import CONFIG

QUEUES={'ranked':'Bewertbar','research':'Recherche offen','excluded':'Außerhalb Suchprofil'}
DECISIONS={'Pending Review':'Offen','Watchlist':'Shortlist','Contact':'Gespräch vorbereiten','Reject':'Zurückgestellt'}


@st.cache_resource
def jobs():return Jobs()


def csv_export(rows):
    target=io.StringIO()
    if rows:
        writer=csv.DictWriter(target,fieldnames=list(rows[0]),delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})
    return ('\ufeff'+target.getvalue()).encode('utf-8')


def rows_for(items, decisions):
    return [{'Unternehmen':a.dossier.name,'Branche':', '.join(a.dossier.sectors),'Score':a.score,
      'Offene Score-Spanne':f'{a.score:.1f}–{a.score_upper:.1f}' if a.score is not None and a.score_upper is not None else 'Offen',
      'Risiko / Prüfbedarf':a.risk,'Marktpotenzialscore':a.market_score,'Unternehmensscore':a.company_score,
      'Stage':a.stage,'Produkt / Value Proposition':a.dossier.facts['description'].value if 'description' in a.dossier.facts else 'Beschreibung noch offen',
      'Investmenthypothese':a.hypothesis,'Datenabdeckung':round(a.coverage*100),
      'Status':QUEUES[a.queue],'Entscheidung':DECISIONS.get(decisions.get(a.dossier.id,{}).get('decision','Pending Review'),'Offen'),
      'HTGF-Profil':a.htgf_fit,'Website':a.dossier.website,'ID':a.dossier.id} for a in items]


def open_company(identity):
    st.session_state.mvp_company=identity
    st.session_state.mvp_page='Unternehmensanalyse'


@st.fragment(run_every='2s')
def progress_panel():
    state=jobs().snapshot()
    if state['status']=='running':
        st.progress(state['percent'],text=state['message'])
        st.caption('Recherche läuft im Hintergrund. Sie können währenddessen den letzten Ergebnisstand prüfen.')
        if st.button('Analyse anhalten',key='stop-analysis'):jobs().cancel();st.rerun()
    elif state['status']=='done' and state.get('result_id') != st.session_state.get('mvp_loaded_run'):
        st.session_state.mvp_run=load_last()
        st.session_state.mvp_loaded_run=state['result_id']
        st.rerun()
    elif state['status'] in {'failed','interrupted'}:
        terminal=(state['status'],state.get('started_at'),state.get('error'))
        if st.session_state.get('mvp_terminal') != terminal:
            st.session_state.mvp_terminal=terminal
            st.rerun()
        st.warning(state['message'])
        if state.get('error'):st.caption(state['error'])


def controls():
    st.title('Frühe Technologieunternehmen finden')
    st.write('Projektspuren auflösen, Unternehmensquellen prüfen und eine nachvollziehbare Gesprächspriorität berechnen.')
    with st.container(border=True):
        left,right=st.columns([2,1])
        sectors=left.multiselect('Branchen',[i.value for i in Industry],default=[i.value for i in Industry])
        age=right.selectbox('Gründung innerhalb',[24,36],format_func=lambda n:f'{n} Monate'+(' · euer Suchprofil' if n==24 else ' · HTGF-Altersgrenze'))
        a,b,c=st.columns([1.5,1,1])
        mode=a.selectbox('Analysemodus',['live','replay'],format_func=lambda m:'Quellen live prüfen' if m=='live' else 'Gespeicherte Fakten neu berechnen')
        budget=b.selectbox('Projekt-Recherchebudget',[0,6,12,30,60],index=2,help='So viele Projektspuren werden zusätzlich zur bestehenden Firmenliste untersucht. Der Rest bleibt sichtbar offen.')
        limit=c.selectbox('Longlist anzeigen',[5,10,15],index=2)
        state=jobs().snapshot()
        if st.button('Analyse starten',type='primary',disabled=not sectors or state['status']=='running',width='stretch'):
            jobs().start(RunOptions(sectors=sectors,max_age_months=age,mode=mode,project_budget=budget,limit=limit))
            st.rerun()
        st.caption('Live = neue Webseitenabrufe auf Basis des vorhandenen Discovery-Pools. Kein KI-Modell. Förderbeginn gilt nie als Firmengründung.')


def overview(run,decisions):
    cols=st.columns(4)
    for col,label,key in zip(cols,['Bewertbare Firmen','Recherche offen','Außerhalb Suchprofil','Projekte zugeordnet'],['ranked','research','excluded','projects_resolved']):
        col.metric(label,run.counts[key])
    st.subheader('Nächste Gespräche vorbereiten')
    top=[a for a in run.assessments if a.queue=='ranked'][:3]
    if not top:st.info('Noch keine ausreichend belegten Firmen im Suchprofil. Die offene Recherche zeigt genau, was fehlt.')
    for col,a in zip(st.columns(3),top):
        with col,st.container(border=True):
            st.markdown('**'+a.dossier.name+'**')
            st.metric('Screening-Score',f'{a.score:.1f} / 100')
            st.caption(f'{round(a.coverage*6)}/6 Screening-Merkmale belegt · {a.stage}')
            st.write(a.dossier.facts.get('description').value if a.dossier.facts.get('description') else a.hypothesis)
            st.button('Unternehmen prüfen',key='open-'+a.dossier.id,on_click=open_company,args=(a.dossier.id,),width='stretch')
    st.caption('Score = belegte Untergrenze der Gesprächspriorität. Offene Dimensionen bleiben als Spanne sichtbar. Datenabdeckung ist keine Trefferwahrscheinlichkeit.')


def longlist(run,decisions):
    st.title('Longlist')
    a,b,c=st.columns([1.1,1,1.5])
    group=a.selectbox('Ergebnisgruppe',list(QUEUES),format_func=QUEUES.get)
    shortlist=b.checkbox('Nur Shortlist')
    query=c.text_input('Unternehmen suchen')
    items=[x for x in run.assessments if x.queue==group and query.casefold() in x.dossier.name.casefold()
           and (not shortlist or decisions.get(x.dossier.id,{}).get('decision') in {'Watchlist','Contact'})]
    limit=run.options.limit if group=='ranked' else len(items)
    visible=items[:limit]
    st.caption(f'{len(visible)} von {len(items)} Firmen · Rangfolge: Score, Datenabdeckung, stabile Unternehmens-ID. Mehrfachbranchen werden nur einmal gezählt.')
    rows=rows_for(visible,decisions)
    if rows:
        st.dataframe(rows,hide_index=True,width='stretch',column_config={
            'Score':st.column_config.NumberColumn(format='%.1f'),
            'Datenabdeckung':st.column_config.ProgressColumn(min_value=0,max_value=100,format='%d%%'),
            'Website':st.column_config.LinkColumn(), 'ID':None},height=380)
        selected=st.selectbox('Unternehmen öffnen',visible,format_func=lambda x:x.dossier.name)
        st.button('Analyse und nächste Schritte',on_click=open_company,args=(selected.dossier.id,),type='primary')
        st.download_button('Longlist als CSV',csv_export(rows),file_name='FounderRadar-Longlist.csv',mime='text/csv')
    else:st.info('Keine Unternehmen in dieser Ansicht.')
    if group!='ranked':
        for item in visible:
            with st.expander(item.dossier.name):
                for reason in item.reasons:st.write('• '+reason)
    with st.expander('Projekt-Recherche: kompletter Bestand'):
        st.caption(f'{run.counts["projects_attempted"]} von {run.counts["projects"]} Projektspuren bisher bearbeitet; {run.counts.get("projects_this_run",0)} in diesem Lauf. Nicht aufgelöste Projekte sind keine gezählten Unternehmen.')
        st.dataframe(run.project_audit,hide_index=True,width='stretch')
        st.download_button('Projektprotokoll exportieren',json.dumps(run.project_audit,ensure_ascii=False,indent=2),file_name='FounderRadar-Projektprotokoll.json',mime='application/json')


def detail(run,decisions):
    st.title('Unternehmensanalyse')
    if not run.assessments:st.info('Noch keine Ergebnisse.');return
    ids=[a.dossier.id for a in run.assessments]
    current=st.session_state.get('mvp_company',ids[0])
    identity=st.selectbox('Unternehmen',ids,index=ids.index(current) if current in ids else 0,
        format_func=lambda x:next(a.dossier.name for a in run.assessments if a.dossier.id==x))
    st.session_state.mvp_company=identity
    item=next(a for a in run.assessments if a.dossier.id==identity);d=item.dossier
    st.subheader(d.name)
    st.caption(f'{QUEUES[item.queue]} · {item.htgf_fit}')
    if d.website:st.link_button('Unternehmenswebsite',d.website)
    c1,c2,c3=st.columns(3)
    c1.metric('Screening-Score',f'{item.score:.1f}' if item.score is not None else 'Offen')
    c2.metric('Screening-Merkmale belegt',f'{round(item.coverage*6)} / 6')
    c3.metric('Belegte Quellen',len(d.sources))
    tabs=st.tabs(['Einordnung','Bewertung & Belege','Quellen','Nächste Schritte'])
    with tabs[0]:
        st.write(item.hypothesis)
        st.write('**Stage:** '+item.stage)
        st.write('**Risiko / Prüfbedarf:** '+item.risk)
        st.write('**Gründung:** '+(str(d.earliest_founding) if d.earliest_founding==d.latest_founding and d.earliest_founding else f'{d.earliest_founding} bis {d.latest_founding}' if d.earliest_founding else 'Offen'))
        st.caption(d.founding_basis or 'Kein Gründungsnachweis gefunden.')
        if d.project_ids:st.write('**Projektzuordnung:** '+', '.join(d.project_ids))
        if item.reasons:st.warning('\n\n'.join(dict.fromkeys(item.reasons)))
        for step in item.next_steps:st.write('• '+step)
    with tabs[1]:
        st.dataframe([{'Kriterium':c.label,'Gewicht':c.weight,'Punkte':c.points,'Regel':c.reason} for c in item.criteria],hide_index=True,width='stretch')
        st.caption('Score = 0,40 × Produkt + 0,35 × Kunde/Nutzen + 0,25 × Entwicklungsnachweis. Offene Kriterien bleiben unbelegt; die Untergrenze enthält nur belegte Beiträge. Unternehmensscore = Produkt & Technologie.')
        if item.score_upper is not None:st.info(f'Belegte Untergrenze: {item.score:.1f} · Obergrenze bei offenen Kriterien: {item.score_upper:.1f}. Keine statistische Erfolgswahrscheinlichkeit.')
        for c in item.criteria:
            with st.expander(c.label,expanded=True):
                if not c.facts:st.write('Keine Belege.');continue
                for key in c.facts:
                    f=d.facts[key]
                    st.write(f'**{key}:** {f.value}')
                    st.caption('Quellenausschnitt: '+f.quote)
                    st.link_button('Beleg öffnen',f.source_url)
    with tabs[2]:
        st.caption('Website-Aussagen sind Selbstauskünfte. Abrufdatum und Herkunft bleiben erhalten; ein Hochschulförderprojekt ist keine Finanzierungsrunde der Firma.')
        st.dataframe([{'Quelle':s.title,'URL':s.url,'Abgerufen':s.retrieved_at,'Art':s.kind} for s in d.sources],hide_index=True,width='stretch',column_config={'URL':st.column_config.LinkColumn()})
        st.download_button('Unternehmensdossier als JSON',item.model_dump_json(indent=2),file_name=d.id+'.json',mime='application/json')
    with tabs[3]:
        saved=decisions.get(identity,{})
        with st.form('decision-'+identity):
            choices=list(DECISIONS)
            decision=st.selectbox('Entscheidung',choices,index=choices.index(saved.get('decision','Pending Review')),format_func=DECISIONS.get)
            reason=st.text_area('Begründung',value=saved.get('reason',''))
            notes=st.text_area('Notizen',value=saved.get('notes',''))
            action=st.text_input('Nächster Schritt',value=saved.get('next_action',item.next_steps[0] if item.next_steps else ''))
            owner=st.text_input('Verantwortlich',value=saved.get('analyst_name',''))
            due=st.date_input('Fällig am',value=date.fromisoformat(saved['due_date']) if saved.get('due_date') else None)
            task=st.selectbox('Aufgabenstatus',['Open','Done'],index=1 if saved.get('task_status')=='Done' else 0,format_func=lambda x:'Offen' if x=='Open' else 'Erledigt')
            if st.form_submit_button('Entscheidung und Aufgabe speichern',type='primary'):
                try:
                    save_decision('live',identity,decision,notes,reason,action,owner,due.isoformat() if due else '',task_status=task)
                    st.success('Gespeichert.');st.rerun()
                except ValueError as ex:st.error(str(ex))
        history=load_history('live',identity)
        if history:
            with st.expander('Änderungsverlauf'):st.dataframe(history,hide_index=True,width='stretch')


def activities(run,decisions):
    st.title('Aufgaben & Shortlist')
    rows=[]
    for a in run.assessments:
        s=decisions.get(a.dossier.id,{})
        if not s:continue
        rows.append({'Unternehmen':a.dossier.name,'Entscheidung':DECISIONS.get(s['decision'],s['decision']),
            'Nächster Schritt':s.get('next_action',''),'Verantwortlich':s.get('analyst_name',''),'Fällig':s.get('due_date',''),'Status':s.get('task_status','Open')})
    if rows:st.dataframe(rows,hide_index=True,width='stretch');st.download_button('Aufgaben exportieren',csv_export(rows),'FounderRadar-Aufgaben.csv','text/csv')
    else:st.info('Öffnen Sie ein Unternehmen, speichern Sie eine Entscheidung und legen Sie den nächsten Schritt fest.')


def methodology(run):
    st.title('Modell & Quellen')
    st.write('**1. Finden:** Bestehender Discovery-Pool aus GLEIF/Open Data und Förderkatalog. Projektnamen werden mit Hochschulverweisen und Firmenimpressen abgeglichen.')
    st.write('**2. Kontext:** Öffentliche Unternehmensseiten liefern belegte Screening-Merkmale. Fehlende und widersprüchliche Angaben bleiben offen.')
    st.write('**3. Bewerten:** Produkt & Technologie 40 %, Kunde & Nutzen 35 %, Entwicklungsnachweis 25 %. Die Rangfolge nutzt die belegte Untergrenze bei festen Gewichten. Die Obergrenze addiert die noch offenen Gewichte. Mindestens Produkt, technischer Ansatz und Kundentyp müssen vorliegen. Das Intervall ist keine statistische Prognose.')
    st.write('**Datenabdeckung:** Sechs Merkmale: Technologie, Produkt, Kunde, Nutzen, Entwicklungsnachweis, Team. Drei belegte Merkmale entsprechen 50 %. Das ist keine Genauigkeit und kein Erfolgsversprechen.')
    st.write('**HTGF-Profil:** Pre-Seed/Seed, Technologiebezug, Deutschland und höchstens drei Jahre. Euer voreingestellter Suchfilter ist enger: 24 Monate. Rundengröße und Kapitalbedarf werden im Gespräch geprüft; eine frühere Seed-Finanzierung führt nicht automatisch zum Ausschluss.')
    st.link_button('Öffentliche HTGF-Kriterien','https://www.htgf.de/')
    st.caption('Regelversion '+CONFIG['version']+' · Keine offizielle HTGF-Scorecard · KI-Aufrufe: 0')
    if run:
        st.json({'Analyse':run.id,'Stichtag':str(run.options.as_of),'Modus':run.options.mode,'Discovery-Stand':run.source_snapshot_date,'Eingabe-Hash':run.input_hash,'Zähler':run.counts})
        with st.expander(f'Quellenhinweise und Abruffehler ({len(run.warnings)})'):
            for warning in run.warnings:st.write(warning)
        st.download_button('Gesamten Analyselauf exportieren',run.model_dump_json(indent=2),'FounderRadar-Analyse.json','application/json')


def main():
    st.set_page_config(page_title='FounderRadar | Early Stage Cockpit',page_icon='◉',layout='wide')
    theme()
    st.markdown('''<style>[data-testid="stHeader"]{display:block!important;background:transparent}
    [data-testid="stToolbar"]{display:flex!important}
    [data-testid="stToolbar"] button:not([data-testid="stExpandSidebarButton"]){display:none!important}
    [data-testid="stMainBlockContainer"]{padding-top:3.5rem!important}</style>''',unsafe_allow_html=True)
    if 'mvp_run' not in st.session_state:
        st.session_state.mvp_run=load_last()
        st.session_state.mvp_loaded_run=st.session_state.mvp_run.id if st.session_state.mvp_run else None
    run=st.session_state.mvp_run
    decisions=load_decisions('live')
    with st.sidebar:
        st.markdown('## FounderRadar')
        st.caption('EARLY STAGE · RESEARCH COCKPIT')
        page=st.radio('Arbeitsbereich',['Start & Übersicht','Longlist','Unternehmensanalyse','Aufgaben','Modell & Quellen'],key='mvp_page')
        st.divider()
        st.caption('Deutschland · fünf Technologiebranchen')
        if run:
            st.caption('Letzter Lauf: '+run.created_at[:16].replace('T',' ')+' UTC')
            st.caption('Stichtag: '+str(run.options.as_of))
            st.caption('Quellen live abgerufen' if run.options.mode=='live' else 'Aus gespeicherten Fakten neu berechnet')
        st.caption('Interne Screening-Hilfe nach öffentlichen HTGF-Kriterien.')
    progress_panel()
    if page=='Start & Übersicht':
        controls()
        if run:
            st.caption('Darunter sehen Sie den gespeicherten letzten Lauf. „Analyse starten“ erstellt einen neuen Lauf.')
            overview(run,decisions)
    elif page=='Modell & Quellen':methodology(run)
    elif not run:st.info('Starten Sie zuerst eine Analyse unter „Start & Übersicht“.')
    elif page=='Longlist':longlist(run,decisions)
    elif page=='Unternehmensanalyse':detail(run,decisions)
    else:activities(run,decisions)
