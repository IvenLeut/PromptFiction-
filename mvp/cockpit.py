"""German management cockpit for the integrated live workflow."""
import csv
import io
import json
import os
import plotly.graph_objects as go
import streamlit as st
from analyst_store import db_path, load_decisions
from mvp.briefs import DEFAULT_MODEL, brief_for
from mvp.detail import OUTREACH_LABELS, company_detail
from mvp.style import apply_theme
from mvp.transfer import export_workspace, import_workspace
from models import Industry
from mvp.contracts import RunOptions
from mvp.engine import data_dir, load_current
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


def rows_for(items, decisions, *, live=False):
    return [{'Unternehmen':a.dossier.name,'Status':QUEUES[a.queue],'Score':a.score,'Kurzprofil':brief.headline,
      'Offener Nachweis':a.reasons[0] if a.reasons else '',
      'Quellenstand':{'fresh':'Live geprüft','failed':'Website nicht bestätigt','snapshot':'Gespeicherte Belege'}.get(a.dossier.refresh_status,'Offen'),
      'Kontaktstatus':
      OUTREACH_LABELS.get(decisions.get(a.dossier.id,{}).get('outreach_status'), 'Noch nicht kontaktiert'),
      'Branche':', '.join(a.dossier.sectors),
      'Offene Score-Spanne':f'{a.score:.1f}–{a.score_upper:.1f}' if a.score is not None and a.score_upper is not None else 'Offen',
      'Risiko / Prüfbedarf':a.risk,'Marktpotenzialscore':a.market_score,'Unternehmensscore':a.company_score,
      'Stage':a.stage,'Produkt / Value Proposition':brief.summary,
      'Investmenthypothese':brief.thesis,'Gesprächsanlass':brief.why,'Datenabdeckung':round(a.coverage*100),
      'Entscheidung':DECISIONS.get(decisions.get(a.dossier.id,{}).get('decision','Pending Review'),'Offen'),
      'HTGF-Profil':a.htgf_fit,'Website':a.dossier.website,'ID':a.dossier.id} for a, brief in [(x,brief_for(x, live=live)) for x in items]]


def open_company(identity, contact=False):
    st.session_state.mvp_company=identity
    st.session_state.mvp_page='Unternehmensanalyse'
    st.session_state.fr_contact_tab=contact


@st.fragment(run_every='2s')
def progress_panel():
    state=jobs().snapshot()
    if state['status']=='running':
        st.progress(state['percent'],text=state['message'])
        st.caption('Recherche läuft im Hintergrund. Sie können währenddessen den letzten Ergebnisstand prüfen.')
        if st.button('Analyse anhalten',key='stop-analysis'):jobs().cancel();st.rerun()
    elif state['status']=='done' and state.get('result_id') != st.session_state.get('mvp_loaded_run'):
        st.session_state.mvp_run=load_current()
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
    st.markdown('<div class="fr-kicker">FounderRadar / Deal Sourcing</div>', unsafe_allow_html=True)
    st.title('Frühe Technologieunternehmen finden')
    st.write('Recherchiere junge Technologieunternehmen und bereite das nächste Gründergespräch vor.')
    with st.container(border=True):
        sectors=st.multiselect('Branchen',[i.value for i in Industry],default=[i.value for i in Industry])
        st.caption('Suchprofil: Deutschland · Gründung in den letzten 24 Monaten')
        state=jobs().snapshot()
        if st.button('Live-Analyse starten',type='primary',disabled=not sectors or state['status']=='running',width='stretch'):
            jobs().start(RunOptions.cockpit_live(sectors=sectors))
            st.rerun()
        st.caption('FounderRadar lädt aktuelle Quellen, prüft Projektspuren und berechnet die Firmenprofile im Hintergrund.')


