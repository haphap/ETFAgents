#!/usr/bin/env node
/**
 * etfagents-ts TUI — Phase-based flow.
 *
 * Flow: ticker input → config modal → analysis → results.
 * Flicker-free: uses flexGrow instead of fixed height, stable layout.
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

type Phase = "ticker" | "config" | "analyzing" | "results" | "error";
type ConfigField = "date" | "provider" | "model";

interface AppState {
  phase: Phase;
  ticker: string;
  date: string;
  provider: string;
  model: string;
  /** Config modal focus */
  focus: ConfigField;
  /** Which field's dropdown is open */
  selectOpen: ConfigField | null;
  selectIdx: number;
  /** Analysis results */
  result: string;
  errorMsg: string;
  /**
   * vllm dynamic models.
   * null = not yet fetched (triggers discovery on next tick),
   * []  = fetch failed or empty (shows free-text input),
   * [...models] = fetched successfully (shows dropdown).
   */
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
    result: "",
    errorMsg: "",
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
    case "openConfig": {
      // Reset config state when entering config
      return {
        ...state,
        phase: "config",
        focus: "date",
        selectOpen: null,
        selectIdx: 0,
        vllmModels: null,
        errorMsg: "",
      };
    }
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
      const next = focusValue(state) + action.char;
      // Clear vllmModels when user types away from vllm provider
      return {
        ...state,
        [key]: next,
        ...(key === "provider" && next.toLowerCase() !== "vllm" ? { vllmModels: null } : {}),
      };
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
      return {
        ...state,
        [state.selectOpen]: value,
        selectOpen: null,
        selectIdx: 0,
        vllmModels,
      };
    }
    case "startAnalysis":
      return { ...state, phase: "analyzing", result: "", errorMsg: "" };
    case "analysisDone":
      return { ...state, phase: "results", result: action.result };
    case "analysisError":
      return { ...state, phase: "error", errorMsg: action.msg };
    case "backToTicker":
      return {
        ...state,
        phase: "ticker",
        errorMsg: "",
        selectOpen: null,
        selectIdx: 0,
      };
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
  try {
    const [{ HumanMessage }] = await Promise.all([import("@langchain/core/messages")]);
    const { BridgeApi, BridgeClient, pickBridgeTools } = await import("../bridge/index.js");
    const { buildMiniSpineGraph } = await import("../graph/mini_spine.js");
    const { createLlmFromConfig } = await import("../llm/factory.js");

    const client = new BridgeClient();
    await client.start();
    try {
      const config = await new BridgeApi(client).configGet();
      const api = new BridgeApi(client);
      const llmOpts: LlmOptions = { tier: "deep" };
      if (state.provider) llmOpts.provider = state.provider;
      if (state.model) llmOpts.model = state.model;
      const llmHandle = createLlmFromConfig(config, llmOpts);

      const tools = await pickBridgeTools(api, [
        "get_etf_price_data",
        "get_etf_indicators",
        "get_etf_share",
        "get_etf_nav",
      ]);

      const charLimit = Number(config.report_context_char_limit);
      const promptContext = {
        language: String(config.output_language ?? "Chinese"),
        ...(Number.isFinite(charLimit) && charLimit > 0
          ? { reportContextCharLimit: charLimit }
          : {}),
      };

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

      dispatch({
        type: "analysisDone",
        result: String(final.trader_allocation_plan ?? "(no plan)"),
      });
    } finally {
      await client.close();
    }
  } catch (err) {
    console.error("Analysis failed:", err);
    const msg = (err as Error).message;
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

  // Refs to stabilize useInput callback — prevents flicker
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

  useInput((input, key) => {
    const s = stateRef.current;
    const d = dispatchRef.current;

    if (key.escape) {
      if (s.phase === "ticker") process.exit(0);
      if (s.phase === "config") {
        d({ type: "backToTicker" });
        return;
      }
      if (s.phase === "error" || s.phase === "results") {
        d({ type: "backToTicker" });
        return;
      }
      process.exit(0);
    }

    // --- Ticker phase ---
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

    // --- Config phase ---
    if (s.phase === "config") {
      // Dropdown is open
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
          // Enter on date field or when all config done: start analysis
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
      return;
    }

    // --- Error phase ---
    if (s.phase === "error" || s.phase === "results") {
      if (key.return || key.escape) {
        d({ type: "backToTicker" });
      }
    }
  });

  // Spinner for analyzing phase
  const [spinnerTick, setSpinnerTick] = useState(0);
  const spinnerRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(() => {
    if (state.phase === "analyzing") {
      spinnerRef.current = setInterval(() => setSpinnerTick((t) => t + 1), 100);
    } else {
      if (spinnerRef.current) clearInterval(spinnerRef.current);
      spinnerRef.current = null;
      setSpinnerTick(0);
    }
    return () => {
      if (spinnerRef.current) clearInterval(spinnerRef.current);
    };
  }, [state.phase]);
  const spinnerFrames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
  const spinner = spinnerFrames[spinnerTick % spinnerFrames.length] ?? " ";

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

      {/* Content — fills remaining space */}
      <Box flexDirection="column" borderStyle="single" padding={1} flexGrow={1}>
        {state.phase === "ticker" && <TickerScreen state={state} />}
        {state.phase === "config" && <ConfigModal state={state} />}
        {state.phase === "analyzing" && (
          <Box flexDirection="column">
            <Text bold>Analysis Running</Text>
            <Box marginY={1}>
              <Text color="cyan">
                {spinner} Analyzing {state.ticker}…
              </Text>
            </Box>
            <Text dimColor>Date: {state.date}</Text>
            {state.provider ? <Text dimColor>Provider: {state.provider}</Text> : null}
            {state.model ? <Text dimColor>Model: {state.model}</Text> : null}
          </Box>
        )}
        {state.phase === "results" && <ResultsScreen state={state} />}
        {state.phase === "error" && <ErrorScreen state={state} />}
      </Box>

      {/* Footer */}
      <Box marginTop={1}>
        <Text dimColor>
          {state.phase === "ticker"
            ? "Enter ticker code and press Enter"
            : state.phase === "config"
              ? "[Tab] next  [↑↓] pick  [Enter] select/run  [Esc] back"
              : state.phase === "analyzing"
                ? "Running analysis pipeline…"
                : state.phase === "error"
                  ? "Connection failed — press Enter to retry"
                  : "Press Enter to analyze another ticker"}
        </Text>
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
      <Text bold>Enter ETF Ticker</Text>
      <Box marginY={1}>
        <Text>
          <Text dimColor>{"> "}</Text>
          <Text color="yellow">{state.ticker || "▌"}</Text>
        </Text>
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
          <Text color="green">
            {state.focus === "model" && !isSelectField(state, "model")
              ? "Press Enter to run"
              : "Fill config, press Enter on Date to run"}
          </Text>
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
// Results / Error
// ===========================================================================

function ResultsScreen({ state }: { state: AppState }) {
  const lines = state.result.split("\n").slice(0, 40);
  return (
    <Box flexDirection="column">
      <Text bold>Results — {state.ticker}</Text>
      <Box marginY={1} flexDirection="column">
        {lines.map((line, i) => (
          /* biome-ignore lint/suspicious/noArrayIndexKey: static snapshot */
          <Text key={i}>{line.slice(0, 120)}</Text>
        ))}
      </Box>
    </Box>
  );
}

function ErrorScreen({ state }: { state: AppState }) {
  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Text bold color="red">
        Error
      </Text>
      <Box marginY={1}>
        <Text>{state.errorMsg}</Text>
      </Box>
      <Text dimColor>Press Enter to go back</Text>
    </Box>
  );
}

// ===========================================================================
// Entry
// ===========================================================================

render(<App />);
