import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

import structlog
from colorama import Fore, Style, init


init(autoreset=True)


CONSOLE_EVENTS = {
  "application_starting",
  "application_started",
  "application_shutting_down",
  "application_shutdown_complete",
  "strategy_initialized",
  "strategy_started",
  "spread_detected",
  "spread_opportunity_detected",
  "position_opened",
  "position_closed",
  "emergency_stop_triggered",
  "gate_dual_mode_enabled",
  "funding_rates_loaded",
  "position_stop_loss_triggered",
  "position_time_limit_reached",
  "critical_close_failure",
}


def console_filter(logger, method_name, event_dict):
  event = event_dict.get("event", "")
  
  if event in CONSOLE_EVENTS:
    event_dict["_console"] = True
  
  return event_dict


def add_colors(logger, method_name, event_dict):
  if not event_dict.get("_console"):
    return event_dict
  
  level = event_dict.get("level", "").upper()
  event = event_dict.get("event", "")
  
  color_map = {
    "DEBUG": Fore.CYAN,
    "INFO": Fore.GREEN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "CRITICAL": Fore.RED + Style.BRIGHT,
  }
  
  event_color_map = {
    "spread_opportunity_detected": Fore.MAGENTA + Style.BRIGHT,
    "position_opened": Fore.GREEN + Style.BRIGHT,
    "position_closed": Fore.BLUE + Style.BRIGHT,
    "emergency_stop_triggered": Fore.RED + Style.BRIGHT,
    "position_stop_loss_triggered": Fore.YELLOW + Style.BRIGHT,
  }
  
  color = event_color_map.get(event, color_map.get(level, ""))
  
  if color:
    event_dict["event"] = f"{color}{event}{Style.RESET_ALL}"
  
  return event_dict


def mask_sensitive_data(logger, method_name, event_dict):
  sensitive_keys = ["api_key", "api_secret", "password", "private_key", "secret", "token"]
  
  def mask_value(value):
    if isinstance(value, str) and len(value) > 8:
      return value[:4] + "***" + value[-4:]
    return "***"
  
  def mask_dict(d):
    result = {}
    for key, value in d.items():
      if any(sensitive in key.lower() for sensitive in sensitive_keys):
        result[key] = mask_value(value)
      elif isinstance(value, dict):
        result[key] = mask_dict(value)
      else:
        result[key] = value
    return result
  
  for key in list(event_dict.keys()):
    if any(sensitive in key.lower() for sensitive in sensitive_keys):
      event_dict[key] = mask_value(event_dict[key])
    elif isinstance(event_dict[key], dict):
      event_dict[key] = mask_dict(event_dict[key])
  
  return event_dict


def round_floats(logger, method_name, event_dict):
  float_keys = [
    "price", "amount", "volume", "profit", "balance", "rate", "fee",
    "spread", "slippage", "pnl", "size", "leverage", "value", "funding"
  ]
  
  for key in list(event_dict.keys()):
    if any(fk in key.lower() for fk in float_keys):
      if isinstance(event_dict[key], (float, int)):
        event_dict[key] = round(float(event_dict[key]), 6)
  
  return event_dict


class ConsoleRenderer:
  
  def __call__(self, logger, method_name, event_dict):
    if not event_dict.get("_console"):
      return ""
    
    event = event_dict.pop("event", "")
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "")
    
    event_dict.pop("_console", None)
    event_dict.pop("filename", None)
    event_dict.pop("func_name", None)
    event_dict.pop("lineno", None)
    event_dict.pop("logger", None)
    
    parts = [f"[{timestamp}]", f"{event}"]
    
    for key, value in event_dict.items():
      if isinstance(value, dict):
        continue
      parts.append(f"{key}={value}")
    
    return " ".join(parts)


def setup_logging(
  log_level: str = "INFO",
  log_dir: str = "logs",
  console_output: bool = True,
  max_bytes: int = 100 * 1024 * 1024,
  backup_count: int = 5,
):
  log_path = Path(log_dir)
  log_path.mkdir(parents=True, exist_ok=True)
  
  processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
    mask_sensitive_data,
    round_floats,
    console_filter,
    add_colors,
    structlog.processors.format_exc_info,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.UnicodeDecoder(),
    structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
  ]
  
  structlog.configure(
    processors=processors,
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
  )
  
  handlers = []
  
  if console_output:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(
      structlog.stdlib.ProcessorFormatter(
        processor=ConsoleRenderer(),
      )
    )
    handlers.append(console_handler)
  
  full_handler = RotatingFileHandler(
    log_path / "full.log",
    maxBytes=max_bytes,
    backupCount=backup_count,
    encoding="utf-8",
  )
  full_handler.setLevel(log_level)
  full_handler.setFormatter(
    structlog.stdlib.ProcessorFormatter(
      processor=structlog.processors.JSONRenderer(),
    )
  )
  handlers.append(full_handler)
  
  error_handler = RotatingFileHandler(
    log_path / "errors.log",
    maxBytes=max_bytes,
    backupCount=backup_count,
    encoding="utf-8",
  )
  error_handler.setLevel(logging.WARNING)
  error_handler.setFormatter(
    structlog.stdlib.ProcessorFormatter(
      processor=structlog.processors.JSONRenderer(),
    )
  )
  handlers.append(error_handler)
  
  logging.basicConfig(
    format="%(message)s",
    level=log_level,
    handlers=handlers,
  )
  
  for logger_name in ["urllib3", "aiohttp", "asyncio"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str = None):
  return structlog.get_logger(name)