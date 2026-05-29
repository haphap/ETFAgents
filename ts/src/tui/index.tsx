#!/usr/bin/env node
/**
 * etfagents-ts TUI — Python-aligned analysis console.
 *
 * Layout matches cli/tui/screens/research.py AnalysisRunScreen:
 *   Left pane (22ch): ETF card, metadata, cancel, queue
 *   Right top: team tabs (分析团队|研究|风险|决策) with counts
 *   Right bottom: overall progress + scrollable report
 *   Stats bar: Agents | LLM · Tools | Reports | timer
 */

import { Box, render, Text, useInput } from "ink";
import { useEffect, useReducer, useRef, useState } from "react";
import type { LlmOptions } from "../llm/factory.js";

// ===========================================================================
// Banner
// ===========================================================================

const BANNER = [
  "╔══════════════════════════════════════════════╗",
  "║                                              ║",
  "║   _____ _____ _____ _                    _   ║",
  "║  | ____|_   _|  ___/ \\   __ _  ___ _ __ | |_ ║",
  "║  |  _|   | | | |_ / _ \\ / _` |/ _ \\ '_ \\| __|║",
  "║  | |___  | | |  _/ ___ \\ (_| |  __/ | | | |_\\__ \\ ║",
  "║  |_____| |_| |_|/_/   \\_\\__, |\\___|_| |_|\\__|___/║",
  "║                         |___/                 ║",
  "║                                              ║",
  "║      Multi-Agent ETF Investment Framework     ║",
  "║               TypeScript Edition              ║",
  "║                                              ║",
  "╚══════════════════════════════════════════════╝",
];

// ===========================================================================
// Provider / Model catalog
// ===========================================================================

const PROVIDERS = ["openai", "deepseek", "ollama", "xai", "openrouter", "minimax", "vllm"] as const;

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3", "o4-mini"],
  deepseek: ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro"],
  ollama: ["llama3.2", "qwen2.5", "mistral", "gemma3"],
  xai: ["grok-3-beta", "grok-3-mini"],
  openrouter: [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-chat",
  ],
  minimax: ["abab6.5s-chat", "abab7-chat"],
  vllm: [],
};

// ===========================================================================
// Team section definitions (matches Python SECTION_DEFINITIONS)
// ===========================================================================

interface SectionDef {
  id: string;
  title: string;
  team: "分析师" | "研究" | "风险" | "决策";
}

const DEFAULT_SECTIONS: SectionDef[] = [
  { id: "catalyst_sentiment", title: "催化剂与情绪分析", team: "分析师" },
  { id: "macro_regime", title: "宏观环境分析", team: "分析师" },
  { id: "meso_commodity", title: "行业与商品分析", team: "分析师" },
  { id: "holdings_industry", title: "持仓行业归因", team: "分析师" },
  { id: "top_holdings", title: "头部持仓分析", team: "分析师" },
  { id: "market_flow", title: "行情数据综合分析", team: "分析师" },
  { id: "bull_researcher", title: "多头研究", team: "研究" },
  { id: "bear_researcher", title: "空头研究", team: "研究" },
  { id: "trader", title: "交易信号生成", team: "风险" },
  { id: "risk_debate", title: "风险辩论", team: "风险" },
  { id: "portfolio_manager", title: "投资组合建议", team: "决策" },
];

function sectionGroups(): Record<string, SectionDef[]> {
  return {
    analysts: DEFAULT_SECTIONS.filter((d) => d.team === "分析师"),
    research: DEFAULT_SECTIONS.filter((d) => d.team === "研究"),
    risk: DEFAULT_SECTIONS.filter((d) => d.team === "风险"),
    decision: DEFAULT_SECTIONS.filter((d) => d.team === "决策"),
  };
}

// ===========================================================================
// State
// ===========================================================================

type Phase = "ticker" | "config" | "dashboard";
type ConfigField = "date" | "provider" | "model";

interface AppState {
  phase: Phase;
  ticker: string;
  date: string;
  provider: string;
  model: string;
  /** Config modal state */
  focus: ConfigField;
  selectOpen: ConfigField | null;
  selectIdx: number;
  /** Dashboard state */
  status: "idle" | "running" | "done" | "error";
  result: string;
  errorMsg: string;
  logs: string[];
  /** Section completion tracking */
  sectionDone: Set<string>;
  /** Stats from analysis runner */
  stats: { llm_calls: number; tool_calls: number; tokens: number };
  /** ETF detail loaded from bridge (basic info card) */
  etfDetail: {
    name?: string;
    close?: number;
    pctChg?: number;
    loading: boolean;
    error?: string;
  } | null;
  /** vllm */
  vllmModels: string[] | null;
}

