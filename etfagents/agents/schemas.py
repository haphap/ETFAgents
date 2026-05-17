import re
from difflib import SequenceMatcher
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from etfagents.agents.utils.agent_utils import (
    collapse_blank_lines,
    format_chinese_positioning_recommendation,
    get_output_language,
    localize_label,
    localize_rating_term,
    strip_manager_instruction_leakage,
    strip_constituent_trade_instructions,
)
from etfagents.agents.utils.rating import detect_chinese_rating, detect_english_rating


class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class Trigger(BaseModel):
    metric: str = Field(description="Metric to evaluate, e.g. close, open, high, low, volume, sma_20, close_50_sma, volume_ratio_20d, pnl_pct, or weight_pct.")
    op: Literal["<", "<=", ">", ">=", "==", "in_range"] = Field(description="Comparison operator for the trigger.")
    threshold: float | tuple[float, float] = Field(description="Threshold value or inclusive range for the trigger.")
    action: Literal["add", "reduce", "exit", "rebalance", "hold"] = Field(description="Action to take when the trigger fires.")
    delta_pct: float | None = Field(default=None, description="Optional percentage-point change in target portfolio weight when the trigger fires.")
    target_weight_pct: float | None = Field(default=None, description="Optional target portfolio weight in percent to set directly when the trigger fires.")
    note: str = Field(default="", description="Short explanation of the trigger and why it matters.")


class RiskRule(BaseModel):
    metric: str = Field(description="Risk metric to evaluate, e.g. close, low, pnl_pct, weight_pct, or volume_ratio_20d.")
    op: Literal["<", "<=", ">", ">=", "==", "in_range"] = Field(description="Comparison operator for the risk rule.")
    threshold: float | tuple[float, float] = Field(description="Threshold value or inclusive range for the risk rule.")
    action: Literal["cap", "floor", "exit", "hold"] = Field(description="Risk action to take when the rule fires.")
    max_weight_pct: float | None = Field(default=None, description="Optional maximum portfolio weight in percent after the rule fires.")
    min_weight_pct: float | None = Field(default=None, description="Optional minimum portfolio weight in percent after the rule fires.")
    note: str = Field(default="", description="Short explanation of the risk rule and why it matters.")


_ETF_ONLY_ALLOCATION_SCOPE = (
    "The execution target is the ETF itself, not individual constituent stocks. "
    "Use holdings and constituent weights only as attribution evidence; do not recommend buying, selling, trimming, clearing, or retaining named constituents."
)


class ResearchPlan(BaseModel):
    debate_conclusion: str = Field(description="A detailed synthesis paragraph comparing both sides, naming the strongest evidence from each, and explaining the decisive weakness in the losing view for ETF allocation.")
    action_logic: str = Field(description="A detailed evidence-to-allocation paragraph linking ETF structure, flows, catalysts, downside boundaries, and confirmation or invalidation triggers to the final decision.")
    positioning_recommendation: str = Field(description=f"Actionable ETF allocation guidance with execution details, exposure sizing, concrete add or reduce conditions, rebalance triggers, and monitoring priorities. Must cite exact price or moving-average levels, volume or fund-flow thresholds, and ETF structure checks rather than vague confirmation language. Restate the numeric level inline in the same sentence instead of referring readers back to an earlier report. {_ETF_ONLY_ALLOCATION_SCOPE}")
    rating: PortfolioRating = Field(description="Final research-manager rating for ETF allocation.")
    snapshot_stance: str = Field(description="Concise stance for the feedback snapshot.")
    snapshot_new_and_rebuttal: str = Field(description="What was newly added this round and how it rebuts the opposing case.")
    snapshot_to_verify: str = Field(description="Specific follow-up points or triggers to verify next.")


class TraderProposal(BaseModel):
    thesis: str = Field(description="Concise ETF allocation thesis explaining the proposed action.")
    execution_plan: str = Field(description=f"Concrete ETF allocation plan with support or resistance references, exact price or moving-average levels, volume or fund-flow thresholds, catalyst triggers, ETF share or premium-discount checks, and explicit add, reduce, rotate, or exit conditions. Do not say 'wait for confirmation' without numeric thresholds. Write the numeric level inline instead of saying 'the key level in the market report'. {_ETF_ONLY_ALLOCATION_SCOPE}")
    risk_management: str = Field(description="Risk controls, rebalance or invalidation signals, monitoring thresholds, and the actions to take when those thresholds are breached.")
    rating: PortfolioRating = Field(description="Trader recommendation for ETF exposure.")
    target_weight_pct: float | None = Field(default=None, description="Structured target portfolio weight in percent for this ETF, from 0 to 100. Use when the execution plan implies a single target sizing.")
    target_weight_band: tuple[float, float] | None = Field(default=None, description="Structured target weight band in percent as (low, high), from 0 to 100. Use when the plan specifies a sizing range rather than a single weight.")
    execution_timing: Literal["same_close", "next_open", "next_close"] | None = Field(default=None, description="Structured execution timing for the backtest signal. Use same_close, next_open, or next_close.")
    add_triggers: list[Trigger] = Field(default_factory=list, description="Structured add triggers that increase the ETF target weight when their conditions are met.")
    reduce_triggers: list[Trigger] = Field(default_factory=list, description="Structured reduce triggers that trim the ETF target weight when their conditions are met.")
    exit_triggers: list[Trigger] = Field(default_factory=list, description="Structured exit triggers that close or nearly close the ETF position when their conditions are met.")
    rebalance_triggers: list[Trigger] = Field(default_factory=list, description="Structured rebalance triggers that restore or rotate the ETF position when their conditions are met.")
    risk_controls: list[RiskRule] = Field(default_factory=list, description="Structured risk rules that cap, floor, or exit the ETF position when risk conditions are breached.")


class PortfolioDecision(BaseModel):
    debate_conclusion: str = Field(description="A detailed synthesis of the full risk debate across all perspectives, explicitly comparing aggressive, conservative, and neutral cases and stating why the losing view was overruled for ETF allocation.")
    action_logic: str = Field(description="A detailed portfolio-manager paragraph showing how ETF evidence leads to sizing, hedging, rebalance triggers, and risk controls.")
    positioning_recommendation: str = Field(description=f"Final actionable ETF portfolio recommendation and implementation guidance with target exposure, execution sequence, rebalance rules, and monitoring priorities. Must cite exact price or moving-average levels, volume or fund-flow thresholds, and ETF structure checks rather than vague confirmation language. Restate those numeric levels inline rather than telling the reader to look back at the market report. {_ETF_ONLY_ALLOCATION_SCOPE}")
    rating: PortfolioRating = Field(description="Final portfolio-manager rating for ETF allocation.")
    target_weight_pct: float | None = Field(default=None, description="Structured target portfolio weight in percent for this ETF, from 0 to 100. Use when the final recommendation implies a single target sizing.")
    target_weight_band: tuple[float, float] | None = Field(default=None, description="Structured target weight band in percent as (low, high), from 0 to 100. Use when the final recommendation specifies a sizing range rather than a single weight.")
    execution_timing: Literal["same_close", "next_open", "next_close"] | None = Field(default=None, description="Structured execution timing for the backtest signal. Use same_close, next_open, or next_close.")
    add_triggers: list[Trigger] = Field(default_factory=list, description="Structured add triggers that increase the ETF target weight when their conditions are met.")
    reduce_triggers: list[Trigger] = Field(default_factory=list, description="Structured reduce triggers that trim the ETF target weight when their conditions are met.")
    exit_triggers: list[Trigger] = Field(default_factory=list, description="Structured exit triggers that close or nearly close the ETF position when their conditions are met.")
    rebalance_triggers: list[Trigger] = Field(default_factory=list, description="Structured rebalance triggers that restore or rotate the ETF position when their conditions are met.")
    risk_controls: list[RiskRule] = Field(default_factory=list, description="Structured risk rules that cap, floor, or exit the ETF position when risk conditions are breached.")
    snapshot_stance: str = Field(description="Concise stance for the feedback snapshot.")
    snapshot_new_and_rebuttal: str = Field(description="What was newly added this round and how it rebutted competing views.")
    snapshot_to_verify: str = Field(description="Specific items or triggers to verify next.")


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


def _render_snapshot(stance: str, new_and_rebuttal: str, to_verify: str) -> str:
    if _is_chinese_output():
        return (
            "反馈快照:\n"
            f"- 立场: {stance.strip()}\n"
            f"- 本轮新增与反驳: {new_and_rebuttal.strip()}\n"
            f"- 待验证: {to_verify.strip()}"
        )
    return (
        "FEEDBACK SNAPSHOT:\n"
        f"- Stance: {stance.strip()}\n"
        f"- New this round & rebuttal: {new_and_rebuttal.strip()}\n"
        f"- To verify: {to_verify.strip()}"
    )


def _expected_rating_text(rating: PortfolioRating) -> str:
    return localize_rating_term(rating.value) if _is_chinese_output() else rating.value.upper()


def _compact_text(text: str) -> str:
    return re.sub(r"[\s:：,，。.!！？/\-—_()（）]+", "", text or "").strip().lower()


def _normalize_portfolio_chinese_phrasing(text: str) -> str:
    content = (text or "").strip()
    if not content or not _is_chinese_output():
        return content
    normalized = content.replace("本组合对", "对")
    normalized = normalized.replace("本组合当前", "当前组合")
    normalized = normalized.replace("本组合", "组合层面")
    return normalized


