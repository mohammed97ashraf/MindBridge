"""Tests for backend.database — checkpointer factory."""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from backend.database import get_checkpointer


class TestGetCheckpointer:
    def test_returns_memory_saver(self):
        cp = get_checkpointer()
        assert isinstance(cp, MemorySaver)

    def test_returns_new_instance_each_call(self):
        """Each call should return a fresh checkpointer, not a cached singleton."""
        cp1 = get_checkpointer()
        cp2 = get_checkpointer()
        assert cp1 is not cp2
