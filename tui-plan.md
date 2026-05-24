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
- 首页右侧可以新增 `.dashboard-grid` / `.workspace-card`，但不要引入卡片套卡片。
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
- 弹窗宽度建议 `88` 左右，最大高度限制，必要时改为滚动容器。
- 动作横排，主动作只用 accent 文本/前缀，取消动作用 muted 文本；不要实心按钮背景。

### 4. Analysis Run Board

目标：运行页是本次重构重点。借鉴 Backlog.md board 的列式信息，将团队从纵向单列改为横向 4 列排列：分析团队、研究、风险、决策。不设嵌套层级，团队名即列头，子项直接平铺在列内。分析团队子项双列排版以节省纵向空间。研究/风险列子项下方显示辩论进度条。左侧 ETF 队列，右上团队看板，右下报告正文，底部统计条常驻。

```text
┌ Analysis Run ───────────────────────────────────────────────────────────────────┐
│ ┌ ETF Queue ───────┐ ┌ Board ──────────────────────────────────────────────────┐│
│ │ 510300.SH        │ │ ┌ 分析团队 (2/6) ──────────┬ 研究 (▒1/1) ┬ 风险 (0/1) ┬ 决策 (0/1) ┐│
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

| 列头显示 | 代码 team | 子项来源 |
|----------|-----------|----------|
| 分析团队 | 分析师 | market_flow, catalyst_sentiment, macro_regime, meso_commodity, holdings_industry, top_holdings |
| 研究 | 研究 | research |
| 风险 | 合成 UI 阶段 | risk_debate_state |
| 决策 | 交易/决策 | trader, portfolio_manager |

Implementation notes:

- 保留 `#ra_queue`, `#ra_sections`, `#ra_body_title`, `#ra_body`, `#ra_stats_bar`, `#btn_ra_cancel`, `#ra_run_config`。
- 右上团队区域改为 4 列横向排列：`分析团队（宽）| 研究 | 风险 | 决策（窄）`
  - 不分层，团队名即列头，子项直接平铺在列内
  - 分析团队列内 6 个子项双列排版（3 行 × 2 列），宽框省纵向空间
  - 研究/风险/决策列各仅 1 个子项，列窄
- 列头含状态图标 + 完成计数：如 `分析团队 (2/6)`、`研究 (▒1/1)`
- 研究/风险列子项下方显示辩论进度条 `▓▓░ current/max`
  - 研究团队：当前轮次 = `investment_debate_state["count"] // 2`，总轮次 = `max_debate_rounds`
  - 风险阶段：当前轮次 = `(risk_debate_state["count"] + 2) // 3`，总轮次 = `max_risk_discuss_rounds`
  - 风险列不是 `trader` section；当前代码中 `risk_debate_state` 是 `portfolio_manager` 的 detection key，因此实现应把风险列作为合成 UI 阶段，由 `risk_debate_state` 驱动
  - 新增 `DebateProgress` 事件，将辩论 count 变化传递给 UI；不要通过改造 `SectionDone` 重载含义
- 活跃列（当前正在产出报告的团队列）`.column-active` 蓝色边框，其余 `.column-inactive` 灰色边框
- `ListItem` label 使用稳定状态前缀：`✔`, `▒`, `○`, `✘`
- 右下报告正文区高度填满剩余空间
- `#ra_stats_bar` 高度固定为 3，padding 不导致文字消失
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
  - 新增 `DebateProgress` 事件，将 `investment_debate_state["count"]` / `risk_debate_state["count"]` 变化传递给 UI。
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
- 风险列作为合成 UI 阶段，数据来自 `risk_debate_state`，不要把它绑定到 `trader` section。

## Acceptance Criteria

- 首页第一屏有明确工作台质感：左侧导航清晰，右侧模块状态块紧凑可读。
- 分析配置弹窗中，所有分析师 label 在 `140x40` 和常见窄宽度下可见。
- 分析运行页的底部统计栏始终显示非空内容，不被 padding/border 挤掉。
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
  - 回测页保留运行表单、结果列表、sparkline、metrics 和 summary。
  - 模拟交易页保留账户、登录/登出、买卖、刷新、持仓、交易历史。
  - 关键页面在 `140x40` 尺寸下无关键控件缺失。

## Assumptions

- 采用"全局外观 + 终端任务板"方案。
- 这次是 TUI 视觉与布局重构，不改分析流程、不改报告验收逻辑、不新增 Web UI。
- 参考 Backlog.md 的风格原则，不复制其 React/Tailwind 组件实现。
- 按钮策略参考 Backlog.md 的终端 board：文本优先，靠高亮条/前缀表达状态，而不是靠大块按钮。
- 运行页团队看板采用横向 4 列布局（分析团队/研究/风险/决策），不按状态分 3 列（已完成/进行中/待开始），以更直观反映团队协作流程。
- 分析团队列子项双列排版，研究/风险列子项下方显示辩论进度条 `▓▓░ current/max`。
- 团队列映射到代码字段：分析团队→`team == "分析师"`；研究→`section_id == "research"`；风险→合成 UI 阶段，来自 `risk_debate_state`；决策→`trader` + `portfolio_manager`。
