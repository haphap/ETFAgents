# TypeScript TUI Parity Plan

This plan tracks the remaining gap between the current TypeScript Ink TUI and
the earlier Python Textual TUI. The intent is not to copy every widget one for
one. The target is functional parity for the research workflow first, then the
supporting screens.

## Implementation Status

All priority items (P0–P6) are implemented in `ts/src/tui/index.tsx`, with
unit coverage in `ts/test/tui_state.test.ts`. Verified with `pnpm typecheck`,
`pnpm lint`, and `pnpm test` (19 files, 317 tests).

- **P0 Full report reader** — `selectedSectionByTab` + `reportScrollBySection`
  state; ↑/↓ select a section, PageUp/PageDown scroll its body; viewport
  rendering with top/bottom/line indicators; scroll resets on report append;
  `setTab` default-selects the first section.
- **P1 Analysis config parity** — analyst toggles (←/→ cursor, Space toggle),
  research depth select, debate/risk round steppers (clamped 1–3), read-only
  backend row. **Multi-round debate is now wired**: `debateRounds`/`riskRounds`
  flow into `buildFullGraph`, the debator nodes accumulate
  `investment_debate_state`/`risk_debate_state` (`count`/`latestSpeaker`/
  `history`), and the bull↔bear and aggressive→conservative→neutral edges loop
  via `routeDebate`/`routeRiskDebate`, matching the Python graph. Analyst
  deselection is still surfaced as a "pending graph support" warning.
- **P2 Report library** — `Ctrl+L` screen; discovers
  `results_dir/{ticker}/{date}/complete_report.md`, newest-first; reuses the P0
  viewport for the selected body; `r` refresh.
- **P3 Watchlist entry** — read-only cards derived from recent report tickers;
  ↑/↓ select, **Tab** appends to input (deduped). Deviation: Tab is used
  instead of the planned Space so manual space-separated multi-ticker input
  keeps working.
- **P4 Backtest viewer** — `Ctrl+B` screen; walks `results_dir/backtest` for
  `metrics.json`/`manifest.json`; `normalizeBacktestResult` accepts both the
  bridge flat-`metrics` shape and the on-disk shape; NAV sparkline, metrics,
  benchmark comparison, health warnings.
- **P5 Paper trading** — `Ctrl+P` screen over bridge `paper.*` RPCs; account,
  positions (sorted), recent trades; `r` refresh.
- **P6 Error detail** — structured `ErrorDetail` (message/ticker/stack/
  timestamp) captured on failure; `e` opens an overlay, any key closes;
  cancellation stays distinct from failure.

## Current Baseline

The current TypeScript TUI already has:

- Single research flow from ticker input to config to dashboard.
- Full-pipeline execution via `buildFullGraph`.
- Live section updates across analyst, research, trader, risk, and decision tabs.
- Multi-ticker queue state and abort-aware cancellation.
- Per-section `pending/running/done/failed` state.
- Multi-role debate report aggregation, so bull/bear and risk debator content is
  no longer overwritten.
- Basic ETF card with price, daily change, high/low, volume change, and sparkline.
- Stats bar with current section, LLM call count, tool count, report count, and
  elapsed time.
- Trader execution summary on the decision tab.

Known remaining gaps:

- Report reading is still shallow: no full selected-section reader, no scroll
  position, and no section picker equivalent.
- Config controls are still much thinner than Python: no analyst selection,
  research depth, debate rounds, risk rounds, or bridge/backend display.
- No report library screen.
- No watchlist entry cards.
- No TUI backtest or paper-trading screens.
- Error details are still inline and short, not a dedicated detail view.

## Current PR Progress

### PR Status

- PR: `#87` (`Polish TS TUI research parity`)
- Base: `main`
- Head: `fix/ts-pipeline-wiring-and-cli`
- Main commit: `0163d9e6ac357f906dc1ce3abcdee414bebc80a4`
- Status when this plan was written: open, with GitHub checks started after
  local verification.

PR #86 was already merged before this parity follow-up was ready, so the work
could not be added to PR #86 directly. PR #87 carries the follow-up UI parity
work on top of the same TypeScript TUI branch.

### PR #87 Completed Work

- Added multi-ticker parsing and queue state.
- Added queue item status: `pending`, `running`, `done`, `failed`,
  `cancelled`.
- Added abort-aware cancellation via `AbortController`.
- Added per-section state: `pending`, `running`, `done`, `failed`.
- Stopped marking every section done on `analysisDone`.
- Preserved multi-node section reports by appending node output under a
  role label instead of replacing the section body.
