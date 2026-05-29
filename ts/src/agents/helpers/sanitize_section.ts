/**
 * Sanitize-section family — port of ``etfagents.agents.schemas`` sanitizers.
 *
 * When LLM output is empty, sparse, placeholder-like, or contains conflicting
 * action verbs, these functions fall back to rating-specific default text or
 * merge defaults into sparse content.
 *
 * Sub-step 2.5c-2 ports:
 *   - compactText / splitSentences / isPlaceholderLike / sectionNeedsDetail
 *   - containsExplicitRatingMarker / isRecommendationOnlySegment /
 *     isRecommendationRestatingSentence / stripRecommendationRestatingSentences
 *   - hasConflictingPrimaryAction
 *   - sentenceSimilarity / removeOverlappingSentences (LCS-based, no deps)
 *   - All default-text generators (bilingual, 5 ratings × 2 languages)
 *   - stripLeadingSectionHeadings
 *   - stripManagerInstructionLeakage (focused subset)
 *   - sanitizeSection / mergeSparseSectionWithDefault /
 *     sanitizeTraderThesis / sanitizeTraderRiskManagement /
 *     missingExecutionThresholds
 */

import type { PortfolioRating } from "../schemas/rating.js";
import { isChinese } from "../schemas/rating.js";
import { anchorClause, primaryAnchor } from "./market_levels.js";

// ---------------------------------------------------------------------------
// Layer 1 — Utilities
// ---------------------------------------------------------------------------

const COMPACT_STRIP_RE = /[\s:：,，。.!！？;；/\-—_()（）]+/g;

export function compactText(text: string | undefined): string {
  return (text ?? "").replace(COMPACT_STRIP_RE, "").trim().toLowerCase();
}

const SENTENCE_SPLIT_RE = /(\n|[。！？!?.])/;

export function splitSentences(text: string | undefined): string[] {
  const content = (text ?? "").trim();
  if (!content) return [];
  // Split on sentence-ending punctuation (preserved via capturing group) or newlines.
  // Then re-join punctuation with its preceding text fragment.
  const parts = content.split(SENTENCE_SPLIT_RE);
  const sentences: string[] = [];
  for (let i = 0; i < parts.length; i++) {
    const frag = parts[i]?.trim();
    if (!frag) continue;
    if (/^[。！？!?.]$/.test(frag) || frag === "\n") {
      // Attach punctuation to the previous sentence
      if (sentences.length > 0) {
        sentences[sentences.length - 1] += frag;
      }
    } else {
      sentences.push(frag);
    }
  }
  return sentences.map((s) => s.trim()).filter(Boolean);
}

const PLACEHOLDER_EXACT = new Set([
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
]);

const PLACEHOLDER_PATTERNS: ReadonlyArray<RegExp> = [
  /评估.*论证.*强度.*总结.*核心论点.*致命弱点/,
  /估值.*催化节奏.*下行边界.*确认.*证伪信号/,
  /明确评级.*执行指引/,
  /balanced.*bull.*bear.*cases/i,
  /evidence.*action.*logic.*valuation.*catalysts/i,
  /actionable.*guidance.*execution.*details/i,
  /synthesis.*risk.*debate/i,
  /portfolio.*logic.*evidence.*execution/i,
  /concrete.*execution.*entry.*reduce.*exit/i,
  /risk.*controls.*monitoring.*items/i,
];

export function isPlaceholderLike(text: string | undefined): boolean {
  const compacted = compactText(text);
  if (!compacted) return false;
  if (PLACEHOLDER_EXACT.has(compacted)) return true;
  return PLACEHOLDER_PATTERNS.some((re) => re.test(compacted));
}

export function sectionNeedsDetail(text: string | undefined, language: string): boolean {
  const content = (text ?? "").trim();
  if (!content) return true;
  if (isChinese(language)) {
    const compacted = compactText(content);
    if (compacted.length < 55) return true;
    const sentenceCount = content.match(/[。！？!?.]+/g)?.length ?? 0;
    return sentenceCount < 2;
  }
  const wordCount = content.match(/\b\w+\b/g)?.length ?? 0;
  if (wordCount < 18) return true;
  const sentenceCount = content.match(/[.!?]+/g)?.length ?? 0;
  return sentenceCount < 2;
}

// ---------------------------------------------------------------------------
// Layer 2 — Rating-marker detection
// ---------------------------------------------------------------------------

const CHINESE_RATING_MARKERS = [
  "建议评级",
  "评级",
  "配置评级",
  "研究结论",
  "执行倾向",
  "最终配置建议",
  "最终交易建议",
  "建议买入",
  "建议增持",
  "建议持有",
  "建议减持",
  "建议卖出",
  "维持买入",
  "维持增持",
  "维持持有",
  "维持减持",
  "维持卖出",
  "采取买入策略",
  "采取增持策略",
  "采取持有策略",
  "采取减持策略",
  "采取卖出策略",
];

const ENGLISH_RATING_MARKERS = [
  "RECOMMENDATION:",
  "RATING:",
  "FINAL ALLOCATION PROPOSAL:",
  "FINAL TRANSACTION PROPOSAL:",
  "RECOMMEND BUY",
  "RECOMMEND OVERWEIGHT",
  "RECOMMEND HOLD",
  "RECOMMEND UNDERWEIGHT",
  "RECOMMEND SELL",
  "MAINTAIN BUY",
  "MAINTAIN OVERWEIGHT",
  "MAINTAIN HOLD",
  "MAINTAIN UNDERWEIGHT",
  "MAINTAIN SELL",
];

export function containsExplicitRatingMarker(line: string, language: string): boolean {
  if (isChinese(language)) {
    return CHINESE_RATING_MARKERS.some((m) => line.includes(m));
  }
  const upper = line.toUpperCase();
  return ENGLISH_RATING_MARKERS.some((m) => upper.includes(m));
}

const CHINESE_RECOMMENDATION_ONLY_PATTERNS: ReadonlyArray<RegExp> = [
  /^(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)[:：].+$/,
  /^(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)(?:为)?(?:买入|增持|持有|减持|卖出)[。！!]*$/,
  /^针对[^，。,；;]+[，,]?(?:建议|应|宜)(?:采取)?(?:买入|增持|持有|减持|卖出)(?:策略)?[。！!]*$/,
  /^(?:建议|维持|转为)(?:买入|增持|持有|减持|卖出)(?:策略)?[。！!]*$/,
  /^建议采取(?:买入|增持|持有|减持|卖出)策略[。！!]*$/,
];

const ENGLISH_RECOMMENDATION_ONLY_PATTERNS: ReadonlyArray<RegExp> = [
  /^(?:RECOMMENDATION|RATING|FINALALLOCATIONPROPOSAL|FINALTRANSACTIONPROPOSAL)[:：]?.+$/,
  /^(?:RECOMMEND|MAINTAIN|SHIFTTO|MOVETO)(?:BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL)[.!]*$/,
  /^FOR[A-Z0-9._-]+,?(?:RECOMMEND|MAINTAIN)(?:BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL)[.!]*$/,
];

