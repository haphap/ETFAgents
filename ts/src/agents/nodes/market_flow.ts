/**
 * etf_market_analyst node — sub-step 2.1 wiring.
 *
 * Replaces the path-A inline single-invoke with the faithful
 * ``runToolReportChain`` port: process-narration extraction, multi-stage
 * fallback retries, and the unexecuted-tool-intent recovery payload list.
 *
 * Still deferred (sub-step 2.2 / 2.4):
 *   - validate_and_refine LLM-judge gate
 *   - normalize_chinese_role_terms / pre_judge_clean / post_judge_clean
 *   - _normalize_market_flow_tail_sections
 *   - _looks_like_complete_market_flow_report acceptance
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BaseMessage } from "@langchain/core/messages";
import { AIMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import type { StructuredToolInterface } from "@langchain/core/tools";
import {
  looksLikeCompleteMarketFlowReport,
  normalizeMarketFlowTailSections,
} from "../helpers/market_flow_normalize.js";
import { buildMemoryPromptSection, injectMemoryPromptSection } from "../helpers/memory.js";
import { postJudgeClean, preJudgeClean } from "../helpers/report_leads.js";
import { normalizeChineseRoleTerms } from "../helpers/role_terms.js";
import {
  buildFinalReportFallback,
  buildRecoveryInstruction,
  runToolReportChain,
  type SystemMessagePhase,
  type UnexecutedToolRecovery,
} from "../helpers/tool_report_chain.js";
import { type AnalystReportSpec, validateAndRefine } from "../helpers/validate_refine.js";
import { buildMarketFlowSystemMessage, ETF_MARKET_INDICATORS } from "../prompts/market_flow.js";
import {
  buildInstrumentContext,
  dateDaysBefore,
  getCollaborationStopInstruction,
  type PromptContext,
} from "../prompts/shared.js";
import type { SpineStateType, SpineStateUpdate } from "../state.js";

export interface AnalystNodeOptions {
  llm: BaseChatModel;
  tools: ReadonlyArray<StructuredToolInterface>;
  promptContext: PromptContext;
}

/**
 * Validation contract for the market_flow analyst — mirrors
 * ``etfagents.agents.analysts.etf_market_analyst._REPORT_SPEC``.
 */
const MARKET_FLOW_REPORT_SPEC: AnalystReportSpec = {
  analystName: "market_flow",
  requiredTopSections: ["一", "二", "三", "四"],
  requiredIndicatorTokens: ["MACD", "RSI"],
  requiredTailTokens: ["综合结论和指标总览"],
  requireTailTable: true,
  customRulesMarkdown:
    "### 内容覆盖\n" +
    "- 是否包含四个一级章节：一、市场结构与量价诊断；二、交易确认与执行计划；三、关键价位与条件情景推演；四、综合结论和指标总览？\n" +
    "- 每个分析章节（一、二、三）标题后是否直接写2-3句结论段，先给方向、证据和交易含义？\n" +
    "- 是否覆盖趋势指标（SMA/EMA）、动量（MACD）、超买超卖（RSI）、波动率（Bollinger）和量能确认（VWMA）？\n" +
    "- 是否结合份额变化、NAV溢价/折价和换手率分析资金积累/分配/拥挤状态？\n" +
    "- 第三部分是否使用连贯段落而非标签式清单？\n" +
    "- 第四部分是否在“综合结论和指标总览”一级标题下整合配置方向、关键价位、资金状态与指标总览表？\n" +
    "- 指标总览表是否包含指标、数值、位置、交易含义和关键阈值五列？",
};