- Added basic stats tracking for loaded tools and streamed LLM node outputs.
- Expanded the ETF info card with one-year price history, sparkline, high/low,
  volume, and volume-change estimate.
- Added trader execution summary from `trader_backtest_signal`.
- Exported small TUI state helpers for unit testing without rendering Ink.
- Added `ts/test/tui_state.test.ts` for queue parsing, queue initialization,
  report aggregation, and completion-state behavior.

### PR #87 Local Verification

- `pnpm typecheck`
- `pnpm lint`
- `env HOME=/tmp/etfagents-ts-test-home pnpm test`
  - 19 test files passed
  - 292 tests passed
- `uv run python -m unittest tests.test_bridge_protocol -q`
  - 14 tests passed
- `git diff --check`

### Not Included In PR #87

PR #87 intentionally stops short of full Python Textual parity. It improves the
core live research dashboard but does not add:

- full selected-section report reader
- report body scroll state
- section picker equivalent
- analyst selection controls
- research-depth/debate-round/risk-round config controls
- report library screen
- watchlist cards
- backtest TUI screen
- paper-trading TUI screen
- full error detail modal/screen

## Python UI vs TypeScript UI Gap Audit

This audit compares the Python Textual TUI to the TypeScript Ink TUI after the
PR #87 changes.

### 1. App Shell And Navigation

Python Textual UI:

- Has a top-level app shell with `HomeScreen`.
- Routes to research, report library, backtest, paper trading, settings, and
  help screens.
- Provides app-level bindings such as help, settings, refresh, and screen
  navigation.
- Uses Textual's focus model, screen stack, modal support, and footer/header.

TypeScript Ink UI now:

- Has one primary flow: ticker input -> config -> live dashboard.
- Does not have a top-level home screen.
- Does not expose report library, backtest, paper trading, settings, or help as
  separate screens.
- Uses custom keyboard handling inside a single Ink component tree.

Remaining gap:

- Add a real top-level screen model before adding report library/backtest/paper
  screens.
- Decide whether settings/help are first-class screens or compact overlays.

### 2. Research Entry And Watchlist

Python Textual UI:

- Provides a research entry screen with ticker input, start/config actions, and
  watchlist area.
- Supports watchlist cards and quick task creation from saved tickers.
- Provides add-to-watchlist affordances.
- Handles batch/multi-ticker style research through a queue model.

TypeScript Ink UI now:

- Supports direct ticker input.
- Supports multiple tickers separated by comma, whitespace, or Chinese
  punctuation.
- Deduplicates tickers before analysis.
- Shows a live queue once analysis starts.
- Does not have watchlist cards.
- Does not persist or load watchlist items.

Remaining gap:

- Add watchlist source discovery.
- Add card/list rendering for watchlist tickers.
- Add "append watchlist ticker to current input" interaction.
- Add persistence only through existing Python/bridge conventions.

### 3. Analysis Configuration

Python Textual UI:

- Supports richer analysis configuration, including provider/model choices,
  analyst selection, research depth, debate rounds, and risk rounds.
- Presents these controls before analysis starts.
- Treats config as part of the research workflow, not just LLM selection.

TypeScript Ink UI now:

- Supports date, provider, and model.
- Supports provider/model selection, including vLLM model discovery.
- Does not expose analyst selection.
- Does not expose research depth.
- Does not expose debate rounds or risk rounds.
- Does not display effective backend/base URL.
- TS full graph is currently single-pass for debate/risk debate, so multi-round
  controls would need either graph support or an explicit unsupported warning.

Remaining gap:

- Add config state and UI controls first.
- Only wire controls to graph behavior when the graph actually supports them.
- Surface unsupported config choices clearly instead of silently ignoring them.

### 4. Analysis Runner And Cancellation

Python Textual UI:

- Uses `AnalysisRunner`.
- Emits structured events:
  - ticker started
  - section done
  - debate progress
  - ticker done
  - ticker failed
  - ticker cancelled
- Supports `request_cancel()`.
- Tracks per-ticker and per-section state.

TypeScript Ink UI now:

- Runs the TypeScript full graph directly.
- Streams graph chunks and maps node output into UI sections.
- Has multi-ticker queue state.
- Uses `AbortController` for cancellation.
- Uses stale-run guards to ignore old dispatches.
- Has per-section state.
- Does not yet have a separate runner abstraction.
- Does not emit a stable public `AnalysisEvent` union equivalent.
- Debate progress is inferred from graph node output, not represented as its
  own event type.

Remaining gap:

- Consider extracting a TS analysis runner service once report reader and config
  state stabilize.
- Add structured event tests if the runner becomes reusable outside the TUI.