type Action =
  | { type: "appendTicker"; char: string }
  | { type: "deleteTicker" }
  | { type: "openConfig" }
  | { type: "setFocus"; focus: ConfigField }
  | { type: "appendChar"; char: string }
  | { type: "deleteChar" }
  | { type: "openSelect" }
  | { type: "closeSelect" }
  | { type: "selectUp" }
  | { type: "selectDown" }
  | { type: "selectPick" }
  | { type: "startAnalysis" }
  | { type: "appendLog"; msg: string }
  | { type: "sectionDone"; sectionId: string }
  | { type: "analysisDone"; result: string }
  | { type: "analysisError"; msg: string }
  | { type: "backToTicker" }
  | { type: "etfDetailLoading" }
  | { type: "etfDetailLoaded"; name?: string; close?: number; pctChg?: number }
  | { type: "etfDetailError"; error: string }
  | { type: "vllmModelsFetched"; models: string[] }
  | { type: "vllmModelsFailed" };

// ===========================================================================
// Helpers
// ===========================================================================

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function initState(): AppState {
  return {
    phase: "ticker",
    ticker: "",
    date: today(),
    provider: "",
    model: "",
    focus: "date",
    selectOpen: null,
    selectIdx: 0,
    status: "idle",
    result: "",
    errorMsg: "",
    logs: [],
    sectionDone: new Set(),
    stats: { llm_calls: 0, tool_calls: 0, tokens: 0 },
    etfDetail: null,
    vllmModels: null,
  };
}

function focusValue(state: AppState): string {
  switch (state.focus) {
    case "date":
      return state.date;
    case "provider":
      return state.provider;
    case "model":
      return state.model;
  }
}

function selectOptions(state: AppState): string[] {
  if (state.selectOpen === "provider") return [...PROVIDERS];
  if (state.selectOpen === "model") {
    const p = state.provider.toLowerCase();
    if (p === "vllm") return state.vllmModels ?? [];
    return MODELS_BY_PROVIDER[p] ?? [];
  }
  return [];
}

function modelHasOptions(state: AppState): boolean {
  if (!state.provider) return false;
  const p = state.provider.toLowerCase();
  if (p === "vllm") return (state.vllmModels?.length ?? 0) > 0;
  return (MODELS_BY_PROVIDER[p]?.length ?? 0) > 0;
}

function isSelectField(state: AppState, field: ConfigField): boolean {
  if (field === "provider") return true;
  if (field === "model") return modelHasOptions(state);
  return false;
}

const FOCUS_ORDER: ConfigField[] = ["date", "provider", "model"];
function nextFocus(current: ConfigField): ConfigField {
  const i = FOCUS_ORDER.indexOf(current);
  return FOCUS_ORDER[i + 1] ?? FOCUS_ORDER[0] ?? "date";
}

