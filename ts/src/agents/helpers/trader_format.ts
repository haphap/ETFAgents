/**
 * Trader-side post-processing helpers (sub-step 2.5a).
 *
 * Ports the ETF-discipline + heading-normalization helpers from
 * ``etfagents/agents/trader/trader.py`` and the constituent-trade stripper
 * from ``etfagents/agents/utils/agent_utils.py``.
 *
 * Sub-step 2.5b (next) will port the prose-section sanitizers
 * (_sanitize_section, _format_trader_thesis_body, _format_trader_numbered_blocks,
 * _inline_contextual_market_levels) and 2.5c will polish
 * invoke_structured_or_freetext_with_result.
 */

import { collapseBlankLines } from "../prompts/shared.js";
import { isChinese } from "../schemas/rating.js";

// ============================================================ heading H1 demote

/**
 * Demote any markdown ``#`` H1 lines to ``##`` so trader output never carries
 * H1 titles. Mirrors ``_demote_trader_h1_headings``.
 */
export function demoteTraderH1Headings(text: string | undefined): string {
  if (!text) return "";
  return text.replace(/^#(?!#)\s*/gm, "## ");
}

// ====================================================== 配置逻辑 heading rename

/**
 * Rename a generic / aliased section-一 heading (e.g. "ETF配置逻辑",
 * "配置核心逻辑") to the canonical "配置逻辑". When the original heading
 * carried distinct semantics, also re-insert it as a free-floating sub-line so
 * the body stays self-explanatory.
 *
 * Mirrors ``_normalize_trader_config_logic_heading``.
 */
export function normalizeTraderConfigLogicHeading(
  text: string | undefined,
  language: string,
): string {
  const content = (text ?? "").trim();
  if (!content || !isChinese(language)) return content;

  const lines = content.split("\n");
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index] ?? "";
    const match = /^(\s*(?:#{1,6}\s*)?)一、\s*(.+?)\s*$/.exec(line);
    if (!match) {
      if (line.trim()) break;
      continue;
    }

    const headingPrefix = match[1] ?? "";
    const headingText = (match[2] ?? "").trim();
    if (headingText === "配置逻辑") return content;

    lines[index] = `${headingPrefix}一、配置逻辑`;

    // If the original heading was an alias (e.g. ETF配置逻辑 / 配置核心逻辑) skip
    // the sub-line; otherwise re-insert as a paragraph so context isn't lost.
    if (!new Set(["ETF配置逻辑", "配置核心逻辑"]).has(headingText)) {
      let nextIdx = index + 1;
      while (nextIdx < lines.length && !(lines[nextIdx] ?? "").trim()) nextIdx += 1;

      let shouldInsertHeading =
        nextIdx >= lines.length || /^\s*(?:#{1,6}\s*)?二、/.test(lines[nextIdx] ?? "");

      if (!shouldInsertHeading) {
        const firstBodyLine = (lines[nextIdx] ?? "").trim();
        const headingNorm = headingText.replace(/[。！？!?；;：:\s]+$/, "");
        const bodyNorm = firstBodyLine.replace(/[。！？!?；;：:\s]+$/, "");
        shouldInsertHeading = !(headingNorm && bodyNorm?.startsWith(headingNorm));
      }

      if (shouldInsertHeading) {
        lines.splice(index + 1, 0, headingText, "");
      }
    }
    return collapseBlankLines(lines.join("\n"));
  }
  return content;
}

// ============================================== restore "四、执行倾向" section

const TRADER_TAIL_EXECUTION_BIAS_RE =
  /(^|[\n。！？!?；;])\s*(?:执行倾向|最终配置建议|最终交易建议|研究结论|配置评级|评级)\s*[:：]\s*\**(?<rating>买入|增持|持有|减持|卖出)\**[。！!？?\s]*$/im;

const RATING_LABEL_LINE_RE =
  /(?:执行倾向|最终配置建议|最终交易建议|研究结论|配置评级|评级)\s*[:：]\s*\**(?<rating>买入|增持|持有|减持|卖出)\**/m;

const BOLD_RATING_RE = /\**(?<rating>买入|增持|持有|减持|卖出)\**/;

/**
 * Ensure section "四、执行倾向" exists with the rating on its own line.
 * Mirrors ``_restore_trader_execution_bias_section``.
 */
export function restoreTraderExecutionBiasSection(
  text: string | undefined,
  language: string,
): string {
  const content = (text ?? "").trim();
  if (!content || !isChinese(language)) return content;

  // Case A: section heading exists — locate the rating in the tail.
  const sectionMatch = /(?:^|\n)\s*四、执行倾向\s*(?:\n|$)/m.exec(content);
  if (sectionMatch) {
    const sectionStart = sectionMatch.index;
    const sectionHeadEnd = sectionStart + sectionMatch[0].length;
    const tail = content.slice(sectionHeadEnd);
    const labelMatch = RATING_LABEL_LINE_RE.exec(tail);
    const boldMatch = !labelMatch ? BOLD_RATING_RE.exec(tail) : null;
    const rating = labelMatch?.groups?.rating ?? boldMatch?.groups?.rating ?? "";
    if (rating) {
      const body = content.slice(0, sectionStart).replace(/\s+$/, "");
      return collapseBlankLines(`${body}\n\n四、执行倾向\n**${rating}**`);
    }
    return content;
  }

  // Case B: a tail line like "执行倾向: **买入**" exists at end → promote it.
  const tailMatch = TRADER_TAIL_EXECUTION_BIAS_RE.exec(content);
  if (!tailMatch) return content;
  const prefix = tailMatch[1] ?? "";
  const rating = tailMatch.groups?.rating ?? "";
  let body = content.slice(0, tailMatch.index);
  if (prefix && prefix !== "\n") body += prefix;
  return collapseBlankLines(`${body.replace(/\s+$/, "")}\n\n四、执行倾向\n**${rating}**`);
}

// ====================================== strip_constituent_trade_instructions

const ETF_ALLOCATION_SCOPE_SENTENCE =
  "成分股层面的估值、盈利和权重信息仅作为ETF仓位调整依据，实际执行对象仍是ETF整体仓位，不对成分股给出直接交易指令。";

// 中国核电（7.91%权重，归母同比-34.19%）style detail block.
const CONSTITUENT_DETAIL_RE =
  /(?<name>[\u4e00-\u9fffA-Za-z]{2,20})[（(][^）)]{0,100}(?:\d+(?:\.\d+)?%|权重|PE|同比|归母|亿元)[^）)]{0,100}[）)]/g;

