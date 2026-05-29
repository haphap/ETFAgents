#!/usr/bin/env node
/**
 * etfagents-ts TUI — Dashboard-style analysis console.
 *
 * Flow: ticker input → config modal → dashboard (analysis + results).
 * Layout: [Banner] [Left sidebar 25ch | Right workspace] [Status bar]
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
// State
// ===========================================================================

type Phase = "ticker" | "config" | "dashboard";
type ConfigField = "date" | "provider" | "model";

/** Pipeline stage counts for the dashboard status cards. */
interface PipelineProgress {
  analysts: { done: number; total: number };
  research: { done: number; total: number };
  risk: { done: number; total: number };
  decision: { done: number; total: number };
  total: number;
}

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
  progress: PipelineProgress;
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
  | { type: "analysisDone"; result: string }
  | { type: "analysisError"; msg: string }
  | { type: "backToTicker" }
  | { type: "vllmModelsFetched"; models: string[] }
  | { type: "vllmModelsFailed" };

// ===========================================================================
// Helpers
// ===========================================================================

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const INIT_PROGRESS: PipelineProgress = {
  analysts: { done: 0, total: 6 },
  research: { done: 0, total: 2 },
  risk: { done: 0, total: 2 },
  decision: { done: 0, total: 1 },
  total: 11,
};

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
    progress: { ...INIT_PROGRESS },
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
        progress: { ...INIT_PROGRESS },
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
      const val = focusValue(state);
      return { ...state, [key]: val.slice(0, -1) };
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
      return {
        ...state,
        selectIdx: state.selectIdx > 0 ? state.selectIdx - 1 : opts.length - 1,
      };
    }
    case "selectDown": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      if (opts.length === 0) return state;
      return {
        ...state,
        selectIdx: state.selectIdx < opts.length - 1 ? state.selectIdx + 1 : 0,
      };
    }
    case "selectPick": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      const value = opts[state.selectIdx];
      if (value === undefined) return { ...state, selectOpen: null, selectIdx: 0 };
      const newProvider = state.selectOpen === "provider" ? value : state.provider;
      const vllmModels =
        state.selectOpen === "provider" && newProvider.toLowerCase() !== "vllm"
          ? null
          : state.vllmModels;
      return { ...state, [state.selectOpen]: value, selectOpen: null, selectIdx: 0, vllmModels };
    }
    case "startAnalysis":
      return {
        ...state,
        phase: "dashboard",
        status: "running",
        result: "",
        errorMsg: "",
        logs: [],
      };
    case "appendLog":
      return { ...state, logs: [...state.logs, action.msg] };
    case "analysisDone":
      return {
        ...state,
        status: "done",
        result: action.result,
        progress: {
          analysts: { done: 6, total: 6 },
          research: { done: 2, total: 2 },
          risk: { done: 2, total: 2 },
          decision: { done: 1, total: 1 },
          total: 11,
        },
      };
    case "analysisError":
      return { ...state, status: "error", errorMsg: action.msg };
    case "backToTicker":
      return { ...state, phase: "ticker", errorMsg: "", selectOpen: null, selectIdx: 0 };
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
      // try next URL
    }
  }
  dispatch({ type: "vllmModelsFailed" });
}

// ===========================================================================
// Analysis runner
// ===========================================================================

