"""Evidence-backed calendar and career history; never reconstruct missing valuations."""
import calendar,json,re
from collections import defaultdict
from datetime import datetime,date,time,timedelta,timezone
from .calendar import BERLIN
from .config import now,eur


def day_window(day):
    try:d=date.fromisoformat(day)
    except (ValueError,TypeError):raise ValueError('Ungültiges Datum; JJJJ-MM-TT erwartet')
    start=datetime.combine(d,time(),BERLIN)
    return d.isoformat(),start.astimezone(timezone.utc).isoformat(),(start+timedelta(days=1)).astimezone(timezone.utc).isoformat()


def month_window(month=None):
    month=month or datetime.now(timezone.utc).astimezone(BERLIN).strftime('%Y-%m')
    if not re.fullmatch(r'\d{4}-\d{2}',month):raise ValueError('Ungültiger Monat; JJJJ-MM erwartet')
    try:first=date.fromisoformat(month+'-01');days=calendar.monthrange(first.year,first.month)[1]
    except ValueError:raise ValueError('Ungültiger Kalendermonat')
    if not 2000<=first.year<=2100:raise ValueError('Kalendermonat außerhalb 2000–2100')
    _,start,_=day_window(first.isoformat());_,_,end=day_window(first.replace(day=days).isoformat())
    return month,first,days,start,end


def local_day(stamp):return datetime.fromisoformat(stamp).astimezone(BERLIN).date().isoformat()


def career(db,aid,as_of=None):
    agent=db.one('SELECT id,department,created_at FROM agents WHERE id=?',(aid,))
    if not agent:raise ValueError('Agent fehlt')
    check_current=as_of is None
    as_of=as_of or now();initial='research' if aid<=50 else 'demo' if aid<=75 else 'fund'
    changes=[]
    for row in db.all("SELECT * FROM decisions WHERE kind='rotation' AND status='applied' AND applied_at IS NOT NULL AND applied_at<=? ORDER BY applied_at,id",(as_of,)):
        p=json.loads(row['payload'])
        if aid not in (p.get('first'),p.get('second')):continue
        first=aid==p['first']
        changes.append({'decision_id':row['id'],'at':row['applied_at'],'from':p['from_first'] if first else p['from_second'],
                        'to':p['from_second'] if first else p['from_first'],'reason':row['reason']})
    periods=[];department=initial;started=agent['created_at'];reason='Dokumentierte Startaufstellung';decision=None;complete=True
    for change in changes:
        if change['from']!=department:complete=False
        periods.append({'department':department,'started_at':started,'ended_at':change['at'],'reason':reason,'decision_id':decision})
        department=change['to'];started=change['at'];reason=change['reason'];decision=change['decision_id']
    periods.append({'department':department,'started_at':started,'ended_at':None,'reason':reason,'decision_id':decision})
    # Direct/legacy role edits without an applied decision must not look like a
    # known full career. Current assignment is still shown separately.
    if check_current and department!=agent['department']:complete=False
    return {'periods':periods,'changes':changes,'complete':complete,'current_department':agent['department'],
            'source':'Startaufstellung und tatsächlich ausgeführte Teamwechsel. Geplante Wechsel zählen nicht.',
            'note':None if complete else 'Lücke in den gespeicherten Rollenwechseln; frühere Abteilungen sind nicht vollständig belegbar.'}


def department_at(db,aid,stamp):
    timeline=career(db,aid,stamp)
    return timeline['periods'][-1]['department']