const ETF_LEVEL_DETAIL_NAME_RE = /(?:ETF|基金|组合|仓位|配置|敞口|目标权重|基准配置)/i;

const CONSTITUENT_TRADE_ACTION_RE =
  /(?:应|建议|优先|直接|全部|进一步|剩余)?[^。！？!?；;]{0,40}(?:清仓|减持|卖出|保留|持有|减至|压至|剩余权重)/;

const CONSTITUENT_ACTION_CLAUSE_RE =
  /(?:优先|直接|全部|进一步|建议)?[^，,；;：:\n]{0,40}(?:清仓|减持|卖出|保留|持有|减至|剩余权重)/;

const ETF_ALLOCATION_PREFIX_RE = /(?:ETF|仓位|目标权重|配置|敞口)/;

interface ConstituentMatch {
  index: number;
  name: string;
}

function findConstituentDetails(segment: string): ConstituentMatch[] {
  const matches: ConstituentMatch[] = [];
  // Reset stateful global regex.
  CONSTITUENT_DETAIL_RE.lastIndex = 0;
  for (;;) {
    const m = CONSTITUENT_DETAIL_RE.exec(segment);
    if (m === null) break;
    const name = (m.groups?.name ?? "").trim();
    if (name && !ETF_LEVEL_DETAIL_NAME_RE.test(name)) {
      matches.push({ index: m.index, name });
    }
  }
  CONSTITUENT_DETAIL_RE.lastIndex = 0;
  return matches;
}

