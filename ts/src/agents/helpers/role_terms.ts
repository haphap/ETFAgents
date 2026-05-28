/**
 * Chinese role-term normalization. Mirrors the surface of
 * ``etfagents.agents.utils.agent_utils.normalize_chinese_role_terms`` and
 * ``normalize_chinese_manager_terms`` but only ports the term-replacement
 * phase. The Python originals also chain through:
 *
 *   - normalize_display_numbering
 *   - normalize_chinese_numeric_expressions
 *   - normalize_chinese_finance_terms
 *   - _normalize_risk_recommendation_text
 *   - _ensure_chinese_section_breaks
 *   - _normalize_structured_block_markers
 *   - strip_constituent_trade_instructions
 *   - strip_manager_instruction_leakage
 *   - strip_all_feedback_snapshots / extract_feedback_snapshot
 *
 * Those normalizers are deferred to sub-step 2.5 (trader-side post-processing)
 * because they are tightly coupled with snapshot/feedback structures.
 */

/** Sorted by length (descending) so longer keys win during regex alternation. */
export const CHINESE_ROLE_TERM_REPLACEMENTS: ReadonlyArray<readonly [string, string]> = [
  ["ETF持仓映射行业研究分析师", "行业研究分析师"],
  ["ETF头部成分股研究分析师", "个股研究分析师"],
  ["ETF持仓行业研究分析师", "行业研究分析师"],
  ["ETF头部企业研究分析师", "个股研究分析师"],
  ["个股研报分析师", "个股研究分析师"],
  ["激进分析师", "激进风险分析师"],
  ["保守分析师", "保守风险分析师"],
  ["中性分析师", "中性风险分析师"],
  ["熊派分析师", "空头分析师"],
  ["熊派投资者", "空头投资者"],
  ["牛派分析师", "多头分析师"],
  ["牛派投资者", "多头投资者"],
  ["根本面分析", "基本面分析"],
  ["新闻分析师", "宏观分析师"],
  ["熊观点", "空头观点"],
  ["牛观点", "多头观点"],
  ["根本分析", "基本面分析"],
  ["辩论裁决", "辩论结论"],
  ["判决结果", "综合结论"],
  ["熊派", "空头"],
  ["牛派", "多头"],
];

/** Build the role-term match regex once. */
function buildRoleTermPattern(): RegExp {
  const escaped = CHINESE_ROLE_TERM_REPLACEMENTS.map(([term]) =>
    term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
  );
  // Length-sorted (already in source array) ensures longest-match wins.
  return new RegExp(`(?:${escaped.join("|")})`, "g");
}

const ROLE_TERM_RE = buildRoleTermPattern();
const ROLE_TERM_MAP = new Map(CHINESE_ROLE_TERM_REPLACEMENTS);

/**
 * Replace deprecated role-term variants with the project's canonical Chinese
 * wording. Skipped sub-passes are listed in the module docstring.
 */
export function normalizeChineseRoleTerms(text: string | undefined): string {
  if (!text) return "";
  return text.replace(ROLE_TERM_RE, (match) => ROLE_TERM_MAP.get(match) ?? match);
}

/**
 * Manager-tier rewrites (English manager-section headings → Chinese variants,
 * plus rating-label canonicalization). Mirrors a focused subset of
 * ``normalize_chinese_manager_terms``; snapshot extraction and constituent
 * trade-instruction stripping land in sub-step 2.5.
 */
const MANAGER_HEADING_REPLACEMENTS: ReadonlyArray<readonly [string, string]> = [
  ["## Risk Debate Conclusion", "## 辩论结论"],
  ["## Debate Verdict", "## 辩论结论"],
  ["## Debate Conclusion", "## 辩论结论"],
  ["## Action Logic", "## 行为逻辑"],
  ["## Positioning Recommendation", "## 持仓建议"],
  ["## Research View", "## 研究结论"],
  ["## Executive Summary", "## 执行摘要"],
  ["## Investment Thesis", "## 投资逻辑"],
  ["Risk Debate Conclusion", "辩论结论"],
  ["Debate Verdict", "辩论结论"],
  ["Debate Conclusion", "辩论结论"],
  ["Action Logic", "行为逻辑"],
  ["Positioning Recommendation", "持仓建议"],
  ["Research View", "研究结论"],
  ["Executive Summary", "执行摘要"],
  ["Investment Thesis", "投资逻辑"],
  ["Time Horizon", "时间区间"],
  ["time horizon", "时间区间"],
  ["EXECUTION BIAS", "执行倾向"],
  ["FINAL ALLOCATION PROPOSAL", "最终配置建议"],
  ["FINAL TRANSACTION PROPOSAL", "最终配置建议"],
];

export function normalizeChineseManagerTerms(text: string | undefined): string {
  let normalized = normalizeChineseRoleTerms(text);
  if (!normalized) return normalized;
  for (const [from, to] of MANAGER_HEADING_REPLACEMENTS) {
    normalized = normalized.split(from).join(to);
  }
  // Rewrite an explicit "最终配置建议:" / "最终交易建议:" line label (left over from
  // FINAL ALLOCATION PROPOSAL strings) into the canonical "研究结论:".
  normalized = normalized.replace(
    /^(\s*)(?:最终配置建议|最终交易建议)\s*[:：]\s*/gm,
    "$1研究结论: ",
  );
  return normalized;
}
