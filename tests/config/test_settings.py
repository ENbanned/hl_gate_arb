import os
from unittest.mock import patch

import pytest

from src.config.settings import PositionSizingRule, Settings
from pydantic import ValidationError


def test_position_sizing_rule_matches():
  rule = PositionSizingRule(1.0, 2.0, 15.0)
  
  assert rule.matches(1.0) is True
  assert rule.matches(1.5) is True
  assert rule.matches(1.99) is True
  assert rule.matches(2.0) is False
  assert rule.matches(0.5) is False


def test_settings_defaults():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc"
  }, clear=True):
    settings = Settings(_env_file=None)
    
    assert settings.min_spread_pct == 2.5
    assert settings.max_position_time_minutes == 20
    assert settings.stop_loss_pct == 2.0
    assert settings.leverage_override is None
    assert settings.min_balance_usd == 100
    assert settings.emergency_stop_loss_pct == 5.0


def test_settings_env_override():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc",
    "MIN_SPREAD_PCT": "5.0",
    "MAX_POSITION_TIME_MINUTES": "30",
    "LEVERAGE_OVERRIDE": "15"
  }):
    settings = Settings()
    
    assert settings.min_spread_pct == 5.0
    assert settings.max_position_time_minutes == 30
    assert settings.leverage_override == 15


def test_settings_leverage_override_null():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc",
    "LEVERAGE_OVERRIDE": "null"
  }):
    settings = Settings()
    assert settings.leverage_override is None


def test_settings_leverage_override_empty():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc",
    "LEVERAGE_OVERRIDE": ""
  }):
    settings = Settings()
    assert settings.leverage_override is None


def test_get_sizing_rules_parsing():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc",
    "POSITION_SIZING": "1.0:2.0:15,2.0:3.0:30,3.0:999:50"
  }):
    settings = Settings()
    rules = settings.get_sizing_rules()
    
    assert len(rules) == 3
    assert rules[0].min_spread == 1.0
    assert rules[0].max_spread == 2.0
    assert rules[0].balance_pct == 15.0
    assert rules[1].balance_pct == 30.0
    assert rules[2].balance_pct == 50.0


def test_get_sizing_rules_caching():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc"
  }):
    settings = Settings()
    rules1 = settings.get_sizing_rules()
    rules2 = settings.get_sizing_rules()
    
    assert rules1 is rules2


def test_get_balance_pct_for_spread():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc",
    "POSITION_SIZING": "1.0:2.0:15,2.0:3.0:30,3.0:999:50"
  }):
    settings = Settings()
    
    assert settings.get_balance_pct_for_spread(1.5) == 15.0
    assert settings.get_balance_pct_for_spread(2.5) == 30.0
    assert settings.get_balance_pct_for_spread(5.0) == 50.0
    assert settings.get_balance_pct_for_spread(0.5) == 50.0


def test_get_balance_pct_for_spread_empty_rules():
  with patch.dict(os.environ, {
    "GATE_API_KEY": "test_key",
    "GATE_API_SECRET": "test_secret",
    "HYPERLIQUID_PRIVATE_KEY": "0x123",
    "HYPERLIQUID_ACCOUNT_ADDRESS": "0xabc",
    "POSITION_SIZING": ""
  }):
    settings = Settings()
    
    assert settings.get_balance_pct_for_spread(2.5) == 15.0


def test_settings_missing_required_fields():
  with patch.dict(os.environ, {}, clear=True):
    with pytest.raises(ValidationError):
      Settings(_env_file=None)