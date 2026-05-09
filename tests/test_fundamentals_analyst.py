import copy
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from etfagents.dataflows.config import get_config, set_config
from etfagents.default_config import DEFAULT_CONFIG


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _CapturingLLM:
    def __init__(self, final_content):
        self.final_content = final_content
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return _FakeResponse(self.final_content)


class _FakeTool:
    def __init__(self, name, response):
        self.name = name
        self.response = response
        self.calls = []

    def invoke(self, args):
        self.calls.append(args)
        return self.response


class FundamentalsAnalystTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

    def tearDown(self):
        set_config(self.original_config)

    def test_fundamentals_analyst_backfills_missing_statements_before_final_report(self):
        llm = _CapturingLLM(
            "# 完整基本面报告\n\n已覆盖资产负债表、利润表、现金流、ROE、毛利率、净利率、资产负债率、自由现金流和增长。"
        )
        node = create_fundamentals_analyst(llm)

        partial_result = AIMessage(content="只给出笼统基本面结论。")
        state = {
            "company_of_interest": "300750.SZ",
            "trade_date": "2026-04-07",
            "messages": [
                HumanMessage(content="请分析 300750.SZ 的财报和基本面"),
                AIMessage(content="# Tushare fundamentals for 300750.SZ\nROE: 20.1"),
            ],
        }

        fake_fundamentals_tool = _FakeTool(
            "get_fundamentals",
            "# Tushare fundamentals for 300750.SZ\nROE: 20.1\nGross Margin: 24.8",
        )
        fake_balance_sheet_tool = _FakeTool(
            "get_balance_sheet",
            "# Tushare balance sheet for 300750.SZ (quarterly)\nend_date,total_assets,total_liab\n20260331,100,55",
        )
        fake_cashflow_tool = _FakeTool(
            "get_cashflow",
            "# Tushare cashflow for 300750.SZ (quarterly)\nend_date,n_cashflow_act,n_cashflow_inv_act\n20260331,12,-8",
        )
        fake_income_statement_tool = _FakeTool(
            "get_income_statement",
            "# Tushare income statement for 300750.SZ (quarterly)\nend_date,total_revenue,n_income_attr_p\n20260331,25,6",
        )

        with (
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.run_tool_report_chain",
                return_value=(partial_result, "只给出笼统基本面结论。"),
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_fundamentals",
                fake_fundamentals_tool,
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_balance_sheet",
                fake_balance_sheet_tool,
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_cashflow",
                fake_cashflow_tool,
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_income_statement",
                fake_income_statement_tool,
            ),
        ):
            result = node(state)

        self.assertEqual(fake_fundamentals_tool.calls, [])
        self.assertEqual(
            fake_balance_sheet_tool.calls,
            [{"ticker": "300750.SZ", "freq": "quarterly", "curr_date": "2026-04-07"}],
        )
        self.assertEqual(
            fake_cashflow_tool.calls,
            [{"ticker": "300750.SZ", "freq": "quarterly", "curr_date": "2026-04-07"}],
        )
        self.assertEqual(
            fake_income_statement_tool.calls,
            [{"ticker": "300750.SZ", "freq": "quarterly", "curr_date": "2026-04-07"}],
        )
        self.assertIn("自由现金流", result["fundamentals_report"])
        self.assertEqual(result["messages"][0].content, result["fundamentals_report"])

    def test_fundamentals_analyst_rewrites_incomplete_report_when_all_tools_are_already_present(self):
        llm = _CapturingLLM(
            "# Full fundamentals report\n\nCovers balance sheet, income statement, cash flow, ROE, gross margin, net margin, debt to assets, free cash flow, and growth."
        )
        node = create_fundamentals_analyst(llm)

        partial_result = AIMessage(content="Basic overview only.")
        state = {
            "company_of_interest": "300750.SZ",
            "trade_date": "2026-04-07",
            "messages": [
                HumanMessage(content="Analyze 300750.SZ fundamentals"),
                AIMessage(content="# Tushare fundamentals for 300750.SZ\nROE: 20.1"),
                AIMessage(content="# Tushare balance sheet for 300750.SZ (quarterly)\nend_date,total_assets,total_liab"),
                AIMessage(content="# Tushare cashflow for 300750.SZ (quarterly)\nend_date,n_cashflow_act,n_cashflow_inv_act"),
                AIMessage(content="# Tushare income statement for 300750.SZ (quarterly)\nend_date,total_revenue,n_income_attr_p"),
            ],
        }

        fake_fundamentals_tool = _FakeTool("get_fundamentals", "unused")
        fake_balance_sheet_tool = _FakeTool("get_balance_sheet", "unused")
        fake_cashflow_tool = _FakeTool("get_cashflow", "unused")
        fake_income_statement_tool = _FakeTool("get_income_statement", "unused")

        with (
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.run_tool_report_chain",
                return_value=(partial_result, "Basic overview only."),
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_fundamentals",
                fake_fundamentals_tool,
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_balance_sheet",
                fake_balance_sheet_tool,
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_cashflow",
                fake_cashflow_tool,
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_income_statement",
                fake_income_statement_tool,
            ),
        ):
            result = node(state)

        self.assertEqual(fake_fundamentals_tool.calls, [])
        self.assertEqual(fake_balance_sheet_tool.calls, [])
        self.assertEqual(fake_cashflow_tool.calls, [])
        self.assertEqual(fake_income_statement_tool.calls, [])
        self.assertIn("free cash flow", result["fundamentals_report"].lower())
        self.assertEqual(result["messages"][0].content, result["fundamentals_report"])

    def test_fundamentals_analyst_rewrites_false_missing_guidance_and_peer_sample(self):
        llm = _CapturingLLM(
            "一、核心概览与估值快照\n已覆盖资产负债表、利润表、现金流、ROE、毛利率、净利率、资产负债率、自由现金流和增长。\n\n"
            "六、业绩预告与前瞻估值\n存在历史业绩预告，但该预告不晚于最新财报期，因此当前无法计算前瞻市盈率。\n\n"
            "七、同业对比\n已提供同业样本，可据此比较PE、PB、ROE与净利润增速。"
        )
        node = create_fundamentals_analyst(llm)

        partial_result = AIMessage(
            content=(
                "一、核心概览与估值快照\n概览。\n\n"
                "六、业绩预告与前瞻估值\n当前数据源中暂无晚于2026年3月31日最新财报期的业绩预告数据，亦无前瞻盈利预测值。\n\n"
                "七、同业对比\n当前数据源中未提供明确的同业样本数据。"
            )
        )
        state = {
            "company_of_interest": "300207.SZ",
            "trade_date": "2026-04-27",
            "messages": [
                HumanMessage(content="请分析 300207.SZ 的财报和基本面"),
                AIMessage(
                    content=(
                        "# Tushare fundamentals for 300207.SZ\n"
                        "Latest Forecast Announcement Date: 20240716\n"
                        "Forecast Summary: 预计:净利润76734-89888\n"
                        "Forward PE Status: Latest available forecast is not newer than the latest reported financial period 20260331.\n"
                        "Peer Sample Basis: same Tushare industry '电气设备'\n"
                        "Peer Sample: 宁德时代 (300750.SZ)\n"
                        "Target vs Peer Median: PE: target 47.30x vs sample median 37.19x\n"
                    )
                ),
                AIMessage(content="# Tushare balance sheet for 300207.SZ (quarterly)\n# Key snapshot\nTotal Assets: 1155.69亿 CNY"),
                AIMessage(content="# Tushare cashflow for 300207.SZ (quarterly)\nOperating Cash Flow: 30.0亿 CNY"),
                AIMessage(content="# Tushare income statement for 300207.SZ (quarterly)\nTotal Revenue: 161.16亿 CNY"),
            ],
        }

        with patch(
            "etfagents.agents.analysts.fundamentals_analyst.run_tool_report_chain",
            return_value=(partial_result, partial_result.content),
        ):
            result = node(state)

        self.assertIn("存在历史业绩预告", result["fundamentals_report"])
        self.assertIn("已提供同业样本", result["fundamentals_report"])
        self.assertNotIn("未提供明确的同业样本数据", result["fundamentals_report"])
        self.assertNotIn("亦无前瞻盈利预测值", result["fundamentals_report"])

    def test_fundamentals_analyst_normalizes_basic_fundamentals_wording(self):
        llm = _CapturingLLM(
            "# 根本分析\n\n已覆盖资产负债表、利润表、现金流、ROE、毛利率、净利率、资产负债率、自由现金流和增长。"
        )
        node = create_fundamentals_analyst(llm)

        partial_result = AIMessage(
            content="# 根本分析\n\n已覆盖资产负债表、利润表、现金流、ROE、毛利率、净利率、资产负债率、自由现金流和增长。"
        )
        state = {
            "company_of_interest": "300750.SZ",
            "trade_date": "2026-04-07",
            "messages": [
                HumanMessage(content="请分析 300750.SZ 的财报和基本面"),
                AIMessage(content="# Tushare fundamentals for 300750.SZ\nROE: 20.1"),
                AIMessage(content="# Tushare balance sheet for 300750.SZ (quarterly)\nend_date,total_assets,total_liab"),
                AIMessage(content="# Tushare cashflow for 300750.SZ (quarterly)\nend_date,n_cashflow_act,n_cashflow_inv_act"),
                AIMessage(content="# Tushare income statement for 300750.SZ (quarterly)\nend_date,total_revenue,n_income_attr_p"),
            ],
        }

        with (
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.run_tool_report_chain",
                return_value=(partial_result, partial_result.content),
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_fundamentals",
                _FakeTool("get_fundamentals", "unused"),
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_balance_sheet",
                _FakeTool("get_balance_sheet", "unused"),
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_cashflow",
                _FakeTool("get_cashflow", "unused"),
            ),
            patch(
                "etfagents.agents.analysts.fundamentals_analyst.get_income_statement",
                _FakeTool("get_income_statement", "unused"),
            ),
        ):
            result = node(state)

        self.assertIn("基本面分析", result["fundamentals_report"])
        self.assertNotIn("根本分析", result["fundamentals_report"])
        self.assertEqual(result["messages"][0].content, result["fundamentals_report"])

    def test_fundamentals_analyst_uses_chinese_only_headings_and_analysis_focused_prompt(self):
        llm = _CapturingLLM(
            "一、Fundamentals Overview and Valuation Snapshot (核心概览与估值快照)\n"
            "根据最新工具输出数据，公司估值处于合理区间。\n\n"
            "二、Growth, R&D, and Business Composition Analysis (增长、研发与主营业务分析)\n"
            "研发投入维持高位。"
        )
        node = create_fundamentals_analyst(llm)

        partial_result = AIMessage(content="只罗列数据。")
        state = {
            "company_of_interest": "300750.SZ",
            "trade_date": "2026-04-07",
            "messages": [
                HumanMessage(content="请深度分析 300750.SZ 的财报和基本面"),
                AIMessage(content="# Tushare fundamentals for 300750.SZ\n## Growth and PEG Snapshot\nPEG: 0.58x"),
                AIMessage(content="# Tushare balance sheet for 300750.SZ (quarterly)\nend_date,total_assets,total_liab"),
                AIMessage(content="# Tushare cashflow for 300750.SZ (quarterly)\nend_date,n_cashflow_act,n_cashflow_inv_act"),
                AIMessage(content="# Tushare income statement for 300750.SZ (quarterly)\nend_date,total_revenue,n_income_attr_p,rd_exp"),
            ],
        }

        with patch(
            "etfagents.agents.analysts.fundamentals_analyst.run_tool_report_chain",
            return_value=(partial_result, partial_result.content),
        ):
            result = node(state)

        self.assertIn("一、核心概览与估值快照", result["fundamentals_report"])
        self.assertNotIn("Fundamentals Overview and Valuation Snapshot", result["fundamentals_report"])
        self.assertNotIn("根据最新工具输出数据", result["fundamentals_report"])
        rewrite_prompt = llm.prompts[0]
        self.assertIn("只保留中文标题", rewrite_prompt)
        self.assertIn("禁止只罗列数字", rewrite_prompt)
        self.assertIn("同业对比部分", rewrite_prompt)


if __name__ == "__main__":
    unittest.main()
