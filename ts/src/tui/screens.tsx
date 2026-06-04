import { Box, Text } from "ink";
import type {
  AppState,
  ConfigField,
  ErrorDetail,
  ExecutionSummary,
  Phase,
  ReportDisplayLine,
  ReportMeta,
  SectionDef,
} from "./model.js";
import {
  ANALYST_IDS,
  backendDisplay,
  DEFAULT_SECTIONS,
  DEPTH_LABELS,
  DEPTH_OPTIONS,
  HOME_BANNER_FOOTER,
  HOME_BANNER_LINES,
  HOME_OPTIONS,
  HOME_SUBTITLE,
  LIBRARY_CARD_VIEWPORT,
  libraryTickers,
  MODELS_BY_PROVIDER,
  modelHasOptions,
  PROVIDERS,
  parseTickers,
  priceRuler,
  queueStatusLabel,
  reportDisplayViewport,
  reportsForTicker,
  sectionGroups,
  sparkline,
  TEAM_TABS,
} from "./model.js";

// ===========================================================================
// Home screen
// ===========================================================================

export function HomeScreen({ state }: { state: AppState }) {
  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Box flexDirection="column" width={78}>
        <HomeBanner />
        <Box flexDirection="column" alignItems="center">
          {HOME_OPTIONS.map((item, i) => {
            const active = i === state.homeIdx;
            const shortcut = homeShortcut(item.key);
            return (
              <Box key={item.key} justifyContent="center" width={52}>
                <Text
                  key={item.key}
                  bold={active}
                  {...(active ? { color: "cyan" as const } : { dimColor: true })}
                >
                  {active ? ">" : " "} [{shortcut}] {item.label} · {item.description}
                </Text>
              </Box>
            );
          })}
        </Box>
        <Box marginTop={2} justifyContent="center">
          <Box marginX={2}>
            <Text dimColor>↑↓ move</Text>
          </Box>
          <Box marginX={2}>
            <Text dimColor>Enter open</Text>
          </Box>
          <Box marginX={2}>
            <Text dimColor>? help</Text>
          </Box>
          <Box marginX={2}>
            <Text dimColor>Esc quit</Text>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

function HomeBanner() {
  return (
    <Box
      flexDirection="column"
      alignItems="center"
      borderStyle="single"
      borderColor="cyan"
      paddingX={2}
      paddingY={1}
      marginBottom={2}
    >
      {HOME_BANNER_LINES.map((line, i) => (
        <Text key={line} bold color={i < 6 ? "cyan" : "green"}>
          {line}
        </Text>
      ))}
      <Box marginTop={1} flexDirection="column" alignItems="center">
        <Text bold>{HOME_BANNER_FOOTER}</Text>
        <Text dimColor>{HOME_SUBTITLE}</Text>
      </Box>
    </Box>
  );
}

function homeShortcut(key: (typeof HOME_OPTIONS)[number]["key"]): string {
  switch (key) {
    case "ticker":
      return "r";
    case "library":
      return "l";
    case "backtest":
      return "b";
    case "paper":
      return "p";
  }
}

function fitText(value: unknown, width: number): string {
  const text = String(value ?? "—")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= width) return text;
  if (width <= 1) return text.slice(0, width);
  return `${text.slice(0, width - 1)}…`;
}

function MetaLine({ label, value }: { label: string; value: unknown }) {
  const labelText = `${label}:`;
  const valueWidth = Math.max(4, LEFT_CONTENT_WIDTH - labelText.length - 1);
  return (
    <Text dimColor>
      {labelText} {fitText(value, valueWidth)}
    </Text>
  );
}

// ===========================================================================
// Ticker screen
// ===========================================================================

export function TickerScreen({ state }: { state: AppState }) {
  const tickers = parseTickers(state.ticker);
  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Text bold>创建研究任务</Text>
      <Box marginY={1}>
        <Text dimColor>ETF 代码 </Text>
        <Text color="yellow">{state.ticker || "▌"}</Text>
      </Box>
      <Text dimColor>
        支持多个代码，用逗号或空格分隔
        {tickers.length > 0 ? ` · 已识别 ${tickers.length} 个` : ""}
      </Text>
      <Text dimColor>输入代码后按 Enter 配置分析参数</Text>

      {/* P3: watchlist cards derived from recent report history. */}
      {state.watchlist.length > 0 && (
        <Box flexDirection="column" marginTop={1} borderStyle="round" paddingX={2}>
          <Text bold>⭐ 自选 / 最近研究</Text>
          <Box marginTop={1} flexWrap="wrap">
            {state.watchlist.map((ticker, i) => (
              <Box key={ticker} marginRight={1}>
                <Text
                  {...(i === state.watchlistIdx ? { color: "cyan" as const, bold: true } : {})}
                  dimColor={i !== state.watchlistIdx}
                >
                  {i === state.watchlistIdx ? "▶ " : "  "}
                  {ticker}
                </Text>
              </Box>
            ))}
          </Box>
          <Text dimColor>↑↓ 选择 · Tab 加入输入</Text>
        </Box>
      )}
      <Box marginTop={1}>
        <Text dimColor>Ctrl+L 报告库 · Ctrl+B 回测 · Ctrl+P 模拟盘 · ? 帮助 · Esc 返回首页</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// Config modal
// ===========================================================================

export function ConfigModal({ state }: { state: AppState }) {
  const showModelSelect = modelHasOptions(state);
  const vllmPending = state.provider.toLowerCase() === "vllm" && state.vllmModels === null;
  const focus = (f: ConfigField) => state.focus === f;

  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Box flexDirection="column" borderStyle="round" paddingX={4} paddingY={1}>
        <Box marginBottom={1}>
          <Text bold>分析配置</Text>
          <Text dimColor> — {state.ticker}</Text>
        </Box>
        <FieldRow label="日期" value={state.date} focused={focus("date")} hint="YYYY-MM-DD" />
        <SelectFieldRow
          label="提供商"
          value={state.provider}
          focused={focus("provider")}
          open={state.selectOpen === "provider"}
          options={PROVIDERS}
          selectedIdx={state.selectIdx}
          hint="选择 LLM 提供商"
        />
        {showModelSelect ? (
          <SelectFieldRow
            label="模型"
            value={state.model}
            focused={focus("model")}
            open={state.selectOpen === "model"}
            options={
              state.provider.toLowerCase() === "vllm"
                ? (state.vllmModels ?? [])
                : (MODELS_BY_PROVIDER[state.provider.toLowerCase()] ?? [])
            }
            selectedIdx={state.selectIdx}
            hint="选择模型"
          />
        ) : vllmPending ? (
          <Box>
            <Text dimColor>{"模型".padEnd(6)}</Text>
            <Text color="yellow">正在获取 vllm 模型列表…</Text>
          </Box>
        ) : (
          <FieldRow
            label="模型"
            value={state.model}
            focused={focus("model")}
            hint={state.provider ? "输入模型名称" : "请先选择提供商"}
          />
        )}
        <SelectFieldRow
          label="研究深度"
          value={DEPTH_LABELS[state.depth]}
          focused={focus("depth")}
          open={state.selectOpen === "depth"}
          options={DEPTH_OPTIONS.map((opt) => DEPTH_LABELS[opt])}
          selectedIdx={state.selectIdx}
          hint="选择研究深度"
        />
        <AnalystToggleRow state={state} focused={focus("analysts")} />
        <RoundStepperRow
          label="辩论轮数"
          value={state.debateRounds}
          focused={focus("debateRounds")}
        />
        <RoundStepperRow label="风险轮数" value={state.riskRounds} focused={focus("riskRounds")} />
        <Box>
          <Text dimColor>{"后端".padEnd(8)}</Text>
          <Text dimColor>{backendDisplay(state.provider, state.backendUrl)}</Text>
        </Box>

        <Box marginTop={1} justifyContent="center">
          <Text color="green">Tab 切换字段 · Enter 开始分析</Text>
        </Box>
      </Box>
    </Box>
  );
}

