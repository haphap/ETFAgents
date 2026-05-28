/**
 * Port of the public surface from
 * ``etfagents.agents.utils.report_leads`` that the analyst pipeline relies on.
 *
 * Sub-step 2.2 ports the regex implementations of:
 *   - collectTopSectionMarks
 *   - hasInvalidOpeningCap (with its meta-opener / self-referential detectors)
 *   - stripRefinePreamble
 *   - stripDecisionLabelArtifacts (fixes the leakage observed during sub-step 1
 *     end-to-end verification: "最终配置建议: **持有**" trailing the report)
 *   - stripMetaOpeners / containsMetaOpeners
 *   - stripSelfReferentialMetaLeads / containsSelfReferentialMetaLeads
 *   - preJudgeClean / postJudgeClean orchestrators
 *
 * Deferred (TODO comments mark the orchestrator skip points):
 *   - normalizeBoxedTextWrapping (TUI box edges; rare for our LLM)
 *   - stripQaLabels (judgement / evidence labels)
 *   - stripOpeningTermExplanations / stripInlineTechnicalTermExplanations
 *   - stripReportTitle / ensureH1Title (we use no-title prompt)
 *   - stripDeclarativeQuestionMarks (token-budget cleanup)
 *
 * These deferrals are by design — the bug observed in sub-step 1 is the
 * decision-label leakage, which preJudgeClean now removes, plus a few generic
 * meta opener / self-referential lead patterns that Qwen-style models can emit.
 */

import { collapseBlankLines } from "../prompts/shared.js";
import { looksLikeProcessNarration } from "./process_narration.js";
import { normalizeChineseRoleTerms } from "./role_terms.js";

// ----------------------------------------------------- top-level marks

const TOP_SECTION_MARK_RE = /^[ \t]*([一二三四五六七八九十])、/gm;
const TOP_SECTION_LINE_RE = /^[ \t]*([一二三四五六七八九十]+)、/;

/** Return Chinese top-level section marks present in the report (e.g. {"一","二","三"}). */
export function collectTopSectionMarks(text: string | undefined): Set<string> {
  const marks = new Set<string>();
  if (!text) return marks;
  for (const match of text.matchAll(TOP_SECTION_MARK_RE)) {
    if (match[1]) marks.add(match[1]);
  }
  return marks;
}

/**
 * Detect reports that start with a heading, section, list, or table.
 * Mirrors ``starts_without_overview_paragraph``.
 */
export function startsWithoutOverviewParagraph(text: string | undefined): boolean {
  const firstLine = firstNonemptyLine(text);
  return Boolean(firstLine) && OPENING_STRUCTURE_RE.test(firstLine);
}

/**
 * Return top-level Chinese sections (from ``requiredMarks``) that jump
 * straight into structure without a 2-3 sentence prose lead. Mirrors
 * ``find_top_sections_missing_leads``.
 */
export function findTopSectionsMissingLeads(
  report: string | undefined,
  requiredMarks: ReadonlyArray<string> = [],
): string[] {
  if (!report) return [];
  const lines = report.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const required = new Set(requiredMarks);
  const missing: string[] = [];

  for (let index = 0; index < lines.length; index++) {
    const stripped = (lines[index] ?? "").trim();
    const sectionMatch = TOP_SECTION_LINE_RE.exec(stripped);
    if (!sectionMatch) continue;
    const mark = sectionMatch[1] ?? "";
    if (!mark) continue;
    if (required.size > 0 && !required.has(mark)) continue;

    let hasLead = false;
    for (let cursor = index + 1; cursor < lines.length; cursor++) {
      const next = (lines[cursor] ?? "").trim();
      if (!next) continue;
      if (TOP_SECTION_LINE_RE.test(next)) break;
      if (looksLikeStructuralLine(next)) break;
      hasLead = true;
      break;
    }
    if (!hasLead) missing.push(mark);
  }
  return missing;
}

function looksLikeMarkdownTableLine(line: string): boolean {
  const stripped = line.trim();
  return (
    stripped.startsWith("|") && stripped.endsWith("|") && (stripped.match(/\|/g)?.length ?? 0) >= 2
  );
}

function looksLikeSectionHeading(line: string): boolean {
  const stripped = line.trim();
  if (stripped.startsWith("#")) return true;
  const bare = stripped.replace(/^\*{1,2}/, "");
  return /^(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十\d]+[）)])/.test(bare);
}

function looksLikeStructuralLine(line: string): boolean {
  const stripped = line.trim();
  if (!stripped) return true;
  if (looksLikeSectionHeading(stripped) || looksLikeMarkdownTableLine(stripped)) return true;
  if (/^[-*+]\s+|^\d+[.)、]\s+|^>{1,}\s*/.test(stripped)) return true;
  return false;
}

// --------------------------------------- opening-cap / structural detectors