export function isRecommendationOnlySegment(line: string, language: string): boolean {
  const compacted = compactText(line);
  if (!compacted) return false;
  const normalized = isChinese(language) ? compacted : compacted.toUpperCase();
  const patterns = isChinese(language)
    ? CHINESE_RECOMMENDATION_ONLY_PATTERNS
    : ENGLISH_RECOMMENDATION_ONLY_PATTERNS;
  return patterns.some((re) => re.test(normalized));
}

const CHINESE_RESTATING_RE =
  /^(?:综合[^。！？!?]{0,40}证据[，,])?(?:(?:本组合|组合层面|当前组合|本次配置|对(?:该ETF|[A-Z0-9.-]+)|对于(?:该ETF|[A-Z0-9.-]+))[^。！？!?]{0,24})?(?:明确)?(?:建议|判断|结论|评级|配置建议)(?:为|是)?\s*\**(?:买入|增持|持有|减持|卖出)\**[。！!？?]*$/;

const ENGLISH_RESTATING_RE =
  /^(?:based on [^.?!]{0,60},\s*)?(?:(?:for|on)\s+[A-Z0-9.-]+[^.?!]{0,24})?(?:the )?(?:clear )?(?:recommendation|view|stance|allocation recommendation|decision)\s*(?:is|remains)?\s*\**(?:buy|overweight|hold|underweight|sell)\**[.!?]*$/i;

export function isRecommendationRestatingSentence(sentence: string, language: string): boolean {
  const content = (sentence ?? "").trim();
  if (!content) return false;
  if (isChinese(language)) return CHINESE_RESTATING_RE.test(content);
  return ENGLISH_RESTATING_RE.test(content);
}

export function stripRecommendationRestatingSentences(
  text: string | undefined,
  language: string,
): string {
  const content = (text ?? "").trim();
  if (!content) return "";
  return splitSentences(content)
    .filter((s) => !isRecommendationRestatingSentence(s, language))
    .join("\n")
    .trim();
}

// ---------------------------------------------------------------------------
// Layer 3 — Conflict detection
// ---------------------------------------------------------------------------

const CHINESE_BULLISH_RE = /买入|建仓|加仓|增持|提高仓位|扩大仓位|回补/;
const CHINESE_BEARISH_RE = /减持|减仓|降低敞口|卖出|退出|清仓|止盈/;
const ENGLISH_BULLISH_RE = /\b(?:buy|build|add|increase exposure|top up|rebuild)\b/i;
const ENGLISH_BEARISH_RE = /\b(?:reduce|trim|sell|exit|cut exposure|take profit)\b/i;
const CONDITIONAL_PREFIX_RE = /(?:若|如果|如|待|当|一旦|条件|触发)/;
const CONDITIONAL_WORD_RE = /(?:if|when|unless)/i;
const ALLOW_SUFFIX_RE = /(?:可|才|再|允许|考虑|暂缓)[^，,、。！？!?；;\n]{0,16}$/;

export function hasConflictingPrimaryAction(
  text: string | undefined,
  rating: PortfolioRating,
  language: string,
): boolean {
  const content = (text ?? "").trim();
  if (!content) return false;

  const bullishRe = isChinese(language) ? CHINESE_BULLISH_RE : ENGLISH_BULLISH_RE;
  const bearishRe = isChinese(language) ? CHINESE_BEARISH_RE : ENGLISH_BEARISH_RE;

  const bullishMatch = bullishRe.exec(content);
  const bearishMatch = bearishRe.exec(content);

  if (!bullishMatch && !bearishMatch) return false;

  const isBullishRating = rating === "Buy" || rating === "Overweight";
  const isBearishRating = rating === "Underweight" || rating === "Sell";

  const hasConflict = (match: RegExpExecArray, isForBullish: boolean): boolean => {
    const prefix = content.slice(0, match.index);
    const sentencePrefix = isChinese(language)
      ? (prefix.split(/[。！？!?；;\n/]/).pop() ?? "")
      : (prefix.split(/[.!?;\n]/).pop() ?? "");
    const clausePrefix = sentencePrefix.split(/[，,、]/).pop() ?? "";

    const condRe = isChinese(language) ? CONDITIONAL_PREFIX_RE : CONDITIONAL_WORD_RE;
    if (condRe.test(clausePrefix)) return false;
    if (ALLOW_SUFFIX_RE.test(clausePrefix)) return false;
    if (/(?:条件|触发)/.test(clausePrefix)) return false;
    if (/(?:条件|触发)/.test(content.slice(match.index + match[0].length).slice(0, 16)))
      return false;

    if (isForBullish) {
      if (isBearishRating) return true;
      if (rating === "Hold") return true;
    } else {
      if (isBullishRating) return true;
      if (rating === "Hold") return true;
    }
    return false;
  };

  if (bullishMatch && hasConflict(bullishMatch, true)) return true;
  if (bearishMatch && hasConflict(bearishMatch, false)) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Layer 4 — Sentence similarity (LCS-based, no external deps)
// ---------------------------------------------------------------------------

function lcsRatio(a: string, b: string): number {
  if (a === b) return 1;
  if (!a || !b) return 0;
  const m = a.length;
  const n = b.length;
  // Optimize: only need two rows
  let prev = new Uint16Array(n + 1);
  let curr = new Uint16Array(n + 1);
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      curr[j] =
        a[i - 1] === b[j - 1] ? (prev[j - 1] ?? 0) + 1 : Math.max(prev[j] ?? 0, curr[j - 1] ?? 0);
    }
    [prev, curr] = [curr, prev];
    curr.fill(0);
  }
  return (2 * (prev[n] ?? 0)) / (m + n);
}

export function sentenceSimilarity(left: string, right: string): number {
  const a = compactText(left);
  const b = compactText(right);
  if (!a || !b) return 0;
  if (a === b) return 1;

  const minLen = Math.min(a.length, b.length);
  const maxLen = Math.max(a.length, b.length);
  if (minLen / maxLen < 0.4) return 0;
  if (minLen >= 12 && (a.includes(b) || b.includes(a))) return 0.9;

  return lcsRatio(a, b);
}

export function removeOverlappingSentences(
  text: string | undefined,
  reference: string | undefined,
  threshold = 0.72,
): string {
  const content = (text ?? "").trim();
  if (!content) return "";
  const refContent = (reference ?? "").trim();
  if (!refContent) return content;

  const textSentences = splitSentences(content);
  const refSentences = splitSentences(refContent);
  if (!refSentences.length) return content;

  return textSentences
    .filter((ts) => {
      return !refSentences.some((rs) => sentenceSimilarity(ts, rs) >= threshold);
    })
    .join("\n")
    .trim();
}