// ===========================================================================
// Reducer
// ===========================================================================

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "appendTicker":
      return { ...state, ticker: state.ticker + action.char };
    case "deleteTicker":
      return { ...state, ticker: state.ticker.slice(0, -1) };
    case "openConfig":
      return {
        ...state,
        phase: "config",
        focus: "date",
        selectOpen: null,
        selectIdx: 0,
        vllmModels: null,
        errorMsg: "",
        status: "idle",
        logs: [],
        result: "",
        sectionDone: new Set(),
        stats: { llm_calls: 0, tool_calls: 0, tokens: 0 },
      };
    case "setFocus":
      return {
        ...state,
        focus: action.focus,
        selectOpen: isSelectField(state, action.focus) ? action.focus : null,
        selectIdx: 0,
      };
    case "appendChar": {
      if (state.selectOpen !== null) return state;
      const key = state.focus;
      return { ...state, [key]: focusValue(state) + action.char };
    }
    case "deleteChar": {
      if (state.selectOpen !== null) return state;
      const key = state.focus;
      return { ...state, [key]: focusValue(state).slice(0, -1) };
    }
    case "openSelect": {
      if (!isSelectField(state, state.focus)) return state;
      const idx = selectOptions({ ...state, selectOpen: state.focus }).indexOf(focusValue(state));
      return { ...state, selectOpen: state.focus, selectIdx: idx >= 0 ? idx : 0 };
    }
    case "closeSelect":
      return { ...state, selectOpen: null, selectIdx: 0 };
    case "selectUp": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      if (opts.length === 0) return state;
      return { ...state, selectIdx: state.selectIdx > 0 ? state.selectIdx - 1 : opts.length - 1 };
    }
    case "selectDown": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      if (opts.length === 0) return state;
      return { ...state, selectIdx: state.selectIdx < opts.length - 1 ? state.selectIdx + 1 : 0 };
    }
    case "selectPick": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      const value = opts[state.selectIdx];
      if (value === undefined) return { ...state, selectOpen: null, selectIdx: 0 };
      const newProvider = state.selectOpen === "provider" ? value : state.provider;
      const newModel = state.selectOpen === "provider" ? "" : state.model;
      const vllmModels =
        state.selectOpen === "provider" && newProvider.toLowerCase() !== "vllm"
          ? null
          : state.vllmModels;
      return {
        ...state,
        provider: newProvider,
        model: newModel,
        [state.selectOpen]: value,
        selectOpen: null,
        selectIdx: 0,
        vllmModels,
      };
    }
    case "startAnalysis":
      return {
        ...state,
        phase: "dashboard",
        status: "running",
        result: "",
        errorMsg: "",
        logs: [],
        sectionDone: new Set(),
        stats: { llm_calls: 0, tool_calls: 0, tokens: 0 },
      };
    case "appendLog":
      return { ...state, logs: [...state.logs, action.msg] };
    case "sectionDone": {
      const next = new Set(state.sectionDone);
      next.add(action.sectionId);
      return { ...state, sectionDone: next };
    }
    case "analysisDone": {
      // Mark all sections done
      const allDone = new Set(state.sectionDone);
      for (const s of DEFAULT_SECTIONS) allDone.add(s.id);
      return { ...state, status: "done", result: action.result, sectionDone: allDone };
    }
    case "analysisError":
      return { ...state, status: "error", errorMsg: action.msg };
    case "backToTicker":
      return { ...state, phase: "ticker", errorMsg: "", selectOpen: null, selectIdx: 0 };
    case "etfDetailLoading":
      return { ...state, etfDetail: { loading: true } };
    case "etfDetailLoaded":
      return {
        ...state,
        etfDetail: {
          loading: false,
          ...(action.name !== undefined ? { name: action.name } : {}),
          ...(action.close !== undefined ? { close: action.close } : {}),
          ...(action.pctChg !== undefined ? { pctChg: action.pctChg } : {}),
        },
      };
    case "etfDetailError":
      return { ...state, etfDetail: { loading: false, error: action.error } };
    case "vllmModelsFetched":
      return { ...state, vllmModels: action.models };
    case "vllmModelsFailed":
      return { ...state, vllmModels: [] };
  }
}

// ===========================================================================
// vllm model discovery
// ===========================================================================

const VLLM_URLS = ["http://127.0.0.1:8020/v1/models", "http://localhost:8000/v1/models"];

async function fetchVllmModels(dispatch: (action: Action) => void) {
  for (const url of VLLM_URLS) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) continue;
      const data = (await res.json()) as { data?: { id: string }[] };
      const models = (data.data ?? []).map((m) => m.id);
      if (models.length > 0) {
        dispatch({ type: "vllmModelsFetched", models });
        return;
      }
    } catch {
      /* try next */
    }
  }
  dispatch({ type: "vllmModelsFailed" });
}

// ===========================================================================
// Analysis runner
// ===========================================================================

