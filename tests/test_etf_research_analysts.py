import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.etf_industry_research_analyst import (
    create_etf_industry_research_analyst,
)
from etfagents.agents.analysts.etf_market_analyst import (
    create_etf_market_analyst,
)
from etfagents.agents.analysts.news_analyst import (
    create_news_analyst,
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
    strip_meta_lead_prefixes,
    strip_report_title,
)


class _CapturingLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
        return AIMessage(content="Report content")


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
        self.assertIn("Per-Report Deep Analysis", system_msg)
        self.assertIn("Cross-Report Comparative Analysis", system_msg)
        self.assertIn("ETF Exposure Read-Through", system_msg)
        self.assertIn("Supply-Chain Implications", system_msg)
        self.assertIn("一、行业主线与分歧焦点", system_msg)
        self.assertIn("Avoid generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("Summary Table", system_msg)
        self.assertIn("Do NOT just list numbers", system_msg)
        self.assertIn("industry allocation timing", system_msg)
        self.assertIn("Never discuss data-source classification noise", system_msg)
        self.assertIn("Exclude them entirely", system_msg)
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
        self.assertIn("Per-Report Deep Analysis", system_msg)
        self.assertIn("Cross-Report Comparative Analysis", system_msg)
        self.assertIn("Earnings Estimate Consensus", system_msg)
        self.assertIn("Valuation Analysis", system_msg)
        self.assertIn("ETF Portfolio Impact", system_msg)
        self.assertIn("一、核心持仓共识与分歧", system_msg)
        self.assertIn("Avoid generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT just list numbers", system_msg)
        self.assertIn("ETF return attribution", system_msg)
        self.assertIn("retrieval artifacts", system_msg)
        self.assertIn("Write a 2-4 sentence overview paragraph before any section headings", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("keep the original numbering hierarchy", system_msg)
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
        self.assertIn("At the very end of the report, after all analytical sections", system_msg)
        self.assertIn(
            "within two weeks, can demand strength in copper and hot-rolled coil drive coking-coal warehouse-receipt drawdown",
            system_msg,
        )
        self.assertIn(
            "failed PPI-to-CPI transmission",
            system_msg,
        )
        self.assertIn(
            "warehouse receipts must fall with it",
            system_msg,
        )
        self.assertIn("Paragraph-based expression", system_msg)
        self.assertIn("Do NOT use quiz-like labels such as", system_msg)
        self.assertIn("Anti-example (forbidden)", system_msg)
        self.assertIn("Positive example (target style)", system_msg)
        self.assertIn("Do NOT write a report title. Start directly with a 2-4 sentence overview paragraph", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("Avoid generic labels such as '总体研判'", system_msg)
        self.assertIn("Forbidden example: `_HEADING_MAP =", system_msg)
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
        self.assertIn("overview paragraph before any section headings", system_msg)
        self.assertIn("Do NOT write unexplained phrases such as '标准多头发散形态'", system_msg)
        self.assertIn("这意味着什么", system_msg)
        self.assertIn("对交易应该怎么做", system_msg)
        self.assertIn("Use EXACTLY three top-level sections (一、二、三)", system_msg)
        self.assertIn("关键价位与条件情景推演", system_msg)
        self.assertIn("（一）关键价位与触发条件", system_msg)
        self.assertIn("（二）条件情景推演", system_msg)
        self.assertIn("Avoid generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT introduce headings like '核心交易信号', '结论依据'", system_msg)
        self.assertIn("without any sub-heading", system_msg)
        self.assertIn("must NOT have a separate lead paragraph or hat paragraph", system_msg)
        self.assertIn("Paragraph-based expression: in section three", system_msg)
        self.assertIn("Anti-example (forbidden)", system_msg)
        self.assertIn("Positive example (target style)", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)


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

    def test_strip_meta_lead_prefixes_removes_direct_present_and_through_phrases(self):
        report = (
            "本部分结论直接呈现全市场主流机构对工业有色核心品种供需格局的基准判断。\n"
            "本部分通过量化数据比对、机构情绪拆解与产业链传导机制，量化评估ETF持仓品种的风险收益比。"
        )
        cleaned = strip_meta_lead_prefixes(report)
        self.assertNotIn("本部分结论直接呈现", cleaned)
        self.assertNotIn("本部分通过", cleaned)
        self.assertIn("全市场主流机构对工业有色核心品种供需格局的基准判断。", cleaned)
        self.assertIn("量化数据比对、机构情绪拆解与产业链传导机制，量化评估ETF持仓品种的风险收益比。", cleaned)


class EtfNewsAndSentimentAnalystPromptTests(unittest.TestCase):
    def test_news_prompt_requires_title_lead_before_first_section(self):
        llm = _CapturingLLM()
        node = create_news_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.news_analyst.run_tool_report_chain",
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
        self.assertIn("overview paragraph before any section headings", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一、暴露与宏观主线", system_msg)
        self.assertIn("Avoid generic labels such as '总体研判'", system_msg)
        self.assertIn("keep the original numbering hierarchy", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)

    def test_news_report_strips_malformed_suffix_only_title_inside_body(self):
        llm = _CapturingLLM()
        node = create_news_analyst(llm)

        raw_report = (
            "# 宏观框架分析\n\n"
            "宏观主线仍然围绕流动性与风险偏好再定价展开。\n\n"
            "一、SZ：宏观框架分析\n\n"
            "## 一、总体判断\n\n"
            "风险偏好修复快于盈利预期修复。"
        )

        with patch(
            "etfagents.agents.analysts.news_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.news_analyst.build_instrument_context",
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

    def test_social_prompt_requires_title_lead_before_first_section(self):
        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.social_media_analyst.run_tool_report_chain",
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
        self.assertIn("overview paragraph before any section headings", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一、情绪主线与权重影响", system_msg)
        self.assertIn("Avoid generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)


class EtfAnalystTitleLeadBackfillTests(unittest.TestCase):
    def test_stock_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_etf_stock_research_analyst(llm)

        raw_report = (
            "# ETF头部持仓研究分析报告\n\n"
            "## 一、总体研判\n\n"
            "高权重个股盈利分化继续扩大。"
        )

        with patch(
            "etfagents.agents.analysts.etf_stock_research_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        rendered = result["top_holdings_report"]
        self.assertIn("该ETF头部持仓的盈利修复、估值分化与权重集中度共同决定组合的收益来源与回撤来源。", rendered)
        self.assertIn("一、核心持仓共识与分歧", rendered)
        self.assertLess(
            rendered.index("该ETF头部持仓的盈利修复、估值分化与权重集中度共同决定组合的收益来源与回撤来源。"),
            rendered.index("一、核心持仓共识与分歧"),
        )

    def test_structure_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_etf_structure_analyst(llm)

        raw_report = (
            "# ETF中观大宗商品分析报告\n\n"
            "## 一、核心矛盾与主线判断\n\n"
            "上游成本压力与下游利润承压并存。"
        )

        with patch(
            "etfagents.agents.analysts.etf_structure_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "159980.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159980.SZ")],
                }
            )

        rendered = result["meso_commodity_report"]
        self.assertIn("本期中观商品主线不在单一品种的涨跌，而在复苏预期能否穿透库存与成本倒逼", rendered)
        self.assertLess(
            rendered.index("本期中观商品主线不在单一品种的涨跌，而在复苏预期能否穿透库存与成本倒逼"),
            rendered.index("一、核心矛盾与主线判断"),
        )

    def test_market_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        raw_report = (
            "# ETF市场与资金流分析报告\n\n"
            "## 一、趋势与动量\n\n"
            "价格仍运行在关键均线之上。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst._etf_market_report_needs_rewrite",
            return_value=False,
        ):
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["market_flow_report"]
        self.assertIn("该ETF当前量价结构更接近趋势延续还是震荡回撤", rendered)
        self.assertLess(
            rendered.index("该ETF当前量价结构更接近趋势延续还是震荡回撤"),
            rendered.index("一、趋势与动量"),
        )

    def test_news_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_news_analyst(llm)

        raw_report = (
            "# ETF宏观框架分析报告\n\n"
            "## 一、总体研判\n\n"
            "利率与政策预期继续主导配置方向。"
        )

        with patch(
            "etfagents.agents.analysts.news_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        rendered = result["macro_regime_report"]
        self.assertIn("该ETF当前的宏观胜负手取决于利率路径、信用环境、政策节奏与核心暴露方向能否形成同向共振。", rendered)
        self.assertFalse(rendered.startswith("#"))
        self.assertIn("一、暴露与宏观主线", rendered)
        self.assertLess(
            rendered.index("该ETF当前的宏观胜负手取决于利率路径、信用环境、政策节奏与核心暴露方向能否形成同向共振。"),
            rendered.index("一、暴露与宏观主线"),
        )

    def test_sentiment_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        raw_report = (
            "# ETF舆情与事件影响分析报告\n\n"
            "## 一、总体研判\n\n"
            "主导板块事件催化仍强于产品层面噪声。"
        )

        with patch(
            "etfagents.agents.analysts.social_media_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        rendered = result["catalyst_sentiment_report"]
        self.assertIn("当前影响该ETF定价的关键变量不在产品 headline 数量，而在主导行业与高权重成分股的事件催化能否继续向净值传导。", rendered)
        self.assertFalse(rendered.startswith("#"))
        self.assertIn("一、情绪主线与权重映射", rendered)
        self.assertLess(
            rendered.index("当前影响该ETF定价的关键变量不在产品 headline 数量，而在主导行业与高权重成分股的事件催化能否继续向净值传导。"),
            rendered.index("一、情绪主线与权重映射"),
        )

    def test_market_report_strips_h1_title(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        raw_report = (
            "# ETF市场与资金流分析报告\n\n"
            "## 一、市场结构与量价诊断\n\n"
            "价格仍运行在关键均线之上。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst._etf_market_report_needs_rewrite",
            return_value=False,
        ):
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["market_flow_report"]
        self.assertFalse(rendered.startswith("#"))
        self.assertIn("一、市场结构与量价诊断", rendered)

    def test_market_report_strips_conclusion_basis_label(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        raw_report = (
            "# ETF市场与资金流分析报告\n\n"
            "偏多格局延续，但确认信号仍需要量能配合。\n\n"
            "## 一、市场结构与量价诊断\n\n"
            "### （一）趋势与动量\n\n"
            "**结论依据**：10日均线继续上穿20日均线。\n\n"
            "## 二、交易确认与执行计划\n\n"
            "### （一）信号确认与决策\n\n"
            "若回踩不破支撑，可继续持有。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst._etf_market_report_needs_rewrite",
            return_value=False,
        ):
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["market_flow_report"]
        self.assertNotIn("结论依据", rendered)
        self.assertNotIn("### （一）信号确认与决策", rendered)
        self.assertIn("10日均线继续上穿20日均线。", rendered)

    def test_market_report_replaces_malformed_suffix_only_title_heading(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        raw_report = (
            "一、SZ：技术面与资金流综合诊断\n\n"
            "价格仍运行在关键均线之上，量能没有失真。\n\n"
            "## 一、市场结构与量价诊断\n\n"
            "### （一）趋势与动量\n\n"
            "10日均线继续上穿20日均线。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst._etf_market_report_needs_rewrite",
            return_value=False,
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst.build_instrument_context",
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

        rendered = result["market_flow_report"]
        self.assertFalse(rendered.startswith("#"))
        self.assertNotIn("一、SZ：技术面与资金流综合诊断", rendered)


if __name__ == "__main__":
    unittest.main()
