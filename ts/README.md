# etfagents-ts

TypeScript front-end for ETFAgents. Drives the existing Python codebase as a
black-box JSON-RPC sidecar (`etfagents/bridge`). See [`docs/bridge.md`](../docs/bridge.md)
for the wire protocol.

This package is **internal-use only** for now (no npm publish). The eventual
delivery is a CLI + Ink TUI; Phase 1 only delivers the bridge plumbing.

## Layout

```
ts/
├── src/
│   ├── bridge/           # JSON-RPC client, types, JSON-Schema → Zod, tool factories
│   ├── llm/              # ChatOpenAI built from bridge config
│   └── cli/              # commander entry + commands (Phase 1)
└── test/                 # Vitest tests, mostly black-box against the real sidecar
```

The same repo also owns `etfagents/bridge/` on the Python side. Cross-language
contract changes touch both halves in a single commit.

## Prerequisites

- Node 22+, pnpm 11+
- A working Python venv with project deps. From the repo root:
  ```bash
  uv sync --frozen
  ```
  This produces `<repoRoot>/.venv/bin/python` which the bridge client picks up
  automatically.

## Dev commands

```bash
pnpm install                 # one-time
pnpm typecheck               # tsc --noEmit
pnpm lint                    # biome check
pnpm format                  # biome format --write
pnpm test                    # vitest run
pnpm build                   # emit dist/

# Phase 1 CLI commands (run via tsx during development)
pnpm dev bridge-ping
pnpm dev tool-call <name> [argsJson]
pnpm dev tool-loop <ticker> [--tool name] [--model name] [--question text]
```

## Python interpreter resolution

The bridge client looks for the Python interpreter in this order:

1. `ETFAGENTS_PYTHON` env var (explicit override)
2. `<repoRoot>/.venv/bin/python` (POSIX)
3. `<repoRoot>/.venv/Scripts/python.exe` (Windows)
4. **Fail loud** with an instruction to run `uv sync --frozen`

There is no silent fallback to a system Python — the failures would surface
inside LangChain imports far from the root cause.

## Phase 1 Exit standard

The `tool-loop` command demonstrates a minimal LLM + bridge tool round-trip:

```bash
# Requires:
#   * OPENAI_API_KEY (or provider-specific key — see src/llm/factory.ts)
#   * TUSHARE_TOKEN (for the default get_etf_info tool)
export OPENAI_API_KEY=sk-...
export TUSHARE_TOKEN=...

pnpm dev tool-loop 510300.SH
```

Flow:

1. Spawn the Python sidecar.
2. Pull `tools.list` and the active config from the bridge.
3. Build a `ChatOpenAI` from the bridge config + env API key.
4. Wrap **one** bridge tool (default `get_etf_info`) as a LangChain
   `DynamicStructuredTool`.
5. Loop: invoke LLM → if `tool_calls`, dispatch through the bridge → feed
   results back as `ToolMessage` → repeat until the LLM produces a final
   answer (max 6 iterations).
6. Print the final assistant message.

This proves: subprocess management, JSON-RPC framing/correlation, Pydantic
JSON Schema → Zod conversion, LangChain.js tool calling, and error
propagation across the language boundary.

## What's NOT in Phase 1

- LangGraph orchestration (Phase 2)
- Agent prompts, schemas, debate, manager (Phase 2)
- Memory, validation, reflection (Phase 2)
- Ink TUI, full CLI command coverage (Phase 3)
- Backtest TS-side integration (Phase 4)

## Tests

```bash
pnpm test
```

The suite has 15 tests across three files:

- `python.test.ts` — interpreter discovery fallback chain (uses tempdirs).
- `client.test.ts` — JSON-RPC client driving the real bridge subprocess:
  request correlation, error envelope mapping, timeout semantics.
- `tools.test.ts` — JSON-Schema → Zod conversion (unit) plus end-to-end:
  every Pydantic schema returned by `tools.list` becomes a usable LangChain
  tool.

Black-box tests start the real `python -m etfagents.bridge` subprocess. They
require `<repoRoot>/.venv` to exist (run `uv sync --frozen` once).