### 5. Section Model And Debate Fidelity

Python Textual UI:

- Maintains section definitions and detection keys in service code.
- Distinguishes analyst reports, research debate, research manager, trader,
  risk debate, portfolio manager, and execution summary.
- Preserves debate content from multiple roles.
- Can display risk/research debate as a complete section.

TypeScript Ink UI now:

- Defines 11 sections across analyst, research, trader, risk, and decision
  teams.
- Maps full-graph nodes into section ids.
- Appends multi-role reports under labels, so:
  - bull and bear both remain visible in `research_debate`
  - aggressive, conservative, and neutral all remain visible in `risk_debate`
- Has no separate execution-summary section in the section list; it renders an
  execution summary panel on the decision tab.

Remaining gap:

- Decide whether execution summary should be a formal section, matching the
  Python decision group more closely.
- Add selected-section reader so aggregated debate content can be inspected
  comfortably.

### 6. Report Reading

Python Textual UI:

- Has a section picker/popover style workflow.
- Renders a selected body area for report content.
- Supports a more complete reading workflow for long reports.
- Includes special handling for portfolio-manager output and execution summary.

TypeScript Ink UI now:

- Shows section checklist and report content inside the active tab.
- Renders more lines than the original snippet view after PR #87, but still uses
  a shallow "all available bodies in this tab" presentation.
- Does not have selected-section state.
- Does not have scroll state.
- Does not have page up/down report navigation.
- Does not have a full body mode or overlay.

Remaining gap:

- This is P0. Add selected-section state, body viewport, and scroll controls.

### 7. ETF Detail Card

Python Textual UI:

- Uses `get_etf_detail`.
- Displays richer ETF data such as:
  - name
  - latest price
  - price metrics
  - NAV/premium information when available
  - volume/change
  - holdings bars
  - price history/sparkline

TypeScript Ink UI now:

- Calls bridge `get_etf_price_data`.
- Fetches roughly one year of price rows.
- Displays:
  - name when returned by data rows
  - close
  - daily percentage change
  - high/low
  - volume
  - volume-change estimate
  - sparkline
- Does not call `get_etf_detail`.
- Does not display NAV, premium/discount, fund shares, manager, benchmark, or
  holdings bars.

Remaining gap:

- Prefer adding a bridge method for `get_etf_detail` or exposing an equivalent
  structured detail payload.
- Avoid reconstructing the full Python detail aggregation independently in TS.

### 8. Stats And Resource Visibility

Python Textual UI:

- Shows agent progress, current section, tool calls, LLM calls, token count,
  report count, elapsed time, and action hints.
- Runner stats are owned by the Python runner.

TypeScript Ink UI now:

- Shows current running section.
- Shows report count.
- Shows elapsed time.
- Tracks loaded tool count and streamed LLM node count.
- Has a `tokens` field in state but does not populate it with real token usage.

Remaining gap:

- Add real token accounting only if the TS LLM client or LangChain callbacks
  expose stable usage metadata.
- Separate "loaded tools" from "executed tool calls" if bridge/tool execution
  events become available.

### 9. Error Handling

Python Textual UI:

- Has a detailed error modal.
- Can show tracebacks and richer failure details.
- Tracks failed/cancelled ticker state distinctly.

TypeScript Ink UI now:

- Shows inline error summaries.
- Preserves queue failed/cancelled status.
- Treats cancellation separately from ordinary failures.
- Does not preserve a structured error detail object.
- Does not show stack traces or bridge tracebacks in a detail view.

Remaining gap:

- This is P6. Add structured error detail storage and a detail overlay/screen.

### 10. Report Library

Python Textual UI:

- Has `ReportLibraryScreen`.
- Discovers historical reports.
- Supports refresh.
- Displays report list and report body/details.

TypeScript Ink UI now:

- Has no report library screen.
- Live reports exist only in current TUI state.
- Does not discover persisted report artifacts.

Remaining gap:

- This is P2. Reuse the P0 report reader for historical reports.

### 11. Backtest

Python Textual UI:

- Has a backtest viewer screen.
- Shows existing result artifacts, NAV, metrics, and related details.

TypeScript Ink UI now:

- Has TypeScript CLI backtest rendering fixed in PR #86.
- Does not expose a TUI backtest screen.
- Does not yet reuse the CLI/bridge result shape inside Ink.

Remaining gap:

- This is P4. Build read-only artifact viewing before adding execution.

### 12. Paper Trading

Python Textual UI:

- Has paper-trading snapshot screen.
- Displays account, positions, and related paper-trading state.

TypeScript Ink UI now:

