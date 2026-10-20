"""Fast factual answers and durable chat requests; no synthetic model output."""
import json
import re
from datetime import datetime,timezone
from uuid import uuid5,NAMESPACE_URL
from .config import now,units
from .db import uid,dumps
from .ledger import Ledger


def reply_id(message_id):
    return str(uuid5(NAMESPACE_URL,'atlas-manager-reply:'+message_id))


def save_reply(db,message_id,text,evidence):
    rid=reply_id(message_id)
    with db.tx() as c:
        c.execute('INSERT OR IGNORE INTO chats VALUES(?,?,?,?,?)',(rid,'assistant',text,dumps(evidence),now()))
    return {'id':rid,'content':text,'evidence':evidence}


def instant_answer(db,cfg,text):
    q=text.strip().lower()
    evidence=[{'source':'Systemdaten, ohne KI-Anfrage','as_of':now()}]
    if re.fullmatch(r'(hallo|hi|hey|ey|servus|moin)[!\.\s]*',q):
        return 'Hallo. Frag mich nach Fondsstand, ausgeführten Trades oder einem bestimmten Agenten.',evidence
    agent=re.search(r'agent\D{0,5}(\d{1,3})\b',q)
    if agent and 1<=int(agent[1])<=100:
        aid=int(agent[1]); a=db.one('SELECT * FROM agents WHERE id=?',(aid,))
        fills=db.one("SELECT COUNT(*) n,COALESCE(SUM(realized_u),0)/1000000.0 pnl FROM fills WHERE agent_id=? AND side='sell'",(aid,))
        positions=db.one('SELECT COUNT(*) n FROM positions WHERE agent_id=?',(aid,))['n']
        return f"Agent {aid}: {a['name']}, {a['department']}. {'Pausiert' if a['paused'] else 'Freigegeben'}. {positions} offene Positionen, {fills['n']} geschlossene Trades, realisiert {fills['pnl']:.2f} EUR. Details stehen im Agentenprofil.",evidence
    if re.search(r'trade|order|gehandelt|gekauft|verkauft|position',q) and re.search(r'schon|heute|letzte|wie viele|offen|jemand|bisher',q):
        fills=db.all('SELECT agent_id,symbol,side,qty FROM fills ORDER BY created_at DESC LIMIT 3')
        count=db.one('SELECT COUNT(*) n FROM fills')['n']
        if not fills:return 'Bisher gibt es keine ausgeführten Paper-Orders. Die Trader warten auf gültige Signale und geeignete Ausführungsdaten.',evidence
        details='; '.join(f"Agent {x['agent_id']}: {x['side']} {x['qty']} {x['symbol']}" for x in fills)
        return f'{count} interne Paper-Ausführungen gespeichert. Zuletzt: {details}. Dies sind keine Alpaca-Brokerfills.',evidence
    if re.search(r'fonds|gewinn|verlust|vermögen|kapital|pnl',q) and re.search(r'wie|stand|aktuell|haben|hat|heute',q):
        p=Ledger(db).portfolio()
        note='' if p['valuation_complete'] else ' Bewertung unvollständig; aktuelle Rendite nicht sicher belegbar.'
        return f"Fonds: {p['equity_eur']:.2f} EUR, davon {p['cash_eur']:.2f} EUR Cash. Realisiert: {p['realized_eur']:+.2f} EUR. {len(p['positions'])} offene Positionen.{note}",evidence
    # Do not queue an AI task that is already known to be blocked.
    from .calendar import BERLIN
    at=datetime.now(timezone.utc).astimezone(BERLIN)
    start=at.replace(day=1,hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
    spent=db.one("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost_u ELSE reserved_u END),0) n FROM usage WHERE created_at>=?",(start,))['n']
    if not cfg.openai_api_key or not db.get('engine_enabled') or spent>=units(cfg.monthly_budget_eur):
        reason='KI-Monatsbudget ausgeschöpft' if cfg.openai_api_key and db.get('engine_enabled') else 'KI-Zugang fehlt oder ist pausiert'
        return f'{reason}. Neue KI-Analysen sind gerade nicht verfügbar. Fragen zu Fondsstand, Trades und Agenten beantworte ich direkt aus den Systemdaten. Der Strategiehandel läuft unabhängig weiter.',evidence
    return None


def create_request(db,cfg,text):
    mid,jid,stamp=uid(),uid(),now()
    instant=instant_answer(db,cfg,text)
    payload={'text':text,'message_id':mid}
    if instant:
        answer,evidence=instant
        payload['result']={'id':reply_id(mid),'content':answer,'evidence':evidence}
    with db.tx() as c:
        c.execute('INSERT INTO chats VALUES(?,?,?,?,?)',(mid,'user',text,dumps([{'job_id':jid}]),stamp))
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,0,?,?,?,NULL)',(jid,'chat-'+mid,'chat',None,dumps(payload),0,'completed' if instant else 'pending',stamp,stamp,stamp))
        if instant:
            c.execute('INSERT INTO chats VALUES(?,?,?,?,?)',(reply_id(mid),'assistant',answer,dumps(evidence),stamp))
    return {'job_id':jid,'message_id':mid,'status':'completed' if instant else 'pending'}
