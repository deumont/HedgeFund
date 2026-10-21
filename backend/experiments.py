"""Auditable chance entries for a small paper-only experimental cohort."""
import hashlib,json
from datetime import datetime,timezone
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from .config import now
from .db import dumps,uid


class ExperimentSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['random_entry']
    lookback: Literal[2]
    threshold: Literal[0.0]
    holding_bars: int=Field(ge=1,le=126)
    stop_pct: float=Field(ge=.001,le=.25)
    position_pct: float=Field(gt=0,le=.25)
    timeframe_minutes: int=Field(ge=15,le=1440)
    max_data_delay_minutes: int=Field(ge=15,le=1440)
    requires_realtime: Literal[False]
    requires_full_market: Literal[False]
    entry_probability: float=Field(ge=.01,le=.5)
    seed: str=Field(min_length=8,max_length=64)


def configure(db):
    with db.tx() as c:
        for aid in range(51,56):
            c.execute("UPDATE agent_mandates SET approach='experimental',focus=?,mandate=? WHERE agent_id=? AND approach='technical'",
                ('Zufallsexperiment',
                 'Eigenständiger Paper-Experimentagent: Zufallseinstiege sind erlaubt und müssen als Zufall bezeichnet werden. '
                 'Keine erfundene technische oder fundamentale Begründung. Bewerte echte Ergebnisse nach Kosten, Verlusten und Stichprobengröße. '
                 'Der Zufalls-Seed bleibt fest; nicht nach gewinnbringenden Seeds suchen. Verändere Wahrscheinlichkeiten, Haltedauer und Positionsgröße nur im Forschungsfenster. '
                 'Kapitalgrenze, Datenqualität und Paper-only bleiben zwingend.',aid))


def initial_strategy(aid):
    return dict(kind='random_entry',lookback=2,threshold=0.0,holding_bars=4,stop_pct=.03,position_pct=.10,
        timeframe_minutes=15,max_data_delay_minutes=15,requires_realtime=False,requires_full_market=False,
        entry_probability=.10,seed=f'atlas-chance-agent-{aid}-v1')


def prepare_strategy(db,aid):
    from .research import require_research
    current=db.one('SELECT * FROM strategies WHERE agent_id=? ORDER BY version DESC LIMIT 1',(aid,))
    if json.loads(current['spec'])['kind']=='random_entry':return
    with db.tx() as c:
        require_research()
        c.execute('INSERT INTO strategies VALUES(?,?,?,?,?,?,?)',(uid(),aid,current['version']+1,dumps(initial_strategy(aid)),
            'Paper-Zufallsexperiment; Einstieg ohne behaupteten Informationsvorteil, fester Seed, reale Kosten und unabhängige Risikoprüfung.','candidate',now()))


def draw(spec,symbol,bar_time):
    """One repeatable uniform pseudo-random draw per stock/closed candle; no rerolls."""
    stamp=datetime.fromisoformat(bar_time)
    if stamp.tzinfo is None:raise ValueError('Zufallsexperiment braucht einen Bar mit Zeitzone')
    key=dumps([spec['seed'],symbol,stamp.astimezone(timezone.utc).isoformat()])
    value=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big')/2**64
    return {'draw':value,'probability':spec['entry_probability'],'bar_time':bar_time,
            'symbol':symbol,'seed':spec['seed'],'selected':value<spec['entry_probability'],
            'method':'Reproduzierbares Paper-Zufallsexperiment; kein behaupteter Prognosevorteil'}
