from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PositionSizingRule:
  
  def __init__(self, min_spread: float, max_spread: float, balance_pct: float):
    self.min_spread = min_spread
    self.max_spread = max_spread
    self.balance_pct = balance_pct
  
  
  def matches(self, spread: float) -> bool:
    return self.min_spread <= spread < self.max_spread


class Settings(BaseSettings):
  model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
  
  gate_api_key: str = Field(..., alias="GATE_API_KEY")
  gate_api_secret: str = Field(..., alias="GATE_API_SECRET")
  hyperliquid_private_key: str = Field(..., alias="HYPERLIQUID_PRIVATE_KEY")
  hyperliquid_account_address: str = Field(..., alias="HYPERLIQUID_ACCOUNT_ADDRESS")
  
  min_spread_pct: float = Field(2.5, alias="MIN_SPREAD_PCT")
  max_position_time_minutes: int = Field(20, alias="MAX_POSITION_TIME_MINUTES")
  stop_loss_pct: float = Field(2.0, alias="STOP_LOSS_PCT")
  
  position_sizing: str = Field("1.0:2.0:15,2.0:3.0:30,3.0:999:50", alias="POSITION_SIZING")
  
  leverage_override: int | None = Field(None, alias="LEVERAGE_OVERRIDE")
  
  gate_taker_fee: float = Field(0.075, alias="GATE_TAKER_FEE")
  gate_maker_fee: float = Field(0.025, alias="GATE_MAKER_FEE")
  hyperliquid_taker_fee: float = Field(0.045, alias="HYPERLIQUID_TAKER_FEE")
  hyperliquid_maker_fee: float = Field(0.015, alias="HYPERLIQUID_MAKER_FEE")
  
  min_balance_usd: float = Field(100, alias="MIN_BALANCE_USD")
  emergency_stop_loss_pct: float = Field(5.0, alias="EMERGENCY_STOP_LOSS_PCT")
  
  max_funding_rate_diff_pct: float = Field(0.05, alias="MAX_FUNDING_RATE_DIFF_PCT")
  
  _sizing_rules: list[PositionSizingRule] | None = None
  
  
  @field_validator("leverage_override", mode="before")
  @classmethod
  def parse_leverage(cls, v):
    if v == "null" or v is None or v == "":
      return None
    return int(v)
  
  
  def get_sizing_rules(self) -> list[PositionSizingRule]:
    if self._sizing_rules is not None:
      return self._sizing_rules
    
    rules = []
    for rule_str in self.position_sizing.split(","):
      parts = rule_str.strip().split(":")
      if len(parts) == 3:
        min_spread = float(parts[0])
        max_spread = float(parts[1])
        balance_pct = float(parts[2])
        rules.append(PositionSizingRule(min_spread, max_spread, balance_pct))
    
    self._sizing_rules = rules
    return rules
  
  
  def get_balance_pct_for_spread(self, spread: float) -> float:
    rules = self.get_sizing_rules()
    for rule in rules:
      if rule.matches(spread):
        return rule.balance_pct
    return rules[-1].balance_pct if rules else 15.0


settings = Settings()