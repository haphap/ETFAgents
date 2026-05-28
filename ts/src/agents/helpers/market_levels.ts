/**
 * Market-level anchor extraction + inlining.
 *
 * Mirrors the helpers under ``etfagents/agents/schemas.py`` that pull labelled
 * price/volume references (``50日均线 3.58 元``, ``布林中轨 449``, etc.) out of
 * the upstream market-flow report and substitute them into the trader prose so
 * downstream sections refer to concrete numbers rather than generic phrases
 * such as ``市场报告中的首个关键位``.
 *
 * Sub-step 2.5c-1 ports:
 *   - ``_MARKET_LEVEL_LABEL_PATTERN`` / ``_MARKET_LEVEL_VALUE_PATTERN``
 *   - ``_extract_market_level_anchors``
 *   - ``_market_level_priority`` / ``_prioritize_market_level_anchors``
 *   - ``_primary_market_level_anchor`` / ``_market_level_anchor_clause``
 *   - ``_extract_market_level_anchor_map``
 *   - ``_inline_contextual_market_levels``
 */

import { isChinese } from "../schemas/rating.js";

const MARKET_LEVEL_LABEL_PATTERN =
  "(?:50日均线|20日均线|10日均线|200日均线|布林中轨|布林上轨|布林下轨|" +
  "布林带中轨|布林带上轨|布林带下轨|前高突破位|前低回踩位|前低|前高|" +
  "主支撑位|主支撑|主阻力位|主阻力|支撑位|阻力位|支撑带|阻力带|" +
  "密集成交区|上一压力位|压力位|止损位|" +
  "50-day(?:\\s+(?:moving average|SMA))?|20-day(?:\\s+(?:moving average|SMA))?|" +
  "10-day(?:\\s+(?:moving average|SMA))?|200-day(?:\\s+(?:moving average|SMA))?|" +
  "Bollinger mid-band|Bollinger middle band|Bollinger upper band|Bollinger lower band|" +
  "prior breakout level|prior retest level|swing low|swing high|support(?: zone)?|" +
  "resistance(?: zone)?|stop(?:-loss)? level|VWMA|ATR|NAV|SMA|EMA)";

const MARKET_LEVEL_VALUE_PATTERN =
  "\\d+(?:\\.\\d+)?(?:\\s*[-—~至to]+\\s*\\d+(?:\\.\\d+)?)?\\s*" +
  "(?:元|美元|港元|点|bp|bps|USD|HKD|pts?|points?)?";

// (label) (optional connector) (value)
const LABEL_THEN_VALUE_RE = new RegExp(
  `(${MARKET_LEVEL_LABEL_PATTERN})(?:位于|在|约|为|处于|落在|落于|对应|回踩至|上移至|下移至|看至|约在|：|:)?\\s*(${MARKET_LEVEL_VALUE_PATTERN})`,
  "g",
);
// (value) [optional 的] (label)
const VALUE_THEN_LABEL_RE = new RegExp(
  `(${MARKET_LEVEL_VALUE_PATTERN})(?:的)?\\s*(${MARKET_LEVEL_LABEL_PATTERN})`,
  "g",
);

const LABEL_FULL_RE = new RegExp(`^${MARKET_LEVEL_LABEL_PATTERN}$`);
const LABEL_BARE_RE = new RegExp(MARKET_LEVEL_LABEL_PATTERN);
const HAS_CJK_RE = /[\u4e00-\u9fff]/;
const COMPACT_STRIP_RE = /[\s:：,，。.!！？/\-—_()（）]+/g;

function compact(text: string): string {
  return text.replace(COMPACT_STRIP_RE, "").trim().toLowerCase();
}

/**
 * Pull labelled market-level anchors (label + value) from text.
 * Mirrors ``_extract_market_level_anchors``.
 */