- Has no paper-trading TUI screen.
- Paper functionality remains CLI/bridge-oriented.

Remaining gap:

- This is P5. Build read-only snapshot first.

## P0: Full Report Reader

### Goal

Make the active analysis result readable inside the terminal without relying on
truncated snippets. This is the highest-impact product gap because the current
dashboard can run the full pipeline but cannot comfortably inspect the output.

### Scope

- Add a selected-section state separate from the active team tab.
- Support moving the selection within the current tab's section list.
- Replace the current "show every available report snippet" layout with:
  - section status list
  - selected section title/status
  - full report body viewport
  - progress log fallback when no section has content yet
- Add scroll state for the report body.
- Keep the layout within the existing Ink single-screen app.

### Controls

- `Tab` / right arrow: next team tab.
- left arrow: previous team tab.
- up/down arrow: move selected section within the active tab.
- `PageUp` / `PageDown`: scroll selected section body.
- `Home` / `End`: jump to top/bottom if Ink key support is reliable.
- `Enter`: return to ticker screen only after done/error, preserving current
  behavior.

### State Changes

- Add `selectedSectionByTab: Record<string, string>`.
- Add `reportScrollBySection: Record<string, number>`.
- Reset scroll for a section when its report body is replaced or appended.
- When changing tabs, select the first section in that tab if no prior selection
  exists.
- Keep `activeSection` as "currently running section"; do not overload it as the
  selected report.

### Rendering Rules

- If selected section has report content, render up to a fixed viewport height
  from `reportScrollBySection[sectionId]`.
- If selected section is running with no report content, show "running" state and
  recent logs.
- If selected section failed, show failure state plus the latest error message.
- If selected section is pending, show a pending state.
- Preserve markdown text as plain terminal text for now. Do not introduce a
  markdown renderer until the state model is stable.

### Tests

- Reducer selects the first section when switching to a tab with no prior
  selected section.
- up/down selection wraps within the active tab.
- report scroll clamps at top and bottom.
- appending a section report preserves content and resets or clamps scroll.
- analysis completion does not mark unreported sections done.

### Acceptance Criteria

- A completed portfolio-manager report can be read beyond the first 40 lines.
- Bull and bear debate content are both visible in the selected research debate
  section.
- Aggressive, conservative, and neutral risk debate content are all visible in
  the selected risk debate section.
- The UI never shows an empty report area for a section that is only pending or
  still running.

## P1: Analysis Config Parity

### Goal

Bring the TypeScript analysis config close enough to Python that users can
control what kind of research run they are starting.

### Scope

- Add analyst selection for the six analyst sections:
  - market flow
  - catalyst sentiment
  - macro regime
  - meso commodity
  - holdings industry
  - top holdings
- Add research depth:
  - quick
  - standard
  - deep
- Add debate round and risk round controls.
- Show effective provider/model/backend values.
- Keep unsupported graph behavior explicit instead of pretending it works.

### Implementation Notes

- Analyst selection can initially drive UI expectations and tool selection.
  If the graph cannot safely skip an analyst yet, mark the setting as pending
  graph support instead of silently ignoring it.
- Current full graph is single-pass for debate/risk debate. If the graph still
  lacks multi-round loops, the config should display that rounds above one are
  not active yet.
- Backend/base URL should be read from bridge config when available.

### Controls

- Use the existing config modal flow.
- Add field types:
  - boolean toggles for analysts
  - select row for depth
  - numeric stepper rows for debate/risk rounds
  - read-only row for backend
- Keep keyboard behavior consistent with existing field focus and select rows.

### Tests

- Default config matches Python's normal path: all analysts enabled, standard
  depth, one debate/risk pass unless graph support changes.
- Toggling an analyst updates config state without mutating defaults.
- Selecting depth updates state and visible label.
- Round controls clamp to supported min/max.
- Unsupported multi-round config produces an explicit warning state.

### Acceptance Criteria

- A user can see and modify the main research controls before starting a run.
- The TUI does not silently accept a setting that the TS graph will ignore.
- Existing provider/model behavior keeps working.

## P2: Report Library

### Goal

Expose historical research outputs in the TypeScript TUI, matching the Python
TUI's core report-library workflow.

### Scope

- Add a top-level report library phase/screen.
- Discover reports from the same result directory conventions as Python.
- Show a report list on the left and selected report details on the right.
- Reuse the P0 full report reader for the selected historical report body.
- Add refresh.

### Implementation Notes

- Prefer bridge-side report discovery if a stable bridge method exists.
- Otherwise, read local result artifacts from the configured results directory.
- Keep file parsing structured where possible. Avoid brittle string parsing of
  filenames unless there is no existing metadata.

