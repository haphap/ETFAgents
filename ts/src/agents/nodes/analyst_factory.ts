/**
 * Shared analyst node factory — every analyst shares the same
 * tool-report-chain + validate-and-refine pipeline.
 *
 * Sub-step 3 extracts the boilerplate from market_flow.ts so each
 * analyst only supplies its prompt, tools, spec, and acceptance check.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { BaseMessage } from "@langchain/core/messages";
import { AIMessage } from "@langchain/core/messages";
import type { StructuredToolInterface } from "@langchain/core/tools";
import type { MemoryRoleConfig } from "../helpers/memory.js";
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
import { buildInstrumentContext, type PromptContext } from "../prompts/shared.js";
import type { SpineStateType, SpineStateUpdate } from "../state.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export interface AnalystConfig {
  /** Human-readable name used in log messages. */
  name: string;
  /** State key the analyst writes its report to. */
  stateKey: keyof SpineStateType;
  /** Build the analyst's system message body. */
  buildSystemBody: (ctx: PromptContext) => string;
  /** Tools available to this analyst. */
  tools: ReadonlyArray<StructuredToolInterface>;
  /** Validation contract (null to skip validate-and-refine). */
  reportSpec: AnalystReportSpec | null;
  /** Memory role configuration. */
  memoryRole: MemoryRoleConfig;
  /**
   * Optional explicit context block appended to the system message (e.g. the
   * six analyst reports + opposing debate history for debators/managers).
   * Mirrors the Python nodes that embed reports directly in the prompt rather
   * than relying solely on accumulated message history.
   */
  buildContextBlock?: (state: SpineStateType) => string;
  /**
   * Whether to append the report to the message history (default true). Debate
   * and manager nodes set this false: they read explicit context blocks and
   * must not grow the shared message history (Python parity).
   */
  appendMessage?: boolean;
  /** Report acceptance check (return true when quality threshold is met). */
  acceptanceCheck?: (report: string) => boolean;
  /** Unexecuted-tool recovery configuration. */
  unexecutedToolRecovery?: UnexecutedToolRecovery;
  /** Optional analyst-specific post-processing before validate-and-refine. */
  postProcess?: (report: string, ctx: PromptContext) => string;
}

/** Standard state fields pushed into every analyst's system-frame template. */
export interface SystemFrameArgs {
  ctx: PromptContext;
  currentDate: string;
  instrumentContext: string;
  toolNames: string;
  analystSystemMessage: string;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createAnalystNode(
  llm: BaseChatModel,
  promptContext: PromptContext,
  config: AnalystConfig,
  /** Callback that assembles the full system frame (common prefix + analyst body). */
  assembleSystemFrame: (args: SystemFrameArgs) => string,
) {
  return async function analystNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const tradeDate = state.trade_date;
    const instrumentContext = buildInstrumentContext(ticker);
    const ctx = promptContext;
    const analystBody = config.buildSystemBody(ctx);
    const toolNames = config.tools.map((t) => t.name).join(", ");
    // Explicit reports/debate context (debators & managers), built from state.
    const contextBlock = config.buildContextBlock?.(state) ?? "";

    const buildSystemMessage = (phase: SystemMessagePhase): string => {
      let body = analystBody;
      if (contextBlock) {
        body = `${body}\n\n${contextBlock}`;
      }
      if (phase.kind === "fallback") {
        body = `${body}${buildFinalReportFallback(ctx.language)}`;
      } else if (phase.kind === "recovery") {
        body = `${body}${buildRecoveryInstruction()}`;
      }
      const baseFrame = assembleSystemFrame({
        ctx,
        currentDate: tradeDate,
        instrumentContext,
        toolNames,
        analystSystemMessage: body,
      });
      // Inject memory context (graceful no-op when memory is empty).
      const memorySection = buildMemoryPromptSection(state, config.memoryRole, ctx.language);
      return injectMemoryPromptSection(baseFrame, memorySection);
    };

    const baseMessages = state.messages as BaseMessage[];

    const { result, report } = await runToolReportChain({
      llm,
      tools: config.tools,
      baseMessages,
      buildSystemMessage,
      ...(config.acceptanceCheck ? { acceptanceCheck: config.acceptanceCheck } : {}),
      ...(config.unexecutedToolRecovery
        ? { unexecutedToolRecovery: config.unexecutedToolRecovery }
        : {}),
      rejectedReportFallback: "last_attempt" as const,
      language: ctx.language,
    });

    // Tool routing: when the model emitted tool calls, surface that message so
    // the graph can route to the ToolNode and re-enter this analyst with the
    // tool results appended. Mirrors the market_flow node's handling — without
    // this the bound tools are never executed and the report comes back empty.
    if ((result.tool_calls ?? []).length > 0) {
      return { messages: [result] } as SpineStateUpdate;
    }

    // --- Post-processing pipeline ---
    let processedReport = report;
    if (processedReport) {
      processedReport = normalizeChineseRoleTerms(processedReport);
      processedReport = preJudgeClean(processedReport);
      if (config.postProcess) {
        processedReport = config.postProcess(processedReport, ctx);
      }
      if (config.reportSpec) {
        const refined = await validateAndRefine(processedReport, llm, config.reportSpec);
        if (refined) processedReport = refined;
      }
      processedReport = postJudgeClean(processedReport);
    }

    const stateUpdate: Record<string, unknown> = {};
    stateUpdate[config.stateKey as string] = processedReport;
    // Analysts append their report to the message history so the next analyst /
    // tool round sees it; debate & manager nodes opt out (appendMessage: false)
    // since they read explicit context blocks instead, matching Python (their
    // nodes return only debate-state / plan fields, not chat messages).
    if (config.appendMessage !== false) {
      stateUpdate.messages = [new AIMessage(processedReport)];
    }

    return stateUpdate as SpineStateUpdate;
  };
}
