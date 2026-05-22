# TUI Milestones

## M0 (PR #62): Skeleton + pre-refactor

**Deliverables:**

- `cli/report_utils.py` — extract `merge_stream_state` cluster from `cli/main.py` so `cli.tui.services` can import stream-state merging without triggering the full CLI module load
- `cli/tui/services.py` — 9-section `SectionDef` model (matching AgentState fields, no `detection_keys` yet), `ReportRepository`, `BacktestViewer` (read-only), `BacktestRecord`/`BacktestViewModel`, `PaperTradingViewModel` (snapshot only), `PaperTradingSnapshot`, `IdRegistry`
- `cli/tui/app.py` — `ETFAgentsTuiApp` + `HomeScreen` (4 buttons) + 4 placeholder screens + `HelpScreen`
- `cli/commands/tui.py` — entry point with `textual` import guard
- `tests/test_tui_runner_contracts.py` — 6 `@skip("M2")` placeholders pinning AnalysisRunner acceptance criteria

**Not included (deferred):**

| Item | Target | Why deferred |
|------|--------|-------------|
| `AnalysisEvent` tagged union | M2 | No producer without AnalysisRunner |
| `TickerState` enum | M2 | Same |
| `SectionDef.detection_keys` | M2 | No consumer without AnalysisRunner |
| `r` refresh binding | M1 | No screen implements refresh in M0 |
| density/panel CSS variants | M4 | Requires settings UI |

## M1: Report library + paper trading views

- `ReportLibraryScreen` — left/right split, section tabs, `r` refresh via `ReportRepository.invalidate()`
- `PaperTradingScreen` — account/positions/history display, worker-thread refresh
- Wire `r` binding at App level, screens override `action_refresh_reports`

## M2: Research analysis

- `AnalysisRunner` — state machine, `request_cancel()`, atomic file writes, event emission
- `AnalysisEvent` tagged union (`TickerStarted | SectionDone | TickerDone | TickerFailed | TickerCancelled`)
- `TickerState` enum, `SectionDef.detection_keys`
- `ResearchAnalysisScreen` — ticker input → worker thread → live event updates → report browsing
- Must satisfy all 6 contracts in `tests/test_tui_runner_contracts.py`

## M3: Backtest viewer

- `BacktestScreen` — list existing results, NAV sparkline, metrics table, `r` refresh
- Pure view of `BacktestViewer` artifacts, no graph execution

## M4 (v1.5): Interactive enhancements

- Settings UI (`SettingsScreen`, theme/density/panel-width persistence)
- Analysis config modal (analyst selection, depth, provider, language)
- Backtest execution (`BacktestRunner` in worker thread)
- Paper trading buy/sell + login modal
- Research analysis cancel button
