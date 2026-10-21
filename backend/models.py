"""Resolve the current approach first, then department, on every request."""
def agent_model(db,cfg,agent_id):
    agent=db.one('SELECT department FROM agents WHERE id=?',(agent_id,))
    if not agent:raise ValueError('Modellwahl: Agent fehlt')
    mandate=db.one('SELECT approach FROM agent_mandates WHERE agent_id=?',(agent_id,))
    if mandate and mandate['approach']=='technical':return cfg.openai_technical_model
    return cfg.openai_research_model if agent['department']=='research' else cfg.openai_model


def request_model(db,cfg,kind,agent_id=None):
    if kind in ('manager','manager_review','manager_daily'):return cfg.openai_manager_model
    return agent_model(db,cfg,agent_id) if agent_id is not None else cfg.openai_model
