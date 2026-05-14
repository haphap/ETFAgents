import copy
from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from etfagents.agents.analysts.etf_market_analyst import create_etf_market_analyst
from etfagents.agents.schemas import PortfolioRating, TraderProposal
from etfagents.agents.trader.trader import create_trader
from etfagents.agents.utils.analysis_memory import (
    AnalysisMemoryStore,
    MemoryContextBuilder,
    MethodPlaybookEntry,
    OutcomeLessonEntry,
    create_memory_writer,
)
from etfagents.dataflows.config import backtest_context, clear_backtest_context, set_config
from etfagents.default_config import DEFAULT_CONFIG
from etfagents.graph.trading_graph import TradingAgentsGraph


def _base_state():
    return {
        "asset_of_interest": "510300.SH",
        "company_of_interest": "510300.SH",
        "trade_date": "2026-01-10",
        "messages": [],
        "market_flow_report": "Price held the 50-day average and flows stayed constructive.",
        "catalyst_sentiment_report": "Policy headlines were supportive but still noisy.",
        "macro_regime_report": "Rates eased and the macro backdrop improved.",
        "meso_commodity_report": "Commodity pressure eased versus the prior month.",
        "holdings_industry_report": "Industry reports stayed constructive on earnings breadth.",
        "top_holdings_report": "Top holdings revisions improved and concentration risk stayed manageable.",
        "research_allocation_plan": "Maintain a constructive stance but wait for confirmation on flows.",
        "trader_allocation_plan": "Start with 20% and add on confirmation above support.",
        "final_allocation_decision": "## Positioning Recommendation\nMaintain an overweight stance with staged adds.\n\nFINAL TRANSACTION PROPOSAL: **BUY**",
        "backtest_signal": {
            "ticker": "510300.SH",
            "decision_date": "2026-01-10",
            "source": "portfolio_manager",
            "source_section": "positioning_recommendation",
            "rating": "BUY",
            "target_weight_pct": 25.0,
            "target_weight_min_pct": 20.0,
            "target_weight_max_pct": 30.0,
            "weight_source": "structured_field",
            "execution_delay": "next_open",
            "add_triggers": [{"metric": "close", "op": ">", "threshold": 10.0, "action": "add", "delta_pct": 5.0, "note": "Breakout"}],
            "reduce_triggers": [],
            "exit_triggers": [{"metric": "close", "op": "<", "threshold": 9.2, "action": "exit", "target_weight_pct": 0.0, "note": "Breakdown"}],
            "rebalance_triggers": [],
            "risk_rules": [{"metric": "pnl_pct", "op": "<", "threshold": -5.0, "action": "cap", "max_weight_pct": 10.0, "note": "Drawdown cap"}],
            "add_conditions": ["Add if closes above resistance with volume."],
            "reduce_conditions": [],
            "exit_conditions": ["Exit if support fails decisively."],
            "rebalance_conditions": [],
            "risk_controls": ["Cut exposure if drawdown breaches 5%."],
            "monitoring_points": ["Watch ETF share creation and breadth."],
            "signal_text_snapshot": "Maintain an overweight stance with staged adds.",
        },
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "current_bull_response": "Bull case: earnings breadth improved and flows stabilized.",
            "current_bear_response": "Bear case: valuation is still rich if flows fade.",
            "bull_snapshot": "",
            "bear_snapshot": "",
            "bull_snapshot_path": "",
            "bear_snapshot_path": "",
            "debate_brief": "",
            "latest_speaker": "",
            "judge_decision": "",
            "judge_snapshot": "",
            "judge_snapshot_path": "",
            "count": 1,
        },
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "",
            "current_aggressive_response": "Aggressive: momentum can carry further if flows stay positive.",
            "current_conservative_response": "Conservative: keep sizing capped until support is retested.",
            "current_neutral_response": "Neutral: wait for confirmation before adding risk.",
            "aggressive_snapshot": "",
            "conservative_snapshot": "",
            "neutral_snapshot": "",
            "aggressive_snapshot_path": "",
            "conservative_snapshot_path": "",
            "neutral_snapshot_path": "",
            "debate_brief": "",
            "judge_decision": "",
            "judge_snapshot": "",
            "judge_snapshot_path": "",
            "count": 1,
        },
    }


class AnalysisMemoryFlowTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(DEFAULT_CONFIG)
        clear_backtest_context()

    def tearDown(self):
        set_config(copy.deepcopy(self.original_config))
        clear_backtest_context()

    def _make_config(self, results_dir: str):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["results_dir"] = results_dir
        cfg["output_language"] = "English"
        cfg["memory_mode"] = "full"
        return cfg

    def test_memory_writer_persists_analysis_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])

            node = create_memory_writer(store, config=cfg, selected_analysts=["market_flow"])
            result = node(_base_state())

            self.assertIn("analysis_memory_entry", result)
            entries = store.load_analysis_entries("510300.SH")
            self.assertEqual(1, len(entries))
            self.assertEqual("BUY", entries[0].signal["rating"])
            self.assertEqual("pending", entries[0].outcome_status)

    def test_context_builder_uses_latest_analysis_and_hides_rating_for_analyst(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            create_memory_writer(store, config=cfg, selected_analysts=["market_flow"])(_base_state())

            bundle = MemoryContextBuilder(store, cfg, ["market_flow"]).build("510300.SH", "2026-01-15")

            self.assertIn("Latest same-ticker thesis", bundle.continuity_context["market_flow"])
            self.assertNotIn("BUY", bundle.continuity_context["market_flow"])
            self.assertIn("Last stance", bundle.continuity_context["portfolio_manager"])
            self.assertIn("BUY", bundle.continuity_context["portfolio_manager"])

    def test_context_builder_disables_memory_in_backtest_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            create_memory_writer(store, config=cfg, selected_analysts=["market_flow"])(_base_state())

            with backtest_context("2026-01-15"):
                bundle = MemoryContextBuilder(store, cfg, ["market_flow"]).build("510300.SH", "2026-01-15")

            self.assertEqual("", bundle.continuity_context["market_flow"])
            self.assertEqual("", bundle.lesson_context["portfolio_manager"])
            self.assertEqual("", bundle.method_context["trader"])

    def test_resolve_analysis_outcomes_creates_lessons_and_draft_playbook(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            create_memory_writer(store, config=cfg, selected_analysts=["market_flow"])(_base_state())

            graph = object.__new__(TradingAgentsGraph)
            graph.analysis_memory_store = store
            graph.reflector = MagicMock()
            graph.reflector.reflect_on_final_decision.return_value = "The confirmation signal mattered; keep invalidation levels explicit next time."
            graph._fetch_returns = lambda ticker, trade_date: (0.05, 0.03, 5)

            graph._resolve_analysis_memory_outcomes("510300.SH")

            outcomes = store.load_outcome_entries("510300.SH")
            self.assertEqual(1, len(outcomes))
            self.assertEqual("confirmed_correct", outcomes[0].outcome_status)
            updated_entry = store.load_analysis_entries("510300.SH")[0]
            self.assertEqual("confirmed_correct", updated_entry.outcome_status)
            drafts = store.load_playbook_entries()
            self.assertEqual(1, len(drafts))
            self.assertEqual("draft", drafts[0].status)
            self.assertEqual([], store.get_active_playbook_entries("trader", "510300.SH", "2026-12-20"))

            promoted = store.promote_playbook(drafts[0].id, expires_days=30)
            active_cutoff = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
            playbooks = store.get_active_playbook_entries("trader", "510300.SH", active_cutoff)
            self.assertTrue(playbooks)
            self.assertEqual(promoted.id, playbooks[-1].id)
            self.assertIn("confirmation signal mattered", playbooks[-1].rule)

    def test_recent_lessons_respect_created_at_clamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            cfg["memory_in_backtest"] = True
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            store.append_outcome(
                OutcomeLessonEntry(
                    id="late-lesson",
                    ticker="510300.SH",
                    trade_date="2026-01-10",
                    created_at="2026-04-15T00:00:00Z",
                    source_analysis_id="analysis-1",
                    raw_return=0.03,
                    alpha_return=0.01,
                    holding_days=5,
                    outcome_status="confirmed_correct",
                    lesson_summary="This lesson was only known later.",
                )
            )

            with backtest_context("2026-02-01"):
                lessons = store.get_recent_lessons("510300.SH", "2026-02-01")

            self.assertEqual([], lessons)

    def test_continuity_filters_out_entries_older_than_max_age(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            cfg["continuity_max_age_days"] = 30
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            state = _base_state()
            state["trade_date"] = "2026-01-01"
            create_memory_writer(store, config=cfg, selected_analysts=["market_flow"])(state)

            bundle = MemoryContextBuilder(store, cfg, ["market_flow"]).build("510300.SH", "2026-02-15")

            self.assertEqual("", bundle.continuity_context["market_flow"])

    def test_active_playbooks_ignore_expired_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            store.append_playbook(
                MethodPlaybookEntry(
                    id="expired-rule",
                    role="all",
                    ticker="510300.SH",
                    created_at="2026-01-01T00:00:00Z",
                    source_lesson_id="lesson-1",
                    rule="Old rule.",
                    status="active",
                    expires_at="2026-02-01",
                )
            )

            active = store.get_active_playbook_entries("trader", "510300.SH", "2026-03-10")

            self.assertEqual([], active)

    def test_analysis_entry_update_rewrites_in_place_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            store = AnalysisMemoryStore(cfg, ["market_flow"])
            node = create_memory_writer(store, config=cfg, selected_analysts=["market_flow"])
            node(_base_state())

            entry = store.load_analysis_entries("510300.SH")[0]
            entry.outcome_status = "confirmed_correct"
            store.append_analysis(entry)

            entries = store.load_analysis_entries("510300.SH")
            self.assertEqual(1, len(entries))
            self.assertEqual("confirmed_correct", entries[0].outcome_status)

    def test_trader_prompt_includes_memory_contexts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            llm = MagicMock()
            structured = MagicMock()
            structured.invoke.return_value = TraderProposal(
                thesis="Stay patient.",
                execution_plan="Add on confirmation.",
                risk_management="Reduce if support breaks.",
                rating=PortfolioRating.HOLD,
            )
            llm.with_structured_output.return_value = structured

            state = _base_state()
            state["continuity_context"] = {"trader": "Latest same-ticker execution snapshot (2026-01-10): start small."}
            state["lesson_context"] = {"trader": "[2026-01-10 | confirmed_correct | raw +5.0% | alpha +3.0%] Confirmation mattered."}
            state["method_context"] = {"trader": "[all/510300.SH] Keep invalidation levels explicit."}

            create_trader(llm)(state)
            prompt = str(structured.invoke.call_args[0][0])

            self.assertIn("Latest same-ticker execution snapshot", prompt)
            self.assertIn("Confirmation mattered.", prompt)
            self.assertIn("Keep invalidation levels explicit.", prompt)

    def test_etf_market_prompt_includes_memory_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self._make_config(tmpdir)
            set_config(cfg)
            llm = MagicMock()
            state = _base_state()
            state["continuity_context"] = {"market_flow": "Latest same-ticker thesis (2026-01-10): flows held up."}
            state["method_context"] = {"market_flow": "[all/510300.SH] Avoid vague confirmation language."}

            with patch("etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain") as mocked:
                mocked.return_value = (AIMessage(content="report"), "report")
                create_etf_market_analyst(llm)(state)
                system_message = mocked.call_args.kwargs["system_message"]

            self.assertIn("Latest same-ticker thesis", system_message)
            self.assertIn("Avoid vague confirmation language.", system_message)


if __name__ == "__main__":
    unittest.main()
