# TUI 全局外观重构计划

## Summary

按 Backlog.md 的“终端任务板”方向重构 ETFAgents TUI：深色 slate 基底、蓝色主强调、绿色/黄色/红色状态色、清晰面板边界、紧凑高信息密度。目标不是做营销页，而是把现有 Textual 工具改成更像本地工作台的操作界面。

参考来源：

- Backlog.md README: https://github.com/MrLesk/Backlog.md
- 终端 board GIF: https://github.com/MrLesk/Backlog.md/blob/main/.github/backlog-v1.40.gif
- Web UI 截图: https://github.com/MrLesk/Backlog.md/blob/main/.github/web.jpeg
- Backlog.md Web 样式基调：slate 深色背景、blue 主强调、green/yellow 语义状态、紧凑任务卡片；终端交互借鉴其 board 的文本优先风格，避免大块按钮。

## Visual Direction

- 视觉关键词：terminal kanban、dark slate、compact dashboard、status chips、task cards、text actions。
- 基底颜色：`#0f172a` / `#111827` 类深色背景，面板使用 `#1e293b`，次级面板使用 `#334155`。
- 主强调色：蓝色 `#3b82f6` 或 Textual 对应 accent，用于当前选中、高亮条、滚动条和焦点边框。
- 状态色：
  - 成功/完成：green。
  - 运行/等待：yellow 或 cyan。
  - 风险/失败：red。
  - 弱信息：slate gray。
- 组件风格：
  - 列表项像 backlog task card：单行可扫读，选中态明显。
  - 面板像 kanban column：标题固定、内容紧凑、边界清晰。
  - 底部统计栏像 status strip：一行展示 Agents、LLM、Tools、Tokens、Reports、Elapsed。
  - 动作控件尽量像文本命令：不用大面积填充色按钮，使用左侧高亮条、下划线、反色焦点或短状态前缀表达可操作性。

## Minimal Interaction Style

当前 UI 的块状按钮观感过重。重构时按钮仍可使用 Textual `Button` 组件以保留事件和测试 ID，但视觉上应伪装成简约文本动作。

- 导航项：一行文本 + 左侧高亮条。未选中为 muted 文本；hover/focus 只改变左侧 `▌` 或文本前缀，不整块铺蓝底。
- 主动作：使用 `› Start Analysis`、`› Run Backtest`、`› Buy` 这类文本动作。仅文字或前缀使用 accent，背景保持透明/面板色。
- 次要动作：使用普通 muted 文本，如 `Refresh`, `Cancel`, `Logout`；危险动作只用红色文字，不用红色实心块。
- 表单控件：输入框和 Select 保留边框，但边框细、背景接近面板色；focus 时只变边框/标题色。
- 不使用 rounded pill、厚重按钮、全宽色块按钮。全宽导航可保留点击区域，但视觉必须是文本行。
- 保留所有 `#btn_*` IDs；“按钮简约化”只改 CSS 和显示文本，不改交互契约。
- Textual `Button` 需要覆盖默认内部样式：`min-width: 0` 或最小可行宽度、`border: none`、`background: transparent`、低 padding、`content-align: left middle`。仅依赖 `compact=True` 不够，首页/侧栏/表单动作都要通过 CSS class 统一处理。

## Reference Interfaces

### 1. Home Dashboard

目标：打开 TUI 第一屏就像一个本地工作台，不再像临时菜单。左侧是主导航，右侧是 4 个状态块，提示每个模块的当前用途和入口。

