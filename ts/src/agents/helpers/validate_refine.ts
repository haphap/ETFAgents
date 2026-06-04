/**
 * Self-critique + refine pipeline for analyst reports.
 *
 * Faithful port of ``etfagents.agents.utils.validate_refine``:
 *
 *   1. Static validation (cheap regex / substring checks driven by ``AnalystReportSpec``)
 *   2. LLM judge (best-effort JSON via free-text channel; tolerant parse)
 *   3. Refine (only when verdict reports issues, ``score < threshold``)
 *
 * Validation mode: ``static_only`` / ``static_plus_llm`` (default) /
 * ``llm_only`` / ``disabled``. Reads from ``promptContext.validationMode``
 * when not explicitly overridden.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { type AIMessage, type BaseMessage, HumanMessage } from "@langchain/core/messages";
import { z } from "zod";
import { extractDecisionSignalSummary } from "../prompts/shared.js";
import { extractTextContent } from "./content.js";
import {
  collectTopSectionMarks,
  containsMetaOpeners,
  containsQaLabelArtifacts,
  containsSelfReferentialMetaLeads,
  findTopSectionsMissingLeads,
  startsWithoutOverviewParagraph,
} from "./report_leads.js";
import { TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX } from "./tool_report_chain.js";

// --------------------------------------------------- spec / verdict types

export interface AnalystReportSpec {
  analystName: string;
  /** Top-level section markers that must appear, e.g. ``["一", "二", "三"]``. */
  requiredTopSections?: ReadonlyArray<string>;
  /** Case-insensitive substrings that must appear somewhere in the report. */
  requiredIndicatorTokens?: ReadonlyArray<string>;
  /** Substrings expected near the end of the report (table headers, etc.). */
  requiredTailTokens?: ReadonlyArray<string>;
  /** Whether every required top-level section must include a prose lead. */
  requireTopSectionLeads?: boolean;
  /** Subset of required top-level marks that must include a prose lead. */
  leadRequiredTopSections?: ReadonlyArray<string>;
  /** Whether a Markdown table (``| --- |`` separator) must exist in the tail. */
  requireTailTable?: boolean;
  /** Whether the report must end with a decision-oriented signal summary. */
  requireDecisionSignalSummary?: boolean;
  /** Free-form rules forwarded verbatim to the LLM judge prompt. */
  customRulesMarkdown?: string;
}

export interface StaticVerdict {
  criticalIssues: string[];
  missingElements: string[];
}

export function staticVerdictHasIssues(v: StaticVerdict): boolean {
  return v.criticalIssues.length > 0 || v.missingElements.length > 0;
}

export const JudgeVerdictSchema = z.object({
  score: z.number().int().min(0).max(10).default(0),
  passed: z.boolean().default(false),
  critical_issues: z.array(z.string()).default([]),
  minor_issues: z.array(z.string()).default([]),
  missing_elements: z.array(z.string()).default([]),
  general_comment: z.string().default(""),
});
export type JudgeVerdict = z.infer<typeof JudgeVerdictSchema>;

export type ValidationMode = "disabled" | "static_only" | "static_plus_llm" | "llm_only";

const VALID_MODES: ReadonlySet<string> = new Set([
  "disabled",
  "static_only",
  "static_plus_llm",
  "llm_only",
]);

function resolveValidationMode(value: string | undefined): ValidationMode {
  const mode = (value ?? "static_plus_llm").trim().toLowerCase();
  return (VALID_MODES.has(mode) ? mode : "static_plus_llm") as ValidationMode;
}

// ----------------------------------------------- static validation core

const MARKDOWN_H1_RE = /^[ \t]*#\s+\S/m;
const MARKDOWN_H2_RE = /^[ \t]*##\s+\S/m;
const MARKDOWN_TABLE_SEPARATOR_RE = /^\|(?:\s*:?-{3,}:?\s*\|)+\s*$/m;
const DECISION_SIGNAL_FIELDS: ReadonlyArray<ReadonlyArray<string>> = [
  ["方向", "Direction"],
  ["置信度", "Confidence"],
  ["时间窗口", "Time Window"],
  ["ETF传导路径", "ETF Transmission Path"],
  ["核心证据", "Core Evidence"],
  ["最大反证条件", "Main Invalidation"],
  ["配置含义", "Allocation Implication"],
  ["下一步观察", "Next Watch Items"],
];

function bodyWithoutDecisionSignalSummary(report: string): string {
  let bestIdx = -1;
  for (const marker of ["决策信号摘要", "Decision Signal Summary"]) {
    const idx = report.lastIndexOf(marker);
    if (idx > bestIdx) bestIdx = idx;
  }
  return bestIdx >= 0 ? report.slice(0, bestIdx) : report;
}