async function runAnalysis(state: AppState, dispatch: (action: Action) => void) {
  dispatch({ type: "appendLog", msg: `开始分析 ${state.ticker}` });
  try {
    const [{ HumanMessage }] = await Promise.all([import("@langchain/core/messages")]);
    const { BridgeApi, BridgeClient, pickBridgeTools } = await import("../bridge/index.js");
    const { buildMiniSpineGraph } = await import("../graph/mini_spine.js");
    const { createLlmFromConfig } = await import("../llm/factory.js");

    dispatch({ type: "appendLog", msg: "── 连接 Bridge…" });
    const client = new BridgeClient();
    await client.start();
    try {
      const config = await new BridgeApi(client).configGet();
      const api = new BridgeApi(client);
      const llmOpts: LlmOptions = { tier: "deep" };
      if (state.provider) llmOpts.provider = state.provider;
      if (state.model) llmOpts.model = state.model;
      dispatch({
        type: "appendLog",
        msg: `── LLM: ${llmOpts.provider ?? config.llm_provider}/${llmOpts.model ?? "default"}`,
      });

      const llmHandle = createLlmFromConfig(config, llmOpts);
      const tools = await pickBridgeTools(api, [
        "get_etf_price_data",
        "get_etf_indicators",
        "get_etf_share",
        "get_etf_nav",
      ]);
      dispatch({ type: "appendLog", msg: `── 已加载 ${tools.length} 个数据工具` });

      const charLimit = Number(config.report_context_char_limit);
      const promptContext = {
        language: String(config.output_language ?? "Chinese"),
        ...(Number.isFinite(charLimit) && charLimit > 0
          ? { reportContextCharLimit: charLimit }
          : {}),
      };

          // Load ETF detail via the same bridge connection
      try {
        const detailResult = await api.toolsCall("get_etf_price_data", {
          ticker: state.ticker,
          start_date: state.date,
          end_date: state.date,
        });
        const raw = JSON.parse(detailResult.text) as { rows?: Array<Record<string, unknown>> };
        const rows = raw?.rows ?? [];
        const last = rows[rows.length - 1];
        if (last) {
          dispatch({
            type: "etfDetailLoaded",
            ...(typeof last.name === "string" ? { name: last.name } : {}),
            ...(typeof last.close === "number" ? { close: last.close } : {}),
            ...(typeof last.pct_chg === "number" ? { pctChg: last.pct_chg } : {}),
          });
        } else {
          dispatch({ type: "etfDetailLoaded", name: state.ticker });
        }
      } catch (e) {
        dispatch({ type: "etfDetailError", error: (e as Error).message });
      }

      dispatch({ type: "appendLog", msg: "── 启动 6-analyst pipeline…" });
      dispatch({ type: "sectionDone", sectionId: "market_flow" });

      const graph = buildMiniSpineGraph({
        llm: llmHandle.llm,
        marketFlowTools: tools,
        promptContext,
      });
      const final = await graph.invoke({
        messages: [new HumanMessage(state.ticker)],
        asset_of_interest: state.ticker,
        trade_date: state.date,
      });

      dispatch({ type: "appendLog", msg: "✓ Pipeline 完成" });
      dispatch({
        type: "analysisDone",
        result: String(final.trader_allocation_plan ?? "(no plan)"),
      });
    } finally {
      await client.close();
    }
  } catch (err) {
    const msg = (err as Error).message;
    dispatch({ type: "appendLog", msg: `✗ 错误: ${msg.slice(0, 120)}` });
    dispatch({
      type: "analysisError",
      msg:
        msg.includes("ECONNREFUSED") || msg.includes("connect")
          ? "Bridge 未运行。请先启动 Python bridge。"
          : msg,
    });
  }
}

// ===========================================================================
// App
// ===========================================================================

