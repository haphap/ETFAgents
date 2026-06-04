# TypeScript TUI Status

This document records the current TypeScript Ink TUI status and remaining
follow-ups. The original parity plan against the Python Textual TUI has been
completed for the main research workflow and supporting read-only screens.

## Current Status

The TUI can be launched from `ts/` with either command:

```bash
pnpm dev tui
pnpm tui
```

The app now uses a home screen instead of a permanently rendered banner. Work
screens use a compact layout to reduce terminal redraw noise. The dashboard
timer refreshes at a lower cadence, and report readers preserve scroll unless
the user is already at the bottom.

Implemented screens and overlays:

- Home navigation for Research, Reports, Backtest, and Paper Trading.
- Research entry with multi-ticker parsing and watchlist/recent-report shortcuts.
- Analysis config with provider/model, analyst toggles, depth presets, and
  manual debate/risk round steppers.
- Live dashboard with team tabs, per-section report reader, queue state, ETF
  detail card, execution summary, and structured error overlay.
- Report library over saved `complete_report.md` artifacts.
- Backtest viewer over saved metrics/NAV/trade artifacts.
- Paper-trading account snapshot.
- `?` help overlay with per-screen keybindings.

## Implementation Layout

`ts/src/tui/index.tsx` is intentionally thin. It owns the Ink app shell,
keyboard routing, effects, and `runTui()` entry point.

```text
ts/src/tui/
  index.tsx              # app shell + key handling + runTui()
  model.ts               # constants, types, helpers, reducer, test exports
  runner.ts              # vLLM discovery + full graph execution
  services/artifacts.ts  # reports, watchlist, backtest, paper snapshot loading
  screens.tsx            # Ink screen and overlay components
```

Public test helpers are re-exported from `index.tsx` so existing Vitest imports
continue to work.

## Bridge Additions

The TUI prefers real watchlist entries through the bridge and falls back to
recent report tickers when the bridge or watchlist DB is unavailable:

- Python handler: `watchlist.list`
- TS wrapper: `BridgeApi.watchlistList()`
- Params: `{group?, db_path?}`
- Result: entries with `ticker`, `name`, `group`, `tags`, `notes`, `added_at`

## Remaining Follow-Ups

- Add Ink render/keyboard snapshot tests for the home screen, help overlay, and
  dashboard at small terminal sizes.
- Consider a richer watchlist card that includes latest price/rating, matching
  the Python Textual watchlist board.
- Keep any future TUI changes within the split module boundaries above; avoid
  growing `index.tsx` back into a mixed state/service/view file.

## Verification

Current verification matrix:

```bash
pnpm --dir ts typecheck
pnpm --dir ts lint
env HOME=/tmp/etfagents-ts-test-home pnpm --dir ts test
uv run python -m unittest tests.test_bridge_protocol -q
pnpm --dir ts dev tui --help
```