def _is_placeholder_like(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return True

    exact_placeholders = {
        "评估双方论证强度总结核心论点与致命弱点",
        "估值催化节奏下行边界与确认证伪信号的推演路径",
        "明确评级与执行指引",
        "本轮新增与反驳",
        "待验证",
        "balancedconclusionafterevaluatingbothbullandbearcases",
        "evidencetoactionlogicexplainingvaluationcatalystsrisksandtriggers",
        "actionabletradingguidancewithexecutiondetails",
        "synthesisofthefullriskdebateacrossallperspectives",
        "portfoliomanagerlogicfromevidencetosizingandexecution",
        "finalactionableportfoliorecommendationandimplementationguidance",
        "concisestanceforthefeedbacksnapshot",
        "whatwasnewlyaddedthisroundandhowitrebutstheopposingcase",
        "specificfollowuppointsortriggerstoverifynext",
        "whatwasnewlyaddedthisroundandhowitrebuttedcompetingviews",
        "specificitemsortriggerstoverifynext",
        "concisetradingthesisexplainingtheproposedaction",
        "concreteexecutionplanwithentryaddreduceorexitconditions",
        "riskcontrolsinvalidationsignalsandmonitoringitems",
    }
    if compact in exact_placeholders:
        return True

    placeholder_patterns = (
        r"评估.*论证强度.*总结.*核心论点.*致命弱点",
        r"估值.*催化节奏.*下行边界.*确认.*证伪信号",
        r"明确评级.*执行指引",
        r"balanced.*bull.*bear.*cases",
        r"evidence.*action.*logic.*valuation.*catalysts",
        r"actionable.*guidance.*execution.*details",
        r"synthesis.*risk.*debate",
        r"portfolio.*logic.*evidence.*execution",
        r"concrete.*execution.*entry.*reduce.*exit",
        r"risk.*controls.*monitoring.*items",
    )
    return any(re.search(pattern, compact, re.IGNORECASE) for pattern in placeholder_patterns)


def _contains_explicit_rating_marker(text: str) -> bool:
    if not text:
        return False
    if _is_chinese_output():
        return any(
            marker in text
            for marker in ("建议评级", "评级", "配置评级", "研究结论", "执行倾向", "最终配置建议", "最终交易建议", "建议买入", "建议增持", "建议持有", "建议减持", "建议卖出", "维持买入", "维持增持", "维持持有", "维持减持", "维持卖出", "采取买入策略", "采取增持策略", "采取持有策略", "采取减持策略", "采取卖出策略")
        )
    upper_text = text.upper()
    return any(
        marker in upper_text
        for marker in ("RECOMMENDATION:", "RATING:", "FINAL ALLOCATION PROPOSAL:", "FINAL TRANSACTION PROPOSAL:", "RECOMMEND BUY", "RECOMMEND OVERWEIGHT", "RECOMMEND HOLD", "RECOMMEND UNDERWEIGHT", "RECOMMEND SELL", "MAINTAIN BUY", "MAINTAIN OVERWEIGHT", "MAINTAIN HOLD", "MAINTAIN UNDERWEIGHT", "MAINTAIN SELL")
    )


def _contains_any_rating_term(text: str) -> bool:
    if not text:
        return False
    if _is_chinese_output():
        return any(term in text for term in ("买入", "增持", "持有", "减持", "卖出"))
    upper_text = text.upper()
    return any(term in upper_text for term in ("BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL"))


def _is_recommendation_only_segment(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    if _is_chinese_output():
        patterns = (
            r"^(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)[:：].+$",
            r"^(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)(?:为)?(?:买入|增持|持有|减持|卖出)[。！!]*$",
            r"^针对[^，。,；;]+[，,]?(?:建议|应|宜)(?:采取)?(?:买入|增持|持有|减持|卖出)(?:策略)?[。！!]*$",
            r"^(?:建议|维持|转为)(?:买入|增持|持有|减持|卖出)(?:策略)?[。！!]*$",
            r"^建议采取(?:买入|增持|持有|减持|卖出)策略[。！!]*$",
        )
    else:
        patterns = (
            r"^(?:RECOMMENDATION|RATING|FINALALLOCATIONPROPOSAL|FINALTRANSACTIONPROPOSAL)[:：].+$",
            r"^(?:RECOMMEND|MAINTAIN|SHIFTTO|MOVETO)(?:BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL)[.!]*$",
            r"^FOR[A-Z0-9._-]+,?(?:RECOMMEND|MAINTAIN)(?:BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL)[.!]*$",
        )
    return any(re.match(pattern, compact, re.IGNORECASE) for pattern in patterns)


def _is_recommendation_restating_sentence(text: str) -> bool:
    sentence = (text or "").strip()
    if not sentence:
        return False
    if _is_chinese_output():
        return bool(
            re.match(
                r"^(?:综合[^。！？!?]{0,40}证据[，,])?"
                r"(?:(?:本组合|组合层面|当前组合|本次配置|对(?:该ETF|[A-Z0-9.\-]+)|对于(?:该ETF|[A-Z0-9.\-]+))[^。！？!?]{0,24})?"
                r"(?:明确)?(?:建议|判断|结论|评级|配置建议)(?:为|是)?\s*\**(?:买入|增持|持有|减持|卖出)\**[。！!？?]*$",
                sentence,
                re.IGNORECASE,
            )
        )
    return bool(
        re.match(
            r"^(?:based on [^.?!]{0,60},\s*)?"
            r"(?:(?:for|on)\s+[A-Z0-9.\-]+[^.?!]{0,24})?"
            r"(?:the )?(?:clear )?(?:recommendation|view|stance|allocation recommendation|decision)\s*(?:is|remains)?\s*\**(?:buy|overweight|hold|underweight|sell)\**[.!?]*$",
            sentence,
            re.IGNORECASE,
        )
    )


def _strip_recommendation_restating_sentences(text: str) -> str:
    content = (text or "").strip()
    if not content:
        return ""
    kept = [
        sentence
        for sentence in _split_sentences(content)
        if not _is_recommendation_restating_sentence(sentence)
    ]
    return "\n".join(kept).strip()


def _strip_leading_section_headings(text: str, headings: tuple[str, ...]) -> str:
    content = (text or "").strip()
    if not content or not headings:
        return content

    escaped_headings = sorted({re.escape(heading.strip()) for heading in headings if heading.strip()}, key=len, reverse=True)
    if not escaped_headings:
        return content

    heading_pattern = "|".join(escaped_headings)
    numbered_heading = (
        rf"(?:[#>*\-\s]*)?"
        rf"(?:(?:[一二三四五六七八九十]+|\d+)\s*[、.．)）\-:：]\s*)?"
        rf"(?:{heading_pattern})\s*"
    )
    line_pattern = re.compile(
        rf"^(?:{numbered_heading})(?:(?:[,，;；/、]\s*|\s+)(?:{numbered_heading}))*$",
        re.IGNORECASE,
    )

    lines = [line.strip() for line in re.split(r"\n+", content) if line.strip()]
    while lines and line_pattern.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()


def _has_conditional_prefix(prefix: str) -> bool:
    return bool(re.search(r"(若|如果|如|待|当|一旦|if|when|unless)", prefix, re.IGNORECASE))


def _has_conflicting_primary_action(text: str, rating: PortfolioRating) -> bool:
    content = (text or "").strip()
    if not content:
        return False

    if _is_chinese_output():
        bullish_pattern = re.compile(r"(买入|建仓|加仓|增持|提高仓位|扩大仓位|回补)")
        bearish_pattern = re.compile(r"(减持|减仓|降低敞口|卖出|退出|清仓|止盈)")
    else:
        bullish_pattern = re.compile(r"(buy|build|add|increase exposure|top up|rebuild)", re.IGNORECASE)
        bearish_pattern = re.compile(r"(reduce|trim|sell|exit|cut exposure|take profit)", re.IGNORECASE)

    if rating in {PortfolioRating.BUY, PortfolioRating.OVERWEIGHT}:
        conflicting_pattern = bearish_pattern
    elif rating in {PortfolioRating.UNDERWEIGHT, PortfolioRating.SELL}:
        conflicting_pattern = bullish_pattern
    else:
        conflicting_pattern = re.compile(
            f"{bullish_pattern.pattern}|{bearish_pattern.pattern}",
            bullish_pattern.flags | bearish_pattern.flags,
        )

    for match in conflicting_pattern.finditer(content):
        sentence_prefix = re.split(r"[。！？!?；;\n]", content[:match.start()])[-1]
        clause_prefix = re.split(r"[，,、]", sentence_prefix)[-1]
        suffix = content[match.end():match.end() + 8]
        if (
            _has_conditional_prefix(clause_prefix)
            or re.search(r"(若|如果|如|待|当|一旦|条件|触发)", clause_prefix)
            or re.search(r"(?:可|才|再|允许|考虑|暂缓)[^，,、。！？!?；;\n]{0,16}$", clause_prefix)
            or re.search(r"(条件|触发)", sentence_prefix)
            or re.match(r"(?:条件|触发)", suffix)
        ):
            continue
        return True
    return False


def _sanitize_positioning_recommendation(text: str, rating: PortfolioRating) -> str:
    content = strip_manager_instruction_leakage((text or "").strip())
    if not content:
        return _default_positioning_guidance(rating)
    content = _normalize_portfolio_chinese_phrasing(content)

    lines = []
    for raw_line in re.split(r"\n+", content):
        line = raw_line.strip()
        if not line:
            continue
        if _contains_explicit_rating_marker(line) and _is_recommendation_only_segment(line):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    if _is_chinese_output():
        cleaned = re.sub(
            r"(?:^|(?<=[\n。！？!?；;]))\s*(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)\s*[:：]?\s*\**(?:买入|增持|持有|减持|卖出)\**[。！!？?\s]*",
            "\n",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:^|\n)\s*针对[^\n。！？!?]{0,60}?(?:建议|应|宜)(?:采取)?(?:买入|增持|持有|减持|卖出)(?:策略)?[。！!?\n]*",
            "\n",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:^|\n)\s*(?:建议|维持|转为)(?:买入|增持|持有|减持|卖出)(?:策略)?[。！!?\n]*",
            "\n",
            cleaned,
        )
        cleaned = re.sub(
            r"(?:^|\n)\s*(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)(?:为)?\s*(?:买入|增持|持有|减持|卖出)[。！!?\n]*",
            "\n",
            cleaned,
        )
    else:
        cleaned = re.sub(
            r"(?:^|(?<=[\n.!?;]))\s*(?:recommendation|rating|final allocation proposal|final transaction proposal|research view|execution bias)\s*[:：]?\s*\**(?:buy|overweight|hold|underweight|sell)\**[.!?\s]*",
            "\n",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:^|\n)\s*for [^\n.]{0,60}?(?:recommend|maintain|shift to|move to) (?:buy|overweight|hold|underweight|sell)[.!?\n]*",
            "\n",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:^|\n)\s*(?:recommend|maintain|shift to|move to) (?:buy|overweight|hold|underweight|sell)[.!?\n]*",
            "\n",
            cleaned,
            flags=re.IGNORECASE,
        )

    split_pattern = r"(?<=[。！？!?])\s*" if _is_chinese_output() else r"(?<=[.!?])\s+"
    segments = []
    for segment in re.split(split_pattern, cleaned):
        sentence = segment.strip()
        if not sentence:
            continue
        if _contains_explicit_rating_marker(sentence) and _is_recommendation_only_segment(sentence):
            continue
        if _is_recommendation_restating_sentence(sentence):
            continue
        segments.append(sentence)
    cleaned = "\n".join(segments).strip()
    cleaned = re.sub(r"(?m)^[，,、；;:：\-\s]+", "", cleaned).strip()
    if _is_placeholder_like(cleaned) or _has_conflicting_primary_action(cleaned, rating):
        return _default_positioning_guidance(rating)
    return cleaned or _default_positioning_guidance(rating)


