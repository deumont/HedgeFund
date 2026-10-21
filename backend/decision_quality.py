"""Manager evidence of decisions as recorded BEFORE execution, not hindsight stories."""
import json
from .db import dumps
from .daily_target import MANAGER_POLICY

RUBRIC={
 'traders':{'source_quality_and_timing':25,'causal_case_and_priced_in':25,'counterevidence_and_invalidation':20,'risk_and_execution_discipline':20,'net_outcomes_with_sample_uncertainty':10},
 'research':{'source_quality_and_timing':35,'research_design_and_validation':35,'falsification_honesty_and_learning':30},
 'rules':[
  MANAGER_POLICY,
  'Forschung/Warteschlange kann technisch keine Orders platzieren. Null Trades dort sind keine Schwäche; nur Recherche, Tests und Lernen bewerten.',
  'Historische Trades nach dem damaligen Konto und der damaligen Rolle beurteilen. Ein späterer Abteilungswechsel macht frühere Demo-/Fondstrades nicht zu Forschungsorders.',
  'Diskretionäre Nachrichten-/Fundamentalagenten haben keine feste algorithmische Strategie. Für sie sind Online-Recherche, Quellenvergleich, Wissen, Gegenargumente und Vorbereitung die Aufgabe; keine Backtests fordern oder für fehlende Backtests abwerten. Technische/regelbasierte Agenten behalten ihre passenden Tests.',
  'Gut belegt, vorausschauend und risikobewusst kann auch bei Verlust eine hohe Bewertung verdienen. Fehlender Beleg ist kein Beweis für eine gute Entscheidung.',
  'Zufallsgewinn und kurzer Glückslauf sind kein Informationsvorteil. Gewinn alleine rechtfertigt keinen hohen Prozessscore oder Aufstieg.',
  'Qualität der konkreten Argumente prüfen, nicht Wortzahl oder bloße Anzahl von Quellen/Trades. Keine nachträglichen Erklärungen als vorherige Motive ausgeben.',
  '0–10 bleibt eine vorläufige begründete Managerbeurteilung, kein statistischer Renditenachweis. Fehlende Vorabbelege offen benennen.'
 ]}


def compact_quality(value):
    """Bound manager batches while keeping one original decision and its evidence IDs."""
    def shorten(obj):
        if isinstance(obj,str):return obj[:400]
        if isinstance(obj,list):return [shorten(x) for x in obj[:3]]
        if isinstance(obj,dict):return {k:shorten(v) for k,v in obj.items()}
        return obj
    result=shorten(value)
    for key in ('pretrade_cases','research_analyses','web_research'):
        result[key]=shorten(value[key][:1])
        result[key+'_available']=len(value[key])
    result['sampling_note']='Auszug der gespeicherten Belege; eine jüngste Entscheidung, Analyse und Web-Recherche. Keine vollständige Tageschronik.'
    return result


def quality_evidence(db,aid,day=None):
    from .reporting import window
    from .web_research import recent_research
    day,start,end=window(day)
    agent=db.one('SELECT department FROM agents WHERE id=?',(aid,))
    trades=db.all("""SELECT f.id,f.side,f.symbol,f.portfolio_id,f.created_at,f.realized_u,s.created_at signal_at,s.observations
      FROM fills f LEFT JOIN order_signals os ON os.order_id=f.order_id
      LEFT JOIN signal_decisions s ON s.id=os.signal_id
      WHERE f.agent_id=? AND f.created_at>=? AND f.created_at<? ORDER BY f.created_at DESC LIMIT 4""",(aid,start,end))
    cases=[]
    for row in trades:
        proof=json.loads(row.pop('observations') or '{}');dossier=proof.get('decision_dossier')
        recorded_before=bool(row['signal_at'] and row['signal_at']<=row['created_at'])
        if dossier and dossier.get('created_at','9999')>row['created_at']:dossier=None
        # Read the immutable fill-linked signal, never the newest/post-hoc thesis.
        cases.append({**row,'pre_execution_signal':recorded_before,
            'thesis':proof.get('event_thesis') if recorded_before else None,
            'decision_dossier':dossier if recorded_before else None,
            'strategy':proof.get('strategy_spec') if recorded_before else None,
            'experiment':proof.get('experiment') if recorded_before else None,
            'data_policy':proof.get('policy') if recorded_before else None})
    analyses=[]
    for r in db.all('SELECT id,result,created_at FROM analyses WHERE agent_id=? AND created_at>=? AND created_at<? ORDER BY created_at DESC LIMIT 2',(aid,start,end)):
        result=json.loads(r['result'])
        analyses.append({'id':r['id'],'created_at':r['created_at'],**{k:result.get(k) for k in ('hypothesis','conclusion','rejected_alternatives','evidence_ids')}})
    tests=[]
    for r in db.all('SELECT id,symbol,result,created_at FROM backtests WHERE agent_id=? AND created_at>=? AND created_at<? ORDER BY created_at DESC LIMIT 2',(aid,start,end)):
        result=json.loads(r['result']);oos=result.get('out_of_sample') or {}
        tests.append({'id':r['id'],'symbol':r['symbol'],'created_at':r['created_at'],'type':result.get('type','technical'),
            'observations':result.get('observations'),'point_in_time_observations':result.get('point_in_time_observations'),
            'caveats':result.get('caveats',[]),'oos_return_pct':oos.get('return_pct'),'oos_trades':len(oos.get('trades') or [])})
    web=[{'id':r['id'],'created_at':r['created_at'],'status':r['status'],'report':r['report'][:2000],'sources':r['sources'][:5],
          'publication_time_verified':False} for r in recent_research(db,aid,1) if start<=r['created_at']<end]
    return {'date':day,'execution_eligible':agent['department']!='research','evaluation_role':agent['department'],
            'pretrade_cases':cases,'research_analyses':analyses,'strategy_tests':tests,'web_research':web,
            'note':'Rechercheberichte und Tests sind keine ausgeführten Trades; ein späterer Bericht erklärt frühere Orders nicht nachträglich.'}
