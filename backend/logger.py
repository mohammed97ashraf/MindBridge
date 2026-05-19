"""
Centralised logger — daily rotation, 30-day retention, console mirror,
and an unhandled-exception hook that routes crashes through the log file
instead of vanishing into the void.

Usage
-----
    from backend.logger import get_logger
    _log = get_logger(__name__)
    _log.info("hello %s", "world")
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

_LOG_DIR = Path(__file__).parent.parent / "logs"
_FMT = "%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Return a named logger with file + console handlers.

    Idempotent — safe to call multiple times with the same *name*.
    File handler: DEBUG+, daily rotation, 30-day backups.
    Console handler: INFO+.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_FMT, _DATEFMT)

    # ── Rotating file: midnight UTC, keep 30 days ────────────────────────────
    fh = TimedRotatingFileHandler(
        filename=_LOG_DIR / "mindbridge.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=True,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    # ── Console: INFO and above ──────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


def install_exception_hook() -> None:
    """
    Route unhandled exceptions through the 'mindbridge.unhandled' logger.

    KeyboardInterrupt is forwarded to the default hook so Ctrl-C still works.
    Call once at application startup (backend/__init__.py does this).
    """
    _root = get_logger("mindbridge.unhandled")

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Optional[object],
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
            return
        _root.critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb),  # type: ignore[arg-type]
        )

    sys.excepthook = _hook
