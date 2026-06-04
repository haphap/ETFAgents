#!/usr/bin/env node
import { pathToFileURL } from "node:url";
import type { Instance, RenderOptions } from "ink";
import { Box, render, useApp, useInput, useStdout } from "ink";
import type { ReactNode } from "react";
import { useEffect, useReducer, useRef, useState } from "react";
import {
  ANALYST_IDS,
  ELAPSED_REFRESH_MS,
  initState,
  isSelectField,
  LIBRARY_CARD_VIEWPORT,
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
  ReportReaderOverlay,
  TeamDetailOverlay,
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
import { enterFullscreen } from "./terminal.js";

export * from "./model.js";
export { runAnalysis } from "./runner.js";
export { ENTER_FULLSCREEN, EXIT_FULLSCREEN, enterFullscreen } from "./terminal.js";

export type RunTuiOptions = RenderOptions & {
  fullscreen?: boolean;
};

function App() {
  const { exit } = useApp();
  const { stdout } = useStdout();
  const [terminalSize, setTerminalSize] = useState(() => readTerminalSize(stdout));
  const [state, dispatch] = useReducer(reducer, undefined, initState);

  const stateRef = useRef(state);
  stateRef.current = state;
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;
  const runSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const quitApp = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    runSeqRef.current += 1;
    exit();
  };

  useEffect(() => {
    const update = () => setTerminalSize(readTerminalSize(stdout));
    stdout.on("resize", update);
    return () => {
      stdout.off("resize", update);
    };
  }, [stdout]);

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

    if ((key.ctrl && input.toLowerCase() === "c") || input === "\u0003") {
      quitApp();
      return;
    }

    // P6: an open error-detail overlay swallows the next key (close on any).
    if (s.showErrorDetail) {
      d({ type: "toggleErrorDetail" });
      return;
    }

    if (s.showHelp) {
      d({ type: "toggleHelp" });
      return;
    }

    if (s.showTeamDetail) {
      if (key.upArrow) {
        d({ type: "selectSection", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "selectSection", delta: 1 });
        return;
      }
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
      if (key.escape || key.return) {
        d({ type: "closeTeamDetail" });
        return;
      }
      d({ type: "closeTeamDetail" });
      return;
    }

    if (s.phase === "library" && s.library.readerOpen) {
      if (key.escape || key.return) {
        d({ type: "libraryCloseReader" });
        return;
      }
      if (key.upArrow || key.pageUp) {
        d({ type: "libraryScroll", delta: -REPORT_VIEWPORT });
        return;
      }
      if (key.downArrow || key.pageDown || input === " ") {
        d({ type: "libraryScroll", delta: REPORT_VIEWPORT });
        return;
      }
      return;
    }

    if (input === "?") {
      d({ type: "toggleHelp" });
      return;
    }

    if (key.escape) {
      if (s.phase === "home") {
        quitApp();
        return;
      }
      if (s.phase === "config") {
        d(s.selectOpen !== null ? { type: "closeSelect" } : { type: "backToTicker" });
        return;
      }
      if (s.phase === "dashboard") {
        abortRef.current?.abort();
        abortRef.current = null;
        runSeqRef.current += 1;
        d({ type: "goPhase", phase: "home" });
        return;
      }
      if (
        s.phase === "ticker" ||
        s.phase === "library" ||
        s.phase === "backtest" ||
        s.phase === "paper"
      ) {
        d({ type: "goPhase", phase: "home" });
        return;
      }
      quitApp();
      return;
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
        d({ type: "toggleTeamDetail" });
        d({ type: "selectSection", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "toggleTeamDetail" });
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
      if (key.return) {
        d({ type: "toggleTeamDetail" });
        return;
      }
      return;
    }

    if (s.phase === "library") {
      if (input === "r") {
        loadLibrary(d);
        return;
      }
      if (key.leftArrow) {
        d({ type: "libraryPane", pane: "tickers" });
        return;
      }
      if (key.rightArrow || key.tab) {
        d({ type: "libraryPane", pane: "reports" });
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
        d({ type: "librarySelect", delta: -LIBRARY_CARD_VIEWPORT });
        return;
      }
      if (key.pageDown) {
        d({ type: "librarySelect", delta: LIBRARY_CARD_VIEWPORT });
        return;
      }
      if (key.return) {
        const selected = s.library.reports[s.library.selectedIdx];
        if (selected) {
          d({ type: "libraryPane", pane: "reports" });
          d({ type: "libraryOpenReader" });
          loadLibraryBody(selected, d);
        }
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

  const content =
    state.phase === "home" ? (
      <HomeScreen state={state} />
    ) : (
      <Box flexDirection="row" flexGrow={1} borderStyle="single">
        {state.phase === "ticker" && <TickerScreen state={state} />}
        {state.phase === "config" && <ConfigModal state={state} />}
        {state.phase === "dashboard" && (
          <Dashboard state={state} elapsed={elapsed} screenRows={terminalSize.rows - 4} />
        )}
        {state.phase === "library" && <ReportLibrary state={state} />}
        {state.phase === "backtest" && <BacktestScreen state={state} />}
        {state.phase === "paper" && <PaperScreen state={state} />}
      </Box>
    );

  return (
    <Box
      flexDirection="column"
      paddingX={1}
      paddingY={state.phase === "home" ? 0 : 1}
      width={terminalSize.columns}
      height={terminalSize.rows}
    >
      {content}
      {state.showErrorDetail && state.errorDetail && (
        <CenteredOverlay columns={terminalSize.columns} rows={terminalSize.rows}>
          <ErrorDetailOverlay detail={state.errorDetail} />
        </CenteredOverlay>
      )}
      {state.showHelp && (
        <CenteredOverlay columns={terminalSize.columns} rows={terminalSize.rows}>
          <HelpOverlay phase={state.phase} />
        </CenteredOverlay>
      )}
      {state.showTeamDetail && (
        <CenteredOverlay columns={terminalSize.columns} rows={terminalSize.rows}>
          <TeamDetailOverlay state={state} />
        </CenteredOverlay>
      )}
      {state.phase === "library" && state.library.readerOpen && (
        <CenteredOverlay columns={terminalSize.columns} rows={terminalSize.rows}>
          <ReportReaderOverlay
            state={state}
            columns={terminalSize.columns}
            rows={terminalSize.rows}
          />
        </CenteredOverlay>
      )}
    </Box>
  );
}

function CenteredOverlay({
  children,
  columns,
  rows,
}: {
  children: ReactNode;
  columns: number;
  rows: number;
}) {
  return (
    <Box
      position="absolute"
      width={columns}
      height={rows}
      justifyContent="center"
      alignItems="center"
    >
      {children}
    </Box>
  );
}

function readTerminalSize(stdout: NodeJS.WriteStream): { columns: number; rows: number } {
  const columns = Number.isFinite(stdout.columns) && stdout.columns > 0 ? stdout.columns : 120;
  const rows = Number.isFinite(stdout.rows) && stdout.rows > 0 ? stdout.rows : 32;
  return { columns, rows };
}

export function runTui(options: RunTuiOptions = {}): Instance {
  const { fullscreen = true, ...renderOptions } = options;
  const screen =
    fullscreen === true ? enterFullscreen(renderOptions.stdout ?? process.stdout) : null;
  const instance = render(<App />, { ...renderOptions, exitOnCtrlC: false });
  if (screen) void instance.waitUntilExit().finally(screen.restore);
  return instance;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runTui();
}