```text
┌ ETFAgents ───────────────────────────────────────────────────────────────┐
│ ┌ Navigation ───────────────┐ ┌ Workspace ─────────────────────────────┐ │
│ │ ▌ Research Analysis        │ │ ETFAgents Interactive Mode             │ │
│ │   Reports Library          │ │ Multi-agent ETF research workspace     │ │
│ │   Backtest                 │ │                                        │ │
│ │   Paper Trading            │ │ ┌ Research ───────┐ ┌ Reports ──────┐ │ │
│ │                            │ │ │ Configure ETFs   │ │ Local reports │ │ │
│ │  ? Help   s Settings       │ │ │ Provider/model   │ │ Section view  │ │ │
│ │  q Quit                    │ │ └──────────────────┘ └───────────────┘ │ │
│ │                            │ │ ┌ Backtest ───────┐ ┌ Paper ────────┐ │ │
│ │                            │ │ │ NAV / metrics    │ │ Account/PnL   │ │ │
│ │                            │ │ │ Run validation   │ │ Orders        │ │ │
│ │                            │ │ └──────────────────┘ └───────────────┘ │ │
│ └────────────────────────────┘ └────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 继续保留 `#btn_research`, `#btn_reports`, `#btn_backtest`, `#btn_paper`。
- 首页右侧可以新增 `.dashboard-grid` / `.workspace-card`，但 `.workspace-card` 应优先用 styled `Static` 文本块或单层 `Vertical` 容器实现，不引入可交互复杂组件，也不要卡片套卡片。
- 左侧导航保留全宽点击区域，但视觉是文本行 + 左侧高亮条；选中/hover 不使用整块蓝色背景。

### 2. Research Input

目标：研究入口像创建 backlog task，一屏内完成 ETF 输入并进入配置，不再大面积空白。

```text
┌ Research ────────────────────────────────────────────────────────────────┐
│ ┌ Create Run ───────────────┐ ┌ Run Brief ────────────────────────────┐ │
│ │ ETF tickers               │ │ New research run                       │ │
│ │ [510300.SH,159915.SZ   ]  │ │ 1. Enter ETF tickers                   │ │
│ │                            │ │ 2. Select analysts, provider, models   │ │
│ │ › Start Analysis           │ │ 3. Track each team output in board     │ │
│ └────────────────────────────┘ └────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#ra_ticker_input`, `#btn_ra_start`, `#ra_intro`。
- 输入框聚焦态用蓝色细边框；开始分析动作显示为文本动作 `› Start Analysis`，不用蓝底块。
- `#ra_intro` 文案要短，避免说明书式长段落。

### 3. Analysis Config Modal

目标：分析配置像 compact form，不再像一串裸控件。分析师文本必须稳定显示，且在窄终端下不被挤没。

```text
                 ┌ Analysis Config ───────────────────────────────┐
                 │ Analysts                                      │
                 │ [x] 宏观分析   [x] 中观大宗   [x] 资金流       │
                 │ [x] 行业持仓   [x] ETF结构   [x] 技术面       │
                 │                                                │
                 │ Depth             Language                     │
                 │ [标准 debate×1]   [中文]                       │
                 │                                                │
                 │ Provider          Quick Model                  │
                 │ [OpenAI]          [provider default]           │
                 │ Deep Model                                     │
                 │ [provider default]                             │
                 │                                                │
                 │ › Confirm    Cancel                            │
                 └────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#acm_*` IDs。
- checkbox 保持 `compact=True` 或等价低高度，但 label 必须有足够宽度。
- 分析师 checkbox 改为明确的 3×2 网格：优先使用 Textual CSS grid（例如容器 class `.analyst-grid`，`grid-size: 3 2`），避免手工嵌套多层 Horizontal/Vertical 造成对齐和窄宽度问题。
- 弹窗宽度建议 `88` 左右，最大高度限制，必要时改为滚动容器。
- 动作横排，主动作只用 accent 文本/前缀，取消动作用 muted 文本；不要实心按钮背景。

### 4. Analysis Run Board

目标：运行页是本次重构重点。借鉴 Backlog.md board 的列式信息，将团队从纵向单列改为横向 4 列排列：分析团队、研究、风险、决策。不设嵌套层级，团队名即列头，子项直接平铺在列内。分析团队子项双列排版以节省纵向空间。研究/风险列子项下方显示辩论进度条。左侧 ETF 队列，右上团队看板，右下报告正文，底部统计条常驻。