def _default_research_positioning_guidance(rating: PortfolioRating, context_text: str = "") -> str:
    if _is_chinese_output():
        support_anchor = _market_level_anchor_clause(
            context_text,
            "关键支撑与均线",
        )
        mapping = {
            PortfolioRating.BUY: (
                f"先按目标仓位的50%—60%建立底仓，确认价格站稳{support_anchor}、成交量连续高于近20日均量且份额继续净申购后，再把仓位逐步提升到目标上沿。"
                "若溢折价异常扩大、主要支撑失守或行业盈利验证不再改善，则暂停加仓并把仓位收回到底仓。"
                "执行上按周度复核价格、量能、份额变化与宏观验证链条，任一环节失效都不追高扩仓。"
            ),
            PortfolioRating.OVERWEIGHT: (
                "先把现有仓位提高到目标上限的70%—80%，只有在价格承接、量能、溢折价和资金流继续同向改善时才进一步增配。"
                "若催化兑现慢于预期、份额恢复停滞或前十大持仓集中度继续抬升而盈利修正未跟上，则先把超配部分降回基准仓位。"
                "再平衡上优先看价格确认、产品层验证和行业盈利线索是否仍保持同向共振。"
            ),
            PortfolioRating.HOLD: (
                f"维持现有基准仓位，不新增方向性敞口，新增资金优先等待价格重新站稳{support_anchor}、成交量回到近期均量上方、份额或资金流同步改善后再考虑上调一个档位。"
                "若价格跌破主要支撑、资金流重新转负或产品层指标恶化，则先把仓位降回更保守区间而不是被动承受回撤。"
                "执行上按周度复核量价、份额变化、溢折价和宏观/行业验证信号，只有验证链条继续强化时才从持有转向增配。"
            ),
            PortfolioRating.UNDERWEIGHT: (
                "先把仓位压回风险预算下沿或目标仓位的30%—40%，反弹只有在价格修复、量能放大和份额恢复净流入同时出现时才允许暂缓减仓。"
                f"若反弹无法收复{support_anchor}、溢折价走弱或行业盈利线索继续下修，则继续分批削减敞口并收缩风险预算。"
                "再平衡重点盯住价格修复质量、产品层承接与风险释放节奏，而不是仅凭单日反弹回补仓位。"
            ),
            PortfolioRating.SELL: (
                "把剩余仓位降到0%—10%的观察仓或直接清仓，只有在基本面、价格结构和产品层指标共同修复时才重新评估是否回补。"
                "若后续仍看不到量价承接、份额回流和盈利修正改善，就继续保持低暴露，不因为短期反弹提前回补。"
                "执行上优先处理流动性和回撤控制，把再入场判断留给下一轮完整验证。"
            ),
        }
        return mapping[rating]
    support_anchor = _market_level_anchor_clause(
        context_text,
        "key support and moving-average anchors",
    )
    mapping = {
        PortfolioRating.BUY: (
            f"Start with roughly 50% to 60% of target exposure, then scale toward the upper bound only after price reclaims {support_anchor}, volume improves, and ETF flow confirmation improve together. "
            "If support breaks, premium-discount widens abnormally, or earnings confirmation stalls, pause the build and cut back to the starter size. "
            "Rebalance weekly against price structure, volume, product-level checks, and macro confirmation rather than chasing a single strong session."
        ),
        PortfolioRating.OVERWEIGHT: (
            "Lift the position to roughly 70% to 80% of the intended overweight first, and only move to full overweight if price support, volume, premium-discount, and flows keep improving together. "
            "If catalyst delivery lags or concentration rises without matching earnings support, trim the add-on back to benchmark size. "
            "Rebalance around confirmation quality, not just around a headline-driven rally."
        ),
        PortfolioRating.HOLD: (
            f"Keep benchmark exposure in place and avoid adding directional risk until price reclaims {support_anchor}, volume recovers versus its recent average, and ETF flows improve at the same time. "
            "If support fails again or product-level indicators deteriorate, reduce back to a more defensive baseline instead of passively absorbing drawdown. "
            "Review price, volume, flows, premium-discount, and macro or industry confirmation weekly before shifting from hold to add."
        ),
        PortfolioRating.UNDERWEIGHT: (
            "Cut the position back toward the low end of the risk budget, roughly 30% to 40% of target exposure, and only pause the reduction if price repair, stronger volume, and ETF flow stabilization arrive together. "
            f"If rebounds fail at {support_anchor} or earnings signals keep weakening, continue trimming in stages and keep risk budget tight. "
            "Rebalance around repair quality and risk-release cadence rather than short-term relief rallies."
        ),
        PortfolioRating.SELL: (
            "Reduce exposure to zero or to a token 0% to 10% watch position, and only reconsider entry after fundamentals, price structure, and product-level metrics all repair together. "
            "If there is still no flow support or earnings repair, stay sidelined and do not buy back a reflex rally. "
            "Keep the focus on liquidity and drawdown control until a new full validation window opens."
        ),
    }
    return mapping[rating]


def _default_positioning_guidance(rating: PortfolioRating, context_text: str = "") -> str:
    detailed = _default_research_positioning_guidance(rating, context_text)
    first_sentence = re.split(r"(?<=[。.])\s*", detailed, maxsplit=1)[0]
    return first_sentence if first_sentence else detailed


def _default_debate_conclusion(rating: PortfolioRating) -> str:
    if _is_chinese_output():
        mapping = {
            PortfolioRating.BUY: "整场辩论中，看多一侧不仅更充分地证明了产业趋势、盈利兑现与价格承接之间的正向联动，也更清楚地解释了为何短期波动不足以破坏中期上行结构。相较之下，看空一侧虽然提示了估值与节奏风险，但未能证明这些风险已经足以推翻主线逻辑，因此当前结论更偏向积极布局而不是继续观望。",
            PortfolioRating.OVERWEIGHT: "整场辩论中，看多一侧在产业趋势、催化兑现与盈利韧性上的论证更占优，说明上行逻辑仍是主导变量；但看空一侧关于波动、估值与兑现节奏的提醒也提示仓位不宜一次性放大。综合来看，更合理的结论是在保留风险边界的前提下逐步增配，而不是激进满仓。",
            PortfolioRating.HOLD: "整场辩论中，多空双方都给出了成立的证据：乐观一侧证明了中期逻辑尚未被破坏，谨慎一侧则指出短期估值、节奏与价格确认仍不够充分。由于现阶段还缺少能够打破平衡的新证据，最稳妥的结论不是贸然加仓或减仓，而是先维持现有敞口并等待更明确的验证信号。",
            PortfolioRating.UNDERWEIGHT: "整场辩论中，偏谨慎一侧对估值约束、风险释放节奏和下行边界的论证更完整，说明当前风险重定价的压力尚未结束。即便乐观一侧提出了中长期逻辑，其关键前提仍依赖后续催化兑现与价格结构修复，因此当前更适合先降低敞口、把仓位收回到更安全的水平。",
            PortfolioRating.SELL: "整场辩论中，看空一侧对基本面下修、技术破位和风险收益失衡的论证最具决定性，并且更清楚地说明了继续持有的代价正在上升。相比之下，乐观论点仍停留在潜在修复或远期改善的假设上，尚不足以抵消当前下行风险，因此更合理的结论是退出仓位而不是继续承受回撤。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "Across the full debate, the bullish side made the more complete case on trend durability, earnings follow-through, and price support, and it also explained more convincingly why the recent risks are not yet thesis-breaking. The opposing side raised valid caution flags, but it did not show that those risks are strong enough to overturn the broader upside setup, so active accumulation is more justified than continued hesitation.",
        PortfolioRating.OVERWEIGHT: "Across the full debate, the bullish evidence is stronger on balance because the upside thesis still has better support from catalysts, earnings resilience, and market structure. Even so, the cautious side made a credible case that volatility and timing risk still matter, so the right conclusion is controlled upside exposure rather than an all-in posture.",
        PortfolioRating.HOLD: "Across the full debate, both sides surfaced credible evidence: the bullish camp showed that the core thesis is still intact, while the cautious camp showed that timing, valuation, and confirmation risk remain unresolved. Because neither side produced the decisive incremental evidence needed to justify a bigger exposure change, maintaining current positioning is more disciplined than forcing either an add or a reduction.",
        PortfolioRating.UNDERWEIGHT: "Across the full debate, the bearish side made the stronger case on valuation pressure, risk-release cadence, and downside boundaries, which means the market is still repricing risk rather than rewarding conviction. The bullish case still depends on future confirmation rather than present proof, so trimming exposure is more appropriate than defending a full-sized position.",
        PortfolioRating.SELL: "Across the full debate, the bearish side presented the decisive case on deteriorating fundamentals, technical breakdown risk, and an unfavorable risk-reward profile. The more optimistic view still relies on future stabilization rather than current evidence, so exiting is more appropriate than continuing to absorb drawdown while waiting for a thesis repair that has not yet materialized.",
    }
    return mapping[rating]


