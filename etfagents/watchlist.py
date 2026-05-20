"""SQLite-backed ETF watchlist management."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WatchlistManager:
    DB_PATH = Path(os.path.expanduser("~/.etfagents/watchlist.db"))

    def __init__(self, db_path: Path | None = None) -> None:
        self._db = db_path or self.DB_PATH
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS groups (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL UNIQUE,
                    sort_order  INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS watchlist (
                    ticker      TEXT    NOT NULL,
                    name        TEXT    NOT NULL DEFAULT '',
                    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                    tags        TEXT    DEFAULT '[]',
                    notes       TEXT    DEFAULT '',
                    added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (ticker, group_id)
                );
                CREATE INDEX IF NOT EXISTS idx_watchlist_group ON watchlist(group_id);
                INSERT OR IGNORE INTO groups (id, name, sort_order) VALUES (1, 'default', 0);
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def list_groups(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT g.id, g.name, g.sort_order, COUNT(w.ticker) AS count "
                "FROM groups g LEFT JOIN watchlist w ON g.id = w.group_id "
                "GROUP BY g.id ORDER BY g.sort_order, g.id"
            ).fetchall()
        return [{"id": r["id"], "name": r["name"], "count": r["count"], "sort_order": r["sort_order"]} for r in rows]

    def add_group(self, name: str, sort_order: int | None = None) -> int:
        with self._connect() as conn:
            if sort_order is None:
                max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM groups").fetchone()[0]
                sort_order = max_order + 1
            try:
                cursor = conn.execute("INSERT INTO groups (name, sort_order) VALUES (?, ?)", (name, sort_order))
            except sqlite3.IntegrityError:
                raise ValueError(f"Group '{name}' already exists") from None
            logger.info("Added group '%s'", name)
            return cursor.lastrowid

    def remove_group(self, name: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
            if row is None:
                return 0
            conn.execute("DELETE FROM groups WHERE id = ?", (row["id"],))
            logger.info("Removed group '%s' (cascade)", name)
            return 1

    def rename_group(self, old_name: str, new_name: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM groups WHERE name = ?", (old_name,)).fetchone()
            if row is None:
                raise ValueError(f"Group '{old_name}' does not exist")
            try:
                conn.execute("UPDATE groups SET name = ? WHERE id = ?", (new_name, row["id"]))
            except sqlite3.IntegrityError:
                raise ValueError(f"Group '{new_name}' already exists") from None
        logger.info("Renamed group '%s' -> '%s'", old_name, new_name)

    def add(self, ticker: str, group: str = "default", tags: list[str] | None = None, notes: str = "", name: str = "") -> None:
        group_id = self._resolve_group_id(group)
        if group_id is None:
            raise ValueError(f"Group '{group}' does not exist")
        if not name:
            name = self._auto_fill_name(ticker)
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO watchlist (ticker, name, group_id, tags, notes) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(ticker, group_id) DO UPDATE SET name=excluded.name, tags=excluded.tags, notes=excluded.notes",
                (ticker, name, group_id, tags_json, notes),
            )
        logger.info("Added ticker %s to group '%s'", ticker, group)

    def remove(self, ticker: str, group: str | None = None) -> int:
        with self._connect() as conn:
            if group is None:
                cursor = conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
            else:
                group_id = self._resolve_group_id(group)
                if group_id is None:
                    return 0
                cursor = conn.execute("DELETE FROM watchlist WHERE ticker = ? AND group_id = ?", (ticker, group_id))
            count = cursor.rowcount
        if count:
            logger.info("Removed ticker %s (%s)", ticker, "all groups" if group is None else f"group '{group}'")
        return count

    def list_tickers(self, group: str | None = None, tags: list[str] | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            query = (
                "SELECT w.ticker, w.name, g.name AS group_name, w.tags, w.notes, w.added_at "
                "FROM watchlist w JOIN groups g ON w.group_id = g.id"
            )
            params: list[Any] = []
            conditions: list[str] = []
            if group is not None:
                conditions.append("g.name = ?")
                params.append(group)
            if tags:
                for tag in tags:
                    conditions.append("w.tags LIKE ? ESCAPE '\\'")
                    escaped = tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    params.append(f'%"{escaped}"%')
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY w.added_at"
            rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            parsed_tags = json.loads(r["tags"]) if r["tags"] else []
            results.append({
                "ticker": r["ticker"],
                "name": r["name"],
                "group": r["group_name"],
                "tags": parsed_tags,
                "notes": r["notes"],
                "added_at": r["added_at"],
            })
        return results

    def get_tickers_for_analysis(self, group: str) -> list[str]:
        entries = self.list_tickers(group=group)
        return [e["ticker"] for e in entries]

    def update(self, ticker: str, group: str = "default", tags: list[str] | None = None, notes: str | None = None) -> None:
        group_id = self._resolve_group_id(group)
        if group_id is None:
            raise ValueError(f"Group '{group}' does not exist")
        with self._connect() as conn:
            if tags is not None:
                conn.execute("UPDATE watchlist SET tags = ? WHERE ticker = ? AND group_id = ?",
                             (json.dumps(tags, ensure_ascii=False), ticker, group_id))
            if notes is not None:
                conn.execute("UPDATE watchlist SET notes = ? WHERE ticker = ? AND group_id = ?",
                             (notes, ticker, group_id))

    def all_tags(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT tags FROM watchlist").fetchall()
        tags: set[str] = set()
        for r in rows:
            try:
                tags.update(json.loads(r["tags"]))
            except (json.JSONDecodeError, TypeError):
                continue
        return sorted(tags)

    def _resolve_group_id(self, name: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else None

    def _auto_fill_name(self, ticker: str) -> str:
        try:
            from etfagents.dataflows.config import set_config, get_config
            from etfagents.dataflows.interface import route_to_vendor
            from etfagents.default_config import DEFAULT_CONFIG
            import copy
            if not get_config():
                set_config(copy.deepcopy(DEFAULT_CONFIG))
            today_iso = date.today().isoformat()
            csv_text = route_to_vendor("get_etf_info", ticker, today_iso)
            if not csv_text or "No ETF profile" in csv_text:
                return ticker
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                if "name" in row and row["name"].strip():
                    return row["name"].strip()
            return ticker
        except (ValueError, KeyError, IndexError, RuntimeError, ConnectionError, OSError) as exc:
            logger.warning("Auto-fill name failed for %s: %s", ticker, exc)
            return ticker