def overview(run,decisions):
    cols=st.columns(4)
    for col,label,key in zip(cols,['Bewertbare Firmen','Recherche offen','Außerhalb Suchprofil','Projekte zugeordnet'],['ranked','research','excluded','projects_resolved']):
        col.metric(label,run.counts[key])
    st.subheader('Nächste Gespräche vorbereiten')
    top=[a for a in run.assessments if a.queue=='ranked'][:3]
    if not top:st.info('Noch keine ausreichend belegten Firmen im Suchprofil. Die offene Recherche zeigt genau, was fehlt.')
    for col,a in zip(st.columns(3),top):
        with col,st.container(border=True):
            brief=brief_for(a, live=bool(run.counts.get('live_profiles')))
            st.markdown('**'+a.dossier.name+'**')
            st.caption(f'{a.score:.1f} / 100 · {brief.headline}')
            st.write(brief.why)
            st.button('Unternehmen prüfen',key='open-'+a.dossier.id,on_click=open_company,args=(a.dossier.id,),width='stretch')
    ranked=[a for a in run.assessments if a.queue=='ranked'][:run.options.limit]
    if ranked:
        st.subheader('Gesprächspriorität und offene Nachweise')
        ranked.reverse()
        names = [a.dossier.name for a in ranked]
        chart = go.Figure()
        chart.add_bar(name='Belegt', y=names, x=[a.score for a in ranked], orientation='h', marker_color='#17624d')
        chart.add_bar(name='Noch offen', y=names, x=[round((a.score_upper or a.score)-a.score,1) for a in ranked],
                      orientation='h', marker_color='#a6d4bf')
        chart.update_layout(barmode='stack', height=max(240, 38*len(ranked)+86), xaxis_range=[0,100],
                            margin=dict(l=0,r=8,t=8,b=25), yaxis=dict(automargin=True),
                            legend=dict(orientation='h',y=-.15))
        st.plotly_chart(chart, width='stretch', config={'displayModeBar':False})


def longlist(run,decisions):
    st.title('Longlist')
    st.caption('Unternehmen finden, Belege prüfen und den Kontaktstatus verfolgen.')
    a,b,c=st.columns([1.1,1,1.5])
    groups = {'all': 'Alle passenden und offenen', **QUEUES}
    group=a.selectbox('Ergebnisgruppe',list(groups),format_func=groups.get)
    shortlist=b.checkbox('Nur Shortlist')
    query=c.text_input('Unternehmen suchen')
    items=[x for x in run.assessments if (x.queue==group or (group=='all' and x.queue!='excluded'))
           and query.casefold() in x.dossier.name.casefold()
           and (not shortlist or decisions.get(x.dossier.id,{}).get('decision') in {'Watchlist','Contact'})]
    st.caption(f'{len(items)} Firmen · Bewertete Firmen zuerst, offene Nachweise in derselben Liste.')
    rows=rows_for(items, decisions, live=bool(run.counts.get('live_profiles')))
    if rows:
        st.dataframe(rows,hide_index=True,width='stretch',column_config={
            'Score':st.column_config.NumberColumn(format='%.1f'),
            'Kurzprofil':st.column_config.TextColumn(width='medium'),
            'Datenabdeckung':st.column_config.ProgressColumn(min_value=0,max_value=100,format='%d%%'),
            'Website':st.column_config.LinkColumn(), 'ID':None},height=380)
        selected=st.selectbox('Unternehmen öffnen',items,format_func=lambda x:x.dossier.name + ' · ' + QUEUES[x.queue])
        left,right=st.columns(2)
        left.button('Deep Dive öffnen',on_click=open_company,args=(selected.dossier.id,),type='primary')
        right.button('Erstkontakt vorbereiten',on_click=open_company,args=(selected.dossier.id,True))
        st.download_button('Longlist als CSV',csv_export(rows),file_name='FounderRadar-Longlist.csv',mime='text/csv')
    else:st.info('Keine Unternehmen in dieser Ansicht.')
    if group in {'research','excluded'}:
        for item in items:
            with st.expander(item.dossier.name):
                for reason in item.reasons:st.write('• '+reason)
    with st.expander('Projekt-Recherche: kompletter Bestand'):
        st.caption(f'{run.counts["projects_attempted"]} von {run.counts["projects"]} Projektspuren bisher bearbeitet; {run.counts.get("projects_this_run",0)} in diesem Lauf. Nicht aufgelöste Projekte sind keine gezählten Unternehmen.')
        st.dataframe(run.project_audit,hide_index=True,width='stretch')
        st.download_button('Projektprotokoll exportieren',json.dumps(run.project_audit,ensure_ascii=False,indent=2),file_name='FounderRadar-Projektprotokoll.json',mime='application/json')


def detail(run, decisions):
    if not run.assessments:
        st.info("Noch keine Unternehmen im aktuellen Lauf.")
        return
    companies = {item.dossier.id: item for item in run.assessments}
    identities = list(companies)
    current = st.session_state.get("mvp_company")
    identity = st.selectbox("Unternehmen", identities,
                            index=identities.index(current) if current in companies else 0,
                            format_func=lambda key: companies[key].dossier.name)
    st.session_state.mvp_company = identity
    company_detail(companies[identity], run, decisions.get(identity, {}), QUEUES, DECISIONS,
                   default_contact=st.session_state.get("fr_contact_tab", False))