```text
┌ Analysis Run ───────────────────────────────────────────────────────────────────┐
│ ┌ ETF Queue ───────┐ ┌ Board ──────────────────────────────────────────────────┐│
│ │ 510300.SH        │ │ ┌ 分析团队 (2/6) ──────────┬ 研究 (1/1) ┬ 风险 (0/1) ┬ 决策 (0/1) ┐│
│ │   status: running│ │ │ ✔ 市场与资金流  ✔ 宏观框架│ ▒ 研究团队   │ ○ 交易员   │ ○ PM      ││
│ │   depth: 标准    │ │ │ ▒ 舆情与事件    ○ 中观大宗│ ▓▓░ 2/3     │ ░░░ 0/1   │           ││
│ │   provider:openai│ │ │ ○ 持仓行业      ○ 头部持仓│             │           │           ││
│ │                  │ │ └──────────────────────────┴─────────────┴───────────┴──────────┘│
│ │ Cancel           │ │ ┌ Report ───────────────────────────────────────────────┐ │
│ │                  │ │ │ ## 舆情与事件分析                                       │ │
│ │ Queue            │ │ │ ...streamed or completed report...                      │ │
│ │ > 510300.SH      │ │ └───────────────────────────────────────────────────────┘ │
│ │   159915.SZ      │ └──────────────────────────────────────────────────────────┘│
│ └──────────────────┘                                                              │
│ Agents 2/9 | Agent 舆情与事件 | LLM 12 | Tools 8 | Tokens 18.4k↑ 3.2k↓ | 03:21  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

列头团队与代码中 team 字段的映射：

| 列头显示 | UI section id | 底层来源 |
|----------|---------------|----------|
| 分析团队 | existing analyst section ids | `team == "分析师"`: market_flow, catalyst_sentiment, macro_regime, meso_commodity, holdings_industry, top_holdings |
| 研究 | research | existing `section_id == "research"` + `investment_debate_state` |
| 风险 | risk_debate | synthetic UI-only section, driven by `risk_debate_state` |
| 决策 | trader, portfolio_manager | UI-only grouping of existing `team == "交易"` and `team == "决策"` |

Implementation notes:

- 保留 `#ra_queue`, `#ra_sections`, `#ra_body_title`, `#ra_body`, `#ra_stats_bar`, `#btn_ra_cancel`, `#ra_run_config`。
- 右上团队区域改为 4 列横向排列：`分析团队（宽）| 研究 | 风险 | 决策（窄）`
  - 不分层，团队名即列头，子项直接平铺在列内
  - 分析团队列内 6 个子项双列排版（3 行 × 2 列），宽框省纵向空间
  - 研究/风险/决策列各仅 1 个子项，列窄
- 列头只显示完成计数：如 `分析团队 (2/6)`、`研究 (1/1)`；运行/完成/失败状态由列内子项图标表达。
- 研究/风险列子项下方显示辩论进度条 `▓▓░ current/max`
  - 研究团队：当前轮次 = `investment_debate_state["count"] // 2`，总轮次 = `max_debate_rounds`
  - 风险阶段：当前轮次 = `(risk_debate_state["count"] + 2) // 3`，总轮次 = `max_risk_discuss_rounds`
  - 风险列不是 `trader` section；当前代码中 `risk_debate_state` 是 `portfolio_manager` 的 detection key，因此实现应把风险列作为合成 UI 阶段，由 `risk_debate_state` 驱动
  - 新增 `DebateProgress` 事件，将辩论 count 变化传递给 UI；不要通过改造 `SectionDone` 重载含义
  - `AnalysisRunner._watch_graph()` 在读取 stream chunk 时检测 `investment_debate_state["count"]` 和 `risk_debate_state["count"]` 是否变化；变化时 emit `DebateProgress`，并继续按现有逻辑 emit `SectionDone`（两者并行，不互相替代）
  - `DebateProgress.section_id` 对研究用 `"research"`，对风险用 synthetic `"risk_debate"`
- 风险列状态规则：
  - `risk_debate_state["count"] > 0` 且未达到 `3 * max_risk_discuss_rounds` 时显示 `▒`
  - 达到 `3 * max_risk_discuss_rounds` 后显示 `✔`
  - 风险列不接收 `SectionDone` 内容事件；它只消费 `DebateProgress` 和可选的最终 state snapshot
