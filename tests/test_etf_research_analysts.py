import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from etfagents.agents.analysts.etf_industry_research_analyst import (
    create_etf_industry_research_analyst,
)
from etfagents.agents.analysts.etf_market_analyst import (
    create_etf_market_analyst,
)
from etfagents.agents.analysts.macro_analyst import (
    create_macro_analyst,
)
from etfagents.agents.analysts.social_media_analyst import (
    create_social_media_analyst,
)
from etfagents.agents.analysts.etf_structure_analyst import (
    create_etf_structure_analyst,
)
from etfagents.agents.analysts.etf_stock_research_analyst import (
    create_etf_stock_research_analyst,
)
from etfagents.agents.utils.agent_utils import build_report_title
from etfagents.agents.utils.report_leads import (
    ensure_h1_title,
    strip_report_title,
)


class _CapturingLLM(RunnableLambda):
    """Mock LLM that works with both tool-calling chains and direct prompt | llm."""

    def __init__(self):
        super().__init__(func=self._invoke)
        self._prompts = []

    def _invoke(self, prompt, **kwargs):
        self._prompts.append(prompt)
        return AIMessage(content="Report content")

    def bind_tools(self, tools):
        return self


class EtfIndustryResearchAnalystPromptTests(unittest.TestCase):
    def test_prompt_uses_tradingagents_style_cross_analysis_framework(self):
        llm = _CapturingLLM()
        node = create_etf_industry_research_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_industry_research_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("逐份深度分析", system_msg)
        self.assertIn("跨报告比较分析", system_msg)
        self.assertIn("ETF Exposure Read-Through", system_msg)
        self.assertIn("Supply-Chain Implications", system_msg)
        self.assertIn("一、行业主线与分歧焦点", system_msg)
        self.assertNotIn("一、行业主线与分歧焦点 (", system_msg)
        self.assertIn("（一）共识主线", system_msg)
        self.assertNotIn("（一）共识主线 (", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("研报总览表", system_msg)
        self.assertIn("不得仅罗列数字", system_msg)
        self.assertIn("行业配置节奏", system_msg)
        self.assertIn("数据源分类噪声", system_msg)
        self.assertIn("应完全排除", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)


class EtfStockResearchAnalystPromptTests(unittest.TestCase):
    def test_prompt_uses_tradingagents_style_stock_framework(self):
        llm = _CapturingLLM()
        node = create_etf_stock_research_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_stock_research_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("逐份深度分析", system_msg)
        self.assertIn("跨报告比较分析", system_msg)
        self.assertIn("Earnings Estimate Consensus", system_msg)
        self.assertIn("Valuation Analysis", system_msg)
        self.assertIn("ETF Portfolio Impact", system_msg)
        self.assertIn("一、核心持仓共识与分歧", system_msg)
        self.assertNotIn("一、核心持仓共识与分歧 (", system_msg)
        self.assertIn("（一）共识主线", system_msg)
        self.assertNotIn("（一）共识主线 (", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("不得仅罗列数字", system_msg)
        self.assertIn("ETF收益归因", system_msg)
        self.assertIn("检索伪影", system_msg)
        self.assertIn("每项论点必须引用", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("不得使用'本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("If the structure does not provide a heading, write one that is brief, forceful, and immediately usable", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)


class EtfStructureAnalystPromptTests(unittest.TestCase):
    def test_prompt_forces_judgment_before_data_dump(self):
        llm = _CapturingLLM()
        node = create_etf_structure_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_structure_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "159980.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159980.SZ")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn(
            "近期合约表现总览",
            system_msg,
        )
        self.assertIn("在所有分析章节之后", system_msg)
        self.assertIn(
            "两周内，铜与热卷的需求强势能否驱动焦煤仓单去化",
            system_msg,
        )
        self.assertIn(
            "PPI向CPI传导失败",
            system_msg,
        )
        self.assertIn(
            "仓单必须同步下降",
            system_msg,
        )
        self.assertIn("段落式表达", system_msg)
        self.assertIn("（一）基准情景 — 概率估计 (%)", system_msg)
        self.assertNotIn("（一）基准情景 (", system_msg)
        self.assertIn("不得使用'判断：'", system_msg)
        self.assertIn("反面示例（禁止）", system_msg)
        self.assertIn("正面示例（目标风格）", system_msg)
        self.assertIn("冲突驱动", system_msg)
        self.assertIn("不得使用'本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("不要写'本节锁定'", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("Do NOT output code blocks", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)


class EtfMarketAnalystPromptTests(unittest.TestCase):
    def test_prompt_requires_title_lead_and_plain_language_trading_explanation(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("overview paragraph that summarizes", system_msg)
        self.assertIn("标准多头发散形态", system_msg)
        self.assertIn("这意味着什么", system_msg)
        self.assertIn("对交易应该怎么做", system_msg)
        self.assertIn("Use EXACTLY three top-level sections (一、二、三)", system_msg)
        self.assertIn("一、市场结构与量价诊断", system_msg)
        self.assertNotIn("一、市场结构与量价诊断 (", system_msg)
        self.assertIn("（一）趋势与动量", system_msg)
        self.assertNotIn("（一）趋势与动量 (", system_msg)
        self.assertIn("关键价位与条件情景推演", system_msg)
        self.assertIn("（一）关键价位与触发条件", system_msg)
        self.assertIn("（二）条件情景推演", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("核心交易信号", system_msg)
        self.assertIn("结论依据", system_msg)
        self.assertIn("without any sub-heading", system_msg)
        self.assertIn("每个一级章节（一、二、三）以2-3句导语开头", system_msg)
        self.assertIn("段落式表达", system_msg)
        self.assertIn("反面示例（禁止）", system_msg)
        self.assertIn("正面示例（目标风格）", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)
        self.assertIn("完整报告示例", system_msg)


class ReportTitleNormalizationTests(unittest.TestCase):
    def test_build_report_title_drops_suffix_only_ticker(self):
        with patch(
            "etfagents.agents.utils.agent_utils._is_chinese_output",
            return_value=True,
        ), patch(
            "etfagents.agents.utils.agent_utils._resolve_company_name",
            return_value="",
        ):
            self.assertEqual(
                build_report_title("SZ", "技术面与资金流综合诊断", "Technical & Flow Diagnosis"),
                "技术面与资金流综合诊断",
            )

    def test_ensure_h1_title_strips_duplicate_malformed_title_lines_in_body(self):
        report = (
            "# 技术面与资金流综合诊断\n\n"
            "这里是标题帽段。\n\n"
            "一、SZ：技术面与资金流综合诊断\n\n"
            "正文内容。\n\n"
            "## 二、交易确认与执行计划\n\n"
            "继续分析。"
        )
        cleaned = ensure_h1_title(report, "技术面与资金流综合诊断")
        self.assertNotIn("一、SZ：技术面与资金流综合诊断", cleaned)
        self.assertIn("正文内容。", cleaned)

    def test_ensure_h1_title_strips_exchange_only_prefix_with_name(self):
        report = (
            "# 588000.SH 科创50ETF华夏：技术面与资金流综合诊断\n\n"
            "这里是标题帽段。\n\n"
            "一、SH 科创50ETF华夏：技术面与资金流综合诊断\n\n"
            "正文内容。\n\n"
            "## 二、交易确认与执行计划\n\n"
            "继续分析。"
        )
        cleaned = ensure_h1_title(report, "588000.SH 科创50ETF华夏：技术面与资金流综合诊断")
        self.assertNotIn("一、SH 科创50ETF华夏：技术面与资金流综合诊断", cleaned)
        self.assertIn("正文内容。", cleaned)

    def test_ensure_h1_title_strips_exchange_only_prefix_with_name_when_h1_has_subject_only(self):
        report = (
            "# 技术面与资金流综合诊断\n\n"
            "这里是标题帽段。\n\n"
            "一、SH 工业有色ETF万家：技术面与资金流综合诊断\n\n"
            "正文内容。\n\n"
            "## 二、交易确认与执行计划\n\n"
            "继续分析。"
        )
        cleaned = ensure_h1_title(report, "技术面与资金流综合诊断")
        self.assertNotIn("一、SH 工业有色ETF万家：技术面与资金流综合诊断", cleaned)
        self.assertIn("正文内容。", cleaned)

    def test_strip_report_title_removes_initial_h1(self):
        report = (
            "# 舆情与事件影响分析\n\n"
            "导语内容。\n\n"
            "## 一、总体研判\n\n"
            "正文内容。"
        )
        cleaned = strip_report_title(report)
        self.assertNotIn("# 舆情与事件影响分析", cleaned)
        self.assertTrue(cleaned.startswith("导语内容。"))



class EtfNewsAndSentimentAnalystPromptTests(unittest.TestCase):
    def test_news_prompt_requires_title_lead_before_first_section(self):
        llm = _CapturingLLM()
        node = create_macro_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.macro_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("不得使用'本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一、暴露与宏观主线", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("If the structure does not provide a heading, write one that is brief, forceful, and immediately usable", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)

    def test_news_report_strips_malformed_suffix_only_title_inside_body(self):
        llm = _CapturingLLM()
        node = create_macro_analyst(llm)

        raw_report = (
            "# 宏观框架分析\n\n"
            "宏观主线仍然围绕流动性与风险偏好再定价展开。\n\n"
            "一、SZ：宏观框架分析\n\n"
            "## 一、总体判断\n\n"
            "风险偏好修复快于盈利预期修复。"
        )

        with patch(
            "etfagents.agents.analysts.macro_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.macro_analyst.build_instrument_context",
            return_value="",
        ), patch(
            "etfagents.agents.utils.agent_utils._is_chinese_output",
            return_value=True,
        ):
            result = node(
                {
                    "company_of_interest": "SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze SZ")],
                }
            )

        rendered = result["macro_regime_report"]
        self.assertFalse(rendered.startswith("#"))
        self.assertNotIn("一、SZ：宏观框架分析", rendered)

    @patch("etfagents.agents.analysts.social_media_analyst.get_news_for_queries")
    @patch("etfagents.agents.analysts.social_media_analyst.get_global_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_holdings")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_info")
    def test_social_prompt_requires_title_lead_before_first_section(
        self, mock_info, mock_holdings, mock_news, mock_global, mock_queries
    ):
        mock_info.func.return_value = "ETF profile"
        mock_holdings.func.return_value = "name,weight\n紫金矿业,8.5%\n"
        mock_news.return_value = "## news"
        mock_global.return_value = "## global"
        mock_queries.return_value = "## holdings"

        captured = {}

        def capturing_func(input, config=None):
            text = str(input)
            if "报告质量审核员" not in text and "prompt" not in captured:
                captured["prompt"] = text
            if "报告质量审核员" in text:
                return AIMessage(content='{"score": 9, "pass": true, "critical_issues": [], "minor_issues": [], "missing_elements": [], "general_comment": "OK"}')
            return AIMessage(content="Report content")

        llm = RunnableLambda(capturing_func)
        node = create_social_media_analyst(llm)

        node(
            {
                "company_of_interest": "510300.SH",
                "trade_date": "2026-04-30",
                "messages": [HumanMessage(content="Analyze 510300.SH")],
            }
        )

        system_msg = captured.get("prompt", "")
        self.assertIn("不得使用'本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一、情绪主线与权重影响", system_msg)
        self.assertNotIn("一、情绪主线与权重影响 (", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)




if __name__ == "__main__":
    unittest.main()