def performance_history(db,aid,through=None):
    """All prior roles and per-role results, cut off BEFORE the requested day ends."""
    day,_,end=day_window(through or datetime.now(timezone.utc).astimezone(BERLIN).date().isoformat())
    as_of=min(end,now());timeline=career(db,aid,as_of)
    fills=db.all('SELECT portfolio_id,side,realized_u,fee_u,created_at FROM fills WHERE agent_id=? AND created_at<? ORDER BY created_at',(aid,as_of))
    roles=[]
    for role in ('research','demo','fund'):
        trades=[f for f in fills if ('fund' if f['portfolio_id']=='fund' else f['portfolio_id'].split('-')[0])==role]
        closed=[f for f in trades if f['side']=='sell']
        roles.append({'department':role,'fills':len(trades),'closed_trades':len(closed),'realized_eur':eur(sum(f['realized_u'] for f in trades)),
                      'fees_eur':eur(sum(f['fee_u'] for f in trades)),
                      'winning_closes':sum(f['realized_u']>0 for f in closed),'losing_closes':sum(f['realized_u']<0 for f in closed),
                      'trading_days':len({local_day(f['created_at']) for f in trades})})
    reviews=[];seen=set()
    for r in db.all('SELECT id,score,summary,created_at FROM manager_reviews WHERE agent_id=? AND created_at<? ORDER BY created_at DESC LIMIT 5000',(aid,as_of)):
        reviewed_day=local_day(r['created_at'])
        if reviewed_day in seen:continue
        seen.add(reviewed_day);reviews.append(r)
        if len(reviews)==7:break
    reports=db.all('''SELECT id,report_date,SUBSTR(content,1,280) content FROM
        (SELECT *,ROW_NUMBER() OVER(PARTITION BY report_date ORDER BY created_at DESC,id DESC) rank
         FROM agent_reports WHERE agent_id=? AND report_date<? AND created_at<?)
        WHERE rank=1 ORDER BY report_date DESC LIMIT 3''',(aid,day,as_of))
    tests=db.one('SELECT COUNT(*) n FROM backtests WHERE agent_id=? AND created_at<?',(aid,as_of))['n']
    return {'as_of':as_of,'roles':roles,'career':{'periods':timeline['periods'],'complete':timeline['complete'],'note':timeline['note']},
            'recent_reviews':reviews,'previous_reports':reports,'research_tests':tests,
            'interpretation':'Demo- und Fondsbeträge getrennt bewerten; unterschiedliche Kapitalbasis. Stichprobengröße, frühere Entscheidungen und Verbesserungen prüfen. Kurzer Gewinnlauf beweist keinen Vorteil.'}


def compact_history(history):
    return {'as_of':history['as_of'],'roles':history['roles'],'research_tests':history['research_tests'],
            'career_complete':history['career']['complete'],'role_changes':max(0,len(history['career']['periods'])-1),
            'recent_roles':history['career']['periods'][-3:],
            'review_scores':[r['score'] for r in history['recent_reviews']],
            'previous_reports':history['previous_reports'][:1]}


