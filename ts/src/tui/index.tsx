#!/usr/bin/env node
import { pathToFileURL } from "node:url";
import { Box, render, useInput } from "ink";
import { useEffect, useReducer, useRef, useState } from "react";
import {
  ANALYST_IDS,
  ELAPSED_REFRESH_MS,
  initState,
  isSelectField,
  nextFocus,
  parseTickers,
  REPORT_VIEWPORT,
  reducer,
  TEAM_TABS,
} from "./model.js";
import { fetchVllmModels, runAnalysis } from "./runner.js";
import {
  BacktestScreen,
  ConfigModal,
  Dashboard,
  ErrorDetailOverlay,
  HelpOverlay,
  HomeScreen,
  PaperScreen,
  ReportLibrary,
  TickerScreen,
} from "./screens.js";
import {
  loadBacktests,
  loadBacktestView,
  loadLibrary,
  loadLibraryBody,
  loadPaper,
  loadWatchlist,
} from "./services/artifacts.js";

export * from "./model.js";
export { runAnalysis } from "./runner.js";

function App() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);

  const stateRef = useRef(state);
  stateRef.current = state;
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;
  const runSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

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
      }, ELAPSED_REFRESH_MS);
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

  // P3: load the read-only watchlist once at startup.
  const watchlistLoadedRef = useRef(false);
  useEffect(() => {
    if (watchlistLoadedRef.current) return;
    watchlistLoadedRef.current = true;
    loadWatchlist(dispatch);
  }, []);

  // P2: discover reports when entering the library.
  useEffect(() => {
    if (state.phase === "library") loadLibrary(dispatch);
  }, [state.phase]);

  // P2: load the selected report body when the selection changes.
  const libSel = state.library.reports[state.library.selectedIdx];
  useEffect(() => {
    if (state.phase === "library" && libSel) loadLibraryBody(libSel, dispatch);
  }, [state.phase, libSel]);

  // P4: discover backtest artifacts when entering the screen.
  useEffect(() => {
    if (state.phase === "backtest") loadBacktests(dispatch);
  }, [state.phase]);

  // P4: load the selected backtest view when the selection changes.
  const btSel = state.backtest.records[state.backtest.selectedIdx];
  useEffect(() => {
    if (state.phase === "backtest" && btSel) loadBacktestView(btSel, dispatch);
  }, [state.phase, btSel]);

  // P5: load paper-trading snapshot when entering the screen.
  useEffect(() => {
    if (state.phase === "paper") loadPaper(dispatch);
  }, [state.phase]);

  useInput((input, key) => {
    const s = stateRef.current;
    const d = dispatchRef.current;

    // P6: an open error-detail overlay swallows the next key (close on any).
    if (s.showErrorDetail) {
      d({ type: "toggleErrorDetail" });
      return;
    }

    if (s.showHelp) {
      d({ type: "toggleHelp" });
      return;
    }

    if (input === "?") {
      d({ type: "toggleHelp" });
      return;
    }

    if (key.escape) {
      if (s.phase === "home") {
        process.exit(0);
      }
      if (s.phase === "config") {
        d({ type: "backToTicker" });
        return;
      }
      if (s.phase === "dashboard") {
        abortRef.current?.abort();
        runSeqRef.current += 1;
        d({ type: "goPhase", phase: "home" });
        return;
      }
      if (s.phase === "library" || s.phase === "backtest" || s.phase === "paper") {
        d({ type: "goPhase", phase: "home" });
        return;
      }
      if (s.phase === "ticker") {
        d({ type: "goPhase", phase: "home" });
        return;
      }
      process.exit(0);
    }

    if (s.phase === "home") {
      if (key.upArrow) {
        d({ type: "homeMove", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "homeMove", delta: 1 });
        return;
      }
      if (key.return) {
        d({ type: "homeOpen" });
        return;
      }
      if (input === "r") {
        d({ type: "goPhase", phase: "ticker" });
        return;
      }
      if (input === "l") {
        d({ type: "goPhase", phase: "library" });
        return;
      }
      if (input === "b") {
        d({ type: "goPhase", phase: "backtest" });
        return;
      }
      if (input === "p") {
        d({ type: "goPhase", phase: "paper" });
        return;
      }
      return;
    }

    if (s.phase === "ticker") {
      // Top-level screen navigation (Ctrl+L/B/P avoids clashing with ticker chars).
      if (key.ctrl && input === "l") {
        d({ type: "goPhase", phase: "library" });
        return;
      }
      if (key.ctrl && input === "b") {
        d({ type: "goPhase", phase: "backtest" });
        return;
      }
      if (key.ctrl && input === "p") {
        d({ type: "goPhase", phase: "paper" });
        return;
      }
      // Watchlist: arrows select, Tab appends the selected ticker to the input.
      if (s.watchlist.length > 0) {
        if (key.upArrow) {
          d({ type: "watchlistMove", delta: -1 });
          return;
        }
        if (key.downArrow) {
          d({ type: "watchlistMove", delta: 1 });
          return;
        }
        if (key.tab) {
          d({ type: "watchlistAddToInput" });
          return;
        }
      }
      if (key.return && parseTickers(s.ticker).length > 0) {
        d({ type: "openConfig" });
        return;
      }
      if (key.backspace || key.delete) {
        d({ type: "deleteTicker" });
        return;
      }
      if (input.length === 1 && /[a-zA-Z0-9._,\-，;；\s]/.test(input))
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
        return;
      }
      if (key.tab) {
        d({ type: "setFocus", focus: nextFocus(s.focus) });
        return;
      }
      // Analyst toggle row: arrows move cursor, space toggles current analyst.
      if (s.focus === "analysts") {
        if (key.leftArrow) {
          d({ type: "moveAnalystCursor", delta: -1 });
          return;
        }
        if (key.rightArrow) {
          d({ type: "moveAnalystCursor", delta: 1 });
          return;
        }
        if (input === " ") {
          const id = ANALYST_IDS[s.analystCursor];
          if (id) d({ type: "toggleAnalyst", id });
          return;
        }
      }
      // Round steppers: left/right adjust the count.
      if (s.focus === "debateRounds" || s.focus === "riskRounds") {
        if (key.leftArrow) {
          d({ type: "stepRounds", field: s.focus, delta: -1 });
          return;
        }
        if (key.rightArrow) {
          d({ type: "stepRounds", field: s.focus, delta: 1 });
          return;
        }
      }
      if (key.return) {
        if (isSelectField(s, s.focus)) {
          d({ type: "openSelect" });
        } else {
          const runId = runSeqRef.current + 1;
          runSeqRef.current = runId;
          abortRef.current?.abort();
          const controller = new AbortController();
          abortRef.current = controller;
          d({ type: "startAnalysis" });
          runAnalysis(s, d, () => runSeqRef.current === runId, controller.signal);
        }
        return;
      }
      if (key.downArrow && isSelectField(s, s.focus)) {
        d({ type: "openSelect" });
        return;
      }
      if (key.backspace || key.delete) {
        if (s.focus === "date" || s.focus === "model") d({ type: "deleteChar" });
        return;
      }
      // Free text entry only for the date and (option-less) model fields.
      if (
        (s.focus === "date" || s.focus === "model") &&
        input.length === 1 &&
        /[a-zA-Z0-9._\-\u4e00-\u9fff/:]/.test(input)
      )
        d({ type: "appendChar", char: input });
      return;
    }

    if (s.phase === "dashboard") {
      // P6: open error detail when a failure is recorded.
      if (input === "e" && s.errorDetail) {
        d({ type: "toggleErrorDetail" });
        return;
      }
      // Cycle team tabs with Tab / left-right arrows.
      if (key.tab || key.rightArrow) {
        const i = TEAM_TABS.findIndex((t) => t.key === s.activeTab);
        const next = TEAM_TABS[(i + 1) % TEAM_TABS.length];
        if (next) d({ type: "setTab", tab: next.key });
        return;
      }
      if (key.leftArrow) {
        const i = TEAM_TABS.findIndex((t) => t.key === s.activeTab);
        const prev = TEAM_TABS[(i - 1 + TEAM_TABS.length) % TEAM_TABS.length];
        if (prev) d({ type: "setTab", tab: prev.key });
        return;
      }
      // P0: up/down select a section, PageUp/PageDown scroll its body.
      if (key.upArrow) {
        d({ type: "selectSection", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "selectSection", delta: 1 });
        return;
      }
      if (key.pageUp) {
        d({ type: "scrollReport", delta: -REPORT_VIEWPORT });
        return;
      }
      if (key.pageDown) {
        d({ type: "scrollReport", delta: REPORT_VIEWPORT });
        return;
      }
      if (key.return && (s.status === "done" || s.status === "error")) {
        abortRef.current?.abort();
        runSeqRef.current += 1;
        d({ type: "goPhase", phase: "home" });
      }
      return;
    }

    if (s.phase === "library") {
      if (input === "r") {
        loadLibrary(d);
        return;
      }
      if (key.upArrow) {
        d({ type: "librarySelect", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "librarySelect", delta: 1 });
        return;
      }
      if (key.pageUp) {
        d({ type: "libraryScroll", delta: -REPORT_VIEWPORT });
        return;
      }
      if (key.pageDown) {
        d({ type: "libraryScroll", delta: REPORT_VIEWPORT });
        return;
      }
      return;
    }

    if (s.phase === "backtest") {
      if (input === "r") {
        loadBacktests(d);
        return;
      }
      if (key.upArrow) {
        d({ type: "backtestSelect", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "backtestSelect", delta: 1 });
        return;
      }
      return;
    }

    if (s.phase === "paper") {
      if (input === "r") loadPaper(d);
      return;
    }
  });

  return (
    <Box flexDirection="column" padding={1} flexGrow={1}>
      {/* Main content */}
      <Box flexDirection="row" flexGrow={1} borderStyle="single">
        {state.phase === "home" && <HomeScreen state={state} />}
        {state.phase === "ticker" && <TickerScreen state={state} />}
        {state.phase === "config" && <ConfigModal state={state} />}
        {state.phase === "dashboard" && <Dashboard state={state} elapsed={elapsed} />}
        {state.phase === "library" && <ReportLibrary state={state} />}
        {state.phase === "backtest" && <BacktestScreen state={state} />}
        {state.phase === "paper" && <PaperScreen state={state} />}
      </Box>

      {/* P6: error detail overlay */}
      {state.showErrorDetail && state.errorDetail && (
        <ErrorDetailOverlay detail={state.errorDetail} />
      )}
      {state.showHelp && <HelpOverlay phase={state.phase} />}
    </Box>
  );
}

export function runTui() {
  render(<App />);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runTui();
}