- 决策列状态规则：
  - `trader` 子项按现有 `SectionDone(section_id="trader")` 完成后显示 `✔`
  - `portfolio_manager` 子项按现有 `SectionDone(section_id="portfolio_manager")` 或 `TickerDone` 后显示 `✔`
  - 决策列把 `trader` 与 `portfolio_manager` 合并展示只是 UI 分组，不改变底层 `SectionDef.team` 值
- 活跃列（当前正在产出报告的团队列）`.column-active` 蓝色边框，其余 `.column-inactive` 灰色边框
- `ListItem` label 使用稳定状态前缀：`✔`, `▒`, `○`, `✘`。列头不再把运行图标塞进计数，使用 `研究 (1/1)` + 子项图标表达状态，避免 `研究 (▒1/1)` 的语义混乱。
- 右下报告正文区高度填满剩余空间
- `#ra_stats_bar` 采用固定单行 status strip：优先移除边框或改用无边框高亮顶线；如果保留 `border: solid`，高度必须提高到 `5`。不要维持 `height: 3 + border` 的组合，因为边框会挤占内容行。
- 当前选中的子项用蓝色高亮，已完成项绿色文字，失败项红色文字

### 5. Report Library

目标：报告库像 backlog task browser，左侧报告列表，右侧章节列表和正文，强调可扫读。

```text
┌ Reports ─────────────────────────────────────────────────────────────────┐
│ ┌ Report List ─────────────┐ ┌ Sections ──────────────────────────────┐ │
│ │ > 510300.SH 2026-05-22   │ │ 宏观分析 / 中观大宗 / 行业持仓 ...     │ │
│ │   BUY                    │ │                                       │ │
│ │   159915.SZ 2026-05-22   │ │ ┌ Body ────────────────────────────┐ │ │
│ │   HOLD                   │ │ │ markdown report section            │ │ │
│ │                          │ │ │                                    │ │ │
│ │ r Refresh                │ │ └────────────────────────────────────┘ │ │
│ └──────────────────────────┘ └──────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#reports`, `#lib_sections`, `#lib_body`。
- 报告列表项最多两行信息，避免长文本撑开布局。
- 空状态要像 placeholder panel，不要只显示孤零零一行文字。

### 6. Backtest Console

目标：回测页不能只是表单 + 表格堆叠，应改成“运行控制台 + 结果看板”。左侧负责选择/发起回测，右侧上方展示关键指标和 NAV sparkline，右侧下方展示摘要、订单和交易结果。

```text
┌ Backtest ───────────────────────────────────────────────────────────────────────┐
│ ┌ Runs / New Test ─────────┐ ┌ Performance Board ─────────────────────────────┐ │
│ │ Recent runs              │ │ ┌ NAV ───────────────────────────────────────┐ │ │
│ │ > 510300.SH +4.8%        │ │ │ ▁▂▃▅▆▇█▇▆▅▇█                              │ │ │
│ │   159915.SZ -1.2%        │ │ └───────────────────────────────────────────┘ │ │
│ │                          │ │ ┌ Metrics ─────┬ Risk ───────┬ Trades ─────┐ │ │
│ │ New backtest             │ │ │ Return +4.8%  │ DD -2.1%    │ 18 orders   │ │ │
│ │ [tickers              ]  │ │ │ Sharpe 1.42   │ Vol 12.0%   │ 12 filled   │ │ │
│ │ [start] [end]            │ │ └───────────────┴─────────────┴─────────────┘ │ │
│ │ › Run   Refresh          │ │ ┌ Summary / Orders / Trades ───────────────┐ │ │
│ │ status: idle             │ │ │ markdown summary or selected table        │ │ │
│ └──────────────────────────┘ └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#bt_list`, `#btn_bt_refresh`, `#bt_run_tickers`, `#bt_run_start`, `#bt_run_end`, `#btn_bt_run`, `#bt_run_status`, `#bt_sparkline`, `#bt_metrics`, `#bt_summary`。
- 右上区域拆成 NAV sparkline + metrics summary，不改变 `BacktestViewer` 或 `BacktestRunner` 的数据契约。
- `#bt_metrics` 继续用 `DataTable`，但外层用一致的 panel/card 样式，指标按收益/风险/交易三组排序。
- 空状态显示“暂无回测结果”和一个可直接填写的新回测表单。
- 回测运行中禁用 Run 动作，状态文字用 yellow；成功用 green；失败用 red。禁用态降低文字亮度，不显示灰色块。
- 可选新增 tabs/segmented control 样式文本，用于在 Summary / Orders / Trades 之间切换；如果不实现切换，先保持 Summary 主视图和 metrics table，避免扩大范围。

