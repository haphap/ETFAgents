#!/usr/bin/env node
/**
 * etfagents-ts TUI — Phase 3.7 Ink screens + state machine.
 *
 * Screens: Research (configure + run) / Results / Cache.
 * Press 1/2/3 to switch, Tab to move between fields, Enter to run.
 */

import { Box, render, Text, useInput } from "ink";
import { useReducer } from "react";

// ===========================================================================
// State
// ===========================================================================

type Screen = "research" | "results" | "cache";
type ResearchField = "ticker" | "date" | "provider" | "model";

interface AppState {
  screen: Screen;
  /** Which field is focused on the research screen. */
  focus: ResearchField;
  ticker: string;
  date: string;
  provider: string;
  model: string;
  status: "idle" | "running" | "done" | "error";
  result: string;
  errorMsg: string;
  cacheOutput: string;
}

type Action =
  | { type: "setScreen"; screen: Screen }
  | { type: "setFocus"; focus: ResearchField }
  | { type: "appendChar"; char: string }
  | { type: "deleteChar" }
  | { type: "startAnalysis" }
  | { type: "analysisDone"; result: string }
  | { type: "analysisError"; msg: string }
  | { type: "cacheResult"; output: string };

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

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "setScreen":
      return { ...state, screen: action.screen };
    case "setFocus":
      return { ...state, focus: action.focus };
    case "appendChar": {
      const key = state.focus;
      return { ...state, [key]: focusValue(state) + action.char };
    }
    case "deleteChar": {
      const key = state.focus;
      const val = focusValue(state);
      return { ...state, [key]: val.slice(0, -1) };
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
// Focus cycling
// ===========================================================================

const FOCUS_ORDER: ResearchField[] = ["ticker", "date", "provider", "model"];

function nextFocus(current: ResearchField): ResearchField {
  const i = FOCUS_ORDER.indexOf(current);
  return FOCUS_ORDER[(i + 1) % FOCUS_ORDER.length]!;
}

// ===========================================================================
// App
// ===========================================================================

function App() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);

  useInput(async (input, key) => {
    if (key.escape) process.exit(0);

    // Screen switching
    if (input === "1") dispatch({ type: "setScreen", screen: "research" });
    if (input === "2") dispatch({ type: "setScreen", screen: "results" });
    if (input === "3") dispatch({ type: "setScreen", screen: "cache" });

    if (state.screen === "research" && state.status !== "running") {
      // Tab: cycle focus
      if (key.tab) {
        dispatch({ type: "setFocus", focus: nextFocus(state.focus) });
        return;
      }
      // Enter: run analysis
      if (key.return && state.ticker) {
        dispatch({ type: "startAnalysis" });
        await runAnalysis(state, dispatch);
        return;
      }
      // Backspace / Delete
      if (key.backspace || key.delete) {
        dispatch({ type: "deleteChar" });
        return;
      }
      // Printable characters
      if (input.length === 1 && /[a-zA-Z0-9._\-\u4e00-\u9fff]/.test(input)) {
        dispatch({ type: "appendChar", char: input });
      }
    }

    if (state.screen === "cache" && key.return) {
      const output = "Cache stats would appear here.\nBridge RPC: cache.stats";
      dispatch({ type: "cacheResult", output });
    }
  });

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="cyan">ETFAgents TUI</Text>
        <Text dimColor>  [1]Research  [2]Results  [3]Cache  [Esc]Quit</Text>
      </Box>

      {/* Tab bar */}
      <Box marginBottom={1}>
        {state.screen === "research" ? <Text backgroundColor="blue"> Research </Text> : <Text> Research </Text>}
        <Text> </Text>
        {state.screen === "results" ? <Text backgroundColor="blue"> Results </Text> : <Text> Results </Text>}
        <Text> </Text>
        {state.screen === "cache" ? <Text backgroundColor="blue"> Cache </Text> : <Text> Cache </Text>}
      </Box>

      {/* Content */}
      <Box flexDirection="column" borderStyle="single" padding={1} height={22}>
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
              ? "Analysis complete"
              : state.status === "error"
                ? `Error: ${state.errorMsg.slice(0, 80)}`
                : state.screen === "research"
                  ? "[Tab] next field  [Enter] run  [Backspace] delete"
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
  const focus = (f: ResearchField) => state.focus === f;

  return (
    <Box flexDirection="column">
      <Text bold>Research Configuration</Text>
      <Text dimColor>Fill fields, Tab to move, Enter to run analysis.</Text>

      <Box marginY={1} flexDirection="column">
        <FieldRow
          label="Ticker"
          value={state.ticker}
          focused={focus("ticker")}
          hint="e.g. 510300.SH"
        />
        <FieldRow
          label="Date"
          value={state.date}
          focused={focus("date")}
          hint="YYYY-MM-DD"
        />
        <FieldRow
          label="Provider"
          value={state.provider}
          focused={focus("provider")}
          hint="openai, deepseek, ollama..."
        />
        <FieldRow
          label="Model"
          value={state.model}
          focused={focus("model")}
          hint="default from config"
        />
      </Box>

      {state.status === "running" && (
        <Text color="cyan">Running 6-analyst pipeline...</Text>
      )}
      {state.status === "error" && (
        <Text color="red">{state.errorMsg}</Text>
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
      <Text dimColor>{label.padEnd(10)}</Text>
      {focused ? (
        <Text color="yellow">{value || "▌"}</Text>
      ) : (
        <Text>{value || hint}</Text>
      )}
    </Box>
  );
}

function ResultsScreen({ state }: { state: AppState }) {
  if (!state.result) {
    return <Text dimColor>No results yet. Run Research first.</Text>;
  }
  const lines = state.result.split("\n").slice(0, 20);
  return (
    <Box flexDirection="column">
      {lines.map((line, i) => (
        /* biome-ignore lint/suspicious/noArrayIndexKey: static snapshot */
        <Text key={i}>{line.slice(0, 100)}</Text>
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
        "get_etf_price_data", "get_etf_indicators", "get_etf_share", "get_etf_nav",
      ]);

      const charLimit = Number(config.report_context_char_limit);
      const promptContext = {
        language: String(config.output_language ?? "Chinese"),
        ...(Number.isFinite(charLimit) && charLimit > 0 ? { reportContextCharLimit: charLimit } : {}),
      };

      const graph = buildMiniSpineGraph({ llm: llmHandle.llm, marketFlowTools: tools, promptContext });
      const final = await graph.invoke({
        messages: [new HumanMessage(state.ticker)],
        asset_of_interest: state.ticker,
        trade_date: state.date,
      });

      dispatch({ type: "analysisDone", result: String(final.trader_allocation_plan ?? "(no plan)") });
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
