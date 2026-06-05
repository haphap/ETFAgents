import { isChinese } from "../schemas/rating.js";

export type AgentSignalValue = string | number | string[];

export interface AgentOutputSignal {
  source: string;
  agent: string;
  fields: Record<string, AgentSignalValue>;
  raw: string;
  decision_summary?: Record<string, string>;
  decision_summary_raw?: string;
  confidence?: number;
  key_drivers?: string[];
}

export type AgentSignalMap = Record<string, AgentOutputSignal>;

const SCHEMA_HEADING_RE = /(?:^|\n)\s*(?:\*\*)?(?:输出Schema|Output Schema)(?:\*\*)?\s*(?:\n|$)/g;
const SCHEMA_FIELD_RE = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:：]\s*(.*?)\s*$/;
const DECISION_SUMMARY_HEADING_RE =
  /(?:^|\n)\s*(?:\*\*)?(?:决策信号摘要|Decision Signal Summary)(?:\*\*)?\s*(?:\n|$)/g;
const DECISION_SUMMARY_FIELD_RE = /^\s*([^:：\n]{1,40})\s*[:：]\s*(.*?)\s*$/;
const NEXT_SECTION_RE =
  /^\s*(?:#{1,6}\s+\S|[一二三四五六七八九十]+、\S|（[一二三四五六七八九十]+）\S)/;

function lastSchemaIndex(text: string): number {
  let index = -1;
  for (const match of text.matchAll(SCHEMA_HEADING_RE)) {
    index = (match.index ?? 0) + match[0].length;
  }
  return index;
}

function lastSchemaHeadingIndex(text: string): number {
  let index = -1;
  for (const match of text.matchAll(SCHEMA_HEADING_RE)) {
    index = match.index ?? index;
  }
  return index;
}

function stripWrappingQuotes(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function parseArrayValue(value: string): string[] | null {
  const trimmed = value.trim();
  if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) return null;
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed.map((item) => String(item).trim()).filter(Boolean);
  } catch {
    // Fall through to a permissive comma split for model outputs with bare items.
  }
  return trimmed.slice(1, -1).split(/[,，]/).map(stripWrappingQuotes).filter(Boolean);
}

function parseSchemaValue(field: string, value: string): AgentSignalValue {
  const arrayValue = parseArrayValue(value);
  if (arrayValue) return arrayValue;
  const trimmed = stripWrappingQuotes(value);
  if (field === "confidence" || /^-?\d+(?:\.\d+)?$/.test(trimmed)) {
    const numeric = Number(trimmed);
    if (Number.isFinite(numeric)) return numeric;
  }
  return trimmed;
}

function readSchemaBlock(report: string): string {
  const start = lastSchemaIndex(report);
  if (start < 0) return "";
  const lines = report.slice(start).split(/\r?\n/);
  const block: string[] = [];
  let sawField = false;
  for (const line of lines) {
    if (NEXT_SECTION_RE.test(line) && sawField) break;
    if (!line.trim()) {
      if (sawField) break;
      continue;
    }
    if (!SCHEMA_FIELD_RE.test(line) && sawField) break;
    block.push(line);
    if (SCHEMA_FIELD_RE.test(line)) sawField = true;
  }
  return block.join("\n").trim();
}

function lastDecisionSummaryIndex(text: string): number {
  let index = -1;
  for (const match of text.matchAll(DECISION_SUMMARY_HEADING_RE)) {
    index = (match.index ?? 0) + match[0].length;
  }
  return index;
}

function readDecisionSummaryBlock(report: string): string {
  const start = lastDecisionSummaryIndex(report);
  if (start < 0) return "";
  const schemaStart = lastSchemaHeadingIndex(report);
  const end = schemaStart > start ? schemaStart : report.length;
  return report.slice(start, end).trim();
}

export function parseDecisionSignalSummary(
  report: string | undefined,
): { raw: string; fields: Record<string, string> } | null {
  if (!report?.trim()) return null;
  const raw = readDecisionSummaryBlock(report);
  if (!raw) return null;
  const fields: Record<string, string> = {};
  for (const line of raw.split(/\r?\n/)) {
    const match = DECISION_SUMMARY_FIELD_RE.exec(line);
    if (!match) continue;
    const [, field, value] = match;
    if (!field || value === undefined) continue;
    fields[field.trim()] = value.trim();
  }
  return { raw, fields };
}

