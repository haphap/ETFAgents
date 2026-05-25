
import importlib.util
import unittest
if not importlib.util.find_spec("langchain_core"):
    raise unittest.SkipTest("langchain_core not installed")

import copy
import unittest
from unittest.mock import MagicMock

from etfagents.agents.managers.portfolio_manager import create_portfolio_manager
from etfagents.agents.managers.research_manager import create_research_manager
from etfagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderProposal,
)
from etfagents.agents.trader.trader import create_trader
from etfagents.dataflows.config import set_config
from etfagents.default_config import DEFAULT_CONFIG

class _FakeResponse:
    def __init__(self, content):
        self.content = content

def _base_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-10",
        "past_context": "",
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "research_report": "",
        "stock_report": "",
        "investment_plan": "Research plan.",
        "trader_investment_plan": "Trader plan.",
        "investment_debate_state": {
            "history": "",
            "bear_history": "",
            "bull_history": "",
            "current_response": "",
            "current_bull_response": "",
            "current_bear_response": "",
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
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
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

class StructuredAgentTests(unittest.TestCase):
    def test_structured_agent_schemas_stay_prompt_sized(self):
        for schema in (ResearchPlan, TraderProposal, PortfolioDecision):
            self.assertLess(len(schema.model_fields), 20)

    def test_trader_renders_structured_output(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "English"
        set_config(cfg)
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = TraderProposal(
            thesis="Wait for confirmation before adding.",
            execution_plan="Enter in tranches above support.",
            risk_management="Reduce if support breaks.",
            rating=PortfolioRating.HOLD,
            target_weight_pct=22.5,
            execution_timing="next_open",
        )
        llm.with_structured_output.return_value = structured

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        self.assertIn("## ETF Allocation Thesis", result["trader_investment_plan"])
        self.assertIn("EXECUTION BIAS: **HOLD**", result["trader_investment_plan"])
        self.assertEqual(result["trader_backtest_signal"]["source"], "trader")
        self.assertEqual(result["trader_backtest_signal"]["rating"], "HOLD")
        self.assertEqual(result["trader_backtest_signal"]["weight_source"], "structured_field")
        self.assertEqual(result["trader_backtest_signal"]["target_weight_pct"], 22.5)

    def test_research_manager_renders_structured_output(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "English"
        set_config(cfg)
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("Side synthesis.")
        structured = MagicMock()
        structured.invoke.return_value = ResearchPlan(
            debate_conclusion="Bull evidence is stronger overall.",
            action_logic="Catalysts still need confirmation before sizing up.",
            positioning_recommendation="Maintain an overweight stance with staged adds.",
            rating=PortfolioRating.OVERWEIGHT,
            snapshot_stance="Overweight",
            snapshot_new_and_rebuttal="Added a clearer catalyst sequence and rebutted valuation-only objections.",
            snapshot_to_verify="Track orders, gross margin, and capex.",
        )
        llm.with_structured_output.return_value = structured

        result = create_research_manager(llm)(copy.deepcopy(_base_state()))

        self.assertIn("## Debate Conclusion", result["investment_plan"])
        self.assertIn("Research View: **Overweight**", result["investment_plan"])
        self.assertNotIn("FEEDBACK SNAPSHOT:", result["investment_plan"])
        self.assertNotIn("FEEDBACK SNAPSHOT:", result["investment_debate_state"]["judge_decision"])
        self.assertIn("Overweight", result["investment_debate_state"]["judge_snapshot"])

    def test_research_manager_uses_schema_only_prompt_for_structured_call(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("Side synthesis.")
        structured = MagicMock()
        structured.invoke.return_value = ResearchPlan(
            debate_conclusion="多方证据更强。",
            action_logic="当前应维持增持并观察确认。",
            positioning_recommendation="维持增持，分批执行并跟踪触发条件。",
            rating=PortfolioRating.OVERWEIGHT,
            snapshot_stance="增持",
            snapshot_new_and_rebuttal="补充了触发条件。",
            snapshot_to_verify="跟踪成交量和资金流。",
        )
        llm.with_structured_output.return_value = structured

        create_research_manager(llm)(copy.deepcopy(_base_state()))

        structured_prompt = structured.invoke.call_args.args[0]
        system_prompt = structured_prompt[0]["content"]
        self.assertIn("Structured-output mode", system_prompt)
        self.assertIn("ResearchPlan", system_prompt)
        self.assertIn("Do not write Markdown headings", system_prompt)
        self.assertNotIn("Use this exact output order with Markdown headings", system_prompt)
        self.assertIn("Use this exact output order with Markdown headings", structured_prompt[1]["content"])

    def test_trader_uses_schema_only_prompt_for_structured_call(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = TraderProposal(
            thesis="当前偏中性。",
            execution_plan="维持轻仓并等待确认。",
            risk_management="跌破支撑则减仓。",
            rating=PortfolioRating.HOLD,
        )
        llm.with_structured_output.return_value = structured

        create_trader(llm)(copy.deepcopy(_base_state()))

        structured_prompt = structured.invoke.call_args.args[0]
        self.assertEqual("system", structured_prompt[0]["role"])
        self.assertIn("Structured-output mode", structured_prompt[0]["content"])
        self.assertIn("TraderProposal", structured_prompt[0]["content"])
        self.assertIn("Do not write Markdown headings", structured_prompt[0]["content"])
        self.assertNotIn("Use exactly four top-level sections", structured_prompt[0]["content"])

    def test_portfolio_manager_uses_schema_only_prompt_for_structured_call(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("Risk synthesis.")
        structured = MagicMock()
        structured.invoke.return_value = PortfolioDecision(
            debate_conclusion="中性观点更稳健。",
            action_logic="当前维持持有并等待触发条件。",
            positioning_recommendation="维持持有，控制仓位并跟踪风险。",
            rating=PortfolioRating.HOLD,
            snapshot_stance="持有",
            snapshot_new_and_rebuttal="补充风险约束。",
            snapshot_to_verify="跟踪价格和资金流。",
        )
        llm.with_structured_output.return_value = structured

        create_portfolio_manager(llm)(copy.deepcopy(_base_state()))

        structured_prompt = structured.invoke.call_args.args[0]
        system_prompt = structured_prompt[0]["content"]
        self.assertIn("Structured-output mode", system_prompt)
        self.assertIn("PortfolioDecision", system_prompt)
        self.assertIn("Do not write Markdown headings", system_prompt)
        self.assertNotIn("Use this exact output order with Markdown headings", system_prompt)
        self.assertIn("Use this exact output order with Markdown headings", structured_prompt[1]["content"])

    def test_portfolio_manager_falls_back_to_freetext(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "English"
        set_config(cfg)
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "## Debate Conclusion\nBalanced view.\n\n"
            "## Action Logic\nWait for confirmation.\n\n"
            "## Positioning Recommendation\nKeep the position light.\n\n"
            "FINAL TRANSACTION PROPOSAL: **HOLD**\n\n"
            "FEEDBACK SNAPSHOT:\n"
            "- Stance: Hold\n"
            "- New this round & rebuttal: Added more cautious sizing.\n"
            "- To verify: Watch earnings."
        )

        result = create_portfolio_manager(llm)(copy.deepcopy(_base_state()))

        self.assertIn("FINAL TRANSACTION PROPOSAL: **HOLD**", result["final_trade_decision"])
        self.assertIn("FEEDBACK SNAPSHOT:", result["final_trade_decision"])
        self.assertEqual(result["portfolio_backtest_signal"]["source"], "portfolio_manager")
        self.assertEqual(result["backtest_signal"]["rating"], "HOLD")

    def test_trader_falls_back_when_structured_invoke_fails(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "English"
        set_config(cfg)
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.side_effect = ValueError("bad structured payload")
        llm.with_structured_output.return_value = structured
        llm.invoke.return_value = _FakeResponse(
            "## Trading Thesis\nFallback thesis.\n\n"
            "## Execution Plan\nWait.\n\n"
            "## Risk Management\nWatch support.\n\n"
            "FINAL TRANSACTION PROPOSAL: **HOLD**"
        )

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        self.assertIn("Fallback thesis.", result["trader_investment_plan"])
        self.assertIn("FINAL TRANSACTION PROPOSAL: **HOLD**", result["trader_investment_plan"])
        structured_prompt = structured.invoke.call_args.args[0]
        self.assertIn("Structured-output mode", structured_prompt[0]["content"])
        fallback_prompt = llm.invoke.call_args.args[0]
        self.assertIn("Use exactly four top-level sections", fallback_prompt[0]["content"])
        self.assertNotIn("Structured-output mode", fallback_prompt[0]["content"])

    def test_trader_freetext_demotes_h1_markdown_headings(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "English"
        set_config(cfg)
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "#Trading Thesis\nFallback thesis.\n\n"
            "#Execution Plan\nWait.\n\n"
            "## Risk Management\nWatch support.\n\n"
            "FINAL TRANSACTION PROPOSAL: **HOLD**"
        )

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        self.assertNotRegex(result["trader_investment_plan"], r"(?m)^#(?!#)\s")
        self.assertIn("## Trading Thesis", result["trader_investment_plan"])
        self.assertIn("## Execution Plan", result["trader_investment_plan"])
        self.assertIn("## Risk Management", result["trader_investment_plan"])

    def test_trader_chinese_freetext_restores_execution_bias_section(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "一、配置逻辑\n"
            "当前主线仍未被证伪，但执行必须等待量价确认。\n\n"
            "二、配置执行计划\n"
            "先维持现有底仓，只有价格重新站稳50日均线且成交量回到20日均量上方后才继续加仓。\n\n"
            "三、再平衡与风险控制\n"
            "若价格跌破关键支撑并放量，则先减仓；继续跟踪ETF份额、溢折价与资金流。执行倾向: 增持。"
        )

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        self.assertIn("四、执行倾向\n**增持**", result["trader_investment_plan"])
        self.assertNotIn("执行倾向: 增持", result["trader_investment_plan"])
        self.assertIn("三、再平衡与风险控制", result["trader_investment_plan"])

    def test_trader_freetext_fallback_prompt_is_prose_only(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "一、配置逻辑\n结论。\n\n二、配置执行计划\n计划。\n\n三、再平衡与风险控制\n风控。\n\n四、执行倾向\n**持有**"
        )

        create_trader(llm)(copy.deepcopy(_base_state()))

        fallback_prompt = llm.invoke.call_args.args[0]
        system_prompt = fallback_prompt[0]["content"]
        self.assertNotIn("populate the structured fields", system_prompt.lower())
        self.assertNotIn("target_weight_pct", system_prompt)
        self.assertNotIn("execution_timing", system_prompt)
        self.assertIn("Use exactly four top-level sections", system_prompt)
        self.assertIn("`一、配置逻辑`", system_prompt)
        self.assertNotIn("[一句话配置逻辑标题]", system_prompt)
        self.assertIn("四、执行倾向", system_prompt)

    def test_trader_chinese_freetext_uses_fixed_config_heading_and_rating_only(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "一、产业现金流拐点与长单锁价机制有效对冲宏观估值压制\n"
            "当前宏观实际利率高企与产业盈利底垫实质性夯实形成明确对冲，偏多逻辑更为完整。\n\n"
            "二、配置执行计划\n"
            "先维持现有底仓，只有价格重新站稳50日均线且成交量回到20日均量上方后才继续加仓。\n\n"
            "三、再平衡与风险控制\n"
            "若价格跌破关键支撑并放量，则先减仓；继续跟踪ETF份额、溢折价与资金流。\n\n"
            "四、执行倾向\n"
            "执行倾向: 增持"
        )

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        plan = result["trader_investment_plan"]
        self.assertIn(
            "一、配置逻辑\n产业现金流拐点与长单锁价机制有效对冲宏观估值压制\n\n当前宏观实际利率高企",
            plan,
        )
        self.assertNotIn("一、产业现金流拐点", plan)
        self.assertIn("四、执行倾向\n**增持**", plan)
        self.assertNotIn("执行倾向: 增持", plan)

    def test_portfolio_manager_freetext_fallback_prompt_is_prose_only(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "## 辩论结论\n结论。\n\n## 行为逻辑\n逻辑。\n\n## 持仓建议\n### （一）评级\n研究结论: **持有**\n### （二）建议\n维持当前仓位。\n\n反馈快照:\n- 立场: 持有\n- 本轮新增与反驳: 新增约束。\n- 待验证: 跟踪量价。"
        )

        create_portfolio_manager(llm)(copy.deepcopy(_base_state()))

        fallback_prompt = llm.invoke.call_args.args[0]
        self.assertNotIn("Populate the structured fields", fallback_prompt)
        self.assertNotIn("target_weight_pct", fallback_prompt)
        self.assertNotIn("execution_timing", fallback_prompt)
        self.assertIn("write only the visible report", fallback_prompt)
        self.assertIn("（一）评级", fallback_prompt)
        self.assertIn("（二）建议", fallback_prompt)

if __name__ == "__main__":
    unittest.main()
