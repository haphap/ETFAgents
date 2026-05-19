import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from cli.main import (
    MessageBuffer,
    _format_manager_decision,
    _merge_stream_state,
    _prepare_report_markdown,
    display_candidate_pool_report,
    _normalize_ticker_list,
    format_research_team_history,
    format_risk_management_history,
    display_complete_report,
    process_chunk_messages,
    save_candidate_pool_report,
    save_report_to_disk,
    update_analyst_statuses,
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

    def test_prepare_report_markdown_strips_second_person_heading_prefixes(self):
        formatted = _prepare_report_markdown(
            "一、你们的资金流确认框架仍需修正\n"
            "正文内容。"
        )

        self.assertIn("# 一、资金流确认框架仍需修正", formatted)
        self.assertNotIn("你们的资金流", formatted)
        self.assertNotIn("们的资金流", formatted)

    def test_prepare_report_markdown_strips_empty_subheadings_and_markdown_noise(self):
        formatted = _prepare_report_markdown(
            "**  \n\n"
            "二、交易计划\n\n"
            "（一）价格与量能联动条件\n\n"
            "（二）分步执行节奏\n\n"
            "首轮减持窗口内优先压降估值极端敞口。\n\n"
            "（三）加仓恢复条件\n"
        )

        self.assertNotIn("**", formatted)
        # Visible report headings are renumbered from the first emitted top-level
        # section, so a lone "二、" becomes the rendered first section.
        self.assertIn("# 一、交易计划", formatted)
        self.assertNotIn("价格与量能联动条件", formatted)
        self.assertIn("## 分步执行节奏", formatted)
        self.assertNotIn("## （一）分步执行节奏", formatted)
        self.assertIn("首轮减持窗口内优先压降估值极端敞口。", formatted)
        self.assertNotIn("加仓恢复条件", formatted)

    def test_prepare_report_markdown_joins_chinese_soft_line_breaks(self):
        formatted = _prepare_report_markdown(
            "第一，焦煤的库存堆积是钢铁产业链内部的产能调整，而非全社会用电需求的直接反映。\n"
            "当前电力需求的核心增长引擎早已切换至第三产业和居民端。"
        )

        self.assertIn(
            "第一，焦煤的库存堆积是钢铁产业链内部的产能调整，而非全社会用电需求的直接反映。当前电力需求的核心增长引擎早已切换至第三产业和居民端。",
            formatted,
        )
        self.assertNotIn("直接反映。\n当前电力需求", formatted)

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

    def test_prepare_report_markdown_strips_data_ready_analysis_preamble(self):
        formatted = _prepare_report_markdown(
            "数据已获取完毕，以下为ETF持仓行业研究分析。\n\n"
            "一、行业主线与分歧焦点\n"
            "正文内容。"
        )

        self.assertNotIn("数据已获取完毕", formatted)
        self.assertNotIn("以下为ETF持仓行业研究分析", formatted)
        self.assertIn("# 一、行业主线与分歧焦点", formatted)

    def test_prepare_report_markdown_strips_data_ready_integrate_analysis_preamble(self):
        formatted = _prepare_report_markdown(
            "数据已全部到位，现在整合分析。\n\n"
            "一、宏观框架分析\n"
            "正文内容。"
        )

        self.assertNotIn("数据已全部到位", formatted)
        self.assertNotIn("现在整合分析", formatted)
        self.assertIn("# 一、宏观框架分析", formatted)

    def test_prepare_report_markdown_strips_report_ready_delivery_preamble(self):
        formatted = _prepare_report_markdown(
            "报告已就绪。下面进入正文：\n\n"
            "一、宏观框架分析\n"
            "正文内容。"
        )

        self.assertNotIn("报告已就绪", formatted)
        self.assertNotIn("下面进入正文", formatted)
        self.assertIn("# 一、宏观框架分析", formatted)

    def test_prepare_report_markdown_keeps_sentence_like_numbering_inside_list_body(self):
        formatted = _prepare_report_markdown(
            "一、情绪主线与权重影响\n\n"
            "二、产品情绪与讨论强弱\n\n"
            "1 舆论情绪偏向积极：富途牛牛等财经媒体在5月6日发布报道，称“全球共振引发芯片市场反弹”，并明确提及科创芯片ETF\n\n"
            "三、近一年涨幅已翻倍。该报道属于事实性新闻（标题可验证），传导路径清晰。\n\n"
            "2 社交媒体热度中等偏弱：产品层面的社交情绪属于温带正面。"
        )

        self.assertIn("# 一、情绪主线与权重影响", formatted)
        self.assertIn("# 二、产品情绪与讨论强弱", formatted)
        self.assertIn("1. 舆论情绪偏向积极", formatted)
        self.assertIn("2. 社交媒体热度中等偏弱", formatted)
        self.assertIn("\n\n近一年涨幅已翻倍。该报道属于事实性新闻", formatted)
        self.assertNotIn("# 三、近一年涨幅已翻倍", formatted)

    def test_prepare_report_markdown_keeps_heading_with_colon_between_list_items(self):
        formatted = _prepare_report_markdown(
            "1. 第一项内容\n"
            "一、市场结构：核心矛盾\n"
            "2. 第二项内容"
        )

        self.assertIn("1. 第一项内容", formatted)
        self.assertIn("# 一、市场结构：核心矛盾", formatted)
        self.assertIn("2. 第二项内容", formatted)
        self.assertNotIn("\n市场结构：核心矛盾\n", formatted)

    def test_prepare_report_markdown_does_not_rewrite_spaced_date_prefix_as_list_item(self):
        formatted = _prepare_report_markdown(
            "1. 主线判断\n\n"
            "5 月15日发布的社零数据显示同比上升5.2%。\n\n"
            "2. 风险点"
        )

        self.assertIn("1. 主线判断", formatted)
        self.assertIn("5 月15日发布的社零数据显示同比上升5.2%。", formatted)
        self.assertIn("2. 风险点", formatted)
        self.assertNotIn("5. 月15日发布的社零数据显示同比上升5.2%。", formatted)

    def test_prepare_report_markdown_merges_orphan_subsection_marker_with_following_heading(self):
        formatted = _prepare_report_markdown(
            "一、情绪主线与权重影响\n\n"
            "（一）\n"
            "产品情绪与讨论强弱"
        )

        self.assertIn("# 一、情绪主线与权重影响", formatted)
        self.assertIn("## （一）产品情绪与讨论强弱", formatted)
        self.assertNotIn("（一）\n产品情绪与讨论强弱", formatted)

    def test_prepare_report_markdown_drops_dangling_orphan_subsection_marker(self):
        formatted = _prepare_report_markdown("科创芯片ETF嘉实\n\n（一）")

        self.assertEqual(formatted, "科创芯片ETF嘉实")

    def test_prepare_report_markdown_joins_wrapped_etf_name_and_ticker(self):
        formatted = _prepare_report_markdown(
            "恒生科技ETF华泰柏瑞\n\n"
            "（513130）跟踪恒生科技指数，重点观察互联网平台和成长股风险偏好。"
        )

        self.assertIn(
            "恒生科技ETF华泰柏瑞（513130）跟踪恒生科技指数",
            formatted,
        )
        self.assertNotIn("恒生科技ETF华泰柏瑞\n\n（513130）", formatted)

    def test_prepare_report_markdown_joins_single_newline_etf_name_and_ticker(self):
        formatted = _prepare_report_markdown(
            "恒生科技ETF华泰柏瑞\n"
            "（513130）跟踪恒生科技指数。"
        )

        self.assertEqual(formatted, "恒生科技ETF华泰柏瑞（513130）跟踪恒生科技指数。")

    def test_prepare_report_markdown_does_not_join_non_etf_name_before_ticker(self):
        formatted = _prepare_report_markdown(
            "宏观框架分析\n\n"
            "（513130）跟踪恒生科技指数。"
        )

        self.assertIn("宏观框架分析\n\n（513130）", formatted)

    def test_prepare_report_markdown_leaves_english_prose_numbering_unchanged(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["output_language"] = "English"
        set_config(cfg)

        formatted = _prepare_report_markdown(
            "1. First item\n\n"
            "5 dogs barked loudly in the yard.\n\n"
            "2. Second item"
        )

        self.assertIn("1. First item", formatted)
        self.assertIn("5 dogs barked loudly in the yard.", formatted)
        self.assertIn("2. Second item", formatted)
        self.assertNotIn("5. dogs barked loudly in the yard.", formatted)

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

    def test_research_manager_dedupes_repeated_rating_and_advice_subsections(self):
        debate_state = {
            "bull_history": "",
            "bear_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "双方证据仍不足以支持加仓。\n\n"
                "## 持仓建议\n"
                "### （一）评级\n"
                "研究结论: **持有**\n"
                "### （二）建议\n"
                "维持当前仓位。\n\n"
                "## 评级\n"
                "研究结论: **持有**\n\n"
                "## 建议\n"
                "继续等待量价确认。"
            ),
        }

        formatted = format_research_team_history(debate_state)

        self.assertEqual(formatted.count("##### （一）评级"), 1)
        self.assertEqual(formatted.count("##### （二）建议"), 1)
        self.assertEqual(formatted.count("研究结论: **持有**"), 1)
        self.assertNotIn("##### （三）评级", formatted)
        self.assertNotIn("##### （四）建议", formatted)
        self.assertIn("维持当前仓位。", formatted)
        self.assertIn("继续等待量价确认。", formatted)

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

    def test_manager_decision_does_not_fall_back_to_orphan_snapshot_item(self):
        formatted = _format_manager_decision(
            "- 本轮新增与反驳: 新增了对仓位节奏与风险预算的约束。",
            show_snapshot_summary=False,
        )

        self.assertEqual(formatted, "")

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

    def test_research_manager_splits_dense_conclusion_points(self):
        debate_state = {
            "bull_history": "",
            "bear_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "空头最强支撑在于：第一，成本传导已结构性断裂，上游原油上涨但聚乙烯价格停滞且仓单暴增；"
                "第二，内部对冲存在2-3个月操作滞后窗口，油运盈利崩塌快于炼化修复启动。"
                "这些因素共同指向ETF在当前位置的风险收益比已不对称，下行压力大于上行空间。\n\n"
                "## 行为逻辑\n"
                "触发减持条件的具体阈值包括：布伦特原油跌破78美元/桶；"
                "原油期货持仓量在连续3个交易日萎缩超10%；"
                "聚乙烯仓单在2周内继续增长且价格跌破8000元/吨；"
                "VLCC TCE回落至15万美元/天以下。"
            ),
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("空头最强支撑在于：\n\n1. 第一，成本传导已结构性断裂", formatted)
        self.assertIn("2. 第二，内部对冲存在2-3个月操作滞后窗口", formatted)
        self.assertIn("触发减持条件的具体阈值包括：\n\n1. 布伦特原油跌破78美元/桶", formatted)
        self.assertIn("4. VLCC TCE回落至15万美元/天以下", formatted)

    def test_portfolio_manager_splits_dense_conclusion_and_action_paragraphs(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "综合结论：激进观点强调反弹弹性，但保守观点指出量价确认不足。"
                "当前ETF仍处在关键均线下方，资金流也没有形成连续净申购。"
                "因此投资组合经理应先控制仓位，再等待价格、份额和溢折价共同修复。\n\n"
                "## 行为逻辑\n"
                "行动上先维持基础仓位，不把单日反弹视为加仓信号。"
                "如果后续成交量回到20日均量上方且份额连续净申购，再考虑小幅上调。"
                "若价格跌破前低且溢价率继续走阔，则优先减仓并复核风险预算。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("#### 一、辩论结论", formatted)
        self.assertIn("量价确认不足。\n\n当前ETF仍处在关键均线下方", formatted)
        self.assertIn("#### 二、行为逻辑", formatted)
        self.assertIn("加仓信号。\n\n如果后续成交量回到20日均量上方", formatted)

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

    def test_research_team_history_parses_noisy_structured_markers(self):
        debate_state = {
            "bull_history": (
                "多头分析师: 这是正文论证。\n"
                "；决策摘要： - 评级: 增持\n"
                "- 置信度: 70%\n"
                "- 时间区间: 3个月\n"
                "反馈快照，- 当前观点: 增持\n"
                "- 发生了什么变化: 新增催化剂。\n"
                "- 为什么变化: 需求增强。"
            ),
            "bear_history": "",
            "judge_decision": "",
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("这是正文论证。", formatted)
        self.assertIn("决策摘要:\n- 评级: 增持", formatted)
        self.assertIn("- 时间区间: 3个月", formatted)
        self.assertNotIn("反馈快照", formatted)

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

    def test_risk_management_history_splits_inline_markdown_headings_in_body(self):
        risk_state = {
            "aggressive_history": (
                "激进风险分析师: ## 一、宏观定价与产业周期的激进共振 ## （一）实际利率高企非压制而是洗盘\n"
                "风险预算仍要绑定价格确认。"
            ),
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": "",
        }

        formatted = format_risk_management_history(risk_state, include_manager=False)

        self.assertIn(
            "一、宏观定价与产业周期的激进共振\n\n（一）实际利率高企非压制而是洗盘",
            formatted,
        )
        self.assertNotIn("## 一、", formatted)
        self.assertNotIn("## （一）", formatted)
        self.assertNotIn("共振 ##", formatted)

    def test_risk_management_history_splits_section_headings_separated_by_whitespace(self):
        risk_state = {
            "aggressive_history": (
                "激进风险分析师: 我们坚持反制保守派。\n"
                "一、对保守观点的激进反制 （一）实际利率与美元约束并非天花板\n"
                "美元 DXY 已回落 1.2%，估值修复有空间。"
            ),
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": "",
        }

        formatted = format_risk_management_history(risk_state, include_manager=False)

        # The two headings must each become their own paragraph so Markdown
        # renderers don't soft-break them onto the same visual line.
        self.assertIn(
            "一、对保守观点的激进反制\n\n（一）实际利率与美元约束并非天花板",
            formatted,
        )
        self.assertNotIn(
            "一、对保守观点的激进反制 （一）实际利率与美元约束并非天花板",
            formatted,
        )
        # Body content following the sub-section heading is still preserved.
        self.assertIn("美元 DXY 已回落 1.2%", formatted)

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

    def test_portfolio_manager_splits_inline_manager_heading_and_strips_noisy_snapshot(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "一、辩论结论\n"
                "综合结论：维持减持。\n\n"
                "二、行为逻辑 先等待发电量与折价修复的双重确认，再决定是否回补仓位。\n\n"
                "三、持仓建议 维持两成仓位，跌破清仓线则进一步减仓。\n\n"
                "反馈快照，- 立场: 维持减持。\n"
                "- 本轮新增与反驳: 焦煤与火电盈利链条继续承压。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("#### 二、行为逻辑", formatted)
        self.assertIn("先等待发电量与折价修复的双重确认", formatted)
        self.assertNotIn("#### 二、行为逻辑 先等待", formatted)
        self.assertIn("#### 三、持仓建议", formatted)
        self.assertNotIn("#### 三、持仓建议 维持两成仓位", formatted)
        self.assertNotIn("反馈快照", formatted)

    def test_portfolio_manager_joins_wrapped_ordinal_round_phrase(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "此外，中性风险分析师在第\n"
                "\n"
                "二、三轮中放宽验证条件，但该方案缺乏行动承诺。\n\n"
                "## 行为逻辑\n"
                "维持减持。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("中性风险分析师在第二、三轮中放宽验证条件", formatted)
        self.assertNotIn("在第\n\n#### 二、三轮", formatted)
        self.assertNotIn("#### 二、三轮", formatted)

    def test_portfolio_manager_strips_orphan_snapshot_items_and_scope_note(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 持仓建议\n"
                "### （一）评级\n"
                "研究结论: **减持**\n"
                "### （二）建议\n"
                "目标仓位维持在4%以下，等待成本传导修复后再评估回补。\n\n"
                "成分股层面的估值、盈利和权重信息仅作为ETF仓位调整依据，实际执行对象仍是ETF整体仓位，不对成分股给出直接交易指令。当前最关键的风险因素是5月18日工业增加值数据若低于4.5%将确认需求放缓。\n"
                "- 本轮新增与反驳: 本轮首次用聚乙烯仓单暴增79.93%反驳激进观点。\n"
                "- 待验证:\n"
                "1. 聚乙烯仓单能否去化。2. 原油期货持仓能否萎缩。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("目标仓位维持在4%以下", formatted)
        self.assertNotIn("实际执行对象仍是ETF整体仓位", formatted)
        self.assertNotIn("本轮新增与反驳", formatted)
        self.assertNotIn("待验证", formatted)
        self.assertNotIn("5月18日工业增加值", formatted)

    def test_portfolio_manager_preserves_legitimate_most_critical_prose(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 行为逻辑\n"
                "当前最关键的支撑位在2.05元，若收盘价连续3日守住该位置，则维持观察仓位。\n\n"
                "## 持仓建议\n"
                "维持持有。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("当前最关键的支撑位在2.05元", formatted)

    def test_portfolio_manager_demotes_inner_action_logic_headings(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "中性观点约束仓位，但价格结构仍未完全转弱。\n\n"
                "## 行为逻辑\n"
                "### 资金流确认\n"
                "需要份额连续净申购后再上调仓位。\n\n"
                "（一）仓位节奏\n"
                "先维持底仓，等待成交量回到20日均量上方。\n\n"
                "一、失效条件\n"
                "若价格跌破2.05元且放量至20日均量1.3倍，应先减仓。\n\n"
                "## 持仓建议\n"
                "维持持有。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("#### 二、行为逻辑", formatted)
        self.assertIn("资金流确认", formatted)
        self.assertIn("仓位节奏", formatted)
        self.assertIn("失效条件", formatted)
        self.assertNotIn("##### 资金流确认", formatted)
        self.assertNotIn("##### 一、仓位节奏", formatted)
        self.assertNotIn("#### 三、失效条件", formatted)
        self.assertIn("#### 三、持仓建议", formatted)

    def test_portfolio_manager_keeps_most_critical_sentence_before_orphan_snapshot_item(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 行为逻辑\n"
                "最关键的事件是下月CPI数据，若高于预期则先降低风险预算。\n"
                "- 立场: 持有\n"
                "- 本轮新增与反驳: 临时快照泄漏。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("最关键的事件是下月CPI数据", formatted)
        self.assertNotIn("- 立场", formatted)
        self.assertNotIn("本轮新增与反驳", formatted)

    def test_portfolio_manager_splits_dense_conclusion_and_action_logic(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "保守风险分析师最强的证据链是：第一，成本传导已结构性断裂；第二，内部对冲存在2-3个月操作滞后窗口。\n\n"
                "## 行为逻辑\n"
                "触发减持条件的具体阈值包括：布伦特原油跌破78美元/桶；原油期货持仓量连续3日萎缩超10%；聚乙烯仓单继续增长且价格跌破8000元/吨。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("保守风险分析师最强的证据链是：\n\n1. 第一，成本传导已结构性断裂", formatted)
        self.assertIn("2. 第二，内部对冲存在2-3个月操作滞后窗口", formatted)
        self.assertIn("触发减持条件的具体阈值包括：\n\n1. 布伦特原油跌破78美元/桶", formatted)

    def test_portfolio_manager_splits_long_sentence_dense_paragraphs(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 行为逻辑\n"
                "当前组合仍需降低石油ETF风险预算，因为油价上行已经从供给冲击转向资金拥挤驱动。"
                "聚乙烯仓单继续高位堆积，说明下游并未顺利承接上游成本。"
                "油运利润虽然处于高位，但运价回落时盈利弹性会快速反向释放。"
                "中国石化炼化利润修复需要库存消化周期，无法立刻抵消上游和油运回撤。"
                "因此后续执行应先保留观察仓位，再等待量价和库存信号共同修复。"
                "如果ETF折溢价连续扩大，说明产品层承接能力也在下降，不能只看油价方向。"
                "若风险预算被连续触发，组合应优先降低波动来源，而不是继续解释单个成分股的短期弹性。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn(
            "资金拥挤驱动。\n\n聚乙烯仓单继续高位堆积",
            formatted,
        )
        self.assertIn(
            "上游成本。\n\n油运利润虽然处于高位",
            formatted,
        )

    def test_portfolio_manager_full_readability_pipeline_handles_combined_failures(self):
        risk_state = {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": (
                "## 辩论结论\n"
                "保守风险分析师最强的证据链是：第一，成本传导已结构性断裂；第二，内部对冲存在2-3个月操作滞后窗口。此外，中性风险分析师在第\n\n"
                "二、三轮中放宽验证条件，但该方案缺乏行动承诺。\n\n"
                "## 行为逻辑\n"
                "当前最关键的支撑位在2.05元。触发减持条件的具体阈值包括：布伦特原油跌破78美元/桶；原油期货持仓量连续3日萎缩超10%；聚乙烯仓单继续增长且价格跌破8000元/吨。\n\n"
                "## 持仓建议\n"
                "### （一）评级\n"
                "研究结论: **减持**\n"
                "### （二）建议\n"
                "目标仓位维持在4%以下。\n"
                "成分股层面的估值、盈利和权重信息仅作为ETF仓位调整依据，实际执行对象仍是ETF整体仓位，不对成分股给出直接交易指令。当前最关键的风险因素是5月18日工业增加值数据。\n"
                "- 本轮新增与反驳: 快照泄漏。\n"
                "- 待验证: 继续跟踪。"
            ),
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("保守风险分析师最强的证据链是：\n\n1. 第一，成本传导已结构性断裂", formatted)
        self.assertIn("中性风险分析师在第二、三轮中放宽验证条件", formatted)
        self.assertIn("当前最关键的支撑位在2.05元", formatted)
        self.assertIn("触发减持条件的具体阈值包括：\n\n1. 布伦特原油跌破78美元/桶", formatted)
        self.assertIn("目标仓位维持在4%以下", formatted)
        self.assertNotIn("实际执行对象仍是ETF整体仓位", formatted)
        self.assertNotIn("本轮新增与反驳", formatted)
        self.assertNotIn("待验证", formatted)
        self.assertNotIn("5月18日工业增加值", formatted)

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

    def test_process_chunk_messages_sanitizes_nested_delivery_preamble(self):
        class FakeMessage:
            def __init__(self, message_id, content):
                self.id = message_id
                self.content = content
                self.tool_calls = []

        buffer = MessageBuffer()
        chunk = {
            "market_flow": {
                "messages": [
                    FakeMessage(
                        "m1",
                        "数据已全部获取完毕，现在撰写完整报告。\n\n"
                        "市场与资金流正文内容。",
                    )
                ]
            }
        }

        with patch("cli.main.classify_message_type", side_effect=lambda message: ("Agent", message.content)):
            process_chunk_messages(chunk, buffer)

        self.assertEqual(
            [content for _, _, content in buffer.messages],
            ["市场与资金流正文内容。"],
        )
        self.assertNotIn("数据已全部获取完毕", buffer.messages[0][2])

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

    def test_stream_state_merge_keeps_earlier_market_flow_report(self):
        accumulated = {"market_flow_report": "市场与资金流分析内容"}

        _merge_stream_state(
            accumulated,
            {
                "trader_allocation_plan": "交易计划内容",
                "risk_debate_state": {"judge_decision": "最终决策"},
            },
        )

        self.assertEqual(accumulated["market_flow_report"], "市场与资金流分析内容")
        self.assertEqual(accumulated["trader_allocation_plan"], "交易计划内容")
        self.assertEqual(accumulated["risk_debate_state"]["judge_decision"], "最终决策")

    def test_stream_state_merge_flattens_nested_meso_commodity_report(self):
        accumulated = {}

        _merge_stream_state(
            accumulated,
            {
                "meso_commodity": {
                    "meso_commodity_report": "中观大宗商品分析内容",
                }
            },
        )

        self.assertEqual(accumulated["meso_commodity_report"], "中观大宗商品分析内容")
        self.assertNotIn("meso_commodity", accumulated)

    def test_stream_state_merge_ignores_messages_without_deepcopy(self):
        class UnsafeMessage:
            def __deepcopy__(self, memo):
                raise AssertionError("messages should not be deep-copied into final state")

        accumulated = {"market_flow_report": "市场与资金流分析内容"}

        _merge_stream_state(
            accumulated,
            {
                "messages": [UnsafeMessage()],
                "market_flow": {"messages": [UnsafeMessage()]},
                "trader_allocation_plan": "交易计划内容",
            },
        )

        self.assertEqual(accumulated["market_flow_report"], "市场与资金流分析内容")
        self.assertEqual(accumulated["trader_allocation_plan"], "交易计划内容")
        self.assertNotIn("messages", accumulated)
        self.assertNotIn("market_flow", accumulated)

    def test_analyst_statuses_capture_nested_meso_commodity_report(self):
        buffer = MessageBuffer()
        buffer.init_for_analysis(["meso_commodity"])

        update_analyst_statuses(
            buffer,
            {
                "meso_commodity": {
                    "meso_commodity_report": "中观大宗商品分析内容",
                }
            },
        )

        self.assertEqual(
            buffer.report_sections["meso_commodity_report"],
            "中观大宗商品分析内容",
        )
        self.assertEqual(buffer.agent_status["Meso Commodity Analyst"], "completed")

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
                "market_flow_report": "市场与资金流分析内容A",
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
            self.assertIn("### 市场与资金流分析", report_text)
            self.assertIn("市场与资金流分析内容A", report_text)
            candidate_text = (Path(tmpdir) / "ranked_candidates" / "01_159915_SZ.md").read_text()
            self.assertIn("## 市场与资金流分析", candidate_text)
            self.assertIn("市场与资金流分析内容A", candidate_text)

    def test_display_candidate_pool_report_includes_final_decision_heading(self):
        candidates = [
            {
                "ticker": "159915.SZ",
                "rating": "BUY",
                "score": "5",
                "suggested_weight_pct": 50.0,
                "market_flow_report": "市场与资金流分析内容A",
                "final_allocation_decision": "## 辩论结论\n最终配置建议: **买入**",
            }
        ]

        class RecordingConsole:
            def __init__(self):
                self.calls = []

            def print(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        recording_console = RecordingConsole()
        with patch("cli.main.console", recording_console):
            display_candidate_pool_report(candidates)

        panel = recording_console.calls[3][0][0]
        self.assertIn("## 市场与资金流分析", panel.renderable.markup)
        self.assertIn("## 投资组合配置决策", panel.renderable.markup)
        self.assertIn("最终配置建议: **买入**", panel.renderable.markup)

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

    def test_prepare_report_markdown_relevels_trader_headings_to_h2(self):
        normalized = _prepare_report_markdown(
            "一、配置逻辑\n"
            "1. 第一条交易逻辑。\n\n"
            "四、执行倾向\n"
            "**增持**",
            2,
        )

        self.assertIn("## 一、配置逻辑", normalized)
        self.assertRegex(normalized, r"(?m)^## [二四]、执行倾向$")
        self.assertNotRegex(normalized, r"(?m)^#(?!#)\s+")

    def test_complete_report_displays_trader_headings_below_h1(self):
        class RecordingConsole:
            def __init__(self):
                self.calls = []

            def print(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        # Keep the state minimal so this test isolates the trader display path.
        final_state = {
            "trader_allocation_plan": (
                "一、配置逻辑\n"
                "1. 境内长端利率对冲海外实际收益率上行。\n\n"
                "四、执行倾向\n"
                "**增持**"
            )
        }
        recording_console = RecordingConsole()

        with patch("cli.main.console", recording_console):
            display_complete_report(final_state)

        rendered_markdown = [
            getattr(getattr(call[0][0], "renderable", None), "markup", "")
            for call in recording_console.calls
            if call[0]
        ]
        trader_markup = "\n".join(markup for markup in rendered_markdown if "配置逻辑" in markup)
        self.assertIn("## 一、配置逻辑", trader_markup)
        self.assertNotRegex(trader_markup, r"(?m)^#(?!#)\s+")


if __name__ == "__main__":
    unittest.main()