def _default_action_logic(rating: PortfolioRating) -> str:
    if _is_chinese_output():
        mapping = {
            PortfolioRating.BUY: "当前的明确动作是买入，而不是继续观望，因为这意味着上方报告已经同时给出了更强的主线证据：宏观冲击对该 ETF 的核心暴露不再构成压制，行业供需或库存信号正在改善，且市场与资金流开始验证这一修复。执行上不能把“看多”停留在口号层面，而要把仓位放大建立在可观察的证据上：价格重新站上关键位、成交量或持仓量放大、主要持仓的盈利与催化继续兑现。只要这些证据仍在强化，就可以沿着既定节奏分批加仓；一旦出现宏观异象反向扩大、产业数据再度转弱或量价验证失效，就必须立刻放慢节奏并重新审视买入理由。",
            PortfolioRating.OVERWEIGHT: "当前的明确动作是增持，因为主线逻辑仍偏向有利一侧，但证据强度还不足以支持一次性把风险敞口推到极限。更合适的做法是在已有底仓上逐步加码，把每一步加仓都和新证据绑定起来：例如宏观错配缓解、行业价格与库存出现改善、头部持仓盈利预期继续上修、以及 ETF 自身的流动性和份额变化没有恶化。这样做的意义，不是机械地“看多”，而是在确认赔率和胜率同步改善时放大收益暴露；若后续出现催化递延、利润兑现弱于预期或价格结构转差，就应暂停增持并把仓位退回更中性的水平。",
            PortfolioRating.HOLD: "当前的明确动作是持有，因为现有证据足以说明不必急于撤退，但还不足以支持立即扩大敞口。换句话说，基准判断并不是“没有观点”，而是上行与下行的关键证据仍在拉锯：宏观环境没有坏到必须减仓，可产业、盈利、流动性或价格确认里仍有至少一环没有完成闭合。接下来最重要的不是空泛地“继续观察”，而是盯住真正能改写结论的异象：例如关键支撑是否被重新站稳、成交量和份额是否同步修复、行业库存与价格是否出现方向一致的变化、主要持仓的业绩验证是否落地。只要这些证据没有向同一方向集中，维持仓位就是更有纪律的动作；一旦验证集中向上，可转入增持；若异象集中转弱，则应切换为减仓。",
            PortfolioRating.UNDERWEIGHT: "当前的明确动作是减持，因为风险释放速度快于利多兑现速度，继续维持原有仓位相当于默认承担一个尚未被充分定价的回撤过程。这里的重点不是宣告长期逻辑彻底结束，而是承认当前最有信息量的证据——宏观压力、行业供需恶化、利润预期下修、或价格与资金流背离——更支持先把ETF净敞口降下来。执行上只能调整这只ETF在组合中的整体目标权重，成分股风险用于解释为什么要降ETF仓位，而不是对成分股下达清仓或减持指令；只有当宏观异象缓和、产业数据止跌回升、并且市场重新给出价格与流动性的双重确认时，才考虑逐步回补ETF仓位，而不是抢跑逆势加仓。",
            PortfolioRating.SELL: "当前的明确动作是卖出，因为最新证据链已经不再支持继续忍受持仓风险：如果宏观冲击仍在加深、行业景气与盈利预期同步走弱、而价格结构又没有出现可靠修复，那么继续持有本身就是一种没有被补偿的风险暴露。此时最重要的不是寻找安慰性理由，而是承认基准情景已经转向防守，并把资金从一个下行概率更高的敞口中撤出来。只有在后续重新看到基本面修复、价格站回关键位、量能与资金流再度转正这些条件同时出现时，才值得重新评估入场；在那之前，回避风险比抄底冲动更有价值。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "The current decision works only if three conditions continue to hold together: valuation remains supportive, catalysts keep improving, and price structure does not break down. That means execution should favor staged accumulation rather than a one-shot position, with adds tied to confirmation in volume, earnings follow-through, and catalyst delivery. If those validation signals weaken, the build pace should slow immediately and the bullish thesis should be re-tested rather than assumed.",
        PortfolioRating.OVERWEIGHT: "The case supports adding exposure, but only in a measured way, because the upside thesis is still stronger than the downside case while volatility and timing risk remain real. Adds should therefore be linked to catalyst follow-through, valuation digestion, and price support rather than pure momentum chasing. If earnings delivery slips, catalysts fade, or price structure deteriorates, the right move is to pause the adds and move back toward neutral exposure.",
        PortfolioRating.HOLD: "The disciplined move is to maintain current exposure because the upside case is not yet strong enough to justify adding, while the downside case is not yet severe enough to force an immediate trim. The key is to keep monitoring support levels, volume and fund-flow behavior, ETF structure stability, and the next round of macro confirmation. If those inputs improve together, the setup can be revisited for an add; if support breaks or structure quality worsens, the stance should shift toward reduction.",
        PortfolioRating.UNDERWEIGHT: "The core logic is to reduce ETF net exposure before the market finishes repricing the current risks, rather than waiting passively for volatility to do the damage. Execution may adjust only the ETF's overall portfolio weight; constituent risks explain why the ETF weight should fall, but they are not direct instructions to trade named holdings. Rebuilding should happen only after valuation resets, catalysts re-accelerate, and price structure stabilizes, not before.",
        PortfolioRating.SELL: "The current risk-reward is unfavorable enough that staying in the name does not offer a justified payoff for the downside being assumed. Execution should therefore prioritize exiting or staying out until both fundamentals and price structure show evidence of repair. Before that happens, attempts to buy the dip would amount to taking uncompensated risk rather than following a disciplined process.",
    }
    return mapping[rating]


def _default_trading_thesis(rating: PortfolioRating) -> str:
    if _is_chinese_output():
        mapping = {
            PortfolioRating.BUY: "当前上行逻辑更完整，适合在确认信号仍然有效的前提下逐步建立仓位。驱动这一判断的核心不是单一价格反弹，而是宏观压制边际缓和、行业盈利与供需线索同步改善，以及 ETF 持仓结构开始获得资金承接。换句话说，配置逻辑要先回答为什么现在值得把风险预算重新投向这只 ETF，再把具体加仓节奏交给执行计划去处理。",
            PortfolioRating.OVERWEIGHT: "当前多头逻辑仍占优，但应以控制节奏的方式增配而不是一次性放大仓位。支撑增配的关键在于主线产业或持仓盈利韧性仍在、市场结构没有转弱，且资金对核心持仓的承接尚未被破坏；真正需要防守的是估值上沿和催化兑现速度，而不是主线本身已经失效。因而本节应先说明为什么组合仍愿意把权重向这只 ETF 倾斜，而不是重复执行层面的加仓步骤。",
            PortfolioRating.HOLD: "当前多空因素并存，短期缺乏足够的赔率与胜率优势，更适合等待更清晰的确认信号。配置逻辑层面需要先说明：中期主线并未被证伪，但宏观估值约束、盈利质量验证和资金流确认还没有形成同向共振，因此没有必要在当前位置主动扩大风险暴露。也就是说，当前持有不是“没有观点”，而是在主线尚存、验证不足的情况下优先保留仓位弹性，把真正的动作阈值留给执行计划。",
            PortfolioRating.UNDERWEIGHT: "当前风险释放节奏快于新增催化兑现速度，更适合先降低敞口并等待更稳健的再介入条件。配置逻辑的重点是说明为什么这只 ETF 当前承受的估值天花板、盈利质量拐点或资金承接弱化，已经让持有成本高于继续等待的收益，而不仅仅是复述减仓动作本身。只有先把这一层“为什么该降权”的逻辑说透，后面的分步减仓和回补条件才有约束力。",
            PortfolioRating.SELL: "当前风险收益比明显失衡，应以退出仓位或回避参与为主，等待风险重新定价完成。这里需要先说明 ETF 的核心驱动已经从可承受波动演变为主线受损：宏观或产业压制仍在、盈利修复没有兑现、价格结构与资金承接也未出现有效修复。先把退出理由讲清楚，再把清仓与重评估条件留给执行层，才能避免逻辑与动作重复。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "The upside thesis is more complete right now, so the setup favors staged accumulation while confirmation remains intact. The core case should explain why macro pressure is easing, industry earnings or supply-demand signals are improving, and ETF structure or flows are starting to validate that repair instead of merely repeating the trade steps. In other words, this section should justify why risk budget belongs here now, while the execution plan handles how to deploy it.",
        PortfolioRating.OVERWEIGHT: "The bullish setup still has the edge, but exposure should be increased in a controlled way rather than all at once. The thesis needs to explain why the main industry and holdings evidence still supports a larger weight, while valuation ceilings and catalyst timing argue for pacing rather than aggression. That rationale should stay conceptually distinct from the execution plan, which is where the actual add rules belong.",
        PortfolioRating.HOLD: "Bullish and bearish factors are still balanced enough that the setup lacks a clear edge, so waiting is more appropriate. The thesis should explain that the medium-term story is not broken, but macro valuation pressure, earnings-quality confirmation, and flow validation are not yet aligned strongly enough to justify a bigger swing in exposure. That way the logic explains why holding is disciplined, while the execution plan can focus on the thresholds that would change the stance.",
        PortfolioRating.UNDERWEIGHT: "Risk is repricing faster than new upside catalysts are materializing, so trimming exposure is more appropriate. The thesis should make clear why valuation pressure, weakening earnings quality, or fading flow sponsorship now outweigh the benefit of maintaining full exposure, rather than simply restating that the position should be reduced. The actual trimming sequence and rebuild conditions belong in the execution section.",
        PortfolioRating.SELL: "The current risk-reward is unfavorable enough that exiting or staying out is the cleaner choice until repricing runs its course. The thesis should first explain why the core ETF driver is impaired across macro, industry, earnings, or structure, and why continued holding no longer earns the downside being taken. The execution section can then handle the mechanics of exit and re-entry review.",
    }
    return mapping[rating]