def calendar_month(db,month=None,at=None):
    at=at or datetime.now(timezone.utc);today=at.astimezone(BERLIN).date().isoformat()
    month,first,days,start,end=month_window(month)
    end=min(end,at.astimezone(timezone.utc).isoformat())
    fund=db.one("SELECT initial_u,created_at FROM portfolios WHERE id='fund'")
    fills=db.all("SELECT agent_id,side,realized_u,fee_u,created_at FROM fills WHERE portfolio_id='fund' AND created_at>=? AND created_at<? ORDER BY created_at",(start,end))
    snapshots=db.all("SELECT * FROM equity WHERE portfolio_id='fund' AND created_at>=? AND created_at<? ORDER BY created_at,id",(start,end))
    baseline=db.one("SELECT * FROM equity WHERE portfolio_id='fund' AND created_at<? ORDER BY created_at DESC,id DESC LIMIT 1",(start,))
    ratings=db.all('SELECT agent_id,score,summary,created_at FROM manager_reviews WHERE created_at>=? AND created_at<? ORDER BY created_at,id',(start,end))
    names={r['id']:r['name'] for r in db.all('SELECT id,name FROM agents')}
    daily_fills=defaultdict(list);daily_equity=defaultdict(list);daily_scores=defaultdict(dict)
    for f in fills:daily_fills[local_day(f['created_at'])].append(f)
    for r in snapshots:daily_equity[local_day(r['created_at'])].append(r)
    for r in ratings:daily_scores[local_day(r['created_at'])][r['agent_id']]=r
    rows=[]
    from .daily import closing_time
    for n in range(1,days+1):
        day=first.replace(day=n).isoformat();trades=daily_fills[day];observed=daily_equity[day];last=observed[-1] if observed else None
        opening=baseline
        if not opening and fund and local_day(fund['created_at'])==day:
            opening={'equity_u':fund['initial_u'],'valuation_complete':1,'created_at':fund['created_at'],'initial':True}
        has_data=bool(trades or observed or daily_scores[day]);future=day>today
        known=bool(last and opening and last['valuation_complete'] and opening['valuation_complete'])
        # An older endpoint spans several days. Show it as a gap, never a precise daily profit.
        gap=(date.fromisoformat(day)-date.fromisoformat(local_day(opening['created_at']))).days if opening else None
        if gap is not None and gap>1:known=False
        pnl=eur(last['equity_u']-opening['equity_u']) if known else None
        latest=list(daily_scores[day].values());top=max((r['score'] for r in latest),default=None)
        leaders=[{'agent_id':r['agent_id'],'name':names.get(r['agent_id'],str(r['agent_id'])),'score':r['score'],'reason':r['summary']} for r in latest if r['score']==top]
        # External capital movements cannot be mistaken for trading performance.
        _,a,b=day_window(day)
        flows=db.one("SELECT COALESCE(SUM(delta_u),0) amount FROM ledger WHERE portfolio_id='fund' AND created_at>=? AND created_at<? AND kind NOT IN ('execution','initial','initial_virtual_capital')",(a,b))['amount']
        if pnl is not None:pnl-=eur(flows)
        closed=bool(last and datetime.fromisoformat(last['created_at'])>=closing_time(db,day) and at>=closing_time(db,day))
        rows.append({'date':day,'status':'future' if future else 'no_data' if not has_data else 'closed' if closed else 'provisional',
            'pnl_eur':None if future else pnl,'realized_eur':eur(sum(f['realized_u'] for f in trades)) if has_data and not future else None,
            'fills':len(trades),'closed_trades':sum(f['side']=='sell' for f in trades),
            'best_agents':leaders[:20] if not future else [],'best_agent_count':len(leaders) if not future else 0,
            'best_basis':'Höchste letzte Managerbewertung dieses Tages (0–10); Gleichstände werden angezeigt.',
            'opening_at':opening['created_at'] if opening else None,'closing_at':last['created_at'] if last else None,
            'valuation_complete':known,'baseline_gap_days':gap,'capital_flow_eur':eur(flows),
            'valuation_note':None if known else 'Keine lückenlos belegte Tagesbewertung; realisierte Ergebnisse separat sehen.'})
        if last:baseline=last
    return {'month':month,'days':rows,'as_of':now(),'time_zone':'Europe/Berlin','paper_only':True,
            'scope':'Fonds-P&L aus gespeicherten Bewertungen, bereinigt um Kapitalbewegungen. Demo-Ergebnisse sind kein Fondsgewinn.'}


def agent_archive(db,aid,day=None,month=None):
    from .reporting import day_view
    day=day or datetime.now(timezone.utc).astimezone(BERLIN).date().isoformat()
    day_window(day);month,first,days,start,end=month_window(month or day[:7])
    activity=defaultdict(lambda:{'trades':0,'analyses':0,'backtests':0,'web_research':0,'realized_eur':0})
    for table,key in (('fills','trades'),('analyses','analyses'),('backtests','backtests'),('web_research','web_research')):
        cols='created_at,realized_u' if table=='fills' else 'created_at'
        for r in db.all(f'SELECT {cols} FROM {table} WHERE agent_id=? AND created_at>=? AND created_at<?',(aid,start,end)):
            record=activity[local_day(r['created_at'])];record[key]+=1
            if table=='fills':record['realized_eur']+=eur(r['realized_u'])
    return {'agent_id':aid,'month':month,'days':[{'date':first.replace(day=i).isoformat(),**activity[first.replace(day=i).isoformat()]} for i in range(1,days+1)],
            'career':career(db,aid),'performance':performance_history(db,aid,day),'day':day_view(db,aid,day),'as_of':now()}
