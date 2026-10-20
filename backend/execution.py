"""Execute stored strategy signals without depending on paid model availability."""
import json
from decimal import Decimal, ROUND_DOWN
from .config import units, eur
from .ledger import RiskError, meta, snapshot, valid_quote, latest_fx, TECH, capped_limit,effective_limits,cash_caps

D = Decimal


def plan_order(db, agent_id, symbol, side, at=None):
    """Conservative sizing only. Ledger.submit/fill remain the authoritative gates."""
    with db.tx() as c:
        agent = c.execute('SELECT * FROM agents WHERE id=?', (agent_id,)).fetchone()
        if not agent or agent['department'] == 'research':
            raise RiskError('Kein freigegebener Trader')
        pid = 'fund' if agent['department'] == 'fund' else f'demo-{agent_id:03}'
        position = c.execute('SELECT * FROM positions WHERE portfolio_id=? AND agent_id=? AND symbol=?',
                             (pid, agent_id, symbol)).fetchone()
        if side == 'sell':
            if not position:
                raise RiskError('Keine gedeckte Position')
            return dict(qty=position['qty'])
        limits = effective_limits(c)
        quote = valid_quote(c, symbol, limits, at)
        fx = latest_fx(c, at, limits['fx_max_age_days'])
        state = snapshot(c, pid, at)
        if not state['valuation_complete']:
            raise RiskError('Unvollständige Portfolio-Bewertung')
        strategy = c.execute('SELECT spec FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1', (agent_id,)).fetchone()
        spec = json.loads(strategy['spec'])
        ask = D(quote['ask'])
        stop = ask * (1 - D(str(spec['stop_pct'])))
        ceiling = ask * D('1.01')
        cost_per_share = ceiling / fx * (1 + D(str(limits['fee_bps'])) / 10000)
        risk_per_share = (ceiling - stop + ceiling * D('.001')) / fx
        equity = units(state['equity_eur'])
        caps = cash_caps(c,pid)
        positions = state['positions']
        pending = c.execute("SELECT * FROM orders WHERE portfolio_id=? AND status IN ('pending','triggered')", (pid,)).fetchall()
        own = sum(p['cost_u'] for p in positions if p['agent_id'] == agent_id)
        own += sum(p['reserved_u'] for p in pending if p['agent_id'] == agent_id)
        symbol_cost = sum(p['cost_u'] for p in positions if p['symbol'] == symbol)
        symbol_cost += sum(p['reserved_u'] for p in pending if p['symbol'] == symbol)
        exposure = sum(units(p['value_eur']) for p in positions) + sum(p['reserved_u'] for p in pending)
        cash_budgets = [units(state['available_eur']), equity * limits['max_agent_pct'] - own,
            capped_limit(caps, 'max_position_eur', equity * limits['max_position_pct']),
            capped_limit(caps, 'max_exposure_eur', equity * limits['max_exposure_pct']) - exposure,
            equity * limits['max_symbol_pct'] - symbol_cost]
        if meta(c,'paper_sizing_mode')=='strategy':
            # Same allocation parameter as the historical simulation; no trade quota.
            from .backtest import validate_spec
            validate_spec(spec)
            cash_budgets.append(equity*spec.get('position_pct',1.0)-own)
        if symbol in TECH:
            bucket = sum(p['cost_u'] for p in positions if p['symbol'] in TECH)
            bucket += sum(p['reserved_u'] for p in pending if p['symbol'] in TECH)
            cash_budgets.append(equity * limits['max_correlated_pct'] - bucket)
        total_risk = own_risk = 0
        for item in positions:
            risk = units(D(item['qty']) * max(D(0), D(item['avg_usd']) - D(item['stop_usd'])) / fx)
            total_risk += risk
            if item['agent_id'] == agent_id:
                own_risk += risk
        for item in pending:
            if item['side'] == 'buy':
                total_risk += item['reserved_u']
                if item['agent_id'] == agent_id:
                    own_risk += item['reserved_u']
        risk_budget = min(capped_limit(caps, 'max_loss_per_position_eur', equity * limits['max_loss_per_position_pct']),
                          equity * limits['max_agent_risk_pct'] - own_risk,
                          equity * limits['max_total_risk_pct'] - total_risk)
        # Rounding buffer protects fixed-point ledger boundaries; visible liquidity is a hard cap.
        qty = min(D(str(eur(min(cash_budgets)))) / cost_per_share,
                  D(str(eur(risk_budget))) / risk_per_share,
                  D(quote['ask_size']) * 100 * D('.05')) * D('.995')
        qty = qty.quantize(D('.000001'), rounding=ROUND_DOWN)
        if not qty.is_finite() or qty <= 0:
            raise RiskError('Kein freies Kapital-/Risikobudget oder keine sichtbare Liquidität')
        return dict(qty=str(qty), stop_usd=str(stop), take_usd=str(ask + (ask - stop) * 2))
