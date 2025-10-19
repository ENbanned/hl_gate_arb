from datetime import datetime, timedelta, UTC
from unittest.mock import patch

import pytest

from src.core.models import Position, PositionStatus
from src.core.risk import RiskManager


def test_risk_manager_initialization():
  manager = RiskManager()
  
  assert manager.total_realized_pnl == 0.0
  assert manager.total_funding_cost == 0.0
  assert manager.initial_balance == 0.0
  assert manager.emergency_stop is False


def test_set_initial_balance():
  manager = RiskManager()
  manager.set_initial_balance(10000.0)
  
  assert manager.initial_balance == 10000.0


def test_update_realized_pnl_profit():
  manager = RiskManager()
  manager.set_initial_balance(10000.0)
  
  manager.update_realized_pnl(100.0, 10.0)
  
  assert manager.total_realized_pnl == 100.0
  assert manager.total_funding_cost == 10.0
  assert manager.emergency_stop is False


def test_update_realized_pnl_loss():
  manager = RiskManager()
  manager.set_initial_balance(10000.0)
  
  manager.update_realized_pnl(-100.0, 10.0)
  
  assert manager.total_realized_pnl == -100.0
  assert manager.total_funding_cost == 10.0
  assert manager.emergency_stop is False


@patch('src.config.settings.settings')
def test_update_realized_pnl_triggers_emergency_stop(mock_settings):
  mock_settings.emergency_stop_loss_pct = 5.0
  
  manager = RiskManager()
  manager.set_initial_balance(10000.0)
  
  manager.update_realized_pnl(-400.0, 100.0)
  
  assert manager.emergency_stop is True


def test_should_stop_trading():
  manager = RiskManager()
  
  assert manager.should_stop_trading() is False
  
  manager.emergency_stop = True
  assert manager.should_stop_trading() is True


@patch('src.config.settings.settings')
def test_check_position_risk_stop_loss(mock_settings, sample_position):
  mock_settings.stop_loss_pct = 2.0
  mock_settings.max_position_time_minutes = 20
  
  manager = RiskManager()
  sample_position.entry_spread = 5.0
  current_spread = 2.5
  
  should_close, reason = manager.check_position_risk(sample_position, current_spread)
  
  assert should_close is True
  assert reason == "stop_loss"


@patch('src.config.settings.settings')
def test_check_position_risk_time_limit(mock_settings, sample_position):
  mock_settings.stop_loss_pct = 2.0
  mock_settings.max_position_time_minutes = 20
  
  manager = RiskManager()
  sample_position.opened_at = datetime.now(UTC) - timedelta(minutes=25)
  sample_position.entry_spread = 5.0
  current_spread = 5.0
  
  should_close, reason = manager.check_position_risk(sample_position, current_spread)
  
  assert should_close is True
  assert reason == "time_limit"


@patch('src.config.settings.settings')
def test_check_position_risk_no_trigger(mock_settings, sample_position):
  mock_settings.stop_loss_pct = 2.0
  mock_settings.max_position_time_minutes = 20
  
  manager = RiskManager()
  sample_position.entry_spread = 5.0
  current_spread = 4.5
  
  should_close, reason = manager.check_position_risk(sample_position, current_spread)
  
  assert should_close is False
  assert reason == ""


def test_check_position_risk_closed_position(sample_position):
  manager = RiskManager()
  sample_position.status = PositionStatus.CLOSED
  
  should_close, reason = manager.check_position_risk(sample_position, 1.0)
  
  assert should_close is False
  assert reason == ""


def test_get_performance_summary():
  manager = RiskManager()
  manager.set_initial_balance(10000.0)
  manager.update_realized_pnl(200.0, 50.0)
  
  summary = manager.get_performance_summary()
  
  assert summary["total_realized_pnl"] == 200.0
  assert summary["total_funding_cost"] == 50.0
  assert summary["net_pnl"] == 150.0
  assert summary["initial_balance"] == 10000.0
  assert summary["return_pct"] == 1.5
  assert summary["emergency_stop"] is False


def test_get_performance_summary_zero_balance():
  manager = RiskManager()
  manager.update_realized_pnl(100.0, 20.0)
  
  summary = manager.get_performance_summary()
  
  assert summary["return_pct"] == 0