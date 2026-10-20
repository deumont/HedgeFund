import contextlib
import json
import sqlite3
import uuid
from pathlib import Path
from .config import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agents(
 id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 100), name TEXT NOT NULL,
 specialty TEXT NOT NULL, mandate TEXT NOT NULL, department TEXT NOT NULL
 CHECK(department IN ('research','demo','fund')), paused INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, last_active TEXT);
CREATE TABLE IF NOT EXISTS strategies(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL REFERENCES agents(id),version INTEGER NOT NULL,
 spec TEXT NOT NULL,rationale TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'candidate',
 created_at TEXT NOT NULL, UNIQUE(agent_id,version));
CREATE TABLE IF NOT EXISTS memories(
 id TEXT PRIMARY KEY,agent_id INTEGER REFERENCES agents(id),kind TEXT NOT NULL,
 content TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS portfolios(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,owner_id INTEGER REFERENCES agents(id),
 initial_u INTEGER NOT NULL,cash_u INTEGER NOT NULL CHECK(cash_u>=0),
 reserved_u INTEGER NOT NULL DEFAULT 0 CHECK(reserved_u>=0 AND reserved_u<=cash_u),
 realized_u INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotes(
 symbol TEXT PRIMARY KEY,bid TEXT NOT NULL,ask TEXT NOT NULL,bid_size INTEGER NOT NULL,
 ask_size INTEGER NOT NULL,market_at TEXT NOT NULL,received_at TEXT NOT NULL,source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bars(
 symbol TEXT NOT NULL,time TEXT NOT NULL,timeframe TEXT NOT NULL,open TEXT NOT NULL,
 high TEXT NOT NULL,low TEXT NOT NULL,close TEXT NOT NULL,volume INTEGER NOT NULL,
 source TEXT NOT NULL,adjustment TEXT NOT NULL,PRIMARY KEY(symbol,time,timeframe,source,adjustment));
CREATE TABLE IF NOT EXISTS fx(
 date TEXT PRIMARY KEY,usd_per_eur TEXT NOT NULL,source TEXT NOT NULL,received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
 date TEXT PRIMARY KEY,opens_at TEXT NOT NULL,closes_at TEXT NOT NULL,source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets(
 symbol TEXT PRIMARY KEY,tradable INTEGER NOT NULL,asset_class TEXT NOT NULL,
 exchange TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positions(
 id TEXT PRIMARY KEY,portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
 agent_id INTEGER NOT NULL REFERENCES agents(id),symbol TEXT NOT NULL,qty TEXT NOT NULL,
 avg_usd TEXT NOT NULL,cost_u INTEGER NOT NULL,entry_fx TEXT NOT NULL,
 stop_usd TEXT NOT NULL,take_usd TEXT,created_at TEXT NOT NULL,
 UNIQUE(portfolio_id,agent_id,symbol));
CREATE TABLE IF NOT EXISTS orders(
 id TEXT PRIMARY KEY,client_id TEXT NOT NULL UNIQUE,portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
 agent_id INTEGER NOT NULL REFERENCES agents(id),symbol TEXT NOT NULL,side TEXT NOT NULL,
 qty TEXT NOT NULL,order_type TEXT NOT NULL,limit_usd TEXT,stop_usd TEXT,take_usd TEXT,
 status TEXT NOT NULL,reserved_u INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL,
 source TEXT NOT NULL DEFAULT 'internal',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fills(
 id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),agent_id INTEGER NOT NULL,
 portfolio_id TEXT NOT NULL,symbol TEXT NOT NULL,side TEXT NOT NULL,qty TEXT NOT NULL,
 price_usd TEXT NOT NULL,fx TEXT NOT NULL,fee_u INTEGER NOT NULL,cash_delta_u INTEGER NOT NULL,
 realized_u INTEGER NOT NULL,stock_pnl_u INTEGER NOT NULL,fx_pnl_u INTEGER NOT NULL,
 source TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger(
 id TEXT PRIMARY KEY,portfolio_id TEXT NOT NULL,event_id TEXT UNIQUE NOT NULL,
 kind TEXT NOT NULL,delta_u INTEGER NOT NULL,cash_after_u INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equity(
 id TEXT PRIMARY KEY,portfolio_id TEXT NOT NULL,equity_u INTEGER NOT NULL,cash_u INTEGER NOT NULL,
 unrealized_u INTEGER NOT NULL,valuation_complete INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS news(
 id TEXT PRIMARY KEY,source TEXT NOT NULL,headline TEXT NOT NULL,summary TEXT NOT NULL,
 url TEXT NOT NULL,symbols TEXT NOT NULL,published_at TEXT NOT NULL,received_at TEXT NOT NULL,
 confidence TEXT NOT NULL,relevance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,symbol TEXT,source TEXT NOT NULL,payload TEXT NOT NULL,
 published_at TEXT NOT NULL,received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analyses(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,strategy_id TEXT,
 context TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS backtests(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,strategy_id TEXT NOT NULL,symbol TEXT NOT NULL,
 data_hash TEXT NOT NULL,parameters TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evaluations(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,score REAL,metrics TEXT NOT NULL,
 explanation TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,
 status TEXT NOT NULL,effective_date TEXT,created_at TEXT NOT NULL,applied_at TEXT);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY AUTOINCREMENT,agent_id INTEGER,kind TEXT NOT NULL,
 level TEXT NOT NULL,message TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chats(
 id TEXT PRIMARY KEY,role TEXT NOT NULL,content TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY,dedupe TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,agent_id INTEGER,
 payload TEXT NOT NULL,priority INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,available_at TEXT NOT NULL,created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,error TEXT);
CREATE TABLE IF NOT EXISTS usage(
 id TEXT PRIMARY KEY,agent_id INTEGER,kind TEXT NOT NULL,model TEXT NOT NULL,
 input_tokens INTEGER NOT NULL DEFAULT 0,output_tokens INTEGER NOT NULL DEFAULT 0,
 reserved_u INTEGER NOT NULL,cost_u INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS integrations(
 name TEXT PRIMARY KEY,status TEXT NOT NULL,detail TEXT NOT NULL,checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS broker_orders(
 id TEXT PRIMARY KEY,client_id TEXT UNIQUE NOT NULL,symbol TEXT NOT NULL,side TEXT NOT NULL,
 qty TEXT NOT NULL,order_type TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,
 broker_id TEXT,result TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_sessions(
 token_hash TEXT PRIMARY KEY,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_equity(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,department TEXT NOT NULL,reference_u INTEGER NOT NULL,
 pnl_u INTEGER NOT NULL,equity_u INTEGER NOT NULL,valuation_complete INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS benchmark(
 id TEXT PRIMARY KEY,symbol TEXT NOT NULL,price_usd TEXT NOT NULL,fx TEXT NOT NULL,
 market_at TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signal_decisions(
 id TEXT PRIMARY KEY,dedupe TEXT NOT NULL UNIQUE,agent_id INTEGER NOT NULL,
 strategy_id TEXT, symbol TEXT NOT NULL,requested_side TEXT NOT NULL,decision TEXT NOT NULL,
 reason TEXT NOT NULL,timeframe_minutes INTEGER NOT NULL,observations TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_signals(
 order_id TEXT PRIMARY KEY REFERENCES orders(id),signal_id TEXT NOT NULL REFERENCES signal_decisions(id));
CREATE TABLE IF NOT EXISTS agent_reports(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,report_date TEXT NOT NULL,
 evidence_hash TEXT NOT NULL,content TEXT NOT NULL,evidence TEXT NOT NULL,
 model TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(agent_id,report_date,evidence_hash));
CREATE TABLE IF NOT EXISTS manager_reviews(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,score REAL NOT NULL CHECK(score BETWEEN 0 AND 10),
 summary TEXT NOT NULL,evidence TEXT NOT NULL,model TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_manager_reviews_agent ON manager_reviews(agent_id,created_at);
CREATE INDEX IF NOT EXISTS ix_agent_reports_day ON agent_reports(agent_id,report_date,created_at);
CREATE TABLE IF NOT EXISTS daily_cycles(
 date TEXT PRIMARY KEY,roster TEXT NOT NULL,reports TEXT NOT NULL,status TEXT NOT NULL,
 summary TEXT NOT NULL,decision_ids TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_drafts(
 agent_id INTEGER PRIMARY KEY REFERENCES agents(id),strategy_id TEXT NOT NULL,
 context TEXT NOT NULL,result TEXT NOT NULL,received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_mandates(
 agent_id INTEGER PRIMARY KEY REFERENCES agents(id),approach TEXT NOT NULL,
 focus TEXT NOT NULL,mandate TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS event_theses(
 id TEXT PRIMARY KEY,agent_id INTEGER NOT NULL,symbol TEXT NOT NULL,event_type TEXT NOT NULL,
 direction TEXT NOT NULL,confidence REAL NOT NULL,evidence_ids TEXT NOT NULL,
 summary TEXT NOT NULL,company_context TEXT NOT NULL,available_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_event_theses ON event_theses(agent_id,symbol,created_at);
CREATE INDEX IF NOT EXISTS ix_events_agent ON events(agent_id,id);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status,priority,available_at);
CREATE INDEX IF NOT EXISTS ix_fills_portfolio ON fills(portfolio_id,created_at);
CREATE INDEX IF NOT EXISTS ix_equity_portfolio ON equity(portfolio_id,created_at);
CREATE INDEX IF NOT EXISTS ix_agent_equity ON agent_equity(agent_id,department,created_at);
CREATE INDEX IF NOT EXISTS ix_signals_agent ON signal_decisions(agent_id,created_at);
"""


def uid():
    return str(uuid.uuid4())


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


class DB:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=30000")
        c.execute("PRAGMA synchronous=FULL")
        return c

    def init(self):
        with contextlib.closing(self.connect()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.execute("INSERT OR IGNORE INTO meta VALUES('schema_version','1')")

    @contextlib.contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def all(self, sql, args=()):
        with contextlib.closing(self.connect()) as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def get(self, key, default=None):
        row = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set(self, key, value):
        with self.tx() as c:
            put(c, key, value)

    def event(self, kind, message, agent_id=None, level="info", data=None):
        with self.tx() as c:
            event(c, kind, message, agent_id, level, data)

    def integration(self, name, status, detail):
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO integrations VALUES(?,?,?,?)",
                      (name, status, detail, now()))

    def backup(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ("fund-" + now().replace(":", "-") + ".sqlite3")
        with contextlib.closing(self.connect()) as src, contextlib.closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup-Integritätsprüfung fehlgeschlagen")
        # Keep latest 30 snapshots; delete only files within this explicit backup folder.
        for old in sorted(folder.glob("fund-*.sqlite3"), reverse=True)[30:]:
            old.unlink()
        return str(target)


def put(c, key, value):
    c.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, dumps(value)))


def event(c, kind, message, agent_id=None, level="info", data=None):
    c.execute("INSERT INTO events(agent_id,kind,level,message,data,created_at) VALUES(?,?,?,?,?,?)",
              (agent_id, kind, level, message, dumps(data or {}), now()))
