/**
 * Market-flow specific report transforms — port of the private helpers under
 * ``etfagents/agents/analysts/etf_market_analyst.py``:
 *
 *   - ``_looks_like_complete_market_flow_report`` (acceptance gate)
 *   - ``_normalize_market_flow_tail_sections`` (legacy tail layouts → canonical
 *     "四、综合结论和指标总览" heading + conclusion paragraph + table)
 *
 * The normalizer migrates three legacy shapes into the canonical layout:
 *
 *   a) Standalone ``指标总览`` / ``四、指标总览`` heading before the table,
 *      with the conclusion paragraph living under a separate
 *      ``四、综合结论和指标总览`` heading above.
 *   b) Standalone ``综合结论`` heading after the table.
 *   c) Inline ``综合结论：…`` label after the table.
 */

import { collapseBlankLines } from "../prompts/shared.js";
import { collectTopSectionMarks, hasInvalidOpeningCap } from "./report_leads.js";

const MARKET_FLOW_REQUIRED_TOP_SECTIONS: ReadonlySet<string> = new Set(["一", "二", "三"]);
const MARKET_FLOW_COMBINED_TAIL_HEADING = "四、综合结论和指标总览";

const TABLE_SEPARATOR_RE = /^\|(?:\s*:?-{3,}:?\s*\|)+\s*$/;
const CONCLUSION_LABEL_RE = /^\s*综合结论\s*[:：]\s*(.+)$/;
const COMBINED_TAIL_LINE_RE =
  /^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]+[、.．]\s*综合结论和指标总览(?:[。.]|\s|$)/;
const COMBINED_TAIL_WITH_TEXT_RE =
  /^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]+[、.．]\s*综合结论和指标总览(?:[。.]?\s*)?(?<tail>.*)$/;
const HEADING_PREFIX_RE = /^#{1,6}\s*/;

/**
 * Strict acceptance contract for accepting a market-flow report into graph
 * state. Mirrors ``_looks_like_complete_market_flow_report`` exactly.
 */
export function looksLikeCompleteMarketFlowReport(report: string | undefined): boolean {
  const content = report ?? "";
  if (!content.trim()) return false;
  if (hasInvalidOpeningCap(content)) return false;

  const marks = collectTopSectionMarks(content);
  for (const need of MARKET_FLOW_REQUIRED_TOP_SECTIONS) {
    if (!marks.has(need)) return false;
  }
  // Section 四 must contain an indicator overview table — accept any
  // markdown table separator anywhere in the content.
  for (const line of content.split("\n")) {
    if (TABLE_SEPARATOR_RE.test(line.trim())) return true;
  }
  return false;
}

// -------------------------------------------------------- internals

interface TableSpan {
  start: number;
  end: number;
}

/** Locate the LAST markdown table span (header line + separator + data rows). */
function findLastMarkdownTable(lines: ReadonlyArray<string>): TableSpan | null {
  let lastTable: TableSpan | null = null;
  let index = 0;
  while (index < lines.length - 1) {
    const header = (lines[index] ?? "").trim();
    const separator = (lines[index + 1] ?? "").trim();
    const looksLikeTableHeader = header.startsWith("|") && header.includes("|");
    if (!(looksLikeTableHeader && TABLE_SEPARATOR_RE.test(separator))) {
      index += 1;
      continue;
    }
    let end = index + 2;
    while (end < lines.length && (lines[end] ?? "").trim().startsWith("|")) {
      end += 1;
    }
    lastTable = { start: index, end };
    index = end;
  }
  return lastTable;
}

function combinedTailInlineText(line: string): string {
  const match = COMBINED_TAIL_WITH_TEXT_RE.exec(line.trim());
  if (!match) return "";
  const tail = (match.groups?.tail ?? "").trim();
  if (!tail || tail === "。" || tail === ".") return "";
  return tail;
}

function findPreviousCombinedTailHeading(
  lines: ReadonlyArray<string>,
  start: number,
): number | null {
  for (let i = start; i >= 0; i--) {
    const stripped = (lines[i] ?? "").trim();
    if (stripped === MARKET_FLOW_COMBINED_TAIL_HEADING || COMBINED_TAIL_LINE_RE.test(stripped)) {
      return i;
    }
  }
  return null;
}

function collectTailConclusion(lines: ReadonlyArray<string>, start: number, end: number): string {
  const parts: string[] = [];
  for (let i = start; i < end; i++) {
    let stripped = (lines[i] ?? "").trim();
    if (!stripped) continue;
    const normalized = stripped.replace(HEADING_PREFIX_RE, "");
    if (
      normalized === "指标总览" ||
      normalized === "四、指标总览" ||
      normalized === "综合结论" ||
      normalized === MARKET_FLOW_COMBINED_TAIL_HEADING
    ) {
      continue;
    }
    const labelMatch = CONCLUSION_LABEL_RE.exec(stripped);
    if (labelMatch) {
      stripped = (labelMatch[1] ?? "").trim();
    }
    if (stripped) parts.push(stripped);
  }
  return parts.join("\n").trim();
}

function stripDuplicateCombinedTail(lines: ReadonlyArray<string>): string[] {
  let seen = false;
  const kept: string[] = [];
  for (const line of lines) {
    const stripped = line.trim();
    const isCombinedHeading =
      stripped === MARKET_FLOW_COMBINED_TAIL_HEADING || COMBINED_TAIL_LINE_RE.test(stripped);
    if (isCombinedHeading) {
      if (seen) break;
      seen = true;
    }
    kept.push(line);
  }
  return kept;
}