export function staticValidate(report: string, spec: AnalystReportSpec): StaticVerdict {
  const verdict: StaticVerdict = { criticalIssues: [], missingElements: [] };
  if (!report) return verdict;

  const requiresNumberedReport = (spec.requiredTopSections?.length ?? 0) > 0;
  const sectionMarks = collectTopSectionMarks(report);
  for (const need of spec.requiredTopSections ?? []) {
    if (!sectionMarks.has(need)) {
      verdict.missingElements.push(`缺少一级章节『${need}、…』`);
    }
  }

  if (spec.requireTopSectionLeads) {
    const leadMarks = spec.leadRequiredTopSections ?? spec.requiredTopSections ?? [];
    for (const mark of findTopSectionsMissingLeads(report, leadMarks)) {
      verdict.missingElements.push(`一级章节『${mark}、…』缺少标题后的结论段`);
    }
  }

  if (MARKDOWN_H1_RE.test(report)) {
    verdict.criticalIssues.push("出现 markdown # H1 标题（应改为正文或中文一级编号）");
  }
  if (requiresNumberedReport && MARKDOWN_H2_RE.test(report)) {
    verdict.criticalIssues.push("出现 markdown ## 二级标题（应使用 中文『（一）』格式）");
  }
  if (requiresNumberedReport && startsWithoutOverviewParagraph(report)) {
    verdict.criticalIssues.push("缺少开篇概述帽段，报告直接以标题、章节、列表或表格开头");
  }

  const lowered = report.toLowerCase();
  for (const token of spec.requiredIndicatorTokens ?? []) {
    if (!lowered.includes(token.toLowerCase())) {
      verdict.missingElements.push(`未覆盖关键指标 / 数据『${token}』`);
    }
  }

  if (spec.requiredTailTokens && spec.requiredTailTokens.length > 0) {
    const tailWindow = report.length > 1500 ? report.slice(-1500) : report;
    for (const tail of spec.requiredTailTokens) {
      if (!tailWindow.includes(tail)) {
        verdict.missingElements.push(`末尾缺少元素『${tail}』`);
      }
    }
  }

  if (spec.requireTailTable) {
    const tailWindow = report.length > 2000 ? report.slice(-2000) : report;
    if (!MARKDOWN_TABLE_SEPARATOR_RE.test(tailWindow)) {
      verdict.missingElements.push("末尾章节缺少指标总览 Markdown 表格");
    }
  }

  if (spec.requireDecisionSignalSummary) {
    const summary = extractDecisionSignalSummary(report);
    if (!summary) {
      verdict.missingElements.push("缺少末尾『决策信号摘要』");
    } else {
      for (const aliases of DECISION_SIGNAL_FIELDS) {
        const hasField = aliases.some(
          (field) => summary.includes(`${field}:`) || summary.includes(`${field}：`),
        );
        if (!hasField) verdict.missingElements.push(`决策信号摘要缺少字段『${aliases[0]}』`);
      }
    }
  }

  const bodyOnly = bodyWithoutDecisionSignalSummary(report);
  if (containsQaLabelArtifacts(bodyOnly)) {
    verdict.criticalIssues.push("出现『判断：』『证据：』『结论：』等标签式结构");
  }
  if (containsSelfReferentialMetaLeads(report)) {
    verdict.criticalIssues.push("出现自指式元叙述（如『本节锁定…』『本部分聚焦…』）");
  }
  if (containsMetaOpeners(report)) {
    verdict.criticalIssues.push("段落以『本报告将…』『This report provides…』等元描述开头");
  }

  return verdict;
}

// -------------------------------------------------- LLM judge prompts

