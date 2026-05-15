import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from cli.main import (
    MessageBuffer,
    _prepare_report_markdown,
    _normalize_ticker_list,
    format_research_team_history,
    format_risk_management_history,
    process_chunk_messages,
    save_candidate_pool_report,
    save_report_to_disk,
)
from etfagents.dataflows.config import get_config, set_config
from etfagents.default_config import DEFAULT_CONFIG


class CliRoundFormattingTests(unittest.TestCase):
    def setUp(self):
        self.original_config = get_config().copy()
        cfg = DEFAULT_CONFIG.copy()
        cfg["output_language"] = "Chinese"
        set_config(cfg)

    def tearDown(self):
        set_config(self.original_config)

    def test_research_team_history_is_grouped_by_round(self):
        debate_state = {
            "bull_history": (
                "多头分析师: 第一轮多头观点\n"
                "反馈快照:\n"
                "- 当前观点: 买入\n"
                "- 发生了什么变化: 强化多头\n"
                "- 为什么变化: 金价走强\n"
                "- 关键反驳: 估值担忧可控\n"
                "- 下一轮教训: 跟踪量价\n"
                "多头分析师: 第二轮多头补充\n"
                "反馈快照:\n"
                "- 当前观点: 强烈买入\n"
                "- 发生了什么变化: 更激进\n"
                "- 为什么变化: 避险升级\n"
                "- 关键反驳: 回撤是买点\n"
                "- 下一轮教训: 盯并购兑现"
            ),
            "bear_history": (
                "空头分析师: 第一轮空头观点\n"
                "反馈快照:\n"
                "- 当前观点: 持有\n"
                "- 发生了什么变化: 维持谨慎\n"
                "- 为什么变化: 估值偏高\n"
                "- 关键反驳: 上涨已透支\n"
                "- 下一轮教训: 看现金流\n"
                "空头分析师: 第二轮空头反驳\n"
                "反馈快照:\n"
                "- 当前观点: 减持\n"
                "- 发生了什么变化: 转向更谨慎\n"
                "- 为什么变化: 风险升高\n"
                "- 关键反驳: 高位放量\n"
                "- 下一轮教训: 盯库存"
            ),
            "judge_decision": "研究经理: 最终结论",
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("### 第 1 轮", formatted)
        self.assertIn("#### 多头分析师\n\n第一轮多头观点", formatted)
        self.assertNotIn("反馈快照", formatted)
        self.assertIn("#### 空头分析师\n\n第一轮空头观点", formatted)
        self.assertIn("### 第 2 轮", formatted)
        self.assertIn("#### 多头分析师\n\n第二轮多头补充", formatted)
        self.assertIn("#### 空头分析师\n\n第二轮空头反驳", formatted)
        self.assertIn("### 研究经理结论\n研究经理: 最终结论", formatted)
        self.assertNotIn("#### 反馈快照摘要", formatted)
        self.assertNotIn("\n\n\n", formatted)

    def test_prepare_report_markdown_inserts_blank_line_after_visible_heading(self):
        formatted = _prepare_report_markdown(
            "一、核心矛盾与主线判断\n本期核心矛盾在于成本传导尚未闭环。"
        )

        self.assertIn(
            "一、核心矛盾与主线判断\n\n本期核心矛盾在于成本传导尚未闭环。",
            formatted,
        )

    def test_prepare_report_markdown_splits_inline_visible_section_heading(self):
        formatted = _prepare_report_markdown(
            "一、总体研判\n\n本部分通过量化数据比对、机构情绪拆解与产业链传导机制，量化评估ETF持仓品种的风险收益比。二、深度分析\n\n后续正文。"
        )

        self.assertIn("风险收益比。\n\n# 二、深度分析", formatted)
        self.assertIn("后续正文。", formatted)

    def test_prepare_report_markdown_splits_inline_markdown_subheading(self):
        formatted = _prepare_report_markdown(
            "一、核心持仓共识与分歧\n"
            "短期扰动更多来自交易层噪声而非基本面失速 ## （一）共识主线\n"
            "多数券商仍将盈利兑现视为主线。"
        )

        self.assertIn(
            "短期扰动更多来自交易层噪声而非基本面失速\n\n## （一）共识主线",
            formatted,
        )
        self.assertNotIn("失速 ## （一）", formatted)

    def test_prepare_report_markdown_splits_inline_top_and_second_level_headings(self):
        formatted = _prepare_report_markdown(
            "一、核心持仓共识与分歧 （一）共识主线\n"
            "多数券商仍将盈利兑现视为主线。\n\n"
            "二、盈利、估值与机构态度 （一）关键数据对比\n"
            "盈利修复宽度决定ETF归因质量。"
        )

        self.assertIn("# 一、核心持仓共识与分歧\n\n## （一）共识主线", formatted)
        self.assertIn("# 二、盈利、估值与机构态度\n\n## （一）关键数据对比", formatted)
        self.assertNotIn("共识与分歧 （一）", formatted)
        self.assertNotIn("机构态度 （一）", formatted)

    def test_prepare_report_markdown_strips_exchange_only_pseudo_title_line(self):
        formatted = _prepare_report_markdown(
            "# 舆情与事件影响分析\n\n"
            "一、SH 工业有色ETF万家：舆情与事件影响分析\n\n"
            "## 一、总体研判\n\n"
            "正文内容。"
        )

        self.assertNotIn("一、SH 工业有色ETF万家：舆情与事件影响分析", formatted)
        self.assertIn("## 一、总体研判", formatted)
        self.assertIn("正文内容。", formatted)

    def test_risk_management_history_supports_english_prefixes(self):
        risk_state = {
            "aggressive_history": (
                "Aggressive Analyst: Round 1 aggressive case\n"
                "DECISION SUMMARY:\n"
                "- Rating: SELL\n"
                "- Confidence: 70%\n"
                "- Time Horizon: 1-3 months\n"
                "- Key Assumptions:\n"
                "  1. Momentum remains weak.\n"
                "  2. Liquidity deteriorates.\n"
                "  3. No upside catalyst.\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Current thesis: Sell\n"
                "- What changed: More defensive\n"
                "- Why it changed: Momentum broke\n"
                "- Key rebuttal: Upside is capped\n"
                "- Lesson for next round: Watch liquidity\n"
                "Aggressive Analyst: Round 2 aggressive follow-up"
            ),
            "conservative_history": (
                "Conservative Analyst: Round 1 conservative case\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Current thesis: Hold\n"
                "- What changed: Stayed cautious\n"
                "- Why it changed: Valuation rich\n"
                "- Key rebuttal: Do not chase\n"
                "- Lesson for next round: Check earnings"
            ),
            "neutral_history": (
                "Neutral Analyst: Round 1 neutral case\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Current thesis: Hold\n"
                "- What changed: Balanced both sides\n"
                "- Why it changed: Conflicting signals\n"
                "- Key rebuttal: Need confirmation\n"
                "- Lesson for next round: Wait for breakout"
            ),
            "judge_decision": "Portfolio Manager: Final allocation",
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("### 第 1 轮", formatted)
        self.assertIn("#### 激进风险分析师\n\nRound 1 aggressive case", formatted)
        self.assertIn("决策摘要:\n- 评级: SELL", formatted)
        self.assertNotIn("FEEDBACK SNAPSHOT", formatted)
        self.assertNotIn("反馈快照", formatted)
        self.assertIn("#### 保守风险分析师\n\nRound 1 conservative case", formatted)
        self.assertIn("#### 中性风险分析师\n\nRound 1 neutral case", formatted)
        self.assertIn("### 第 2 轮", formatted)
        self.assertIn("#### 激进风险分析师\n\nRound 2 aggressive follow-up", formatted)
        self.assertIn("### 投资组合经理结论\nPortfolio Manager: Final allocation", formatted)
        self.assertNotIn("\n\n\n", formatted)

    def test_inferred_snapshot_shows_snapshot_without_review_heading(self):
        debate_state = {
            "bull_history": (
                "多头分析师: 本轮新增了对库存风险的反驳，并强调需要继续跟踪金价与并购进度。\n"
                "反馈快照:\n"
                "- 当前观点: 暂无。\n"
                "- 发生了什么变化: 未明确说明。\n"
                "- 为什么变化: 未明确说明。\n"
                "- 关键反驳: 未明确说明。\n"
                "- 下一轮教训: 未明确说明。"
            ),
            "bear_history": "",
            "judge_decision": "",
        }

        formatted = format_research_team_history(debate_state)

        self.assertNotIn("反馈快照", formatted)
        self.assertNotIn("##### 自动复盘", formatted)
        self.assertNotIn("##### 本轮复盘", formatted)

    def test_research_manager_shows_body_before_snapshot_summary(self):
        debate_state = {
            "bull_history": "",
            "bear_history": "",
            "judge_decision": (
                "## 辩论裁决\n"
                "多头证据更扎实，空头对估值风险的论证不足。\n\n"
                "## 行为逻辑\n"
                "先验证需求兑现，再决定是否继续加仓。\n\n"
                "## 持仓建议\n"
                "维持增持，回踩支撑再分批加仓。\n\n"
                "反馈快照:\n"
                "- 立场: 增持——需求与盈利兑现仍占优。\n"
                "- 本轮新增: 新增了对需求验证节奏的约束。\n"
                "- 关键反驳: 空头高估了估值压缩速度。\n"
                "- 待验证: 跟踪订单、毛利率和客户资本开支。"
            ),
            "judge_snapshot_path": "/tmp/research_manager_round_1.md",
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("### 研究经理结论", formatted)
        self.assertIn("#### 一、辩论结论", formatted)
        self.assertIn("#### 二、行为逻辑", formatted)
        self.assertIn("#### 三、持仓建议", formatted)
        self.assertNotIn("#### 反馈快照摘要", formatted)
        self.assertNotIn("反馈快照", formatted)

    def test_research_manager_dedupes_repeated_feedback_snapshots(self):
        repeated_snapshot = (
            "反馈快照:\n"
            "- 立场: 增持——需求与盈利兑现仍占优。\n"
            "- 本轮新增与反驳: 新增了对需求验证节奏的约束。\n"
            "- 待验证: 跟踪订单、毛利率和客户资本开支。"
        )
        debate_state = {
            "bull_history": "",
            "bear_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "多头证据更扎实，空头对估值风险的论证不足。\n\n"
                "## 行为逻辑\n"
                "先验证需求兑现，再决定是否继续加仓。\n\n"
                "## 持仓建议\n"
                "维持增持，回踩支撑再分批加仓。\n\n"
                f"{repeated_snapshot}\n\n{repeated_snapshot}"
            ),
        }

        formatted = format_research_team_history(debate_state)

        self.assertEqual(formatted.count("反馈快照:"), 0)
        self.assertEqual(formatted.count("#### 反馈快照摘要"), 0)

    def test_research_manager_normalizes_judicial_wording_to_debate_conclusion(self):
        debate_state = {
            "bull_history": "",
            "bear_history": "",
            "judge_decision": (
                "## 辩论裁决\n"
                "判决结果：本轮双方论点势均力敌。\n\n"
                "## 行为逻辑\n"
                "等待更多盈利兑现信号后再提高仓位。"
            ),
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("#### 一、辩论结论", formatted)
        self.assertIn("综合结论：整场辩论中双方论据势均力敌。", formatted)
        self.assertNotIn("判决结果", formatted)
        self.assertNotIn("本轮双方论点势均力敌", formatted)

    def test_research_team_history_shows_decision_summary_outside_argument_body(self):
        debate_state = {
            "bull_history": (
                "多头分析师: 这是正文论证。\n\n"
                "决策摘要:\n"
                "- 评级: 增持\n"
                "- 置信度: 80%\n"
                "- 时间区间: 6-12个月\n"
                "- 关键假设:\n"
                "  1. AI需求持续。\n"
                "  2. 公司维持份额。\n"
                "  3. 供应链稳定。\n\n"
                "反馈快照:\n"
                "- 当前观点: 增持\n"
                "- 发生了什么变化: 新增催化剂。\n"
                "- 为什么变化: 需求增强。\n"
                "- 关键反驳: 空头低估景气度。\n"
                "- 下一轮教训: 跟踪订单。"
            ),
            "bear_history": "",
            "judge_decision": "",
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("这是正文论证。", formatted)
        self.assertIn("决策摘要:\n- 评级: 增持", formatted)
        self.assertEqual(formatted.count("决策摘要:"), 1)
        self.assertNotIn("##### 决策摘要", formatted)
        self.assertLess(formatted.index("这是正文论证。"), formatted.index("决策摘要:\n- 评级: 增持"))

    def test_risk_history_strips_duplicate_role_self_introduction(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": (
                "保守分析师: 作为保守风险分析师，我必须再次强调高估值和库存风险。\n"
                "反馈快照:\n"
                "- 当前观点: 持有\n"
                "- 发生了什么变化: 维持谨慎。\n"
                "- 为什么变化: 风险收益比偏弱。\n"
                "- 关键反驳: 不宜追高。\n"
                "- 下一轮教训: 跟踪支撑位。"
            ),
            "neutral_history": "",
            "judge_decision": "",
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("#### 保守风险分析师\n\n我必须再次强调高估值和库存风险。", formatted)
        self.assertNotIn("#### 保守风险分析师\n\n作为保守风险分析师", formatted)

    def test_portfolio_manager_hides_snapshot_summary(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "Portfolio Manager: Final allocation\n\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Stance: Hold\n"
                "- New this round & rebuttal: Keep flexibility.\n"
                "- To verify: Watch earnings."
            ),
            "judge_snapshot_path": "/tmp/portfolio_manager_round_1.md",
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("### 投资组合经理结论\nPortfolio Manager: Final allocation", formatted)
        self.assertNotIn("反馈快照摘要", formatted)
        self.assertNotIn("FEEDBACK SNAPSHOT", formatted)

    def test_risk_management_history_can_hide_portfolio_manager_block(self):
        risk_state = {
            "aggressive_history": "Aggressive Analyst: Round 1 aggressive case",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": "Portfolio Manager: Final allocation",
        }

        formatted = format_risk_management_history(risk_state, include_manager=False)

        self.assertIn("#### 激进风险分析师", formatted)
        self.assertNotIn("### 投资组合经理结论", formatted)

    def test_portfolio_manager_normalizes_mixed_english_headings_and_terms(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## Debate Verdict\n"
                "综合结论：应维持更谨慎的仓位。\n\n"
                "## Action Logic\n"
                "当前 time horizon 应控制在1-3个月，等待盈利确认后再决定是否加仓。\n\n"
                "## Positioning Recommendation\n"
                "维持持有，若支撑位失守则减仓。\n\n"
                "最终配置建议: **持有**"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("#### 一、辩论结论", formatted)
        self.assertIn("#### 二、行为逻辑", formatted)
        self.assertIn("#### 三、持仓建议", formatted)
        self.assertIn("时间区间", formatted)
        self.assertNotIn("time horizon", formatted.lower())
        self.assertIn("##### （一）评级", formatted)
        self.assertIn("##### （二）建议", formatted)
        self.assertNotIn("（一）##", formatted)
        self.assertNotIn("（二）##", formatted)

    def test_portfolio_manager_inserts_paragraph_break_after_rating_line(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 持仓建议\n"
                "评级: 增持\n"
                "建议针对回踩后的确认信号分批加仓，并继续跟踪量价配合。\n\n"
                "最终配置建议: **增持**"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("#### 持仓建议", formatted)
        self.assertIn("##### 一、评级", formatted)
        self.assertIn("##### 二、建议", formatted)
        self.assertNotIn("评级: 增持", formatted)
        self.assertIn("研究结论: **增持**", formatted)
        self.assertIn("建议针对回踩后的确认信号分批加仓", formatted)

    def test_message_buffer_localizes_etf_structure_section_title_in_chinese(self):
        buffer = MessageBuffer()
        buffer.init_for_analysis(["etf_structure"])
        buffer.update_report_section("fundamentals_report", "财务质量稳健。")

        self.assertIn("### 中观大宗商品分析\n财务质量稳健。", buffer.current_report)
        self.assertIn("### 中观大宗商品分析\n财务质量稳健。", buffer.final_report)
        self.assertNotIn("基本面分析", buffer.final_report)

    def test_message_buffer_counts_market_flow_report_after_market_analyst_completes(self):
        buffer = MessageBuffer()
        buffer.init_for_analysis(["market"])
        buffer.update_report_section("research_report", "行业研报交叉分析内容。")
        buffer.update_agent_status("Market & Flow Analyst", "completed")

        self.assertEqual(1, buffer.get_completed_reports_count())

    def test_process_chunk_messages_records_all_unique_messages_and_tool_calls(self):
        class FakeMessage:
            def __init__(self, message_id, content, tool_calls=None):
                self.id = message_id
                self.content = content
                self.tool_calls = tool_calls or []

        buffer = MessageBuffer()
        chunk = {
            "messages": [
                FakeMessage("m1", "first", [{"name": "tool_a", "args": {"symbol": "AAPL"}}]),
                FakeMessage("m2", "second"),
                FakeMessage("m1", "duplicate", [{"name": "tool_b", "args": {"symbol": "MSFT"}}]),
            ]
        }

        with patch("cli.main.classify_message_type", side_effect=lambda message: ("Agent", message.content)):
            process_chunk_messages(chunk, buffer)

        self.assertEqual([content for _, _, content in buffer.messages], ["first", "second"])
        self.assertEqual(
            [(name, args) for _, name, args in buffer.tool_calls],
            [("tool_a", {"symbol": "AAPL"})],
        )

    def test_save_report_to_disk_persists_complete_report_locally(self):
        final_state = {
            "market_report": "# 宁德时代（300750.SZ）综合技术分析报告\n\n## 一、行情概览\n市场分析内容",
            "sentiment_report": "情绪分析内容",
            "news_report": "新闻分析内容",
            "fundamentals_report": "基本面分析内容",
            "research_report": "",
            "stock_report": "",
            "investment_debate_state": {
                "bull_history": "多头分析师: 多头观点",
                "bear_history": "空头分析师: 空头观点",
                "judge_decision": "## 辩论结论\n研究经理结论",
                "judge_snapshot_path": "",
            },
            "trader_allocation_plan": "ETF配置计划内容",
            "risk_debate_state": {
                "aggressive_history": "激进风险分析师: 激进观点",
                "conservative_history": "保守风险分析师: 保守观点",
                "neutral_history": "中性风险分析师: 中性观点",
                "judge_decision": "## 辩论结论\n投资组合经理结论\n\n最终配置建议: **持有**",
                "judge_snapshot_path": "",
            },
            "final_allocation_decision": "## 辩论结论\n投资组合经理结论\n\n最终配置建议: **持有**",
        }

        with TemporaryDirectory() as tmpdir:
            report_path = save_report_to_disk(
                final_state,
                "300750.SZ",
                Path(tmpdir),
            )

            self.assertTrue(report_path.exists())
            self.assertTrue((Path(tmpdir) / "4_risk" / "rounds.md").exists())
            self.assertTrue((Path(tmpdir) / "5_portfolio" / "decision.md").exists())
            report_text = report_path.read_text()
            self.assertIn("ETF配置分析报告", report_text)
            self.assertIn("### 市场与资金流分析师", report_text)
            self.assertIn("#### 宁德时代（300750.SZ）综合技术分析报告", report_text)
            self.assertIn("##### 一、行情概览", report_text)

    def test_normalize_ticker_list_dedupes_candidate_pool_input(self):
        tickers = _normalize_ticker_list("510300.sh, 159915.sz,510300.SH\n513100.sh")

        self.assertEqual(tickers, ["510300.SH", "159915.SZ", "513100.SH"])

    def test_save_candidate_pool_report_persists_ranked_summary(self):
        candidates = [
            {
                "ticker": "159915.SZ",
                "rating": "BUY",
                "score": "5",
                "suggested_weight_pct": 50.0,
                "research_allocation_plan": "研究观点A",
                "trader_allocation_plan": "交易计划A",
                "final_allocation_decision": "## 辩论结论\n最终配置建议: **买入**",
            },
            {
                "ticker": "510300.SH",
                "rating": "OVERWEIGHT",
                "score": "4",
                "suggested_weight_pct": 33.3,
                "research_allocation_plan": "研究观点B",
                "trader_allocation_plan": "交易计划B",
                "final_allocation_decision": "## 辩论结论\n最终配置建议: **增持**",
            },
        ]

        with TemporaryDirectory() as tmpdir:
            report_path = save_candidate_pool_report(
                candidates,
                "2026-01-15",
                Path(tmpdir),
            )

            self.assertTrue(report_path.exists())
            self.assertTrue((Path(tmpdir) / "ranked_candidates" / "01_159915_SZ.md").exists())
            report_text = report_path.read_text()
            self.assertIn("ETF候选池分析报告", report_text)
            self.assertIn("| 排名 | 代码 | 评级 | 分数 | 建议权重 |", report_text)
            self.assertIn("159915.SZ", report_text)
            self.assertIn("50.0%", report_text)

    def test_prepare_report_markdown_normalizes_official_hierarchy(self):
        text = (
            "# 示例报告\n\n"
            "## 一、总体判断\n\n"
            "### 1.1 市场回顾\n\n"
            "#### 1. 关键信号\n\n"
            "##### ① 细项说明\n\n"
            "###### 1. 更细分项"
        )

        normalized = _prepare_report_markdown(text)

        self.assertIn("# 示例报告", normalized)
        self.assertIn("## 一、总体判断", normalized)
        self.assertIn("### （一）市场回顾", normalized)
        self.assertIn("#### 1. 关键信号", normalized)
        self.assertIn("##### (1) 细项说明", normalized)
        self.assertIn("###### ① 更细分项", normalized)


if __name__ == "__main__":
    unittest.main()