/**
 * Migrate legacy tail shapes into the canonical
 * ``四、综合结论和指标总览`` heading + paragraph + Markdown table.
 *
 * Mirrors ``_normalize_market_flow_tail_sections``.
 */
export function normalizeMarketFlowTailSections(report: string | undefined): string {
  if (!report) return "";

  const lines = report.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const tableSpan = findLastMarkdownTable(lines);

  if (tableSpan) {
    const { start: tableStart, end: tableEnd } = tableSpan;
    const tableLines = lines.slice(tableStart, tableEnd);
    let replacementStart = tableStart;
    let conclusionText = "";

    // Inspect the line immediately before the table.
    let beforeIdx = tableStart - 1;
    while (beforeIdx >= 0 && !(lines[beforeIdx] ?? "").trim()) beforeIdx -= 1;
    const beforeStripped =
      beforeIdx >= 0 ? (lines[beforeIdx] ?? "").trim().replace(HEADING_PREFIX_RE, "") : "";

    if (beforeIdx >= 0 && (beforeStripped === "指标总览" || beforeStripped === "四、指标总览")) {
      // Layout (a): 综合结论 paragraph above + 指标总览 heading + table
      replacementStart = beforeIdx;
      const headingIdx = findPreviousCombinedTailHeading(lines, beforeIdx - 1);
      if (headingIdx !== null) {
        replacementStart = headingIdx;
        const inlineText = combinedTailInlineText(lines[headingIdx] ?? "");
        const paragraphText = collectTailConclusion(lines, headingIdx + 1, beforeIdx);
        conclusionText = [inlineText, paragraphText].filter(Boolean).join("\n").trim();
      }
    } else if (
      beforeIdx >= 0 &&
      (beforeStripped === MARKET_FLOW_COMBINED_TAIL_HEADING ||
        COMBINED_TAIL_LINE_RE.test((lines[beforeIdx] ?? "").trim()))
    ) {
      // Layout already canonical or the heading sits directly above the table.
      replacementStart = beforeIdx;
      conclusionText = combinedTailInlineText(lines[beforeIdx] ?? "");
    } else if (beforeIdx >= 0) {
      // Walk back to find a combined-tail heading above a paragraph.
      let paragraphStart = beforeIdx;
      while (paragraphStart >= 0 && (lines[paragraphStart] ?? "").trim()) paragraphStart -= 1;
      let headingIdx = paragraphStart;
      while (headingIdx >= 0 && !(lines[headingIdx] ?? "").trim()) headingIdx -= 1;
      if (headingIdx >= 0 && COMBINED_TAIL_LINE_RE.test((lines[headingIdx] ?? "").trim())) {
        replacementStart = headingIdx;
        const inlineText = combinedTailInlineText(lines[headingIdx] ?? "");
        const paragraphText = lines
          .slice(headingIdx + 1, tableStart)
          .map((line) => line.trim())
          .filter(Boolean)
          .join("\n")
          .trim();
        conclusionText = [inlineText, paragraphText].filter(Boolean).join("\n").trim();
      }
    }

    let replacementEnd = tableEnd;

    // Inspect what follows the table. Layout (b)/(c).
    let conclusionIdx = tableEnd;
    while (conclusionIdx < lines.length && !(lines[conclusionIdx] ?? "").trim()) conclusionIdx += 1;
    if (conclusionIdx < lines.length) {
      const labelMatch = CONCLUSION_LABEL_RE.exec(lines[conclusionIdx] ?? "");
      if (labelMatch) {
        conclusionText = (labelMatch[1] ?? "").trim();
        replacementEnd = conclusionIdx + 1;
      } else if ((lines[conclusionIdx] ?? "").trim() === "综合结论") {
        let paragraphStart = conclusionIdx + 1;
        while (paragraphStart < lines.length && !(lines[paragraphStart] ?? "").trim()) {
          paragraphStart += 1;
        }
        let paragraphEnd = paragraphStart;
        while (paragraphEnd < lines.length && (lines[paragraphEnd] ?? "").trim()) {
          paragraphEnd += 1;
        }
        conclusionText = lines
          .slice(paragraphStart, paragraphEnd)
          .map((line) => line.trim())
          .join("\n")
          .trim();
        replacementEnd = paragraphEnd;
      }
    }

    const replacement: string[] = [MARKET_FLOW_COMBINED_TAIL_HEADING, ""];
    if (conclusionText) {
      replacement.push(conclusionText, "");
    }
    replacement.push(...tableLines);
    if (replacementStart > 0 && (lines[replacementStart - 1] ?? "").trim()) {
      replacement.unshift("");
    }
    lines.splice(replacementStart, replacementEnd - replacementStart, ...replacement);
  } else {
    // No table at all — only handle the inline 综合结论：… label, promoting it
    // to the canonical heading.
    for (let i = 0; i < lines.length; i++) {
      const match = CONCLUSION_LABEL_RE.exec(lines[i] ?? "");
      if (!match) continue;
      lines[i] = MARKET_FLOW_COMBINED_TAIL_HEADING;
      lines.splice(i + 1, 0, "", (match[1] ?? "").trim());
      break;
    }
  }

  const deduped = stripDuplicateCombinedTail(lines);
  return collapseBlankLines(deduped.join("\n"));
}
