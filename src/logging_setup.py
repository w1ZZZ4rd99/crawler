"""Loguru configuration used by demos and the crawler itself."""

import sys

from loguru import logger

LOG_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan> - <level>{message}</level>"
)


def setup_logging(level: str = "INFO") -> None:
    """Replace default loguru sink with a configured stderr sink."""
    logger.remove()
    logger.add(sys.stderr, level=level, format=LOG_FORMAT, colorize=True)