def activities(run,decisions):
    st.title('Aufgaben & Shortlist')
    rows=[]
    for a in run.assessments:
        s=decisions.get(a.dossier.id,{})
        if not s:continue
        rows.append({'Unternehmen':a.dossier.name,'Entscheidung':DECISIONS.get(s['decision'],s['decision']),
            'Kontakt':OUTREACH_LABELS.get(s.get('outreach_status'), 'Noch nicht kontaktiert'),
            'Nächster Schritt':s.get('next_action',''),'Verantwortlich':s.get('analyst_name',''),'Fällig':s.get('due_date',''),'Status':s.get('task_status','Open')})
    if rows:
        st.dataframe(rows,hide_index=True,width='stretch')
        st.download_button('Aufgaben exportieren',csv_export(rows),'FounderRadar-Aufgaben.csv','text/csv')
        followups=[a for a in run.assessments if a.dossier.id in decisions]
        selected=st.selectbox('Wiedervorlage öffnen',followups,format_func=lambda a:a.dossier.name)
        st.button('Kontakt & Aufgabe öffnen', on_click=open_company, args=(selected.dossier.id,True))
    else:st.info('Öffnen Sie ein Unternehmen, speichern Sie eine Entscheidung und legen Sie den nächsten Schritt fest.')


def methodology(run):
    st.title('Modell & Quellen')
    st.write('**1. Finden** · Aktuelle deutsche LEI-Einträge ergänzen den Förderkatalog. Pro Lauf werden weitere Projektspuren und eine begrenzte Auswahl neuer LEI-Firmen geprüft. Die Rechtsform und das Gründungsfenster werden unabhängig vom Produkt belegt.')
    st.write('**2. Kontext:** Öffentliche Unternehmensseiten liefern belegte Screening-Merkmale. Fehlende und widersprüchliche Angaben bleiben offen.')
    st.write('**3. Bewerten:** Produkt & Technologie 40 %, Kunde & Nutzen 35 %, Entwicklungsnachweis 25 %. Die Rangfolge nutzt die belegte Untergrenze bei festen Gewichten. Die Obergrenze addiert die noch offenen Gewichte. Mindestens Produkt, technischer Ansatz und Kundentyp müssen vorliegen. Das Intervall ist keine statistische Prognose.')
    st.write('**Datenabdeckung:** Sechs Merkmale: Technologie, Produkt, Kunde, Nutzen, Entwicklungsnachweis, Team. Drei belegte Merkmale entsprechen 50 %. Das ist keine Genauigkeit und kein Erfolgsversprechen.')
    st.write('**Suchprofil** · Gründung in Deutschland innerhalb von 24 Monaten. Wenn ein Nachweis fehlt, bleibt die Firma mit offenem Prüfpunkt in der Longlist.')
    st.write('**Live-Kommentare** · Unternehmensseiten liefern Produkt-, Kunden- und Entwicklungssignale. Regeln formulieren daraus Gesprächsanlass und Prüfhypothese. Abrufbare Vergleichsangebote werden als eigene Marktquellen angezeigt. Die Marktgröße bleibt Gegenstand des Umsatzszenarios.')
    st.link_button('Öffentliche HTGF-Kriterien','https://www.htgf.de/')
    st.caption('Regelversion '+CONFIG['version']+' · Internes Screening · Berechnung ohne KI')
    with st.expander('Gespeicherte Belege für eine Offline-Vorführung'):
        st.caption('Diese Option berechnet vorhandene Quellen erneut und kennzeichnet den Lauf als offline.')
        if st.button('Offline neu berechnen', disabled=jobs().snapshot()['status']=='running'):
            jobs().start(RunOptions(mode='replay', sectors=run.options.sectors if run else RunOptions().sectors))
            st.rerun()
    if run:
        st.json({'Analyse':run.id,'Stichtag':str(run.options.as_of),'Modus':run.options.mode,'Discovery-Stand':run.source_snapshot_date,'Eingabe-Hash':run.input_hash,'Zähler':run.counts})
        with st.expander(f'Quellenhinweise und Abruffehler ({len(run.warnings)})'):
            for warning in run.warnings:st.write(warning)
        st.download_button('Gesamten Analyselauf exportieren',run.model_dump_json(indent=2),'FounderRadar-Analyse.json','application/json')