const JUDGE_BASE_RULES =
  "你是一名报告质量审核员。请严格按以下标准评审报告，并以结构化方式返回评审结果。\n\n" +
  "## 通用评审标准\n\n" +
  "### 结构完整性\n" +
  "- 报告是否以2-4句概述段落开头（不得以标题或列表开头）？\n" +
  "- 一级标题是否使用「一、」「二、」「三、」格式，且标题中不得包含英文翻译或括号注释？\n" +
  "- 不得出现连续重复的一级标题。\n" +
  "- 每个一级章节标题后是否直接写2-3句概括性结论段，且结论段高于子章节层面（不重复子章节内容）？\n" +
  "- 当报告结构要求「一、二、三、」中文编号时，不得出现 ## 或其他 markdown 标题格式；经理层辩论结论类报告若提示词明确要求Markdown标题，则按其专属结构评审。\n\n" +
  "### 术语表达\n" +
  "- 必要术语说明是否自然融入分析句子，而不是前置术语表、括号定义、注释块或口径说明？\n" +
  "- 不得用独立术语解释段替代正文中的因果分析。\n\n" +
  "### 可操作性\n" +
  "- 是否把主要信号的配置含义融入正文推理，而不是写成「这意味着什么」「对交易应该怎么做」等问答标签或交易指引块？\n" +
  "- 开篇第一句是否直接陈述核心结论或判断（偏多/偏空/中性及原因），而非「本报告将…」等场景设置？\n\n" +
  "### 决策价值\n" +
  "- 末尾是否包含「决策信号摘要」或「Decision Signal Summary」，且包含方向、置信度、时间窗口、ETF传导路径、核心证据、最大反证条件、配置含义和下一步观察？\n" +
  "- 方向是否明确为偏多/偏空/中性或 bullish/bearish/neutral，而不是含糊描述？\n" +
  "- 配置含义是否落到ETF整体仓位的增持、持有、减持或回避，而不是停留在行业评论或成分股交易？\n" +
  "- 是否至少给出一个能推翻当前判断的反证条件，以及2-3条带数据或来源的核心证据？\n\n" +
  "### 禁止内容\n" +
  "- 一级章节标题后的结论段和段落开头不得使用任何自指式元叙述（「本节锁定…」「本部分聚焦…」等）。\n" +
  "- 不得使用「判断：」「证据：」「关键价位：」「条件情景：」等标签式结构。\n" +
  "- 不得讨论数据源分类噪声、券商标签噪声、搜索错配或检索伪影。\n\n" +
  "### 段落质量\n" +
  "- 连续三个以上裸数据片段后是否有解释性语句？\n" +
  "- 是否避免了「值得注意的是」「深度挂钩」「全面覆盖」等填充语？\n\n";

const JUDGE_OUTPUT_GUIDE =
  "## 评分标准\n" +
  "- 9-10：完全满足所有标准，passed=true\n" +
  "- 7-8：仅有 minor_issues 而无 critical_issues，passed=true\n" +
  "- 6 及以下：存在 critical_issues，passed=false\n" +
  "- 任何结构错误、缺少关键章节、多处无解释术语 → critical_issue → passed=false。\n\n" +
  "## 输出格式\n" +
  "仅输出一个 JSON 对象，不要附带任何前言、标题、markdown 包裹或其他文本。JSON 格式如下：\n" +
  '{"score": <int>, "passed": <bool>, "critical_issues": [<str>, ...], ' +
  '"minor_issues": [<str>, ...], "missing_elements": [<str>, ...], ' +
  '"general_comment": "<str>"}\n';

function buildJudgePrompt(report: string, spec: AnalystReportSpec): string {
  const custom = (spec.customRulesMarkdown ?? "").trim();
  const customBlock = custom ? `## 分析师专属标准\n\n${custom}\n\n` : "";
  return `${JUDGE_BASE_RULES + customBlock + JUDGE_OUTPUT_GUIDE}\n## 评审报告\n\n${report}`;
}

const REFINE_PROMPT_TEMPLATE = (verdictJson: string, report: string): string =>
  "你的报告存在以下问题，请重新生成完整报告以修正所有缺陷。保留原有正确部分，但必须完全满足评审标准。\n\n" +
  "## 评审结果\n\n" +
  `${verdictJson}\n\n` +
  "## 原始报告\n\n" +
  `${report}\n\n` +
  "## 要求\n" +
  "- 重新生成完整报告，不是补丁。\n" +
  "- 逐一修正 critical_issues 中列出的所有问题。\n" +
  "- 补充 missing_elements 中列出的缺失内容。\n" +
  "- 保留原报告中正确的分析和数据。\n" +
  "- 严格遵守所有结构、术语、可操作性和风格要求。\n\n" +
  "直接输出修正后的完整报告，不要附带任何前言或元描述。";

// ------------------------------------------- tolerant JSON-object parser

/**
 * Find every position of `{` and try ``JSON.parse`` on progressively longer
 * substrings. Returns the first balanced object whose payload contains a
 * ``score`` field. Mirrors Python's ``raw_decode`` walk semantics.
 */
export function parseJudgeJson(text: string | undefined): JudgeVerdict | null {
  if (!text) return null;
  for (let start = 0; start < text.length; start++) {
    if (text.charCodeAt(start) !== 0x7b) continue; // '{'
    const payload = tryParseObjectAt(text, start);
    if (!payload) continue;
    if (typeof payload !== "object" || !("score" in payload)) continue;
    // Backward-compat: legacy callers emit ``"pass"`` instead of ``"passed"``.
    const candidate = payload as Record<string, unknown>;
    if ("pass" in candidate && !("passed" in candidate)) {
      candidate.passed = candidate.pass;
      delete candidate.pass;
    }
    const parsed = JudgeVerdictSchema.safeParse(candidate);
    if (parsed.success) return parsed.data;
  }
  return null;
}

