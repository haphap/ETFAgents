/**
 * Shared prompt-instruction helpers ported from
 * ``etfagents/agents/utils/agent_utils.py`` and ``report_leads.py``.
 *
 * Path A scope: language-aware string constants only. The complex
 * post-processing helpers (``pre_judge_clean``, ``post_judge_clean``,
 * ``normalize_chinese_role_terms``, ``has_invalid_opening_cap``,
 * ``collect_top_section_marks`` etc.) are deferred to sub-step 2.
 */

import { isChinese } from "../schemas/rating.js";

export interface PromptContext {
  /** Output language from bridge config — `"Chinese"` or `"English"`. */
  language: string;
  /**
   * Character cap for context fields when included in prompts.
   * Mirrors ``report_context_char_limit`` in DEFAULT_CONFIG.
   */
  reportContextCharLimit?: number;
  /**
   * Validation/refine mode for analyst reports.
   * Mirrors ``validation_mode`` in ``DEFAULT_CONFIG``. Default
   * ``static_plus_llm`` runs both regex and LLM-judge passes.
   */
  validationMode?: "disabled" | "static_only" | "static_plus_llm" | "llm_only";
}

const DEFAULT_REPORT_CHAR_LIMIT = 16_000;

export function truncateForPrompt(text: string | undefined, ctx: PromptContext): string {
  if (!text) return "";
  const limit = ctx.reportContextCharLimit ?? DEFAULT_REPORT_CHAR_LIMIT;
  if (limit <= 0 || text.length <= limit) return text;
  const omitted = text.length - limit;
  return `[Content trimmed, omitted ${omitted} characters]\n${text.slice(-limit)}`;
}

/** Collapse 3+ consecutive newlines into 2. Mirrors collapse_blank_lines. */
export function collapseBlankLines(text: string | undefined): string {
  if (!text) return "";
  const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  return normalized.replace(/\n([ \t]*\n){2,}/g, "\n\n").trim();
}

export function getLanguageInstruction(ctx: PromptContext): string {
  const lang = ctx.language ?? "English";
  if (lang.trim().toLowerCase() === "english") return "";
  return (
    ` Write your entire response in ${lang}.` +
    " Translate mixed English finance terms into Chinese as well, including items such as" +
    " Capex, Forward PE, quarterly earnings, and scalability." +
    " Follow Chinese publishing number style: use Arabic numerals for dates, times," +
    " percentages, prices, quantities, ticker symbols, securities codes, model numbers," +
    " and other codes/serial numbers; keep approximate expressions such as" +
    " '三四个月', '十余次', '一千多件', and '约三千名' in Chinese unless a local" +
    " statistical comparison clearly requires Arabic numerals. For very large currency" +
    " figures written in Arabic numerals, rescale raw `元/美元/港元` amounts into" +
    " `万` or `亿` units when that produces a clean, publication-style expression" +
    " (e.g. `300000000000元` -> `3000亿元`). In visible Chinese prose, replace raw" +
    " technical-indicator parameter keys such as `close_10_ema`, `boll_ub`, and" +
    " `vwma` with reader-friendly labels such as `10日EMA`, `布林带上轨`, and" +
    " `成交量加权移动平均线`." +
    " Use Chinese official-document heading hierarchy numbering throughout the report:" +
    " first level 一、二、三、; second level （一）（二）（三）; third level 1. 2. 3.;" +
    " fourth level (1) (2) (3); fifth level ① ② ③. " +
    " Keep paragraphs distinct and numbering consistent from start to finish."
  );
}

export function getCollaborationStopInstruction(ctx: PromptContext): string {
  if (isChinese(ctx.language)) {
    return (
      " 如果你或其他助手已经给出了最终结论，请在响应中包含：" +
      "'最终配置建议: **买入/增持/持有/减持/卖出**'，团队将以此为停止信号。"
    );
  }
  return (
    " If you or any other assistant has the FINAL ALLOCATION PROPOSAL: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL** or deliverable," +
    " prefix your response with FINAL ALLOCATION PROPOSAL: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL** so the team knows to stop."
  );
}