function preserveEtfAllocationPrefix(segment: string): string {
  const details = findConstituentDetails(segment);
  const first = details[0];
  if (!first) return "";
  let prefix = segment.slice(0, first.index);
  const clauses = prefix
    .split(/[，,；;：:\n]+/)
    .map((c) => c.trim())
    .filter(Boolean);
  while (
    clauses.length > 0 &&
    CONSTITUENT_ACTION_CLAUSE_RE.test(clauses[clauses.length - 1] ?? "")
  ) {
    clauses.pop();
  }
  prefix = clauses.join("，").replace(/[，,；;：:\s]+$/, "");
  if (!ETF_ALLOCATION_PREFIX_RE.test(prefix)) return "";
  return prefix;
}

function hasConstituentTradeInstruction(segment: string): boolean {
  if (!CONSTITUENT_TRADE_ACTION_RE.test(segment)) return false;
  return findConstituentDetails(segment).length > 0;
}

/**
 * Remove direct constituent-stock trade instructions from ETF allocation prose.
 * Chinese-only — English prose carries the same constraint via prompt
 * instructions, so we don't try to parse English company names.
 *
 * Mirrors ``strip_constituent_trade_instructions``.
 */
export function stripConstituentTradeInstructions(
  text: string | undefined,
  language: string,
  opts: { insertScopeNote?: boolean } = {},
): string {
  const content = text ?? "";
  if (!content || !isChinese(language)) return content.trim();

  const insertScopeNote = opts.insertScopeNote ?? true;
  // Split into sentence-like fragments preserving Chinese / English terminal punctuation.
  const parts = content.split(/([。！？!?；;]\s*)/);
  if (parts.length === 0) return content.trim();

  const cleanedParts: string[] = [];
  let insertedScopeNote = false;
  for (let i = 0; i < parts.length; i += 2) {
    const segment = parts[i] ?? "";
    const punctuation = i + 1 < parts.length ? (parts[i + 1] ?? "") : "";
    if (!segment) {
      cleanedParts.push(segment + punctuation);
      continue;
    }
    if (!hasConstituentTradeInstruction(segment)) {
      cleanedParts.push(segment + punctuation);
      continue;
    }
    const prefix = preserveEtfAllocationPrefix(segment);
    if (prefix) {
      if (insertScopeNote) {
        const trailing = prefix.slice(-1);
        const suffix = "，、；：,;:".includes(trailing) ? "" : "，";
        cleanedParts.push(`${prefix}${suffix}${ETF_ALLOCATION_SCOPE_SENTENCE}`);
        insertedScopeNote = true;
      } else {
        cleanedParts.push(prefix);
      }
      continue;
    }
    if (insertScopeNote && !insertedScopeNote) {
      cleanedParts.push(ETF_ALLOCATION_SCOPE_SENTENCE);
      insertedScopeNote = true;
    }
  }

  return cleanedParts
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// ====================================================== Chinese numbering polish

const NUMBERED_HEADING_PREFIX_RE =
  /^\s*(?:#{1,6}\s*)?(?:[一二三四五六七八九十]+|[1-9]\d*)\s*[、.．)）:：-]\s*/;

/** Strip a leading "一、" / "1." / "1)" heading marker from a single line. */
export function stripNumberedHeadingPrefix(text: string | undefined): string {
  return (text ?? "").trim().replace(NUMBERED_HEADING_PREFIX_RE, "");
}

const SENTENCE_SPLIT_RE = /\n+|(?<=[。！？!?])\s*/;
const HAS_NUMBERED_BLOCK_RE = /^\s*(?:\d+[.．、)]|[一二三四五六七八九十]+、)\s*\S/m;

function splitSentences(text: string | undefined): string[] {
  const content = (text ?? "").trim();
  if (!content) return [];
  return content
    .split(SENTENCE_SPLIT_RE)
    .map((s) => s.trim())
    .filter(Boolean);
}

function hasNumberedBlocks(text: string | undefined): boolean {
  return HAS_NUMBERED_BLOCK_RE.test(text ?? "");
}

const COMPACT_STRIP_RE = /[\s:：,，。.!！？/\-—_()（）]+/g;
function compactText(text: string | undefined): string {
  return (text ?? "").replace(COMPACT_STRIP_RE, "").trim().toLowerCase();
}

const NEGATION_PREFIX = "(?:不|未|无|勿|别|避免|不要|不能|无需|暂不)";

function hasUnnegatedKeyword(content: string, keywordPattern: string): boolean {
  if (!new RegExp(keywordPattern).test(content)) return false;
  const negated = new RegExp(`${NEGATION_PREFIX}\\s*(?:再|去|做)?\\s*(?:${keywordPattern})`);
  return !negated.test(content);
}

type BlockKey = "initial" | "add" | "reduce" | "monitor";

function traderBlockKey(sentence: string): BlockKey {
  const content = sentence ?? "";
  if (hasUnnegatedKeyword(content, "减仓|减持|降低|退出|止损|清仓|失守|跌破|破位|转弱|回撤")) {
    return "reduce";
  }
  if (hasUnnegatedKeyword(content, "加仓|增配|上调|回补|提高|扩大|买入")) return "add";
  if (hasUnnegatedKeyword(content, "跟踪|监控|复核|观察|验证|再平衡|确认|关注")) return "monitor";
  return "initial";
}

function traderBlockLabel(key: BlockKey, sectionKind: "execution" | "risk"): string {
  const RISK_LABELS: Record<BlockKey, string> = {
    initial: "风险预算与仓位边界",
    add: "回补与恢复条件",
    reduce: "减仓触发的核心条件",
    monitor: "监控优先级",
  };
  const EXEC_LABELS: Record<BlockKey, string> = {
    initial: "初始仓位与执行节奏",
    add: "加仓触发条件",
    reduce: "减仓触发的核心条件",
    monitor: "跟踪验证与再平衡",
  };
  return (sectionKind === "risk" ? RISK_LABELS : EXEC_LABELS)[key];
}

const BUCKET_ORDER: Record<BlockKey, number> = {
  initial: 0,
  add: 1,
  reduce: 2,
  monitor: 3,
};

/**
 * Bucket sentences in a trader execution-plan or risk-controls section into
 * numbered blocks (initial / add / reduce / monitor). Mirrors
 * ``_format_trader_numbered_blocks``.
 */
export function formatTraderNumberedBlocks(
  text: string | undefined,
  sectionKind: "execution" | "risk",
  language: string,
): string {
  const content = (text ?? "").trim();
  if (!content || !isChinese(language) || hasNumberedBlocks(content)) return content;

  const sentences = splitSentences(content);
  const compact = compactText(content);
  if (sentences.length < 3 && compact.length < 180) return content;

  const indexByKey = new Map<BlockKey, number>();
  const buckets: Array<{ key: BlockKey; sentences: string[] }> = [];
  for (const sentence of sentences) {
    const key = traderBlockKey(sentence);
    let idx = indexByKey.get(key);
    if (idx === undefined) {
      idx = buckets.length;
      indexByKey.set(key, idx);
      buckets.push({ key, sentences: [] });
    }
    const bucket = buckets[idx];
    if (bucket) bucket.sentences.push(sentence);
  }
  if (buckets.length < 2) return content;

  buckets.sort((a, b) => (BUCKET_ORDER[a.key] ?? 99) - (BUCKET_ORDER[b.key] ?? 99));

  const blocks = buckets.map(
    (bucket, index) =>
      `${index + 1}. ${traderBlockLabel(bucket.key, sectionKind)}\n${bucket.sentences.join("")}`,
  );
  return blocks.join("\n\n").trim();
}

/**
 * Promote each sentence in the thesis body to a numbered argument (1./2./3.).
 * Mirrors ``_format_trader_thesis_body``.
 */
export function formatTraderThesisBody(text: string | undefined, language: string): string {
  const content = (text ?? "").trim();
  if (!content || !isChinese(language)) return content;
  const sentences = splitSentences(content);
  if (sentences.length <= 1) return content;
  return sentences.map((sentence, idx) => `${idx + 1}. ${sentence}`).join("\n\n");
}
