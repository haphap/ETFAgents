# Development

## Setup

```bash
git clone https://github.com/haphap/ETFAgents.git && cd ETFAgents
python -m venv .venv && source .venv/bin/activate
pip install .                 # or: uv venv && uv pip install -e .
cd ts && pnpm install --frozen-lockfile
cp ../.env.example ../.env
```

The TS front-end auto-discovers `<repo>/.venv/bin/python` (override with
`ETFAGENTS_PYTHON`) and spawns the bridge subprocess.

## Release metadata

Current release metadata is split across the Python and TypeScript packages:

- Python package version: `0.5` in `pyproject.toml` and `uv.lock`.
- TypeScript package / CLI version: `0.5.0` in `ts/package.json` and
  `ts/src/cli/index.ts`.
- License: Apache-2.0, with the full text in the repository root `LICENSE`.

When bumping a release, update the package metadata, README badges, and this
wiki page together.

## Verification matrix

All green before opening a PR:

```bash
# Python
python -m unittest discover -s tests -q
# TypeScript (run from ts/)
cd ts && pnpm typecheck && pnpm lint && pnpm test
```

CI (`.github/workflows/ci.yml`, `etfagents-ci`) runs two jobs on push/PR to
`main`: a **python** job (`pip install .` + `tests.test_bridge_protocol`) and a
**typescript** job (`pnpm lint && pnpm typecheck && pnpm test`).

## Conventions

- **Python**: 4-space indent, snake_case, PascalCase classes. Prefer repository
  helpers: `create_llm_client()`, `route_to_vendor()`, localization helpers, and
  `copy.deepcopy(DEFAULT_CONFIG)` before mutating config.
- **TypeScript**: formatted/linted by **biome** (`pnpm lint` / `pnpm format`).
  The repo uses `exactOptionalPropertyTypes` — omit optional keys rather than
  assigning `undefined`.
- **Tests**: Python `unittest` in `tests/test_*.py`; TS `vitest` in `ts/test/`.
  Mock network / LLM / vendor calls unless a test is explicitly integration.
- **Tickers**: always preserve full exchange suffixes (`510300.SH`, `7203.T`).

## Adding a bridge method

1. Register `@method("namespace.action")` in `etfagents/bridge/handlers/<x>.py`.
2. Import the handler module in `etfagents/bridge/handlers/__init__.py`.
3. Add a typed wrapper in `ts/src/bridge/types.ts` (`BridgeApi`).
4. Add a focused test (e.g. `tests/test_bridge_*.py`).

## Adding an agent node

TS analyst nodes are built with `createAnalystNode` (shared tool-loop factory)
in `ts/src/agents/nodes/`. Debate/manager nodes set `appendMessage: false` and
supply a `buildContextBlock`. Wire new nodes into `ts/src/graph/full_graph.ts`.

See [`AGENTS.md`](https://github.com/haphap/ETFAgents/blob/main/AGENTS.md) for
project-wide rules.
