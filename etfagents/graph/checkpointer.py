"""LangGraph checkpoint helpers for resumable TradingAgents runs."""

from __future__ import annotations

import hashlib
import sqlite3
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change in a future version\..*",
    category=LangChainPendingDeprecationWarning,
)

from langgraph.checkpoint.sqlite import SqliteSaver

_DELETE_BY_THREAD_ID = {
    "writes": "DELETE FROM writes WHERE thread_id = ?",
    "checkpoints": "DELETE FROM checkpoints WHERE thread_id = ?",
}


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """Return the checkpoint database path for a ticker."""
    checkpoint_dir = Path(data_dir) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir / f"{ticker.upper()}.db"


def thread_id(ticker: str, trade_date: str) -> str:
    """Return a deterministic checkpoint thread ID for ticker+date."""
    payload = f"{ticker.upper()}:{trade_date}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@contextmanager
def get_checkpointer(
    data_dir: str | Path,
    ticker: str,
) -> Generator[SqliteSaver, None, None]:
    """Yield a SQLite-backed LangGraph checkpointer."""
    database_path = _db_path(data_dir, ticker)
    conn = sqlite3.connect(str(database_path), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def checkpoint_step(data_dir: str | Path, ticker: str, trade_date: str) -> int | None:
    """Return the most recent saved step for a ticker/date, if present."""
    database_path = _db_path(data_dir, ticker)
    if not database_path.exists():
        return None

    config = {"configurable": {"thread_id": thread_id(ticker, trade_date)}}
    with get_checkpointer(data_dir, ticker) as saver:
        checkpoint_tuple = saver.get_tuple(config)
    if checkpoint_tuple is None:
        return None
    return checkpoint_tuple.metadata.get("step")


def has_checkpoint(data_dir: str | Path, ticker: str, trade_date: str) -> bool:
    """Return whether a resumable checkpoint exists for ticker/date."""
    return checkpoint_step(data_dir, ticker, trade_date) is not None


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """Delete all checkpoint databases and return the number removed."""
    checkpoint_dir = Path(data_dir) / "checkpoints"
    if not checkpoint_dir.exists():
        return 0

    deleted = 0
    for database_path in checkpoint_dir.glob("*.db"):
        database_path.unlink()
        deleted += 1
    return deleted


def clear_checkpoint(data_dir: str | Path, ticker: str, trade_date: str) -> None:
    """Delete the saved rows for a specific ticker/date checkpoint."""
    database_path = _db_path(data_dir, ticker)
    if not database_path.exists():
        return

    tid = thread_id(ticker, trade_date)
    conn = sqlite3.connect(str(database_path))
    try:
        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for table, query in _DELETE_BY_THREAD_ID.items():
            if table in existing_tables:
                conn.execute(query, (tid,))
        conn.commit()
    finally:
        conn.close()