def _default_execution_plan(rating: PortfolioRating, context_text: str = "") -> str:
    if _is_chinese_output():
        primary_anchor = _primary_market_level_anchor(
            context_text,
            "首个关键位（优先是50日均线、布林中轨、前高突破位或前低回踩位的具体数值）",
        )
        support_anchor = _market_level_anchor_clause(
            context_text,
            "50日均线、布林中轨、前低或密集成交区",
        )
        mapping = {
            PortfolioRating.BUY: f"先以计划目标仓位的20%—30%建立试探仓，后续每一笔只增加10%—15%。只有当价格重新站回{primary_anchor}，且日成交量连续2个交易日达到近20日均量的1.2—1.3倍，同时 ETF 份额继续净申购或溢折价不再走阔，才继续加仓。若催化只是消息预期而未兑现为订单、业绩指引、份额扩张或放量突破，就暂停追价，等待回踩{primary_anchor}不破后再执行下一笔。",
            PortfolioRating.OVERWEIGHT: f"在保留现有底仓的前提下择机增配，但每一笔加仓都要绑定清晰的关键数据：价格至少守住{support_anchor}，日成交量回到近20日均量的1.1—1.2倍以上，且 ETF 份额、净申购或溢折价改善没有转弱。单笔增配宜控制在目标仓位的10%—15%，只有当新增催化从“预期”变成“可验证进展”并连续两个交易时段保持量价承接时，才继续上调；若量价配合不足或催化兑现延迟，就把超配部分压回到底仓。",
            PortfolioRating.HOLD: f"维持当前仓位，不主动追涨或杀跌。这里优先看的关键支撑直接写成{support_anchor}；只有当价格在该位置附近连续2个交易时段止跌企稳，日成交量至少较近5日均量放大15%—20%且明显回到20日均量附近，同时份额或资金流不再恶化，才考虑把持有转为试探性加仓。若新增催化只是消息层面的预期而未带来份额扩张、溢折价改善、资金流确认或放量突破，则继续维持仓位，不提前放大敞口。",
            PortfolioRating.UNDERWEIGHT: f"优先分2—3笔降低ETF整体敞口，每一笔先减掉目标仓位的10%—15%，不得把执行动作拆成对成分股的清仓或减持。若反弹连{support_anchor}都收不回，且日成交量仍低于近20日均量的0.9—1.0倍或 ETF 份额继续净赎回，就继续执行ETF层面的减仓；只有当价格重新收复主要均线、日成交量回到20日均量的1.1—1.2倍、份额转为连续净申购，才考虑小比例回补ETF仓位，而不是在缩量反弹里抢跑。",
            PortfolioRating.SELL: f"以退出仓位或避免入场为主，执行上不要等待模糊修复信号。若价格已跌破{support_anchor}，且单日放量达到近20日均量的1.3倍以上，或 ETF 溢折价继续恶化、份额净赎回扩大，就应直接完成清仓；即便后续出现技术性反弹，也要先看到基本面修复、价格重新站回关键均线、日成交量恢复到20日均量上方以及催化兑现三者同时出现，才考虑重新纳入观察名单。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "Start with only 20%-30% of the intended target size and keep later adds to 10%-15% increments. Add only after price reclaims the first concrete market level already named in the market report — ideally the actual 50-day average, Bollinger mid-band, prior breakout, or retest level — while daily volume holds at roughly 1.2x-1.3x the 20-day average for two sessions and ETF share creation or premium-discount behavior does not deteriorate. If the catalyst is still only narrative rather than verifiable progress, pause the build and wait for a successful retest of that level.",
        PortfolioRating.OVERWEIGHT: "Add selectively from the core position, but tie each add to explicit confirmation: price must hold the market report's main support or moving-average anchor, volume should recover to roughly 1.1x-1.2x the 20-day average, and ETF share or premium-discount signals should remain orderly. Keep each add controlled rather than one-shot, and if that confirmation fades, cut the pace and keep only the already-validated core exposure.",
        PortfolioRating.HOLD: "Maintain current exposure and avoid forcing new trades. Treat the key support zone as the concrete 50-day moving average, Bollinger mid-band, prior swing low, or repeated support area already cited in the market report; only reconsider adding if price stabilizes there for two trading sessions, volume improves by roughly 15%-20% versus the recent 5-day average and recovers toward the 20-day average, and ETF share or fund-flow conditions stop worsening. If the catalyst remains only a headline without share growth, premium-discount improvement, fund-flow confirmation, or breakout confirmation, keep the allocation unchanged.",
        PortfolioRating.UNDERWEIGHT: "Trim exposure in two or three steps, starting with the weakest-conviction slice and reducing roughly 10%-15% of target exposure per step. If rebounds fail to reclaim the market report's key averages or resistance levels while volume stays below roughly 0.9x-1.0x the 20-day average or ETF shares keep shrinking, continue trimming; only consider a small rebuild after price, volume, and ETF flow repair arrive together.",
        PortfolioRating.SELL: "Prioritize exiting or staying out without waiting for vague repair signals. If price has already broken the market report's core support or stop level on roughly 1.3x the 20-day average volume, or ETF share and premium-discount behavior keep worsening, complete the exit; only revisit the name after fundamentals, catalysts, and price structure all repair together.",
    }
    return mapping[rating]


def _default_risk_management(rating: PortfolioRating) -> str:
    if _is_chinese_output():
        mapping = {
            PortfolioRating.BUY: "把失效条件写清楚：若价格重新跌回关键支撑下方，且单日成交量放大到20日均量的1.3倍以上，说明承接失败，应立即暂停加仓并把仓位降回试探水平。同时持续跟踪催化兑现时点、业绩验证与行业相对强弱，避免在只有情绪而没有基本面确认时继续追价。",
            PortfolioRating.OVERWEIGHT: "在增配过程中把单一标的仓位上限、每次加仓比例和失效条件同步约束。若价格连续两天跌破关键支撑，或成交量恢复但股价仍无法突破前高，说明筹码承接不足，应停止加仓并回到核心底仓；若催化兑现不及预期，也要主动降低仓位节奏。",
            PortfolioRating.HOLD: "持续跟踪关键支撑/阻力、成交量、资金流与 ETF 结构信号，并把动作条件写明确：若价格有效跌破关键支撑且单日放量达到20日均量的1.3倍以上，先减掉20%—30%的试探仓位；若价格守住支撑并连续2个交易时段放量修复，同时份额变化和溢折价表现未恶化，再考虑恢复到原仓位。对“成交量改善”的判断不能只看单日放量，至少要结合5日均量、20日均量和价格是否同步收复关键位一起确认。",
            PortfolioRating.UNDERWEIGHT: "在减仓过程中重点看反弹强度、成交量结构和事件兑现进度，避免把缩量反弹误判为趋势修复。若价格反弹但成交量明显弱于20日均量，或催化仍停留在预期阶段，就维持减仓节奏；只有在量价和基本面同步改善时，才允许小比例回补。",
            PortfolioRating.SELL: "在退出或回避期间继续观察是否出现基本面修复与价格结构重建，但不要把短线反弹当作重新入场信号。只有当关键支撑重新站回、成交量恢复到20日均量以上、并且后续催化或业绩验证同步改善时，才考虑重新评估；否则保持空仓或极轻仓观察。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "Define the invalidation clearly: if price falls back below key support and daily volume expands beyond roughly 1.3x the 20-day average, treat that as a failed setup, stop adding, and cut exposure back to probe size. Keep tracking catalyst timing, earnings confirmation, and relative strength so momentum alone does not justify more risk.",
        PortfolioRating.OVERWEIGHT: "While adding, cap single-name exposure, define each add size, and keep explicit failure conditions. If price loses support for two sessions or volume returns without a clean breakout, stop adding and revert to the core position; if catalyst follow-through weakens, slow the sizing pace immediately.",
        PortfolioRating.HOLD: "Track support/resistance, volume, fund flows, and ETF structure with action thresholds attached: if price breaks key support on roughly 1.3x the 20-day average volume, trim 20%-30% of the probing risk; if price stabilizes and reclaims the level with improving volume for two sessions while share changes and premium-discount behavior remain orderly, restore the prior size. Do not call it volume improvement from one noisy session alone—confirm it against both the 5-day and 20-day averages and against price recovery.",
        PortfolioRating.UNDERWEIGHT: "As exposure is reduced, focus on rebound quality, volume structure, and catalyst follow-through so weak countertrend moves are not mistaken for a true repair. Only allow a small rebuild if price, volume, and fundamentals all improve together.",
        PortfolioRating.SELL: "While staying out, keep watching for real repair in fundamentals and price structure, but do not treat a short squeeze or reflex bounce as enough. Reconsider only after support is reclaimed, volume recovers above the 20-day average, and catalysts or guidance improve together.",
    }
    return mapping[rating]


