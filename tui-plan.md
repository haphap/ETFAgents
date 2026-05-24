# TUI 全局外观重构计划

## Summary

按 Backlog.md 的“终端任务板”方向重构 ETFAgents TUI：深色 slate 基底、蓝色主强调、绿色/黄色/红色状态色、清晰面板边界、紧凑高信息密度。目标不是做营销页，而是把现有 Textual 工具改成更像本地工作台的操作界面。

参考来源：

- Backlog.md README: https://github.com/MrLesk/Backlog.md
- 终端 board GIF: https://github.com/MrLesk/Backlog.md/blob/main/.github/backlog-v1.40.gif
- Web UI 截图: https://github.com/MrLesk/Backlog.md/blob/main/.github/web.jpeg
- Backlog.md Web 样式基调：slate 深色背景、blue 主强调、green/yellow 语义状态、紧凑任务卡片。

## Visual Direction

- 视觉关键词：terminal kanban、dark slate、compact dashboard、status chips、task cards。
- 基底颜色：`#0f172a` / `#111827` 类深色背景，面板使用 `#1e293b`，次级面板使用 `#334155`。
- 主强调色：蓝色 `#3b82f6` 或 Textual 对应 accent，用于当前选中、主按钮、滚动条和焦点边框。
- 状态色：
  - 成功/完成：green。
  - 运行/等待：yellow 或 cyan。
  - 风险/失败：red。
  - 弱信息：slate gray。
- 组件风格：
  - 列表项像 backlog task card：单行可扫读，选中态明显。
  - 面板像 kanban column：标题固定、内容紧凑、边界清晰。
  - 底部统计栏像 status strip：一行展示 Agents、LLM、Tools、Tokens、Reports、Elapsed。

## Reference Interfaces

### 1. Home Dashboard

目标：打开 TUI 第一屏就像一个本地工作台，不再像临时菜单。左侧是主导航，右侧是 4 个状态块，提示每个模块的当前用途和入口。

```text
┌ ETFAgents ───────────────────────────────────────────────────────────────┐
│ ┌ Navigation ───────────────┐ ┌ Workspace ─────────────────────────────┐ │
│ │  > Research Analysis       │ │ ETFAgents Interactive Mode             │ │
│ │    Reports Library         │ │ Multi-agent ETF research workspace     │ │
│ │    Backtest                │ │                                        │ │
│ │    Paper Trading           │ │ ┌ Research ───────┐ ┌ Reports ──────┐ │ │
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
- 左侧导航按钮保持全宽，选中/hover 用蓝色背景。

### 2. Research Input

目标：研究入口像创建 backlog task，一屏内完成 ETF 输入并进入配置，不再大面积空白。

```text
┌ Research ────────────────────────────────────────────────────────────────┐
│ ┌ Create Run ───────────────┐ ┌ Run Brief ────────────────────────────┐ │
│ │ ETF tickers               │ │ New research run                       │ │
│ │ [510300.SH,159915.SZ   ]  │ │ 1. Enter ETF tickers                   │ │
│ │                            │ │ 2. Select analysts, provider, models   │ │
│ │ [ Start Analysis ]         │ │ 3. Track each team output in board     │ │
│ └────────────────────────────┘ └────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#ra_ticker_input`, `#btn_ra_start`, `#ra_intro`。
- 输入框聚焦态用蓝色边框，主按钮用蓝底。
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
                 │ [ Confirm ] [ Cancel ]                         │
                 └────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#acm_*` IDs。
- checkbox 保持 `compact=True` 或等价低高度，但 label 必须有足够宽度。
- 弹窗宽度建议 `88` 左右，最大高度限制，必要时改为滚动容器。
- 按钮横排，主按钮蓝色，取消按钮 slate。

### 4. Analysis Run Board

目标：运行页是本次重构重点。借鉴 Backlog.md board 的列式信息：左侧 ETF 队列，中间团队阶段，右侧报告正文，底部统计条常驻。

