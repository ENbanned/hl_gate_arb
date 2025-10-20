import logging
import sys
from pathlib import Path

import structlog


def setup_logging(log_level: str = "INFO", log_dir: Path | None = None):
  if log_dir:
    log_dir.mkdir(parents=True, exist_ok=True)
  
  structlog.configure(
    processors=[
      structlog.contextvars.merge_contextvars,
      structlog.processors.add_log_level,
      structlog.processors.TimeStamper(fmt="iso", utc=True),
      structlog.processors.StackInfoRenderer(),
      structlog.processors.format_exc_info,
      structlog.processors.UnicodeDecoder(),
      structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
      getattr(logging, log_level.upper())
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
  )


def get_logger(name: str) -> structlog.BoundLogger:
  return structlog.get_logger(name)