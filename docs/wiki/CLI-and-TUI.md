# CLI & TUI

## TypeScript front-end

Run from `ts/` with `pnpm dev <command>` (development) or `etfagents <command>`
after `pnpm build`.

| Command | Purpose |
| --- | --- |
| `analyze-mini <ticker>` | Minimal 1-analyst pipeline (fastest smoke test) |
| `analyze <ticker>` | Full 6-analyst pipeline → debate → trader → risk → decision |
| `analyze-pool <tickers...>` | Multi-ticker analysis ranked by rating / target weight |
| `backtest <ticker> --start-date … --end-date …` | Backtrader candidate-pool backtest |
| `paper <account\|positions\|trades\|buy\|sell\|…>` | Paper-trading account management |
| `detail <ticker>` | ETF info lookup |
| `cache <stats\|cleanup\|clear>` | Cache management |
| `tui` | Interactive Ink terminal dashboard |

Developer utilities: `bridge-ping`, `tool-call`, `tool-loop`.

```bash
cd ts
pnpm dev analyze 510300.SH
pnpm dev analyze-pool 510300.SH 159915.SZ
pnpm dev backtest 510300.SH --start-date 2024-01-01 --end-date 2024-06-01
pnpm dev tui       # or: pnpm tui
```

## Python CLI

`pip install .` provides the `etfagents` console script (Typer/Rich):

```bash
python -m cli.main            # or: etfagents  (interactive CLI)
etfagents cache stats
etfagents cache cleanup --days 30
etfagents backtest --tickers 510300.SH,159915.SZ --benchmark-tickers equal_weight_pool \
  --start-date 2026-01-02 --end-date 2026-03-31
```

## TUI screens (Ink)

The TUI (`pnpm dev tui` or `pnpm tui`) opens in the terminal alternate screen,
restores the previous terminal contents on exit, and provides home navigation
across several workflow screens:

- **Research dashboard** — ticker input → config → live dashboard. Team tabs
  (analysts / research / trader / risk / decision) show inline completion
  counts; `Enter` opens the team-detail overlay for section selection, and the
  report reader scrolls with `PgUp/PgDn`. The screen also includes an ETF info
  card, a multi-ticker queue, and a stats bar.
- **Config screen** — date, provider, model (incl. vLLM model discovery that
  probes `http://127.0.0.1:8020/v1` before `http://localhost:8000/v1` and uses
  the discovered endpoint),
  research depth (`快速=1/1`, `标准=2/2`, `深度=3/3` debate/risk rounds),
  analyst selection, and manual round steppers.
- **Report library** (`Ctrl+L`) — browse historical reports from the results
  directory and read them with the same scroll viewer.
- **Watchlist** — quick-select real watchlist entries when available, falling
  back to recent report tickers.
- **Backtest viewer** (`Ctrl+B`) — NAV sparkline, metrics, benchmark
  comparison, and health warnings from saved backtest artifacts.
- **Paper trading** (`Ctrl+P`) — account snapshot, positions, recent trades.
- **Error detail overlay** (`e`) — structured failure detail (ticker, message,
  stack, timestamp).
- **Help overlay** (`?`) — per-screen keybindings.

Implementation note: `ts/src/tui/index.tsx` is only the Ink app shell. Shared
state/reducer helpers live in `ts/src/tui/model.ts`, graph execution in
`ts/src/tui/runner.ts`, artifact loading in `ts/src/tui/services/`, and screen
components in `ts/src/tui/screens.tsx`. Full-screen terminal lifecycle code
lives in `ts/src/tui/terminal.ts`.

> Output language is set by the `output_language` config (中文 / English).
> Always preserve full exchange-suffixed tickers (`510300.SH`, `159915.SZ`).
