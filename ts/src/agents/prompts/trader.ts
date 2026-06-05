/**
 * Trader system message + structured-output-only sentences.
 * Port of the prompt block in ``etfagents.agents.trader.trader`` with
 * TS-specific visible schema guidance.
 *
 * Path A: omits ``inject_memory_prompt_section``. Sub-step 2 will add it.
 */

import { isChinese } from "../schemas/rating.js";
import {
  getAgentOutputSchemaInstruction,
  getLanguageInstruction,
  getLocalizedExecutionBiasInstruction,
  type PromptContext,
} from "./shared.js";

export const STRUCTURED_FIELD_POPULATION_INSTRUCTION =
  "In addition to the prose sections, populate the structured fields " +
  "key_drivers, confidence, target_weight_pct, target_weight_band, execution_timing, add_triggers, " +
  "reduce_triggers, exit_triggers, rebalance_triggers, and risk_controls " +
  "whenever the evidence supports them; use null or empty lists only when " +
  "the reports truly do not justify reliable values.";

export const STRUCTURED_TRIGGER_METRICS_INSTRUCTION =
  "For structured triggers, prefer supported metrics such as close, open, " +
  "high, low, volume, sma_20, close_50_sma, volume_ratio_20d, pnl_pct, " +
  "and weight_pct.";

export const STRUCTURED_FIELD_VISIBILITY_INSTRUCTION =
  "Never expose machine-readable field names such as target_weight_pct, " +
  "target_weight_band, execution_timing, add_triggers, reduce_triggers, " +
  "exit_triggers, rebalance_triggers, or risk_controls in the visible prose outside the required Output Schema block.";

export const TRADER_FREETEXT_FALLBACK_INSTRUCTION =
  "Free-text fallback mode: write the final visible report directly, not hidden schema fields. " +
  "Use exactly four top-level sections in this order: " +
  "`一、配置逻辑`, `二、配置执行计划`, `三、再平衡与风险控制`, `四、执行倾向`. " +
  "In section `四、执行倾向`, put only the final rating on the next line as `**买入/增持/持有/减持/卖出**` when writing in Chinese, " +
  "or `**BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL**` when writing in English. " +
  "After the four sections, append the required plain-text Output Schema block if the system prompt asks for it. " +
  "Do not output parameter mappings, field-value tables outside that Output Schema, hidden structured field dumps, or trigger arrays.";

function traderDetailInstruction(ctx: PromptContext): string {
  if (isChinese(ctx.language)) {
    return (
      '对于 ETF 配置执行计划和风险控制，不能只写"等待支撑""观察成交量""关注资金流"这类泛化表述而不给解释。' +
      "所有执行动作的对象必须是ETF整体仓位或ETF目标权重；成分股和重仓股只能作为风险归因，不能写成清仓、减持、保留或调仓某只成分股。" +
      "每个论据必须引用上方报告中的具体数据，不能只写泛化判断。请明确什么算关键支撑或阻力，并优先引用市场报告中的具体类型和数值" +
      "（例如50日均线位于X元、布林中轨位于Y元、前低位于Z元）；" +
      "不要写“市场报告中的关键位”“前文提到的50日均线”这类让读者回头查找的表述，必须把数值直接重写在当前句子里。" +
      '同时说明成交量或资金流改善应相对近5日或20日均量达到什么程度（如"成交量需达到近20日均量的1.3倍以上"）；' +
      "以及什么样的宏观、风格或结构催化确认才足以支持加仓、持有、减仓、轮动或退出（如利率决议时间、指数成分调整窗口、资金流向阈值）；" +
      "还需要说明 ETF 结构验证的具体指标（如份额变化幅度、溢折价偏离百分比、跟踪误差、前十大持仓集中度百分比）。" +
      "这两部分必须写成完整分析段落，并给出清晰阈值与触发条件。" +
      "若没有上方报告里的具体价位、均线数值、量能基数或份额/溢折价数据，就不要下加仓、减仓或回补指令。" +
      '优先写成"2.08元的50日均线、2.05元的布林中轨、成交量回到20日均量的1.3倍、份额连续2日净申购"这种可执行格式。'
    );
  }
  return (
    "For the ETF allocation execution plan and risk controls, do not use generic phrases such as 'wait for support', 'watch volume', or 'monitor fund flows' without explanation. " +
    "Every execution action must target the ETF position or ETF target weight; constituent stocks may be used only as risk attribution, never as direct buy/sell/trim/retain instructions for named holdings. " +
    "Every argument must quote specific data from the reports above — do not rely on generic judgments. " +
    "Spell out what counts as key support or resistance by referencing the market report with exact numbers (e.g., 50-day SMA at X, Bollinger mid-band at Y, prior swing low at Z), " +
    "and restate those numbers inline in the same sentence instead of telling the reader to look back at the market report. " +
    "what level of volume or fund-flow recovery counts as improvement (e.g., 'volume must reach 1.3x the 20-day average of N shares'), " +
    "what specific macro, style, or structure catalyst confirmation would justify adding, holding, reducing, rotating, or exiting (e.g., rate decision dates, index rebalancing windows, fund-flow thresholds), " +
    "and what ETF structure checks matter (e.g., share change magnitude, premium-discount deviation percentage, tracking error, top-10 holdings concentration percentage). " +
    "Write these sections as full analytical paragraphs with explicit thresholds and trigger conditions. " +
    "If you cannot cite concrete price levels, moving-average values, volume baselines, or ETF share / premium-discount data from the reports above, do not issue add, reduce, or rebuild instructions."
  );
}