// ---------------------------------------------------------------------------
// Layer 5 — Default text generators (bilingual, 5 ratings × 2 languages)
// ---------------------------------------------------------------------------

const TRADING_THESIS_CN: Record<PortfolioRating, string> = {
  Buy: "当前上行逻辑更完整，适合在确认信号仍然有效的前提下逐步建立仓位。驱动这一判断的核心不是单一价格反弹，而是宏观压制边际缓和、行业盈利与供需线索同步改善，以及 ETF 持仓结构开始获得资金承接。换句话说，配置逻辑要先回答为什么现在值得把风险预算重新投向这只 ETF，再把具体加仓节奏交给执行计划去处理。",
  Overweight:
    "当前多头逻辑仍占优，但应以控制节奏的方式增配而不是一次性放大仓位。支撑增配的关键在于主线产业或持仓盈利韧性仍在、市场结构没有转弱，且资金对核心持仓的承接尚未被破坏；真正需要防守的是估值上沿和催化兑现速度，而不是主线本身已经失效。因而本节应先说明为什么组合仍愿意把权重向这只 ETF 倾斜，而不是重复执行层面的加仓步骤。",
  Hold: "当前多空因素并存，短期缺乏足够的赔率与胜率优势，更适合等待更清晰的确认信号。配置逻辑层面需要先说明：中期主线并未被证伪，但宏观估值约束、盈利质量验证和资金流确认还没有形成同向共振，因此没有必要在当前位置主动扩大风险暴露。也就是说，当前持有不是“没有观点”，而是在主线尚存、验证不足的情况下优先保留仓位弹性，把真正的动作阈值留给执行计划。",
  Underweight:
    "当前风险释放节奏快于新增催化兑现速度，更适合先降低敞口并等待更稳健的再介入条件。配置逻辑的重点是说明为什么这只 ETF 当前承受的估值天花板、盈利质量拐点或资金承接弱化，已经让持有成本高于继续等待的收益，而不仅仅是复述减仓动作本身。只有先把这一层“为什么该降权”的逻辑说透，后面的分步减仓和回补条件才有约束力。",
  Sell: "当前风险收益比明显失衡，应以退出仓位或回避参与为主，等待风险重新定价完成。这里需要先说明 ETF 的核心驱动已经从可承受波动演变为主线受损：宏观或产业压制仍在、盈利修复没有兑现、价格结构与资金承接也未出现有效修复。先把退出理由讲清楚，再把清仓与重评估条件留给执行层，才能避免逻辑与动作重复。",
};

const TRADING_THESIS_EN: Record<PortfolioRating, string> = {
  Buy: "The upside thesis is more complete right now, so the setup favors staged accumulation while confirmation remains intact. The core case should explain why macro pressure is easing, industry earnings or supply-demand signals are improving, and ETF structure or flows are starting to validate that repair instead of merely repeating the trade steps. In other words, this section should justify why risk budget belongs here now, while the execution plan handles how to deploy it.",
  Overweight:
    "The bullish setup still has the edge, but exposure should be increased in a controlled way rather than all at once. The thesis needs to explain why the main industry and holdings evidence still supports a larger weight, while valuation ceilings and catalyst timing argue for pacing rather than aggression. That rationale should stay conceptually distinct from the execution plan, which is where the actual add rules belong.",
  Hold: "Bullish and bearish factors are still balanced enough that the setup lacks a clear edge, so waiting is more appropriate. The thesis should explain that the medium-term story is not broken, but macro valuation pressure, earnings-quality confirmation, and flow validation are not yet aligned strongly enough to justify a bigger swing in exposure. That way the logic explains why holding is disciplined, while the execution plan can focus on the thresholds that would change the stance.",
  Underweight:
    "Risk is repricing faster than new upside catalysts are materializing, so trimming exposure is more appropriate. The thesis should make clear why valuation pressure, weakening earnings quality, or fading flow sponsorship now outweigh the benefit of maintaining full exposure, rather than simply restating that the position should be reduced. The actual trimming sequence and rebuild conditions belong in the execution section.",
  Sell: "The current risk-reward is unfavorable enough that exiting or staying out is the cleaner choice until repricing runs its course. The thesis should first explain why the core ETF driver is impaired across macro, industry, earnings, or structure, and why continued holding no longer earns the downside being taken. The execution section can then handle the mechanics of exit and re-entry review.",
};

export function defaultTradingThesis(rating: PortfolioRating, language: string): string {
  return isChinese(language) ? TRADING_THESIS_CN[rating] : TRADING_THESIS_EN[rating];
}

const RISK_MANAGEMENT_CN: Record<PortfolioRating, string> = {
  Buy: "把失效条件写清楚：若价格重新跌回关键支撑下方，且单日成交量放大到20日均量的1.3倍以上，说明承接失败，应立即暂停加仓并把仓位降回试探水平。同时持续跟踪催化兑现时点、业绩验证与行业相对强弱，避免在只有情绪而没有基本面确认时继续追价。",
  Overweight:
    "在增配过程中把单一标的仓位上限、每次加仓比例和失效条件同步约束。若价格连续两天跌破关键支撑，或成交量恢复但股价仍无法突破前高，说明筹码承接不足，应停止加仓并回到核心底仓；若催化兑现不及预期，也要主动降低仓位节奏。",
  Hold: "持续跟踪关键支撑/阻力、成交量、资金流与 ETF 结构信号，并把动作条件写明确：若价格有效跌破关键支撑且单日放量达到20日均量的1.3倍以上，先减掉20%—30%的试探仓位；若价格守住支撑并连续2个交易时段放量修复，同时份额变化和溢折价表现未恶化，再考虑恢复到原仓位。对“成交量改善”的判断不能只看单日放量，至少要结合5日均量、20日均量和价格是否同步收复关键位一起确认。",
  Underweight:
    "在减仓过程中重点看反弹强度、成交量结构和事件兑现进度，避免把缩量反弹误判为趋势修复。若价格反弹但成交量明显弱于20日均量，或催化仍停留在预期阶段，就维持减仓节奏；只有在量价和基本面同步改善时，才允许小比例回补。",
  Sell: "在退出或回避期间继续观察是否出现基本面修复与价格结构重建，但不要把短线反弹当作重新入场信号。只有当关键支撑重新站回、成交量恢复到20日均量以上、并且后续催化或业绩验证同步改善时，才考虑重新评估；否则保持空仓或极轻仓观察。",
};