export function createMarketFlowNode(opts: AnalystNodeOptions) {
  return async function marketFlowNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const tradeDate = state.trade_date;
    const instrumentContext = buildInstrumentContext(ticker);
    const analystBody = buildMarketFlowSystemMessage(opts.promptContext);
    const toolNames = opts.tools.map((t) => t.name).join(", ");

    const buildSystemMessage = (phase: SystemMessagePhase): string => {
      let body = analystBody;
      if (phase.kind === "fallback") {
        body = `${body}${buildFinalReportFallback(opts.promptContext.language)}`;
      } else if (phase.kind === "recovery") {
        body = `${body}${buildRecoveryInstruction()}`;
      }
      const baseFrame = assembleSystemFrame({
        ctx: opts.promptContext,
        currentDate: tradeDate,
        instrumentContext,
        toolNames,
        analystSystemMessage: body,
      });
      // Inject memory context (graceful no-op when memory is empty).
      const memorySection = buildMemoryPromptSection(
        state,
        { role: "etf_market_analyst" },
        opts.promptContext.language,
      );
      return injectMemoryPromptSection(baseFrame, memorySection);
    };

    const baseMessages = state.messages as BaseMessage[];
    const recovery = buildRecoveryConfig({
      ticker,
      currentDate: tradeDate,
      tools: opts.tools,
    });

    const { result, report } = await runToolReportChain({
      llm: opts.llm,
      tools: opts.tools,
      baseMessages,
      buildSystemMessage,
      ...(recovery ? { unexecutedToolRecovery: recovery } : {}),
      acceptanceCheck: looksLikeCompleteMarketFlowReport,
      rejectedReportFallback: "last_attempt",
      language: opts.promptContext.language,
    });

    if ((result.tool_calls ?? []).length > 0) {
      // Tool routing — graph re-enters this node after the ToolNode runs.
      return { messages: [result] };
    }

    // Sub-step 2.2 + 2.3 + 2.4 cleanup chain. Order mirrors Python:
    //   normalizeChineseRoleTerms
    //     → preJudgeClean
    //     → validateAndRefine
    //     → postJudgeClean
    //     → normalizeMarketFlowTailSections (market_flow specific)
    //     → strict acceptance check (warn if still failing)
    let cleaned = report;
    if (cleaned) {
      cleaned = normalizeChineseRoleTerms(cleaned);
      cleaned = preJudgeClean(cleaned);
      cleaned = await validateAndRefine(cleaned, opts.llm, MARKET_FLOW_REPORT_SPEC, {
        ...(opts.promptContext.validationMode
          ? { validationMode: opts.promptContext.validationMode }
          : {}),
      });
      cleaned = postJudgeClean(cleaned);
      cleaned = normalizeMarketFlowTailSections(cleaned);
      if (cleaned && !looksLikeCompleteMarketFlowReport(cleaned)) {
        // Mirrors Python's logger.warning: keep the cleaned draft but surface
        // that the strict acceptance gate is still not satisfied.
        console.warn(
          "[market_flow] report failed strict acceptance after retries; keeping last cleaned draft.",
        );
      }
    }

    return {
      messages: [cleaned ? new AIMessage(cleaned) : result],
      market_flow_report: cleaned,
    };
  };
}

export function assembleSystemFrame(args: {
  ctx: PromptContext;
  currentDate: string;
  instrumentContext: string;
  toolNames: string;
  analystSystemMessage: string;
}): string {
  return (
    "You are a helpful AI assistant, collaborating with other assistants." +
    " Use the provided tools to progress towards answering the question." +
    " If you are unable to fully answer, that's OK; another assistant with different tools" +
    " will help where you left off. Execute what you can to make progress." +
    getCollaborationStopInstruction(args.ctx) +
    ` You have access to the following tools: ${args.toolNames}.\n${args.analystSystemMessage}` +
    ` For your reference, the current date is ${args.currentDate}. ${args.instrumentContext}`
  );
}

function buildRecoveryConfig(args: {
  ticker: string;
  currentDate: string;
  tools: ReadonlyArray<StructuredToolInterface>;
}): UnexecutedToolRecovery | null {
  const byName = new Map(args.tools.map((t) => [t.name, t] as const));
  const indicatorIds = ETF_MARKET_INDICATORS.map(([id]) => id).join(",");

  const candidates: Array<{
    name: string;
    payload: Record<string, unknown>;
  }> = [
    {
      name: "get_etf_price_data",
      payload: {
        symbol: args.ticker,
        start_date: dateDaysBefore(args.currentDate, 180),
        end_date: args.currentDate,
      },
    },
    {
      name: "get_etf_indicators",
      payload: {
        symbol: args.ticker,
        indicator: indicatorIds,
        curr_date: args.currentDate,
        look_back_days: 180,
      },
    },
    {
      name: "get_etf_share",
      payload: { ticker: args.ticker, curr_date: args.currentDate },
    },
    {
      name: "get_etf_nav",
      payload: { ticker: args.ticker, curr_date: args.currentDate },
    },
    {
      name: "get_etf_universe",
      payload: { curr_date: args.currentDate, limit: 20 },
    },
  ];

  const toolPayloads: Array<{
    tool: StructuredToolInterface;
    payload: Record<string, unknown>;
  }> = [];
  for (const { name, payload } of candidates) {
    const tool = byName.get(name);
    if (tool) toolPayloads.push({ tool, payload });
  }
  if (toolPayloads.length === 0) return null;
  return {
    triggerToolNames: args.tools.map((t) => t.name),
    toolPayloads,
  };
}

// Re-export so the legacy mini_spine import keeps working.
export type { SystemMessagePhase } from "../helpers/tool_report_chain.js";

// Helpers used in tests
export const __test__ = { assembleSystemFrame, buildRecoveryConfig };

// Suppress unused-import lint warnings — these are part of the public API
// surface used elsewhere in src/ but TS doesn't flag the re-import otherwise.
void HumanMessage;
void SystemMessage;
