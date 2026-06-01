# Configuration

## Environment variables (`.env`)

Copy `.env.example` to `.env`. Never commit secrets.

| Variable | Description |
| --- | --- |
| `TUSHARE_TOKEN` | A-share ETF quotes / financials (core data source) |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY` / `MINIMAX_API_KEY` / `OPENROUTER_API_KEY` | LLM provider keys (set the ones you use; local Ollama / vLLM need none) |
| `FRED_API_KEY` / `BRAVE_SEARCH_API_KEY` / `ALPHA_VANTAGE_API_KEY` | Optional: global macro / news search |
| `ETFAGENTS_RESULTS_DIR` | Results + logs dir (default `~/.etfagents/logs`) |
| `ETFAGENTS_CACHE_DIR` | Cache dir (default `~/.etfagents/cache`) |
| `ETFAGENTS_PYTHON` | Override the Python interpreter the TS front-end spawns |

Legacy `TRADINGAGENTS_RESULTS_DIR` / `TRADINGAGENTS_CACHE_DIR` are still honored.

## Key config fields (`DEFAULT_CONFIG`)

| Key | Meaning |
| --- | --- |
| `output_language` | Report / decision language (`Chinese` / `English`) |
| `llm_provider` | Default LLM provider |
| `deep_think_llm` / `quick_think_llm` | Deep-tier (managers/trader/PM) and quick-tier (analysts/debators) models |
| `backend_url` | LLM base URL override |
| `max_debate_rounds` / `max_risk_discuss_rounds` | Research / risk debate rounds (default 1) |
| `research_depth_name` | Research depth label (`标准` etc.) |
| `report_context_char_limit` | Per-report prompt truncation budget |
| `results_dir` / `data_cache_dir` | Result and cache roots |
| `memory_mode` | `full` / `continuity-only` / `lesson` / `disabled` |

The memory **config hash** is derived from `llm_provider`, `deep_think_llm`,
`quick_think_llm`, `max_debate_rounds`, `max_risk_discuss_rounds`,
`output_language`, and `backend_url` — so a run's stored/read memory matches the
exact model + round configuration it ran under.

## Memory modes

- `full` — continuity + lessons + method playbook context.
- `continuity-only` — only the previous-run continuity brief.
- `lesson` — continuity + outcome lessons (no method playbook).
- `disabled` — no memory read/write (the writer node is a no-op).