### 7. Paper Trading Console

目标：模拟交易页改成交易工作台：左侧账户与操作，右侧上方资产/PnL 概览，右侧下方持仓和成交记录。买入/卖出仍用弹窗，不改交易行为。

```text
┌ Paper Trading ──────────────────────────────────────────────────────────────────┐
│ ┌ Account / Actions ──────┐ ┌ Portfolio Board ────────────────────────────────┐ │
│ │ user: default           │ │ ┌ Account Snapshot ───────────────────────────┐ │ │
│ │ status: connected       │ │ │ Total 150,000 | Cash 100,000 | MV 50,000    │ │ │
│ │                         │ │ │ Unrealized +1,234.56 | Realized -200.00    │ │ │
│ │ Login   Logout          │ │ └────────────────────────────────────────────┘ │ │
│ │ › Buy   Sell            │ │ ┌ Positions ─────────────────────────────────┐ │ │
│ │ Refresh                 │ │ │ 510300.SH  沪深300ETF   +6.67%  +300.00    │ │ │
│ │                         │ │ │ 159915.SZ  创业板ETF    -9.52%  -100.00    │ │ │
│ │ order status: idle      │ │ └────────────────────────────────────────────┘ │ │
│ │                         │ │ ┌ Trades ────────────────────────────────────┐ │ │
│ │                         │ │ │ 2026-05-20 BUY 510300.SH 1000 @ 4.500      │ │ │
│ └─────────────────────────┘ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#pt_user_status`, `#btn_pt_login`, `#btn_pt_logout`, `#btn_pt_buy`, `#btn_pt_sell`, `#btn_pt_refresh`, `#pt_account`, `#pt_positions`, `#pt_trades`。
- 账户概览用紧凑 status strip，数字对齐，正收益 green，负收益 red。
- 持仓和交易历史继续使用 `DataTable`，但表格上方加明确面板标题和空状态。
- 登录/下单弹窗沿用全局 modal 样式；不改变登录、买入、卖出、刷新逻辑。
- 未配置模拟交易引擎时显示可见 warning panel，不只在右侧孤立显示一句话。

### 8. Settings

目标：保留现有设置页的主题、密度、面板宽度能力，但避免新 slate 视觉方向和 Textual theme selector 互相误导。

Implementation notes:

- 保留 `#sel_theme`, `#sel_density`, `#sel_panel_width`, `#btn_settings_save`, `#btn_settings_reset`, `#settings_status`。
- slate/kanban 外观应实现为应用 CSS 的默认视觉层，不硬编码到业务屏幕；`theme` selector 继续控制 Textual 基础 theme，但文案应说明它是“终端基础主题”，不是完整品牌皮肤。
- 如果 slate palette 覆盖了大多数颜色，设置页需要同步文案，避免用户选择其他 Textual theme 后期待完整换肤。
- 密度和面板宽度 presets 继续生效，不能被新布局绕过。

## Implementation Changes

- `cli/tui/app.py`
  - 重写全局 CSS，新增统一的 panel/card/list/status/text-action/form 样式。
  - 调整 `.left-pane`, `.right-pane`, `.right-top`, `.right-bottom`, `.nav-pane`, `.dashboard-pane`, `#ra_stats_bar` 的视觉层级。
  - 新增语义 class：`.workspace-card`, `.status-strip`, `.section-card`, `.text-action`, `.nav-action`, `.muted`, `.success-text`, `.warning-text`, `.error-text`。
  - 新增看板 class：`.column-active`, `.column-inactive`（活跃列蓝色边框、非活跃灰色边框）。