async function runAnalysis(state: AppState, dispatch: (action: Action) => void) {
  dispatch({ type: "appendLog", msg: `▶ 开始分析 ${state.ticker}` });
  try {
    const [{ HumanMessage }] = await Promise.all([import("@langchain/core/messages")]);
    const { BridgeApi, BridgeClient, pickBridgeTools } = await import("../bridge/index.js");
    const { buildMiniSpineGraph } = await import("../graph/mini_spine.js");
    const { createLlmFromConfig } = await import("../llm/factory.js");

    dispatch({ type: "appendLog", msg: "  ── 连接 Bridge…" });
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
        msg: `  ── LLM: ${llmOpts.provider ?? config.llm_provider}/${llmOpts.model ?? "default"}`,
      });

      const llmHandle = createLlmFromConfig(config, llmOpts);

      const tools = await pickBridgeTools(api, [
        "get_etf_price_data",
        "get_etf_indicators",
        "get_etf_share",
        "get_etf_nav",
      ]);
      dispatch({ type: "appendLog", msg: `  ── 已加载 ${tools.length} 个数据工具` });

      const charLimit = Number(config.report_context_char_limit);
      const promptContext = {
        language: String(config.output_language ?? "Chinese"),
        ...(Number.isFinite(charLimit) && charLimit > 0
          ? { reportContextCharLimit: charLimit }
          : {}),
      };

      dispatch({ type: "appendLog", msg: "  ── 启动 6-analyst pipeline…" });
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

      dispatch({ type: "appendLog", msg: "  ✓ Pipeline 完成" });
      dispatch({
        type: "analysisDone",
        result: String(final.trader_allocation_plan ?? "(no plan)"),
      });
    } finally {
      await client.close();
    }
  } catch (err) {
    const msg = (err as Error).message;
    dispatch({ type: "appendLog", msg: `  ✗ 错误: ${msg.slice(0, 120)}` });
    dispatch({
      type: "analysisError",
      msg:
        msg.includes("ECONNREFUSED") || msg.includes("connect")
          ? "Bridge not running. Start the Python bridge first."
          : msg,
    });
  }
}

// ===========================================================================
// App
// ===========================================================================

function App() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);

  // Refs to stabilize useInput callback
  const stateRef = useRef(state);
  stateRef.current = state;
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;

  // vllm model discovery
  const vllmFetchedRef = useRef(false);
  useEffect(() => {
    if (state.provider.toLowerCase() === "vllm" && state.vllmModels === null) {
      if (vllmFetchedRef.current) return;
      vllmFetchedRef.current = true;
      fetchVllmModels(dispatch);
    }
    if (state.provider.toLowerCase() !== "vllm") {
      vllmFetchedRef.current = false;
    }
  }, [state.provider, state.vllmModels]);

  // Elapsed timer for dashboard
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
      startTimeRef.current = null;
    }
    startTimeRef.current = null;
    setElapsed(0);
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

    // Ticker phase
    if (s.phase === "ticker") {
      if (key.return && s.ticker) {
        d({ type: "openConfig" });
        return;
      }
      if (key.backspace || key.delete) {
        d({ type: "deleteTicker" });
        return;
      }
      if (input.length === 1 && /[a-zA-Z0-9._-]/.test(input)) {
        d({ type: "appendTicker", char: input });
      }
      return;
    }

    // Config phase
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
      if (input.length === 1 && /[a-zA-Z0-9._\-\u4e00-\u9fff/:]/.test(input)) {
        d({ type: "appendChar", char: input });
      }
    }

    // Dashboard phase
    if (s.phase === "dashboard") {
      if (key.return && (s.status === "done" || s.status === "error")) {
        d({ type: "backToTicker" });
      }
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

      {/* Content */}
      <Box flexDirection="row" flexGrow={1} borderStyle="single">
        {state.phase === "ticker" && <TickerScreen state={state} />}
        {state.phase === "config" && <ConfigModal state={state} />}
        {state.phase === "dashboard" && <Dashboard state={state} elapsed={elapsed} />}
      </Box>

      {/* Footer */}
      <Box marginTop={1}>
        <Text dimColor>
          {state.phase === "ticker"
            ? "Enter ticker → Enter  [Esc] quit"
            : state.phase === "config"
              ? "[Tab] next  [↑↓] pick  [Enter] select/run  [Esc] back"
              : state.status === "running"
                ? `◎ Agents ${state.progress.analysts.done}/${state.progress.analysts.total} · 分析中  |  LLM ···  Tools ···  Reports ${state.progress.total - state.progress.decision.done}/${state.progress.total}  ${fmtElapsed(elapsed)}`
                : state.status === "error"
                  ? `◎ Error  |  [Enter] back  [q] quit  ${fmtElapsed(elapsed)}`
                  : `◎ Done  |  [Enter] new analysis  [q] quit  ${fmtElapsed(elapsed)}`}
        </Text>
      </Box>
    </Box>
  );
}

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