function AnalystToggleRow({ state, focused }: { state: AppState; focused: boolean }) {
  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{"分析师".padEnd(6)}</Text>
        {focused ? (
          <Text color="yellow" dimColor>
            (←→ 移动 · 空格 开关)
          </Text>
        ) : (
          <Text dimColor>
            已选 {ANALYST_IDS.filter((id) => state.selectedAnalysts[id]).length}/
            {ANALYST_IDS.length}
          </Text>
        )}
      </Box>
      {focused && (
        <Box flexWrap="wrap" marginLeft={2}>
          {ANALYST_IDS.map((id, i) => {
            const on = state.selectedAnalysts[id] !== false;
            const title = DEFAULT_SECTIONS.find((s) => s.id === id)?.title ?? id;
            const isCursor = i === state.analystCursor;
            return (
              <Box key={id} marginRight={1}>
                <Text
                  {...(isCursor ? { color: "cyan" as const, bold: true } : {})}
                  dimColor={!isCursor}
                >
                  {on ? "☑" : "☐"} {title}
                </Text>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

function RoundStepperRow({
  label,
  value,
  focused,
}: {
  label: string;
  value: number;
  focused: boolean;
}) {
  return (
    <Box>
      <Text dimColor>{label.padEnd(8)}</Text>
      {focused ? (
        <Text color="yellow">
          ◀ {value} ▶ <Text dimColor>(←→ 调整)</Text>
        </Text>
      ) : (
        <Text>{value}</Text>
      )}
    </Box>
  );
}

function FieldRow({
  label,
  value,
  focused,
  hint,
}: {
  label: string;
  value: string;
  focused: boolean;
  hint: string;
}) {
  return (
    <Box>
      <Text dimColor>{label.padEnd(8)}</Text>
      {focused ? <Text color="yellow">{value || "▌"}</Text> : <Text>{value || hint}</Text>}
    </Box>
  );
}

function SelectFieldRow({
  label,
  value,
  focused,
  open,
  options,
  selectedIdx,
  hint,
}: {
  label: string;
  value: string;
  focused: boolean;
  open: boolean;
  options: readonly string[];
  selectedIdx: number;
  hint: string;
}) {
  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{label.padEnd(8)}</Text>
        {focused ? (
          <Text color="yellow">
            {value || (open ? "▾" : "▸")}{" "}
            <Text dimColor>{open ? "(↑↓ 选择, Enter 确认)" : "(Enter 展开)"}</Text>
          </Text>
        ) : (
          <Text>{value || hint}</Text>
        )}
      </Box>
      {open && (
        <Box flexDirection="column" marginLeft={2}>
          {options.map((opt, i) => {
            const color = i === selectedIdx ? "cyan" : undefined;
            return (
              <Text key={opt} {...(color ? { color } : {})}>
                {i === selectedIdx ? "▶ " : "  "}
                {opt === value ? (
                  <Text bold color="green">
                    {opt}
                  </Text>
                ) : (
                  <Text>{opt}</Text>
                )}
              </Text>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

// ===========================================================================
// Dashboard (Python-aligned layout)
// ===========================================================================

const LEFT_PANE_WIDTH = 26;
const LEFT_CONTENT_WIDTH = LEFT_PANE_WIDTH - 4;

export function Dashboard({
  state,
  elapsed,
  screenRows,
}: {
  state: AppState;
  elapsed: number;
  screenRows: number;
}) {
  const groups = sectionGroups(state.selectedAnalysts);
  const done = state.sectionDone;

  function countDone(key: string): number {
    return (groups[key] ?? []).filter((s) => done.has(s.id)).length;
  }
  function total(key: string): number {
    return (groups[key] ?? []).length;
  }

  const el = fmtElapsed(elapsed);

  // Totals reflect only the sections active for the current analyst selection.
  const activeSectionIds = Object.values(groups).flat();
  const agentsTotal = activeSectionIds.length;
  const agentsDone = activeSectionIds.filter((s) => done.has(s.id)).length;
  const reportsTotal = agentsTotal;
  const reportsDone = agentsDone;
  const viewportRows = Math.max(6, screenRows - 10);

  return (
    <Box flexDirection="column" flexGrow={1}>
      {/* Main two-column layout */}
      <Box flexDirection="row" flexGrow={1}>
        {/* Left pane */}
        <Box flexDirection="column" width={LEFT_PANE_WIDTH} borderStyle="single" paddingX={1}>
          {/* ETF card */}
          <Box flexDirection="column" marginBottom={1}>
            <Text bold>📊 基本信息</Text>
            {state.etfDetail?.loading ? (
              <Text dimColor>加载中…</Text>
            ) : state.etfDetail?.error ? (
              <Text color="red">{fitText(state.etfDetail.error, LEFT_CONTENT_WIDTH)}</Text>
            ) : (
              <>
                <Text>{fitText(state.etfDetail?.name || state.ticker, LEFT_CONTENT_WIDTH)}</Text>
                {state.etfDetail?.close !== undefined && (
                  <Text>
                    现价: <Text bold>{state.etfDetail.close.toFixed(3)}</Text>
                    {state.etfDetail.pctChg !== undefined && (
                      <Text
                        {...(state.etfDetail.pctChg > 0
                          ? { color: "red" as const }
                          : state.etfDetail.pctChg < 0
                            ? { color: "green" as const }
                            : {})}
                      >
                        {" "}
                        {state.etfDetail.pctChg > 0 ? "+" : ""}
                        {state.etfDetail.pctChg.toFixed(2)}%
                      </Text>
                    )}
                  </Text>
                )}
                {state.etfDetail?.history && state.etfDetail.history.length > 1 && (
                  <Text color="cyan">{sparkline(state.etfDetail.history, LEFT_CONTENT_WIDTH)}</Text>
                )}
                {(state.etfDetail?.high !== undefined || state.etfDetail?.low !== undefined) && (
                  <MetaLine
                    label="H/L"
                    value={`${state.etfDetail.high?.toFixed(3) ?? "—"}/${state.etfDetail.low?.toFixed(3) ?? "—"}`}
                  />
                )}
                {state.etfDetail?.volume !== undefined && (
                  <MetaLine
                    label="量"
                    value={`${Math.round(state.etfDetail.volume).toLocaleString()}${
                      state.etfDetail.volumeChangePct !== undefined
                        ? ` ${state.etfDetail.volumeChangePct > 0 ? "+" : ""}${state.etfDetail.volumeChangePct.toFixed(1)}%`
                        : ""
                    }`}
                  />
                )}
                <MetaLine label="日期" value={state.date} />
              </>
            )}
            {state.status === "running" ? (
              <Text color="yellow">分析中…</Text>
            ) : state.status === "done" ? (
              <Text color="green">分析完成</Text>
            ) : state.status === "error" ? (
              <Text color="red">分析失败</Text>
            ) : (
              <Text dimColor>等待中</Text>
            )}
          </Box>

          {/* Metadata */}
          <Box flexDirection="column" marginBottom={1}>
            <Text bold>📋 分析元数据</Text>
            <MetaLine label="日期" value={state.date} />
            <MetaLine label="提供商" value={state.provider || "—"} />
            <MetaLine label="模型" value={state.model || "—"} />
            <MetaLine
              label="标的"
              value={state.tickers.length || parseTickers(state.ticker).length}
            />
          </Box>

          {/* Cancel button */}
          <Box marginBottom={1}>
            {state.status === "running" ? (
              <Text dimColor>Esc 取消并返回首页</Text>
            ) : (
              <Text dimColor>Esc 返回首页</Text>
            )}
          </Box>

          {/* Queue — shows tickers being analyzed */}
          <Box flexDirection="column" flexGrow={1}>
            <Text bold>🧠 研究队列</Text>
            <Text dimColor>
              {state.status === "error"
                ? "🔴 "
                : state.status === "done"
                  ? "🟢 "
                  : state.status === "running"
                    ? "🟡 "
                    : "⚪ "}
              {state.queue.filter((item) => item.status === "done").length}/
              {state.queue.length || 1} ·{" "}
              {state.status === "error"
                ? "失败"
                : state.status === "done"
                  ? "完成"
                  : state.status === "running"
                    ? "运行"
                    : "等待"}
            </Text>
            <Box flexDirection="column" marginTop={1}>
              {state.queue.length > 0 ? (
                state.queue.slice(0, 8).map((item, index) => (
                  <Text key={item.ticker}>
                    <Text
                      {...(() => {
                        const color =
                          item.status === "done"
                            ? "green"
                            : item.status === "failed" || item.status === "cancelled"
                              ? "red"
                              : item.status === "running"
                                ? "yellow"
                                : undefined;
                        return color ? { color: color as "green" | "red" | "yellow" } : {};
                      })()}
                    >
                      {fitText(
                        `${index === state.currentTickerIdx ? "> " : "  "}${item.ticker}`,
                        14,
                      )}
                    </Text>
                    <Text dimColor> {fitText(queueStatusLabel(item.status), 4)}</Text>
                  </Text>
                ))
              ) : (
                <Text dimColor>等待分析启动…</Text>
              )}
            </Box>
          </Box>
        </Box>

        {/* Right pane */}
        <Box flexDirection="column" flexGrow={1} paddingLeft={1}>
          {/* Team tabs (top) */}
          <Box marginBottom={1} flexDirection="row" width="100%">
            {TEAM_TABS.map((tab, index) => (
              <TabButton
                key={tab.key}
                label={tab.label}
                done={countDone(tab.key)}
                total={total(tab.key)}
                active={state.activeTab === tab.key}
                marginRight={index === TEAM_TABS.length - 1 ? 0 : 1}
              />
            ))}
          </Box>

          {/* Tabbed section view + progress (bottom) */}
          <Box flexDirection="column" flexGrow={1}>
            <TabContent state={state} groups={groups} viewportRows={viewportRows} />
          </Box>
        </Box>
      </Box>

      {/* Stats bar */}
      <Box marginTop={1} justifyContent="space-between">
        <Text color="cyan">
          ◎ Agents {agentsDone}/{agentsTotal}{" "}
          {state.status === "running"
            ? "· 分析中"
            : state.status === "done"
              ? "· 完成"
              : state.status === "error"
                ? "· 错误"
                : "· 等待"}
        </Text>
        <Text dimColor>
          {state.activeSection
            ? `当前 ${DEFAULT_SECTIONS.find((s) => s.id === state.activeSection)?.title ?? state.activeSection}`
            : state.rating
              ? `评级 ${state.rating}`
              : "完整流水线"}
        </Text>
        <Text color="green">
          Nodes {state.stats.llm_calls} · Toolset {state.stats.tool_calls} · Reports {reportsDone}/
          {reportsTotal}
        </Text>
        <Text dimColor>{el} ←→ 团队 · Enter 团队详情 · PgUp/PgDn 滚动 · e 错误 · Esc 返回首页</Text>
      </Box>
    </Box>
  );
}

/**
 * Right-pane body. Shows the progress log for the analysts tab while running,
 * and the per-section report content for the selected team tab. Falls back to
 * the progress log until a section has produced output.
 */
function TabContent({
  state,
  groups,
  viewportRows,
}: {
  state: AppState;
  groups: Record<string, SectionDef[]>;
  viewportRows: number;
}) {
  const sections = groups[state.activeTab] ?? [];
  const tabMeta = TEAM_TABS.find((t) => t.key === state.activeTab);

  // P0: the selected section for this tab (default to the first section).
  const selectedId = state.selectedSectionByTab[state.activeTab] ?? sections[0]?.id;
  const selected = sections.find((s) => s.id === selectedId);
  const selectedStatus = selectedId ? (state.sectionStatus[selectedId] ?? "pending") : "pending";
  const selectedBody = selectedId ? (state.reports[selectedId] ?? "") : "";
  const scroll = selectedId ? (state.reportScrollBySection[selectedId] ?? 0) : 0;
  const summaryRows = state.activeTab === "decision" && state.executionSummary ? 9 : 0;
  const bodyRows = Math.max(4, viewportRows - summaryRows - 2);
  const bodyAreaRows = bodyRows + 2;
  const view = reportDisplayViewport(selectedBody, scroll, bodyRows);
  const runningLogs = state.logs.slice(-Math.max(0, bodyAreaRows - 1));
  const progressLogs = state.logs.slice(-Math.max(0, bodyAreaRows - 1));

  return (
    <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1}>
      <Box marginBottom={1}>
        <Text bold>{tabMeta?.label ?? "整体进度"}</Text>
        <Text dimColor> · </Text>
        <Text>{selected?.title ?? "整体进度"}</Text>
        <Text dimColor> · Enter 查看团队详情</Text>
      </Box>

      {state.activeTab === "decision" && state.executionSummary && (
        <ExecutionSummaryView
          summary={state.executionSummary}
          history={state.etfDetail?.history ?? []}
          current={state.etfDetail?.close}
        />
      )}
      {selected && selectedBody.trim() ? (
        <>
          <Text bold color="cyan">
            ── {selected.title} ── <Text dimColor>({selectedStatus})</Text>
          </Text>
          {view.lines.map((line, i) => (
            /* biome-ignore lint/suspicious/noArrayIndexKey: scrolled snapshot */
            <ReportLine key={`${selectedId}-${i}`} line={line} />
          ))}
          <Text dimColor>
            {view.atTop ? "顶部" : "↑"} · {view.atBottom ? "底部" : "↓"} ·{" "}
            {scroll + view.lines.length}/{view.total} 行 · PgUp/PgDn 滚动
          </Text>
          <BlankLines count={bodyAreaRows - view.lines.length - 2} prefix="report-pad" />
        </>
      ) : selectedStatus === "running" ? (
        <>
          <Text color="yellow">{selected?.title ?? ""} 运行中…</Text>
          {runningLogs.map((log, i) => (
            /* biome-ignore lint/suspicious/noArrayIndexKey: append-only log */
            <Text key={`${i}`} dimColor>
              • {log}
            </Text>
          ))}
          <BlankLines count={bodyAreaRows - runningLogs.length - 1} prefix="running-pad" />
        </>
      ) : selectedStatus === "failed" ? (
        <>
          <Text color="red">{selected?.title ?? ""} 失败</Text>
          <Text color="red">{state.errorMsg.slice(0, 200)}</Text>
          {state.errorDetail && <Text dimColor>按 e 查看错误详情</Text>}
          <BlankLines count={bodyAreaRows - (state.errorDetail ? 3 : 2)} prefix="failed-pad" />
        </>
      ) : (
        <>
          <Text dimColor>整体进度</Text>
          {state.logs.length > 0 ? (
            progressLogs.map((log, i) => (
              /* biome-ignore lint/suspicious/noArrayIndexKey: append-only log */
              <Text key={`${i}`} dimColor={log.startsWith("──") || log.startsWith("✓")}>
                {log.startsWith("──") || log.startsWith("✓") ? `  ${log}` : `• ${log}`}
              </Text>
            ))
          ) : (
            <Text dimColor>{selected ? `${selected.title} 等待中` : "准备开始分析。"}</Text>
          )}
          {state.status === "error" && (
            <Box marginTop={1} flexDirection="column">
              <Text color="red">{state.errorMsg.slice(0, 120)}</Text>
              {state.errorDetail && <Text dimColor>按 e 查看错误详情</Text>}
            </Box>
          )}
          <BlankLines
            count={
              bodyAreaRows -
              1 -
              (state.logs.length > 0 ? progressLogs.length : 1) -
              (state.status === "error" ? (state.errorDetail ? 2 : 1) : 0)
            }
            prefix="progress-pad"
          />
        </>
      )}
    </Box>
  );
}

function BlankLines({ count, prefix }: { count: number; prefix: string }) {
  return (
    <>
      {Array.from({ length: Math.max(0, count) }, (_, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-height terminal padding
        <Text key={`${prefix}-${index}`}> </Text>
      ))}
    </>
  );
}

function TabButton({
  label,
  done,
  total,
  active,
  marginRight,
}: {
  label: string;
  done: number;
  total: number;
  active: boolean;
  marginRight: number;
}) {
  return (
    <Box
      flexGrow={1}
      flexBasis={0}
      marginRight={marginRight}
      borderStyle={active ? "round" : "single"}
      borderColor={active ? "cyan" : undefined}
      borderDimColor={!active}
      paddingX={1}
      justifyContent="center"
      overflow="hidden"
    >
      <Text bold={active} {...(active ? { color: "cyan" as const } : {})}>
        {label}{" "}
        <Text color={done === total && total > 0 ? "green" : "yellow"}>
          ({done}/{total})
        </Text>
        {active ? " ▾" : " ▸"}
      </Text>
    </Box>
  );
}

function ExecutionSummaryView({
  summary,
  history,
  current,
}: {
  summary: ExecutionSummary;
  history: number[];
  current: number | undefined;
}) {
  const range =
    summary.targetWeightMinPct !== undefined && summary.targetWeightMaxPct !== undefined
      ? `${summary.targetWeightMinPct.toFixed(1)}%-${summary.targetWeightMaxPct.toFixed(1)}%`
      : summary.targetWeightPct !== undefined
        ? `${summary.targetWeightPct.toFixed(1)}%`
        : "—";
  const weight = summary.targetWeightPct ?? summary.targetWeightMaxPct ?? 0;
  const filled = Math.max(0, Math.min(12, Math.round((weight / 50) * 12)));
  const recent = history.filter((value) => Number.isFinite(value));
  const low = recent.length > 0 ? Math.min(...recent) : undefined;
  const high = recent.length > 0 ? Math.max(...recent) : undefined;
  const ruler =
    current !== undefined && summary.stopPrice !== undefined && summary.targetPrice !== undefined
      ? priceRuler(summary.stopPrice, current, summary.targetPrice)
      : "";
  const ratingTextColor = ratingColor(summary.rating);
  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1}>
      <Text bold color="cyan">
        ── 核心执行摘要 ──
      </Text>
      <Text>
        研报结论:{" "}
        <Text bold {...(ratingTextColor ? { color: ratingTextColor } : {})}>
          {ratingLabel(summary.rating)}
        </Text>{" "}
        · 推荐仓位: <Text color="cyan">{"█".repeat(filled)}</Text>
        <Text dimColor>{"░".repeat(12 - filled)}</Text> <Text bold>{range}</Text>
      </Text>
      <Text>
        价格趋势:{" "}
        {recent.length >= 2 ? (
          <Text color="cyan">{sparkline(recent, 44)}</Text>
        ) : (
          <Text dimColor>—</Text>
        )}
      </Text>
      <Text dimColor>
        区间: {low !== undefined ? fmtNum(low) : "—"} - {high !== undefined ? fmtNum(high) : "—"}
        {current !== undefined ? ` · 现价 ${fmtNum(current)}` : ""}
        {summary.stopPrice !== undefined ? ` · 止损 ${fmtNum(summary.stopPrice)}` : ""}
        {summary.targetPrice !== undefined ? ` · 目标 ${fmtNum(summary.targetPrice)}` : ""}
      </Text>
      <Text dimColor>{ruler || "价格标尺: 等待目标价与止损价"}</Text>
      <Text dimColor>执行节奏: {summary.executionDelay || "—"}</Text>
      <SummaryLine label="加仓依据" values={summary.addConditions} />
      <SummaryLine label="减仓依据" values={summary.reduceConditions} />
      <SummaryLine label="风控规则" values={summary.riskControls} />
    </Box>
  );
}

function ratingLabel(rating: string | undefined): string {
  switch ((rating ?? "").toUpperCase()) {
    case "BUY":
      return "买入";
    case "OVERWEIGHT":
      return "增持";
    case "HOLD":
      return "持有";
    case "UNDERWEIGHT":
      return "减持";
    case "SELL":
      return "卖出";
    default:
      return rating || "—";
  }
}

function ratingColor(rating: string | undefined): "green" | "yellow" | "red" | undefined {
  switch ((rating ?? "").toUpperCase()) {
    case "BUY":
    case "OVERWEIGHT":
      return "green";
    case "SELL":
    case "UNDERWEIGHT":
      return "red";
    case "HOLD":
      return "yellow";
    default:
      return undefined;
  }
}

function SummaryLine({ label, values }: { label: string; values: string[] }) {
  return (
    <Text dimColor>
      {label}: {values.length > 0 ? values.join("；").slice(0, 112) : "—"}
    </Text>
  );
}

const NUMBER_TOKEN_RE =
  /(\d{4}-\d{2}-\d{2}|[+-]?\d+(?:\.\d+)?\s*(?:%|％|倍|万手|亿份|元|日|天|周|月)?)/g;
const NUMBER_TOKEN_TEST_RE =
  /^(\d{4}-\d{2}-\d{2}|[+-]?\d+(?:\.\d+)?\s*(?:%|％|倍|万手|亿份|元|日|天|周|月)?)$/;

function ReportLine({ line }: { line: ReportDisplayLine }) {
  if (line.kind === "blank") return <Text> </Text>;
  const text = line.text.trimEnd();
  if (line.kind === "heading") {
    return (
      <Text bold color="cyan">
        {text}
      </Text>
    );
  }
  if (line.kind === "subheading") {
    return (
      <Text bold {...(line.level && line.level <= 3 ? { color: "cyan" as const } : {})}>
        {text}
      </Text>
    );
  }
  if (line.kind === "table") {
    return <Text dimColor>{text}</Text>;
  }
  if (line.kind === "quote") {
    return <Text dimColor>│ {text}</Text>;
  }
  if (line.kind === "code") {
    return <Text dimColor>{`  ${text}`}</Text>;
  }
  if (line.kind === "bullet" || line.kind === "ordered") {
    return (
      <Text>
        <HighlightedText text={text} />
      </Text>
    );
  }
  return (
    <Text>
      <HighlightedText text={text} />
    </Text>
  );
}

function HighlightedText({ text }: { text: string }) {
  const parts = text.split(NUMBER_TOKEN_RE);
  return (
    <>
      {parts.map((part, i) => {
        if (!part) return null;
        const isNumber = NUMBER_TOKEN_TEST_RE.test(part);
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: split text fragments are stable for a line
          <Text key={i} bold={isNumber} {...(isNumber ? { color: "yellow" as const } : {})}>
            {part}
          </Text>
        );
      })}
    </>
  );
}

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// ===========================================================================
// P2: Report library screen
// ===========================================================================

export function ReportLibrary({ state }: { state: AppState }) {
  const { reports, selectedIdx, loading, error, pane, cardOffset } = state.library;
  const tickers = libraryTickers(reports);
  const selected = reports[selectedIdx];
  const selectedTicker = selected?.ticker ?? tickers[0];
  const tickerReports = reportsForTicker(reports, selectedTicker);
  const selectedWithin = Math.max(
    0,
    tickerReports.findIndex((report) => report.path === selected?.path),
  );
  const tickerIndex = Math.max(0, tickers.indexOf(selectedTicker ?? ""));
  const tickerOffset = Math.max(0, Math.min(Math.max(0, tickerIndex - 8), tickers.length - 18));
  const visibleReports = tickerReports.slice(cardOffset, cardOffset + LIBRARY_CARD_VIEWPORT);

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      <Text bold>📚 报告库</Text>
      <Box flexDirection="row" flexGrow={1} marginTop={1}>
        {/* Left: ticker list */}
        <Box flexDirection="column" width={28} borderStyle="single" paddingX={1}>
          <Text bold {...(pane === "tickers" ? { color: "cyan" as const } : {})}>
            股票代码
          </Text>
          {loading ? (
            <Text dimColor>加载中…</Text>
          ) : error ? (
            <Text color="red">{error.slice(0, 24)}</Text>
          ) : reports.length === 0 ? (
            <Text dimColor>暂无报告</Text>
          ) : (
            tickers.slice(tickerOffset, tickerOffset + 18).map((ticker) => {
              const active = ticker === selectedTicker;
              const count = reportsForTicker(reports, ticker).length;
              return (
                <Text
                  key={ticker}
                  {...(active ? { color: "cyan" as const, bold: true } : {})}
                  dimColor={!active}
                >
                  {active ? "▶ " : "  "}
                  {ticker.padEnd(12)} {String(count).padStart(2)} 份
                </Text>
              );
            })
          )}
          <Box marginTop={1}>
            <Text dimColor>←→ 切换区域 · ↑↓ 选择 · r 刷新 · Esc 返回首页</Text>
          </Box>
        </Box>

        {/* Right: report cards */}
        <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1} marginLeft={1}>
          {selectedTicker && (
            <Text bold {...(pane === "reports" ? { color: "cyan" as const } : {})}>
              {selectedTicker} · {tickerReports.length} 份报告
            </Text>
          )}
          {reports.length === 0 && !loading ? (
            <Text dimColor>暂无可展示的历史报告。</Text>
          ) : (
            <>
              {visibleReports.map((report) => (
                <ReportCard
                  key={report.path}
                  report={report}
                  active={report.path === selected?.path}
                  focused={pane === "reports"}
                />
              ))}
              <Text dimColor>
                {tickerReports.length > LIBRARY_CARD_VIEWPORT
                  ? `${selectedWithin + 1}/${tickerReports.length} · PgUp/PgDn 快速移动 · `
                  : ""}
                Enter 阅读全文 · Esc 返回首页
              </Text>
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
}

function ReportCard({
  report,
  active,
  focused,
}: {
  report: ReportMeta;
  active: boolean;
  focused: boolean;
}) {
  const color = active ? "cyan" : undefined;
  const rating = ratingLabel(report.rating);
  const ratingTextColor = reportRatingColor(report.rating);
  return (
    <Box
      flexDirection="column"
      borderStyle={active ? "round" : "single"}
      borderColor={color}
      borderDimColor={!active}
      paddingX={1}
      marginTop={1}
    >
      <Box justifyContent="space-between">
        <Text bold={active} {...(color ? { color } : {})}>
          {active ? "▶ " : "  "}
          {report.date}
        </Text>
        <Text bold={active} {...(ratingTextColor ? { color: ratingTextColor } : {})}>
          {rating}
        </Text>
      </Box>
      <Text>
        <Text dimColor>分析师建议: </Text>
        {fitText(report.recommendation, 104)}
      </Text>
      <Text>
        <Text dimColor>操作策略: </Text>
        {fitText(report.strategy, 106)}
      </Text>
      <Text>
        <Text dimColor>风控: </Text>
        {fitText(report.riskControls, 110)}
      </Text>
      {active && focused && <Text dimColor>Enter 打开阅读弹窗</Text>}
    </Box>
  );
}

function reportRatingColor(rating: string | undefined): "green" | "yellow" | "red" | undefined {
  switch ((rating ?? "").toUpperCase()) {
    case "买入":
    case "BUY":
    case "增持":
    case "OVERWEIGHT":
      return "green";
    case "卖出":
    case "SELL":
    case "减持":
    case "UNDERWEIGHT":
      return "red";
    case "持有":
    case "HOLD":
      return "yellow";
    default:
      return undefined;
  }
}

export function ReportReaderOverlay({
  state,
  columns = 120,
  rows = 32,
}: {
  state: AppState;
  columns?: number;
  rows?: number;
}) {
  const report = state.library.reports[state.library.selectedIdx];
  const width = Math.max(72, Math.min(118, columns - 8));
  const viewport = Math.max(8, Math.min(24, rows - 10));
  const view = reportDisplayViewport(state.library.body, state.library.scroll, viewport, width - 6);
  return (
    <Box flexDirection="column" width={width} borderStyle="single" paddingX={2} paddingY={1}>
      <Box justifyContent="space-between">
        <Text bold color="cyan">
          {report ? `${report.ticker} · ${report.date}` : "报告阅读"}
        </Text>
        <Text dimColor>Esc 关闭</Text>
      </Box>
      {state.library.bodyLoading ? (
        <Text dimColor>读取中…</Text>
      ) : state.library.body ? (
        <>
          <Box flexDirection="column" marginTop={1}>
            {view.lines.map((line, i) => (
              /* biome-ignore lint/suspicious/noArrayIndexKey: scrolled snapshot */
              <ReportLine key={`reader-${i}`} line={line} />
            ))}
          </Box>
          <Text dimColor>
            {view.atTop ? "顶部" : "↑"} · {view.atBottom ? "底部" : "↓"} ·{" "}
            {view.scroll + view.lines.length}/{view.total} 行 · PgUp/PgDn 滚动
          </Text>
        </>
      ) : (
        <Text dimColor>暂无正文。</Text>
      )}
    </Box>
  );
}

// ===========================================================================
// P4: Backtest viewer screen
// ===========================================================================

function fmtPct(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(2)}%` : "—";
}
function fmtNum(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(4) : "—";
}

export function BacktestScreen({ state }: { state: AppState }) {
  const { records, selectedIdx, view, loading, error } = state.backtest;
  const selected = records[selectedIdx];
  const metrics = view?.metrics ?? {};
  const health = view?.health ?? null;
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      <Text bold>📈 回测结果</Text>
      <Box flexDirection="row" flexGrow={1} marginTop={1}>
        <Box flexDirection="column" width={28} borderStyle="single" paddingX={1}>
          <Text bold>回测记录</Text>
          {loading ? (
            <Text dimColor>加载中…</Text>
          ) : error ? (
            <Text color="red">{error.slice(0, 24)}</Text>
          ) : records.length === 0 ? (
            <Text dimColor>暂无回测产物</Text>
          ) : (
            records.slice(0, 16).map((r, i) => (
              <Text
                key={r.path}
                {...(i === selectedIdx ? { color: "cyan" as const, bold: true } : {})}
                dimColor={i !== selectedIdx}
              >
                {i === selectedIdx ? "▶ " : "  "}
                {(r.tickers[0] ?? "?").padEnd(12)} {r.startDate}
              </Text>
            ))
          )}
          <Box marginTop={1}>
            <Text dimColor>↑↓ 选择 · r 刷新 · Esc 返回首页</Text>
          </Box>
        </Box>
        <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1} marginLeft={1}>
          {selected ? (
            <>
              <Text bold color="cyan">
                {selected.tickers.join(", ") || "?"} · {selected.startDate} → {selected.endDate}
              </Text>
              {view && view.nav.length > 1 && <Text color="cyan">{sparkline(view.nav, 40)}</Text>}
              <Box flexDirection="column" marginTop={1}>
                <Text>最终净值: {fmtNum(metrics.final_value)}</Text>
                <Text>累计收益: {fmtPct(metrics.cumulative_return)}</Text>
                <Text>年化收益: {fmtPct(metrics.annualized_return)}</Text>
                <Text>最大回撤: {fmtPct(metrics.max_drawdown)}</Text>
                <Text>夏普比率: {fmtNum(metrics.sharpe_ratio)}</Text>
                <Text>交易笔数: {String(metrics.total_trades ?? view?.trades ?? "—")}</Text>
              </Box>
              {view && view.benchmarkMetrics.length > 0 && (
                <Box flexDirection="column" marginTop={1}>
                  <Text bold>基准对比</Text>
                  {view.benchmarkMetrics.slice(0, 3).map((b, i) => (
                    <Text key={String(b.benchmark ?? i)} dimColor>
                      {String(b.benchmark ?? "?")}: 累计 {fmtPct(b.cumulative_return)} · 超额{" "}
                      {fmtPct(b.excess_cumulative_return)}
                    </Text>
                  ))}
                </Box>
              )}
              {health && Array.isArray(health.warnings) && health.warnings.length > 0 && (
                <Box flexDirection="column" marginTop={1}>
                  <Text bold color="yellow">
                    ⚠ 健康提示
                  </Text>
                  {(health.warnings as unknown[]).slice(0, 4).map((w, i) => (
                    /* biome-ignore lint/suspicious/noArrayIndexKey: static list */
                    <Text key={`w-${i}`} color="yellow">
                      • {String(w).slice(0, 80)}
                    </Text>
                  ))}
                </Box>
              )}
            </>
          ) : (
            <Text dimColor>选择左侧回测记录查看详情。</Text>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// ===========================================================================
// P5: Paper trading screen
// ===========================================================================

export function PaperScreen({ state }: { state: AppState }) {
  const { account, positions, trades, loading, error, user } = state.paper;
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      <Text bold>💼 模拟交易{user ? ` · ${user}` : ""}</Text>
      {loading ? (
        <Text dimColor>加载中…</Text>
      ) : error ? (
        <Text color="red">{error}</Text>
      ) : (
        <Box flexDirection="column" marginTop={1}>
          {account && (
            <Box flexDirection="column" marginBottom={1}>
              <Text bold>账户</Text>
              <Text>
                总资产: {fmtNum(account.total_assets)} · 现金: {fmtNum(account.cash)} · 市值:{" "}
                {fmtNum(account.market_value)}
              </Text>
              <Text dimColor>
                已实现盈亏: {fmtNum(account.realized_pnl)} · 浮动盈亏:{" "}
                {fmtNum(account.unrealized_pnl)}
              </Text>
            </Box>
          )}
          <Text bold>持仓 ({positions.length})</Text>
          {positions.length === 0 ? (
            <Text dimColor>无持仓</Text>
          ) : (
            positions.slice(0, 10).map((p) => (
              <Text key={String(p.ticker)}>
                {String(p.ticker).padEnd(12)} 数量 {String(p.quantity)} · 现价{" "}
                {fmtNum(p.current_price)} · 盈亏 {fmtPct(p.pnl_pct)}
              </Text>
            ))
          )}
          <Box marginTop={1} flexDirection="column">
            <Text bold>最近成交 ({trades.length})</Text>
            {trades.slice(0, 8).map((t) => (
              <Text key={String(t.id)} dimColor>
                {String(t.created_at).slice(0, 10)} {String(t.side)} {String(t.ticker)} ×{" "}
                {String(t.quantity)} @ {fmtNum(t.price)}
              </Text>
            ))}
          </Box>
        </Box>
      )}
      <Box marginTop={1}>
        <Text dimColor>r 刷新 · Esc 返回首页</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// Team detail overlay
// ===========================================================================

export function TeamDetailOverlay({ state }: { state: AppState }) {
  const groups = sectionGroups(state.selectedAnalysts);
  const sections = groups[state.activeTab] ?? [];
  const tabMeta = TEAM_TABS.find((t) => t.key === state.activeTab);
  const selectedId = state.selectedSectionByTab[state.activeTab] ?? sections[0]?.id;
  const done = sections.filter((section) => state.sectionDone.has(section.id)).length;

  return (
    <Box
      flexDirection="column"
      borderStyle="double"
      borderColor="cyan"
      paddingX={2}
      paddingY={1}
      marginTop={1}
      width={56}
    >
      <Text bold color="cyan">
        {tabMeta?.label ?? "团队详情"} ({done}/{sections.length})
      </Text>
      <Box flexDirection="column" marginTop={1}>
        {sections.length === 0 ? (
          <Text dimColor>当前团队没有可选章节。</Text>
        ) : (
          sections.map((section) => {
            const status = state.sectionStatus[section.id] ?? "pending";
            const isDone = status === "done";
            const hasBody = Boolean(state.reports[section.id]?.trim());
            const isSelected = section.id === selectedId;
            const mark =
              status === "done"
                ? "✓"
                : status === "failed"
                  ? "×"
                  : status === "running"
                    ? "◐"
                    : state.status === "running"
                      ? "○"
                      : "·";
            const colorProps = isSelected
              ? { color: "cyan" as const }
              : isDone
                ? { color: "green" as const }
                : status === "failed"
                  ? { color: "red" as const }
                  : hasBody || status === "running"
                    ? { color: "yellow" as const }
                    : {};
            return (
              <Text
                key={section.id}
                bold={isSelected}
                dimColor={!isSelected && !isDone && !hasBody}
                {...colorProps}
              >
                {isSelected ? "> " : "  "}
                {mark} {section.title}
              </Text>
            );
          })
        )}
      </Box>
      <Box marginTop={1}>
        <Text dimColor>↑↓ 选择章节 · ←→ 切团队 · Enter/Esc 关闭</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// Help overlay
// ===========================================================================

export function HelpOverlay({ phase }: { phase: Phase }) {
  const shared = "? 帮助 · Esc 返回首页 · Ctrl+C 退出";
  const lines: Record<Phase, string[]> = {
    home: [
      "↑↓ 选择入口",
      "Enter 打开",
      "r/l/b/p 快速进入研究/报告/回测/模拟盘",
      "Esc / Ctrl+C 退出",
    ],
    ticker: ["输入 ETF 代码，逗号或空格分隔", "Enter 配置分析", "Tab 加入选中的最近研究", shared],
    config: [
      "Tab 切换字段",
      "Enter 展开选择或开始分析",
      "←→ 调整分析师/轮数",
      "Esc 关闭下拉或返回输入 · Ctrl+C 退出",
    ],
    dashboard: [
      "←→ 切换团队",
      "Enter 打开团队详情",
      "详情中 ↑↓ 选择章节",
      "PgUp/PgDn 滚动正文",
      "Esc 取消并返回首页 · Ctrl+C 退出",
    ],
    library: [
      "←→/Tab 切换代码与报告卡片",
      "↑↓ 选择代码或日期卡片",
      "Enter 打开阅读弹窗",
      "弹窗中 PgUp/PgDn 滚动正文，Esc 关闭",
      "r 刷新",
      shared,
    ],
    backtest: ["↑↓ 选择回测记录", "r 刷新", shared],
    paper: ["r 刷新账户快照", shared],
  };
  return (
    <Box flexDirection="column" borderStyle="single" paddingX={2} paddingY={1} marginTop={1}>
      <Text bold>帮助</Text>
      {(lines[phase] ?? lines.home).map((line) => (
        <Text key={line} dimColor>
          {line}
        </Text>
      ))}
      <Box marginTop={1}>
        <Text dimColor>按任意键关闭</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// P6: Error detail overlay
// ===========================================================================

export function ErrorDetailOverlay({ detail }: { detail: ErrorDetail }) {
  return (
    <Box
      flexDirection="column"
      borderStyle="double"
      borderColor="red"
      paddingX={2}
      paddingY={1}
      marginTop={1}
    >
      <Text bold color="red">
        ✗ 错误详情
      </Text>
      {detail.ticker && <Text>标的: {detail.ticker}</Text>}
      {detail.section && <Text>章节: {detail.section}</Text>}
      <Text dimColor>时间: {detail.timestamp}</Text>
      <Box marginTop={1}>
        <Text>{detail.message.slice(0, 400)}</Text>
      </Box>
      {detail.stack && (
        <Box flexDirection="column" marginTop={1}>
          <Text dimColor>调用栈:</Text>
          {detail.stack
            .split("\n")
            .slice(0, 8)
            .map((line, i) => (
              /* biome-ignore lint/suspicious/noArrayIndexKey: static stack snapshot */
              <Text key={`stk-${i}`} dimColor>
                {line.slice(0, 110)}
              </Text>
            ))}
        </Box>
      )}
      <Box marginTop={1}>
        <Text dimColor>按任意键关闭</Text>
      </Box>
    </Box>
  );
}
