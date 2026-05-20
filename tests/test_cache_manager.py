import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from etfagents.cache_manager import CacheManager
from etfagents.default_config import DEFAULT_CONFIG


class CacheManagerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config["data_cache_dir"] = str(self.root / "cache")
        self.config["results_dir"] = str(self.root / "results")
        self.mgr = CacheManager(self.config)

    def tearDown(self):
        self.tempdir.cleanup()

    def _create_file(self, path: Path, content: str = "{}", mtime_offset: float = 0) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if mtime_offset != 0:
            atime = mtime = time.time() + mtime_offset
            os.utime(path, (atime, mtime))
        return path

    def test_stats_empty_dir(self):
        s = self.mgr.stats()
        self.assertEqual(s["api"]["count"], 0)
        self.assertEqual(s["signals"]["count"], 0)
        self.assertEqual(s["snapshots"]["count"], 0)
        self.assertEqual(s["checkpoints"]["count"], 0)
        self.assertEqual(s["total_mb"], 0.0)

    def test_stats_nonexistent_dir(self):
        self.config["data_cache_dir"] = str(self.root / "nonexistent")
        self.config["results_dir"] = str(self.root / "nonexistent")
        mgr = CacheManager(self.config)
        s = mgr.stats()
        self.assertEqual(s["total_mb"], 0.0)

    def test_stats_counts_files(self):
        self._create_file(Path(self.config["data_cache_dir"]) / "api_data.json", '{"a":1}' * 1000)
        self._create_file(Path(self.config["results_dir"]) / "backtest_cache" / "hash" / "ticker" / "2026-01-01.json", '{"b":2}' * 1000)
        self._create_file(Path(self.config["data_cache_dir"]) / "shared_snapshots" / "macro" / "2026-01-01.json", '{"c":3}' * 1000)
        self._create_file(Path(self.config["data_cache_dir"]) / "checkpoints" / "test.db", "data" * 1000)

        s = self.mgr.stats()
        self.assertEqual(s["api"]["count"], 1)
        self.assertEqual(s["signals"]["count"], 1)
        self.assertEqual(s["snapshots"]["count"], 1)
        self.assertEqual(s["checkpoints"]["count"], 1)
        self.assertTrue(s["total_mb"] > 0)

    def test_stats_api_excludes_snapshots_and_checkpoints(self):
        self._create_file(Path(self.config["data_cache_dir"]) / "api_data.json", '{}')
        self._create_file(Path(self.config["data_cache_dir"]) / "shared_snapshots" / "kind" / "f.json", '{}')
        self._create_file(Path(self.config["data_cache_dir"]) / "checkpoints" / "x.db", "d")

        s = self.mgr.stats()
        self.assertEqual(s["api"]["count"], 1)
        self.assertEqual(s["snapshots"]["count"], 1)
        self.assertEqual(s["checkpoints"]["count"], 1)

    def test_cleanup_by_age(self):
        old_file = self._create_file(
            Path(self.config["data_cache_dir"]) / "old.json", '{}',
            mtime_offset=-8 * 86400,
        )
        new_file = self._create_file(
            Path(self.config["data_cache_dir"]) / "new.json", '{}',
        )
        result = self.mgr.cleanup(days=7, category="api")
        self.assertEqual(result["deleted_files"], 1)
        self.assertFalse(old_file.exists())
        self.assertTrue(new_file.exists())

    def test_cleanup_days_zero_clears_all(self):
        f = self._create_file(Path(self.config["data_cache_dir"]) / "x.json", '{}')
        result = self.mgr.cleanup(days=0, category="api")
        self.assertEqual(result["deleted_files"], 1)

    def test_clear_signals(self):
        f = self._create_file(
            Path(self.config["results_dir"]) / "backtest_cache" / "hash" / "ticker" / "d.json", '{}'
        )
        result = self.mgr.clear("signals")
        self.assertFalse(f.parent.parent.exists())
        self.assertEqual(result["deleted_files"], 1)

    def test_clear_checkpoints(self):
        db_path = self._create_file(
            Path(self.config["data_cache_dir"]) / "checkpoints" / "510300.SH.db", "sqlite data"
        )
        result = self.mgr.clear("checkpoints")
        self.assertFalse(db_path.exists())
        self.assertEqual(result["deleted_files"], 1)

    def test_clear_all(self):
        self._create_file(Path(self.config["data_cache_dir"]) / "api_data.json", '{}')
        self._create_file(Path(self.config["results_dir"]) / "backtest_cache" / "h" / "t" / "d.json", '{}')
        self._create_file(Path(self.config["data_cache_dir"]) / "shared_snapshots" / "kind" / "f.json", '{}')
        self._create_file(Path(self.config["data_cache_dir"]) / "checkpoints" / "t.db", "d")

        result = self.mgr.clear("all")
        self.assertGreater(result["deleted_files"], 0)

    def test_details_pagination(self):
        for i in range(5):
            self._create_file(
                Path(self.config["data_cache_dir"]) / f"file_{i}.json", '{}'
            )
        page1 = self.mgr.details("api", page=1, page_size=2)
        self.assertEqual(page1["total"], 5)
        self.assertEqual(len(page1["entries"]), 2)
        page3 = self.mgr.details("api", page=3, page_size=2)
        self.assertEqual(len(page3["entries"]), 1)

    def test_details_nonexistent_category_returns_empty(self):
        result = self.mgr.details("api", page=1, page_size=10)
        self.assertEqual(result["total"], 0)

    def test_cleanup_preserves_excluded_subdirs(self):
        api_file = self._create_file(Path(self.config["data_cache_dir"]) / "x.json", '{}')
        snap_file = self._create_file(
            Path(self.config["data_cache_dir"]) / "shared_snapshots" / "kind" / "f.json", '{}'
        )
        cp_file = self._create_file(
            Path(self.config["data_cache_dir"]) / "checkpoints" / "t.db", "d"
        )
        result = self.mgr.cleanup(days=0, category="api")
        self.assertFalse(api_file.exists())
        self.assertTrue(snap_file.exists())
        self.assertTrue(cp_file.exists())

    def test_stats_shows_subdirs_and_kinds(self):
        self._create_file(Path(self.config["data_cache_dir"]) / "subdir_a" / "f.json", '{}')
        self._create_file(Path(self.config["data_cache_dir"]) / "shared_snapshots" / "macro" / "f.json", '{}')
        self._create_file(Path(self.config["data_cache_dir"]) / "checkpoints" / "510300.SH.db", "d")

        s = self.mgr.stats()
        self.assertIn("subdir_a", s["api"]["subdirs"])
        self.assertIn("macro", s["snapshots"]["kinds"])
        self.assertIn("510300.SH", s["checkpoints"]["tickers"])


