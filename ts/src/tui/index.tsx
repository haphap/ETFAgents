#!/usr/bin/env node
/**
 * etfagents-ts TUI — Phase 3.7 Ink screens + state machine.
 *
 * Screens: Research (configure + run) / Results / Cache.
 * Full-screen layout with ASCII banner header.
 */

import { Box, render, Text, useInput, useStdout } from "ink";
import { useReducer } from "react";

// ===========================================================================
// Banner — standard FIGlet font for readability
// ===========================================================================

const BANNER = [
  "╔══════════════════════════════════════════════╗",
  "║                                              ║",
  "║   _____ _____ _____ _                    _   ║",
  "║  | ____|_   _|  ___/ \\   __ _  ___ _ __ | |_ ║",
  "║  |  _|   | | | |_ / _ \\ / _` |/ _ \\ '_ \\| __|║",
  "║  | |___  | | |  _/ ___ \\ (_| |  __/ | | | |_ ║",
  "║  |_____| |_| |_|/_/   \\_\\__, |\\___|_| |_|\\__|║",
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

type Screen = "research" | "results" | "cache";
type ResearchField = "ticker" | "date" | "provider" | "model";

interface AppState {
  screen: Screen;
  focus: ResearchField;
  ticker: string;
  date: string;
  provider: string;
  model: string;
  status: "idle" | "running" | "done" | "error";
  result: string;
  errorMsg: string;
  cacheOutput: string;
  /** Which field's dropdown is open (null = no dropdown visible). */
  selectOpen: ResearchField | null;
  /** Highlighted index in the open dropdown. */
  selectIdx: number;
}

type Action =
  | { type: "setScreen"; screen: Screen }
  | { type: "setFocus"; focus: ResearchField }
  | { type: "appendChar"; char: string }
  | { type: "deleteChar" }
  | { type: "startAnalysis" }
  | { type: "analysisDone"; result: string }
  | { type: "analysisError"; msg: string }
  | { type: "cacheResult"; output: string }
  | { type: "openSelect" }
  | { type: "closeSelect" }
  | { type: "selectUp" }
  | { type: "selectDown" }
  | { type: "selectPick" };

// ===========================================================================
// Helpers
// ===========================================================================

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function initState(): AppState {
  return {
    screen: "research",
    focus: "ticker",
    ticker: "",
    date: today(),
    provider: "",
    model: "",
    status: "idle",
    result: "",
    errorMsg: "",
    cacheOutput: "",
    selectOpen: null,
    selectIdx: 0,
  };
}

function focusValue(state: AppState): string {
  switch (state.focus) {
    case "ticker":
      return state.ticker;
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
    return MODELS_BY_PROVIDER[p] ?? [];
  }
  return [];
}

const FOCUS_ORDER: ResearchField[] = ["ticker", "date", "provider", "model"];

function nextFocus(current: ResearchField): ResearchField {
  const i = FOCUS_ORDER.indexOf(current);
  return FOCUS_ORDER[i + 1] ?? FOCUS_ORDER[0] ?? "ticker";
}

function isSelectField(f: ResearchField): boolean {
  return f === "provider" || f === "model";
}

// ===========================================================================
// Reducer
// ===========================================================================

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "setScreen":
      return { ...state, screen: action.screen };
    case "setFocus":
      return {
        ...state,
        focus: action.focus,
        selectOpen: isSelectField(action.focus) ? action.focus : null,
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
      if (!isSelectField(state.focus)) return state;
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
      // When provider changes, clear model so user re-picks
      const provider = state.selectOpen === "provider" ? value : state.provider;
      const model = state.selectOpen === "model" ? value : state.model;
      return {
        ...state,
        [state.selectOpen]: value,
        provider,
        model,
        selectOpen: null,
        selectIdx: 0,
      };
    }
    case "startAnalysis":
      return { ...state, status: "running", result: "", errorMsg: "" };
    case "analysisDone":
      return { ...state, status: "done", result: action.result, screen: "results" };
    case "analysisError":
      return { ...state, status: "error", errorMsg: action.msg };
    case "cacheResult":
      return { ...state, cacheOutput: action.output };
  }
}

// ===========================================================================
// App
// ===========================================================================