```text
┌ Analysis Run ────────────────────────────────────────────────────────────┐
│ ┌ ETF Queue ────────────────┐ ┌ Team Board ───────────────────────────┐ │
│ │ 510300.SH                 │ │ ┌ Teams ────────────────────────────┐ │ │
│ │   status: running          │ │ │ ✓ 宏观分析                         │ │ │
│ │   depth: 标准              │ │ │ ▶ 中观大宗                         │ │ │
│ │   provider: openai         │ │ │ · 行业持仓                         │ │ │
│ │                            │ │ │ · ETF结构                          │ │ │
│ │ [ Cancel ]                 │ │ └───────────────────────────────────┘ │ │
│ │                            │ │ ┌ Report / Progress ───────────────┐ │ │
│ │ Queue                      │ │ │ ## 中观大宗分析                    │ │ │
│ │ > 510300.SH                │ │ │ ...streamed or completed report... │ │ │
│ │   159915.SZ                │ │ │                                   │ │ │
│ └────────────────────────────┘ └────────────────────────────────────────┘ │
│ Agents 2/9 | Agent 中观大宗 | LLM 12 | Tools 8 | Tokens 18.4k/3.2k | 03:21 │
└───────────────────────────────────────────────────────────────────────────┘
```

Implementation notes:

- 保留 `#ra_queue`, `#ra_sections`, `#ra_body_title`, `#ra_body`, `#ra_stats_bar`。
- `ListItem` label 使用稳定状态前缀：`✓`, `▶`, `·`, `✗`。
- 右上团队列表高度保持 30%-35%，右下正文填满剩余空间。
- `#ra_stats_bar` 高度固定为 3，padding 不导致文字消失。
- 当前选中的团队/ETF 用蓝色高亮，已完成项可用绿色文字，失败项红色文字。

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

## Implementation Changes

- `cli/tui/app.py`
  - 重写全局 CSS，新增统一的 panel/card/list/status/button/form 样式。
  - 调整 `.left-pane`, `.right-pane`, `.right-top`, `.right-bottom`, `.nav-pane`, `.dashboard-pane`, `#ra_stats_bar` 的视觉层级。
  - 新增语义 class：`.workspace-card`, `.status-strip`, `.section-card`, `.muted`, `.success-text`, `.warning-text`, `.error-text`。
- `cli/tui/screens/home.py`
  - 改造首页右侧为任务板式 dashboard。
  - 保持导航按钮 IDs 和导航行为不变。
- `cli/tui/screens/research.py`
  - 优化研究输入页提示和布局。
  - 调整 `AnalysisConfigModal` 的分组、宽度、间距。
  - 优化运行页队列/团队/正文/统计栏显示，不改变分析线程和事件处理逻辑。
- `cli/tui/screens/reports.py`, `cli/tui/screens/backtest.py`, `cli/tui/screens/paper.py`
  - 只做样式 class 和少量文案一致化。
  - 不改数据加载、表格列、登录/下单/回测行为。

## Interfaces

- 不新增公开 API。
- 保留现有 widget IDs，尤其是：
  - `#btn_research`, `#btn_reports`, `#btn_backtest`, `#btn_paper`
  - `#acm_*`
  - `#ra_queue`, `#ra_sections`, `#ra_body`, `#ra_stats_bar`
  - `#reports`, `#lib_sections`, `#lib_body`
- 允许新增 CSS class 和少量 `Static` 文本块，但不破坏现有测试可查询对象。

## Acceptance Criteria

- 首页第一屏有明确工作台质感：左侧导航清晰，右侧模块状态块紧凑可读。
- 分析配置弹窗中，所有分析师 label 在 `140x40` 和常见窄宽度下可见。
- 分析运行页的底部统计栏始终显示非空内容，不被 padding/border 挤掉。
- 运行页中 ETF 队列、团队列表、正文区域视觉层级明确，当前选择项清楚。
- 报告库、回测、模拟交易页面与首页/研究页使用一致配色和组件风格。
- 不改变研究分析、报告读取、回测运行、模拟交易的业务行为。

## Test Plan

- 跑完整 TUI UI 测试：
  - `uv run python -m unittest tests.test_tui_ui -q`
- 跑编译检查：
  - `uv run python -m py_compile cli/tui/app.py cli/tui/screens/home.py cli/tui/screens/research.py cli/tui/screens/reports.py cli/tui/screens/backtest.py cli/tui/screens/paper.py tests/test_tui_ui.py`
- 增加/调整视觉回归类测试：
  - 首页仍显示 4 个主按钮并可导航。
  - 分析配置弹窗仍显示分析师文字。
  - 运行页底部统计栏文本非空且 widget 可见。
  - 关键页面在 `140x40` 尺寸下无关键控件缺失。

## Assumptions

- 采用“全局外观 + 终端任务板”方案。
- 这次是 TUI 视觉与布局重构，不改分析流程、不改报告验收逻辑、不新增 Web UI。
- 参考 Backlog.md 的风格原则，不复制其 React/Tailwind 组件实现。