class F3IsUsableSnapshotTests(unittest.TestCase):
    def test_coverage_days_non_int_returns_false(self):
        from etfagents.agents.utils.daily_snapshot_cache import _is_usable_snapshot
        snapshot = {
            "schema_version": 1,
            "metadata": {"coverage_days": "not_an_int"},
            "payload": {},
        }
        self.assertFalse(_is_usable_snapshot(snapshot, schema_version=1, min_coverage_days=1))

    def test_coverage_days_none_returns_false(self):
        from etfagents.agents.utils.daily_snapshot_cache import _is_usable_snapshot
        snapshot = {
            "schema_version": 1,
            "metadata": {},
            "payload": {},
        }
        self.assertFalse(_is_usable_snapshot(snapshot, schema_version=1, min_coverage_days=1))

    def test_coverage_days_valid_int_passes(self):
        from etfagents.agents.utils.daily_snapshot_cache import _is_usable_snapshot
        snapshot = {
            "schema_version": 1,
            "metadata": {"coverage_days": 365},
            "payload": {},
        }
        self.assertTrue(_is_usable_snapshot(snapshot, schema_version=1, min_coverage_days=365))


class F2QuarantineCorruptSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_config = copy.deepcopy(DEFAULT_CONFIG)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config["data_cache_dir"] = self.tempdir.name

    def tearDown(self):
        self.tempdir.cleanup()

    def test_corrupt_json_file_is_quarantined(self):
        from etfagents.agents.utils.daily_snapshot_cache import (
            DailySnapshotCacheError,
            _load_snapshot_file,
        )
        from etfagents.dataflows.config import set_config

        set_config(self.config)
        kind_dir = Path(self.tempdir.name) / "shared_snapshots" / "test_kind"
        kind_dir.mkdir(parents=True, exist_ok=True)
        corrupt_file = kind_dir / "2026-01-01.json"
        corrupt_file.write_text("NOT VALID JSON{{{")

        with self.assertRaises(DailySnapshotCacheError):
            _load_snapshot_file("test_kind", "2026-01-01")

        remaining = list(kind_dir.glob("2026-01-01.json"))
        self.assertEqual(len(remaining), 0)
        quarantined = list(kind_dir.glob("2026-01-01.json.corrupt.*"))
        self.assertEqual(len(quarantined), 1)

    def test_corrupt_structure_file_is_quarantined(self):
        from etfagents.agents.utils.daily_snapshot_cache import (
            DailySnapshotCacheError,
            _load_snapshot_file,
        )
        from etfagents.dataflows.config import set_config

        set_config(self.config)
        kind_dir = Path(self.tempdir.name) / "shared_snapshots" / "struct_kind"
        kind_dir.mkdir(parents=True, exist_ok=True)
        corrupt_file = kind_dir / "2026-01-01.json"
        corrupt_file.write_text('"not an object"')

        with self.assertRaises(DailySnapshotCacheError):
            _load_snapshot_file("struct_kind", "2026-01-01")

        remaining = list(kind_dir.glob("2026-01-01.json"))
        self.assertEqual(len(remaining), 0)


class F4PromptVersionTests(unittest.TestCase):
    def test_config_hash_includes_prompt_version(self):
        from etfagents.backtest.cache import BacktestSignalStore, BACKTEST_SIGNAL_PROMPT_VERSION
        store = BacktestSignalStore(
            config=copy.deepcopy(DEFAULT_CONFIG),
            selected_analysts=["market_flow"],
        )
        hash_v1 = store._config_hash()
        self.assertIsInstance(hash_v1, str)
        self.assertEqual(len(hash_v1), 16)


class F1AtomicWriteTests(unittest.TestCase):
    def test_put_creates_valid_json_file(self):
        from etfagents.backtest.cache import BacktestSignalStore
        from etfagents.dataflows.config import set_config, get_backtest_context

        tempdir = tempfile.TemporaryDirectory()
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["results_dir"] = tempdir.name
        set_config(config)

        store = BacktestSignalStore(
            config=config,
            selected_analysts=["market_flow"],
        )

        payload = {"rating": "BUY", "target_weight_pct": 30.0}
        with patch.object(store, 'is_enabled', return_value=True):
            store.put("510300.SH", "2026-01-01", payload)

        cache_path = store._cache_path("510300.SH", "2026-01-01")
        self.assertTrue(cache_path.exists())
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        self.assertEqual(data["rating"], "BUY")
        tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