def workspace():
    st.title('Daten & Einrichtung')
    st.subheader('Dein lokaler Arbeitsstand')
    st.write('Jede entpackte Kopie hat ihre eigenen Analyseläufe, Notizen, Entscheidungen und Wiedervorlagen.')
    st.caption('Entscheidungen, Aufgaben und Kontaktverlauf')
    st.code(str(db_path()), language=None)
    st.caption('Ergebnisse, Rechercheprotokoll und KI-Entwürfe')
    st.code(str(data_dir()), language=None)
    st.download_button('Arbeitsstand sichern', export_workspace(), 'FounderRadar-Arbeitsstand.json', 'application/json')
    st.caption('Die Sicherung enthält Notizen, Aufgaben und Kontaktstatus. Analyseläufe werden unter Modell & Quellen separat exportiert.')
    archive = st.file_uploader('Arbeitsstand aus JSON übernehmen', type=['json'])
    if archive and st.button('Arbeitsstand importieren'):
        try:
            count=import_workspace(archive.getvalue())
        except (ValueError, OSError):
            st.error('Die Datei konnte nicht importiert werden. Verwende eine gültige FounderRadar-Sicherung bis 15 MB.')
        else:
            st.success(f'{count} Entscheidungen übernommen. Neuere lokale Einträge haben Vorrang.')
    st.subheader('OpenAI für redaktionelle Deep Dives')
    st.write('Hinterlege bei Bedarf einen Schlüssel für diese Browsersitzung. Die OpenAI-Analyse wird im jeweiligen Deep Dive manuell gestartet.')
    st.text_input('OpenAI API-Key', type='password', value=st.session_state.get('fr_openai_key', ''), key='fr_openai_key_input')
    st.text_input('OpenAI Modell', value=st.session_state.get('fr_openai_model', os.environ.get('FOUNDERRADAR_OPENAI_MODEL',DEFAULT_MODEL)),
                  key='fr_openai_model_input')
    st.session_state.fr_openai_key=st.session_state.fr_openai_key_input
    st.session_state.fr_openai_model=st.session_state.fr_openai_model_input.strip() or DEFAULT_MODEL
    if st.session_state.fr_openai_key or os.environ.get('OPENAI_API_KEY'):
        st.caption('API-Key verfügbar · Modell '+st.session_state.fr_openai_model)
    st.link_button('OpenAI API-Dokumentation', 'https://developers.openai.com/api/docs/quickstart')


def main():
    st.set_page_config(page_title='FounderRadar | Research Cockpit',page_icon='◉',layout='wide')
    apply_theme()
    if 'mvp_run' not in st.session_state:
        st.session_state.mvp_run=load_current()
        st.session_state.mvp_loaded_run=st.session_state.mvp_run.id if st.session_state.mvp_run else None
    if st.session_state.mvp_run is None:
        jobs().start_initial(RunOptions.cockpit_live())
    run=st.session_state.mvp_run
    decisions=load_decisions('live')
    with st.sidebar:
        st.markdown('<div class="fr-brand">Founder<span>Radar</span></div>', unsafe_allow_html=True)
        st.caption('Research Cockpit')
        page=st.radio('Arbeitsbereich',['Start & Übersicht','Longlist','Unternehmensanalyse','Aufgaben','Modell & Quellen','Daten & Einrichtung'],key='mvp_page')
        st.divider()
        st.caption('Deutschland · fünf Technologiebranchen')
        if run:
            st.caption('Letzter Lauf: '+run.created_at[:16].replace('T',' ')+' UTC')
            st.caption('Stichtag: '+str(run.options.as_of))
            st.caption('Live-Analyse abgeschlossen' if run.options.mode=='live' else 'Aus gespeicherten Fakten neu berechnet')
        st.caption('Interne Screening-Hilfe nach öffentlichen HTGF-Kriterien.')
    progress_panel()
    if page=='Start & Übersicht':
        controls()
        if run:
            st.caption('Ergebnisse des zuletzt abgeschlossenen Laufs')
            if run.options.mode == 'live' and run.counts.get('live_profiles'):
                st.write(f"{run.counts['web_requests']} Abrufversuche · {run.counts['gleif_records']} LEI-Einträge gelesen · "
                         f"{run.counts['gleif_new']} neue Firmen zur Prüfung")
            overview(run,decisions)
        elif jobs().snapshot()['status']=='running':
            st.info('Deine erste Live-Analyse läuft. Die Longlist erscheint nach der Berechnung.')
    elif page=='Modell & Quellen':methodology(run)
    elif page=='Daten & Einrichtung':workspace()
    elif not run:st.info('Hier erscheinen die Ergebnisse, sobald eine Analyse abgeschlossen ist.')
    elif page=='Longlist':longlist(run,decisions)
    elif page=='Unternehmensanalyse':detail(run,decisions)
    else:activities(run,decisions)