function App() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);
  const { stdout } = useStdout();
  const termHeight = stdout?.rows ?? 30;

  useInput(async (input, key) => {
    if (key.escape) process.exit(0);

    if (input === "1") dispatch({ type: "setScreen", screen: "research" });
    if (input === "2") dispatch({ type: "setScreen", screen: "results" });
    if (input === "3") dispatch({ type: "setScreen", screen: "cache" });

    if (state.screen === "research" && state.status !== "running") {
      // Dropdown is open — navigate / pick / close
      if (state.selectOpen !== null) {
        if (key.upArrow) {
          dispatch({ type: "selectUp" });
          return;
        }
        if (key.downArrow) {
          dispatch({ type: "selectDown" });
          return;
        }
        if (key.return) {
          dispatch({ type: "selectPick" });
          return;
        }
        if (key.tab) {
          dispatch({ type: "setFocus", focus: nextFocus(state.focus) });
          return;
        }
        // Any other key closes the dropdown and falls through to typing
        dispatch({ type: "closeSelect" });
      }

      // Tab cycles focus (auto-opens dropdown for select fields)
      if (key.tab) {
        dispatch({ type: "setFocus", focus: nextFocus(state.focus) });
        return;
      }

      // Enter on non-select fields: run analysis
      if (key.return) {
        if (isSelectField(state.focus)) {
          dispatch({ type: "openSelect" });
        } else if (state.ticker) {
          dispatch({ type: "startAnalysis" });
          await runAnalysis(state, dispatch);
        }
        return;
      }

      // Arrow down on select field opens dropdown
      if (key.downArrow && isSelectField(state.focus)) {
        dispatch({ type: "openSelect" });
        return;
      }

      // Backspace/delete
      if (key.backspace || key.delete) {
        dispatch({ type: "deleteChar" });
        return;
      }

      // Printable chars
      if (input.length === 1 && /[a-zA-Z0-9._\-\u4e00-\u9fff]/.test(input)) {
        dispatch({ type: "appendChar", char: input });
      }
    }

    if (state.screen === "cache" && key.return) {
      dispatch({
        type: "cacheResult",
        output: "Cache stats would appear here.\nBridge RPC: cache.stats",
      });
    }
  });

  // Content area height: terminal minus banner(12) - tabs(1) - footer(1) - padding
  const contentHeight = termHeight - 16;

  return (
    <Box flexDirection="column" padding={1} height={termHeight}>
      {/* Banner */}
      <Box flexDirection="column" alignItems="center" marginBottom={1}>
        {BANNER.map((line) => (
          <Text key={line} bold color="cyan">
            {line}
          </Text>
        ))}
      </Box>

      {/* Header + Tabs */}
      <Box justifyContent="space-between" marginBottom={1}>
        <Box>
          {(["research", "results", "cache"] as const).map((s) => {
            const label = s.charAt(0).toUpperCase() + s.slice(1);
            return (
              <Text key={s}>
                {" "}
                {state.screen === s ? (
                  <Text backgroundColor="blue"> {label} </Text>
                ) : (
                  <Text> {label} </Text>
                )}
              </Text>
            );
          })}
        </Box>
        <Text dimColor>[1/2/3] Switch [Esc] Quit</Text>
      </Box>

      {/* Content */}
      <Box flexDirection="column" borderStyle="single" padding={1} height={contentHeight}>
        {state.screen === "research" && <ResearchScreen state={state} />}
        {state.screen === "results" && <ResultsScreen state={state} />}
        {state.screen === "cache" && <CacheScreen state={state} />}
      </Box>

      {/* Footer */}
      <Box marginTop={1}>
        <Text dimColor>
          {state.status === "running"
            ? "Analyzing..."
            : state.status === "done"
              ? "Analysis complete — switch to Results [2]"
              : state.status === "error"
                ? `Error: ${state.errorMsg.slice(0, 80)}`
                : state.screen === "research"
                  ? "[Tab] next  [Enter] run/select  [↓] open picker  [Esc] quit"
                  : "Ready"}
        </Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// Screens
// ===========================================================================

function ResearchScreen({ state }: { state: AppState }) {
  return (
    <Box flexDirection="column">
      <Text bold>Research Configuration</Text>
      <Text dimColor>Tab to move, ↑↓ to pick, Enter to run analysis.</Text>

      <Box marginY={1} flexDirection="column">
        <FieldRow
          label="Ticker"
          value={state.ticker}
          focused={state.focus === "ticker"}
          hint="e.g. 510300.SH"
        />
        <FieldRow
          label="Date"
          value={state.date}
          focused={state.focus === "date"}
          hint="YYYY-MM-DD"
        />
        <SelectFieldRow
          label="Provider"
          value={state.provider}
          focused={state.focus === "provider"}
          open={state.selectOpen === "provider"}
          options={PROVIDERS as unknown as string[]}
          selectedIdx={state.selectIdx}
          hint="Choose LLM provider"
        />
        <SelectFieldRow
          label="Model"
          value={state.model}
          focused={state.focus === "model"}
          open={state.selectOpen === "model"}
          options={state.provider ? (MODELS_BY_PROVIDER[state.provider.toLowerCase()] ?? []) : []}
          selectedIdx={state.selectIdx}
          hint={state.provider ? "Choose model" : "Select provider first"}
        />
      </Box>

      {state.status === "running" && <Text color="cyan">Running 6-analyst pipeline...</Text>}
      {state.status === "error" && <Text color="red">{state.errorMsg}</Text>}
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
  options: string[];
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
      {/* Dropdown overlay */}
      {open && options.length > 0 && (
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
      {open && options.length === 0 && (
        <Box marginLeft={2}>
          <Text dimColor>No options available</Text>
        </Box>
      )}
    </Box>
  );
}

function ResultsScreen({ state }: { state: AppState }) {
  if (!state.result) {
    return <Text dimColor>No results yet. Run Research first.</Text>;
  }
  const lines = state.result.split("\n").slice(0, 40);
  return (
    <Box flexDirection="column">
      {lines.map((line, i) => (
        /* biome-ignore lint/suspicious/noArrayIndexKey: static snapshot */
        <Text key={i}>{line.slice(0, 120)}</Text>
      ))}
    </Box>
  );
}

function CacheScreen({ state }: { state: AppState }) {
  return (
    <Box flexDirection="column">
      <Text bold>Cache Management</Text>
      <Text dimColor>Press Enter to refresh stats</Text>
      {state.cacheOutput ? (
        <Box marginTop={1} flexDirection="column">
          {state.cacheOutput.split("\n").map((line, i) => (
            /* biome-ignore lint/suspicious/noArrayIndexKey: static snapshot */
            <Text key={i}>{line}</Text>
          ))}
        </Box>
      ) : (
        <Text dimColor>Press Enter to load cache stats from bridge</Text>
      )}
    </Box>
  );
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
      const llmOpts: Record<string, unknown> = { tier: "deep" };
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
    dispatch({ type: "analysisError", msg: (err as Error).message });
  }
}

// ===========================================================================
// Entry
// ===========================================================================

render(<App />);
