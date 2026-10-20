"""Single authoritative virtual ledger. No broker method is called from this module."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from .config import now, units, eur
from .db import uid, event, put
from .calendar import phase, BERLIN

D = Decimal
ACTIVE = ('pending', 'triggered')
TECH = {'AAPL','MSFT','NVDA','AMD','META','GOOGL','AMZN','TSLA','QQQ'}


class RiskError(ValueError):
    pass


def meta(c, key, default=None):
    row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def capped_limit(caps,key,percentage_limit):
    return min(percentage_limit,units(caps[key])) if key in caps else percentage_limit


def latest_fx(c, at=None, max_days=5):
    at = at or datetime.now(timezone.utc)
    row = c.execute("SELECT * FROM fx WHERE date<=? ORDER BY date DESC LIMIT 1",
                    (at.date().isoformat(),)).fetchone()
    if not row or (at.date() - datetime.fromisoformat(row['date']).date()).days > max_days:
        raise RiskError("Kein aktueller dokumentierter EUR/USD-Kurs")
    rate = D(row['usd_per_eur'])
    if not rate.is_finite() or rate <= 0:
        raise RiskError("Ungültiger FX-Kurs")
    return rate


def valid_quote(c, symbol, limits, at=None):
    at = at or datetime.now(timezone.utc)
    q = c.execute("SELECT * FROM quotes WHERE symbol=?", (symbol,)).fetchone()
    if not q:
        raise RiskError("Keine echte Quote für " + symbol)
    age = (at - datetime.fromisoformat(q['market_at'])).total_seconds()
    if age < -2 or age > limits['quote_max_age_seconds']:
        raise RiskError("Veraltete/zukünftige Marktdaten")
    bid, ask = D(q['bid']), D(q['ask'])
    if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask < bid:
        raise RiskError("Ungültiger oder gekreuzter Spread")
    if (ask-bid) / ((ask+bid)/2) * 10000 > D(str(limits['max_spread_bps'])):
        raise RiskError("Spread überschreitet Limit")
    return dict(q)


def snapshot(c, pid, at=None):
    at = at or datetime.now(timezone.utc)
    p = c.execute("SELECT * FROM portfolios WHERE id=?", (pid,)).fetchone()
    if not p:
        raise RiskError("Portfolio fehlt")
    complete, position_value, details = True, 0, []
    limits = meta(c, 'risk_limits')
    try:
        fx = latest_fx(c, at, limits['fx_max_age_days'])
    except RiskError:
        fx = None
    for pos in c.execute("SELECT * FROM positions WHERE portfolio_id=?", (pid,)):
        value = pos['cost_u']
        try:
            q = valid_quote(c, pos['symbol'], limits, at)
            if fx is None:
                raise RiskError("FX fehlt")
            value = units(D(pos['qty']) * D(q['bid']) / fx)
        except RiskError:
            complete = False
        position_value += value
        details.append(dict(pos) | dict(value_eur=eur(value), unrealized_eur=eur(value-pos['cost_u'])))
    equity = p['cash_u'] + position_value
    high = c.execute("SELECT MAX(equity_u) FROM equity WHERE portfolio_id=? AND valuation_complete=1", (pid,)).fetchone()[0]
    high = max(high or p['initial_u'], equity)
    return dict(id=pid, kind=p['kind'], owner_id=p['owner_id'], initial_eur=eur(p['initial_u']),
                equity_eur=eur(equity), cash_eur=eur(p['cash_u']), reserved_eur=eur(p['reserved_u']),
                available_eur=eur(p['cash_u']-p['reserved_u']), realized_eur=eur(p['realized_u']),
                unrealized_eur=eur(equity-p['cash_u']-sum(x['cost_u'] for x in details)),
                pnl_eur=eur(equity-p['initial_u']), return_pct=(equity/p['initial_u']-1)*100,
                drawdown_pct=(1-equity/high)*100 if high else 0,
                drawdown_eur=eur(high-equity),
                valuation_complete=complete, positions=details, fx=str(fx) if fx else None)


class Ledger:
    def __init__(self, db):
        self.db = db

    def portfolio(self, pid='fund'):
        with self.db.tx() as c:
            return snapshot(c, pid)

    def submit(self, agent_id, symbol, side, qty, client_id, order_type='market',
               limit_usd=None, stop_usd=None, take_usd=None, reason='', at=None):
        try:
            return self._submit(agent_id,symbol,side,qty,client_id,order_type,limit_usd,stop_usd,take_usd,reason,at)
        except RiskError as exc:
            self.db.event('no_trade',str(exc),agent_id,level='info',data={'symbol':symbol,'side':side,'client_id':client_id,'action':'HOLD / NO TRADE'})
            raise

    def _submit(self, agent_id, symbol, side, qty, client_id, order_type='market',
               limit_usd=None, stop_usd=None, take_usd=None, reason='', at=None):
        at = at or datetime.now(timezone.utc)
        symbol = symbol.upper()
        qty = D(str(qty))
        if not qty.is_finite() or qty <= 0 or qty > 100000 or qty.as_tuple().exponent < -6:
            raise RiskError("Ungültige Stückzahl; höchstens 6 Nachkommastellen")
        if side not in ('buy','sell') or order_type not in ('market','limit','stop'):
            raise RiskError("Nur Long-Aktienorders market/limit/stop")
        for value in (limit_usd, stop_usd, take_usd):
            if value is not None and (not D(str(value)).is_finite() or D(str(value)) <= 0):
                raise RiskError("Ungültiger Orderpreis")
        if order_type == 'limit' and limit_usd is None:
            raise RiskError("Limitpreis fehlt")
        if order_type == 'stop' and stop_usd is None:
            raise RiskError("Stoppreis fehlt")
        # A model's textual BUY/SELL is never an authorization. Check stored strategy first.
        existing=self.db.one('SELECT * FROM orders WHERE client_id=?',(client_id,))
        if existing:
            if (existing['agent_id'],existing['symbol'],existing['side'],D(existing['qty']))!=(agent_id,symbol,side,qty):
                raise RiskError('Idempotenzschlüssel für andere Order verwendet')
            return existing
        from .signals import SignalEngine,evaluate_tx
        preliminary=SignalEngine(self.db).evaluate(agent_id,symbol,side,at)
        if not preliminary.valid:
            raise RiskError(preliminary.reason)
        with self.db.tx() as c:
            prior = c.execute("SELECT * FROM orders WHERE client_id=?", (client_id,)).fetchone()
            if prior:
                if (prior['agent_id'],prior['symbol'],prior['side'],D(prior['qty'])) != (agent_id,symbol,side,qty):
                    raise RiskError("Idempotenzschlüssel für andere Order verwendet")
                return dict(prior)
            a = c.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
            if not a or a['department'] == 'research':
                raise RiskError("Research-Agenten senden keine Tagesorders")
            decision=evaluate_tx(self.db,c,agent_id,symbol,side,at,expected_strategy=preliminary.strategy_id)
            if not decision.valid:
                raise RiskError(decision.reason)
            pid = 'fund' if a['department'] == 'fund' else f'demo-{agent_id:03}'
            clock = phase(self.db, at)
            if not clock['trading'] and not (side == 'sell' and clock['liquidating']):
                raise RiskError(clock['reason'])
            limits = meta(c, 'risk_limits')
            q = valid_quote(c, symbol, limits, at)
            fx = latest_fx(c, at, limits['fx_max_age_days'])
            asset = c.execute("SELECT * FROM assets WHERE symbol=?", (symbol,)).fetchone()
            if not asset or not asset['tradable'] or asset['asset_class'] != 'us_equity':
                raise RiskError("Kein bestätigtes handelbares US-Asset")
            if (at-datetime.fromisoformat(asset['updated_at'])).total_seconds() > 86400*4:
                raise RiskError("Assetprüfung veraltet")
            p = c.execute("SELECT * FROM portfolios WHERE id=?", (pid,)).fetchone()
            pos = c.execute("SELECT * FROM positions WHERE portfolio_id=? AND agent_id=? AND symbol=?",
                            (pid,agent_id,symbol)).fetchone()
            if c.execute("SELECT 1 FROM orders WHERE agent_id=? AND symbol=? AND status IN ('pending','triggered')",
                         (agent_id,symbol)).fetchone():
                raise RiskError("Bereits offene Order für Agent/Aktie")
            reserve = 0
            if side == 'buy':
                if a['paused'] or meta(c,'kill_switch') or not meta(c,'trading_enabled') or not meta(c,'risk_confirmed') or meta(c,'risk_halt_'+pid):
                    raise RiskError("Neue Positionen gesperrt: Pause/Not-Aus/Risikofreigabe")
                stream = c.execute("SELECT status,checked_at FROM integrations WHERE name='market_stream'").fetchone()
                if not stream or stream['status'] != 'connected':
                    raise RiskError("Marktdatenverbindung nicht bestätigt")
                if not reason.strip():
                    raise RiskError("Entscheidungsbegründung fehlt")
                # Stop buys are not enabled: price gaps make a bounded cash reservation impossible.
                if order_type == 'stop':
                    raise RiskError("Stop-Einstiege gesperrt; Stop-Verkäufe unterstützt")
                ask = D(q['ask'])
                ceiling = D(str(limit_usd)) if order_type == 'limit' else ask*D('1.01')
                reserve = units(qty*ceiling/fx*(1+D(str(limits['fee_bps']))/10000))
                if not stop_usd or not D(str(stop_usd)) < ask:
                    raise RiskError("Gültiger Schutzstop unter aktuellem Ask erforderlich")
                if take_usd is not None and D(str(take_usd)) <= ask:
                    raise RiskError("Take Profit muss über Einstieg liegen")
                s = snapshot(c,pid,at)
                if not s['valuation_complete']:
                    raise RiskError("Unvollständige Portfolio-Bewertung")
                equity = units(s['equity_eur'])
                caps=meta(c,'fund_cash_limits',{}) if pid=='fund' else {}
                start_local = datetime.combine(at.astimezone(BERLIN).date(), datetime.min.time(), BERLIN).astimezone(timezone.utc).isoformat()
                opening = c.execute("SELECT equity_u FROM equity WHERE portfolio_id=? AND created_at>=? AND valuation_complete=1 ORDER BY created_at LIMIT 1", (pid,start_local)).fetchone()
                start_equity = opening[0] if opening else p['initial_u']
                if start_equity-equity >= capped_limit(caps,'max_daily_loss_eur',start_equity*limits['max_daily_loss_pct']):
                    raise RiskError("Tagesverlustlimit erreicht")
                if s['drawdown_pct']/100 >= limits['max_drawdown_pct'] or ('max_drawdown_eur' in caps and units(s['drawdown_eur'])>=units(caps['max_drawdown_eur'])):
                    raise RiskError("Drawdown-Limit erreicht")
                if reserve > p['cash_u']-p['reserved_u']:
                    raise RiskError("Nicht genügend freies Kapital")
                exposure = equity-p['cash_u']+p['reserved_u']
                if exposure+reserve > capped_limit(caps,'max_exposure_eur',equity*limits['max_exposure_pct']):
                    raise RiskError("Gesamtexposure überschritten")
                own = sum(x['cost_u'] for x in s['positions'] if x['agent_id']==agent_id)
                own += c.execute("SELECT COALESCE(SUM(reserved_u),0) FROM orders WHERE portfolio_id=? AND agent_id=? AND status IN ('pending','triggered')",(pid,agent_id)).fetchone()[0]
                symbol_cost = sum(x['cost_u'] for x in s['positions'] if x['symbol']==symbol)
                symbol_cost += c.execute("SELECT COALESCE(SUM(reserved_u),0) FROM orders WHERE portfolio_id=? AND symbol=? AND status IN ('pending','triggered')",(pid,symbol)).fetchone()[0]
                if own+reserve > equity*limits['max_agent_pct']:
                    raise RiskError("Kapitalbudget des Agenten überschritten")
                if reserve+(pos['cost_u'] if pos else 0) > capped_limit(caps,'max_position_eur',equity*limits['max_position_pct']):
                    raise RiskError("Positionsgröße überschritten")
                if symbol_cost+reserve > equity*limits['max_symbol_pct']:
                    raise RiskError("Aktienkonzentration überschritten")
                # Conservative correlated bucket until enough return observations exist.
                if symbol in TECH:
                    bucket = sum(x['cost_u'] for x in s['positions'] if x['symbol'] in TECH)
                    for other in c.execute("SELECT symbol,reserved_u FROM orders WHERE portfolio_id=? AND status IN ('pending','triggered')",(pid,)):
                        if other['symbol'] in TECH:
                            bucket += other['reserved_u']
                    if bucket+reserve > equity*limits['max_correlated_pct']:
                        raise RiskError("Konservatives Tech-Korrelationsbudget überschritten")
                risk = units(qty*(ceiling-D(str(stop_usd)))/fx) + units(qty*ceiling/fx*D('0.001'))
                if risk > capped_limit(caps,'max_loss_per_position_eur',equity*limits['max_loss_per_position_pct']):
                    raise RiskError("Geplantes Stop-Risiko überschritten; Gaps bleiben möglich")
                total_risk = own_risk = 0
                for item in s['positions']:
                    r = units(D(item['qty'])*max(D(0),D(item['avg_usd'])-D(item['stop_usd']))/fx)
                    total_risk += r
                    if item['agent_id'] == agent_id:
                        own_risk += r
                for item in c.execute("SELECT * FROM orders WHERE portfolio_id=? AND side='buy' AND status IN ('pending','triggered')",(pid,)):
                    # Full cash reservation is a conservative bound on pending stop risk.
                    total_risk += item['reserved_u']
                    if item['agent_id'] == agent_id:
                        own_risk += item['reserved_u']
                if own_risk+risk > equity*limits['max_agent_risk_pct'] or total_risk+risk > equity*limits['max_total_risk_pct']:
                    raise RiskError("Gesamtes/individuelles Stop-Risikobudget überschritten")
            elif not pos or qty > D(pos['qty']):
                raise RiskError("Keine gedeckte Long-Position; Short Selling deaktiviert")
            available = q['ask_size'] if side == 'buy' else q['bid_size']
            if qty > D(available)*100*D('0.05'):
                raise RiskError("Order über 5% der sichtbaren Feed-Liquidität")
            oid, stamp = uid(), now()
            c.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (oid,client_id,pid,agent_id,symbol,side,str(qty),order_type,
                       str(limit_usd) if limit_usd else None,str(stop_usd) if stop_usd else None,
                       str(take_usd) if take_usd else None,'pending',reserve,reason,'internal',stamp,stamp))
            c.execute("UPDATE portfolios SET reserved_u=reserved_u+? WHERE id=?", (reserve,pid))
            c.execute('INSERT INTO order_signals VALUES(?,?)',(oid,decision.id))
            event(c,'order_reserved',f"{side.upper()} {qty} {symbol}: Interne Simulation vorgemerkt",agent_id,data={'order_id':oid,'reserved_eur':eur(reserve)})
            return dict(c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone())

    def cancel(self, oid, why='CEO-Stornierung'):
        with self.db.tx() as c:
            o = c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
            if not o:
                raise RiskError("Order fehlt")
            if o['status'] not in ACTIVE:
                return dict(o)
            c.execute("UPDATE portfolios SET reserved_u=reserved_u-? WHERE id=?",(o['reserved_u'],o['portfolio_id']))
            c.execute("UPDATE orders SET status='cancelled',reserved_u=0,updated_at=? WHERE id=?",(now(),oid))
            event(c,'order_cancelled',why,o['agent_id'],data={'order_id':oid})
            return {'id':oid,'status':'cancelled'}

    def fill(self,oid,at=None):
        try:
            return self._fill(oid,at)
        except RiskError as exc:
            if self.db.get('fill_block_'+oid)!=str(exc):
                self.db.set('fill_block_'+oid,str(exc))
                order=self.db.one('SELECT agent_id FROM orders WHERE id=?',(oid,))
                self.db.event('no_trade','Keine Ausführung: '+str(exc),order['agent_id'] if order else None,
                              data={'order_id':oid,'action':'HOLD / NO TRADE'})
            raise

    def _fill(self, oid, at=None):
        at = at or datetime.now(timezone.utc)
        with self.db.tx() as c:
            o = c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
            if not o or o['status'] not in ACTIVE:
                return None
            if c.execute("SELECT 1 FROM fills WHERE order_id=?",(oid,)).fetchone():
                return None
            proof=c.execute('SELECT s.* FROM order_signals os JOIN signal_decisions s ON s.id=os.signal_id WHERE os.order_id=?',(oid,)).fetchone()
            from .signals import evaluate_tx
            decision=evaluate_tx(self.db,c,o['agent_id'],o['symbol'],o['side'],at,
                                 expected_strategy=proof['strategy_id'] if proof else '__missing_proof__')
            if not proof or not decision.valid:
                c.execute('UPDATE portfolios SET reserved_u=reserved_u-? WHERE id=?',(o['reserved_u'],o['portfolio_id']))
                c.execute("UPDATE orders SET status='cancelled',reserved_u=0,updated_at=? WHERE id=?",(now(),oid))
                event(c,'signal_rejected','Keine Ausführung: '+decision.reason,o['agent_id'],level='warning',data={'order_id':oid,'decision_id':decision.id})
                return None
            clock = phase(self.db, at)
            if not clock['trading'] and not (o['side']=='sell' and clock['liquidating']):
                return None
            if o['side']=='buy':
                a = c.execute("SELECT paused FROM agents WHERE id=?",(o['agent_id'],)).fetchone()
                stream=c.execute("SELECT status FROM integrations WHERE name='market_stream'").fetchone()
                if a['paused'] or meta(c,'kill_switch') or not meta(c,'trading_enabled') or meta(c,'risk_halt_'+o['portfolio_id']) or not stream or stream['status']!='connected':
                    return None
            limits = meta(c,'risk_limits')
            q = valid_quote(c,o['symbol'],limits,at)
            fx = latest_fx(c,at,limits['fx_max_age_days'])
            qty = D(o['qty'])
            raw = D(q['ask'] if o['side']=='buy' else q['bid'])
            if o['order_type']=='stop' and raw > D(o['stop_usd']) and o['status']!='triggered':
                return None
            price = raw*(1+D(str(limits['slippage_bps']))/10000*(1 if o['side']=='buy' else -1))
            if o['order_type']=='limit':
                limit = D(o['limit_usd'])
                if (o['side']=='buy' and price>limit) or (o['side']=='sell' and price<limit):
                    return None
            if qty > D(q['ask_size'] if o['side']=='buy' else q['bid_size'])*100*D('0.05'):
                return None
            gross = units(qty*price/fx)
            fee = units(qty*price/fx*D(str(limits['fee_bps']))/10000)
            p = c.execute("SELECT * FROM portfolios WHERE id=?",(o['portfolio_id'],)).fetchone()
            pos = c.execute("SELECT * FROM positions WHERE portfolio_id=? AND agent_id=? AND symbol=?",
                            (o['portfolio_id'],o['agent_id'],o['symbol'])).fetchone()
            realized = stock_pnl = fx_pnl = 0
            if o['side']=='buy':
                if gross+fee > o['reserved_u'] or gross+fee > p['cash_u']:
                    # Price gapped through reservation: never mint money or spend other orders' cash.
                    return None
                delta = -gross-fee
                newqty = qty+(D(pos['qty']) if pos else 0)
                cost = gross+fee+(pos['cost_u'] if pos else 0)
                avg = (qty*price+(D(pos['qty'])*D(pos['avg_usd']) if pos else 0))/newqty
                # Weighted entry FX is derived from gross USD / EUR gross basis (fees excluded).
                old_gross = D(pos['qty'])*D(pos['avg_usd'])/D(pos['entry_fx']) if pos else D(0)
                entryfx = newqty*avg/(old_gross+qty*price/fx)
                c.execute("INSERT OR REPLACE INTO positions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (pos['id'] if pos else uid(),o['portfolio_id'],o['agent_id'],o['symbol'],str(newqty),str(avg),cost,str(entryfx),o['stop_usd'],o['take_usd'],pos['created_at'] if pos else now()))
            else:
                if not pos or qty>D(pos['qty']):
                    raise RiskError("Positionsbestand nach Reservierung verändert")
                part = qty/D(pos['qty'])
                basis = int((D(pos['cost_u'])*part).quantize(D(1)))
                delta = gross-fee
                realized = delta-basis
                stock_pnl = units(qty*(price-D(pos['avg_usd']))/D(pos['entry_fx']))
                # FX component includes the converted sale proceeds; costs shown separately.
                fx_pnl = units(qty*price*(1/fx-1/D(pos['entry_fx'])))
                if qty==D(pos['qty']):
                    c.execute("DELETE FROM positions WHERE id=?",(pos['id'],))
                else:
                    c.execute("UPDATE positions SET qty=?,cost_u=? WHERE id=?",(str(D(pos['qty'])-qty),pos['cost_u']-basis,pos['id']))
            fid, stamp = uid(), now()
            c.execute("INSERT INTO fills VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (fid,oid,o['agent_id'],o['portfolio_id'],o['symbol'],o['side'],str(qty),str(price),str(fx),fee,delta,realized,stock_pnl,fx_pnl,'Interne Simulation',stamp))
            c.execute("UPDATE portfolios SET cash_u=cash_u+?,reserved_u=reserved_u-?,realized_u=realized_u+? WHERE id=?",
                      (delta,o['reserved_u'],realized,o['portfolio_id']))
            c.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?)",(uid(),o['portfolio_id'],fid,'execution',delta,p['cash_u']+delta,stamp))
            c.execute("UPDATE orders SET status='filled',reserved_u=0,updated_at=? WHERE id=?",(stamp,oid))
            event(c,'execution',f"Interne Simulation ausgeführt: {o['side']} {qty} {o['symbol']} @ {price:.4f} USD",o['agent_id'],data={'order_id':oid,'fill_id':fid})
            return dict(c.execute("SELECT * FROM fills WHERE id=?",(fid,)).fetchone())

    def record_equity(self):
        with self.db.tx() as c:
            for p in c.execute("SELECT id FROM portfolios WHERE kind!='research'").fetchall():
                s = snapshot(c,p['id'])
                c.execute("INSERT INTO equity VALUES(?,?,?,?,?,?,?)",(uid(),p['id'],units(s['equity_eur']),units(s['cash_eur']),units(s['unrealized_eur']),int(s['valuation_complete']),now()))
            for a in c.execute("SELECT id,department FROM agents WHERE department!='research'").fetchall():
                dept=a['department']
                pid='fund' if dept=='fund' else f"demo-{a['id']:03}"
                base=units(120 if dept=='fund' else 3000)
                # Fund contribution belongs to the agent; reference capital is analytical, never cash.
                realized=c.execute('SELECT COALESCE(SUM(realized_u),0) FROM fills WHERE agent_id=? AND portfolio_id=?',(a['id'],pid)).fetchone()[0]
                pstate=snapshot(c,pid)
                positions=[x for x in pstate['positions'] if x['agent_id']==a['id']]
                unrealized=sum(units(x['unrealized_eur']) for x in positions)
                pnl=realized+unrealized
                c.execute('INSERT INTO agent_equity VALUES(?,?,?,?,?,?,?,?)',(uid(),a['id'],dept,base,pnl,base+pnl,int(pstate['valuation_complete']),now()))
            try:
                q=valid_quote(c,'SPY',meta(c,'risk_limits'))
                fx=latest_fx(c)
                c.execute('INSERT INTO benchmark VALUES(?,?,?,?,?,?)',(uid(),'SPY',q['bid'],str(fx),q['market_at'],now()))
            except RiskError:
                pass

    def reconcile(self):
        with self.db.tx() as c:
            for p in c.execute("SELECT * FROM portfolios").fetchall():
                cash = c.execute("SELECT COALESCE(SUM(delta_u),0) FROM ledger WHERE portfolio_id=?",(p['id'],)).fetchone()[0]
                reserve = c.execute("SELECT COALESCE(SUM(reserved_u),0) FROM orders WHERE portfolio_id=? AND status IN ('pending','triggered')",(p['id'],)).fetchone()[0]
                if cash!=p['cash_u'] or reserve!=p['reserved_u']:
                    put(c,'kill_switch',True)
                    event(c,'reconciliation','Ledger-Abweichung: Handel gesperrt',level='critical',data={'portfolio':p['id']})
                    return False
            return True
