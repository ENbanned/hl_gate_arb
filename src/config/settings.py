from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
  )
  
  gate_api_key: str
  gate_api_secret: str
  
  hyperliquid_private_key: str
  hyperliquid_account_address: str
  
  telegram_bot_token: str
  telegram_chat_id: str
  
  min_balance_usd: float = Field(default=100.0)
  leverage_override: int | None = Field(default=3)
  
  min_net_spread_pct: float = Field(default=0.5)
  max_funding_rate_pct: float = Field(default=0.15)
  position_size_pct: float = Field(default=8.0)
  
  target_spread_pct: float = Field(default=0.15)
  stop_loss_pct: float = Field(default=1.5)
  spread_compression_pct: float = Field(default=70.0)
  time_limit_minutes: int = Field(default=30)
  
  partial_exit_spread_pct: float = Field(default=0.25)
  partial_exit_size_pct: float = Field(default=50.0)
  
  max_concurrent_positions: int = Field(default=3)
  daily_loss_limit_pct: float = Field(default=2.0)
  position_check_interval_seconds: int = Field(default=10)
  consecutive_loss_limit: int = Field(default=3)
  
  scan_interval_seconds: float = Field(default=3.0)
  funding_rate_update_seconds: int = Field(default=300)
  
  log_level: str = Field(default="INFO")


settings = Settings()