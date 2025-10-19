import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.logging import (
  ConsoleRenderer,
  add_colors,
  console_filter,
  get_logger,
  mask_sensitive_data,
  round_floats,
  setup_logging,
)


def test_console_filter_console_event():
  event_dict = {"event": "application_starting"}
  
  result = console_filter(None, None, event_dict)
  
  assert result["_console"] is True


def test_console_filter_non_console_event():
  event_dict = {"event": "some_debug_event"}
  
  result = console_filter(None, None, event_dict)
  
  assert "_console" not in result


def test_add_colors_console_event():
  event_dict = {
    "event": "spread_opportunity_detected",
    "level": "INFO",
    "_console": True
  }
  
  result = add_colors(None, None, event_dict)
  
  assert "\033[" in result["event"]


def test_add_colors_non_console_event():
  event_dict = {
    "event": "test_event",
    "level": "INFO"
  }
  
  result = add_colors(None, None, event_dict)
  
  assert result["event"] == "test_event"


def test_mask_sensitive_data_api_key():
  event_dict = {"api_key": "1234567890abcdef"}
  
  result = mask_sensitive_data(None, None, event_dict)
  
  assert result["api_key"] == "1234***cdef"


def test_mask_sensitive_data_private_key():
  event_dict = {"private_key": "0x1234567890abcdef"}
  
  result = mask_sensitive_data(None, None, event_dict)
  
  assert result["private_key"] == "0x12***cdef"


def test_mask_sensitive_data_nested_dict():
  event_dict = {
    "user": {
      "password": "secretpassword123"
    }
  }
  
  result = mask_sensitive_data(None, None, event_dict)
  
  assert result["user"]["password"] == "secr***d123"


def test_mask_sensitive_data_short_value():
  event_dict = {"secret": "short"}
  
  result = mask_sensitive_data(None, None, event_dict)
  
  assert result["secret"] == "***"


def test_round_floats_price():
  event_dict = {"price": 50123.456789123}
  
  result = round_floats(None, None, event_dict)
  
  assert result["price"] == 50123.456789


def test_round_floats_multiple_fields():
  event_dict = {
    "buy_price": 50123.456789123,
    "sell_price": 50100.123456789,
    "profit": 23.123456789
  }
  
  result = round_floats(None, None, event_dict)
  
  assert result["buy_price"] == 50123.456789
  assert result["sell_price"] == 50100.123457
  assert result["profit"] == 23.123457


def test_round_floats_non_float_fields():
  event_dict = {
    "event": "test",
    "count": 5
  }
  
  result = round_floats(None, None, event_dict)
  
  assert result["event"] == "test"
  assert result["count"] == 5


def test_console_renderer_console_event():
  renderer = ConsoleRenderer()
  event_dict = {
    "event": "position_opened",
    "timestamp": "12:34:56",
    "level": "INFO",
    "_console": True,
    "coin": "BTC",
    "size": 100.0
  }
  
  result = renderer(None, None, event_dict)
  
  assert "position_opened" in result
  assert "coin=BTC" in result
  assert "size=100.0" in result


def test_console_renderer_non_console_event():
  renderer = ConsoleRenderer()
  event_dict = {
    "event": "debug_event",
    "timestamp": "12:34:56",
    "level": "DEBUG"
  }
  
  result = renderer(None, None, event_dict)
  
  assert result == ""


def test_console_renderer_removes_metadata():
  renderer = ConsoleRenderer()
  event_dict = {
    "event": "test",
    "timestamp": "12:34:56",
    "level": "INFO",
    "_console": True,
    "filename": "test.py",
    "func_name": "test_func",
    "lineno": 42,
    "logger": "test_logger"
  }
  
  result = renderer(None, None, event_dict)
  
  assert "filename" not in result
  assert "func_name" not in result


@patch('pathlib.Path.mkdir')
@patch('logging.basicConfig')
def test_setup_logging(mock_basicConfig, mock_mkdir):
  setup_logging(log_level="INFO", console_output=True)
  
  mock_mkdir.assert_called_once()
  mock_basicConfig.assert_called_once()


@patch('pathlib.Path.mkdir')
@patch('logging.basicConfig')
def test_setup_logging_no_console(mock_basicConfig, mock_mkdir):
  setup_logging(log_level="DEBUG", console_output=False)
  
  mock_basicConfig.assert_called_once()


@patch('pathlib.Path.mkdir')
@patch('logging.basicConfig')
def test_setup_logging_custom_log_dir(mock_basicConfig, mock_mkdir):
  setup_logging(log_level="INFO", log_dir="custom_logs")
  
  mock_mkdir.assert_called_once()


def test_get_logger():
  logger = get_logger("test_module")
  
  assert logger is not None


def test_get_logger_no_name():
  logger = get_logger()
  
  assert logger is not None


def test_console_filter_all_console_events():
  console_events = [
    "application_starting",
    "application_started",
    "spread_opportunity_detected",
    "position_opened",
    "position_closed",
    "emergency_stop_triggered"
  ]
  
  for event in console_events:
    event_dict = {"event": event}
    result = console_filter(None, None, event_dict)
    assert result["_console"] is True


def test_add_colors_levels():
  levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
  
  for level in levels:
    event_dict = {
      "event": "test",
      "level": level,
      "_console": True
    }
    result = add_colors(None, None, event_dict)
    assert result["event"] == event_dict["event"]


def test_mask_sensitive_data_preserves_non_sensitive():
  event_dict = {
    "coin": "BTC",
    "price": 50000.0,
    "api_key": "secret123456"
  }
  
  result = mask_sensitive_data(None, None, event_dict)
  
  assert result["coin"] == "BTC"
  assert result["price"] == 50000.0
  assert "***" in result["api_key"]