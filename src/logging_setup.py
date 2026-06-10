"""Loguru configuration used by demos and the crawler itself."""

import sys

from loguru import logger

LOG_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan> - <level>{message}</level>"
)
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}"


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    rotation: str = "10 MB",
    retention: int = 5,
) -> None:
    """Console sink, plus an optional rotating file sink."""
    logger.remove()
    logger.add(sys.stderr, level=level, format=LOG_FORMAT, colorize=True)
    if log_file:
        logger.add(
            log_file,
            level=level,
            format=FILE_FORMAT,
            rotation=rotation,      # start a new file when it grows past this
            retention=retention,    # keep this many rotated files
            compression="zip",
            encoding="utf-8",
            enqueue=True,           # do not block the event loop on writes
        )
