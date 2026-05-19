"""
State-persistence layer.

Exposes a single factory: get_checkpointer().

The current backend is MemorySaver (in-process, single-worker).
To migrate to a persistent store, replace only the body of
get_checkpointer() — nothing else in the codebase needs to change:

    # SQLite example
    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver.from_conn_string("checkpoints.db")

    # Redis example
    from langgraph.checkpoint.redis import RedisSaver
    return RedisSaver.from_conn_string(os.getenv("REDIS_URL"))
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from backend.logger import get_logger

_log = get_logger(__name__)


def get_checkpointer() -> MemorySaver:
    """Return an initialised LangGraph checkpointer."""
    _log.debug("Creating in-memory checkpointer")
    return MemorySaver()
