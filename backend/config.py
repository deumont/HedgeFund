from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
PAPER_URL = "https://paper-api.alpaca.markets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openai_api_key: str = ""
    alpaca_paper_api_key: str = ""
    alpaca_paper_secret_key: str = ""
    openai_model: str = "gpt-6.1-sol"
    openai_manager_model: str = "gpt-5.4-mini"
    openai_input_usd_per_million: Decimal = Decimal("2")
    openai_output_usd_per_million: Decimal = Decimal("10")
    monthly_budget_eur: Decimal = Decimal("30")
    alpaca_feed: str = "iex"
    watchlist: str = "SPY,QQQ,AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA,AMD"
    sec_user_agent: str = ""
    host: str = "127.0.0.1"
    port: int = 8765
    session_secret: str = ""
    ceo_password_hash: str = ""
    database_path: str = str(ROOT / "data" / "fund.sqlite3")
    supabase_url: str = ""
    supabase_secret_key: str = ""
    cloud_sync_enabled: bool = False
    cloud_sync_seconds: int = 60

    @property
    def symbols(self):
        return [x.strip().upper() for x in self.watchlist.split(",") if x.strip()][:30]

    @property
    def has_alpaca(self):
        return bool(self.alpaca_paper_api_key and self.alpaca_paper_secret_key)


def now():
    return datetime.now(timezone.utc).isoformat()


def units(eur):
    value = Decimal(str(eur))
    if not value.is_finite():
        raise ValueError("Betrag ist nicht endlich")
    return int((value * 1_000_000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def eur(value):
    return value / 1_000_000