def _default_snapshot_new_and_rebuttal(rating: PortfolioRating) -> str:
    if _is_chinese_output():
        mapping = {
            PortfolioRating.BUY: "本轮进一步强化了上行催化、盈利兑现与价格承接之间的对应关系，并回应了对估值与波动的主要质疑。",
            PortfolioRating.OVERWEIGHT: "本轮进一步强化了增配逻辑与风险边界之间的对应关系，并回应了对节奏与仓位控制的主要质疑。",
            PortfolioRating.HOLD: "本轮进一步明确了多空证据仍在拉锯，并回应了对过早加仓或过早减仓的主要质疑。",
            PortfolioRating.UNDERWEIGHT: "本轮进一步强化了风险释放节奏与估值约束之间的对应关系，并回应了对过度乐观假设的主要质疑。",
            PortfolioRating.SELL: "本轮进一步强化了退出逻辑与风险收益失衡之间的对应关系，并回应了对继续持仓的主要质疑。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "This round further linked upside catalysts, earnings follow-through, and price support, while addressing the main valuation and volatility objections.",
        PortfolioRating.OVERWEIGHT: "This round clarified why the add-on setup still works within defined risk boundaries and addressed the main pacing objections.",
        PortfolioRating.HOLD: "This round reinforced that the evidence remains mixed and addressed the main objections to changing exposure too early.",
        PortfolioRating.UNDERWEIGHT: "This round clarified the interaction between risk-release cadence and valuation pressure, while addressing the main overly bullish assumptions.",
        PortfolioRating.SELL: "This round reinforced the exit case by linking downside risks to the deteriorating risk-reward profile and addressing the main hold-the-line objections.",
    }
    return mapping[rating]


def _default_snapshot_to_verify(rating: PortfolioRating) -> str:
    if _is_chinese_output():
        mapping = {
            PortfolioRating.BUY: "继续跟踪关键催化、成交量与盈利兑现是否同步验证当前建仓逻辑。",
            PortfolioRating.OVERWEIGHT: "继续跟踪催化兑现、估值消化与价格结构，确认增配逻辑是否继续成立。",
            PortfolioRating.HOLD: "继续跟踪关键支撑/阻力、成交量与后续业绩验证，确认是否出现足以调整仓位的新信号。",
            PortfolioRating.UNDERWEIGHT: "继续跟踪风险释放节奏、关键支撑与估值回落情况，确认是否仍需维持偏谨慎仓位。",
            PortfolioRating.SELL: "继续跟踪基本面修复与价格结构重建信号，确认是否具备重新评估入场的条件。",
        }
        return mapping[rating]
    mapping = {
        PortfolioRating.BUY: "Keep tracking catalysts, volume, and earnings follow-through to confirm that staged accumulation still makes sense.",
        PortfolioRating.OVERWEIGHT: "Keep tracking catalyst delivery, valuation digestion, and price structure to confirm that the add-on case still holds.",
        PortfolioRating.HOLD: "Keep tracking support/resistance, volume, and earnings follow-through to see whether a clearer exposure signal emerges.",
        PortfolioRating.UNDERWEIGHT: "Keep tracking risk-release cadence, key support levels, and valuation reset progress to confirm whether caution is still warranted.",
        PortfolioRating.SELL: "Keep tracking fundamental repair and price stabilization before reconsidering whether re-entry conditions exist.",
    }
    return mapping[rating]


def _sanitize_section(
    text: str,
    default_text: str,
    rating: PortfolioRating,
    *,
    check_action_conflict: bool = False,
    require_detail: bool = False,
    strip_headings: tuple[str, ...] = (),
) -> str:
    content = strip_manager_instruction_leakage(
        _strip_leading_section_headings((text or "").strip(), strip_headings)
    )
    if not content or _is_placeholder_like(content):
        return default_text
    # Strip embedded recommendation labels (line-level and sentence-level)
    lines = []
    for line in re.split(r"\n+", content):
        if _contains_explicit_rating_marker(line) and _is_recommendation_only_segment(line):
            continue
        # Also strip recommendation-only sentences within a line
        kept_sentences = [
            s for s in _split_sentences(line)
            if not (_contains_explicit_rating_marker(s) and _is_recommendation_only_segment(s))
        ]
        joined = "".join(kept_sentences).strip()
        if joined:
            lines.append(joined)
    content = "\n".join(lines).strip()
    content = _strip_recommendation_restating_sentences(content)
    if not content or _is_placeholder_like(content):
        return default_text
    if check_action_conflict and _has_conflicting_primary_action(content, rating):
        return default_text
    if require_detail and _section_needs_detail(content):
        return _merge_sparse_section_with_default(content, default_text)
    return content