function App() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);

  const stateRef = useRef(state);
  stateRef.current = state;
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;

  // vllm discovery
  const vllmFetchedRef = useRef(false);
  useEffect(() => {
    if (state.provider.toLowerCase() === "vllm" && state.vllmModels === null) {
      if (vllmFetchedRef.current) return;
      vllmFetchedRef.current = true;
      fetchVllmModels(dispatch);
    }
    if (state.provider.toLowerCase() !== "vllm") vllmFetchedRef.current = false;
  }, [state.provider, state.vllmModels]);

  // Elapsed timer
  const [elapsed, setElapsed] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  useEffect(() => {
    if (state.phase === "dashboard" && state.status === "running") {
      startTimeRef.current = Date.now();
      const id = setInterval(() => {
        if (startTimeRef.current)
          setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
      return () => clearInterval(id);
    }
    if (state.status === "done" || state.status === "error") {
      // Freeze the timer — keep the last elapsed value visible.
      if (startTimeRef.current !== null) {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
        startTimeRef.current = null;
      }
      return undefined;
    }
    setElapsed(0);
    startTimeRef.current = null;
    return undefined;
  }, [state.phase, state.status]);



  useInput((input, key) => {
    const s = stateRef.current;
    const d = dispatchRef.current;

    if (key.escape) {
      if (s.phase === "ticker") process.exit(0);
      if (s.phase === "config") {
        d({ type: "backToTicker" });
        return;
      }
      if (s.phase === "dashboard") {
        d({ type: "backToTicker" });
        return;
      }
      process.exit(0);
    }

    if (s.phase === "ticker") {
      if (key.return && s.ticker) {
        d({ type: "openConfig" });
        return;
      }
      if (key.backspace || key.delete) {
        d({ type: "deleteTicker" });
        return;
      }
      if (input.length === 1 && /[a-zA-Z0-9._-]/.test(input))
        d({ type: "appendTicker", char: input });
      return;
    }

    if (s.phase === "config") {
      if (s.selectOpen !== null) {
        if (key.upArrow) {
          d({ type: "selectUp" });
          return;
        }
        if (key.downArrow) {
          d({ type: "selectDown" });
          return;
        }
        if (key.return) {
          d({ type: "selectPick" });
          return;
        }
        if (key.tab) {
          d({ type: "setFocus", focus: nextFocus(s.focus) });
          return;
        }
        d({ type: "closeSelect" });
      }
      if (key.tab) {
        d({ type: "setFocus", focus: nextFocus(s.focus) });
        return;
      }
      if (key.return) {
        if (isSelectField(s, s.focus)) {
          d({ type: "openSelect" });
        } else {
          d({ type: "startAnalysis" });
          runAnalysis(s, d);
        }
        return;
      }
      if (key.downArrow && isSelectField(s, s.focus)) {
        d({ type: "openSelect" });
        return;
      }
      if (key.backspace || key.delete) {
        d({ type: "deleteChar" });
        return;
      }
      if (input.length === 1 && /[a-zA-Z0-9._\-\u4e00-\u9fff/:]/.test(input))
        d({ type: "appendChar", char: input });
    }

    if (s.phase === "dashboard") {
      if (key.return && (s.status === "done" || s.status === "error")) d({ type: "backToTicker" });
    }
  });

  return (
    <Box flexDirection="column" padding={1} flexGrow={1}>
      {/* Banner */}
      <Box flexDirection="column" alignItems="center" marginBottom={1}>
        {BANNER.map((line) => (
          <Text key={line} bold color="cyan">
            {line}
          </Text>
        ))}
      </Box>

      {/* Main content */}
      <Box flexDirection="row" flexGrow={1} borderStyle="single">
        {state.phase === "ticker" && <TickerScreen state={state} />}
        {state.phase === "config" && <ConfigModal state={state} />}
        {state.phase === "dashboard" && <Dashboard state={state} elapsed={elapsed} />}
      </Box>
    </Box>
  );
}

// ===========================================================================
// Ticker screen
// ===========================================================================

function TickerScreen({ state }: { state: AppState }) {
  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Text bold>创建研究任务</Text>
      <Box marginY={1}>
        <Text dimColor>ETF 代码 </Text>
        <Text color="yellow">{state.ticker || "▌"}</Text>
      </Box>
      <Text dimColor>输入代码后按 Enter 配置分析参数</Text>
    </Box>
  );
}

// ===========================================================================
// Config modal
// ===========================================================================

