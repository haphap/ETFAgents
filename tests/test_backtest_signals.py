import unittest

from etfagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    RiskRule,
    TraderProposal,
    Trigger,
)
from etfagents.backtest.signals import (
    build_candidate_backtest_signal,
    build_portfolio_backtest_signal,
    build_state_backtest_signal,
    build_trader_backtest_signal,
)


class BacktestSignalTests(unittest.TestCase):
    def test_trader_signal_uses_execution_advice_before_rating_map(self):
        signal = build_trader_backtest_signal(
            "510300.SH",
            "2026-01-15",
            "",
            TraderProposal(
                thesis="当前多空因素并存。",
                execution_plan=(
                    "目标仓位先控制在20%至25%，若价格重新站稳50日均线且成交量回到20日均量上方，"
                    "再分两次加仓。"
                ),
                risk_management="若跌破关键支撑并放量，则先减仓；继续跟踪份额变化与资金流。",
                rating=PortfolioRating.HOLD,
                target_weight_band=(20.0, 25.0),
                execution_timing="next_close",
                add_triggers=[
                    Trigger(
                        metric="close",
                        op=">",
                        threshold=2.08,
                        action="add",
                        delta_pct=5.0,
                        note="突破关键价格后加仓",
                    )
                ],
                risk_controls=[
                    RiskRule(
                        metric="pnl_pct",
                        op=">",
                        threshold=8.0,
                        action="cap",
                        max_weight_pct=25.0,
                        note="浮盈过高时封顶",
                    )
                ],
            ),
        )

        self.assertEqual(signal["rating"], "HOLD")
        self.assertEqual(signal["weight_source"], "structured_field")
        self.assertAlmostEqual(signal["target_weight_pct"], 22.5)
        self.assertEqual(signal["execution_delay"], "next_close")
        self.assertEqual(signal["add_triggers"][0]["metric"], "close")
        self.assertEqual(signal["risk_rules"][0]["action"], "cap")
        self.assertIn("再分两次加仓", "\n".join(signal["add_conditions"]))
        self.assertIn("先减仓", "\n".join(signal["reduce_conditions"]))
        self.assertIn("继续跟踪份额变化与资金流", "\n".join(signal["monitoring_points"]))

    def test_portfolio_signal_extracts_last_step_action_advice(self):
        signal = build_portfolio_backtest_signal(
            "516160.SH",
            "2026-02-10",
            "",
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥。",
                action_logic="若关键位失守则执行减仓，并按周度再平衡复核。",
                positioning_recommendation=(
                    "目标仓位先维持在15%至20%，若价格重新站稳50日均线且成交量回到20日均量上方，"
                    "再考虑上调一个档位；若跌破2.08元支撑位则强制降仓。"
                ),
                rating=PortfolioRating.HOLD,
                target_weight_pct=18.0,
                execution_timing="same_close",
                rebalance_triggers=[
                    Trigger(
                        metric="sma_20",
                        op="<",
                        threshold=2.05,
                        action="rebalance",
                        target_weight_pct=12.0,
                        note="跌破中期均线则回到低配",
                    )
                ],
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了仓位上限与风险约束。",
                snapshot_to_verify="继续跟踪均线、成交量和份额变化。",
            ),
        )

        self.assertEqual(signal["source"], "portfolio_manager")
        self.assertEqual(signal["weight_source"], "structured_field")
        self.assertAlmostEqual(signal["target_weight_pct"], 18.0)
        self.assertEqual(signal["execution_delay"], "same_close")
        self.assertEqual(signal["rebalance_triggers"][0]["action"], "rebalance")
        self.assertIn("上调一个档位", "\n".join(signal["add_conditions"]))
        self.assertIn("强制降仓", "\n".join(signal["reduce_conditions"]))
        self.assertIn("按周度再平衡复核", "\n".join(signal["rebalance_conditions"]))

    def test_state_signal_falls_back_to_rendered_report(self):
        state = {
            "asset_of_interest": "159915.SZ",
            "trade_date": "2026-03-01",
            "final_allocation_decision": (
                "## 辩论结论\n略。\n\n"
                "## 行为逻辑\n若跌破关键支撑则减仓，并持续跟踪资金流。\n\n"
                "## 持仓建议\n"
                "### （一）评级\n研究结论: **增持**\n\n"
                "### （二）建议\n目标仓位先控制在20%至25%，若放量突破则继续加仓。"
            ),
        }

        signal = build_state_backtest_signal(state)

        self.assertEqual(signal["rating"], "OVERWEIGHT")
        self.assertEqual(signal["weight_source"], "parsed_target_range")
        self.assertAlmostEqual(signal["target_weight_pct"], 22.5)
        self.assertIn("继续加仓", "\n".join(signal["add_conditions"]))

    def test_candidate_signal_overrides_weight_with_candidate_pool_weight(self):
        signal = build_candidate_backtest_signal(
            {
                "ticker": "159915.SZ",
                "rating": "BUY",
                "suggested_weight_pct": 50.0,
                "backtest_signal": {
                    "source": "portfolio_manager",
                    "source_section": "positioning_recommendation",
                    "rating": "BUY",
                    "target_weight_pct": 22.5,
                    "target_weight_min_pct": 20.0,
                    "target_weight_max_pct": 25.0,
                    "weight_source": "parsed_target_range",
                    "execution_delay": "next_open",
                    "starter_size_text": "",
                    "add_triggers": [
                        {
                            "metric": "close",
                            "op": ">",
                            "threshold": 2.1,
                            "action": "add",
                            "delta_pct": 5.0,
                            "target_weight_pct": None,
                            "note": "突破后加仓",
                        }
                    ],
                    "reduce_triggers": [],
                    "exit_triggers": [],
                    "rebalance_triggers": [],
                    "risk_rules": [],
                    "add_conditions": ["若放量突破则继续加仓。"],
                    "reduce_conditions": [],
                    "exit_conditions": [],
                    "rebalance_conditions": [],
                    "risk_controls": [],
                    "monitoring_points": [],
                    "signal_text_snapshot": "原始建议。",
                },
            },
            "2026-04-01",
        )

        self.assertEqual(signal["source"], "candidate_pool")
        self.assertEqual(signal["weight_source"], "candidate_pool")
        self.assertEqual(signal["target_weight_pct"], 50.0)
        self.assertEqual(signal["target_weight_min_pct"], 50.0)
        self.assertEqual(signal["target_weight_max_pct"], 50.0)
        self.assertEqual(signal["add_triggers"][0]["action"], "add")
        self.assertIn("若放量突破则继续加仓。", signal["add_conditions"])


if __name__ == "__main__":
    unittest.main()