- `cli/tui/screens/home.py`
  - 改造首页右侧为任务板式 dashboard。
  - 保持导航 Button IDs 和导航行为不变，但视觉改为文本导航 + 左侧高亮条。
- `cli/tui/screens/research.py`
  - 优化研究输入页提示和布局。
  - 调整 `AnalysisConfigModal` 的分组、宽度、间距。
  - 运行页团队区域从纵向单列改为横向 4 列看板（分析团队/研究/风险/决策），不设嵌套层级，子项直接平铺。
  - 分析团队列内 6 个子项双列排版（3 行 × 2 列），宽框省纵向空间。
  - 研究/风险列子项下方显示辩论进度条 `▓▓░ current/max`。
  - 新增 `DebateProgress` 事件，将 `investment_debate_state["count"]` / `risk_debate_state["count"]` 变化传递给 UI；事件由 `AnalysisRunner._watch_graph()` 在 count 变化时发出。
  - 保持现有 `SectionDone` 内容更新语义，不把 section 内容事件和进度事件混用。
- `cli/tui/screens/reports.py`
  - 报告库按 backlog browser 风格重排列表、章节和正文空状态。
  - 不改报告发现和读取逻辑。
- `cli/tui/screens/backtest.py`
  - 改成“Runs / New Test + Performance Board”布局。
  - 强化 NAV sparkline、metrics summary、运行状态和空状态。
  - 保留现有回测输入、刷新、运行、详情加载逻辑。
- `cli/tui/screens/paper.py`
  - 改成“Account / Actions + Portfolio Board”布局。
  - 强化账户概览、持仓、交易历史和未配置引擎状态。
  - 保留登录、下单、刷新行为和弹窗 IDs。
- `cli/tui/screens/settings_screen.py`
  - 保留现有设置项和 IDs。
  - 更新文案说明主题 selector 是 Textual 基础主题；密度/面板宽度继续作用于新布局。
- 所有屏幕
  - `Button` 组件统一加 `text-action` / `nav-action` 等 class，CSS 去掉厚重背景、粗边框和大色块。
  - 只在焦点、hover、选中态使用短高亮条或前缀色，不使用整块蓝底。

## Interfaces

- 不新增公开 API。
- 保留现有 widget IDs，尤其是：
  - `#btn_research`, `#btn_reports`, `#btn_backtest`, `#btn_paper`
  - `#acm_*`
  - `#ra_queue`, `#ra_sections`, `#ra_body_title`, `#ra_body`, `#ra_stats_bar`, `#btn_ra_cancel`, `#ra_run_config`
  - `#reports`, `#lib_sections`, `#lib_body`
  - `#bt_list`, `#btn_bt_refresh`, `#bt_run_tickers`, `#bt_run_start`, `#bt_run_end`, `#btn_bt_run`, `#bt_run_status`, `#bt_sparkline`, `#bt_metrics`, `#bt_summary`
  - `#pt_user_status`, `#btn_pt_login`, `#btn_pt_logout`, `#btn_pt_buy`, `#btn_pt_sell`, `#btn_pt_refresh`, `#pt_account`, `#pt_positions`, `#pt_trades`
- 允许新增 CSS class 和少量 `Static` 文本块，但不破坏现有测试可查询对象。
- 新增 `DebateProgress` 事件类型，携带 `ticker`, `section_id`, `current_round`, `max_rounds` 字段，用于驱动研究/风险列的辩论进度条。
- `DebateProgress` 由 `AnalysisRunner._watch_graph()` 发出：当 `investment_debate_state["count"]` 或 `risk_debate_state["count"]` 相对上次 chunk 变化时 emit。
- 风险列使用 synthetic `section_id == "risk_debate"`，数据来自 `risk_debate_state`，不要把它绑定到 `trader` section。
- 现有 `_format_research()` / `_format_risk()` 继续负责 Markdown 内容渲染；看板进度从 raw debate state 的 `count` 读取，不从格式化后的 Markdown 反解析。

