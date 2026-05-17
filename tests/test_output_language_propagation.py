import copy
import unittest
from unittest.mock import MagicMock

from cli.main import format_research_team_history, format_risk_management_history
from etfagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderProposal,
    _format_trader_numbered_blocks,
    _split_trader_heading_and_body,
    render_portfolio_decision,
    render_research_plan,
    render_trader_proposal,
)
from etfagents.agents.managers.portfolio_manager import create_portfolio_manager
from etfagents.agents.managers.research_manager import create_research_manager
from etfagents.agents.researchers.bear_researcher import create_bear_researcher
from etfagents.agents.researchers.bull_researcher import create_bull_researcher
from etfagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from etfagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from etfagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from etfagents.agents.trader.trader import create_trader
from etfagents.agents.utils.agent_utils import (
    get_localized_final_proposal_instruction,
    normalize_chinese_manager_terms,
    normalize_chinese_role_terms,
    normalize_visible_debate_body,
)
from etfagents.dataflows.config import get_config, set_config
from etfagents.default_config import DEFAULT_CONFIG


class _FakeResponse:
    def __init__(self, content="ok"):
        self.content = content


class _CapturingLLM:
    def __init__(self):
        self.calls = []
        self.structured_calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        return _FakeResponse(
            "测试输出\n"
            "决策摘要:\n"
            "- 评级: 持有\n"
            "- 置信度: 60%\n"
            "- 时间区间: 1-3个月\n"
            "- 关键假设:\n"
            "  1. 需求平稳。\n"
            "  2. 波动可控。\n"
            "  3. 等待验证。\n"
            "反馈快照:\n"
            "- 当前观点: x\n"
            "- 发生了什么变化: y\n"
            "- 为什么变化: z\n"
            "- 关键反驳: r\n"
            "- 下一轮教训: l"
        )

    def with_structured_output(self, schema):
        parent = self

        class _StructuredInvoker:
            def invoke(self, prompt):
                parent.structured_calls.append(prompt)
                if schema is TraderProposal:
                    return TraderProposal(
                        thesis="交易逻辑测试。",
                        execution_plan="1. 等待确认后分批执行。",
                        risk_management="跌破关键位就减仓，并继续跟踪成交量。",
                        rating=PortfolioRating.HOLD,
                    )
                if schema is ResearchPlan:
                    return ResearchPlan(
                        debate_conclusion="多空双方都提出了有效证据，但多头证据略强。",
                        action_logic="估值仍需消化，但催化节奏与盈利兑现共同支持保留上行敞口。",
                        positioning_recommendation="维持增持，等待确认后分批加仓，并跟踪风险边界。",
                        rating=PortfolioRating.OVERWEIGHT,
                        snapshot_stance="增持",
                        snapshot_new_and_rebuttal="本轮补充了盈利兑现与估值约束之间的平衡关系。",
                        snapshot_to_verify="继续跟踪订单、毛利率与资本开支。",
                    )
                if schema is PortfolioDecision:
                    return PortfolioDecision(
                        debate_conclusion="保守与中性观点限制了仓位，但激进观点提供了上行线索。",
                        action_logic="在估值、催化节奏与仓位约束之间平衡后，当前更适合维持中性偏积极配置。",
                        positioning_recommendation="先保留基础仓位，确认催化后再加仓，并设置回撤风控。",
                        rating=PortfolioRating.HOLD,
                        snapshot_stance="持有",
                        snapshot_new_and_rebuttal="新增了对仓位节奏与风险预算的约束。",
                        snapshot_to_verify="继续跟踪波动率、资金流和业绩兑现。",
                    )
                raise AssertionError(f"Unexpected schema: {schema}")

        return _StructuredInvoker()


class _EmptyMemory:
    def get_memories(self, *_args, **_kwargs):
        return []


class _MemoryWithLessons:
    def get_memories(self, *_args, **_kwargs):
        return [{"recommendation": "Keep sizing small until demand confirms."}]


class OutputLanguagePropagationTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        self.base_state = {
            "company_of_interest": "002155.SZ",
            "trade_date": "2026-04-28",
            "past_context": "",
            "investment_plan": "Plan",
            "market_report": "Market report",
            "sentiment_report": "Sentiment report",
            "news_report": "News report",
            "fundamentals_report": "Fundamentals report",
            "research_report": "",
            "stock_report": "",
            "trader_investment_plan": "Trader plan",
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
                "debate_brief": "",
                "judge_decision": "",
                "judge_snapshot": "",
                "judge_snapshot_path": "",
                "count": 0,
            },
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
                "count": 0,
            },
        }

    def tearDown(self):
        set_config(self.original_config)

    def test_trader_prompt_respects_output_language(self):
        llm = _CapturingLLM()
        node = create_trader(llm)
        node(self.base_state)

        system_prompt = llm.structured_calls[0][0]["content"]
        self.assertIn("Write your entire response in Chinese.", system_prompt)
        self.assertIn("ETF", system_prompt)
        self.assertIn("时机", system_prompt)
        self.assertIn("关键支撑", system_prompt)
        self.assertIn("成交量", system_prompt)
        self.assertIn("份额变化", system_prompt)
        self.assertIn("若没有上方报告里的具体价位、均线数值、量能基数或份额/溢折价数据，就不要下加仓、减仓或回补指令", system_prompt)
        self.assertIn("所有执行动作的对象必须是ETF整体仓位或ETF目标权重", system_prompt)
        self.assertIn("The three sections must open with DIFFERENT sentences", system_prompt)
        self.assertIn("do not mention sizing, levels, or execution steps", system_prompt)
        self.assertIn("do not restate the thesis rationale", system_prompt)
        self.assertIn("failure conditions, rebalance triggers, cut or restore rules", system_prompt)

    def test_research_manager_prompt_respects_output_language(self):
        llm = _CapturingLLM()
        node = create_research_manager(llm, _EmptyMemory())
        node(self.base_state)

        prompt = llm.structured_calls[0]
        self.assertIn("Write your entire response in Chinese.", prompt)
        self.assertIn("多头分析师", prompt)
        self.assertIn("空头分析师", prompt)
        self.assertIn("买入", prompt)
        self.assertIn("持有", prompt)
        self.assertIn("市场与资金流分析", prompt)
        self.assertIn("舆情与事件影响分析", prompt)
        self.assertIn("ETF持仓行业研究", prompt)
        self.assertIn("ETF头部持仓研究", prompt)
        self.assertIn("所有执行动作只能针对ETF整体仓位或ETF目标权重", prompt)
        self.assertIn("催化节奏", prompt)
        self.assertNotIn("catalyst timing", prompt)

    def test_bull_bear_researcher_prompts_require_chinese_body_and_decision_summary(self):
        for factory in (create_bull_researcher, create_bear_researcher):
            llm = _CapturingLLM()
            node = factory(llm, _EmptyMemory())
            node(self.base_state)

            prompt = llm.calls[0]
            self.assertIn("written entirely in Chinese", prompt)
            self.assertIn("决策摘要", prompt)
            self.assertNotIn("Internal lessons from similar situations", prompt)
            self.assertIn("Write your entire response in Chinese.", prompt)
            self.assertIn("Do not use variants like", prompt)
            self.assertIn("牛派分析师", prompt)
            self.assertIn("熊派分析师", prompt)
            self.assertIn("反馈快照", prompt)
            self.assertIn("关键约束", prompt)

    def test_portfolio_manager_prompt_includes_past_context_only_when_present(self):
        llm = _CapturingLLM()
        state = copy.deepcopy(self.base_state)
        state["past_context"] = "Past analyses of 002155.SZ:\n[2026-01-10 | 002155.SZ | Hold | +2.0% | +0.5% | 5d]"
        node = create_portfolio_manager(llm, _EmptyMemory())
        node(state)

        prompt = llm.structured_calls[0]
        self.assertIn("历史决策复盘", prompt)
        self.assertIn("Past analyses of 002155.SZ", prompt)

    def test_research_team_history_keeps_real_snapshot_blocks(self):
        llm = _CapturingLLM()
        node = create_bull_researcher(llm, _EmptyMemory())

        investment_debate_state = node(copy.deepcopy(self.base_state))["investment_debate_state"]
        formatted = format_research_team_history(investment_debate_state)

        self.assertIn("决策摘要:", formatted)
        self.assertIn("- 评级: 持有", formatted)
        self.assertNotIn("##### 本轮复盘", formatted)
        self.assertNotIn("##### 自动复盘", formatted)
        self.assertNotIn("- 立场: x", formatted)
        self.assertNotIn("反馈快照", formatted)
        self.assertNotIn("决策摘要", investment_debate_state["current_bull_response"])
        self.assertNotIn("反馈快照", investment_debate_state["current_bull_response"])

    def test_bull_researcher_visible_body_strips_markdown_decorations(self):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse(
            "**核心判断：** 多头主线仍占优。\n"
            "## 证据展开\n"
            "需求修复与份额扩张正在同步改善。\n\n"
            "决策摘要:\n"
            "- 评级: 增持\n"
            "- 置信度: 75%\n"
            "- 时间区间: 3-6个月\n"
            "- 关键假设:\n"
            "  1. 需求继续改善。\n"
            "  2. 份额维持净申购。\n"
            "  3. 回撤可控。\n\n"
            "反馈快照:\n"
            "- 立场: 增持\n"
            "- 本轮新增与反驳: 强化了需求与份额共振。\n"
            "- 待验证: 继续跟踪成交量和份额变化。"
        )

        result = create_bull_researcher(llm, _EmptyMemory())(copy.deepcopy(self.base_state))
        body = result["investment_debate_state"]["current_bull_response"]
        formatted = format_research_team_history(result["investment_debate_state"])

        self.assertNotIn("**", body)
        self.assertNotIn("##", body)
        self.assertIn("核心判断： 多头主线仍占优。", body)
        self.assertNotIn("**", formatted)
        self.assertNotIn("## 证据展开", formatted)

    def test_normalize_chinese_role_terms_replaces_display_variants(self):
        text = "我是熊派分析师，也不同意牛派分析师、激进分析师、保守分析师、中性分析师、熊派投资者和根本分析的说法。"
        normalized = normalize_chinese_role_terms(text)

        self.assertNotIn("熊派分析师", normalized)
        self.assertNotIn("牛派分析师", normalized)
        self.assertNotIn("激进分析师", normalized)
        self.assertNotIn("保守分析师", normalized)
        self.assertNotIn("中性分析师", normalized)
        self.assertNotIn("熊派投资者", normalized)
        self.assertNotIn("根本分析", normalized)
        self.assertIn("空头分析师", normalized)
        self.assertIn("多头分析师", normalized)
        self.assertIn("激进风险分析师", normalized)
        self.assertIn("保守风险分析师", normalized)
        self.assertIn("中性风险分析师", normalized)
        self.assertIn("空头投资者", normalized)
        self.assertIn("基本面分析", normalized)

    def test_normalize_chinese_role_terms_preserves_standalone_markdown_headings(self):
        normalized = normalize_chinese_role_terms(
            "正文上一行。\n"
            "### （一）评级\n"
            "研究结论: **持有**"
        )

        self.assertIn("正文上一行。\n### （一）评级", normalized)
        self.assertIn("研究结论: **持有**", normalized)

    def test_risk_team_prompts_respect_output_language(self):
        for factory in (
            create_aggressive_debator,
            create_conservative_debator,
            create_neutral_debator,
        ):
            llm = _CapturingLLM()
            node = factory(llm)
            node(self.base_state)

            prompt = llm.calls[0]
            self.assertIn("Write your entire response in Chinese.", prompt)
            self.assertIn("决策摘要", prompt)
            self.assertIn("反馈快照", prompt)
            self.assertIn("关键约束", prompt)

    def test_neutral_risk_analyst_body_is_paragraphized(self):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse(
            "当前更适合维持中性偏谨慎仓位，因为上行催化尚未形成连续验证。"
            "虽然价格没有失速，但量能与资金流共振仍然不足。"
            "如果过早追高，组合会在宏观扰动重新放大时暴露更高回撤。"
            "因此更合理的做法是等待价格、量能和产业验证同步改善后再扩大敞口。\n\n"
            "决策摘要:\n"
            "- 评级: 持有\n"
            "- 置信度: 60%\n"
            "- 时间区间: 1-3个月\n"
            "- 关键假设:\n"
            "  1. 需求平稳。\n"
            "  2. 波动可控。\n"
            "  3. 等待验证。\n\n"
            "反馈快照:\n"
            "- 立场: 持有\n"
            "- 本轮新增与反驳: 补充了量价和回撤约束。\n"
            "- 待验证: 继续跟踪量能、资金流和产业数据。"
        )

        result = create_neutral_debator(llm)(copy.deepcopy(self.base_state))
        body = result["risk_debate_state"]["current_neutral_response"]

        self.assertIn("\n\n", body)
        self.assertIn("量能与资金流共振仍然不足。", body)
        self.assertIn("因此更合理的做法是等待价格、量能和产业验证同步改善后再扩大敞口。", body)

    def test_risk_team_history_keeps_real_snapshot_blocks(self):
        llm = _CapturingLLM()
        node = create_aggressive_debator(llm)

        risk_debate_state = node(copy.deepcopy(self.base_state))["risk_debate_state"]
        formatted = format_risk_management_history(risk_debate_state)

        self.assertIn("决策摘要:", formatted)
        self.assertIn("- 评级: 持有", formatted)
        self.assertNotIn("##### 本轮复盘", formatted)
        self.assertNotIn("##### 自动复盘", formatted)
        self.assertNotIn("- 立场: x", formatted)
        self.assertNotIn("反馈快照", formatted)
        self.assertNotIn("决策摘要", risk_debate_state["current_aggressive_response"])
        self.assertNotIn("反馈快照", risk_debate_state["current_aggressive_response"])

    def test_aggressive_risk_visible_body_strips_sentence_numbering(self):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse(
            "1. 价格重新站上20日均线后，进攻仓位的赔率明显改善。\n"
            "2. ETF份额恢复净申购，说明资金回流已经开始验证主线。\n"
            "3. 若成交量继续放大，激进仓位可以继续上调。\n\n"
            "决策摘要:\n"
            "- 评级: 增持\n"
            "- 置信度: 70%\n"
            "- 时间区间: 1-3个月\n"
            "- 关键假设:\n"
            "  1. 量价继续共振。\n"
            "  2. 资金流不再转弱。\n"
            "  3. 催化维持兑现。\n\n"
            "反馈快照:\n"
            "- 立场: 增持\n"
            "- 本轮新增与反驳: 补充了量价与份额验证。\n"
            "- 待验证: 继续跟踪成交量、份额变化和催化兑现。"
        )

        result = create_aggressive_debator(llm)(copy.deepcopy(self.base_state))
        body = result["risk_debate_state"]["current_aggressive_response"]
        formatted = format_risk_management_history(result["risk_debate_state"])
        visible_before_summary = formatted.split("决策摘要:")[0]

        self.assertNotIn("1. 价格重新站上20日均线后", body)
        self.assertNotIn("2. ETF份额恢复净申购", body)
        self.assertIn("价格重新站上20日均线后，进攻仓位的赔率明显改善。", body)
        self.assertIn("\n\n", body)
        self.assertNotIn("1. 价格重新站上20日均线后", visible_before_summary)
        self.assertIn("  1. 量价继续共振。", formatted)

    def test_risk_visible_body_splits_inline_chinese_headings(self):
        body = normalize_visible_debate_body(
            "## 一、宏观定价与产业周期的激进共振 ## （一）实际利率高企非压制而是洗盘"
        )

        self.assertIn(
            "一、宏观定价与产业周期的激进共振\n\n（一）实际利率高企非压制而是洗盘",
            body,
        )
        self.assertNotIn("共振 （一）", body)
        self.assertNotIn("##", body)

    def test_visible_debate_body_promotes_inline_numbered_sentence_to_heading(self):
        body = normalize_visible_debate_body(
            "一、石油ETF看似拥有供给端支撑，实则正在被成本传导断裂反噬。"
            "你重点强调原油持仓增幅116.67%，但聚乙烯仓单暴增79.93%。"
        )

        self.assertIn(
            "一、石油ETF看似拥有供给端支撑，实则正在被成本传导断裂反噬\n\n"
            "你重点强调原油持仓增幅116.67%",
            body,
        )

    def test_visible_debate_body_strips_second_person_heading_prefix(self):
        body = normalize_visible_debate_body(
            "一、你的成本传导断裂叙事忽略了ETF独有的对冲结构。"
            "空头分析师反复强调聚乙烯仓单暴增。"
        )

        self.assertIn("一、成本传导断裂叙事忽略了ETF独有的对冲结构", body)
        self.assertNotIn("一、你的成本传导断裂叙事", body)

    def test_visible_debate_body_strips_empty_markdown_and_joins_soft_breaks(self):
        body = normalize_visible_debate_body(
            "**  \n"
            "第一，焦煤的库存堆积是钢铁产业链内部的产能调整，而非全社会用电需求的直接反映。\n"
            "当前电力需求的核心增长引擎早已切换至第三产业和居民端。"
        )

        self.assertNotIn("**", body)
        self.assertIn(
            "第一，焦煤的库存堆积是钢铁产业链内部的产能调整，而非全社会用电需求的直接反映。当前电力需求的核心增长引擎早已切换至第三产业和居民端。",
            body,
        )
        self.assertNotIn("直接反映。\n当前电力需求", body)

    def test_visible_debate_body_keeps_list_like_lines_after_soft_join(self):
        body = normalize_visible_debate_body(
            "当前电力需求仍在改善。\n"
            "- 但火电利润仍受煤价压制。"
        )

        self.assertIn("当前电力需求仍在改善。\n- 但火电利润仍受煤价压制。", body)
        self.assertNotIn("当前电力需求仍在改善。- 但火电利润", body)

    def test_portfolio_manager_prompt_respects_output_language(self):
        llm = _CapturingLLM()
        node = create_portfolio_manager(llm, _EmptyMemory())
        node(self.base_state)

        prompt = llm.structured_calls[0]
        self.assertIn("Write your entire response in Chinese.", prompt)
        self.assertIn("反馈快照", prompt)
        self.assertIn("激进风险分析师", prompt)
        self.assertIn("保守风险分析师", prompt)
        self.assertIn("中性风险分析师", prompt)
        self.assertIn("市场与资金流分析", prompt)
        self.assertIn("ETF持仓行业研究", prompt)
        self.assertIn("ETF头部持仓研究", prompt)
        self.assertIn("评级体系", prompt)
        self.assertIn("买入", prompt)
        self.assertIn("增持", prompt)
        self.assertIn("持有", prompt)
        self.assertIn("减持", prompt)
        self.assertIn("卖出", prompt)
        self.assertIn("## 辩论结论", prompt)
        self.assertIn("## 行为逻辑", prompt)
        self.assertIn("## 持仓建议", prompt)
        self.assertIn("关键约束", prompt)
        self.assertIn("所有执行动作的对象必须是这只ETF的整体仓位", prompt)
        self.assertNotIn("Lessons from past decisions", prompt)
        self.assertIn("催化节奏", prompt)
        self.assertNotIn("catalyst timing", prompt)

    def test_research_plan_rendering_drops_conflicting_recommendation_text(self):
        rendered = render_research_plan(
            ResearchPlan(
                debate_conclusion="综合证据偏中性。",
                action_logic="仍需等待更多确认信号。",
                positioning_recommendation="针对300308.SZ，建议采取减持策略。继续跟踪订单兑现与估值消化。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对订单兑现节奏的约束。",
                snapshot_to_verify="继续跟踪订单、毛利率和需求恢复。",
            )
        )

        self.assertIn("### （一）评级", rendered)
        self.assertIn("### （二）建议", rendered)
        self.assertIn("研究结论: **持有**", rendered)
        self.assertNotIn("建议采取减持策略", rendered)
        self.assertIn("继续跟踪订单兑现与估值消化", rendered)
        self.assertNotIn("\n\n\n", rendered)

    def test_portfolio_decision_rendering_keeps_single_consistent_rating(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="多空争议仍在，但上行逻辑更完整。",
                action_logic="在催化明确前仍需控制仓位节奏。",
                positioning_recommendation="建议评级: 减持\n等待催化确认后再分批布局。",
                rating=PortfolioRating.BUY,
                snapshot_stance="减持",
                snapshot_new_and_rebuttal="新增了对催化节奏的拆解。",
                snapshot_to_verify="继续跟踪成交量、订单和毛利率。",
            )
        )

        self.assertIn("### （一）评级", rendered)
        self.assertIn("### （二）建议", rendered)
        self.assertIn("研究结论: **买入**", rendered)
        self.assertIn("### （一）评级\n研究结论: **买入**", rendered)
        self.assertIn("研究结论: **买入**\n### （二）建议", rendered)
        self.assertIn("### （二）建议\n等待催化确认后再分批布局。", rendered)
        self.assertNotIn("建议评级: 减持", rendered)
        self.assertEqual(rendered.count("研究结论: **买入**"), 1)
        self.assertNotIn("反馈快照:\n- 立场: 减持", rendered)

    def test_research_plan_rendering_replaces_placeholder_sections(self):
        rendered = render_research_plan(
            ResearchPlan(
                debate_conclusion="评估双方论证强度，总结核心论点与致命弱点",
                action_logic="估值、催化节奏、下行边界与确认/证伪信号的推演路径",
                positioning_recommendation="明确评级与执行指引",
                rating=PortfolioRating.UNDERWEIGHT,
                snapshot_stance="减持",
                snapshot_new_and_rebuttal="本轮新增与反驳",
                snapshot_to_verify="待验证",
            )
        )

        self.assertIn("研究结论: **减持**", rendered)
        self.assertNotIn("评估双方论证强度，总结核心论点与致命弱点", rendered)
        self.assertNotIn("估值、催化节奏、下行边界与确认/证伪信号的推演路径", rendered)
        self.assertNotIn("明确评级与执行指引", rendered)
        self.assertNotIn("- 本轮新增与反驳: 本轮新增与反驳", rendered)
        self.assertNotIn("- 待验证: 待验证", rendered)

    def test_research_plan_rendering_expands_overly_brief_sections(self):
        rendered = render_research_plan(
            ResearchPlan(
                debate_conclusion="多头略强。",
                action_logic="等待验证。",
                positioning_recommendation="继续观察关键变量。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对订单兑现节奏的约束。",
                snapshot_to_verify="继续跟踪订单、毛利率和需求恢复。",
            )
        )

        self.assertIn("多头略强。", rendered)
        self.assertIn("由于现阶段还缺少能够打破平衡的新证据", rendered)
        self.assertIn("等待验证。", rendered)
        self.assertIn("当前的明确动作是持有", rendered)
        self.assertIn("盯住真正能改写结论的异象", rendered)
        self.assertNotIn("\n\n\n", rendered)

    def test_research_plan_rendering_enriches_positioning_recommendation(self):
        rendered = render_research_plan(
            ResearchPlan(
                debate_conclusion="多空证据仍在拉锯。",
                action_logic="先维持现有仓位，等待更多确认。",
                positioning_recommendation="维持持有，继续观察。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对份额变化的约束。",
                snapshot_to_verify="继续跟踪成交量、份额变化和盈利兑现。",
            )
        )

        self.assertIn("研究结论: **持有**", rendered)
        self.assertIn("继续观察。", rendered)
        self.assertIn("新增资金优先等待价格重新站稳关键支撑与均线", rendered)
        self.assertIn("按周度复核量价、份额变化、溢折价和宏观/行业验证信号", rendered)

    def test_trader_rendering_rewrites_conflicting_execution_plan(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前多空因素并存。",
                execution_plan="1. 分批减持：在当前价位区间减持持仓的30%至50%。",
                risk_management="继续跟踪关键支撑与业绩验证。",
                rating=PortfolioRating.HOLD,
            )
        )

        self.assertIn("执行倾向: **持有**", rendered)
        self.assertNotIn("分批减持", rendered)
        self.assertIn("维持当前仓位", rendered)
        self.assertNotIn("\n\n\n", rendered)

    def test_trader_rendering_expands_overly_brief_execution_plan(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前多空因素并存。",
                execution_plan="维持当前仓位，不主动追涨或杀跌；等待关键支撑企稳、成交量改善或新增催化落地后，再决定是否调整敞口。",
                risk_management="继续跟踪关键支撑与业绩验证。",
                rating=PortfolioRating.HOLD,
            )
        )

        self.assertIn("50日均线、布林中轨、前低或密集成交区", rendered)
        self.assertIn("较近5日均量放大15%—20%", rendered)
        self.assertIn("份额扩张、溢折价改善、资金流确认或放量突破", rendered)
        self.assertIn("20日均量的1.3倍以上", rendered)

    def test_trader_rendering_strengthens_simple_thesis(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前多空因素并存。",
                execution_plan="维持当前仓位，不主动追涨或杀跌；等待关键支撑企稳、成交量改善或新增催化落地后，再决定是否调整敞口。",
                risk_management="继续跟踪关键支撑与业绩验证。",
                rating=PortfolioRating.HOLD,
            )
        )

        self.assertIn("当前多空因素并存", rendered)
        self.assertIn("中期主线并未被证伪", rendered)
        self.assertIn("把真正的动作阈值留给执行计划", rendered)

    def test_trader_rendering_dedupes_overlap_with_execution_plan(self):
        repeated_sentence = "当前基准情形下，在具体的执行节奏上，159949.SZ面临宏观估值天花板与盈利质量拐点的双重压制，建议下调配置权重。"
        rendered = render_trader_proposal(
            TraderProposal(
                thesis=(
                    f"{repeated_sentence}"
                    "当前需要先承认主线压力尚未解除，再决定是否保留观察仓位。"
                ),
                execution_plan=(
                    f"{repeated_sentence}"
                    "若反弹无法收复50日均线且成交量仍低于20日均量，则继续分批降低敞口。"
                ),
                risk_management="若成交量异常放大且跌破关键支撑，则继续减仓。",
                rating=PortfolioRating.UNDERWEIGHT,
            )
        )

        self.assertEqual(rendered.count(repeated_sentence), 1)
        self.assertIn("当前风险释放节奏快于新增催化兑现速度", rendered)
        self.assertIn("若反弹无法收复50日均线且成交量仍低于20日均量，则继续分批降低敞口。", rendered)

    def test_trader_rendering_dedupes_overlap_with_risk_management(self):
        repeated_sentence = "当前基准情形下，在具体的执行节奏上，159949.SZ面临宏观估值天花板与盈利质量拐点的双重压制，建议下调配置权重。"
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前需要先承认主线压力尚未解除，再决定是否保留观察仓位。",
                execution_plan=(
                    f"{repeated_sentence}"
                    "若反弹无法收复50日均线且成交量仍低于20日均量，则继续分批降低敞口。"
                ),
                risk_management=(
                    f"{repeated_sentence}"
                    "若价格有效跌破关键支撑且单日放量达到20日均量的1.3倍以上，则先减掉20%—30%的试探仓位。"
                ),
                rating=PortfolioRating.UNDERWEIGHT,
            )
        )

        self.assertEqual(rendered.count(repeated_sentence), 1)
        self.assertIn("若价格有效跌破关键支撑且单日放量达到20日均量的1.3倍以上，则先减掉20%—30%的试探仓位。", rendered)
        self.assertIn("在减仓过程中重点看反弹强度、成交量结构和事件兑现进度", rendered)

    def test_trader_rendering_strips_redundant_section_headings(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="一、 配置核心逻辑",
                execution_plan="二、 交易执行计划",
                risk_management="三、 调仓与风控机制",
                rating=PortfolioRating.HOLD,
            )
        )

        self.assertNotIn("## ETF配置逻辑", rendered)
        self.assertIn("一、当前多空因素并存", rendered)
        self.assertEqual(rendered.count("二、配置执行计划"), 1)
        self.assertEqual(rendered.count("三、再平衡与风险控制"), 1)
        self.assertEqual(rendered.count("四、执行倾向"), 1)
        self.assertNotIn("一、 配置核心逻辑", rendered)
        self.assertNotIn("二、 交易执行计划", rendered)
        self.assertNotIn("三、 调仓与风控机制", rendered)
        self.assertIn("执行倾向: **持有**", rendered)
        self.assertIn("维持当前仓位，不主动追涨或杀跌", rendered)

    def test_trader_rendering_uses_capped_substantive_thesis_heading(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis=(
                    "一、当前宏观压制边际缓和、行业盈利改善信号同步出现，偏多逻辑更完整。"
                    "资金流仍需确认，执行上不能追高。"
                ),
                execution_plan="先维持现仓，等待50日均线确认后再加仓。若跌破支撑则减仓。",
                risk_management="若成交量放大跌破支撑，则降低仓位。继续跟踪份额变化。",
                rating=PortfolioRating.OVERWEIGHT,
            )
        )

        self.assertIn("一、当前宏观压制边际缓和、行业盈利改善信号同步出现\n", rendered)
        self.assertIn("偏多逻辑更完整。", rendered)
        self.assertIn("资金流仍需确认，执行上不能追高。", rendered)
        self.assertNotIn("一、当前宏观压制边际缓和、行业盈利改善信号同步出现，偏多逻辑更完整。资金流", rendered)

    def test_split_trader_heading_and_body_keeps_short_single_sentence_thesis_as_heading_only(self):
        heading, body = _split_trader_heading_and_body("维持持有，等待确认。")

        self.assertEqual(heading, "维持持有，等待确认")
        self.assertEqual(body, "")

    def test_trader_rendering_splits_long_execution_paragraph_into_numbered_points(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前主线仍占优，但执行必须等待确认。",
                execution_plan=(
                    "先维持现有底仓并把新增仓位拆成两批执行。"
                    "若价格站稳50日均线且成交量回到20日均量上方，则加仓。"
                    "继续跟踪ETF份额、溢折价和资金流变化。"
                ),
                risk_management="若价格连续两天跌破关键支撑，则降低仓位。继续监控成交量。",
                rating=PortfolioRating.OVERWEIGHT,
            )
        )

        self.assertIn("1. 初始仓位与执行节奏", rendered)
        self.assertIn("2. 加仓触发条件", rendered)
        self.assertIn("跟踪验证与再平衡", rendered)
        self.assertIn("减仓触发的核心条件", rendered)

    def test_trader_numbered_blocks_reorder_buckets_into_canonical_execution_flow(self):
        rendered = _format_trader_numbered_blocks(
            "继续跟踪ETF份额、溢折价和资金流变化。"
            "若价格站稳50日均线且成交量回到20日均量上方，则加仓。"
            "若价格跌破关键支撑，则减仓。"
            "先保留底仓并分两批执行新增仓位。",
            "execution",
        )

        self.assertLess(rendered.index("1. 初始仓位与执行节奏"), rendered.index("2. 加仓触发条件"))
        self.assertLess(rendered.index("2. 加仓触发条件"), rendered.index("3. 减仓触发的核心条件"))
        self.assertLess(rendered.index("3. 减仓触发的核心条件"), rendered.index("4. 跟踪验证与再平衡"))

    def test_trader_rendering_preserves_single_bucket_content_when_only_initial_bucket_exists(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前主线仍占优，但执行必须等待确认。",
                execution_plan="先维持现仓，再按既定节奏逐步执行。",
                risk_management="若价格连续两天跌破关键支撑，则降低仓位。",
                rating=PortfolioRating.HOLD,
            )
        )

        self.assertIn("先维持现仓，再按既定节奏逐步执行。", rendered)

    def test_trader_rendering_expands_execution_plan_missing_price_anchor(self):
        rendered = render_trader_proposal(
            TraderProposal(
                thesis="当前主线未被证伪，但执行必须更看重量价与产品层确认。",
                execution_plan=(
                    "先以计划目标仓位的20%—30%建立试探仓，只有当价格重新站稳市场分析中给出的首个关键阻力/支撑转换位，"
                    "且成交量至少较近5日均量放大15%—20%并连续两个交易时段维持，才继续分批加仓。"
                ),
                risk_management="若跌破关键支撑且放量，则及时收缩仓位。",
                rating=PortfolioRating.BUY,
            ),
            context_text="10日均线452元、20日均线448元、50日均线443元。布林中轨449元。",
        )

        self.assertIn("50日均线443元", rendered)
        self.assertIn("日成交量连续2个交易日达到近20日均量的1.2—1.3倍", rendered)
        self.assertIn("ETF 份额继续净申购或溢折价不再走阔", rendered)
        self.assertNotIn("市场分析中给出的首个关键阻力/支撑转换位", rendered)

    def test_portfolio_decision_rendering_expands_vague_execution_guidance(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥，但主线尚未被证伪。",
                action_logic="当前的明确动作是持有，等待更扎实的量价与产品层验证后再决定是否扩大仓位。",
                positioning_recommendation="目标仓位先维持在15%至20%，等待关键位确认和成交量改善后再考虑分批加仓。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对仓位上限与验证链条的约束。",
                snapshot_to_verify="继续跟踪关键均线、成交量和份额变化。",
            )
        )

        self.assertIn("研究结论: **持有**", rendered)
        self.assertIn("成交量回到近期均量上方", rendered)
        self.assertIn("份额或资金流同步改善后再考虑上调一个档位", rendered)

    def test_portfolio_decision_rendering_rewrites_conflicting_reduce_guidance(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="保守风险分析师观点占优。",
                action_logic="当前技术破位与宏观去杠杆共振，立即执行分批减仓；若股价企稳再考虑回补。",
                positioning_recommendation="建议评级: 持有\n建议评级为减持。\n分批减持当前持仓的百分之三十至百分之五十。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对波动率与风险预算的约束。",
                snapshot_to_verify="继续跟踪关键支撑与成交量。",
            )
        )

        self.assertIn("研究结论: **持有**", rendered)
        self.assertEqual(rendered.count("研究结论: **持有**"), 1)
        self.assertNotIn("建议评级为减持", rendered)
        self.assertNotIn("分批减持当前持仓", rendered)
        self.assertIn("维持现有基准仓位", rendered)

    def test_portfolio_decision_catches_direct_conflict_after_conditional_clause(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥。",
                action_logic="当前仍以持有为主。",
                positioning_recommendation="若市场企稳则加仓，反之则立即卖出至零仓位。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对触发条件的约束。",
                snapshot_to_verify="继续跟踪量价变化。",
            )
        )

        self.assertNotIn("立即卖出至零仓位", rendered)
        self.assertIn("维持现有基准仓位", rendered)

    def test_portfolio_decision_rendering_expands_overly_brief_sections(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥。",
                action_logic="先别激进操作。",
                positioning_recommendation="保留基础仓位。",
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对波动率与风险预算的约束。",
                snapshot_to_verify="继续跟踪关键支撑与成交量。",
            )
        )

        self.assertIn("中性观点更稳妥。", rendered)
        self.assertIn("最稳妥的结论不是贸然加仓或减仓", rendered)
        self.assertIn("先别激进操作。", rendered)
        self.assertIn("当前的明确动作是持有", rendered)

    def test_portfolio_decision_strips_inline_duplicate_final_recommendation(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="多空比较后仍以产业修复和资金承接更占优。",
                action_logic="维持增配节奏，但每一步都必须绑定价格和资金流验证。",
                positioning_recommendation=(
                    "建议对516650.SH给予增持评级，在净值回落至2.08元支撑带时分批建立15%至20%的初始底仓。"
                    "加仓条件为MACD柱状图持续放大至0.0076以上且单日净流入超过1亿元。"
                    "风控措施严格设置1.97元硬性止损线，跌破则强制降仓50%。"
                    "最终配置建议: 增持。"
                ),
                rating=PortfolioRating.OVERWEIGHT,
                snapshot_stance="增持",
                snapshot_new_and_rebuttal="新增了对资金流与止损位的约束。",
                snapshot_to_verify="继续跟踪宏观数据、龙头矿企现金流和升贴水结构。",
            )
        )

        self.assertEqual(rendered.count("研究结论: **增持**"), 1)
        self.assertNotIn("最终配置建议: 增持。", rendered)
        self.assertIn("在净值回落至2.08元支撑带时分批建立15%至20%的初始底仓", rendered)

    def test_portfolio_decision_strips_restatement_sentence_and_awkward_ben_combo(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="综合宏观与产业共振证据，本组合对516160.SH的明确建议为增持。",
                action_logic="综合量价与份额变化，本组合当前更适合维持增配节奏。",
                positioning_recommendation=(
                    "综合宏观与产业共振证据，本组合对516160.SH的明确建议为增持。"
                    "目标仓位先控制在20%至25%，只有在价格重新站稳50日均线且成交量回到20日均量上方后再考虑继续加仓。"
                ),
                rating=PortfolioRating.OVERWEIGHT,
                snapshot_stance="增持",
                snapshot_new_and_rebuttal="新增了对量价与份额验证的约束。",
                snapshot_to_verify="继续跟踪50日均线、成交量和份额变化。",
            ),
            context_text="10日均线452元、20日均线448元、50日均线443元。布林中轨449元。",
        )

        self.assertEqual(rendered.count("研究结论: **增持**"), 1)
        self.assertNotIn("本组合对516160.SH的明确建议为增持", rendered)
        self.assertNotIn("本组合当前", rendered)
        self.assertNotIn("明确建议为增持", rendered)
        self.assertIn("当前组合更适合维持增配节奏", rendered)
        self.assertIn("目标仓位先控制在20%至25%", rendered)
        self.assertIn("50日均线443元", rendered)

    def test_portfolio_decision_removes_constituent_trade_instructions(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="谨慎观点更强，因为盈利下修和资金流转弱同时出现。",
                action_logic="当前应降低ETF整体目标仓位，并把回补条件绑定在价格和份额修复上。",
                positioning_recommendation=(
                    "当前应将仓位从偏多配置的4至5成降至2至3成（对应目标权重约25%），"
                    "优先减持极端估值标的：永泰能源（4.17%权重，PE 40至75倍）应全部清仓；"
                    "中国核电（7.91%权重，2026年一季度归母同比-34.19%）应减持至剩余权重约2%；"
                    "华能国际（3.28%）和上海电力（2.74%）等纯火电敞口应减持至剩余权重约1%。"
                    "保留长江电力（9.02%）、国投电力（3.61%）、川投能源（3.09%）等底仓。"
                ),
                rating=PortfolioRating.UNDERWEIGHT,
                snapshot_stance="减持",
                snapshot_new_and_rebuttal="新增了成分股盈利下修对ETF风险的解释。",
                snapshot_to_verify="继续跟踪ETF价格、份额和溢折价。",
            )
        )

        self.assertIn("目标权重约25%", rendered)
        self.assertNotIn("实际执行对象仍是ETF整体仓位", rendered)
        self.assertNotIn("优先减持极端估值标的", rendered)
        self.assertNotIn("永泰能源", rendered)
        self.assertNotIn("中国核电", rendered)
        self.assertNotIn("华能国际", rendered)
        self.assertNotIn("上海电力", rendered)
        self.assertNotIn("长江电力", rendered)
        self.assertNotIn("国投电力", rendered)
        self.assertNotIn("应全部清仓", rendered)
        self.assertNotIn("应减持至剩余权重", rendered)

    def test_portfolio_decision_keeps_legitimate_etf_parenthetical(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="多空因素均衡，当前更适合控制节奏。",
                action_logic="当前维持ETF目标仓位，并把后续调整绑定在价格和份额验证上。",
                positioning_recommendation=(
                    "建议在25%-30%区间持有这只ETF（对应基准配置约5%），"
                    "若价格重新站稳1.25元且份额连续2日净申购，再评估是否上调ETF仓位。"
                ),
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了ETF目标仓位约束。",
                snapshot_to_verify="继续跟踪ETF价格和份额。",
            )
        )

        self.assertIn("建议在25%-30%区间持有这只ETF（对应基准配置约5%）", rendered)
        self.assertNotIn("实际执行对象仍是ETF整体仓位", rendered)

    def test_manager_normalization_removes_constituent_trade_instructions(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "### （一）评级\n"
            "研究结论: **减持**\n"
            "### （二）建议\n"
            "当前将ETF目标仓位降至25%，优先减持极端估值标的："
            "永泰能源（4.17%权重，PE 40至75倍）应全部清仓；"
            "中国核电（7.91%权重，归母同比-34.19%）应减持至剩余权重约2%。\n\n"
            "反馈快照:\n"
            "- 立场: 减持\n"
            "- 本轮新增与反驳: 永泰能源（4.17%权重）应全部清仓。\n"
            "- 待验证: ETF价格和份额。"
        )

        self.assertIn("当前将ETF目标仓位降至25%", normalized)
        self.assertNotIn("实际执行对象仍是ETF整体仓位", normalized)
        self.assertNotIn("永泰能源", normalized)
        self.assertNotIn("中国核电", normalized)
        self.assertNotIn("应全部清仓", normalized)

    def test_portfolio_decision_rendering_strips_snapshot_leakage_from_positioning_recommendation(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥，但产业修复与资金承接尚未完全失效。",
                action_logic="维持基础仓位，同时把后续动作绑定在价格和资金流验证上。",
                positioning_recommendation=(
                    "目标仓位先维持在15%至20%，若净值回落至2.08元附近仍有承接，再考虑小幅回补。\n"
                    "反馈快照:\n"
                    "- 立场: 持有\n"
                    "- 本轮新增与反驳: 新增了对仓位上限与回补价位的约束。\n"
                    "- 待验证: 继续跟踪份额变化、成交量和净值承接。"
                ),
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对仓位上限与回补价位的约束。",
                snapshot_to_verify="继续跟踪份额变化、成交量和净值承接。",
            )
        )

        advice_section = rendered.split("### （二）建议\n", 1)[1].split("\n\n反馈快照:", 1)[0]
        self.assertIn("目标仓位先维持在15%至20%", advice_section)
        self.assertNotIn("本轮新增与反驳", advice_section)
        self.assertNotIn("待验证", advice_section)
        self.assertEqual(rendered.count("反馈快照:"), 1)

    def test_portfolio_decision_rendering_strips_prompt_leakage(self):
        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥，但产业修复与资金承接尚未完全失效。",
                action_logic="维持基础仓位，同时把后续动作绑定在价格和资金流验证上。",
                positioning_recommendation=(
                    "目标仓位先维持在15%至20%，若净值回落至2.08元附近仍有承接，再考虑小幅回补。\n"
                    "- Give a clear, actionable ETF portfolio recommendation—买入, 增持, 持有, 减持, or 卖出—grounded in the debate's strongest evidence.\n"
                    "- Include concrete execution guidance: target allocation band, add / reduce / rotate conditions, maximum initial sizing, rebalance triggers, risk controls, and what to monitor next.\n"
                    '- When writing in Chinese, avoid mixed English labels such as "Time Horizon", "Executive Summary", or "Investment Thesis".\n'
                    "- The rating, the positioning recommendation text, and the final transaction proposal must all point to the same action. Do not restate a conflicting recommendation in prose.\n"
                    "- Keep exactly one explicit final recommendation label in this section and make the rest of the paragraph explanatory rather than repetitive. 最终配置建议: 持有 。"
                ),
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对仓位上限与回补价位的约束。",
                snapshot_to_verify="继续跟踪份额变化、成交量和净值承接。",
            )
        )

        self.assertIn("研究结论: **持有**", rendered)
        self.assertIn("目标仓位先维持在15%至20%", rendered)
        self.assertNotIn("Give a clear, actionable ETF portfolio recommendation", rendered)
        self.assertNotIn("Time Horizon", rendered)
        self.assertEqual(rendered.count("研究结论: **持有**"), 1)
        self.assertNotIn("\n\n\n", rendered)

    def test_portfolio_positioning_recommendation_is_split_into_numbered_blocks(self):
        long_advice = (
            "当前维持不超过12%的轻仓头寸，严格遵循“底仓静待+阈值触发”原则，核心目标是在保留参与反弹权利的同时将尾部风险锁定在可控范围。"
            "初始仓位带控制在总ETF配置仓位的12%-15%之间，若5月18日社零数据高于5.0%且猪价周度企稳在9.7元/公斤以上，可在次一交易日将仓位提升至25%。"
            "加仓条件需同时满足三个技术标准：价格放量站上0.830元，日成交量需达到近20日均量的1.3倍以上；RSI回升至40以上；份额结束净流出转为周度净增长。"
            "关键支撑位：0.800元为心理关口，0.784元为2倍ATR止损位；关键阻力位：0.830元和0.852元。"
            "减仓条件为价格跌破0.800元整数关口且成交量未萎缩，若同时伴随份额加速流出，需将仓位减至5%以下或清仓止损。"
            "退出触发（极端情景）：若美国10年实际利率突破2.20%，且豆粕价格跌破2900元/吨、玉米跌破2300元/吨，同时份额单日减少超1000万份，需立即全仓清仓。"
            "再平衡触发：当ETF溢价率扩大至超过0.3%以上且换手率超过5%，可分批减仓10%-15%以锁定浮盈。"
            "下一步重点监控的验证指标包括：豆粕仓单是否连续2周环比下降、5月18日社零数据是否高于5.0%、美国10年实际利率是否突破2.20%、份额是否连续3日净增长。"
        )

        rendered = render_portfolio_decision(
            PortfolioDecision(
                debate_conclusion="中性观点更稳妥，但反弹权利仍值得保留。",
                action_logic="当前以轻仓持有为主，把加仓和止损都绑定在价格、量能和份额验证上。",
                positioning_recommendation=long_advice,
                rating=PortfolioRating.HOLD,
                snapshot_stance="持有",
                snapshot_new_and_rebuttal="新增了对仓位上限与触发条件的约束。",
                snapshot_to_verify="继续跟踪量价、份额和宏观利率。",
            )
        )

        self.assertIn("1. 初始仓位设置。当前维持不超过12%的轻仓头寸", rendered)
        self.assertIn("2. 加仓条件与关键位。加仓条件需同时满足三个技术标准", rendered)
        self.assertIn("3. 减仓与止损条件。减仓条件为价格跌破0.800元整数关口", rendered)
        self.assertIn("4. 极端退出触发（极端情景）：若美国10年实际利率突破2.20%", rendered)
        self.assertIn("5. 再平衡触发：当ETF溢价率扩大", rendered)
        self.assertIn("6. 后续验证指标。下一步重点监控的验证指标包括", rendered)

    def test_manager_normalization_splits_long_freetext_positioning_advice(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "研究结论: **持有**\n"
            "当前维持不超过12%的轻仓头寸，等待验证。"
            "加仓条件需同时满足价格放量站上0.830元且份额转为净增长。"
            "减仓条件为价格跌破0.800元且成交量未萎缩。"
            "退出触发：若份额单日减少超1000万份则清仓。"
            "再平衡触发：当ETF溢价率超过0.3%且换手率超过5%时减仓。"
            "下一步重点监控的验证指标包括社零、猪价和份额变化。"
        )

        self.assertIn("1. 初始仓位设置。当前维持不超过12%的轻仓头寸", normalized)
        self.assertIn("2. 加仓条件与关键位。加仓条件需同时满足", normalized)
        self.assertIn("### （一）评级", normalized)
        self.assertIn("### （二）建议", normalized)

    def test_manager_normalization_splits_pre_numbered_advice_inlined_on_one_line(self):
        # The portfolio manager LLM sometimes emits all numbered items on a single
        # line, with the rating verdict glued onto the first item's title. Without
        # the inline-marker pre-split + leaked-rating strip, Rich Markdown rendered
        # only "1." as a list marker and the rest of the body as plain prose.
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "1. 初始仓位设置。 研究结论: 买入/增持。"
            "初始配置带设定为组合总仓位的15%至20%，首笔建仓严格限制在10%以内，"
            "仅在ETF净值回踩至2.78元支撑带时分批介入。"
            "加仓触发条件要求10日EMA突破2.81元，"
            "若出现逆风信号必须立即减仓至5%以下并增配30%短债ETF。 "
            "2. 再平衡触发。再平衡触发机制设定为硬性止损线2.77元与溢价率警戒线1.5%，"
            "一旦净值跌破2.77元即刻启动网格止盈或止损程序。 "
            "3. 后续验证指标。下一步重点监控指标聚焦实物需求报告、议息会议、持仓量。\n\n"
            "最终配置建议: **买入**"
        )

        # All three numbered items must be line-anchored so Rich/CommonMark renders
        # them as separate list items rather than inlining 2./3. into item 1's body.
        for marker in ("\n1. 初始仓位设置。", "\n2. 再平衡触发。", "\n3. 后续验证指标。"):
            self.assertIn(marker, normalized)

        # The leaked "研究结论: 买入/增持" prefix must be stripped from item 1's body
        # and not surface anywhere else in the advice section.
        self.assertNotIn("研究结论: 买入/增持", normalized)
        self.assertNotIn("买入/增持。初始配置带", normalized)
        # The rating subsection still carries the canonical (non-compound) verdict.
        self.assertIn("研究结论: **买入**", normalized)

    def test_rating_only_line_pattern_recognises_compound_ratings(self):
        from etfagents.agents.utils.agent_utils import _RATING_ONLY_LINE_PATTERN

        for line in (
            "研究结论: 买入",
            "研究结论: 买入/增持",
            "研究结论: 买入／增持",
            "研究结论: 买入或增持",
            "评级: 买入/增持",
            "最终配置建议: 持有/增持",
        ):
            self.assertTrue(
                _RATING_ONLY_LINE_PATTERN.match(line),
                f"expected compound rating to match: {line!r}",
            )

    def test_research_manager_normalization_strips_inline_duplicate_research_view(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "研究结论: **增持**\n"
            "在回调时分批布局，并跟踪量价验证。研究结论: 增持。\n"
        )

        self.assertEqual(normalized.count("研究结论"), 1)
        self.assertNotIn("研究结论: 增持。", normalized)
        self.assertIn("在回调时分批布局，并跟踪量价验证。", normalized)

    def test_manager_normalization_strips_prompt_leakage_and_duplicate_headings(self):
        normalized = normalize_chinese_manager_terms(
            "## 辩论结论\n"
            "## 辩论结论\n"
            "整场辩论里，中性观点认为在2.08元支撑带附近承接仍在，但放量突破之前不宜贸然扩仓。\n\n"
            "## 持仓建议\n"
            "- 这一部分必须写成连贯分析段落，至少 4 句，不能只写简短观点或要点摘录。\n"
            "- 必须引用报告中的具体数据来支撑判断——包括价格水平、均线位置、成交量、份额变化、溢折价、持仓集中度、宏观指标等。\n"
            "最终配置建议: **持有**\n"
            "- Give a clear, actionable ETF portfolio recommendation—买入, 增持, 持有, 减持, or 卖出—grounded in the debate's strongest evidence.\n"
            "目标仓位维持在15%至20%，若成交量回到20日均量上方且份额恢复净申购，再考虑上调仓位。\n"
        )

        self.assertEqual(normalized.count("## 辩论结论"), 1)
        self.assertIn("研究结论: **持有**", normalized)
        self.assertIn("目标仓位维持在15%至20%", normalized)
        self.assertNotIn("这一部分必须写成连贯分析段落", normalized)
        self.assertNotIn("Give a clear, actionable ETF portfolio recommendation", normalized)
        self.assertNotIn("\n\n\n", normalized)

    def test_manager_normalization_merges_duplicate_positioning_sections(self):
        normalized = normalize_chinese_manager_terms(
            "## 辩论结论\n"
            "当前宏观与盈利线索仍未形成同向共振。\n\n"
            "## 持仓建议\n"
            "最终配置建议: **持有**\n\n"
            "## 持仓建议\n"
            "维持当前仓位，等待价格、量能与份额变化共同确认后再决定是否调整敞口。\n"
        )

        self.assertEqual(normalized.count("## 持仓建议"), 1)
        self.assertEqual(normalized.count("研究结论: **持有**"), 1)
        self.assertIn("维持当前仓位，等待价格、量能与份额变化共同确认后再决定是否调整敞口。", normalized)

    def test_manager_normalization_uses_later_corrected_rating_when_merging_sections(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "### （一）评级\n"
            "研究结论: **持有**\n"
            "### （二）建议\n"
            "先维持当前仓位。\n\n"
            "## 持仓建议\n"
            "### （一）评级\n"
            "研究结论: **增持**\n"
            "### （二）建议\n"
            "后续若量价确认，应小幅加仓。"
        )

        self.assertEqual(normalized.count("研究结论:"), 1)
        self.assertIn("研究结论: **增持**", normalized)
        self.assertNotIn("研究结论: **持有**", normalized)
        self.assertIn("先维持当前仓位。", normalized)
        self.assertIn("后续若量价确认，应小幅加仓。", normalized)

    def test_manager_normalization_dedupes_inline_rating_labels_in_positioning_section(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "建议评级：增持。最终配置建议: 增持\n"
            "目标仓位控制在20%至25%，只有在量能与份额同步改善后才继续加仓。\n"
        )

        self.assertNotIn("建议评级：增持", normalized)
        self.assertEqual(normalized.count("研究结论: **增持**"), 1)
        self.assertIn("目标仓位控制在20%至25%", normalized)

    def test_manager_normalization_fills_empty_positioning_section(self):
        normalized = normalize_chinese_manager_terms(
            "## 辩论结论\n"
            "当前估值约束仍在，价格确认不足。\n\n"
            "## 持仓建议\n"
            "最终配置建议: **持有**\n"
        )

        self.assertEqual(normalized.count("## 持仓建议"), 1)
        self.assertIn("研究结论: **持有**", normalized)
        self.assertIn("维持当前仓位，不新增方向性敞口", normalized)
        self.assertIn("若验证链条继续改善，只做小幅上调", normalized)

    def test_manager_normalization_rewrites_rating_and_advice_as_subsections(self):
        normalized = normalize_chinese_manager_terms(
            "## 辩论结论\n"
            "低利率环境与盈利兑现仍提供底座。\n\n"
            "四、评级\n"
            "最终配置建议: **持有**\n\n"
            "五、建议\n"
            "基于低利率宏观底座稳固、AI算力基建周期业绩兑现以及量价背离下的健康筹码沉淀，组合正式给予588000.SH持有评级。"
        )

        self.assertIn("## 持仓建议", normalized)
        self.assertIn("### （一）评级", normalized)
        self.assertIn("### （二）建议", normalized)
        self.assertNotIn("四、评级", normalized)
        self.assertNotIn("五、建议", normalized)
        self.assertEqual(normalized.count("## 持仓建议"), 1)
        self.assertIn("研究结论: **持有**", normalized)

    def test_manager_normalization_removes_portfolio_final_proposal_label(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "最终配置建议: **持有**\n"
            "目标仓位先维持在15%至20%，等待成交量与份额变化共同确认。\n"
        )

        self.assertNotIn("最终配置建议", normalized)
        self.assertIn("研究结论: **持有**", normalized)

    def test_manager_normalization_prevents_inline_markdown_heading_echo(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "### （一）评级\n"
            "研究结论: **持有**\n\n"
            "### （二）建议\n"
            "维持当前仓位。"
        )

        self.assertNotIn("（一）##", normalized)
        self.assertNotIn("（二）##", normalized)

    def test_manager_normalization_compacts_positioning_subsection_spacing(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n\n"
            "### （一）评级\n"
            "研究结论: **持有**\n\n"
            "### （二）建议\n"
            "维持当前仓位。"
        )

        self.assertNotIn("## 持仓建议\n\n### （一）评级", normalized)
        self.assertNotIn("研究结论: **持有**\n\n### （二）建议", normalized)
        self.assertIn("## 持仓建议\n### （一）评级", normalized)
        self.assertIn("研究结论: **持有**\n### （二）建议", normalized)

    def test_manager_normalization_strips_machine_field_name_leakage(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "### （一）评级\n"
            "研究结论: **持有**\n"
            "### （二）建议\n"
            "target_weight_pct: 20\n"
            "execution_timing: next_open\n"
            "rebalance_triggers: close > 2.08\n"
            "目标仓位先维持在15%至20%，只有在成交量回到20日均量上方后才继续加仓。"
        )

        self.assertNotIn("target_weight_pct", normalized)
        self.assertNotIn("execution_timing", normalized)
        self.assertNotIn("rebalance_triggers", normalized)
        self.assertIn("目标仓位先维持在15%至20%", normalized)

    def test_manager_normalization_strips_chinese_structured_mapping_leakage(self):
        normalized = normalize_chinese_manager_terms(
            "## 持仓建议\n"
            "### （一）评级\n"
            "研究结论: **持有**\n"
            "### （二）建议\n"
            "结构化参数参数映射如下：target_weight_pct 对应目标仓位，execution_timing 对应执行时机。\n"
            "对于结构化触发器，优先使用支持的指标，如 close、volume、weight_pct。\n"
            "不得在可见正文中暴露机器可读字段名。\n"
            "目标仓位先维持在15%至20%，只有量价与份额变化同步改善后才继续加仓。"
        )

        self.assertNotIn("结构化参数参数映射", normalized)
        self.assertNotIn("支持的指标", normalized)
        self.assertNotIn("机器可读字段名", normalized)
        self.assertIn("目标仓位先维持在15%至20%", normalized)

    def test_collaboration_stop_instruction_prefers_chinese_display(self):
        instruction = get_localized_final_proposal_instruction()
        self.assertIn("研究结论: **买入/增持/持有/减持/卖出**", instruction)


if __name__ == "__main__":
    unittest.main()