// ===========================================================================
// Ticker screen
// ===========================================================================

function TickerScreen({ state }: { state: AppState }) {
  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Text bold>Enter ETF Ticker</Text>
      <Box marginY={1}>
        <Text dimColor>{"> "}</Text>
        <Text color="yellow">{state.ticker || "▌"}</Text>
      </Box>
      <Text dimColor>e.g. 510300.SH, 159915.SZ</Text>
      <Box marginTop={1}>
        <Text dimColor>Press Enter to configure analysis</Text>
      </Box>
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
          <Text bold>Research Configuration</Text>
          <Text dimColor> — {state.ticker}</Text>
        </Box>
        <FieldRow label="Date" value={state.date} focused={focus("date")} hint="YYYY-MM-DD" />
        <SelectFieldRow
          label="Provider"
          value={state.provider}
          focused={focus("provider")}
          open={state.selectOpen === "provider"}
          options={PROVIDERS}
          selectedIdx={state.selectIdx}
          hint="Choose LLM provider"
        />
        {showModelSelect ? (
          <SelectFieldRow
            label="Model"
            value={state.model}
            focused={focus("model")}
            open={state.selectOpen === "model"}
            options={
              state.provider.toLowerCase() === "vllm"
                ? (state.vllmModels ?? [])
                : (MODELS_BY_PROVIDER[state.provider.toLowerCase()] ?? [])
            }
            selectedIdx={state.selectIdx}
            hint="Choose model"
          />
        ) : vllmPending ? (
          <Box>
            <Text dimColor>{"Model".padEnd(10)}</Text>
            <Text color="yellow">Fetching models from vllm…</Text>
          </Box>
        ) : (
          <FieldRow
            label="Model"
            value={state.model}
            focused={focus("model")}
            hint={
              state.provider ? "Type model name (e.g. Qwen/Qwen2.5-7B)" : "Select provider first"
            }
          />
        )}
        <Box marginTop={1} justifyContent="center">
          <Text color="green">Press Enter on Date to run analysis</Text>
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
      <Text dimColor>{label.padEnd(10)}</Text>
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
        <Text dimColor>{label.padEnd(10)}</Text>
        {focused ? (
          <Text color="yellow">
            {value || (open ? "▾" : "▸")}{" "}
            <Text dimColor>{open ? "(↑↓ pick, Enter)" : "(Enter to open)"}</Text>
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
// Dashboard: left sidebar + right workspace
// ===========================================================================

function Dashboard({ state, elapsed }: { state: AppState; elapsed: number }) {
  const p = state.progress;

  return (
    <Box flexDirection="row" flexGrow={1}>
      {/* Left sidebar — 26 chars */}
      <Box flexDirection="column" width={26} borderStyle="single" paddingX={1}>
        {/* Basic info */}
        <Box flexDirection="column" marginBottom={1}>
          <Text bold>📊 基本信息</Text>
          <Text>{state.ticker || "—"}</Text>
          <Text dimColor>{state.date}</Text>
          {state.status === "error" ? (
            <Text color="red">分析失败</Text>
          ) : state.status === "done" ? (
            <Text color="green">分析完成</Text>
          ) : (
            <Text color="yellow">分析中…</Text>
          )}
        </Box>

        <Box flexDirection="column" marginBottom={1}>
          <Text bold>📋 分析参数</Text>
          <Text dimColor>日期: {state.date}</Text>
          <Text dimColor>提供商: {state.provider || "—"}</Text>
          <Text dimColor>模型: {state.model || "—"}</Text>
        </Box>

        {/* Cancel button */}
        <Box marginBottom={1}>
          {state.status === "running" ? (
            <Text dimColor>[ 取消分析 ]</Text>
          ) : (
            <Text dimColor>[ 分析已结束 ]</Text>
          )}
        </Box>

        {/* Research queue */}
        <Box flexDirection="column" flexGrow={1}>
          <Text bold>🧠 研究队列</Text>
          <Text dimColor>
            状态: {state.status === "error" ? "🔴" : state.status === "done" ? "🟢" : "🟡"}{" "}
            {p.analysts.done}/{p.analysts.total}
            {state.status === "error"
              ? " 有失败"
              : state.status === "done"
                ? " 已全部完成"
                : " 进行中"}
          </Text>
          <Box flexDirection="column" marginTop={1}>
            <QueueItem
              label="分析师团队"
              done={p.analysts.done}
              total={p.analysts.total}
              status={state.status}
            />
            <QueueItem
              label="研究方向"
              done={p.research.done}
              total={p.research.total}
              status={state.status}
            />
            <QueueItem
              label="风险评估"
              done={p.risk.done}
              total={p.risk.total}
              status={state.status}
            />
            <QueueItem
              label="最终决策"
              done={p.decision.done}
              total={p.decision.total}
              status={state.status}
            />
          </Box>
        </Box>
      </Box>

      {/* Right workspace */}
      <Box flexDirection="column" flexGrow={1} padding={1}>
        {/* Status cards */}
        <Box marginBottom={1}>
          <StatusCard label="📊 分析团队" done={p.analysts.done} total={p.analysts.total} />
          <Text> </Text>
          <StatusCard label="📖 研究" done={p.research.done} total={p.research.total} />
          <Text> </Text>
          <StatusCard label="⚠ 风险" done={p.risk.done} total={p.risk.total} />
          <Text> </Text>
          <StatusCard label="🎯 决策" done={p.decision.done} total={p.decision.total} />
        </Box>

        {/* Main content: logs + results */}
        <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1}>
          <Text bold>整体进度</Text>
          <Box flexDirection="column" marginTop={1}>
            {state.logs.length > 0 ? (
              state.logs.map((log, i) => (
                /* biome-ignore lint/suspicious/noArrayIndexKey: append-only log */
                <Text key={`${i}`} dimColor={log.startsWith("  ──") || log.startsWith("  ✓")}>
                  {log}
                </Text>
              ))
            ) : (
              <Text dimColor>等待分析启动…</Text>
            )}
            {/* Results when done */}
            {state.status === "done" && state.result ? (
              <Box flexDirection="column" marginTop={1}>
                <Box>
                  <Text bold color="green">
                    ── 分析结果 ──
                  </Text>
                </Box>
                {state.result
                  .split("\n")
                  .slice(0, 30)
                  .map((line, i) => (
                    /* biome-ignore lint/suspicious/noArrayIndexKey: static snapshot */
                    <Text key={`r${i}`}>{line.slice(0, 120)}</Text>
                  ))}
              </Box>
            ) : null}
            {/* Error */}
            {state.status === "error" && (
              <Box marginTop={1}>
                <Text color="red">{state.errorMsg.slice(0, 120)}</Text>
              </Box>
            )}
          </Box>
        </Box>

        {/* Footer hint */}
        <Box marginTop={1}>
          <Text dimColor>
            {state.status === "running"
              ? `${fmtElapsed(elapsed)}  [?]帮助 [s]设置 [q]退出`
              : state.status === "error"
                ? `${fmtElapsed(elapsed)}  [Enter]重新分析 [?]帮助 [q]退出`
                : `${fmtElapsed(elapsed)}  [Enter]新分析 [?]帮助 [q]退出`}
          </Text>
        </Box>
      </Box>
    </Box>
  );
}

function QueueItem({
  label,
  done,
  total,
  status,
}: {
  label: string;
  done: number;
  total: number;
  status: string;
}) {
  const icon = status === "done" ? "✓" : status === "error" ? "✗" : "○";
  const color = status === "done" ? "green" : status === "error" ? "red" : "yellow";
  return (
    <Text>
      <Text color={color}>
        {icon} {label}
      </Text>
      <Text dimColor>
        {" "}
        {done}/{total}
      </Text>
    </Text>
  );
}

function StatusCard({ label, done, total }: { label: string; done: number; total: number }) {
  const allDone = done === total && total > 0;
  const color = allDone ? "green" : "yellow";
  return (
    <Box flexDirection="column" borderStyle="single" paddingX={1}>
      <Text>{label}</Text>
      <Text color={color}>
        {done}/{total}
      </Text>
    </Box>
  );
}

// ===========================================================================
// Entry
// ===========================================================================

render(<App />);