## Acceptance Criteria

- 首页第一屏有明确工作台质感：左侧导航清晰，右侧模块状态块紧凑可读。
- 分析配置弹窗中，所有分析师 label 在 `140x40` 和常见窄宽度下可见。
- 分析运行页的底部统计栏始终显示非空内容，不被 padding/border 挤掉。
- 底部统计栏使用无边框单行 strip，或在保留边框时高度至少为 `5`；不得保留会裁剪内容的 `height: 3 + border` 组合。
- 运行页团队看板区 4 列横向排列（分析团队/研究/风险/决策），不设嵌套层级，子项直接平铺。
- 分析团队列内 6 个子项双列排版（3 行 × 2 列），不过度占用纵向空间。
- 研究/风险列子项下方显示辩论进度条 `▓▓░ current/max`，数据来自 debate_state 的 count 字段。
- 活跃团队列蓝色边框，非活跃列灰色边框。
- 报告库、回测、模拟交易页面与首页/研究页使用一致配色和组件风格。
- 回测页呈现 Runs / New Test + Performance Board，NAV、核心指标、状态和空状态清晰可见。
- 模拟交易页呈现 Account / Actions + Portfolio Board，账户快照、持仓和交易历史清晰可见。
- 所有按钮视觉简约：文本动作 + 高亮条/前缀/焦点反色，无大面积实心色块。
- 不改变研究分析、报告读取、回测运行、模拟交易的业务行为。

## Test Plan

- 跑完整 TUI UI 测试：
  - `uv run python -m unittest tests.test_tui_ui -q`
- 跑编译检查：
  - `uv run python -m py_compile cli/tui/app.py cli/tui/screens/home.py cli/tui/screens/research.py cli/tui/screens/reports.py cli/tui/screens/backtest.py cli/tui/screens/paper.py tests/test_tui_ui.py`
- 增加/调整视觉回归类测试：
  - 首页仍显示 4 个主按钮并可导航。
  - 首页 4 个导航 Button 仍保留原 IDs，但渲染为文本导航样式，不出现厚重实心按钮。
  - 分析配置弹窗仍显示分析师文字。
  - 运行页底部统计栏文本非空且 widget 可见。
  - 运行页团队看板区 4 列正确渲染（分析团队/研究/风险/决策）。
  - 分析团队列双列排版显示 6 个子项，不过度占用纵向空间。
  - 研究/风险列辩论进度条在 debate_state 更新时正确刷新。
  - `_watch_graph()` 在 debate count 变化时 emit `DebateProgress`，且不影响现有 `SectionDone` emit。
  - 风险列使用 synthetic `risk_debate` 进度，`portfolio_manager` 最终输出仍按原 section 完成。
  - 回测页保留运行表单、结果列表、sparkline、metrics 和 summary。
  - 模拟交易页保留账户、登录/登出、买卖、刷新、持仓、交易历史。
  - 关键页面在 `140x40` 尺寸下无关键控件缺失。

## Assumptions

- 采用"全局外观 + 终端任务板"方案。
- 这次是 TUI 视觉与布局重构，不改分析流程、不改报告验收逻辑、不新增 Web UI。
- 参考 Backlog.md 的风格原则，不复制其 React/Tailwind 组件实现。
- 按钮策略参考 Backlog.md 的终端 board：文本优先，靠高亮条/前缀表达状态，而不是靠大块按钮。
- `max_risk_discuss_rounds` 是当前代码中的实际配置键，计划沿用该名称。
- 运行页团队看板采用横向 4 列布局（分析团队/研究/风险/决策），不按状态分 3 列（已完成/进行中/待开始），以更直观反映团队协作流程。
- 分析团队列子项双列排版，研究/风险列子项下方显示辩论进度条 `▓▓░ current/max`。
- 团队列映射到代码字段：分析团队→`team == "分析师"`；研究→`section_id == "research"`；风险→synthetic `risk_debate`，来自 `risk_debate_state`；决策→UI-only grouping of `trader` + `portfolio_manager`，不改变底层 team assignments。
