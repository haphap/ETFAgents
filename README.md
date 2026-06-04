<div align="center">

<!-- LOGO PLACEHOLDER · 在此放置项目 Logo / Banner (docs/assets/etfagents-banner.png) -->

# 📊 ETFAgents

**多智能体 ETF 研究与配置框架**
_A multi-agent ETF research & allocation framework, built on LangGraph._

[![CI](https://github.com/haphap/ETFAgents/actions/workflows/ci.yml/badge.svg)](https://github.com/haphap/ETFAgents/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-3776AB?logo=python&logoColor=white)
![Node](https://img.shields.io/badge/Node-%E2%89%A522-339933?logo=node.js&logoColor=white)
![Output](https://img.shields.io/badge/output-中文%20%2F%20English-informational)
![Status](https://img.shields.io/badge/use-research%20only-orange)

> 6 位分析师 · 多空研究辩论 · 风险三辩 + 组合经理 · 智能体记忆 · Backtrader 回测 · 纸上交易 —— 全部跑在一个混合 **Python sidecar + TypeScript 前端** 架构上，两端通过**行分隔 JSON-RPC over stdio** 通信。

</div>

> ⚠️ **ETFAgents 仅用于研究与实验，不构成任何投资建议。**
> ETFAgents is for research and experimentation only — **not financial advice.**

---

## 📑 目录 (Table of Contents)

- [关于项目 (About)](#-关于项目-about)
- [技术栈与环境要求 (Tech Stack & Prerequisites)](#️-技术栈与环境要求-tech-stack--prerequisites)
- [快速上手 (Getting Started)](#-快速上手-getting-started)
  - [安装 (Installation)](#安装-installation)
  - [使用 (Usage)](#使用-usage)
- [核心架构与目录结构 (Architecture & Project Structure)](#️-核心架构与目录结构-architecture--project-structure)
- [配置 (Configuration)](#-配置-configuration)
- [贡献指南 (Contributing)](#-贡献指南-contributing)
- [开源协议与致谢 (License & Acknowledgments)](#-开源协议与致谢-license--acknowledgments)

---

## 🎯 关于项目 (About)

**ETFAgents** 协调一支分层的智能体团队，对 ETF（A 股与全球宽基）产出**结构化配置决策**：6 位专业分析师 → 多空研究辩论 → 研究经理 → 交易员 → 风险三辩 → 组合经理。它采用混合架构：**重逻辑（行情/财务数据、Backtrader 回测、纸上交易、记忆存储）留在 Python sidecar，编排 / LLM / CLI / TUI 交给 TypeScript 前端**，两端通过**行分隔 JSON-RPC over stdio** 通信。

**解决的痛点 (Pain Points):**

- 单一 LLM「分析师」缺乏对抗、缺乏记忆、容易自说自话 —— ETFAgents 用分层 agent 群体 + 多空/风险对抗 + 跨运行记忆来应对。
- ETF 研究停留在「代码层」、看不清持仓与行业传导 —— 6 位分析师把宏观→行业→重仓股→ETF 定价串成完整逻辑链。
- A 股本地化数据与 ETF 产品规则缺位 —— 内置 Tushare / akshare / yfinance / FRED / Brave 等**厂商路由数据层**，纸上交易内建 **A 股 ETF 规则（T+1 / 佣金 / 最小交易单位）**。

**核心特性 (Key Features):**

- 🧠 **分层多智能体**：6 位分析师（市场与资金流 · 舆情与事件 · 宏观框架 · 中观大宗 · 持仓行业 · 头部持仓）→ 多空研究员 + 研究经理 → 交易员 → 激进/保守/中性三辩 → 组合经理 → 记忆写回，由 **LangGraph.js** 编排成单次完整流水线。
- 🔁 **多轮辩论 (Multi-round)**：多空与风险辩论可按 `maxDebateRounds` / `maxRiskRounds` 循环，由 `routeDebate` / `routeRiskDebate` 驱动并以累计回合数终止。
- 🧬 **智能体记忆 (Memory)**：运行结束写回 `analysis_memory_entry`（延续性 / 经验教训 / 方法手册），下次运行前由 `memory.build_context` 注入到图初始状态——**先读后写**的闭环。
- 📊 **Backtrader 回测 + 纸上交易**：结构化触发信号驱动的回测（NAV / 基准对比 / 指标 / 健康检查），以及多用户纸上交易引擎（T+1、佣金、最小交易单位、bcrypt 鉴权）。
- 🖥️ **Ink TUI 终端仪表盘**：实时研究面板（团队标签 + 团队详情弹窗 + 章节阅读器）、报告库、自选、回测查看、纸上交易快照、错误详情，以及分析师选择 / 研究深度 / 辩论轮数等配置。
- 🌐 **多 LLM Provider + 厂商路由数据**：LLM 走 OpenAI 兼容工厂（OpenAI / DeepSeek / xAI / OpenRouter / Ollama / MiniMax / vLLM）+ Python 端原生 Anthropic / Google；数据按 `route_to_vendor()` 在 Tushare / yfinance / akshare / FRED / Brave / qlib 间路由。
- 🈶 **中英文输出**：分析报告与最终决策支持中文 / English。

---

## 🛠️ 技术栈与环境要求 (Tech Stack & Prerequisites)

| 层 (Layer)           | 技术 (Stack)                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| **Python sidecar**   | Python `≥3.10` · langchain-core / langgraph · pandas · Backtrader · Tushare / akshare / yfinance · SQLite checkpoint · Typer + Rich CLI |
| **TypeScript 前端**  | Node `≥22` · LangGraph.js `^1.3` · `@langchain/{core,openai}` · commander · zod · Ink `^5` + React `18` |
| **工具链 (Tooling)** | pip / [uv](https://github.com/astral-sh/uv) (Python) · pnpm `11` · biome · vitest · pytest / unittest · GitHub Actions CI |

**运行前置条件 (Prerequisites):**

- 🐍 **Python ≥ 3.10**（推荐用 `uv` 或 `venv` 管理虚拟环境）
- 🟢 **Node.js ≥ 22** 与 **pnpm 11**（仅 TypeScript 前端需要）
- 🔑 **API 凭证**（按需，写入 `.env`，参考 `.env.example`）：
  - `TUSHARE_TOKEN` —— A 股 ETF 行情 / 财务（核心数据源）
  - LLM keys —— `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY` / `MINIMAX_API_KEY` / `OPENROUTER_API_KEY`（按所用 provider 填写；本地 Ollama / vLLM 无需 key）
  - 可选数据源 —— `FRED_API_KEY` / `BRAVE_SEARCH_API_KEY` / `ALPHA_VANTAGE_API_KEY`

---

## 🚀 快速上手 (Getting Started)

### 安装 (Installation)

```bash
# 1. 克隆仓库
git clone https://github.com/haphap/ETFAgents.git
cd ETFAgents

# 2. Python sidecar：创建虚拟环境并安装包（含 etfagents 控制台脚本）
python -m venv .venv && source .venv/bin/activate
pip install .          # 或：uv venv && uv pip install -e .

# 3. 配置环境变量
cp .env.example .env   # 填入 TUSHARE_TOKEN 与所用 LLM provider 的 key

# 4. （可选）TypeScript 前端
cd ts
pnpm install --frozen-lockfile
```

> 💡 TS 前端会自动发现 `<repo>/.venv/bin/python` 并以子进程方式拉起 Python bridge；可用 `ETFAGENTS_PYTHON` 覆盖解释器路径。

### 使用 (Usage)

**TypeScript 前端**（在 `ts/` 下，开发期用 `pnpm dev <command>`，构建后用 `etfagents <command>`）：

```bash
cd ts

pnpm dev analyze-mini 510300.SH                 # 最小 1-分析师流水线（最快验证）
pnpm dev analyze 510300.SH                      # 完整 6-分析师流水线 → 辩论 → 交易 → 风控 → 决策
pnpm dev analyze-pool 510300.SH 159915.SZ       # 多标的排序
pnpm dev backtest 510300.SH --start-date 2024-01-01 --end-date 2024-06-01
pnpm dev paper account                          # 纸上交易账户
pnpm dev detail 510300.SH                       # ETF 信息查询
pnpm dev cache stats                            # 缓存管理
pnpm dev tui                                    # 全屏交互式 Ink 终端仪表盘（也可 pnpm tui）
```

**Python CLI**（`pip install .` 后提供 `etfagents` 控制台脚本）：

```bash
python -m cli.main            # 或：etfagents —— 交互式 CLI
etfagents cache stats
etfagents cache cleanup --days 30
etfagents backtest --tickers 510300.SH,159915.SZ --benchmark-tickers equal_weight_pool \
  --start-date 2026-01-02 --end-date 2026-03-31
```

> ⚙️ 输出语言由 `output_language` 配置（中文 / English）。保留完整代码与交易所后缀（如 `510300.SH` / `159915.SZ` / `7203.T`）。

---

## 🏗️ 核心架构与目录结构 (Architecture & Project Structure)

```text
TypeScript 前端 (ts/)              JSON-RPC / stdio        Python sidecar (etfagents/ + cli/)
────────────────────────          ───────────────         ──────────────────────────────────
CLI (commander) + TUI (Ink)                               bridge/    (JSON-RPC 服务 + handlers)
LangGraph.js 完整流水线:                                   agents/ · graph/ · dataflows/
  6 分析师 → 多空辩论 ⇄          行分隔 JSON  ⇄            backtest/ (Backtrader) · paper_trading/
  → 研究经理 → 交易员                                       llm_clients/ · cache_manager · watchlist
  → 风险三辩 → 组合经理 → 记忆                              持久化: SQLite checkpoint + 结果目录
LLM 工厂 · 回测信号提取
```

```text
ETFAgents/
├── etfagents/                  # 🐍 Python sidecar
│   ├── bridge/                 #   JSON-RPC over stdio + handlers/ (tools/config/cache/paper/backtest/memory/watchlist)
│   ├── agents/                 #   analyst / researcher / trader / risk / manager 角色 + utils
│   ├── graph/                  #   LangGraph 编排、checkpoint、回放、信号处理
│   ├── dataflows/              #   Tushare / yfinance / akshare / FRED / Brave + route_to_vendor()
│   ├── llm_clients/            #   多 provider 归一化 (OpenAI / Anthropic / Google / ...)
│   ├── backtest/               #   Backtrader 引擎 + 结果产物 (nav/metrics/trades/...)
│   ├── paper_trading/          #   A 股 ETF 纸上交易 (T+1 / 佣金 / 最小单位 / 多用户)
│   ├── watchlist.py · detail.py · cache_manager.py · default_config.py
├── cli/                        # ⌨️ Typer/Rich Python CLI (etfagents 控制台脚本) + Textual TUI
├── ts/                         # 🟦 TypeScript 前端
│   └── src/
│       ├── bridge/             #   BridgeClient + 类型化 RPC 封装
│       ├── llm/                #   OpenAI 兼容 LLM 工厂
│       ├── agents/             #   nodes · helpers · prompts · schemas · state
│       ├── graph/              #   full_graph LangGraph.js 装配
│       ├── cli/commands/       #   analyze / analyze-pool / backtest / paper / detail / cache / ...
│       └── tui/                #   Ink TUI shell + model/runner/services/screens
├── tests/                      # ✅ Python unittest
├── docs/ · pyproject.toml · ts/package.json · .github/workflows/ci.yml
```

> 📐 **架构原则**：工具调用边界一律用字符串 / JSON（无跨语言 DataFrame 传输）；优先复用仓库 helper（`create_llm_client()` / `route_to_vendor()` / 本地化标签 / `copy.deepcopy(DEFAULT_CONFIG)`）。协议细节见 [`docs/bridge.md`](docs/bridge.md)，TS 布局见 [`ts/README.md`](ts/README.md)。

---

## 🔧 配置 (Configuration)

```bash
cp .env.example .env
```

| 变量 (Variable)                          | 说明 (Description)                                  |
| ---------------------------------------- | --------------------------------------------------- |
| `TUSHARE_TOKEN`                          | A 股 ETF 行情 / 财务（核心数据源）                  |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` …  | 各 LLM provider 凭证（按所用 provider 填写）        |
| `FRED_API_KEY` / `BRAVE_SEARCH_API_KEY`  | 可选：全球宏观 / 新闻搜索                            |
| `ETFAGENTS_RESULTS_DIR`                  | 结果与日志目录（默认 `~/.etfagents/logs`）          |
| `ETFAGENTS_CACHE_DIR`                    | 缓存目录（默认 `~/.etfagents/cache`）               |

> 🔒 请勿提交 `.env` 与任何密钥。运行日志默认落 `~/.etfagents/logs`、缓存落 `~/.etfagents/cache`。

---

## 🤝 贡献指南 (Contributing)

欢迎 Issue 与 PR！请遵循以下约定：

1. **Issue**：报告 bug 请附复现步骤、期望/实际行为与环境（Python / Node 版本）；功能建议请说明动机与使用场景。
2. **提交前自检 (Verification Matrix)** —— 全绿方可提 PR：
   ```bash
   # Python
   python -m unittest discover -s tests -q
   # TypeScript
   cd ts && pnpm typecheck && pnpm lint && pnpm test
   ```
3. **风格 (Style)**：Python 四空格缩进、snake_case、PascalCase 类；TS 由 biome 统一格式。Mock 网络 / LLM / 厂商调用，除非测试明确是集成型。
4. **PR**：聚焦单一关注点；描述需包含「改了什么 / 怎么测的 / 配置或环境影响」；保持默认行为向后兼容，新能力以**可选开关 (opt-in)** 引入。终端渲染变化请附截图或示例输出。

> 📚 更多约定见 [`AGENTS.md`](AGENTS.md)（项目级规则）与 [`docs/`](docs/) 下的设计笔记。

---

## 📜 开源协议与致谢 (License & Acknowledgments)

### License

⚠️ 本仓库**尚未附带开源协议文件**。发布前请先添加 `LICENSE`。在此之前，默认保留所有权利。
This repository does **not yet include a license** — add a `LICENSE` file before publishing.

### 致谢 (Acknowledgments)

- 🔗 **[LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph)** —— Agent 编排框架（Python + LangGraph.js）。
- 📈 **[Backtrader](https://www.backtrader.com/)** —— 回测引擎。
- 🇨🇳 **[Tushare](https://tushare.pro/) · [akshare](https://akshare.akfamily.xyz/) · [yfinance](https://github.com/ranaroussi/yfinance) · [FRED](https://fred.stlouisfed.org/)** —— A 股与全球行情 / 宏观数据。
- 🖥️ **[Ink](https://github.com/vadimdemedes/ink) · [Typer](https://typer.tiangolo.com/) · [Rich](https://github.com/Textualize/rich)** —— 终端 UI。

---

<div align="center">
<sub>Built with 📊 by the ETFAgents contributors · Python sidecar × TypeScript front-end · 仅供研究 / research only</sub>
</div>
