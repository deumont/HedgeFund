"""All eligible Alpaca US stocks; bounded data subscriptions, not a fixed tradable watchlist."""
import re
from .config import now


def eligible(db,symbol):
    return bool(isinstance(symbol,str) and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}',symbol) and
                db.one("SELECT 1 FROM assets WHERE symbol=? AND tradable=1 AND asset_class='us_equity'",(symbol,)))


def active_symbols(db,cfg):
    return list(dict.fromkeys([p['symbol'] for p in db.all('SELECT DISTINCT symbol FROM positions')]+
                             db.get('market_symbols',cfg.symbols)))


def rotate(db,cfg):
    catalog=[r['symbol'] for r in db.all("SELECT symbol FROM assets WHERE tradable=1 AND asset_class='us_equity' ORDER BY symbol")]
    required=[p['symbol'] for p in db.all('SELECT DISTINCT symbol FROM positions')]
    requested=db.get('requested_stocks',[])[-15:]
    base=list(dict.fromkeys(required+requested+cfg.symbols))
    cursor=db.get('stock_scan_cursor',0)
    scanned=[catalog[(cursor+i)%len(catalog)] for i in range(min(15,len(catalog)))] if catalog else []
    selected=list(dict.fromkeys(base+scanned))[:max(30,len(required))]
    db.set('stock_scan_cursor',(cursor+max(1,len(scanned)))%max(1,len(catalog)))
    db.set('market_symbols',selected)
    return selected


def select_stock(db,cfg,agent_id,symbol):
    if not eligible(db,symbol):
        raise ValueError('Aktie ist nicht im bestätigten handelbaren Alpaca-US-Katalog')
    requested=db.get('requested_stocks',[])
    db.set('requested_stocks',[s for s in requested if s!=symbol][-199:]+[symbol])
    db.set('agent-stock-'+str(agent_id),symbol)
    rotate(db,cfg)
    from .worker import enqueue
    return enqueue(db,'prepare_stock',{'symbol':symbol},priority=4,dedupe='prepare-'+symbol+'-'+now()[:16])