const RISK_MANAGEMENT_EN: Record<PortfolioRating, string> = {
  Buy: "Define the invalidation clearly: if price falls back below key support and daily volume expands beyond roughly 1.3x the 20-day average, treat that as a failed setup, stop adding, and cut exposure back to probe size. Keep tracking catalyst timing, earnings confirmation, and relative strength so momentum alone does not justify more risk.",
  Overweight:
    "While adding, cap single-name exposure, define each add size, and keep explicit failure conditions. If price loses support for two sessions or volume returns without a clean breakout, stop adding and revert to the core position; if catalyst follow-through weakens, slow the sizing pace immediately.",
  Hold: "Track support/resistance, volume, fund flows, and ETF structure with action thresholds attached: if price breaks key support on roughly 1.3x the 20-day average volume, trim 20%-30% of the probing risk; if price stabilizes and reclaims the level with improving volume for two sessions while share changes and premium-discount behavior remain orderly, restore the prior size. Do not call it volume improvement from one noisy session alone—confirm it against both the 5-day and 20-day averages and against price recovery.",
  Underweight:
    "As exposure is reduced, focus on rebound quality, volume structure, and catalyst follow-through so weak countertrend moves are not mistaken for a true repair. Only allow a small rebuild if price, volume, and fundamentals all improve together.",
  Sell: "While staying out, keep watching for real repair in fundamentals and price structure, but do not treat a short squeeze or reflex bounce as enough. Reconsider only after support is reclaimed, volume recovers above the 20-day average, and catalysts or guidance improve together.",
};

export function defaultRiskManagement(rating: PortfolioRating, language: string): string {
  return isChinese(language) ? RISK_MANAGEMENT_CN[rating] : RISK_MANAGEMENT_EN[rating];
}

const DEBATE_CONCLUSION_CN: Record<PortfolioRating, string> = {
  Buy: "整场辩论中，看多一侧不仅更充分地证明了产业趋势、盈利兑现与价格承接之间的正向联动，也更清楚地解释了为何短期波动不足以破坏中期上行结构。相较之下，看空一侧虽然提示了估值与节奏风险，但未能证明这些风险已经足以推翻主线逻辑，因此当前结论更偏向积极布局而不是继续观望。",
  Overweight:
    "整场辩论中，看多一侧在产业趋势、催化兑现与盈利韧性上的论证更占优，说明上行逻辑仍是主导变量；但看空一侧关于波动、估值与兑现节奏的提醒也提示仓位不宜一次性放大。综合来看，更合理的结论是在保留风险边界的前提下逐步增配，而不是激进满仓。",
  Hold: "整场辩论中，多空双方都给出了成立的证据：乐观一侧证明了中期逻辑尚未被破坏，谨慎一侧则指出短期估值、节奏与价格确认仍不够充分。由于现阶段还缺少能够打破平衡的新证据，最稳妥的结论不是贸然加仓或减仓，而是先维持现有敞口并等待更明确的验证信号。",
  Underweight:
    "整场辩论中，偏谨慎一侧对估值约束、风险释放节奏和下行边界的论证更完整，说明当前风险重定价的压力尚未结束。即便乐观一侧提出了中长期逻辑，其关键前提仍依赖后续催化兑现与价格结构修复，因此当前更适合先降低敞口、把仓位收回到更安全的水平。",
  Sell: "整场辩论中，看空一侧对基本面下修、技术破位和风险收益失衡的论证最具决定性，并且更清楚地说明了继续持有的代价正在上升。相比之下，乐观论点仍停留在潜在修复或远期改善的假设上，尚不足以抵消当前下行风险，因此更合理的结论是退出仓位而不是继续承受回撤。",
};

const DEBATE_CONCLUSION_EN: Record<PortfolioRating, string> = {
  Buy: "Across the full debate, the bullish side made the more complete case on trend durability, earnings follow-through, and price support, and it also explained more convincingly why the recent risks are not yet thesis-breaking. The opposing side raised valid caution flags, but it did not show that those risks are strong enough to overturn the broader upside setup, so active accumulation is more justified than continued hesitation.",
  Overweight:
    "Across the full debate, the bullish evidence is stronger on balance because the upside thesis still has better support from catalysts, earnings resilience, and market structure. Even so, the cautious side made a credible case that volatility and timing risk still matter, so the right conclusion is controlled upside exposure rather than an all-in posture.",
  Hold: "Across the full debate, both sides surfaced credible evidence: the bullish camp showed that the core thesis is still intact, while the cautious camp showed that timing, valuation, and confirmation risk remain unresolved. Because neither side produced the decisive incremental evidence needed to justify a bigger exposure change, maintaining current positioning is more disciplined than forcing either an add or a reduction.",
  Underweight:
    "Across the full debate, the bearish side made the stronger case on valuation pressure, risk-release cadence, and downside boundaries, which means the market is still repricing risk rather than rewarding conviction. The bullish case still depends on future confirmation rather than present proof, so trimming exposure is more appropriate than defending a full-sized position.",
  Sell: "Across the full debate, the bearish side presented the decisive case on deteriorating fundamentals, technical breakdown risk, and an unfavorable risk-reward profile. The more optimistic view still relies on future stabilization rather than current evidence, so exiting is more appropriate than continuing to absorb drawdown while waiting for a thesis repair that has not yet materialized.",
};

export function defaultDebateConclusion(rating: PortfolioRating, language: string): string {
  return isChinese(language) ? DEBATE_CONCLUSION_CN[rating] : DEBATE_CONCLUSION_EN[rating];
}

const ACTION_LOGIC_CN: Record<PortfolioRating, string> = {
  Buy: "当前的明确动作是买入，而不是继续观望，因为这意味着上方报告已经同时给出了更强的主线证据：宏观冲击对该 ETF 的核心暴露不再构成压制，行业供需或库存信号正在改善，且市场与资金流开始验证这一修复。执行上不能把“看多”停留在口号层面，而要把仓位放大建立在可观察的证据上：价格重新站上关键位、成交量或持仓量放大、主要持仓的盈利与催化继续兑现。只要这些证据仍在强化，就可以沿着既定节奏分批加仓；一旦出现宏观异象反向扩大、产业数据再度转弱或量价验证失效，就必须立刻放慢节奏并重新审视买入理由。",
  Overweight:
    "当前的明确动作是增持，因为主线逻辑仍偏向有利一侧，但证据强度还不足以支持一次性把风险敞口推到极限。更合适的做法是在已有底仓上逐步加码，把每一步加仓都和新证据绑定起来：例如宏观错配缓解、行业价格与库存出现改善、头部持仓盈利预期继续上修、以及 ETF 自身的流动性和份额变化没有恶化。这样做的意义，不是机械地“看多”，而是在确认赔率和胜率同步改善时放大收益暴露；若后续出现催化递延、利润兑现弱于预期或价格结构转差，就应暂停增持并把仓位退回更中性的水平。",
  Hold: "当前的明确动作是持有，因为现有证据足以说明不必急于撤退，但还不足以支持立即扩大敞口。换句话说，基准判断并不是“没有观点”，而是上行与下行的关键证据仍在拉锯：宏观环境没有坏到必须减仓，可产业、盈利、流动性或价格确认里仍有至少一环没有完成闭合。接下来最重要的不是空泛地“继续观察”，而是盯住真正能改写结论的异象：例如关键支撑是否被重新站稳、成交量和份额是否同步修复、行业库存与价格是否出现方向一致的变化、主要持仓的业绩验证是否落地。只要这些证据没有向同一方向集中，维持仓位就是更有纪律的动作；一旦验证集中向上，可转入增持；若异象集中转弱，则应切换为减仓。",
  Underweight:
    "当前的明确动作是减持，因为风险释放速度快于利多兑现速度，继续维持原有仓位相当于默认承担一个尚未被充分定价的回撤过程。这里的重点不是宣告长期逻辑彻底结束，而是承认当前最有信息量的证据——宏观压力、行业供需恶化、利润预期下修、或价格与资金流背离——更支持先把ETF净敞口降下来。执行上只能调整这只ETF在组合中的整体目标权重，成分股风险用于解释为什么要降ETF仓位，而不是对成分股下达清仓或减持指令；只有当宏观异象缓和、产业数据止跌回升、并且市场重新给出价格与流动性的双重确认时，才考虑逐步回补ETF仓位，而不是抢跑逆势加仓。",
  Sell: "当前的明确动作是卖出，因为最新证据链已经不再支持继续忍受持仓风险：如果宏观冲击仍在加深、行业景气与盈利预期同步走弱、而价格结构又没有出现可靠修复，那么继续持有本身就是一种没有被补偿的风险暴露。此时最重要的不是寻找安慰性理由，而是承认基准情景已经转向防守，并把资金从一个下行概率更高的敞口中撤出来。只有在后续重新看到基本面修复、价格站回关键位、量能与资金流再度转正这些条件同时出现时，才值得重新评估入场；在那之前，回避风险比抄底冲动更有价值。",
};

