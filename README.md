<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/WeChat-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/Join_GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# ETFAgents: Multi-Agents LLM ETF Investment Framework

## News
- [2026-04] **ETFAgents** aligned the framework around ETF allocation outputs, canonical ETF state keys, checkpoint/resume support, and structured manager/trader reports.
- [2026-03] **ETFAgents** added multi-language support, GPT-5.4 family models, unified model catalog, and backtesting date fidelity.
- [2026-03] **ETFAgents** expanded structured five-tier ratings, OpenAI Responses API support, Anthropic effort control, and cross-platform stability.
- [2026-02] The project foundation was bootstrapped from the open-source **TradingAgents** architecture with multi-provider LLM support and LangGraph orchestration.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> 🎉 **ETFAgents** focuses the TradingAgents architecture on ETF research, allocation, and rebalance workflows.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

<div align="center">

🚀 [ETFAgents](#etfagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#etfagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## ETFAgents Framework

ETFAgents is an ETF-oriented multi-agent investment framework derived from TradingAgents. It keeps the original LangGraph-based multi-agent skeleton, provider abstraction, checkpoint/resume flow, and runtime reporting, while extending the analyst stack toward ETF timing and portfolio construction. The current implementation adds a dedicated `EtfAgentsGraph`, canonical ETF allocation state keys, ETF-specific analysts, ETF universe routing, and candidate-pool ranking for Chinese exchange-traded ETFs.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> ETFAgents is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes ETF allocation work into specialized roles. This ensures the system achieves a robust, scalable approach to market analysis, allocation, and rebalance decisions.

### Analyst Team
- ETF Market Analyst: Reviews ETF price action, turnover, and technical signals such as MACD, RSI, Bollinger Bands, and VWMA.
- ETF Structure Analyst: Evaluates benchmark design, holdings concentration, fund size, fees, tracking features, and structural fit.
- ETF Flow Analyst: Analyzes ETF share changes, primary-market creations/redemptions, liquidity, and fund-flow pressure.
- ETF Macro Analyst: Interprets macro regime, policy catalysts, and cross-asset exposure relevant to ETF allocation.
- Sentiment Analyst: Analyzes social media and public sentiment to gauge short-term market mood around ETF themes.
- News Analyst: Monitors global news and macroeconomic developments, interpreting the impact on ETF sectors, styles, and benchmarks.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Allocation Trader
- Synthesizes analyst and debate outputs into an ETF allocation execution plan, including target weight bands, add/reduce conditions, and rebalance triggers.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager
- Continuously evaluates portfolio risk by assessing volatility, liquidity, correlation, crowding, and drawdown risk. The risk management team adjusts the proposed ETF allocation and provides assessment reports to the Portfolio Manager.
- The Portfolio Manager produces the final ETF allocation decision, including target positioning, rebalance conditions, and risk controls.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

Clone your ETFAgents repository:
```bash
git clone <your-etfagents-repo-url>
cd etfagents
```

Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n etfagents python=3.13
conda activate etfagents
```

Install the package and its dependencies:
```bash
pip install .
```

### Required APIs

ETFAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export MINIMAX_API_KEY=...         # MiniMax
export OPENROUTER_API_KEY=...      # OpenRouter
export TUSHARE_TOKEN=...           # Tushare (A-share / HK / US price and fundamentals)
export BRAVE_SEARCH_API_KEY=...    # Brave Search (news search)
```

For local models, configure Ollama with `llm_provider: "ollama"` in your config.

Alternatively, copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

By default, ETFAgents stores runtime logs under `~/.etfagents/logs` and cache data under `~/.etfagents/cache`. Override them with `ETFAGENTS_RESULTS_DIR` and `ETFAGENTS_CACHE_DIR` if needed. Legacy `TRADINGAGENTS_RESULTS_DIR` and `TRADINGAGENTS_CACHE_DIR` remain supported as fallbacks.

### CLI Usage

Launch the interactive CLI:
```bash
etfagents          # installed command
python -m cli.main     # alternative: run directly from source
```
You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more.

To make long-running analyses resumable after interruption, enable checkpoints:

```bash
etfagents analyze --checkpoint
etfagents analyze --clear-checkpoints --checkpoint
```

Trading decisions are also written to a persistent memory log at `results/trading_memory.md` by default. You can change this with `memory_log_path`, and optionally cap resolved entries with `memory_log_max_entries`.

For a direct provider-level sanity check of the structured Research Manager / Trader / Portfolio Manager flow, run `python scripts/smoke_structured_output.py <provider>`.

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## ETFAgents Package

### Implementation Details

We build ETFAgents on LangGraph so the ETF analyst pipeline, debate loops, and portfolio decision chain remain modular. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, MiniMax, OpenRouter, and Ollama.

### Python Usage

To use ETFAgents inside your code, import the `etfagents` module and initialize an `EtfAgentsGraph()` object. The `.propagate()` function returns the final allocation-oriented decision. You can run `main.py`, here's also a quick example:

```python
from etfagents.graph.etf_graph import EtfAgentsGraph
from etfagents.default_config import DEFAULT_CONFIG

ta = EtfAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("510300.SH", "2026-01-15")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from etfagents.graph.etf_graph import EtfAgentsGraph
from etfagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, minimax, openrouter, ollama
config["deep_think_llm"] = "gpt-5.4"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5.4-mini" # Model for quick tasks
config["max_debate_rounds"] = 2

ta = EtfAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("510300.SH", "2026-01-15")
print(decision)
```

See `etfagents/default_config.py` for all configuration options.

## Contributing

We welcome contributions from the community! Whether it's fixing a bug, improving documentation, or suggesting a new feature, your input helps make this project better. If you are interested in this line of research, please consider joining our open-source financial AI research community [Tauric Research](https://tauric.ai/).

## Citation

Please reference the upstream TradingAgents work if ETFAgents or its parent architecture helps your research.

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
