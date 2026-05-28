# ETFAgents Bridge — JSON-RPC Sidecar

The bridge (`etfagents/bridge/`) exposes the existing Python codebase as an
external JSON-RPC service over stdio. It exists so a TypeScript CLI (and any
other non-Python runtime) can drive ETFAgents as a black box without
embedding a Python interpreter or reimplementing the data layer.

The bridge **does not modify any code outside `etfagents/bridge/`**. It is a
thin re-exporter: every method delegates to existing public APIs.

## Quick start

```bash
# 1. Install deps in a uv-managed venv
uv sync --frozen

# 2. Spawn the bridge (stdio)
.venv/bin/python -m etfagents.bridge
```

Send one JSON value per line on stdin, read one JSON value per line on stdout.
All logging goes to stderr.

## Wire protocol

* **Framing**: newline-delimited JSON. One JSON value per line, both directions.
* **Spec**: JSON-RPC 2.0 (`jsonrpc: "2.0"`, request `id` echoed back).
* **Encoding**: UTF-8.
* **Channels**: stdin (requests in), stdout (responses out, never anything
  else), stderr (logs and unhandled stack traces).
* **Concurrency**: serial. The server processes one request at a time; pending
  requests on stdin are buffered. This keeps the underlying state — config
  `ContextVar`s, SQLite connections, the LangChain tool registry — simple.

A request:

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools.call",
 "params": {"name": "get_news", "args": {"ticker": "510300.SH",
                                          "start_date": "2024-01-01",
                                          "end_date": "2024-01-31"}}}
```

A success response:

```json
{"jsonrpc": "2.0", "id": 1, "result": {"text": "..."}}
```

An error response:

```json
{"jsonrpc": "2.0", "id": 1,
 "error": {"code": -32001, "message": "DataVendorUnavailable: ..."}}