def _section_needs_detail(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return True
    compact = _compact_text(content)
    sentence_count = len(re.findall(r"[。！？!?\.]+", content))
    if _is_chinese_output():
        return len(compact) < 55 or sentence_count < 2
    word_count = len(re.findall(r"\b\w+\b", content))
    return word_count < 18 or sentence_count < 2


def _merge_sparse_section_with_default(content: str, default_text: str) -> str:
    stripped = (content or "").strip()
    if not stripped:
        return default_text
    if _compact_text(stripped) == _compact_text(default_text):
        return default_text
    if _is_chinese_output():
        joiner = "" if stripped.endswith(("。", "！", "？")) else "。"
        return f"{stripped}{joiner}{default_text}"
    joiner = "" if stripped.endswith((".", "!", "?")) else "."
    return f"{stripped}{joiner} {default_text}"


def _split_sentences(text: str) -> list[str]:
    content = (text or "").strip()
    if not content:
        return []
    return [
        segment.strip()
        for segment in re.split(r"(?:\n+|(?<=[。！？!?])\s*)", content)
        if segment.strip()
    ]


def _has_numbered_blocks(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*(?:\d+[.．、)]|[一二三四五六七八九十]+、)\s*\S", text or ""))


_TRADER_BUCKET_ORDER = {"initial": 0, "add": 1, "reduce": 2, "monitor": 3}
_TRADER_NEGATION_PREFIX = r"(?:不|未|无|勿|别|避免|不要|不能|无需|暂不)"


def _has_unnegated_keyword(content: str, keyword_pattern: str) -> bool:
    text = content or ""
    if not re.search(keyword_pattern, text):
        return False
    negated_pattern = re.compile(rf"{_TRADER_NEGATION_PREFIX}\s*(?:再|去|做)?\s*(?:{keyword_pattern})")
    return not negated_pattern.search(text)


def _trader_block_key(sentence: str) -> str:
    content = sentence or ""
    if _has_unnegated_keyword(content, r"减仓|减持|降低|退出|止损|清仓|失守|跌破|破位|转弱|回撤"):
        return "reduce"
    if _has_unnegated_keyword(content, r"加仓|增配|上调|回补|提高|扩大|买入"):
        return "add"
    if _has_unnegated_keyword(content, r"跟踪|监控|复核|观察|验证|再平衡|确认|关注"):
        return "monitor"
    return "initial"


def _trader_block_label(key: str, section_kind: str) -> str:
    if section_kind == "risk":
        labels = {
            "initial": "风险预算与仓位边界",
            "add": "回补与恢复条件",
            "reduce": "减仓触发的核心条件",
            "monitor": "监控优先级",
        }
    else:
        labels = {
            "initial": "初始仓位与执行节奏",
            "add": "加仓触发条件",
            "reduce": "减仓触发的核心条件",
            "monitor": "跟踪验证与再平衡",
        }
    return labels.get(key, "执行要点")


def _format_trader_numbered_blocks(text: str, section_kind: str = "execution") -> str:
    content = (text or "").strip()
    if not content or not _is_chinese_output() or _has_numbered_blocks(content):
        return content

    sentences = _split_sentences(content)
    compact = _compact_text(content)
    if len(sentences) < 3 and len(compact) < 180:
        return content

    buckets: list[tuple[str, list[str]]] = []
    index_by_key: dict[str, int] = {}
    for sentence in sentences:
        key = _trader_block_key(sentence)
        if key not in index_by_key:
            index_by_key[key] = len(buckets)
            buckets.append((key, []))
        buckets[index_by_key[key]][1].append(sentence)

    if len(buckets) < 2:
        return content

    buckets.sort(key=lambda bucket: _TRADER_BUCKET_ORDER.get(bucket[0], 99))

    blocks = []
    for index, (key, grouped_sentences) in enumerate(buckets, start=1):
        blocks.append(
            f"{index}. {_trader_block_label(key, section_kind)}\n"
            + "".join(grouped_sentences)
        )
    return "\n\n".join(blocks).strip()


def _sentence_similarity(left: str, right: str) -> float:
    left_key = _compact_text(left)
    right_key = _compact_text(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    min_len = min(len(left_key), len(right_key))
    max_len = max(len(left_key), len(right_key))
    if max_len > 0 and min_len / max_len < 0.4:
        return 0.0
    if min_len >= 12 and (
        left_key in right_key or right_key in left_key
    ):
        return 0.9
    return SequenceMatcher(None, left_key, right_key).ratio()


def _remove_overlapping_sentences(text: str, reference: str) -> str:
    reference_sentences = _split_sentences(reference)
    if not reference_sentences:
        return (text or "").strip()

    kept = []
    for sentence in _split_sentences(text):
        if any(_sentence_similarity(sentence, ref) >= 0.72 for ref in reference_sentences):
            continue
        kept.append(sentence)
    return "\n".join(kept).strip()


def _strip_numbered_heading_prefix(text: str) -> str:
    return re.sub(
        r"^\s*(?:#{1,6}\s*)?(?:[一二三四五六七八九十]+|[1-9]\d*)\s*[、.．)）:：\-]\s*",
        "",
        (text or "").strip(),
    )


def _split_trader_heading_and_body(text: str) -> tuple[str, str]:
    content = (text or "").strip()
    if not content:
        return "", ""
    if not _is_chinese_output():
        return "", content
    sentences = _split_sentences(content)
    if not sentences:
        return "", content
    first_sentence = _strip_numbered_heading_prefix(sentences[0]).strip()
    heading = first_sentence.rstrip("。！？!?；;：:")
    body = "\n".join(sentences[1:]).strip()
    if not body and len(_compact_text(heading)) > 16:
        return "配置逻辑", first_sentence
    if len(_compact_text(heading)) > 24:
        overflow = heading[24:].lstrip("，、；：: ")
        heading = heading[:24].rstrip("，、；：: ")
        body_parts = []
        if overflow:
            body_parts.append(f"{overflow}。")
        if body:
            body_parts.append(body)
        body = "\n".join(part for part in body_parts if part).strip()
    return heading or "配置逻辑", body


def _trader_thesis_needs_detail(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return True
    compact = _compact_text(content)
    sentence_count = len(_split_sentences(content))
    if _is_chinese_output():
        return len(compact) < 85 or sentence_count < 3
    word_count = len(re.findall(r"\b\w+\b", content))
    return word_count < 30 or sentence_count < 3


_MARKET_LEVEL_LABEL_PATTERN = (
    r"(?:50日均线|20日均线|10日均线|200日均线|布林中轨|布林上轨|布林下轨|"
    r"布林带中轨|布林带上轨|布林带下轨|前高突破位|前低回踩位|前低|前高|"
    r"主支撑位|主支撑|主阻力位|主阻力|支撑位|阻力位|支撑带|阻力带|"
    r"密集成交区|上一压力位|压力位|止损位|"
    r"50-day(?:\s+(?:moving average|SMA))?|20-day(?:\s+(?:moving average|SMA))?|"
    r"10-day(?:\s+(?:moving average|SMA))?|200-day(?:\s+(?:moving average|SMA))?|"
    r"Bollinger mid-band|Bollinger middle band|Bollinger upper band|Bollinger lower band|"
    r"prior breakout level|prior retest level|swing low|swing high|support(?: zone)?|"
    r"resistance(?: zone)?|stop(?:-loss)? level|VWMA|ATR|NAV|SMA|EMA)"
)
_MARKET_LEVEL_VALUE_PATTERN = (
    r"\d+(?:\.\d+)?(?:\s*[-—~至to]+\s*\d+(?:\.\d+)?)?\s*(?:元|美元|港元|点|bp|bps|USD|HKD|pts?|points?)?"
)
_MARKET_LEVEL_PATTERNS = (
    re.compile(
        rf"({_MARKET_LEVEL_LABEL_PATTERN})(?:位于|在|约|为|处于|落在|落于|对应|回踩至|上移至|下移至|看至|约在|：|:)?\s*({_MARKET_LEVEL_VALUE_PATTERN})"
    ),
    re.compile(
        rf"({_MARKET_LEVEL_VALUE_PATTERN})(?:的)?\s*({_MARKET_LEVEL_LABEL_PATTERN})"
    ),
)


def _extract_market_level_anchors(text: str, limit: int = 3) -> list[str]:
    content = (text or "").strip()
    if not content or limit <= 0:
        return []

    anchors: list[str] = []
    seen: set[str] = set()
    for pattern in _MARKET_LEVEL_PATTERNS:
        for match in pattern.finditer(content):
            left, right = match.group(1).strip(), match.group(2).strip()
            if re.fullmatch(_MARKET_LEVEL_LABEL_PATTERN, left):
                separator = "" if re.search(r"[\u4e00-\u9fff]", left) else " "
                anchor = f"{left}{separator}{right}".strip()
            else:
                separator = "的" if re.search(r"[\u4e00-\u9fff]", right) else " "
                anchor = f"{left}{separator}{right}".strip()
            normalized = _compact_text(anchor)
            if not normalized or normalized in seen:
                continue
            anchors.append(anchor)
            seen.add(normalized)
            if len(anchors) >= limit:
                return anchors
    return anchors


def _market_level_priority(anchor: str) -> int:
    normalized = (anchor or "").lower()
    priorities = (
        ("50日均线", 0),
        ("50-day", 0),
        ("布林中轨", 1),
        ("布林带中轨", 1),
        ("bollinger mid-band", 1),
        ("bollinger middle band", 1),
        ("前高突破位", 2),
        ("prior breakout level", 2),
        ("前低回踩位", 3),
        ("prior retest level", 3),
        ("前低", 4),
        ("swing low", 4),
        ("前高", 5),
        ("swing high", 5),
        ("支撑", 6),
        ("support", 6),
        ("阻力", 7),
        ("resistance", 7),
        ("20日均线", 8),
        ("20-day", 8),
        ("10日均线", 9),
        ("10-day", 9),
        ("200日均线", 10),
        ("200-day", 10),
    )
    for token, priority in priorities:
        if token in normalized:
            return priority
    return 99


def _prioritize_market_level_anchors(anchors: list[str], limit: int) -> list[str]:
    ranked = sorted(
        enumerate(anchors),
        key=lambda item: (_market_level_priority(item[1]), item[0]),
    )
    return [anchor for _, anchor in ranked[:limit]]


def _primary_market_level_anchor(context_text: str, fallback: str) -> str:
    anchors = _prioritize_market_level_anchors(
        _extract_market_level_anchors(context_text, limit=6),
        1,
    )
    return anchors[0] if anchors else fallback


def _market_level_anchor_clause(context_text: str, fallback: str, *, limit: int = 2) -> str:
    anchors = _prioritize_market_level_anchors(
        _extract_market_level_anchors(context_text, limit=6),
        limit,
    )
    if not anchors:
        return fallback
    if len(anchors) == 1:
        return anchors[0]
    return "或".join(anchors)


def _extract_market_level_anchor_map(context_text: str) -> dict[str, str]:
    anchor_map: dict[str, str] = {}
    for anchor in _prioritize_market_level_anchors(
        _extract_market_level_anchors(context_text, limit=8),
        8,
    ):
        match = re.search(_MARKET_LEVEL_LABEL_PATTERN, anchor, re.IGNORECASE)
        if not match:
            continue
        label = match.group(0)
        anchor_map.setdefault(label, anchor)
    return anchor_map


def _inline_contextual_market_levels(text: str, context_text: str) -> str:
    content = (text or "").strip()
    if not content or not context_text or not _is_chinese_output():
        return content

    primary_anchor = _primary_market_level_anchor(context_text, "")
    support_anchor = _market_level_anchor_clause(context_text, "", limit=2)
    if primary_anchor:
        content = content.replace("市场分析中给出的首个关键阻力/支撑转换位", primary_anchor)
        content = content.replace("市场报告已经写明的首个关键位", primary_anchor)
    if support_anchor:
        content = content.replace("市场报告中的主支撑位或50日均线", support_anchor)
        content = content.replace("主支撑位或50日均线", support_anchor)

    for label, anchor in _extract_market_level_anchor_map(context_text).items():
        content = re.sub(rf"{re.escape(label)}(?!\s*\d)", anchor, content)
    return content


def _has_market_level_anchor(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    return bool(_extract_market_level_anchors(stripped, limit=1))


def _has_volume_or_flow_threshold(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    patterns = (
        r"(?:成交量|成交额|量能|5日均量|20日均量|日均量|净流入|净流出|净申购|净赎回|份额|溢折价|跟踪误差|volume|turnover|fund flow|share change|share creation|premium-discount|tracking error)[^。\n]{0,32}\d+(?:\.\d+)?\s*(?:%|％|倍|x|亿元|亿|万份|亿份|bp|bps|天|日)",
        r"\d+(?:\.\d+)?\s*(?:%|％|倍|x|亿元|亿|万份|亿份|bp|bps|天|日)[^。\n]{0,32}(?:成交量|成交额|量能|5日均量|20日均量|日均量|净流入|净流出|净申购|净赎回|份额|溢折价|跟踪误差|volume|turnover|fund flow|share change|share creation|premium-discount|tracking error)",
    )
    return any(re.search(pattern, stripped, re.IGNORECASE) for pattern in patterns)


def _missing_execution_thresholds(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    has_any_numeric_threshold = bool(
        re.search(
            r"\d+(?:\.\d+)?(?:%|％|倍|元|美元|港元|日|天|周|月|SMA|EMA|ATR|VWMA|均线|布林|bp|bps|x)",
            stripped,
            re.IGNORECASE,
        )
    )
    return not (
        has_any_numeric_threshold
        and _has_market_level_anchor(stripped)
        and _has_volume_or_flow_threshold(stripped)
    )


def _sanitize_snapshot_stance(stance: str, rating: PortfolioRating) -> str:
    expected = _expected_rating_text(rating)
    content = (stance or "").strip()
    if not content:
        return expected
    if _is_chinese_output():
        detected = detect_chinese_rating(content)
    else:
        detected = detect_english_rating(content)
    if _contains_any_rating_term(content) and detected != expected:
        return expected
    return content


def _sanitize_trader_thesis(
    text: str,
    execution_plan: str,
    rating: PortfolioRating,
    strip_headings: tuple[str, ...],
) -> str:
    content = strip_manager_instruction_leakage(
        _strip_leading_section_headings((text or "").strip(), strip_headings)
    )
    default_text = _default_trading_thesis(rating)
    if not content or _is_placeholder_like(content):
        return default_text
    if _has_conflicting_primary_action(content, rating):
        return default_text

    deduped = _remove_overlapping_sentences(content, execution_plan)
    if not deduped:
        return default_text
    if _has_conflicting_primary_action(deduped, rating):
        return default_text
    if _trader_thesis_needs_detail(deduped):
        return _merge_sparse_section_with_default(deduped, default_text)
    return deduped


def _sanitize_trader_risk_management(
    text: str,
    thesis: str,
    execution_plan: str,
    rating: PortfolioRating,
    strip_headings: tuple[str, ...],
) -> str:
    content = strip_manager_instruction_leakage(
        _strip_leading_section_headings((text or "").strip(), strip_headings)
    )
    default_text = _default_risk_management(rating)
    if not content or _is_placeholder_like(content):
        return default_text

    deduped = _remove_overlapping_sentences(
        content,
        "\n".join(part for part in (thesis, execution_plan) if part),
    )
    if not deduped:
        return default_text
    if _section_needs_detail(deduped):
        return _merge_sparse_section_with_default(deduped, default_text)
    return deduped


def render_research_plan(plan: ResearchPlan) -> str:
    recommendation = localize_rating_term(plan.rating.value)
    debate_conclusion = _sanitize_section(
        plan.debate_conclusion,
        _default_debate_conclusion(plan.rating),
        plan.rating,
        require_detail=True,
    )
    action_logic = _sanitize_section(
        plan.action_logic,
        _default_action_logic(plan.rating),
        plan.rating,
        check_action_conflict=True,
        require_detail=True,
    )
    positioning_recommendation = _sanitize_positioning_recommendation(
        plan.positioning_recommendation, plan.rating
    )
    positioning_recommendation = strip_constituent_trade_instructions(
        positioning_recommendation
    )
    detailed_positioning = _default_research_positioning_guidance(plan.rating)
    if _compact_text(positioning_recommendation) == _compact_text(
        _default_positioning_guidance(plan.rating)
    ):
        positioning_recommendation = detailed_positioning
    elif _section_needs_detail(positioning_recommendation):
        positioning_recommendation = _merge_sparse_section_with_default(
            positioning_recommendation, detailed_positioning
        )
    positioning_recommendation = format_chinese_positioning_recommendation(
        positioning_recommendation
    )
    if _is_chinese_output():
        body = (
            "## 辩论结论\n"
            f"{debate_conclusion}\n\n"
            "## 行为逻辑\n"
            f"{action_logic}\n\n"
            "## 持仓建议\n"
            "### （一）评级\n"
            f"研究结论: **{recommendation}**\n"
            "### （二）建议\n"
            f"{positioning_recommendation}"
        )
    else:
        body = (
            f"## {localize_label('Debate Conclusion', '辩论结论')}\n"
            f"{debate_conclusion}\n\n"
            f"## {localize_label('Action Logic', '行为逻辑')}\n"
            f"{action_logic}\n\n"
            f"## {localize_label('Positioning Recommendation', '持仓建议')}\n"
            f"{localize_label('Research View', '研究结论')}: **{recommendation}**\n"
            f"{positioning_recommendation}"
        )
    snapshot = _render_snapshot(
        _sanitize_snapshot_stance(plan.snapshot_stance, plan.rating),
        _sanitize_section(
            plan.snapshot_new_and_rebuttal,
            _default_snapshot_new_and_rebuttal(plan.rating),
            plan.rating,
        ),
        _sanitize_section(
            plan.snapshot_to_verify,
            _default_snapshot_to_verify(plan.rating),
            plan.rating,
        ),
    )
    return collapse_blank_lines(f"{body}\n\n{snapshot}")


def render_trader_proposal(plan: TraderProposal, context_text: str = "") -> str:
    heading_aliases = (
        "ETF配置逻辑",
        "配置核心逻辑",
        "配置执行计划",
        "交易执行计划",
        "再平衡与风险控制",
        "调仓与风控机制",
        "ETF Allocation Thesis",
        "Allocation Core Logic",
        "Allocation Execution Plan",
        "Trading Execution Plan",
        "Rebalance and Risk Controls",
        "Rebalance and Risk Control",
    )
    recommendation = localize_rating_term(plan.rating.value)
    default_execution_plan = _default_execution_plan(plan.rating, context_text)
    execution_plan = _sanitize_section(
        plan.execution_plan,
        default_execution_plan,
        plan.rating,
        check_action_conflict=True,
        require_detail=True,
        strip_headings=heading_aliases,
    )
    execution_plan = _inline_contextual_market_levels(execution_plan, context_text)
    execution_plan = strip_constituent_trade_instructions(execution_plan)
    if _missing_execution_thresholds(execution_plan) and _compact_text(default_execution_plan) not in _compact_text(execution_plan):
        execution_plan = _merge_sparse_section_with_default(
            execution_plan,
            default_execution_plan,
        )
        execution_plan = _inline_contextual_market_levels(execution_plan, context_text)
        execution_plan = strip_constituent_trade_instructions(execution_plan)
    thesis = _sanitize_trader_thesis(
        plan.thesis,
        execution_plan,
        plan.rating,
        heading_aliases,
    )
    risk_management = _sanitize_trader_risk_management(
        plan.risk_management,
        thesis,
        execution_plan,
        plan.rating,
        heading_aliases,
    )
    risk_management = strip_constituent_trade_instructions(risk_management)
    if _is_chinese_output():
        thesis_heading, thesis_body = _split_trader_heading_and_body(thesis)
        execution_plan = _format_trader_numbered_blocks(execution_plan, "execution")
        risk_management = _format_trader_numbered_blocks(risk_management, "risk")
        thesis_section = (
            f"一、{thesis_heading}\n"
            f"{thesis_body.strip()}\n\n"
            if thesis_body.strip()
            else f"一、{thesis_heading}\n\n"
        )
        return collapse_blank_lines(
            f"{thesis_section}"
            "二、配置执行计划\n"
            f"{execution_plan}\n\n"
            "三、再平衡与风险控制\n"
            f"{risk_management}\n\n"
            "四、执行倾向\n"
            f"执行倾向: **{recommendation}**"
        )
    return collapse_blank_lines(
        "## ETF Allocation Thesis\n"
        f"{thesis}\n\n"
        "## Allocation Execution Plan\n"
        f"{execution_plan}\n\n"
        "## Rebalance and Risk Controls\n"
        f"{risk_management}\n\n"
        f"EXECUTION BIAS: **{recommendation.upper()}**"
    )


def render_portfolio_decision(plan: PortfolioDecision, context_text: str = "") -> str:
    recommendation = localize_rating_term(plan.rating.value)
    debate_conclusion = _strip_recommendation_restating_sentences(_normalize_portfolio_chinese_phrasing(_sanitize_section(
        plan.debate_conclusion,
        _default_debate_conclusion(plan.rating),
        plan.rating,
        require_detail=True,
    )))
    action_logic = _strip_recommendation_restating_sentences(_normalize_portfolio_chinese_phrasing(_sanitize_section(
        plan.action_logic,
        _default_action_logic(plan.rating),
        plan.rating,
        check_action_conflict=True,
        require_detail=True,
    )))
    positioning_recommendation = _sanitize_positioning_recommendation(
        plan.positioning_recommendation, plan.rating
    )
    positioning_recommendation = strip_constituent_trade_instructions(
        positioning_recommendation
    )
    detailed_positioning = _default_research_positioning_guidance(plan.rating, context_text)
    if _compact_text(positioning_recommendation) == _compact_text(
        _default_positioning_guidance(plan.rating)
    ) or _compact_text(positioning_recommendation) == _compact_text(
        _default_positioning_guidance(plan.rating, context_text)
    ):
        positioning_recommendation = detailed_positioning
    elif (
        _section_needs_detail(positioning_recommendation)
        or _missing_execution_thresholds(positioning_recommendation)
    ) and _compact_text(detailed_positioning) not in _compact_text(positioning_recommendation):
        positioning_recommendation = _merge_sparse_section_with_default(
            positioning_recommendation, detailed_positioning
        )
    positioning_recommendation = _inline_contextual_market_levels(
        positioning_recommendation,
        context_text,
    )
    positioning_recommendation = format_chinese_positioning_recommendation(
        positioning_recommendation
    )
    if _is_chinese_output():
        final_line = f"研究结论: **{recommendation}**"
    else:
        final_line = f"FINAL ALLOCATION PROPOSAL: **{recommendation.upper()}**"

    if _is_chinese_output():
        body = (
            "## 辩论结论\n"
            f"{debate_conclusion}\n\n"
            "## 行为逻辑\n"
            f"{action_logic}\n\n"
            "## 持仓建议\n"
            "### （一）评级\n"
            f"{final_line}\n"
            "### （二）建议\n"
            f"{positioning_recommendation}"
        )
    else:
        body = (
            f"## {localize_label('Debate Conclusion', '辩论结论')}\n"
            f"{debate_conclusion}\n\n"
            f"## {localize_label('Action Logic', '行为逻辑')}\n"
            f"{action_logic}\n\n"
            f"## {localize_label('Positioning Recommendation', '持仓建议')}\n"
            f"{final_line}\n"
            f"{positioning_recommendation}"
        )
    snapshot = _render_snapshot(
        _sanitize_snapshot_stance(plan.snapshot_stance, plan.rating),
        _sanitize_section(
            plan.snapshot_new_and_rebuttal,
            _default_snapshot_new_and_rebuttal(plan.rating),
            plan.rating,
        ),
        _sanitize_section(
            plan.snapshot_to_verify,
            _default_snapshot_to_verify(plan.rating),
            plan.rating,
        ),
    )
    return collapse_blank_lines(f"{body}\n\n{snapshot}")