### Controls

- `r`: refresh report list.
- up/down: move report selection.
- `Enter`: open selected report body.
- `Esc`: return to home/research entry.

### Tests

- Report discovery handles empty directories.
- Report discovery sorts newest first.
- Malformed report files are skipped or shown with a clear error state.
- Opening a report uses the same body viewer state as live reports.

### Acceptance Criteria

- A user can inspect at least the ticker, date, title/source, and body of a
  historical report.
- Refresh updates the list without restarting the TUI.

## P3: Watchlist Entry

### Goal

Make repeated research starts faster by adding the Python-style watchlist entry
surface.

### Scope

- Show watchlist cards below or beside the ticker input.
- Add selected watchlist item to the ticker queue.
- Add current ticker or completed ticker to the watchlist.
- Keep persistence aligned with existing Python or bridge conventions.

### Implementation Notes

- First pass can read-only display a default/static watchlist if persistence is
  not exposed yet.
- Do not invent a separate TS-only persistence format if Python already owns a
  watchlist file or service.
- Multi-ticker input from the current TUI should remain the shared queue model.

### Controls

- up/down or left/right: move watchlist selection.
- `Space`: add selected watchlist ticker to input.
- `a`: add current input ticker to watchlist if persistence is available.

### Tests

- Adding a watchlist ticker deduplicates against existing input.
- Multi-ticker input and watchlist additions share the same parser.
- Missing watchlist source renders an empty state, not an exception.

### Acceptance Criteria

- A frequent ticker can be started without typing the full code.
- Watchlist interaction does not break direct ticker input.

## P4: Backtest TUI Screen

### Goal

Bring the Python TUI backtest viewer into the TypeScript TUI without duplicating
the CLI engine.

### Scope

- Add a top-level backtest screen.
- Load existing backtest artifacts.
- Show NAV sparkline, benchmark comparison, key metrics, trades/orders summary,
  and health warnings.
- Optionally trigger a backtest run later, after the read-only viewer is stable.

### Implementation Notes

- Reuse the TS backtest result shape fixed in PR86:
  - `nav`
  - `benchmark_nav`
  - `metrics`
  - `benchmark_metrics`
  - `trades`
  - `orders`
  - `positions`
  - `rebalances`
  - `health`
- Do not reimplement strategy logic in the TUI.

### Tests

- Backtest artifact loader accepts the bridge result shape.
- Empty or missing benchmark data renders gracefully.
- Metrics render from flat `BacktraderMetrics`, not nested objects.

### Acceptance Criteria

- A user can inspect an existing backtest result from inside the TUI.
- The displayed metrics match the TS CLI output for the same artifact.

## P5: Paper Trading TUI Screen

### Goal

Expose paper-trading account state in the TUI.

### Scope

- Add a top-level paper trading screen.
- Display account snapshot, positions, orders, and recent activity.
- Add manual refresh.
- Defer trade placement until read-only state is reliable.

### Tests

- Empty account renders cleanly.
- Positions and orders are sorted deterministically.
- Bridge failures show an actionable error.

### Acceptance Criteria

- A user can inspect paper-trading status without using the CLI command.

## P6: Error Detail View

### Goal

Replace short inline errors with a useful detail view similar to Python's error
modal.

### Scope

- Store structured error details:
  - ticker
  - section if known
  - message
  - stack/traceback if available
  - timestamp
- Add an error detail overlay or screen.
- Keep inline summary short, with a key to open details.

### Tests

- Error state preserves full message while rendering a short summary.
- Error detail view handles absent stack traces.
- Cancelling a run is shown separately from a failure.

### Acceptance Criteria

- A failing bridge, LLM, or graph run gives enough detail to debug without
  rerunning with external logs.

## Suggested Execution Order

1. P0: Full report reader.
2. P1: Analysis config parity.
3. P2: Report library.
4. P3: Watchlist entry.
5. P4: Backtest TUI screen.
6. P5: Paper trading TUI screen.
7. P6: Error detail view.

P0 and P1 should be completed before adding more top-level screens. They improve
the core research workflow and provide shared state/view primitives that the
report library and historical readers can reuse.

## Non-Goals For The Next Iteration

- Do not migrate from Ink to another TUI framework.
- Do not attempt pixel-perfect Textual parity.
- Do not add a separate TS persistence format for reports or watchlists.
- Multi-round debate support is now implemented in the graph (see Implementation
  Status); analyst deselection remains the one config control not yet wired.
- Do not add trade placement to paper trading before the read-only view is
  reliable.
