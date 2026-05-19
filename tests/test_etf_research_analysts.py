import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from etfagents.agents.analysts.etf_industry_research_analyst import (
    create_etf_industry_research_analyst,
    _looks_like_complete_holdings_industry_report,
)
from etfagents.agents.analysts.etf_market_analyst import (
    _REPORT_SPEC,
    create_etf_market_analyst,
    _looks_like_complete_market_flow_report,
    _normalize_market_flow_tail_sections,
)
from etfagents.agents.analysts.macro_analyst import (
    create_macro_analyst,
)
from etfagents.agents.analysts.social_media_analyst import (
    create_social_media_analyst,
    _looks_like_complete_catalyst_sentiment_report,
)
from etfagents.agents.analysts.etf_structure_analyst import (
    create_etf_structure_analyst,
    _looks_like_complete_meso_commodity_report,
)
from etfagents.agents.analysts.etf_stock_research_analyst import (
    create_etf_stock_research_analyst,
    _looks_like_complete_top_holdings_report,
)
from etfagents.agents.utils.agent_utils import build_report_title
from etfagents.agents.utils.report_leads import (
    clean_generated_report,
    ensure_h1_title,
    post_judge_clean,
    strip_report_title,
    strip_refine_preamble,
)
from etfagents.agents.utils.validate_refine import static_validate


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


class _IntentThenFinalLLM(RunnableLambda):
    """First emits a fake future tool-call note, then writes a report from recovered data."""

    def __init__(self, tool_name="get_etf_industry_research", final_content=None):
        super().__init__(func=self._invoke)
        self._prompts = []
        self.tool_name = tool_name
        self.final_content = final_content or (
            "券商行业研究显示ETF主导暴露集中在工业金属，需求验证优先级高于估值扩张。\n\n"
            "一、行业主线与分歧焦点\n"
            "工业金属报告的共同主线是需求验证强于估值扩张，ETF配置需要等待库存和订单同步确认。\n\n"
            "（一）共识主线\n"
            "报告内容。\n\n"
            "二、景气、政策与产业链验证\n"
            "景气验证集中在价格、库存和政策传导三个变量，任何单点改善都不足以支撑行业贝塔扩散。\n\n"
            "（一）景气与价格对比\n"
            "报告内容。\n\n"
            "三、未解问题与风险边界\n"
            "未解问题在于需求弹性和成本传导，风险边界应跟随盈利修正频次调整。\n\n"
            "（一）未解问题\n"
            "报告内容。\n\n"
            "四、ETF影响与研报总览\n"
            "ETF暴露需要把工业金属行业景气转化为权重贡献，当前仍以需求验证作为加仓前提。\n\n"
            "（一）ETF暴露与配置含义\n"
            "ETF暴露需要等待行业需求验证。\n\n"
            "（二）研报总览表\n"
            "| 券商 | 行业关键词 | 立场 |\n"
            "| --- | --- | --- |\n"
            "| 示例券商 | 工业金属 | 中性 |"
        )

    def _invoke(self, prompt, **kwargs):
        self._prompts.append(prompt)
        if len(self._prompts) == 1:
            return AIMessage(
                content=(
                    "好的，接下来我将获取该ETF主导行业的券商研究报告，以完成深度交叉分析。"
                    f"我将调用 {self.tool_name} 工具。"
                )
            )
        return AIMessage(content=self.final_content)

    def bind_tools(self, tools):
        return self


class _FakeTool:
    def __init__(self, name, return_value):
        self.name = name
        self.calls = []
        self.return_value = return_value

    def invoke(self, payload):
        self.calls.append(payload)
        return self.return_value