function ConfigModal({ state }: { state: AppState }) {
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
        <Box marginTop={1} justifyContent="center">
          <Text color="green">按 Enter 开始分析</Text>
        </Box>
      </Box>
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

function Dashboard({ state, elapsed }: { state: AppState; elapsed: number }) {
  const groups = sectionGroups();
  const done = state.sectionDone;

  function countDone(team: string): number {
    return (groups[team] ?? []).filter((s) => done.has(s.id)).length;
  }
  function total(team: string): number {
    return (groups[team] ?? []).length;
  }

  const el = fmtElapsed(elapsed);

  // Stats bar values
  const agentsTotal = DEFAULT_SECTIONS.length;
  const agentsDone = done.size;
  const reportsTotal = DEFAULT_SECTIONS.length;
  const reportsDone = done.size;

  return (
    <Box flexDirection="column" flexGrow={1}>
      {/* Main two-column layout */}
      <Box flexDirection="row" flexGrow={1}>
        {/* Left pane — 22ch */}
        <Box flexDirection="column" width={22} borderStyle="single" paddingX={1}>
          {/* ETF card */}
          <Box flexDirection="column" marginBottom={1}>
            <Text bold>📊 基本信息</Text>
            {state.etfDetail?.loading ? (
              <Text dimColor>加载中…</Text>
            ) : state.etfDetail?.error ? (
              <Text color="red">{state.etfDetail.error.slice(0, 18)}</Text>
            ) : (
              <>
                <Text>{state.etfDetail?.name || state.ticker}</Text>
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
                <Text dimColor>{state.date}</Text>
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
            <Text dimColor>日期: {state.date}</Text>
            <Text dimColor>提供商: {state.provider || "—"}</Text>
            <Text dimColor>模型: {state.model || "—"}</Text>
          </Box>

          {/* Cancel button */}
          <Box marginBottom={1}>
            {state.status === "running" ? (
              <Text dimColor>⏹ 取消分析</Text>
            ) : (
              <Text dimColor>⏹ 分析已结束</Text>
            )}
          </Box>

          {/* Queue — shows tickers being analyzed */}
          <Box flexDirection="column" flexGrow={1}>
            <Text bold>🧠 研究队列</Text>
            <Text dimColor>
              状态:{" "}
              {state.status === "error"
                ? "🔴"
                : state.status === "done"
                  ? "🟢"
                  : state.status === "running"
                    ? "🟡"
                    : "⚪"}{" "}
              1/1
              {state.status === "error"
                ? " 有失败"
                : state.status === "done"
                  ? " 已完成"
                  : state.status === "running"
                    ? " 分析中"
                    : " 等待中"}
            </Text>
            <Box flexDirection="column" marginTop={1}>
              {state.status === "running" || state.status === "done" || state.status === "error" ? (
                <Text>
                  <Text
                    color={
                      state.status === "done"
                        ? "green"
                        : state.status === "error"
                          ? "red"
                          : "yellow"
                    }
                  >
                    {"> "}
                    {state.ticker.split(".")[0] ?? state.ticker}
                  </Text>
                  <Text dimColor>
                    {" "}
                    (
                    {state.status === "done"
                      ? "已完成"
                      : state.status === "error"
                        ? "失败"
                        : "分析中"}
                    )
                  </Text>
                </Text>
              ) : (
                <Text dimColor>等待分析启动…</Text>
              )}
            </Box>
          </Box>
        </Box>

        {/* Right pane */}
        <Box flexDirection="column" flexGrow={1} paddingLeft={1}>
          {/* Team tabs (top) */}
          <Box marginBottom={1}>
            <TabButton label="📊 分析团队" done={countDone("analysts")} total={total("analysts")} />
            <Text> </Text>
            <TabButton label="📖 研究" done={countDone("research")} total={total("research")} />
            <Text> </Text>
            <TabButton label="⚠️ 风险" done={countDone("risk")} total={total("risk")} />
            <Text> </Text>
            <TabButton label="🎯 决策" done={countDone("decision")} total={total("decision")} />
          </Box>

          {/* Report body (bottom) */}
          <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1}>
            <Text bold>整体进度</Text>
            <Box flexDirection="column" marginTop={1}>
              {state.logs.length > 0 ? (
                state.logs.map((log, i) => (
                  /* biome-ignore lint/suspicious/noArrayIndexKey: append-only log */
                  <Text key={`${i}`} dimColor={log.startsWith("──") || log.startsWith("✓")}>
                    {log.startsWith("──") || log.startsWith("✓") ? `  ${log}` : `• ${log}`}
                  </Text>
                ))
              ) : (
                <Text dimColor>准备开始分析。</Text>
              )}
              {/* Results */}
              {state.status === "done" && state.result ? (
                <Box flexDirection="column" marginTop={1}>
                  <Box>
                    <Text bold color="green">
                      ── 分析结果 ──
                    </Text>
                  </Box>
                  {state.result
                    .split("\n")
                    .slice(0, 25)
                    .map((line, i) => (
                      /* biome-ignore lint/suspicious/noArrayIndexKey: static snapshot */
                      <Text key={`r${i}`}>{line.slice(0, 120)}</Text>
                    ))}
                </Box>
              ) : null}
              {state.status === "error" && (
                <Box marginTop={1}>
                  <Text color="red">{state.errorMsg.slice(0, 120)}</Text>
                </Box>
              )}
            </Box>
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
          LLM {state.stats.llm_calls} · Tools {state.stats.tool_calls} ·{" "}
          {state.stats.tokens > 0 ? `${state.stats.tokens} tokens` : "--"}
        </Text>
        <Text color="green">
          Reports {reportsDone}/{reportsTotal}
        </Text>
        <Text dimColor>{el} ?帮助 s设置 q退出</Text>
      </Box>
    </Box>
  );
}

function TabButton({ label, done, total }: { label: string; done: number; total: number }) {
  const allDone = done === total && total > 0;
  return (
    <Box flexDirection="column" borderStyle="single" paddingX={1}>
      <Text>{label} ▾</Text>
      <Text color={allDone ? "green" : "yellow"}>
        {done}/{total}
      </Text>
    </Box>
  );
}

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// ===========================================================================
// Entry
// ===========================================================================

render(<App />);
