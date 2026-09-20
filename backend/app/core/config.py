from decimal import Decimal
from typing import List, Optional
from app.core.constants import BotMode

try:
    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=[".env", "../.env"],
            env_file_encoding="utf-8",
            extra="ignore"
        )

        BOT_MODE: BotMode = BotMode.PAPER
        EXCHANGE_ID: str = "binance"
        USE_TESTNET: bool = True

        EXCHANGE_API_KEY: str = ""
        EXCHANGE_API_SECRET: str = ""
        EXCHANGE_PASSWORD: str = ""

        # IQ Option Credentials & Staking
        IQOPTION_EMAIL: str = ""
        IQOPTION_PASSWORD: str = ""
        IQOPTION_BALANCE_MODE: str = "PRACTICE"  # "PRACTICE" (Demo) | "REAL"
        IQOPTION_MARTINGALE_STEPS: List[float] = [50.0, 100.0, 200.0]

        TRADING_SYMBOLS: List[str] = [
            "EURUSD-OTC", "GBPUSD-OTC", "EURGBP-OTC",
            "EURJPY-OTC", "USDCHF-OTC", "GBPJPY-OTC", "NZDUSD-OTC", "AUDCAD-OTC"
        ]
        DEFAULT_TIMEFRAME: str = "1m"

        @field_validator("IQOPTION_MARTINGALE_STEPS", mode="before")
        @classmethod
        def parse_martingale_steps(cls, v):
            if isinstance(v, str):
                import json
                try:
                    return [float(x) for x in json.loads(v)]
                except Exception:
                    return [float(s.strip()) for s in v.replace("[", "").replace("]", "").split(",") if s.strip()]
            return v

        @field_validator("TRADING_SYMBOLS", mode="before")
        @classmethod
        def parse_trading_symbols(cls, v):
            if isinstance(v, str):
                return [s.strip() for s in v.split(",") if s.strip()]
            return v

        MAX_DAILY_DRAWDOWN_PCT: Decimal = Decimal("3.0")
        MAX_ACCOUNT_EXPOSURE_PCT: Decimal = Decimal("20.0")
        MAX_RISK_PER_TRADE_PCT: Decimal = Decimal("1.0")
        CIRCUIT_BREAKER_MAX_ERRORS: int = 3

        TELEGRAM_BOT_TOKEN: str = ""
        TELEGRAM_ADMIN_CHAT_ID: str = ""
        TELEGRAM_CHANNEL_ID: str = ""
        TELEGRAM_SIGNAL_TTL_SECONDS: int = 45
        TELEGRAM_HEARTBEAT_MINUTES: int = 60

        APP_ENV: str = "development"
        PORT: int = 8000
        DATABASE_URL: str = "sqlite+aiosqlite:///./trading_bot.db"
        AUTO_START_TRADING: bool = True

    settings = Settings()

except ImportError:
    import os
    from dataclasses import dataclass, field

    @dataclass
    class Settings:
        BOT_MODE: BotMode = BotMode.PAPER
        EXCHANGE_ID: str = os.getenv("EXCHANGE_ID", "binance")
        USE_TESTNET: bool = os.getenv("USE_TESTNET", "true").lower() == "true"

        EXCHANGE_API_KEY: str = os.getenv("EXCHANGE_API_KEY", "")
        EXCHANGE_API_SECRET: str = os.getenv("EXCHANGE_API_SECRET", "")
        EXCHANGE_PASSWORD: str = os.getenv("EXCHANGE_PASSWORD", "")

        TRADING_SYMBOLS: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
        DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "1h")

        MAX_DAILY_DRAWDOWN_PCT: Decimal = Decimal(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "3.0"))
        MAX_ACCOUNT_EXPOSURE_PCT: Decimal = Decimal(os.getenv("MAX_ACCOUNT_EXPOSURE_PCT", "20.0"))
        MAX_RISK_PER_TRADE_PCT: Decimal = Decimal(os.getenv("MAX_RISK_PER_TRADE_PCT", "1.0"))
        CIRCUIT_BREAKER_MAX_ERRORS: int = int(os.getenv("CIRCUIT_BREAKER_MAX_ERRORS", "3"))

        TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        TELEGRAM_ADMIN_CHAT_ID: str = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")
        TELEGRAM_CHANNEL_ID: str = os.getenv("TELEGRAM_CHANNEL_ID", "")
        TELEGRAM_SIGNAL_TTL_SECONDS: int = int(os.getenv("TELEGRAM_SIGNAL_TTL_SECONDS", "45"))
        TELEGRAM_HEARTBEAT_MINUTES: int = int(os.getenv("TELEGRAM_HEARTBEAT_MINUTES", "60"))

        APP_ENV: str = os.getenv("APP_ENV", "development")
        PORT: int = int(os.getenv("PORT", "8000"))
        DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./trading_bot.db")
        AUTO_START_TRADING: bool = os.getenv("AUTO_START_TRADING", "true").lower() == "true"

    settings = Settings()
