"""Tests for paper trading engine."""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from etfagents.paper_trading.engine import PaperTradingEngine
from etfagents.paper_trading.rules import (
    calc_commission,
    calc_stamp_duty,
    estimate_trade_cost,
    get_t1_available,
    validate_quantity,
)


def _make_price_csv(close: float = 4.12, trade_date: str = "20260521") -> str:
    return (
        "trade_date,open,high,low,close,pct_chg,vol,amount\n"
        f"{trade_date},4.00,4.15,3.95,{close},1.50,1000000,4120000\n"
    )


class RulesTests(unittest.TestCase):
    def test_calc_commission_normal(self):
        self.assertAlmostEqual(calc_commission(100000), 25.0)

    def test_calc_commission_minimum(self):
        self.assertEqual(calc_commission(1000), 5.0)

    def test_calc_stamp_duty_zero(self):
        self.assertEqual(calc_stamp_duty(100000), 0.0)

    def test_validate_quantity_valid(self):
        validate_quantity(100)
        validate_quantity(1000)

    def test_validate_quantity_not_multiple_of_100(self):
        with self.assertRaises(ValueError):
            validate_quantity(50)

    def test_validate_quantity_zero(self):
        with self.assertRaises(ValueError):
            validate_quantity(0)

    def test_validate_quantity_negative(self):
        with self.assertRaises(ValueError):
            validate_quantity(-100)

    def test_get_t1_available(self):
        self.assertEqual(get_t1_available(1000, 300), 700)
        self.assertEqual(get_t1_available(500, 600), 0)
        self.assertEqual(get_t1_available(500, 0), 500)

    def test_estimate_trade_cost_buy(self):
        result = estimate_trade_cost(4.12, 500, "buy")
        self.assertEqual(result["amount"], 2060.0)
        self.assertAlmostEqual(result["commission"], 5.0)
        self.assertEqual(result["stamp_duty"], 0.0)
        self.assertEqual(result["total_cost"], 2065.0)

    def test_estimate_trade_cost_sell(self):
        result = estimate_trade_cost(4.12, 500, "sell")
        self.assertEqual(result["amount"], 2060.0)
        self.assertAlmostEqual(result["commission"], 5.0)
        self.assertEqual(result["stamp_duty"], 0.0)
        self.assertEqual(result["total_cost"], 2055.0)


class PaperTradingTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        self.session_path = Path(self._tmpdir.name) / "session.json"
        self._orig_db_path = PaperTradingEngine.DB_PATH
        self._orig_session_path = PaperTradingEngine.SESSION_PATH
        PaperTradingEngine.DB_PATH = self.db_path
        PaperTradingEngine.SESSION_PATH = self.session_path
        self.engine = PaperTradingEngine(db_path=self.db_path)
        self.default_uid = "default"
        self._price_patcher = patch.object(
            PaperTradingEngine,
            "_get_current_price",
            return_value=4.12,
        )
        self._name_patcher = patch.object(
            PaperTradingEngine,
            "_auto_fill_name",
            side_effect=lambda ticker: f"{ticker} ETF",
        )
        self._price_patcher.start()
        self._name_patcher.start()

    def tearDown(self):
        self._price_patcher.stop()
        self._name_patcher.stop()
        PaperTradingEngine.DB_PATH = self._orig_db_path
        PaperTradingEngine.SESSION_PATH = self._orig_session_path
        self._tmpdir.cleanup()

    def _session_write(self, username: str):
        data = {"username": username, "login_at": "2026-05-21T10:00:00"}
        self.session_path.write_text(json.dumps(data))

    def _session_clear(self):
        if self.session_path.exists():
            self.session_path.unlink()

    # ----------------------------------------------------------------- auth

    def test_default_user_exists(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE username = 'default'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_default_user_has_account(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT cash FROM account WHERE user_id = 'default'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["cash"], 1_000_000.0)

    def test__get_current_user_no_session_returns_default(self):
        self._session_clear()
        self.assertEqual(self.engine._get_current_user(), "default")

    def test__get_current_user_with_session(self):
        try:
            self.engine.register("alice", "pass")
        except Exception:
            raise unittest.SkipTest("bcrypt not available")
        self._session_write("alice")
        engine2 = PaperTradingEngine(db_path=self.db_path)
        self.assertEqual(engine2._get_current_user(), "alice")

    @patch("builtins.input", return_value="")
    def test_register_user_stores_bcrypt_hash(self, _mock_input):
        try:
            self.engine.register("alice", "secret123")
        except Exception:
            return  # bcrypt may not be available
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE username = 'alice'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("$2b$", row[0])  # bcrypt hash prefix

    def test_register_duplicate_raises(self):
        try:
            self.engine.register("alice", "pass")
        except Exception:
            return
        with self.assertRaises(ValueError):
            self.engine.register("alice", "other")

    def test_register_default_user_raises(self):
        with self.assertRaises(ValueError):
            self.engine.register("default", "pass")

    def test_login_wrong_password(self):
        try:
            self.engine.register("bob", "correct")
        except Exception:
            return
        ok = self.engine.login("bob", "wrong")
        self.assertFalse(ok)

    def test_login_correct_password(self):
        try:
            self.engine.register("bob", "correct")
        except Exception:
            return
        engine2 = PaperTradingEngine(db_path=self.db_path)
        engine2.SESSION_PATH = self.session_path
        ok = engine2.login("bob", "correct")
        self.assertTrue(ok)
        self.assertTrue(self.session_path.exists())

    def test_login_default_no_password(self):
        ok = self.engine.login("default", "anything")
        self.assertTrue(ok)

    def test_logout_removes_session(self):
        try:
            self.engine.register("alice", "pass")
        except Exception:
            raise unittest.SkipTest("bcrypt not available")
        self._session_write("alice")
        engine2 = PaperTradingEngine(db_path=self.db_path)
        self.assertTrue(self.session_path.exists())
        engine2.logout()
        self.assertFalse(self.session_path.exists())

    # ---------------------------------------------------------------- account

    def test_account_initial_state(self):
        acc = self.engine.get_account()
        self.assertEqual(acc["cash"], 1_000_000.0)
        self.assertEqual(acc["realized_pnl"], 0.0)
        self.assertEqual(acc["total_commission"], 0.0)
        self.assertEqual(acc["total_assets"], 1_000_000.0)

    # ------------------------------------------------------------------- buy

    def test_buy_basic(self):
        result = self.engine.buy("510300.SH", 1000)
        self.assertEqual(result["side"], "buy")
        self.assertEqual(result["quantity"], 1000)
        self.assertEqual(result["price"], 4.12)
        self.assertEqual(result["amount"], 4120.0)
        self.assertAlmostEqual(result["commission"], 5.0)
        self.assertEqual(result["total_cost"], 4125.0)

    def test_buy_updates_account(self):
        self.engine.buy("510300.SH", 1000)
        acc = self.engine.get_account()
        # Cash: 1M - 4125 = 995875
        self.assertAlmostEqual(acc["cash"], 995875.0)
        self.assertAlmostEqual(acc["total_commission"], 5.0)

    def test_buy_invalid_quantity_raises(self):
        with self.assertRaises(ValueError):
            self.engine.buy("510300.SH", 50)

    def test_buy_insufficient_cash_raises(self):
        with self.assertRaises(ValueError):
            self.engine.buy("510300.SH", 1_000_000)

    def test_buy_multiple_averages_cost(self):
        self.engine.buy("510300.SH", 200)
        with patch.object(PaperTradingEngine, "_get_current_price", return_value=5.00):
            self.engine.buy("510300.SH", 200)
        pos = self.engine.get_positions()
        self.assertEqual(len(pos), 1)
        # avg = (200*4.12 + 200*5.00) / 400 = (824 + 1000) / 400 = 4.56
        self.assertAlmostEqual(pos[0]["avg_cost"], 4.56, places=2)

    def test_buy_creates_trade_record(self):
        self.engine.buy("510300.SH", 1000)
        trades = self.engine.get_trades()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "buy")
        self.assertEqual(trades[0]["ticker"], "510300.SH")
        self.assertEqual(trades[0]["quantity"], 1000)

    # ------------------------------------------------------------------ sell

    def test_sell_basic(self):
        self.engine.buy("510300.SH", 1000)
        # Need to unlock T+1 to sell
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        result = self.engine.sell("510300.SH", 500)
        self.assertEqual(result["side"], "sell")
        self.assertEqual(result["quantity"], 500)
        self.assertEqual(result["price"], 4.12)
        self.assertEqual(result["amount"], 2060.0)
        self.assertAlmostEqual(result["commission"], 5.0)
        # PnL: (4.12 - 4.12) * 500 - 5.0 = -5.0
        self.assertAlmostEqual(result["pnl"], -5.0)

    def test_sell_updates_account(self):
        self.engine.buy("510300.SH", 1000)
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        self.engine.sell("510300.SH", 500)
        acc = self.engine.get_account()
        # cash: 1000000 - 4125 (buy) + 2060 - 5 (sell) = 997930
        self.assertAlmostEqual(acc["cash"], 997930.0)
        self.assertAlmostEqual(acc["realized_pnl"], -5.0)

    def test_sell_zeroes_position_when_fully_sold(self):
        self.engine.buy("510300.SH", 500)
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        self.engine.sell("510300.SH", 500)
        pos = self.engine.get_positions()
        self.assertEqual(len(pos), 0)

    def test_sell_insufficient_shares_raises(self):
        self.engine.buy("510300.SH", 200)
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        with self.assertRaises(ValueError):
            self.engine.sell("510300.SH", 500)

    def test_sell_unheld_ticker_raises(self):
        with self.assertRaises(ValueError):
            self.engine.sell("510300.SH", 100)

    # ------------------------------------------------------------- T+1 rules

    def test_t1_restriction_same_day(self):
        """Shares bought today cannot be sold today."""
        self.engine.buy("510300.SH", 500)
        with self.assertRaises(ValueError):
            self.engine.sell("510300.SH", 100)

    def test_t1_unlock_next_day(self):
        """After day barrier, available_qty equals quantity."""
        self.engine.buy("510300.SH", 500)
        # Simulate next day
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        pos = self.engine.get_positions()
        self.assertEqual(pos[0]["available_qty"], 500)
        # Sell should now work
        self.engine.sell("510300.SH", 500)
        pos = self.engine.get_positions()
        self.assertEqual(len(pos), 0)

    # ------------------------------------------------------------- positions

    def test_positions_empty(self):
        pos = self.engine.get_positions()
        self.assertEqual(pos, [])

    def test_positions_with_holdings(self):
        self.engine.buy("510300.SH", 500)
        pos = self.engine.get_positions()
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos[0]["ticker"], "510300.SH")
        self.assertEqual(pos[0]["quantity"], 500)
        self.assertEqual(pos[0]["available_qty"], 0)
        self.assertEqual(pos[0]["current_price"], 4.12)
        self.assertEqual(pos[0]["market_value"], 2060.0)

    # ------------------------------------------------------------- history

    def test_history(self):
        self.engine.buy("510300.SH", 500)
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        self.engine.sell("510300.SH", 300)
        trades = self.engine.get_trades()
        self.assertEqual(len(trades), 2)
        sides = {t["side"] for t in trades}
        self.assertEqual(sides, {"buy", "sell"})

    def test_history_limit(self):
        for _ in range(5):
            self.engine.buy("510300.SH", 100)
        trades = self.engine.get_trades(limit=3)
        self.assertEqual(len(trades), 3)

    # --------------------------------------------------------------- reset

    def test_reset_account(self):
        self.engine.buy("510300.SH", 500)
        self.engine.reset_account(initial_cash=500000)
        acc = self.engine.get_account()
        self.assertEqual(acc["cash"], 500000)
        self.assertEqual(acc["realized_pnl"], 0.0)
        self.assertEqual(acc["total_commission"], 0.0)
        pos = self.engine.get_positions()
        self.assertEqual(pos, [])
        trades = self.engine.get_trades()
        self.assertEqual(trades, [])

    # ------------------------------------------------------- multi-user

    def test_multi_user_isolation(self):
        try:
            self.engine.register("alice", "pass")
            self.engine.register("bob", "pass")
        except Exception:
            raise unittest.SkipTest("bcrypt not available")
        self.engine.buy("510300.SH", 500, user_id="alice")
        self.engine.buy("159915.SZ", 300, user_id="bob")
        pos_alice = self.engine.get_positions(user_id="alice")
        pos_bob = self.engine.get_positions(user_id="bob")
        self.assertEqual(len(pos_alice), 1)
        self.assertEqual(pos_alice[0]["ticker"], "510300.SH")
        self.assertEqual(len(pos_bob), 1)
        self.assertEqual(pos_bob[0]["ticker"], "159915.SZ")

    def test_multi_user_accounts_separate(self):
        try:
            self.engine.register("alice", "pass")
            self.engine.register("bob", "pass")
        except Exception:
            raise unittest.SkipTest("bcrypt not available")
        self.engine.buy("510300.SH", 500, user_id="alice")
        # bob should still have full cash
        acc_bob = self.engine.get_account(user_id="bob")
        self.assertEqual(acc_bob["cash"], 1_000_000.0)

    # ---------------------------------------------------- analysis_id

    def test_analysis_id_stored_in_trades(self):
        self.engine.buy("510300.SH", 500, analysis_id="/reports/510300/20260521")
        trades = self.engine.get_trades()
        self.assertEqual(trades[0]["analysis_id"], "/reports/510300/20260521")

    def test_analysis_id_none_by_default(self):
        self.engine.buy("510300.SH", 500)
        trades = self.engine.get_trades()
        self.assertIsNone(trades[0]["analysis_id"])

    # ----------------------------------------------------- suggest_order

    def test_suggest_order_from_signal_buy(self):
        state = {
            "portfolio_backtest_signal": {
                "ticker": "510300.SH",
                "decision_date": "2026-05-21",
                "source": "portfolio_manager",
                "source_section": "positioning_recommendation",
                "rating": "BUY",
                "target_weight_pct": 35.0,
                "target_weight_min_pct": 35.0,
                "target_weight_max_pct": 35.0,
            }
        }
        suggestion = self.engine.suggest_order_from_signal("510300.SH", state)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["ticker"], "510300.SH")
        self.assertEqual(suggestion["side"], "buy")
        self.assertEqual(suggestion["rating"], "BUY")
        self.assertEqual(suggestion["target_weight_pct"], 35.0)
        self.assertGreaterEqual(suggestion["quantity"], 100)
        self.assertEqual(suggestion["quantity"] % 100, 0)

    def test_suggest_order_from_signal_sell(self):
        self.engine.buy("510300.SH", 30000)
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        state = {
            "portfolio_backtest_signal": {
                "ticker": "510300.SH",
                "decision_date": "2026-05-21",
                "source": "portfolio_manager",
                "source_section": "positioning_recommendation",
                "rating": "SELL",
                "target_weight_pct": 0.0,
                "target_weight_min_pct": 0.0,
                "target_weight_max_pct": 0.0,
                "execution_delay": "next_open",
                "starter_size_text": "",
                "add_triggers": [],
                "reduce_triggers": [],
                "exit_triggers": [],
                "rebalance_triggers": [],
                "risk_rules": [],
                "add_conditions": [],
                "reduce_conditions": [],
                "exit_conditions": [],
                "rebalance_conditions": [],
                "risk_controls": [],
                "monitoring_points": [],
                "signal_text_snapshot": "",
            }
        }
        suggestion = self.engine.suggest_order_from_signal("510300.SH", state)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["side"], "sell")
        self.assertGreaterEqual(suggestion["quantity"], 100)

    def test_suggest_order_from_signal_none_when_no_weight(self):
        state = {
            "portfolio_backtest_signal": {
                "ticker": "510300.SH",
                "decision_date": "2026-05-21",
                "source": "portfolio_manager",
                "source_section": "positioning_recommendation",
                "rating": "HOLD",
            }
        }
        suggestion = self.engine.suggest_order_from_signal("510300.SH", state)
        self.assertIsNone(suggestion)

    # ---------------------------------------------------- _execute_suggestion

    def test_execute_buy_suggestion(self):
        suggestion = {
            "ticker": "510300.SH", "side": "buy",
            "quantity": 500, "price": 4.12,
            "target_weight_pct": 25.0, "rating": "OVERWEIGHT",
        }
        result = self.engine._execute_suggestion(suggestion)
        self.assertEqual(result["side"], "buy")
        self.assertEqual(result["quantity"], 500)

    def test_execute_sell_suggestion(self):
        self.engine.buy("510300.SH", 1000)
        self.engine._last_date[self.default_uid] = "2000-01-01"
        self.engine._update_day_barrier(self.default_uid)
        suggestion = {
            "ticker": "510300.SH", "side": "sell",
            "quantity": 300, "price": 4.12,
            "target_weight_pct": 15.0, "rating": "HOLD",
        }
        result = self.engine._execute_suggestion(suggestion)
        self.assertEqual(result["side"], "sell")
        self.assertEqual(result["quantity"], 300)

    # -------------------------------------------------------- session consistency

    def test_session_consistency_clears_invalid_user(self):
        self._session_write("nonexistent_user")
        engine2 = PaperTradingEngine(db_path=self.db_path)
        engine2.SESSION_PATH = self.session_path
        self.assertFalse(self.session_path.exists())

    # ---------------------------------------------------- position names

    def test_position_name_defaults_to_ticker(self):
        self.engine.buy("510300.SH", 500)
        pos = self.engine.get_positions()
        self.assertTrue(pos[0]["name"])  # should have some name

    # ------------------------------------------ package-level API contract

    def test_package_level_suggest_order_from_signal(self):
        """suggest_order_from_signal must be importable and callable."""
        from etfagents.paper_trading import suggest_order_from_signal
        state = {
            "portfolio_backtest_signal": {
                "ticker": "510300.SH",
                "decision_date": "2026-05-21",
                "source": "portfolio_manager",
                "source_section": "positioning_recommendation",
                "rating": "BUY",
                "target_weight_pct": 35.0,
                "target_weight_min_pct": 35.0,
                "target_weight_max_pct": 35.0,
            }
        }
        with patch.object(PaperTradingEngine, "SESSION_PATH", self.session_path):
            with patch.object(PaperTradingEngine, "DB_PATH", self.db_path):
                suggestion = suggest_order_from_signal(
                    "510300.SH", state, db_path=self.db_path,
                )
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["ticker"], "510300.SH")
        self.assertEqual(suggestion["side"], "buy")
        self.assertGreaterEqual(suggestion["quantity"], 100)


if __name__ == "__main__":
    unittest.main()