const OPENING_STRUCTURE_RE =
  /^\s*(?:#{1,6}\s+\S|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十\d]+[）)]|(?:[-*•]|\d+[.．、)])\s+\S|\|)/;

const OPENING_LABEL_RE = new RegExp(
  // Standalone label-only lines (e.g. "概述：", "结论") OR labelled prefixes
  String.raw`^\s*(?:[【\[]?\s*)?` +
    "(?:概述|开篇综述|结论|核心结论|导语|前置指引|核心结论与前置指引)" +
    String.raw`\s*(?:[】\]]|[:：])?\s*$|^\s*(?:概述|开篇综述|结论|核心结论|导语|前置指引|核心结论与前置指引)\s*[:：]`,
);

function firstNonemptyLine(text: string | undefined): string {
  if (!text) return "";
  const lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  for (const line of lines) {
    if (line.trim()) return line.trim();
  }
  return "";
}

/**
 * Detect opening lines that are structural, label-style, or task-description
 * prose. Mirrors ``has_invalid_opening_cap``.
 */
export function hasInvalidOpeningCap(
  text: string | undefined,
  opts: { rejectLabels?: boolean; rejectMeta?: boolean } = {},
): boolean {
  const { rejectLabels = true, rejectMeta = true } = opts;
  const firstLine = firstNonemptyLine(text);
  if (!firstLine) return true;
  if (OPENING_STRUCTURE_RE.test(firstLine)) return true;
  if (rejectLabels && OPENING_LABEL_RE.test(firstLine)) return true;
  if (looksLikeProcessNarration(firstLine)) return true;
  if (rejectMeta && containsMetaOpeners(firstLine)) return true;
  if (rejectMeta && containsSelfReferentialMetaLeads(firstLine)) return true;
  return false;
}

// ---------------------------------------------- decision-label artifacts

const DECISION_LABEL_LINE_RE =
  /^\s*(?:final allocation proposal|final transaction proposal|execution bias|recommendation|rating|research view|最终配置建议|最终交易建议|执行倾向|建议评级|配置评级|研究结论|评级)\s*[:：]?\s*\**(?:buy|overweight|hold|underweight|sell|买入|增持|持有|减持|卖出)\**[。！!？?\s]*$/gim;

const DECISION_LABEL_PREFIX_RE =
  /^\s*(?:final allocation proposal|final transaction proposal|execution bias|recommendation|rating|research view|最终配置建议|最终交易建议|执行倾向|建议评级|配置评级|研究结论|评级)\s*[:：]?\s*\**(?:buy|overweight|hold|underweight|sell|买入|增持|持有|减持|卖出)\**[。！!？?\s]+/gim;

/**
 * Remove leaked recommendation labels such as "最终配置建议: **持有**" /
 * "FINAL ALLOCATION PROPOSAL: **HOLD**". These come from
 * ``getCollaborationStopInstruction`` and should never appear in finished
 * analyst reports — only in the trader / portfolio-manager output.
 */
export function stripDecisionLabelArtifacts(report: string | undefined): string {
  if (!report) return "";
  let cleaned = report.replace(DECISION_LABEL_LINE_RE, "");
  cleaned = cleaned.replace(DECISION_LABEL_PREFIX_RE, "");
  return collapseBlankLines(cleaned);
}

// --------------------------------------------------------- refine preamble

const REFINE_PREAMBLE_RE =
  /^\s*(?:以下是|根据|按照|依据|参照|基于)[^\n]{0,160}(?:修正|修订|修改|改进|完善|优化|调整|评审|审核)[^\n]*\n?/gm;

const REPORT_PROCESS_PREAMBLE_RE =
  // Mirror of `_REPORT_PROCESS_PREAMBLE_RE = (?m)<OPENING_DELIVERY_PREAMBLE_RE>[..]?\s*`.
  // We intentionally keep this narrow — the multi-line strip below is enough to
  // catch "数据已就绪。下面开始撰写..." style prefixes when they leak into the
  // refine output.
  /^\s*(?:数据|资料|信息|报告)(?:已经?|已)\s*(?:全部|所有|必要|所需)?\s*(?:获取|收集|拿到|完成|掌握|到位|就绪|齐备|生成|整理好|准备好)[^\n]{0,160}\n?/gm;

const PROMPT_INSTRUCTION_LEAK_RE =
  /^\s*(?:直接进入正文|Start directly with (?:your )?(?:argument|body|report))[。.!！]?\s*$\n?/gm;

const ARTIFACT_ONLY_LINE_RE = /^[\s│|╭╮╰╯┌┐└┘├┤┬┴┼─━—-]+$/;

function isArtifactOnlyLine(line: string | undefined): boolean {
  if (!line) return false;
  return ARTIFACT_ONLY_LINE_RE.test(line);
}

function stripLeadingArtifactLines(report: string): string {
  const lines = report.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  let firstContent = 0;
  while (firstContent < lines.length) {
    const stripped = (lines[firstContent] ?? "").trim();
    if (!stripped || isArtifactOnlyLine(stripped)) {
      firstContent += 1;
      continue;
    }
    break;
  }
  return collapseBlankLines(lines.slice(firstContent).join("\n"));
}

function stripArtifactOnlyLines(report: string): string {
  const lines = report
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split("\n")
    .filter((line) => !isArtifactOnlyLine(line));
  return collapseBlankLines(lines.join("\n"));
}

/** Remove meta-commentary from the refine step. Mirrors ``strip_refine_preamble``. */
export function stripRefinePreamble(report: string | undefined): string {
  if (!report) return "";
  let cleaned = report.replace(REFINE_PREAMBLE_RE, "");
  cleaned = cleaned.replace(REPORT_PROCESS_PREAMBLE_RE, "");
  cleaned = cleaned.replace(PROMPT_INSTRUCTION_LEAK_RE, "");
  cleaned = stripArtifactOnlyLines(cleaned);
  return stripLeadingArtifactLines(cleaned);
}

// ---------------------------------------------------------- meta openers

const META_OPENER_RE =
  /^\s*(?:本报告(?:将|围绕|聚焦|基于|对[^\n]{0,80}(?:进行|展开))|本分析(?:将|围绕|聚焦|基于|对[^\n]{0,80}(?:进行|展开))|本文(?:将|围绕|聚焦|基于)|下文(?:将|围绕|聚焦)|This report(?: provides| aims| reviews| analyzes| focuses on)|This analysis(?: provides| aims| reviews| presents| focuses on)?)[^\n]*\n?/gm;

export function stripMetaOpeners(report: string | undefined): string {
  if (!report) return "";
  const cleaned = report.replace(META_OPENER_RE, "");
  return stripLeadingArtifactLines(cleaned);
}

export function containsMetaOpeners(report: string | undefined): boolean {
  if (!report) return false;
  // Use match() (returns array or null) to avoid the global-regex lastIndex
  // state that would make repeated .test() calls non-idempotent.
  return report.match(META_OPENER_RE) !== null;
}

// --------------------------------------------------- self-referential leads

const SELF_REFERENTIAL_META_LEAD_RE =
  /^\s*(?:（[^）]*）)?\s*(?:本节|本部分|该部分|这一节|本段|本文|本章节|本章)(?:核心结论|章节导语|导语|锁定|聚焦|讨论|围绕|分析|探讨|旨在|将|主要|重点|结论|说明|指出|表明|认为|阐述|梳理|审视|检视)[^\n]*\n?/gm;

export function stripSelfReferentialMetaLeads(report: string | undefined): string {
  if (!report) return "";
  return collapseBlankLines(report.replace(SELF_REFERENTIAL_META_LEAD_RE, ""));
}

export function containsSelfReferentialMetaLeads(report: string | undefined): boolean {
  if (!report) return false;
  return report.match(SELF_REFERENTIAL_META_LEAD_RE) !== null;
}

// ---------------------------------------------------------- QA labels

/**
 * Minimal detector for label-style structures such as `判断: ...`,
 * `证据: ...`, `结论: ...` at line start. The full strip implementation
 * (covering every cue in Python's ``_LABEL_CUES`` plus parenthetical term
 * blocks) is deferred to a later sub-step; the detector is enough for the
 * static validator to flag the issue and let the LLM judge fix it.
 */
const QA_LABEL_LINE_RE =
  /^\s*(?:#{1,6}\s*)?\*{0,2}(?:对交易应该怎么做|这意味着什么|交易建议|交易指引|交易含义|市场含义|配置含义|判断|证据|关键价位|条件情景|核心结论|结论|前置指引|信号总结|章节总结|信号小结|导语|章节导语|本章节导语)\*{0,2}\s*[:：]/m;

export function containsQaLabelArtifacts(report: string | undefined): boolean {
  if (!report) return false;
  return QA_LABEL_LINE_RE.test(report);
}

// ----------------------------------------------------- orchestrators

/**
 * Idempotent regex cleanups that should run BEFORE the LLM judge / refine.
 * Mirrors ``pre_judge_clean``. Sub-passes deferred to later sub-steps:
 *
 *   - normalizeBoxedTextWrapping (rare TUI-box leakage)
 *   - stripReportTitle (we use no-title prompt; H1 should never be emitted)
 *   - stripQaLabels (judgement / evidence label families)
 *   - stripOpeningTermExplanations / stripInlineTechnicalTermExplanations
 */
export function preJudgeClean(report: string | undefined): string {
  if (!report) return "";
  let cleaned = stripRefinePreamble(report);
  cleaned = stripDecisionLabelArtifacts(cleaned);
  cleaned = stripMetaOpeners(cleaned);
  cleaned = stripSelfReferentialMetaLeads(cleaned);
  return collapseBlankLines(cleaned);
}

/**
 * Cleanups that should run AFTER the LLM refine step.
 * Mirrors ``post_judge_clean`` minus the deferred punctuation pass
 * (stripDeclarativeQuestionMarks).
 */
export function postJudgeClean(report: string | undefined): string {
  if (!report) return "";
  const cleaned = preJudgeClean(report);
  return collapseBlankLines(normalizeChineseRoleTerms(cleaned));
}