const ACTION_LOGIC_EN: Record<PortfolioRating, string> = {
  Buy: "The current decision works only if three conditions continue to hold together: valuation remains supportive, catalysts keep improving, and price structure does not break down. That means execution should favor staged accumulation rather than a one-shot position, with adds tied to confirmation in volume, earnings follow-through, and catalyst delivery. If those validation signals weaken, the build pace should slow immediately and the bullish thesis should be re-tested rather than assumed.",
  Overweight:
    "The case supports adding exposure, but only in a measured way, because the upside thesis is still stronger than the downside case while volatility and timing risk remain real. Adds should therefore be linked to catalyst follow-through, valuation digestion, and price support rather than pure momentum chasing. If earnings delivery slips, catalysts fade, or price structure deteriorates, the right move is to pause the adds and move back toward neutral exposure.",
  Hold: "The disciplined move is to maintain current exposure because the upside case is not yet strong enough to justify adding, while the downside case is not yet severe enough to force an immediate trim. The key is to keep monitoring support levels, volume and fund-flow behavior, ETF structure stability, and the next round of macro confirmation. If those inputs improve together, the setup can be revisited for an add; if support breaks or structure quality worsens, the stance should shift toward reduction.",
  Underweight:
    "The core logic is to reduce ETF net exposure before the market finishes repricing the current risks, rather than waiting passively for volatility to do the damage. Execution may adjust only the ETF’s overall portfolio weight; constituent risks explain why the ETF weight should fall, but they are not direct instructions to trade named holdings. Rebuilding should happen only after valuation resets, catalysts re-accelerate, and price structure stabilizes, not before.",
  Sell: "The current risk-reward is unfavorable enough that staying in the name does not offer a justified payoff for the downside being assumed. Execution should therefore prioritize exiting or staying out until both fundamentals and price structure show evidence of repair. Before that happens, attempts to buy the dip would amount to taking uncompensated risk rather than following a disciplined process.",
};

export function defaultActionLogic(rating: PortfolioRating, language: string): string {
  return isChinese(language) ? ACTION_LOGIC_CN[rating] : ACTION_LOGIC_EN[rating];
}

function buildPositioningGuidanceTemplates(contextText?: string): {
  cn: Record<PortfolioRating, string>;
  en: Record<PortfolioRating, string>;
} {
  const support = anchorClause(contextText ?? "", "关键均线位", 2);
  const cn: Record<PortfolioRating, string> = {
    Buy: `先按目标仓位的50%—60%建立底仓，确认价格站稳${support}、成交量连续高于近20日均量且份额继续净申购后，再把仓位逐步提升到目标上沿。若溢折价异常扩大、主要支撑失守或行业盈利验证不再改善，则暂停加仓并把仓位收回到底仓。执行上按周度复核价格、量能、份额变化与宏观验证链条，任一环节失效都不追高扩仓。`,
    Overweight:
      "先把现有仓位提高到目标上限的70%—80%，只有在价格承接、量能、溢折价和资金流继续同向改善时才进一步增配。若催化兑现慢于预期、份额恢复停滞或前十大持仓集中度继续抬升而盈利修正未跟上，则先把超配部分降回基准仓位。再平衡上优先看价格确认、产品层验证和行业盈利线索是否仍保持同向共振。",
    Hold: `维持现有基准仓位，不新增方向性敞口，新增资金优先等待价格重新站稳${support}、成交量回到近期均量上方、份额或资金流同步改善后再考虑上调一个档位。若价格跌破主要支撑、资金流重新转负或产品层指标恶化，则先把仓位降回更保守区间而不是被动承受回撤。执行上按周度复核量价、份额变化、溢折价和宏观/行业验证信号，只有验证链条继续强化时才从持有转向增配。`,
    Underweight: `先把仓位压回风险预算下沿或目标仓位的30%—40%，反弹只有在价格修复、量能放大和份额恢复净流入同时出现时才允许暂缓减仓。若反弹无法收复${support}、溢折价走弱或行业盈利线索继续下修，则继续分批削减敞口并收缩风险预算。再平衡重点盯住价格修复质量、产品层承接与风险释放节奏，而不是仅凭单日反弹回补仓位。`,
    Sell: "把剩余仓位降到0%—10%的观察仓或直接清仓，只有在基本面、价格结构和产品层指标共同修复时才重新评估是否回补。若后续仍看不到量价承接、份额回流和盈利修正改善，就继续保持低暴露，不因为短期反弹提前回补。执行上优先处理流动性和回撤控制，把再入场判断留给下一轮完整验证。",
  };
  const en: Record<PortfolioRating, string> = {
    Buy: `Start with roughly 50% to 60% of target exposure, then scale toward the upper bound only after price reclaims ${support}, volume improves, and ETF flow confirmation improve together. If support breaks, premium-discount widens abnormally, or earnings confirmation stalls, pause the build and cut back to the starter size. Rebalance weekly against price structure, volume, product-level checks, and macro confirmation rather than chasing a single strong session.`,
    Overweight:
      "Lift the position to roughly 70% to 80% of the intended overweight first, and only move to full overweight if price support, volume, premium-discount, and flows keep improving together. If catalyst delivery lags or concentration rises without matching earnings support, trim the add-on back to benchmark size. Rebalance around confirmation quality, not just around a headline-driven rally.",
    Hold: `Keep benchmark exposure in place and avoid adding directional risk until price reclaims ${support}, volume recovers versus its recent average, and ETF flows improve at the same time. If support fails again or product-level indicators deteriorate, reduce back to a more defensive baseline instead of passively absorbing drawdown. Review price, volume, flows, premium-discount, and macro or industry confirmation weekly before shifting from hold to add.`,
    Underweight: `Cut the position back toward the low end of the risk budget, roughly 30% to 40% of target exposure, and only pause the reduction if price repair, stronger volume, and ETF flow stabilization arrive together. If rebounds fail at ${support} or earnings signals keep weakening, continue trimming in stages and keep risk budget tight. Rebalance around repair quality and risk-release cadence rather than short-term relief rallies.`,
    Sell: "Reduce exposure to zero or to a token 0% to 10% watch position, and only reconsider entry after fundamentals, price structure, and product-level metrics all repair together. If there is still no flow support or earnings repair, stay sidelined and do not buy back a reflex rally. Keep the focus on liquidity and drawdown control until a new full validation window opens.",
  };
  return { cn, en };
}

