from pathlib import Path
import sys

from loguru import logger


def setup():
  logger.remove()
  
  format_console = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
  )
  
  format_file = (
    "{time:YYYY-MM-DD HH:mm:ss} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
  )
  
  logger.add(
    sys.stdout,
    format=format_console,
    level="DEBUG",
    colorize=True,
  )
  
  logs_dir = Path("logs")
  logs_dir.mkdir(exist_ok=True)
  
  logger.add(
    logs_dir / "app.log",
    format=format_file,
    level="INFO",
    rotation="100 MB",
    retention="30 days",
    compression="zip",
  )
  
  logger.add(
    logs_dir / "errors.log",
    format=format_file,
    level="ERROR",
    rotation="50 MB",
    retention="90 days",
    compression="zip",
  )
  
  logger.level("SUCCESS", color="<green>")
  logger.level("ERROR", color="<red>")
  logger.level("INFO", color="<white>")
  logger.level("DEBUG", color="<dim>")
  logger.level("WARNING", color="<yellow>")
  
  return logger


log = setup()