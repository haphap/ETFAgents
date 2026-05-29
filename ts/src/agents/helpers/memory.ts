/**
 * Memory prompt injection helpers (read path).
 *
 * Port of ``etfagents.agents.utils.analysis_memory`` read-side:
 *   - buildMemoryPromptSection / injectMemoryPromptSection
 *   - getMemoryUsageInstruction / _lookupRoleContext
 *
 * Sub-step 2.7 ports the prompt injection layer. Memory context is read
 * from LangGraph state (populated by Python's AnalysisMemoryStore in
 * sub-step 4). When no context is available, returns empty string — the
 * caller gracefully omits the memory section.
 */

import type { SpineStateType } from "../state.js";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface MemoryRoleConfig {
  /** Primary role name used as the state key (e.g. "etf_market_analyst"). */
  role: string;
  /** Fallback role names to try if the primary key is absent. */
  aliases?: string[];
}

/**
 * Build the memory prompt section for a role, reading pre-built context
 * dicts from state. Returns "" when no memory is available.
 */
export function buildMemoryPromptSection(
  state: SpineStateType,
  role: MemoryRoleConfig,
  language: string,
): string {
  const roles = [role.role, ...(role.aliases ?? [])];

  const continuity = lookupRoleContext(state, "continuity_context" as keyof SpineStateType, roles);
  const lesson = lookupRoleContext(state, "lesson_context" as keyof SpineStateType, roles);
  const method = lookupRoleContext(state, "method_context" as keyof SpineStateType, roles);

  const isChinese = language === "Chinese";
  const labels = {
    continuity: isChinese
      ? "最近一次同标的分析摘要（仅供内部吸收，不要照抄到可见答案中）"
      : "Latest same-ticker analysis brief (internal only; do not quote verbatim)",
    lesson: isChinese
      ? "已验证历史复盘（仅供内部吸收，不要照抄到可见答案中）"
      : "Resolved historical lessons (internal only; do not quote verbatim)",
    method: isChinese
      ? "可复用分析方法提醒（仅供内部吸收，不要照抄到可见答案中）"
      : "Reusable analysis-method reminders (internal only; do not quote verbatim)",
  };

  const blocks: string[] = [];
  if (continuity) blocks.push(`**${labels.continuity}:**\n${continuity}`);
  if (lesson) blocks.push(`**${labels.lesson}:**\n${lesson}`);
  if (method) blocks.push(`**${labels.method}:**\n${method}`);

  const block = blocks.join("\n\n").trim();
  if (!block) return "";

  return `${block}\n\n${getMemoryUsageInstruction(language)}`;
}

/**
 * Prepend the memory section to the system message. Returns the system
 * message unchanged when the memory section is empty.
 */
export function injectMemoryPromptSection(systemMessage: string, memorySection: string): string {
  if (!memorySection) return systemMessage;
  return `${memorySection}\n\n${systemMessage}`.trim();
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

function lookupRoleContext(
  state: SpineStateType,
  contextKey: keyof SpineStateType,
  roles: string[],
): string {
  const dict = state[contextKey];
  if (!dict || typeof dict !== "object") return "";
  const record = dict as Record<string, unknown>;
  for (const role of roles) {
    const value = record[role];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function getMemoryUsageInstruction(language: string): string {
  if (language === "Chinese") {
    return (
      "若提供了最近一次分析摘要、历史复盘或方法提醒，必须先独立基于当前证据完成判断，再明确说明哪些前提延续、哪些变化、哪些失效。" +
      "上次结论仅作对照，不应成为本次结论的默认起点；不得机械复述旧记忆。" +
      "记忆不能替代本轮数据获取；若当前任务要求调用工具，必须发出结构化工具调用，" +
      "不得在可见答案中写'我将调用/接下来调用/准备调用某工具'等过程性承诺。"
    );
  }
  return (
    "If prior analysis, lessons, or method reminders are provided, first reason independently from current evidence, then explain what still holds, what changed, and what is invalidated. " +
    "Treat prior conclusions as checkpoints rather than the default answer, and do not mechanically restate memory text. " +
    "Memory never replaces fresh data retrieval; when the current task requires tools, emit structured tool calls and do not write visible process promises such as 'I will call' or 'I am going to use' a tool."
  );
}