export function defaultResearchPositioningGuidance(
  rating: PortfolioRating,
  language: string,
  contextText?: string,
): string {
  const templates = buildPositioningGuidanceTemplates(contextText);
  return isChinese(language) ? templates.cn[rating] : templates.en[rating];
}

export function defaultPositioningGuidance(
  rating: PortfolioRating,
  language: string,
  contextText?: string,
): string {
  const detailed = defaultResearchPositioningGuidance(rating, language, contextText);
  const firstSentence = isChinese(language)
    ? (detailed.split(/(?<=[。.])\s*/)[0] ?? detailed)
    : (detailed.split(/(?<=\.)\s+/)[0] ?? detailed);
  return firstSentence || detailed;
}

function buildExecutionPlanTemplates(contextText?: string): {
  cn: Record<PortfolioRating, string>;
  en: Record<PortfolioRating, string>;
} {
  const primary = primaryAnchor(contextText ?? "", "关键均线位");
  const support = anchorClause(contextText ?? "", "关键支撑位", 2);
  const cn: Record<PortfolioRating, string> = {
    Buy: `先以计划目标仓位的20%—30%建立试探仓，后续每一笔只增加10%—15%。只有当价格重新站回${primary}，且日成交量连续2个交易日达到近20日均量的1.2—1.3倍，同时 ETF 份额继续净申购或溢折价不再走阔，才继续加仓。若催化只是消息预期而未兑现为订单、业绩指引、份额扩张或放量突破，就暂停追价，等待回踩${primary}不破后再执行下一笔。`,
    Overweight: `在保留现有底仓的前提下择机增配，但每一笔加仓都要绑定清晰的关键数据：价格至少守住${support}，日成交量回到近20日均量的1.1—1.2倍以上，且 ETF 份额、净申购或溢折价改善没有转弱。单笔增配宜控制在目标仓位的10%—15%，只有当新增催化从"预期"变成"可验证进展"并连续两个交易时段保持量价承接时，才继续上调；若量价配合不足或催化兑现延迟，就把超配部分压回到底仓。`,
    Hold: `维持当前仓位，不主动追涨或杀跌。这里优先看的关键支撑直接写成${support}；只有当价格在该位置附近连续2个交易时段止跌企稳，日成交量至少较近5日均量放大15%—20%且明显回到20日均量附近，同时份额或资金流不再恶化，才考虑把持有转为试探性加仓。若新增催化只是消息层面的预期而未带来份额扩张、溢折价改善、资金流确认或放量突破，则继续维持仓位，不提前放大敞口。`,
    Underweight: `优先分2—3笔降低ETF整体敞口，每一笔先减掉目标仓位的10%—15%，不得把执行动作拆成对成分股的清仓或减持。若反弹连${support}都收不回，且日成交量仍低于近20日均量的0.9—1.0倍或 ETF 份额继续净赎回，就继续执行ETF层面的减仓；只有当价格重新收复主要均线、日成交量回到20日均量的1.1—1.2倍、份额转为连续净申购，才考虑小比例回补ETF仓位，而不是在缩量反弹里抢跑。`,
    Sell: `以退出仓位或避免入场为主，执行上不要等待模糊修复信号。若价格已跌破${support}，且单日放量达到近20日均量的1.3倍以上，或 ETF 溢折价继续恶化、份额净赎回扩大，就应直接完成清仓；即便后续出现技术性反弹，也要先看到基本面修复、价格重新站回关键均线、日成交量恢复到20日均量上方以及催化兑现三者同时出现，才考虑重新纳入观察名单。`,
  };
  const en: Record<PortfolioRating, string> = {
    Buy: "Start with only 20%-30% of the intended target size and keep later adds to 10%-15% increments. Add only after price reclaims the first concrete market level already named in the market report — ideally the actual 50-day average, Bollinger mid-band, prior breakout, or retest level — while daily volume holds at roughly 1.2x-1.3x the 20-day average for two sessions and ETF share creation or premium-discount behavior does not deteriorate. If the catalyst is still only narrative rather than verifiable progress, pause the build and wait for a successful retest of that level.",
    Overweight:
      "Add selectively from the core position, but tie each add to explicit confirmation: price must hold the market report’s main support or moving-average anchor, volume should recover to roughly 1.1x-1.2x the 20-day average, and ETF share or premium-discount signals should remain orderly. Keep each add controlled rather than one-shot, and if that confirmation fades, cut the pace and keep only the already-validated core exposure.",
    Hold: "Maintain current exposure and avoid forcing new trades. Treat the key support zone as the concrete 50-day moving average, Bollinger mid-band, prior swing low, or repeated support area already cited in the market report; only reconsider adding if price stabilizes there for two trading sessions, volume improves by roughly 15%-20% versus the recent 5-day average and recovers toward the 20-day average, and ETF share or fund-flow conditions stop worsening. If the catalyst remains only a headline without share growth, premium-discount improvement, fund-flow confirmation, or breakout confirmation, keep the allocation unchanged.",
    Underweight:
      "Trim exposure in two or three steps, starting with the weakest-conviction slice and reducing roughly 10%-15% of target exposure per step. If rebounds fail to reclaim the market report’s key averages or resistance levels while volume stays below roughly 0.9x-1.0x the 20-day average or ETF shares keep shrinking, continue trimming; only consider a small rebuild after price, volume, and ETF flow repair arrive together.",
    Sell: "Prioritize exiting or staying out without waiting for vague repair signals. If price has already broken the market report’s core support or stop level on roughly 1.3x the 20-day average volume, or ETF share and premium-discount behavior keep worsening, complete the exit; only revisit the name after fundamentals, catalysts, and price structure all repair together.",
  };
  return { cn, en };
}