function tryParseObjectAt(text: string, start: number): unknown {
  let depth = 0;
  let inString = false;
  let escaping = false;
  for (let cursor = start; cursor < text.length; cursor++) {
    const ch = text[cursor];
    if (inString) {
      if (escaping) {
        escaping = false;
      } else if (ch === "\\") {
        escaping = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) {
        try {
          return JSON.parse(text.slice(start, cursor + 1));
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

// ----------------------------------------------------- public entry

export interface ValidateAndRefineOptions {
  scoreThreshold?: number;
  validationMode?: ValidationMode;
}

async function safeInvoke(llm: BaseChatModel, prompt: string): Promise<string> {
  try {
    const messages: BaseMessage[] = [new HumanMessage(prompt)];
    const response = (await llm.invoke(messages)) as AIMessage;
    return extractTextContent(response.content);
  } catch (err) {
    console.warn(`[validate_refine] LLM invocation failed: ${(err as Error).message}`);
    return "";
  }
}

async function runLlmJudge(
  llm: BaseChatModel,
  report: string,
  spec: AnalystReportSpec,
): Promise<JudgeVerdict | null> {
  const prompt = buildJudgePrompt(report, spec);
  const rendered = await safeInvoke(llm, prompt);
  return parseJudgeJson(rendered);
}

async function runLlmRefine(
  llm: BaseChatModel,
  report: string,
  verdict: JudgeVerdict,
): Promise<string> {
  const verdictJson = JSON.stringify(
    {
      score: verdict.score,
      passed: verdict.passed,
      critical_issues: verdict.critical_issues,
      missing_elements: verdict.missing_elements,
      general_comment: verdict.general_comment,
    },
    null,
    2,
  );
  return safeInvoke(llm, REFINE_PROMPT_TEMPLATE(verdictJson, report));
}

function mergeVerdicts(args: {
  mode: ValidationMode;
  staticVerdict: StaticVerdict;
  llm: JudgeVerdict | null;
  scoreThreshold: number;
}): JudgeVerdict | null {
  const { mode, staticVerdict, llm, scoreThreshold } = args;
  const hasStaticIssues = staticVerdictHasIssues(staticVerdict);

  if (mode === "static_only") {
    if (!hasStaticIssues) {
      return JudgeVerdictSchema.parse({
        score: 10,
        passed: true,
        critical_issues: [],
        missing_elements: [],
        general_comment: "static_only: no structural issues detected",
      });
    }
    return JudgeVerdictSchema.parse({
      score: 4,
      passed: false,
      critical_issues: [...staticVerdict.criticalIssues],
      missing_elements: [...staticVerdict.missingElements],
      general_comment: "static_only: failures detected by structural checks",
    });
  }

  if (!llm) {
    if (hasStaticIssues) {
      return JudgeVerdictSchema.parse({
        score: 4,
        passed: false,
        critical_issues: [...staticVerdict.criticalIssues],
        missing_elements: [...staticVerdict.missingElements],
        general_comment: "llm judge unavailable; relying on static checks",
      });
    }
    return null;
  }

  if (mode === "llm_only") return llm;

  const mergedCritical = Array.from(
    new Set([...llm.critical_issues, ...staticVerdict.criticalIssues]),
  );
  const mergedMissing = Array.from(
    new Set([...llm.missing_elements, ...staticVerdict.missingElements]),
  );
  const passed = llm.passed && !hasStaticIssues && llm.score >= scoreThreshold;
  const score = hasStaticIssues ? Math.min(llm.score, scoreThreshold - 1) : llm.score;
  return {
    score,
    passed,
    critical_issues: mergedCritical,
    minor_issues: [...llm.minor_issues],
    missing_elements: mergedMissing,
    general_comment: llm.general_comment,
  };
}

export async function validateAndRefine(
  report: string,
  llm: BaseChatModel,
  spec: AnalystReportSpec,
  options: ValidateAndRefineOptions = {},
): Promise<string> {
  if (!report?.trim()) return report;
  if (report.trimStart().startsWith(TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX)) return report;

  const mode = resolveValidationMode(options.validationMode);
  if (mode === "disabled") return report;

  const scoreThreshold = options.scoreThreshold ?? 7;
  const staticVerdict =
    mode !== "llm_only"
      ? staticValidate(report, spec)
      : { criticalIssues: [], missingElements: [] };

  const llmVerdict = mode !== "static_only" ? await runLlmJudge(llm, report, spec) : null;

  const finalVerdict = mergeVerdicts({ mode, staticVerdict, llm: llmVerdict, scoreThreshold });
  if (!finalVerdict) return report;
  if (finalVerdict.passed && finalVerdict.score >= scoreThreshold) return report;

  const refined = await runLlmRefine(llm, report, finalVerdict);
  return refined || report;
}