export function buildTraderSystemMessage(ctx: PromptContext): string {
  return (
    "You are an ETF allocation strategist analyzing market data to make ETF exposure decisions. " +
    "Provide a clear allocation thesis, an execution plan, and explicit rebalance and risk controls. " +
    "Your first sentence in each section must state the current base-case view rather than circling around it. " +
    "The three sections must open with DIFFERENT sentences — never use the same or near-identical first sentence across sections. " +
    "In the ETF allocation thesis (section 一), the opening sentence must state WHY the evidence supports this stance (e.g., '当前宏观压制边际缓和、行业盈利改善信号同步出现，偏多逻辑更完整'); do not mention sizing, levels, or execution steps. " +
    "In the execution plan (section 二), the opening sentence must state WHAT to do and at what levels (e.g., '先以目标仓位的20%—30%建立试探仓，价格站回50日均线上方后逐步加仓'); do not restate the thesis rationale. " +
    "In rebalance and risk controls (section 三), focus on failure conditions, rebalance triggers, cut or restore rules, and what must be monitored next; do not repeat the thesis or execution sentence verbatim. " +
    "Do not stack multiple rating labels with different wording. " +
    "If you mention timing in Chinese output, translate it as 时机 or 节奏 instead of leaving the English word. " +
    "For ordinary lists, use Arabic numerals such as 1. 2. 3.; if you use Chinese section headings, keep forms like 一、二、三. " +
    `${STRUCTURED_FIELD_POPULATION_INSTRUCTION} ` +
    `${STRUCTURED_TRIGGER_METRICS_INSTRUCTION} ` +
    `${STRUCTURED_FIELD_VISIBILITY_INSTRUCTION} ` +
    `${traderDetailInstruction(ctx)} ` +
    `${getLocalizedExecutionBiasInstruction(ctx)}` +
    getAgentOutputSchemaInstruction("trader", ctx, "afterExecutionBias") +
    getLanguageInstruction(ctx)
  );
}

export function buildTraderContextMessage(opts: {
  asset: string;
  instrumentContext: string;
  structuredSignals?: string;
  researchPlan: string;
  marketFlowReport: string;
  catalystSentimentReport: string;
  macroRegimeReport: string;
  mesoCommodityReport: string;
  holdingsIndustryReport: string;
  topHoldingsReport: string;
}): string {
  return (
    `Based on a comprehensive analysis by a team of analysts, here is an ETF allocation view tailored for ${opts.asset}. ` +
    `${opts.instrumentContext} ` +
    "This view incorporates insights from current technical market trends, macroeconomic indicators, commodity signals, " +
    "market flows, event-driven sentiment, industry structure, and constituent-level research. " +
    "Use this view as a foundation for evaluating your next ETF allocation decision. " +
    "When an upstream block contains `决策信号摘要` or `Decision Signal Summary`, treat that block as the highest-priority summary and use the surrounding report excerpt only as supporting evidence.\n\n" +
    (opts.structuredSignals?.trim()
      ? `${opts.structuredSignals.trim()}\n\nUse these structured signals as the machine-readable state snapshot; use the report excerpts below to verify evidence and thresholds.\n\n`
      : "") +
    `Proposed Allocation View: ${opts.researchPlan}\n\n` +
    `Macro regime analysis: ${opts.macroRegimeReport}\n` +
    `Meso commodity analysis: ${opts.mesoCommodityReport}\n` +
    `Market and flow analysis: ${opts.marketFlowReport}\n` +
    `Sentiment and catalyst impact analysis: ${opts.catalystSentimentReport}\n` +
    `ETF holdings-industry research: ${opts.holdingsIndustryReport}\n` +
    `ETF top holdings research: ${opts.topHoldingsReport}\n\n` +
    "Leverage these insights to make an informed and disciplined ETF allocation decision."
  );
}

/**
 * Strip structured-output-only sentences from a system message so the
 * free-text fallback prompt does not surface field names in prose.
 *
 * Mirrors ``_strip_structured_only_text`` in structured.py.
 */
export function stripStructuredOnlyText(text: string): string {
  const sentences = [
    STRUCTURED_FIELD_POPULATION_INSTRUCTION,
    STRUCTURED_TRIGGER_METRICS_INSTRUCTION,
    STRUCTURED_FIELD_VISIBILITY_INSTRUCTION,
  ];
  let cleaned = text || "";
  for (const sentence of sentences) {
    cleaned = cleaned.split(sentence).join("");
  }
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  cleaned = cleaned.replace(/[ \t]{2,}/g, " ");
  return cleaned.trim();
}