export function defaultExecutionPlan(
  rating: PortfolioRating,
  language: string,
  contextText?: string,
): string {
  const templates = buildExecutionPlanTemplates(contextText);
  return isChinese(language) ? templates.cn[rating] : templates.en[rating];
}

// ---------------------------------------------------------------------------
// Layer 6 — Section heading strip
// ---------------------------------------------------------------------------

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function stripLeadingSectionHeadings(
  text: string | undefined,
  headings: ReadonlyArray<string>,
): string {
  const content = (text ?? "").trim();
  if (!content || !headings.length) return content;

  const escaped = [...new Set(headings.map((h) => h.trim()).filter(Boolean))]
    .map(escapeRegExp)
    .sort((a, b) => b.length - a.length);
  if (!escaped.length) return content;

  const headingPattern = escaped.join("|");
  const numberedHeading =
    `(?:[#>*\\-\\s]*)?` +
    `(?:(?:[一二三四五六七八九十]+|\\d+)\\s*[、.．)）\\-:：]\\s*)?` +
    `(?:${headingPattern})\\s*`;
  const lineRe = new RegExp(
    `^(?:${numberedHeading})(?:(?:[,，;；/、]\\s*|\\s+)(?:${numberedHeading}))*$`,
    "i",
  );

  const lines = content
    .split(/\n+/)
    .map((l) => l.trim())
    .filter(Boolean);
  while (lines.length > 0 && lineRe.test(lines[0] ?? "")) {
    lines.shift();
  }
  return lines.join("\n").trim();
}

// ---------------------------------------------------------------------------
// Layer 7 — Instruction leakage strip (focused subset)
// ---------------------------------------------------------------------------

const MANAGER_INSTRUCTION_INLINE_PATTERNS: ReadonlyArray<RegExp> = [
  /请在[^。！？\n]{0,40}(?:字段|参数|输出|填写|格式)[^。！？\n]{0,20}(?:中|里|内|上)[^。！？\n]{0,20}(?:提供|填写|输出|包含|给出|使用)[。！]?\s*/g,
  /请(?:确保|确认|注意|务必)[^。！？\n]{0,30}(?:字段|参数|输出|格式|JSON|json)[^。！？\n]{0,20}[。！]?\s*/g,
  /(?:Please|please)\s+.{0,60}(?:field|parameter|output|format|JSON).{0,40}[.!]?\s*/g,
  /(?:You must|you must|Make sure|make sure)\s+.{0,60}(?:field|parameter|output|format).{0,40}[.!]?\s*/g,
  /(?:输出|填写|提供)(?:时|中|里)?(?:需要|必须|应该|应当)[^。！？\n]{0,20}(?:包含|包括|遵循|按照|使用)[^。！？\n]{0,30}[。！]?\s*/g,
];

const MANAGER_SCHEMA_FIELD_LINE_RE = /(?:字段名|参数名|field name|parameter name)\s*[:：]\s*\S+/i;

const STRUCTURED_PARAMETER_BLOCK_START_RE = /\|\s*(?:字段|参数|field|parameter|指标|metric)\s*\|/i;

const STRUCTURED_PARAMETER_ROW_RE = /\|\s*\S+\s*\|\s*\S+\s*\|/;

const MARKDOWN_OR_CHINESE_SECTION_HEADING_RE = /^#{1,6}\s|^[一二三四五六七八九十]+[、.]/;

function stripStructuredParameterBlocks(text: string): string {
  const lines = text.split("\n");
  const kept: string[] = [];
  let skipping = false;

  for (const rawLine of lines) {
    const stripped = rawLine.trim();
    if (!stripped) {
      skipping = false;
      kept.push(rawLine);
      continue;
    }
    if (skipping) {
      if (MARKDOWN_OR_CHINESE_SECTION_HEADING_RE.test(stripped)) {
        skipping = false;
        kept.push(rawLine);
        continue;
      }
      if (
        /[│─┌┐└┘├┤┬┴┼|]/.test(stripped) ||
        STRUCTURED_PARAMETER_ROW_RE.test(stripped) ||
        MANAGER_SCHEMA_FIELD_LINE_RE.test(stripped)
      ) {
        continue;
      }
      skipping = false;
      kept.push(rawLine);
      continue;
    }
    if (
      STRUCTURED_PARAMETER_BLOCK_START_RE.test(stripped) &&
      STRUCTURED_PARAMETER_ROW_RE.test(stripped)
    ) {
      skipping = true;
      continue;
    }
    kept.push(rawLine);
  }
  return kept.join("\n");
}

export function stripManagerInstructionLeakage(text: string | undefined): string {
  let cleaned = text ?? "";
  if (!cleaned) return "";

  for (const pattern of MANAGER_INSTRUCTION_INLINE_PATTERNS) {
    cleaned = cleaned.replace(pattern, "");
  }
  cleaned = stripStructuredParameterBlocks(cleaned);

  const filteredLines: string[] = [];
  for (const rawLine of cleaned.split("\n")) {
    const stripped = rawLine.trim();
    if (stripped && MANAGER_SCHEMA_FIELD_LINE_RE.test(stripped)) continue;
    if (
      stripped &&
      ((stripped.includes("结构化") &&
        stripped.includes("参数") &&
        (stripped.includes("映射") ||
          stripped.includes("字段") ||
          stripped.includes("填写") ||
          stripped.includes("填充"))) ||
        (stripped.includes("结构化") &&
          (stripped.includes("触发器") || stripped.includes("触发条件")) &&
          (stripped.includes("指标") || stripped.includes("度量"))) ||
        ((stripped.includes("机器可读") ||
          stripped.includes("字段名") ||
          stripped.includes("参数名")) &&
          (stripped.includes("不要") || stripped.includes("不得") || stripped.includes("切勿"))))
    ) {
      continue;
    }
    filteredLines.push(rawLine);
  }
  cleaned = filteredLines.join("\n");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

// ---------------------------------------------------------------------------
// Layer 8 — Core sanitizers
// ---------------------------------------------------------------------------

export interface SanitizeSectionOptions {
  checkActionConflict?: boolean;
  requireDetail?: boolean;
  stripHeadings?: ReadonlyArray<string>;
}

export function sanitizeSection(
  text: string | undefined,
  defaultText: string,
  rating: PortfolioRating,
  language: string,
  opts?: SanitizeSectionOptions,
): string {
  let content = (text ?? "").trim();

  // 1. Strip leading section headings
  if (opts?.stripHeadings?.length) {
    content = stripLeadingSectionHeadings(content, opts.stripHeadings);
  }

  // 2. Strip manager instruction leakage
  content = stripManagerInstructionLeakage(content);

  // 3. Placeholder check
  if (!content || isPlaceholderLike(content)) return defaultText;

  // 4. Strip embedded recommendation labels line-by-line
  const lines = content.split("\n");
  const keptLines: string[] = [];
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      keptLines.push(rawLine);
      continue;
    }
    if (
      containsExplicitRatingMarker(line, language) &&
      isRecommendationOnlySegment(line, language)
    ) {
      continue;
    }
    // Within each line, strip individual sentences meeting both conditions
    const splitPattern = isChinese(language) ? /(?<=[。！？!?])\s*/ : /(?<=[.!?])\s+/;
    const sentences = line.split(splitPattern);
    const keptSentences = sentences.filter((s) => {
      const trimmed = s.trim();
      if (!trimmed) return false;
      return !(
        containsExplicitRatingMarker(trimmed, language) &&
        isRecommendationOnlySegment(trimmed, language)
      );
    });
    if (keptSentences.length > 0) {
      keptLines.push(keptSentences.join(isChinese(language) ? "" : " "));
    }
  }
  content = keptLines.join("\n").trim();

  // 5. Strip recommendation-restating sentences
  content = stripRecommendationRestatingSentences(content, language);

  // 6. Post-strip placeholder check
  if (!content || isPlaceholderLike(content)) return defaultText;

  // 7. Action conflict check
  if (opts?.checkActionConflict && hasConflictingPrimaryAction(content, rating, language)) {
    return defaultText;
  }

  // 8. Detail check
  if (opts?.requireDetail && sectionNeedsDetail(content, language)) {
    return mergeSparseSectionWithDefault(content, defaultText, language);
  }

  return content;
}