export function extractMarketLevelAnchors(text: string | undefined, limit = 3): string[] {
  const content = (text ?? "").trim();
  if (!content || limit <= 0) return [];

  const anchors: string[] = [];
  const seen = new Set<string>();

  const collect = (regex: RegExp): boolean => {
    regex.lastIndex = 0;
    for (;;) {
      const match = regex.exec(content);
      if (match === null) break;
      const left = (match[1] ?? "").trim();
      const right = (match[2] ?? "").trim();
      let anchor: string;
      if (LABEL_FULL_RE.test(left)) {
        const sep = HAS_CJK_RE.test(left) ? "" : " ";
        anchor = `${left}${sep}${right}`.trim();
      } else {
        const sep = HAS_CJK_RE.test(right) ? "的" : " ";
        anchor = `${left}${sep}${right}`.trim();
      }
      const normalized = compact(anchor);
      if (!normalized || seen.has(normalized)) continue;
      anchors.push(anchor);
      seen.add(normalized);
      if (anchors.length >= limit) {
        regex.lastIndex = 0;
        return true;
      }
    }
    regex.lastIndex = 0;
    return false;
  };

  if (collect(LABEL_THEN_VALUE_RE)) return anchors;
  collect(VALUE_THEN_LABEL_RE);
  return anchors;
}

const PRIORITIES: ReadonlyArray<readonly [string, number]> = [
  ["50日均线", 0],
  ["50-day", 0],
  ["布林中轨", 1],
  ["布林带中轨", 1],
  ["bollinger mid-band", 1],
  ["bollinger middle band", 1],
  ["前高突破位", 2],
  ["prior breakout level", 2],
  ["前低回踩位", 3],
  ["prior retest level", 3],
  ["前低", 4],
  ["swing low", 4],
  ["前高", 5],
  ["swing high", 5],
  ["支撑", 6],
  ["support", 6],
  ["阻力", 7],
  ["resistance", 7],
  ["20日均线", 8],
  ["20-day", 8],
  ["10日均线", 9],
  ["10-day", 9],
  ["200日均线", 10],
  ["200-day", 10],
];

function marketLevelPriority(anchor: string): number {
  const normalized = (anchor ?? "").toLowerCase();
  for (const [token, priority] of PRIORITIES) {
    if (normalized.includes(token)) return priority;
  }
  return 99;
}

function prioritizeAnchors(anchors: ReadonlyArray<string>, limit: number): string[] {
  return anchors
    .map((anchor, index) => ({ anchor, index }))
    .sort((a, b) => {
      const pa = marketLevelPriority(a.anchor);
      const pb = marketLevelPriority(b.anchor);
      return pa !== pb ? pa - pb : a.index - b.index;
    })
    .slice(0, limit)
    .map(({ anchor }) => anchor);
}

export function primaryAnchor(contextText: string, fallback: string): string {
  const ranked = prioritizeAnchors(extractMarketLevelAnchors(contextText, 6), 1);
  return ranked[0] ?? fallback;
}

export function anchorClause(contextText: string, fallback: string, limit = 2): string {
  const ranked = prioritizeAnchors(extractMarketLevelAnchors(contextText, 6), limit);
  if (ranked.length === 0) return fallback;
  if (ranked.length === 1) return ranked[0] ?? fallback;
  return ranked.join("或");
}

function extractAnchorMap(contextText: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const anchor of prioritizeAnchors(extractMarketLevelAnchors(contextText, 8), 8)) {
    const labelMatch = LABEL_BARE_RE.exec(anchor);
    if (!labelMatch) continue;
    const label = labelMatch[0];
    if (!map.has(label)) map.set(label, anchor);
  }
  return map;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Inline concrete market levels from ``contextText`` (the upstream
 * market-flow report) into the trader prose, replacing generic phrases and
 * bare labels with ``label+value`` anchors. Mirrors
 * ``_inline_contextual_market_levels``.
 */
export function inlineContextualMarketLevels(
  text: string | undefined,
  contextText: string | undefined,
  language: string,
): string {
  let content = (text ?? "").trim();
  if (!content || !contextText || !isChinese(language)) return content;

  const primary = primaryAnchor(contextText, "");
  const support = anchorClause(contextText, "", 2);

  if (primary) {
    content = content.split("市场分析中给出的首个关键阻力/支撑转换位").join(primary);
    content = content.split("市场报告已经写明的首个关键位").join(primary);
  }
  if (support) {
    content = content.split("市场报告中的主支撑位或50日均线").join(support);
    content = content.split("主支撑位或50日均线").join(support);
  }

  for (const [label, anchor] of extractAnchorMap(contextText)) {
    // Replace bare labels NOT already followed by a number (i.e. not already
    // an anchor itself).
    const re = new RegExp(`${escapeRegExp(label)}(?!\\s*\\d)`, "g");
    content = content.replace(re, anchor);
  }
  return content;
}
