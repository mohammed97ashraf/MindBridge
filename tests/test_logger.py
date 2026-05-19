"""Tests for backend.logger — handler setup, idempotency, log directory."""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest

from backend.logger import get_logger, install_exception_hook


class TestGetLogger:
    def test_returns_logger_instance(self):
        log = get_logger("test.basic")
        assert isinstance(log, logging.Logger)

    def test_has_file_and_console_handlers(self):
        log = get_logger("test.handlers")
        handler_types = [type(h) for h in log.handlers]
        assert TimedRotatingFileHandler in handler_types
        assert logging.StreamHandler in handler_types

    def test_idempotent_no_duplicate_handlers(self):
        name = "test.idempotent"
        log1 = get_logger(name)
        count_after_first = len(log1.handlers)
        log2 = get_logger(name)
        assert log1 is log2
        assert len(log2.handlers) == count_after_first

    def test_does_not_propagate(self):
        log = get_logger("test.propagate")
        assert log.propagate is False

    def test_level_is_debug(self):
        log = get_logger("test.level")
        assert log.level == logging.DEBUG

    def test_log_directory_created(self):
        get_logger("test.dir")
        log_dir = Path(__file__).parent.parent / "logs"
        assert log_dir.exists()

    def test_file_handler_rotates_at_midnight(self):
        log = get_logger("test.rotation")
        fh = next(h for h in log.handlers if isinstance(h, TimedRotatingFileHandler))
        assert fh.when.upper() == "MIDNIGHT"

    def test_file_handler_keeps_30_days(self):
        log = get_logger("test.retention")
        fh = next(h for h in log.handlers if isinstance(h, TimedRotatingFileHandler))
        assert fh.backupCount == 30

    def test_console_handler_level_is_info(self):
        log = get_logger("test.console_level")
        ch = next(
            h for h in log.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, TimedRotatingFileHandler)
        )
        assert ch.level == logging.INFO


class TestInstallExceptionHook:
    def test_installs_without_error(self):
        """install_exception_hook() must not raise."""
        install_exception_hook()

    def test_keyboard_interrupt_uses_default_hook(self, monkeypatch):
        """KeyboardInterrupt must fall through to sys.__excepthook__."""
        import sys
        called = {}

        def fake_default(etype, val, tb):
            called["etype"] = etype

        monkeypatch.setattr(sys, "__excepthook__", fake_default)
        install_exception_hook()
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        assert called.get("etype") is KeyboardInterrupt
