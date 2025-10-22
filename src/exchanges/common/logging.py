import sys

import structlog


def setup_logging(level: str = "INFO") -> None:
  structlog.configure(
    processors=[
      structlog.contextvars.merge_contextvars,
      structlog.processors.add_log_level,
      structlog.processors.StackInfoRenderer(),
      structlog.dev.set_exc_info,
      structlog.processors.TimeStamper(fmt="iso", utc=True),
      structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
      getattr(structlog.stdlib, level.upper(), structlog.stdlib.INFO)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=False,
  )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
  return structlog.get_logger(name)