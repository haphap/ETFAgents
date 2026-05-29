#!/usr/bin/env node
/**
 * etfagents-ts TUI — Phase 3.7 Ink screens + state machine.
 *
 * Screens: Research (run analysis) / Results / Cache.
 * Press 1/2/3 to switch, Esc to quit, Enter to run analysis.
 */

import { Box, render, Text, useInput } from "ink";
import { useReducer } from "react";

// ===========================================================================
// State
// ===========================================================================

type Screen = "research" | "results" | "cache";

interface AppState {
  screen: Screen;
  ticker: string;
  status: "idle" | "running" | "done" | "error";
  result: string;
  errorMsg: string;
  cacheOutput: string;
}

type Action =
  | { type: "setScreen"; screen: Screen }
  | { type: "setTicker"; ticker: string }
  | { type: "appendTicker"; char: string }
  | { type: "backspaceTicker" }
  | { type: "startAnalysis" }
  | { type: "analysisDone"; result: string }
  | { type: "analysisError"; msg: string }
  | { type: "cacheResult"; output: string };

function initState(): AppState {
  return {
    screen: "research",
    ticker: "",
    status: "idle",
    result: "",
    errorMsg: "",
    cacheOutput: "",
  };
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "setScreen":
      return { ...state, screen: action.screen };
    case "setTicker":
      return { ...state, ticker: action.ticker };
    case "appendTicker":
      return { ...state, ticker: state.ticker + action.char };
    case "backspaceTicker":
      return { ...state, ticker: state.ticker.slice(0, -1) };
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

  useInput(async (input, key) => {
    if (key.escape) process.exit(0);

    if (input === "1") dispatch({ type: "setScreen", screen: "research" });
    if (input === "2") dispatch({ type: "setScreen", screen: "results" });
    if (input === "3") dispatch({ type: "setScreen", screen: "cache" });

    if (state.screen === "research" && state.status !== "running") {
      if (input === "\r") {
        dispatch({ type: "startAnalysis" });
        await runAnalysis(state.ticker, dispatch);
        return;
      }
      if (input.length === 1 && /[a-zA-Z0-9._\u4e00-\u9fff]/.test(input)) {
        dispatch({ type: "appendTicker", char: input });
      }
      if (key.backspace) dispatch({ type: "backspaceTicker" });
    }

    if (state.screen === "cache" && input === "\r") {
      const output = "Cache stats would appear here.\nBridge RPC: cache.stats";
      dispatch({ type: "cacheResult", output });
    }
  });

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="cyan">
          ETFAgents TUI
        </Text>
        <Text dimColor> [1]Research [2]Results [3]Cache [Esc]Quit</Text>
      </Box>

      {/* Tab bar */}
      <Box marginBottom={1}>
        {state.screen === "research" ? (
          <Text backgroundColor="blue"> Research </Text>
        ) : (
          <Text> Research </Text>
        )}
        <Text> </Text>
        {state.screen === "results" ? (
          <Text backgroundColor="blue"> Results </Text>
        ) : (
          <Text> Results </Text>
        )}
        <Text> </Text>
        {state.screen === "cache" ? (
          <Text backgroundColor="blue"> Cache </Text>
        ) : (
          <Text> Cache </Text>
        )}
      </Box>

      {/* Content */}
      <Box flexDirection="column" borderStyle="single" padding={1} height={20}>
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
      <Text bold>Single Ticker Analysis</Text>
      <Text dimColor>Enter an ETF ticker (e.g. 510300.SH) and press Enter.</Text>
      <Box marginY={1}>
        <Text>Ticker: </Text>
        <Text color="yellow">{state.ticker || "_"}</Text>
      </Box>
      {state.status === "running" && <Text color="cyan">Running 6-analyst pipeline...</Text>}
    </Box>
  );
}

function ResultsScreen({ state }: { state: AppState }) {
  if (!state.result) {
    return <Text dimColor>No results yet. Run Research first.</Text>;
  }
  const lines = state.result.split("\n").slice(0, 18);
  return (
    <Box flexDirection="column">
      {lines.map((line) => (
        <Text key={line.slice(0, 40)}>{line.slice(0, 100)}</Text>
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
          {state.cacheOutput.split("\n").map((line) => (
            <Text key={line.slice(0, 40)}>{line}</Text>
          ))}
        </Box>
      ) : (
        <Text dimColor>Press Enter to load cache stats from bridge</Text>
      )}
    </Box>
  );
}

// ===========================================================================
// Analysis runner (uses full graph via bridge)
// ===========================================================================

async function runAnalysis(ticker: string, dispatch: (action: Action) => void) {
  try {
    // Dynamic imports avoid loading bridge deps at TUI startup.
    const [{ HumanMessage }] = await Promise.all([import("@langchain/core/messages")]);
    const { BridgeApi, BridgeClient, pickBridgeTools } = await import("../bridge/index.js");
    const { buildMiniSpineGraph } = await import("../graph/mini_spine.js");
    const { createLlmFromConfig } = await import("../llm/factory.js");

    const client = new BridgeClient();
    await client.start();
    try {
      const config = await new BridgeApi(client).configGet();
      const api = new BridgeApi(client);
      const llmHandle = createLlmFromConfig(config, { tier: "deep" });

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
        messages: [new HumanMessage(ticker)],
        asset_of_interest: ticker,
        trade_date: new Date().toISOString().slice(0, 10),
      });

      const plan = String(final.trader_allocation_plan ?? "(no plan produced)");
      dispatch({ type: "analysisDone", result: plan });
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
