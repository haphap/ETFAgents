"""Integration test for the ``etfagents.bridge`` JSON-RPC sidecar.

The test deliberately drives the bridge as an external subprocess and never
imports ``etfagents`` directly — this proves the bridge is usable as an opaque
black box from another runtime (the future TypeScript CLI).

Tests that need real vendor data (tushare/qlib/yfinance) are skipped: those
belong in vendor-specific suites. Here we only validate protocol shape,
parameter routing, and error mapping.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")


class BridgeProtocolTests(unittest.TestCase):
    """Spawn one bridge process per test for hermetic state."""

    def setUp(self) -> None:
        # Isolate cache/results/paper state to a tempdir so tests don't touch
        # the developer's ~/.etfagents.
        self._tmp = tempfile.TemporaryDirectory()
        self._cache_dir = Path(self._tmp.name) / "cache"
        self._results_dir = Path(self._tmp.name) / "results"
        self._cache_dir.mkdir()
        self._results_dir.mkdir()
        self._paper_db = Path(self._tmp.name) / "paper_trading.db"

        env = {
            **os.environ,
            "ETFAGENTS_CACHE_DIR": str(self._cache_dir),
            "ETFAGENTS_RESULTS_DIR": str(self._results_dir),
            "PYTHONUNBUFFERED": "1",
        }
        self._proc = subprocess.Popen(
            [PYTHON, "-m", "etfagents.bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=env,
            text=True,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=2)
        finally:
            for stream in (self._proc.stdout, self._proc.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
            self._tmp.cleanup()

    # ------------------------------------------------------------ helpers

    def call(self, method: str, params: dict | None = None, *, req_id: int = 1) -> dict:
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if not line:
            stderr = ""
            if self._proc.stderr:
                stderr = self._proc.stderr.read()
            self.fail(f"Bridge closed stdout unexpectedly. stderr:\n{stderr}")
        return json.loads(line)

    def call_ok(self, method: str, params: dict | None = None, *, req_id: int = 1) -> object:
        response = self.call(method, params, req_id=req_id)
        self.assertNotIn(
            "error",
            response,
            msg=f"Expected success but got error: {response.get('error')}",
        )
        return response["result"]

    def call_err(self, method: str, params: dict | None = None, *, req_id: int = 1) -> dict:
        response = self.call(method, params, req_id=req_id)
        self.assertIn(
            "error",
            response,
            msg=f"Expected error but got result: {response.get('result')}",
        )
        return response["error"]

    # ------------------------------------------------------- tools.* tests

    def test_tools_list_returns_metadata_for_each_at_tool(self) -> None:
        """tools.list must surface every @tool with name/description/schema.

        This is the contract the TS LangGraph.js side relies on to construct
        ``DynamicStructuredTool`` instances.
        """
        tools = self.call_ok("tools.list", {})
        self.assertIsInstance(tools, list)
        self.assertGreaterEqual(len(tools), 20, "expected ~22 @tool functions")
        names = {t["name"] for t in tools}
        # Spot-check a representative tool from each module
        self.assertIn("get_stock_data", names)
        self.assertIn("get_indicators", names)
        self.assertIn("get_news", names)
        self.assertIn("get_etf_price_data", names)
        self.assertIn("get_broker_research", names)
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("args_schema", tool)
            schema = tool["args_schema"]
            self.assertEqual(schema.get("type"), "object")
            self.assertIn("properties", schema)

    def test_tools_call_unknown_name_returns_method_not_found(self) -> None:
        err = self.call_err("tools.call", {"name": "nonexistent_tool", "args": {}})
        self.assertEqual(err["code"], -32601)

    def test_tools_call_invalid_params_returns_invalid_params(self) -> None:
        err = self.call_err("tools.call", {"args": {}})  # missing 'name'
        self.assertEqual(err["code"], -32602)

    def test_tools_call_in_backtest_mode_blocks_unbounded_news_call(self) -> None:
        """Backtest-mode date-bounds clamp must reject ``get_news`` (no end_date here).

        This proves the bridge wires the existing ``backtest_context`` correctly
        without modifying any production code.
        """
        err = self.call_err(
            "tools.call",
            {
                "name": "get_news",
                "args": {
                    "ticker": "510300.SH",
                    "start_date": "2020-01-01",
                    "end_date": "2020-12-31",
                },
                "context": {"mode": "backtest", "as_of_date": "2020-06-01"},
            },
        )
        # Either TOOL_EXECUTION_ERROR (the RuntimeError from _apply_backtest_date_bounds)
        # or DATA_VENDOR_UNAVAILABLE if the vendor short-circuits earlier.
        self.assertIn(err["code"], (-32001, -32003))
        self.assertIn("Backtest mode", err["message"])

    # ------------------------------------------------------- config.* tests

    def test_config_default_get_set_round_trip(self) -> None:
        default = self.call_ok("config.default", {})
        self.assertIsInstance(default, dict)
        self.assertIn("data_vendors", default)
        self.assertIn("tool_vendors", default)

        # Modify a key and push back
        modified = dict(default)
        modified["max_debate_rounds"] = 3
        applied = self.call_ok("config.set", {"config": modified})
        self.assertEqual(applied["max_debate_rounds"], 3)

        # config.get must reflect the change in this process
        live = self.call_ok("config.get", {})
        self.assertEqual(live["max_debate_rounds"], 3)

    def test_config_set_rejects_non_object(self) -> None:
        err = self.call_err("config.set", {"config": "not an object"})
        self.assertEqual(err["code"], -32602)

    # -------------------------------------------------------- cache.* tests

    def test_cache_stats_returns_per_category_breakdown(self) -> None:
        stats = self.call_ok("cache.stats", {})
        self.assertIsInstance(stats, dict)
        for category in ("api", "signals", "snapshots", "checkpoints"):
            self.assertIn(category, stats)
            self.assertIn("count", stats[category])
            self.assertIn("size_mb", stats[category])
        self.assertIn("total_mb", stats)

    def test_cache_cleanup_rejects_invalid_category(self) -> None:
        err = self.call_err("cache.cleanup", {"days": 30, "category": "bogus"})
        self.assertEqual(err["code"], -32602)

    # ----------------------------------------------------- paper.* tests

    def _paper_params(self, **extra) -> dict:
        return {"db_path": str(self._paper_db), **extra}

    def test_paper_default_user_flow(self) -> None:
        """A fresh tempdir paper db should expose a 'default' user account."""
        user = self.call_ok("paper.current_user", self._paper_params())
        self.assertEqual(user["user"], "default")
        account = self.call_ok("paper.get_account", self._paper_params())
        for key in ("user_id", "cash", "market_value", "total_assets"):
            self.assertIn(key, account)
        self.assertEqual(account["user_id"], "default")

        positions = self.call_ok("paper.get_positions", self._paper_params())
        self.assertEqual(positions, [])

        trades = self.call_ok("paper.get_trades", self._paper_params(limit=10))
        self.assertEqual(trades, [])

    def test_paper_buy_validates_lot_size(self) -> None:
        """A-share lot size is 100 — non-multiples must be rejected."""
        err = self.call_err(
            "paper.buy",
            self._paper_params(ticker="510300.SH", quantity=50),
        )
        self.assertEqual(err["code"], -32020)
        self.assertIn("multiple of 100", err["message"])

    def test_paper_suggest_order_rejects_non_object_state(self) -> None:
        err = self.call_err(
            "paper.suggest_order_from_signal",
            self._paper_params(ticker="510300.SH", state="not-a-dict"),
        )
        self.assertEqual(err["code"], -32602)

    # -------------------------------------------------- backtest.* tests

    def test_backtest_requires_tickers_and_signals(self) -> None:
        err = self.call_err(
            "backtest.run_candidate_pool",
            {"start_date": "2026-01-02", "end_date": "2026-01-31", "signals": {}},
        )
        self.assertEqual(err["code"], -32602)
        self.assertIn("tickers", err["message"])

        err = self.call_err(
            "backtest.run_candidate_pool",
            {
                "tickers": ["510300.SH"],
                "start_date": "2026-01-02",
                "end_date": "2026-01-31",
            },
        )
        self.assertEqual(err["code"], -32602)
        self.assertIn("signals", err["message"])

    # ------------------------------------------------- protocol-level

    def test_unknown_method_returns_method_not_found(self) -> None:
        err = self.call_err("does.not.exist", {})
        self.assertEqual(err["code"], -32601)

    def test_parse_error_does_not_kill_server(self) -> None:
        """Garbage input should produce a parse-error response, not crash the loop.

        Why this matters: the future TS client may send malformed JSON during
        development — the bridge must stay alive so the next valid request
        succeeds.
        """
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.write("this is not json\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        response = json.loads(line)
        self.assertEqual(response["error"]["code"], -32700)

        # Subsequent valid request still works
        result = self.call_ok("config.get", {}, req_id=99)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    sys.exit(unittest.main())