class EtfIndustryResearchAnalystPromptTests(unittest.TestCase):
    def test_prompt_uses_tradingagents_style_cross_analysis_framework(self):
        llm = _CapturingLLM()
        node = create_etf_industry_research_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            captured["recovery"] = kwargs.get("unexecuted_tool_recovery", {})
            captured["acceptance_check"] = kwargs.get("report_acceptance_check")
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
        self.assertIn("逐份提取并记录", system_msg)
        self.assertIn("跨报告比较时", system_msg)
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
        self.assertIn("Do NOT narrate your workflow, tool usage", system_msg)
        self.assertNotIn("## 第一步：数据获取", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一级标题 -> 1-2句结论段 -> 子章节标题", system_msg)
        self.assertIn("不得写'本章''本节''本部分''旨在''梳理'", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)
        self.assertIs(
            captured["acceptance_check"],
            _looks_like_complete_holdings_industry_report,
        )

    def test_holdings_industry_acceptance_rejects_delivery_preamble(self):
        valid_report = (
            "券商行业研究显示煤炭链条盈利预期仍受煤价下行压制，ETF配置应等待需求和库存同步修复。\n\n"
            "一、行业主线与分歧焦点\n"
            "煤炭链条共识集中在煤价下行对盈利的压制，ETF配置需要等待需求和库存同步修复。\n\n"
            "（一）共识主线\n"
            "报告内容。\n\n"
            "二、景气、政策与产业链验证\n"
            "景气验证的关键在于价格、库存和政策传导能否同时改善，否则行业贝塔仍难扩散。\n\n"
            "（一）景气与价格对比\n"
            "报告内容。\n\n"
            "三、未解问题与风险边界\n"
            "券商分歧主要落在需求斜率和煤价中枢，风险边界应围绕盈利下修频次重新定价。\n\n"
            "（一）未解问题\n"
            "报告内容。\n\n"
            "四、ETF影响与研报总览\n"
            "ETF暴露需要把行业盈利弹性转化为权重贡献，当前更适合等待需求验证后再提高仓位。\n\n"
            "（一）ETF暴露与配置含义\n"
            "ETF暴露需要等待需求验证。\n\n"
            "（二）研报总览表\n"
            "| 券商 | 行业关键词 | 立场 |\n"
            "| --- | --- | --- |\n"
            "| 示例券商 | 煤炭 | 谨慎 |"
        )

        self.assertTrue(_looks_like_complete_holdings_industry_report(valid_report))
        self.assertFalse(
            _looks_like_complete_holdings_industry_report(
                "报告已就绪。以下为煤炭ETF（515220.SH）行业券商研究交叉分析：\n\n"
                + valid_report
            )
        )
        self.assertFalse(
            _looks_like_complete_holdings_industry_report(
                "本章旨在梳理当前新能源产业链的核心投资逻辑与市场认知差异。\n\n"
                + valid_report
            )
        )
        self.assertFalse(
            _looks_like_complete_holdings_industry_report(
                "券商行业研究显示煤炭链条盈利预期仍受煤价下行压制。\n\n"
                "一、行业主线与分歧焦点\n"
                "（一）共识主线\n"
                "报告内容。\n\n"
                "二、景气、政策与产业链验证\n"
                "景气验证依赖库存去化。\n\n"
                "（一）景气与价格对比\n"
                "报告内容。\n\n"
                "三、未解问题与风险边界\n"
                "风险边界来自盈利下修。\n\n"
                "（一）未解问题\n"
                "报告内容。\n\n"
                "四、ETF影响与研报总览\n"
                "ETF暴露需要等待需求验证。\n\n"
                "（一）ETF暴露与配置含义\n"
                "ETF暴露需要等待需求验证。\n\n"
                "（二）研报总览表\n"
                "| 券商 | 行业关键词 | 立场 |\n"
                "| --- | --- | --- |\n"
                "| 示例券商 | 煤炭 | 谨慎 |"
            )
        )

    def test_recovers_when_model_describes_tool_call_without_executing_it(self):
        llm = _IntentThenFinalLLM()
        node = create_etf_industry_research_analyst(llm)
        fake_holdings = _FakeTool("get_etf_holdings", "holdings data")
        fake_industry = _FakeTool("get_etf_industry_research", "industry research data")

        with (
            patch(
                "etfagents.agents.analysts.etf_industry_research_analyst.get_etf_holdings",
                fake_holdings,
            ),
            patch(
                "etfagents.agents.analysts.etf_industry_research_analyst.get_etf_industry_research",
                fake_industry,
            ),
            patch(
                "etfagents.agents.analysts.etf_industry_research_analyst.validate_and_refine",
                side_effect=lambda report, *_args, **_kwargs: report,
            ),
        ):
            output = node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        report = output["holdings_industry_report"]
        self.assertIn("券商行业研究显示", report)
        self.assertNotIn("我将调用 get_etf_industry_research", report)
        self.assertEqual([], fake_holdings.calls)
        self.assertEqual(
            [{"ticker": "516650.SH", "curr_date": "2026-04-30"}],
            fake_industry.calls,
        )


class EtfStockResearchAnalystPromptTests(unittest.TestCase):
    def test_prompt_uses_tradingagents_style_stock_framework(self):
        llm = _CapturingLLM()
        node = create_etf_stock_research_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            captured["recovery"] = kwargs.get("unexecuted_tool_recovery", {})
            captured["acceptance_check"] = kwargs.get("report_acceptance_check")
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
        self.assertIn("逐份提取并记录", system_msg)
        self.assertIn("跨报告比较时", system_msg)
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
        self.assertIn("一级标题 -> 2-3句结论段 -> 子章节标题", system_msg)
        self.assertIn("不得写'本章''本节''本部分''旨在''梳理'", system_msg)
        self.assertIn("Do NOT narrate your workflow, tool usage", system_msg)
        self.assertNotIn("## 第一步：数据获取", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("If the structure does not provide a heading, write one that is brief, forceful, and immediately usable", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)
        self.assertIs(
            captured["acceptance_check"],
            _looks_like_complete_top_holdings_report,
        )

    def test_top_holdings_acceptance_rejects_delivery_preamble(self):
        valid_report = (
            "券商个股研究显示ETF头部持仓盈利修正方向分化，组合贡献集中在龙头。\n\n"
            "一、核心持仓共识与分歧\n"
            "头部持仓的券商共识集中在龙头盈利韧性，但ETF组合贡献仍受权重集中度放大。\n\n"
            "（一）共识主线\n"
            "报告内容。\n\n"
            "二、盈利、估值与机构态度\n"
            "盈利预期分化和估值层级差异决定ETF收益归因，机构评级分布需要与权重贡献一起看。\n\n"
            "（一）关键数据对比\n"
            "报告内容。\n\n"
            "三、催化、盲点与风险边界\n"
            "催化剂集中在订单和利润率修复，未解问题是盈利兑现节奏能否覆盖估值压力。\n\n"
            "（一）未解问题\n"
            "报告内容。\n\n"
            "四、ETF影响与研报总览\n"
            "ETF组合影响集中在龙头盈利修正和权重贡献，摘要表用于校验券商观点覆盖度。\n\n"
            "（一）ETF组合影响\n"
            "头部持仓对ETF组合影响集中在盈利修正和权重贡献。\n\n"
            "（二）研报总览表\n"
            "| 券商 | 持仓 | 评级 |\n"
            "| --- | --- | --- |\n"
            "| 示例券商 | 龙头公司 | 买入 |"
        )

        self.assertTrue(_looks_like_complete_top_holdings_report(valid_report))
        self.assertFalse(
            _looks_like_complete_top_holdings_report(
                "报告已就绪。以下为煤炭ETF（515220.SH）头部持仓的券商研究交叉分析：\n\n"
                + valid_report
            )
        )
        self.assertFalse(
            _looks_like_complete_top_holdings_report(
                "数据已全部获取完毕，现在撰写完整报告。\n\n" + valid_report
            )
        )
        self.assertFalse(
            _looks_like_complete_top_holdings_report(
                "券商个股研究显示ETF头部持仓盈利修正方向分化。\n\n"
                "一、核心持仓共识与分歧\n"
                "（一）共识主线\n"
                "报告内容。\n\n"
                "二、盈利、估值与机构态度\n"
                "盈利预期分化决定ETF收益归因。\n\n"
                "（一）关键数据对比\n"
                "报告内容。\n\n"
                "三、催化、盲点与风险边界\n"
                "催化剂集中在订单和利润率修复。\n\n"
                "（一）未解问题\n"
                "报告内容。\n\n"
                "四、ETF影响与研报总览\n"
                "ETF组合影响集中在龙头盈利修正。\n\n"
                "（一）ETF组合影响\n"
                "头部持仓对ETF组合影响集中在盈利修正和权重贡献。\n\n"
                "（二）研报总览表\n"
                "| 券商 | 持仓 | 评级 |\n"
                "| --- | --- | --- |\n"
                "| 示例券商 | 龙头公司 | 买入 |"
            )
        )

    def test_recovers_when_model_describes_top_holdings_tool_call_without_executing_it(self):
        llm = _IntentThenFinalLLM(
            tool_name="get_etf_top_holdings_research",
            final_content=(
                "券商个股研究显示ETF头部持仓盈利修正方向分化，组合贡献集中在龙头。\n\n"
                "一、核心持仓共识与分歧\n"
                "头部持仓的共识集中在龙头盈利韧性，但ETF组合贡献仍取决于权重集中度和修正广度。\n\n"
                "（一）共识主线\n"
                "报告内容。\n\n"
                "二、盈利、估值与机构态度\n"
                "盈利预期和估值分层共同决定ETF收益归因，机构态度分布需要结合权重贡献判断。\n\n"
                "（一）关键数据对比\n"
                "报告内容。\n\n"
                "三、催化、盲点与风险边界\n"
                "催化剂集中在订单和利润率修复，主要风险是盈利兑现慢于估值压力释放。\n\n"
                "（一）未解问题\n"
                "报告内容。\n\n"
                "四、ETF影响与研报总览\n"
                "ETF组合影响集中在龙头盈利修正和权重贡献，摘要表用于校验券商观点覆盖度。\n\n"
                "（一）ETF组合影响\n"
                "ETF组合影响集中在龙头盈利修正。\n\n"
                "（二）研报总览表\n"
                "| 券商 | 持仓 | 评级 |\n"
                "| --- | --- | --- |\n"
                "| 示例券商 | 龙头公司 | 买入 |"
            ),
        )
        node = create_etf_stock_research_analyst(llm)
        fake_holdings = _FakeTool("get_etf_holdings", "holdings data")
        fake_stock = _FakeTool("get_etf_top_holdings_research", "stock research data")

        with (
            patch(
                "etfagents.agents.analysts.etf_stock_research_analyst.get_etf_holdings",
                fake_holdings,
            ),
            patch(
                "etfagents.agents.analysts.etf_stock_research_analyst.get_etf_top_holdings_research",
                fake_stock,
            ),
            patch(
                "etfagents.agents.analysts.etf_stock_research_analyst.validate_and_refine",
                side_effect=lambda report, *_args, **_kwargs: report,
            ),
        ):
            output = node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        report = output["top_holdings_report"]
        self.assertIn("券商个股研究显示", report)
        self.assertNotIn("我将调用 get_etf_top_holdings_research", report)
        self.assertEqual([], fake_holdings.calls)
        self.assertEqual(
            [{"ticker": "516650.SH", "curr_date": "2026-04-30"}],
            fake_stock.calls,
        )


class EtfStructureAnalystPromptTests(unittest.TestCase):
    def test_prompt_forces_judgment_before_data_dump(self):
        llm = _CapturingLLM()
        node = create_etf_structure_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            captured["recovery"] = kwargs.get("unexecuted_tool_recovery", {})
            captured["acceptance_check"] = kwargs.get("report_acceptance_check")
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
            "四、近期合约表现总览",
            system_msg,
        )
        self.assertIn("报告含四个一级章节", system_msg)
        self.assertIn("一、二、三章标题后直接写2-3句结论段", system_msg)
        self.assertIn("标题下一行必须是Markdown表格第一行", system_msg)
        self.assertIn("禁止任何说明文字、结论段、子章节或其他标题", system_msg)
        self.assertIn(
            "四、近期合约表现总览\n| 合约 | 最新水平 | 近期价格表现 | 持仓变化 | 仓单变化 | 信号备注 |",
            system_msg,
        )
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
        self.assertIn("不得使用'本章''本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("不要写'本节锁定'", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Do NOT narrate your workflow, tool usage", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("Do NOT output code blocks", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)
        self.assertEqual(
            ["get_commodity_cluster_data"],
            captured["recovery"]["trigger_tool_names"],
        )
        self.assertEqual(
            ["get_commodity_cluster_data"],
            [item["tool"].name for item in captured["recovery"]["tool_payloads"]],
        )
        self.assertIs(
            captured["acceptance_check"],
            _looks_like_complete_meso_commodity_report,
        )

    def test_meso_commodity_acceptance_rejects_delivery_preamble(self):
        valid_report = (
            "铜与热卷的需求强势若不能带动焦煤仓单去化，黑色链利润仍会被上游成本挤压，ETF配置应先保持防守。\n\n"
            "一、核心矛盾与主线判断\n"
            "核心矛盾集中在制造业需求和上游成本传导。\n\n"
            "二、矛盾推演\n"
            "（一）制造业复苏与上游需求\n"
            "报告内容。\n\n"
            "三、情景推演与策略启示\n"
            "基准情景仍偏防守，若制造业需求未能带动仓单去化，ETF配置不应主动放大风险暴露。\n\n"
            "（一）基准情景 — 概率估计 (%)\n"
            "报告内容。\n\n"
            "四、近期合约表现总览\n"
            "| 合约 | 最新水平 | 信号备注 |\n"
            "| --- | --- | --- |\n"
            "| CU | 80000 | 需求验证 |"
        )

        self.assertTrue(_looks_like_complete_meso_commodity_report(valid_report))
        self.assertFalse(
            _looks_like_complete_meso_commodity_report(
                valid_report.replace("四、近期合约表现总览", "近期合约表现总览")
            )
        )
        self.assertFalse(
            _looks_like_complete_meso_commodity_report(
                valid_report.replace(
                    "四、近期合约表现总览\n",
                    "四、近期合约表现总览\n（一）合约表现\n",
                )
            )
        )
        self.assertFalse(
            _looks_like_complete_meso_commodity_report(
                valid_report.replace(
                    "四、近期合约表现总览\n",
                    "四、近期合约表现总览\n铜和焦煤的仓单变化最能验证前述判断。\n\n",
                )
            )
        )
        self.assertFalse(
            _looks_like_complete_meso_commodity_report(
                "报告已就绪。以下为中观商品策略分析：\n\n" + valid_report
            )
        )


class EtfMarketAnalystPromptTests(unittest.TestCase):
    def test_prompt_requires_title_lead_and_plain_language_trading_explanation(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            captured["recovery"] = kwargs.get("unexecuted_tool_recovery", {})
            captured["acceptance_check"] = kwargs.get("report_acceptance_check")
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
        self.assertIn("Use EXACTLY four top-level sections (一、二、三、四)", system_msg)
        self.assertIn("一、市场结构与量价诊断", system_msg)
        self.assertNotIn("一、市场结构与量价诊断 (", system_msg)
        self.assertIn("（一）趋势与动量", system_msg)
        self.assertNotIn("（一）趋势与动量 (", system_msg)
        self.assertIn("关键价位与条件情景推演", system_msg)
        self.assertIn("（一）关键价位与触发条件", system_msg)
        self.assertIn("（二）条件情景推演", system_msg)
        self.assertIn("四、综合结论和指标总览", system_msg)
        self.assertIn("不得再写“指标总览”或“综合结论”独立标题", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("核心交易信号", system_msg)
        self.assertIn("结论依据", system_msg)
        self.assertIn("without any sub-heading", system_msg)
        self.assertIn("前三个一级章节（一、二、三）标题后直接写2-3句结论段", system_msg)
        self.assertIn("段落式表达", system_msg)
        self.assertIn("反面示例（禁止）", system_msg)
        self.assertIn("正面示例（目标风格）", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Do NOT narrate your workflow, tool usage", system_msg)
        self.assertNotIn("## 数据获取", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)
        self.assertIn("完整报告示例", system_msg)
        expected_tool_names = [
            "get_etf_price_data",
            "get_etf_indicators",
            "get_etf_share",
            "get_etf_nav",
            "get_etf_universe",
        ]
        self.assertEqual(expected_tool_names, captured["recovery"]["trigger_tool_names"])
        self.assertEqual(
            expected_tool_names,
            [item["tool"].name for item in captured["recovery"]["tool_payloads"]],
        )
        self.assertIs(
            captured["acceptance_check"],
            _looks_like_complete_market_flow_report,
        )

    def test_market_flow_report_acceptance_requires_complete_report_shape(self):
        valid_report = (
            "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n"
            "趋势导语。\n\n"
            "二、交易确认与执行计划\n"
            "执行导语。\n\n"
            "三、关键价位与条件情景推演\n"
            "情景导语。\n\n"
            "四、综合结论和指标总览\n"
            "偏多配置，等待回踩确认。\n\n"
            "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| MACD | 1 | 上方 | 动能改善 | 下穿转弱 |"
        )

        self.assertTrue(_looks_like_complete_market_flow_report(valid_report))
        self.assertTrue(
            _looks_like_complete_market_flow_report(
                "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
                "一、市场结构与量价诊断\n趋势导语。\n\n"
                "二、交易确认与执行计划\n执行导语。\n\n"
                "三、关键价位与条件情景推演\n情景导语。"
            )
        )
        self.assertFalse(
            _looks_like_complete_market_flow_report(
                "数据已获取完毕，现在整合所有信息撰写报告。"
            )
        )
        self.assertFalse(
            _looks_like_complete_market_flow_report(
                "概述：趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
                "一、市场结构与量价诊断\n趋势导语。\n\n"
                "二、交易确认与执行计划\n执行导语。\n\n"
                "三、关键价位与条件情景推演\n情景导语。\n\n"
                "四、综合结论和指标总览\n偏多配置。"
            )
        )
        self.assertFalse(
            _looks_like_complete_market_flow_report(
                "本报告对159949.SZ进行市场与资金流分析，聚焦量价结构和执行质量。\n\n"
                "一、市场结构与量价诊断\n趋势导语。\n\n"
                "二、交易确认与执行计划\n执行导语。\n\n"
                "三、关键价位与条件情景推演\n情景导语。\n\n"
                "四、综合结论和指标总览\n偏多配置。"
            )
        )
        self.assertFalse(
            _looks_like_complete_market_flow_report(
                "一、市场结构与量价诊断\n趋势偏多。\n\n二、交易确认与执行计划\n执行。\n\n三、关键价位与条件情景推演\n情景。\n\n四、综合结论和指标总览\n偏多。"
            )
        )

    def test_market_flow_spec_marks_missing_tail_markers_without_failing_shape_gate(self):
        report = (
            "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n趋势导语。\n\n"
            "二、交易确认与执行计划\n执行导语。\n\n"
            "三、关键价位与条件情景推演\n情景导语。"
        )

        verdict = static_validate(report, _REPORT_SPEC)

        self.assertTrue(_looks_like_complete_market_flow_report(report))
        self.assertTrue(any("缺少一级章节『四、…』" in item for item in verdict.missing_elements))
        self.assertTrue(any("综合结论和指标总览" in item for item in verdict.missing_elements))

    def test_market_flow_tail_normalizer_inserts_missing_hard_headings(self):
        report = (
            "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n趋势导语。\n\n"
            "二、交易确认与执行计划\n执行导语。\n\n"
            "三、关键价位与条件情景推演\n情景导语。\n\n"
            "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| MACD | 1 | 上方 | 动能改善 | 下穿转弱 |\n\n"
            "综合结论：偏多配置，等待回踩确认。"
        )

        normalized = _normalize_market_flow_tail_sections(report)

        self.assertIn("\n四、综合结论和指标总览\n\n偏多配置，等待回踩确认。", normalized)
        self.assertIn("\n\n| 指标 |", normalized)
        self.assertNotIn("\n指标总览\n", normalized)
        self.assertNotIn("\n综合结论\n", normalized)

    def test_market_flow_tail_normalizer_keeps_combined_tail_heading_once(self):
        report = (
            "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n趋势导语。\n\n"
            "二、交易确认与执行计划\n执行导语。\n\n"
            "三、关键价位与条件情景推演\n情景导语。\n\n"
            "四、综合结论和指标总览\n\n"
            "偏多配置，等待回踩确认。\n\n"
            "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| MACD | 1 | 上方 | 动能改善 | 下穿转弱 |"
        )

        normalized = _normalize_market_flow_tail_sections(report)
        normalized_again = _normalize_market_flow_tail_sections(normalized)

        self.assertEqual(1, normalized.count("四、综合结论和指标总览"))
        self.assertIn("\n四、综合结论和指标总览\n\n偏多配置，等待回踩确认。", normalized)
        self.assertIn("\n\n| 指标 |", normalized)
        self.assertEqual(normalized, normalized_again)

    def test_market_flow_tail_normalizer_converts_inline_conclusion_without_table(self):
        report = (
            "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n趋势导语。\n\n"
            "二、交易确认与执行计划\n执行导语。\n\n"
            "三、关键价位与条件情景推演\n情景导语。\n\n"
            "综合结论：偏多配置，等待回踩确认。"
        )

        normalized = _normalize_market_flow_tail_sections(report)

        self.assertIn("\n四、综合结论和指标总览\n\n偏多配置，等待回踩确认。", normalized)
        self.assertNotIn("综合结论：", normalized)

    def test_market_flow_node_normalizes_tail_headings_when_content_exists(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)
        incomplete_report = (
            "趋势和资金流同步改善，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n"
            "趋势导语。\n\n"
            "二、交易确认与执行计划\n"
            "执行导语。\n\n"
            "三、关键价位与条件情景推演\n"
            "情景导语。\n\n"
            "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| MACD | 1 | 上方 | 动能改善 | 下穿转弱 |\n\n"
            "综合结论：偏多配置，等待回踩确认。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=incomplete_report), incomplete_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst.validate_and_refine",
            side_effect=lambda report, *_args, **_kwargs: report,
        ):
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        self.assertIn("趋势和资金流同步改善", result["market_flow_report"])
        self.assertIn(
            "\n四、综合结论和指标总览\n\n偏多配置，等待回踩确认。",
            result["market_flow_report"],
        )
        self.assertIn("\n\n| 指标 |", result["market_flow_report"])
        self.assertNotIn("\n指标总览\n", result["market_flow_report"])
        self.assertNotIn("\n综合结论\n", result["market_flow_report"])

    def test_market_flow_node_warns_when_tail_elements_remain_missing(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)
        incomplete_report = (
            "趋势和资金流同步改善，MACD与RSI均显示动能仍偏强，当前交易含义是等待回踩确认后分批加仓。\n\n"
            "一、市场结构与量价诊断\n"
            "趋势导语。\n\n"
            "二、交易确认与执行计划\n"
            "执行导语。\n\n"
            "三、关键价位与条件情景推演\n"
            "情景导语。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=incomplete_report), incomplete_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst.validate_and_refine",
            side_effect=lambda report, *_args, **_kwargs: report,
        ), self.assertLogs(
            "etfagents.agents.analysts.etf_market_analyst",
            level="WARNING",
        ) as logs:
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        self.assertEqual(incomplete_report, result["market_flow_report"])
        self.assertTrue(any("四、" in line for line in logs.output))
        self.assertTrue(any("综合结论和指标总览" in line for line in logs.output))


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

    def test_top_holdings_cleaning_removes_delivery_preamble_and_bold_title(self):
        report = (
            "数据已全部获取完毕，现在撰写完整报告。\n\n"
            "**ETF头部持仓分析报告：561360.SH 石油ETF国泰**\n\n"
            "券商个股研究显示上游现金流与炼化亏损形成分歧。\n\n"
            "一、核心持仓共识与分歧\n"
            "正文内容。"
        )

        cleaned = clean_generated_report(report)

        self.assertNotIn("数据已全部获取完毕", cleaned)
        self.assertNotIn("ETF头部持仓分析报告", cleaned)
        self.assertTrue(cleaned.startswith("券商个股研究显示"))

    def test_strip_refine_preamble_removes_prompt_echo_and_box_lines(self):
        report = (
            "以下是根据评审标准修正后的完整报告，直接陈述核心结论并补充第三部分导语，保留原有正确分析与数据。                                                               │\n"
            "│                                                                                                                                                                 │\n"
            "│  -------------------------------------------------------------------------------------------------------------------------------------------------------------\n"
            "价格仍站在20日均线上方，短线结构未被破坏。"
        )
        cleaned = strip_refine_preamble(report)
        self.assertEqual(cleaned, "价格仍站在20日均线上方，短线结构未被破坏。")

    def test_clean_generated_report_removes_chapter_meta_opener(self):
        report = (
            "本章旨在梳理当前新能源产业链的核心投资逻辑与市场认知差异。"
            "通过对机构共识的提炼与关键分歧点的拆解，明确周期位置与未来演绎路径，"
            "为后续景气验证与风险定价提供基准框架。\n\n"
            "新能源链条的订单兑现和价格止跌才是ETF配置节奏的核心变量。"
        )

        cleaned = clean_generated_report(report)

        self.assertNotIn("本章旨在", cleaned)
        self.assertNotIn("机构共识的提炼", cleaned)
        self.assertTrue(cleaned.startswith("新能源链条的订单兑现"))

    def test_clean_generated_report_removes_combined_format_artifacts(self):
        report = (
            "以下是根据评审标准修正后的完整报告，直接陈述核心结论并补充第三部分导语，保留原有正确分析与数据。                                                               │\n"
            "│                                                                                                                                                                 │\n"
            "│  -------------------------------------------------------------------------------------------------------------------------------------------------------------\n"
            "直接进入正文。\n"
            "# 技术面与资金流综合诊断\n\n"
            "本报告将围绕当前ETF的量价结构和资金流给出判断。\n"
            "本报告对515220.SH煤炭ETF国泰进行截至2026年4月30日的宏观与配置分析。\n"
            "结论：偏多，但短线不宜追高。\n"
            "价格仍站在20日均线上方，MACD维持在零轴上方，趋势仍偏强。\n\n"
            "一、市场结构与量价诊断\n\n"
            "本节核心结论指出趋势仍未走坏。\n"
            "正文内容。"
        )
        cleaned = clean_generated_report(report)
        self.assertTrue(cleaned.startswith("偏多，但短线不宜追高。"))
        self.assertNotIn("以下是根据评审标准修正后的完整报告", cleaned)
        self.assertNotIn("直接进入正文", cleaned)
        self.assertNotIn("# 技术面与资金流综合诊断", cleaned)
        self.assertNotIn("本报告将围绕", cleaned)
        self.assertNotIn("本报告对515220.SH", cleaned)
        self.assertNotIn("结论：偏多", cleaned)
        self.assertNotIn("本节核心结论指出", cleaned)
        self.assertIn("价格仍站在20日均线上方，MACD维持在零轴上方，趋势仍偏强。", cleaned)
        self.assertIn("正文内容。", cleaned)

    def test_clean_generated_report_removes_remaining_format_markers(self):
        report = (
            "核心结论：偏多，但不宜追高。\n"
            "概述：煤价下行仍压制煤炭ETF风险溢价。\n"
            "（关键技术指标交易含义速览：MACD 金叉代表动能增强）\n"
            "本章节导语：价格仍站在20日均线上方？\n"
            "这意味着什么：趋势尚未破坏？\n"
            "对交易应该怎么做：等待回踩确认后再加仓。\n"
        )
        cleaned = clean_generated_report(report)
        self.assertNotIn("核心结论：", cleaned)
        self.assertNotIn("概述：", cleaned)
        self.assertNotIn("（关键技术指标交易含义速览", cleaned)
        self.assertNotIn("本章节导语", cleaned)
        self.assertNotIn("这意味着什么", cleaned)
        self.assertNotIn("对交易应该怎么做", cleaned)
        self.assertIn("偏多，但不宜追高。", cleaned)
        self.assertIn("煤价下行仍压制煤炭ETF风险溢价。", cleaned)
        self.assertIn("价格仍站在20日均线上方。", cleaned)
        self.assertIn("趋势尚未破坏。", cleaned)
        self.assertIn("等待回踩确认后再加仓。", cleaned)

    def test_clean_generated_report_removes_markdown_heading_labels_for_all_analysts(self):
        report = (
            "### 章节导语\n"
            "盈利修复正在从龙头向产业链扩散。\n\n"
            "### 信号总结：订单与现金流同步改善。\n"
            "### 这意味着什么？行业景气度仍在上行。\n"
            "### 交易该怎么做？优先等待回踩确认，再分批布局。\n"
        )
        cleaned = clean_generated_report(report)
        self.assertNotIn("### 章节导语", cleaned)
        self.assertNotIn("### 信号总结", cleaned)
        self.assertNotIn("### 这意味着什么", cleaned)
        self.assertNotIn("### 交易该怎么做", cleaned)
        self.assertNotIn("### ", cleaned)
        self.assertIn("盈利修复正在从龙头向产业链扩散。", cleaned)
        self.assertIn("订单与现金流同步改善。", cleaned)
        self.assertIn("行业景气度仍在上行。", cleaned)
        self.assertIn("优先等待回踩确认，再分批布局。", cleaned)

    def test_post_judge_clean_removes_section_lead_heading_without_merging_lines(self):
        report = (
            "一、行业主线与分歧焦点\n"
            "### 章节导语\n"
            "盈利修复正在从龙头向产业链扩散。\n"
        )
        cleaned = post_judge_clean(report)
        self.assertNotIn("章节导语", cleaned)
        self.assertNotIn("###", cleaned)
        self.assertIn("一、行业主线与分歧焦点\n盈利修复正在从龙头向产业链扩散。", cleaned)

    def test_post_judge_clean_splits_intro_paragraph_and_inline_subheading(self):
        report = (
            "一、核心持仓共识与分歧\n"
            "短期扰动更多来自交易层噪声而非基本面失速。  ## （一）主线共识\n"
            "多数券商仍将盈利兑现视为主线。\n"
        )
        cleaned = post_judge_clean(report)
        self.assertIn("短期扰动更多来自交易层噪声而非基本面失速。\n（一）主线共识", cleaned)
        self.assertNotIn("失速。  ## （一）", cleaned)
        self.assertNotIn("失速。  （一）", cleaned)
        self.assertNotIn("## （一）", cleaned)

    def test_post_judge_clean_removes_opening_parenthetical_term_explanations(self):
        report = (
            "铜与热卷需求能否驱动焦煤仓单去化，是本轮中观判断的核心路标"
            "（仓单是指交易所注册库存，用来衡量现货压力）。若去化不能兑现，首要动作应是减仓。\n\n"
            "一、核心矛盾与主线判断\n"
            "制造业需求与上游成本正在争夺利润分配。"
        )

        cleaned = post_judge_clean(report)

        self.assertNotIn("（仓单是指交易所注册库存，用来衡量现货压力）", cleaned)
        self.assertIn("核心路标。若去化不能兑现", cleaned)
        self.assertIn("一、核心矛盾与主线判断", cleaned)



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
        self.assertIn("不得使用'本章''本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Do NOT narrate your workflow, tool usage", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一、暴露与宏观主线", system_msg)
        self.assertIn("标题后直接写2-3句结论段", system_msg)
        self.assertNotIn("以2-3句导语开头", system_msg)
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
        self.assertIn("不得使用'本章''本节''本部分''该部分''这一节'等自指式开头", system_msg)
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("Do NOT narrate your workflow, tool usage", system_msg)
        self.assertNotIn("## 数据来源（已获取，直接使用）", system_msg)
        self.assertNotIn("## 分析指引", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("一、情绪主线与权重影响", system_msg)
        self.assertIn("标题后直接写2-3句结论段", system_msg)
        self.assertNotIn("以2-3句导语开头", system_msg)
        self.assertNotIn("一、情绪主线与权重影响 (", system_msg)
        self.assertIn("Do NOT substitute generic labels such as '总体研判'", system_msg)
        self.assertIn("Do NOT output code blocks, JSON, dictionary mappings", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)

    def test_catalyst_sentiment_acceptance_rejects_delivery_preamble(self):
        valid_report = (
            "宏观新闻和重仓股事件对ETF形成中性偏谨慎影响，真实支撑仍需等待行业催化同步扩散。\n\n"
            "一、情绪主线与权重影响\n"
            "（一）产品情绪与讨论强弱\n"
            "报告内容。\n\n"
            "二、事件传导与定价辨别\n"
            "（一）宏观事件传导\n"
            "报告内容。\n"
            "（二）真实支撑与短期噪声\n"
            "报告内容。\n\n"
            "三、后续触发与验证要点\n"
            "（一）后续监控要点\n"
            "报告内容。\n\n"
            "四、结论与跟踪表\n"
            "| 事件 | ETF影响 | 跟踪表 |\n"
            "| --- | --- | --- |\n"
            "| 宏观新闻 | 中性 | 继续观察 |"
        )

        self.assertTrue(_looks_like_complete_catalyst_sentiment_report(valid_report))
        self.assertFalse(
            _looks_like_complete_catalyst_sentiment_report(
                "报告已就绪。以下为ETF催化剂与情绪分析：\n\n" + valid_report
            )
        )




if __name__ == "__main__":
    unittest.main()