export function mergeSparseSectionWithDefault(
  content: string | undefined,
  defaultText: string,
  language?: string,
): string {
  const trimmed = (content ?? "").trim();
  if (!trimmed) return defaultText;
  if (compactText(trimmed) === compactText(defaultText)) return defaultText;

  const endsWithPunctuation = isChinese(language ?? "")
    ? /[。！？!?]$/.test(trimmed)
    : /[.!?]$/.test(trimmed);
  const joiner = endsWithPunctuation ? "\n" : isChinese(language ?? "") ? "。\n" : ".\n";
  return `${trimmed}${joiner}${defaultText}`;
}

const HEADING_ALIASES = [
  "配置逻辑",
  "配置执行计划",
  "再平衡与风险控制",
  "执行倾向",
  "ETF Allocation Thesis",
  "Allocation Execution Plan",
  "Rebalance and Risk Controls",
  "ETF配置逻辑",
  "执行计划",
  "风险控制",
  "配置逻辑与执行倾向",
  "配置执行逻辑",
];

export function sanitizeTraderThesis(
  text: string | undefined,
  executionPlan: string,
  rating: PortfolioRating,
  language: string,
): string {
  const headings = HEADING_ALIASES;
  let content = stripLeadingSectionHeadings((text ?? "").trim(), headings);
  content = stripManagerInstructionLeakage(content);

  const defaultText = defaultTradingThesis(rating, language);
  if (!content || isPlaceholderLike(content)) return defaultText;
  if (hasConflictingPrimaryAction(content, rating, language)) return defaultText;

  // Deduplicate against execution_plan
  content = removeOverlappingSentences(content, executionPlan);
  if (!content) return defaultText;
  if (hasConflictingPrimaryAction(content, rating, language)) return defaultText;

  // Detail check (stricter thresholds: Chinese < 85 chars or < 3 sentences)
  const compacted = compactText(content);
  const sentenceCount = content.match(/[。！？!?.]+/g)?.length ?? 0;
  const needsDetail = isChinese(language)
    ? compacted.length < 85 || sentenceCount < 3
    : (content.match(/\b\w+\b/g)?.length ?? 0) < 30 || sentenceCount < 3;

  if (needsDetail) {
    return mergeSparseSectionWithDefault(content, defaultText, language);
  }
  return content;
}

export function sanitizeTraderRiskManagement(
  text: string | undefined,
  thesis: string,
  executionPlan: string,
  rating: PortfolioRating,
  language: string,
): string {
  const headings = HEADING_ALIASES;
  let content = stripLeadingSectionHeadings((text ?? "").trim(), headings);
  content = stripManagerInstructionLeakage(content);

  const defaultText = defaultRiskManagement(rating, language);
  if (!content || isPlaceholderLike(content)) return defaultText;

  // Deduplicate against thesis AND execution_plan combined
  content = removeOverlappingSentences(content, `${thesis}\n${executionPlan}`);
  if (!content) return defaultText;

  if (sectionNeedsDetail(content, language)) {
    return mergeSparseSectionWithDefault(content, defaultText, language);
  }
  return content;
}

// ---------------------------------------------------------------------------
// missingExecutionThresholds
// ---------------------------------------------------------------------------

const NUMERIC_THRESHOLD_RE =
  /\d+(?:\.\d+)?(?:%|％|倍|元|美元|港元|日|天|周|月|SMA|EMA|ATR|VWMA|均线|布林|bp|bps|x)/;

const MARKET_LEVEL_ANCHOR_RE =
  /(?:50日均线|20日均线|10日均线|200日均线|布林中轨|布林上轨|布林下轨|布林带中轨|布林带上轨|布林带下轨|前高突破位|前低回踩位|前低|前高|主支撑位|主支撑|主阻力位|主阻力|支撑位|阻力位|支撑带|阻力带|密集成交区|上一压力位|压力位|止损位|50-day(?:\s+(?:moving average|SMA))?|20-day(?:\s+(?:moving average|SMA))?|10-day(?:\s+(?:moving average|SMA))?|200-day(?:\s+(?:moving average|SMA))?|Bollinger mid-band|Bollinger middle band|Bollinger upper band|Bollinger lower band|prior breakout level|prior retest level|swing low|swing high|support(?: zone)?|resistance(?: zone)?|stop(?:-loss)? level|VWMA|ATR|NAV|SMA|EMA)/;

const VOLUME_FLOW_LABELS =
  "(?:成交量|成交额|量能|5日均量|20日均量|日均量|净流入|净流出|净申购|净赎回|份额|溢折价|跟踪误差|volume|turnover|fund flow|share change|share creation|premium-discount|tracking error)";
const VOLUME_FLOW_WITH_NUM_RE = new RegExp(
  `${VOLUME_FLOW_LABELS}[^。\\n]{0,32}\\d+(?:\\.\\d+)?\\s*(?:%|％|倍|x|亿元|亿|万份|亿份|bp|bps|天|日)` +
    "|" +
    `\\d+(?:\\.\\d+)?\\s*(?:%|％|倍|x|亿元|亿|万份|亿份|bp|bps|天|日)[^。\\n]{0,32}${VOLUME_FLOW_LABELS}`,
  "i",
);

export function missingExecutionThresholds(text: string | undefined): boolean {
  const content = (text ?? "").trim();
  if (!content) return true;
  const hasNumeric = NUMERIC_THRESHOLD_RE.test(content);
  const hasAnchor = MARKET_LEVEL_ANCHOR_RE.test(content);
  const hasVolume = VOLUME_FLOW_WITH_NUM_RE.test(content);
  return !(hasNumeric && hasAnchor && hasVolume);
}