export function stripAgentMachineBlocks(report: string | undefined): string {
  if (!report) return "";
  const normalized = report.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  let cut = normalized.length;
  const summaryStart = (() => {
    let best = -1;
    for (const match of normalized.matchAll(DECISION_SUMMARY_HEADING_RE)) {
      best = match.index ?? best;
    }
    return best;
  })();
  const schemaStart = (() => {
    let best = -1;
    for (const match of normalized.matchAll(SCHEMA_HEADING_RE)) {
      best = match.index ?? best;
    }
    return best;
  })();
  for (const idx of [summaryStart, schemaStart]) {
    if (idx >= 0) cut = Math.min(cut, idx);
  }
  return normalized
    .slice(0, cut)
    .replace(/\n[ \t]*\n[ \t]*$/g, "\n")
    .trim();
}

export function parseAgentOutputSchema(
  report: string | undefined,
  source: string,
): AgentOutputSignal | null {
  if (!report?.trim()) return null;
  const raw = readSchemaBlock(report);
  if (!raw) return null;

  const fields: Record<string, AgentSignalValue> = {};
  for (const line of raw.split(/\r?\n/)) {
    const match = SCHEMA_FIELD_RE.exec(line);
    if (!match) continue;
    const [, field, value] = match;
    if (!field || value === undefined) continue;
    fields[field] = parseSchemaValue(field, value);
  }
  const agent = typeof fields.agent === "string" && fields.agent ? fields.agent : source;
  const confidence = typeof fields.confidence === "number" ? fields.confidence : undefined;
  const keyDrivers = Array.isArray(fields.key_drivers) ? fields.key_drivers : undefined;
  const summary = parseDecisionSignalSummary(report);
  return {
    source,
    agent,
    fields,
    raw,
    ...(summary ? { decision_summary: summary.fields, decision_summary_raw: summary.raw } : {}),
    ...(confidence !== undefined ? { confidence } : {}),
    ...(keyDrivers ? { key_drivers: keyDrivers } : {}),
  };
}

export function mergeAgentSignals(
  previous: AgentSignalMap | undefined,
  next: AgentSignalMap | undefined,
): AgentSignalMap {
  return { ...(previous ?? {}), ...(next ?? {}) };
}

export function signalUpdate(source: string, report: string | undefined): AgentSignalMap {
  const signal = parseAgentOutputSchema(report, source);
  return signal ? { [source]: signal } : {};
}

export function formatAgentSignalsForPrompt(
  signals: AgentSignalMap | undefined,
  opts: { language?: string; include?: ReadonlyArray<string>; title?: string } = {},
): string {
  const include = opts.include ? new Set(opts.include) : null;
  const entries = Object.entries(signals ?? {}).filter(
    ([source, signal]) => signal && (!include || include.has(source)),
  );
  if (entries.length === 0) return "";

  const title =
    opts.title ?? (isChinese(opts.language) ? "## 结构化信号" : "## Structured Signals");
  const intro = isChinese(opts.language)
    ? "以下字段由各角色的决策信号摘要和输出Schema解析得到；优先作为机器可读状态使用，报告正文只用于核验证据。"
    : "These fields were parsed from each role's Decision Signal Summary and Output Schema; use them as machine-readable state and use the prose reports only to verify evidence.";
  const blocks = entries.map(([source, signal]) => {
    const fields = Object.entries(signal.fields)
      .map(([field, value]) => {
        const rendered = Array.isArray(value) ? JSON.stringify(value) : String(value);
        return `${field}: ${rendered}`;
      })
      .join("\n");
    const summary = signal.decision_summary
      ? Object.entries(signal.decision_summary)
          .map(([field, value]) => `${field}: ${value}`)
          .join("\n")
      : "";
    const summaryTitle = isChinese(opts.language) ? "决策信号摘要" : "Decision Signal Summary";
    const schemaTitle = isChinese(opts.language) ? "输出Schema字段" : "Output Schema Fields";
    return [
      `### ${source}`,
      summary ? `${summaryTitle}\n${summary}` : "",
      fields ? `${schemaTitle}\n${fields}` : "",
    ]
      .filter(Boolean)
      .join("\n\n");
  });
  return `${title}\n\n${intro}\n\n${blocks.join("\n\n")}`;
}
