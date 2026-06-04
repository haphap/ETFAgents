# Bridge Protocol

The TypeScript front-end drives the Python sidecar over **newline-delimited
JSON-RPC 2.0 over stdio**. Each line is one request or response object.

- Server entry point: `python -m etfagents.bridge`.
- Client: `BridgeClient` (`ts/src/bridge/client.ts`); typed wrappers in
  `BridgeApi` (`ts/src/bridge/types.ts`).
- Errors map to JSON-RPC `{error}` envelopes (`RpcError` with `code`/`message`).

## Methods

| Method | Purpose |
| --- | --- |
| `tools.list` | List available data/analysis tools + their JSON schemas |
| `tools.call` | Invoke a tool by name with args (+ optional live/backtest context) |
| `config.default` / `config.get` / `config.set` | Read defaults / read / write the effective config |
| `cache.stats` / `cache.cleanup` / `cache.clear` / `cache.details` | Cache management |
| `paper.current_user` / `paper.get_account` / `paper.get_positions` / `paper.get_trades` | Paper-trading reads |
| `paper.register` / `paper.login` / `paper.logout` / `paper.buy` / `paper.sell` | Paper-trading actions |
| `watchlist.list` | List watchlist entries for a group (`group`, optional `db_path`) |
| `backtest.run_candidate_pool` | Run a Backtrader candidate-pool backtest from a precomputed signal bundle |
| `memory.build_context` | Build per-role continuity/lesson/method context (memory **read**) |
| `memory.append_analysis` | Persist an analysis memory entry (memory **write**) |

## Conventions

- Tool calls cross the boundary as **strings / JSON** — no DataFrames.
- `memory.append_analysis` / `memory.build_context` accept an optional `config`
  (the effective runtime config) and `selected_analysts`; an explicit empty
  `selected_analysts` is preserved (not coerced to "all"), and a non-list value
  is rejected with `INVALID_PARAMS`.
- Adding a method: register it with `@method("namespace.action")` in
  `etfagents/bridge/handlers/`, import the module in `handlers/__init__.py`, and
  add a typed wrapper in `ts/src/bridge/types.ts`.

See [`docs/bridge.md`](https://github.com/haphap/ETFAgents/blob/main/docs/bridge.md)
for the full protocol notes.