export function getLocalizedExecutionBiasInstruction(ctx: PromptContext): string {
  if (isChinese(ctx.language)) {
    return (
      "以明确的执行倾向结束，最后一行必须使用格式：" +
      "'执行倾向: **买入/增持/持有/减持/卖出**'。" +
      "这里表达的是交易执行层的倾向，不要冒充最终投资组合决策。"
    );
  }
  return (
    "End with a clear execution-bias line and always conclude your response with " +
    "'EXECUTION BIAS: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL**'. " +
    "This is an execution-layer stance, not the final portfolio decision."
  );
}

export function getNoTitleInstruction(): string {
  return (
    " Do NOT write a report title or H1 heading. Begin with a 2-4 sentence overview paragraph before section one. " +
    "For Chinese reports, write that overview before the first '一、' section; never start directly with '一、', '（一）', a bullet list, or a table. " +
    "Do NOT repeat the report subject as a standalone title-like line anywhere in the body, and never construct pseudo-titles from only SH / SZ / HK / BJ or similar exchange suffixes."
  );
}

export function getTopicAndTermStyleInstruction(): string {
  return (
    " Make the opening sentence concise and thesis-led, with the same sharpness a strong title would have, rather than using generic scene-setting. " +
    "Do NOT start the opening paragraph with a standalone conclusion label such as '结论：偏多' or '结论：偏空' — weave the directional stance into the body of the paragraph naturally. " +
    "Do NOT use '（导语）' as a label before introductory paragraphs. " +
    "When explaining technical terms, weave the explanation into the sentence where the term first appears without parentheses — " +
    "do NOT write inline parenthetical definitions such as '10日EMA（指数移动平均线，...）', " +
    "and do NOT collect multiple term definitions into a single parenthetical block such as '（附首次出现关键术语的白话解释：...）' or '（关键术语交易含义速览：...）'. " +
    "In Chinese output, do NOT lean on a single repeated word such as '反噬'; vary the wording with precise alternatives like '利润挤压', '成本倒逼', '负反馈', '传导受阻', or '盈利受压' when the context fits."
  );
}

export function getConciseHeadingInstruction(): string {
  return (
    " Top-level and second-level headings must be concise, specific, and point directly to the content of that section. " +
    "You MUST use the exact section headings specified in the report structure above. " +
    "Do NOT substitute generic labels such as '总体研判', '深度分析', '风险与催化', or '总结' " +
    "when the structure already provides a precise heading for that section. " +
    "If the structure does not provide a heading, write one that is brief, forceful, and immediately usable. " +
    "In Chinese output, top-level and second-level headings must stay in plain Chinese and must NOT append English translations or notes in parentheses. " +
    "Do NOT output code blocks, JSON, dictionary mappings, variable assignments, or any programming-language structure. " +
    "Each heading should appear directly in the report as readable text, not as configuration. " +
    "Use '一、' for top-level headings and '（一）' for second-level headings."
  );
}

export function getNoProcessNarrationInstruction(): string {
  // Mirrors etfagents.report_prompt_utils.get_no_process_narration_instruction.
  return (
    " Do NOT begin your reply with process narration such as 'Now let me', 'Next', " +
    "'I will', 'I can now', '现在我来', '接下来', '下面', '我将', '我可以开始', or any " +
    "status update describing what you are about to do. Begin immediately with the " +
    "report's opening overview paragraph."
  );
}

export function buildInstrumentContext(ticker: string): string {
  // Path A: omit local company-name lookup. Sub-step 2 will plumb a name resolver.
  return (
    `The instrument to analyze is \`${ticker}\`. ` +
    "Use this exact ticker in every tool call, report, and recommendation, " +
    "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`). " +
    "Never spell ticker digits in Chinese and never replace `.` with `点`."
  );
}

export function dateDaysBefore(currDate: string, days: number): string {
  const parsed = Date.parse(`${currDate}T00:00:00Z`);
  if (Number.isNaN(parsed)) return currDate;
  const shifted = new Date(parsed - days * 86_400_000);
  const yyyy = shifted.getUTCFullYear();
  const mm = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(shifted.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
