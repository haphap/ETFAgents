from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator

from etfagents.dataflows.config import get_config


logger = logging.getLogger(__name__)


class DailySnapshotCacheError(RuntimeError):
    """Raised when the shared daily snapshot cache cannot be read safely."""


SnapshotBuilder = Callable[[str, int], tuple[dict[str, Any], dict[str, Any] | None]]


def get_or_build_shared_snapshot(
    snapshot_kind: str,
    curr_date: str,
    min_coverage_days: int,
    schema_version: int,
    builder: SnapshotBuilder,
) -> tuple[dict[str, Any], bool]:
    """Return a cached snapshot payload or build and persist it."""
    cached = _load_snapshot_file(snapshot_kind, curr_date)
    if _is_usable_snapshot(cached, schema_version, min_coverage_days):
        return cached["payload"], True

    with _snapshot_lock(_lock_path(snapshot_kind, curr_date)):
        cached = _load_snapshot_file(snapshot_kind, curr_date)
        if _is_usable_snapshot(cached, schema_version, min_coverage_days):
            return cached["payload"], True

        payload, metadata = builder(curr_date, min_coverage_days)
        snapshot = {
            "schema_version": schema_version,
            "snapshot_kind": snapshot_kind,
            "curr_date": curr_date,
            "metadata": {
                **(metadata or {}),
                "built_at_utc": datetime.now(timezone.utc).isoformat(),
                "coverage_days": int(min_coverage_days),
            },
            "payload": payload,
        }
        _write_snapshot_file(snapshot_kind, curr_date, snapshot)
        return payload, False


def _snapshot_root() -> Path:
    cache_dir = Path(get_config()["data_cache_dir"])
    root = cache_dir / "shared_snapshots"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _snapshot_path(snapshot_kind: str, curr_date: str) -> Path:
    kind_dir = _snapshot_root() / snapshot_kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    return kind_dir / f"{curr_date}.json"


def _lock_path(snapshot_kind: str, curr_date: str) -> Path:
    kind_dir = _snapshot_root() / snapshot_kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    return kind_dir / f"{curr_date}.lock"


def _load_snapshot_file(snapshot_kind: str, curr_date: str) -> dict[str, Any] | None:
    path = _snapshot_path(snapshot_kind, curr_date)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
    except json.JSONDecodeError as exc:
        _quarantine_corrupt_snapshot(path)
        raise DailySnapshotCacheError(
            f"Corrupted shared snapshot cache at '{path}': invalid JSON."
        ) from exc

    if not isinstance(snapshot, dict):
        _quarantine_corrupt_snapshot(path)
        raise DailySnapshotCacheError(
            f"Corrupted shared snapshot cache at '{path}': root payload must be an object."
        )
    if not isinstance(snapshot.get("metadata"), dict):
        _quarantine_corrupt_snapshot(path)
        raise DailySnapshotCacheError(
            f"Corrupted shared snapshot cache at '{path}': missing metadata object."
        )
    if "payload" not in snapshot:
        _quarantine_corrupt_snapshot(path)
        raise DailySnapshotCacheError(
            f"Corrupted shared snapshot cache at '{path}': missing payload field."
        )
    return snapshot


def _quarantine_corrupt_snapshot(path: Path) -> None:
    """Rename a corrupt snapshot file to ``.corrupt.<timestamp>`` so it self-heals on next call.

    Unlike the plan's suggested pattern of returning ``None`` (transparent rebuild),
    callers still raise :class:`DailySnapshotCacheError` after quarantining. This
    preserves backward compatibility with existing tests that assert corrupted caches
    must raise. The file is moved aside so the *next* call rebuilds successfully.
    """
    corrupt_path = path.with_suffix(path.suffix + f".corrupt.{int(time.time())}")
    try:
        path.rename(corrupt_path)
    except OSError as exc:
        logger.warning("Failed to quarantine corrupt snapshot %s: %s", path, exc)


def _is_usable_snapshot(
    snapshot: dict[str, Any] | None,
    schema_version: int,
    min_coverage_days: int,
) -> bool:
    if not snapshot:
        return False
    if snapshot.get("schema_version") != schema_version:
        return False
    metadata = snapshot.get("metadata", {})
    coverage_days = metadata.get("coverage_days")
    if not isinstance(coverage_days, int):
        return False
    return coverage_days >= min_coverage_days


def _write_snapshot_file(
    snapshot_kind: str,
    curr_date: str,
    snapshot: dict[str, Any],
) -> None:
    path = _snapshot_path(snapshot_kind, curr_date)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f"{path.stem}.",
            suffix=".tmp",
        ) as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = handle.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@contextmanager
def _snapshot_lock(
    path: Path,
    timeout_seconds: float = 60.0,
    stale_lock_seconds: float = 300.0,
) -> Generator[None, None, None]:
    start = time.monotonic()
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("utf-8"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                age_seconds = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age_seconds >= stale_lock_seconds:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() - start >= timeout_seconds:
                raise DailySnapshotCacheError(
                    f"Timed out waiting for shared snapshot cache lock '{path}'."
                )
            time.sleep(0.1)
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