```

## Method catalog

| Method | Description |
|---|---|
| `tools.list` | List every LangChain `@tool` discovered in `etfagents/agents/utils/*_tools.py`. Returns `[{name, description, args_schema}, ...]`. `args_schema` is the Pydantic v2 JSON Schema produced by `args_schema.model_json_schema()`. |
| `tools.call` | Invoke a tool. Params: `{name, args, context?}`. `context` is `{as_of_date, mode}`; when set with `mode="backtest"` the existing `backtest_context()` clamps date arguments before dispatch. Returns `{text}` (the tool's string output). |
| `config.default` | Return a deep copy of `etfagents.default_config.DEFAULT_CONFIG`. |
| `config.get` | Return the active config for this process. |
| `config.set` | Replace the active config. Params: `{config}`. Returns the merged config. |
| `cache.stats` | Per-category cache breakdown (`api`, `signals`, `snapshots`, `checkpoints`, `total_mb`). |
| `cache.cleanup` | Remove cache entries older than `days`. Params: `{days, category?}` where category ∈ `{api, signals, snapshots, checkpoints, all}`. |
| `cache.clear` | Wipe a category. Params: `{category}`. |
| `cache.details` | Paginated entry list for a category. Params: `{category, page?, page_size?}`. |
| `paper.register` | Create a paper trading user. Params: `{username, password}`. |
| `paper.login` | Login. Params: `{username, password}`. Returns `{ok, username}`. |
| `paper.logout` | Returns `{logged_out}`. |
| `paper.current_user` | Returns `{user}` (always defined; `"default"` when no session). |
| `paper.get_account` | Params: `{user_id?}`. Returns account dict. |
| `paper.reset_account` | Params: `{user_id?, initial_cash?}`. |
| `paper.buy` | Params: `{ticker, quantity, user_id?, analysis_id?}`. Quantity must be a positive multiple of 100 (A-share lot size). |
| `paper.sell` | Params: `{ticker, quantity, user_id?, analysis_id?}`. |
| `paper.get_positions` | Params: `{user_id?}`. |
| `paper.get_trades` | Params: `{user_id?, limit?}`. |
| `paper.suggest_order_from_signal` | Params: `{ticker, state, user_id?}`. |
| `backtest.run_candidate_pool` | Run a Backtrader candidate-pool backtest with **TS-precomputed signals**. See "Backtest contract" below. |

All `paper.*` methods accept an optional `db_path` param to override the
default SQLite location (used by tests).

## Backtest contract

The backtest engine reaches back into the agent graph at every rebalance date
to call `graph.analyze_candidate_pool(tickers, decision_date)`. Because the
TS side will own the agent graph after migration, the bridge does **not** call
back into TS during a run. Instead, TS pre-computes the analysis payload for
every rebalance date and submits the entire bundle.

`backtest.run_candidate_pool` params:

```jsonc
{
  "tickers": ["510300.SH", "159915.SZ"],
  "start_date": "2026-01-02",
  "end_date": "2026-03-31",

  // Required: keyed by decision_date (yyyy-mm-dd), value is the same shape
  // EtfAgentsGraph.analyze_candidate_pool would return for that date.
  "signals": {
    "2026-01-02": [
      {"ticker": "510300.SH", "rating": "BUY", "score": "5",
       "market_flow_report": "...",  /* ... all _report keys ... */
       "research_allocation_plan": "...", "trader_allocation_plan": "...",
       "final_allocation_decision": "...",
       "backtest_signal": { /* BacktestSignal-shaped dict */ },
       "suggested_weight_pct": 60.0},
      {"ticker": "159915.SZ", /* ... */}
    ],
    "2026-01-23": [/* ... */]
  },

  // Optional, with same defaults as run_candidate_pool_backtest():
  "rebalance_interval_days": 21,
  "top_k": 3,
  "execution_timing": "same_close",      // or "next_open" | "next_close"
  "initial_cash": 1000000.0,
  "commission": 0.0,
  "slippage_perc": 0.0,
  "cash_buffer_pct": 0.0,
  "benchmark_tickers": ["equal_weight_pool"],
  "force_refresh": false,
  "default_benchmark_ticker": "510300.SH"  // shim fallback when benchmark_tickers is null
}
```

The result is `BacktraderBacktestResult.to_dict()` with NaN/±Infinity values
replaced by `null` so it is strict-JSON-parseable.

The bridge loads price frames itself (via the existing `route_to_vendor`
chain), so price data does not cross the language boundary.

## Error codes

| Code | Meaning |
|---|---|
| `-32700` | Parse error — request line is not valid JSON. |
| `-32600` | Invalid request — missing or malformed JSON-RPC envelope. |
| `-32601` | Method not found. |
| `-32602` | Invalid params — caller-side validation failed. |
| `-32603` | Internal error — unhandled Python exception. `data.traceback` is included. |
| `-32001` | Tool execution error. |
| `-32002` | Backtest mode rejected the call (date bounds violation). |
| `-32003` | Data vendor unavailable. |
| `-32010` | `config.*` error. |
| `-32020` | `paper.*` error (validation / SQLite / business rule). |
| `-32030` | `backtest.*` error. |

## Backtest date-bounds context

For historical analysis runs, the existing dispatcher (`route_to_vendor`)
clamps any date argument that exceeds `as_of_date` and rejects calls to
unbounded news endpoints. The bridge wires this transparently:

```jsonc
{
  "method": "tools.call",
  "params": {
    "name": "get_etf_price_data",
    "args": {"ticker": "510300.SH", "start_date": "2020-01-01",
             "end_date": "2024-12-31"},
    "context": {"mode": "backtest", "as_of_date": "2020-06-01"}
  }
}
```

Inside the handler, the bridge enters `etfagents.dataflows.config.backtest_context(as_of_date, mode)`
before invoking the tool, then exits on return. No state leaks to the next
request.

## Example: 100-line Python client

A self-contained client that drives the bridge. Runnable as
`python docs/bridge_client_demo.py` after `uv sync`. It deliberately does
**not** import `etfagents` directly — it talks to the bridge as a black box.

See [`bridge_client_demo.py`](./bridge_client_demo.py).

## TypeScript client

The TS implementation lives at [`ts/`](../ts/). It wraps this protocol in a
`BridgeClient` class with typed RPC method helpers and converts `tools.list`
output into LangChain `DynamicStructuredTool` instances. See [`ts/README.md`](../ts/README.md)
for layout, dev commands, and the Phase 1 Exit demo.
