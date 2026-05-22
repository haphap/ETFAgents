# ETFAgents Textual TUI 重构计划

## 目标

新增独立入口 `etfagents tui`，基于 Textual 提供主菜单式终端界面。现有 `etfagents analyze`、`etfagents backtest`、`etfagents paper` 命令保持兼容，不替换、不迁移原有交互流程。

v1 采用分阶段落地：先完成主菜单、研究分析队列、研究报告库、回测结果读取、模拟交易查看；后续再增强回测交互、买卖弹窗、更多 Textual pilot 覆盖。

## 执行校准

本计划以根目录 `plan.md` 的当前执行版为准。旧方案中关于 `etfagents/tui/`、独立 `etfagents-tui` 入口、默认安装 `textual/plotext`、多 ETF 并发分析和独立 widget 包的设想暂不作为 v1 要求。

v1 当前工程安排：

- 使用 `etfagents tui`，不新增 `etfagents-tui` console script。
- 使用 `cli/tui/` 和 `cli/commands/tui.py`，暂不迁到 `etfagents/tui/`。
- `textual` 作为 `[project.optional-dependencies] tui`，基础安装不拉取 Textual。
- 不引入 `plotext`；回测图表 v1 使用字符 Sparkline。
- 多 ETF 分析使用顺序队列；并发推迟到 v1.5/v2，在限流、日志、memory、checkpoint 隔离方案明确后再做。
- 现有 `etfagents analyze/backtest/paper` 行为保持不变。

## 关键假设

- 接受新增 `textual` 依赖。**应作为 `[project.optional-dependencies] tui` extra**，而不是默认依赖；非 TUI 用户安装基础包时不应被迫拉入 Textual 及其传递依赖。`etfagents tui` 启动时若 `textual` 未安装，应给出明确的安装提示（`pip install 'etfagents[tui]'`）并保留其他 CLI 命令的可用性。
- TUI 作为新增入口存在，现有 CLI 命令行为不改变。
- 多 ETF 分析先采用顺序队列，不引入并发。
- 报告库 v1 只展示单 ETF 报告目录，不纳入 `_candidate_pools` 汇总报告。
- 回测图表 v1 使用终端字符图和 Sparkline，不新增绘图库。
- TUI 服务层必须可单元测试，避免测试依赖真实 LLM、Tushare 或 Textual 事件循环。**`tests/test_tui_services.py` 顶部应加 `assert "textual" not in sys.modules` 守卫**，强制服务层与 UI 解耦。

## 当前已完成工作

### 命令入口与依赖

- `pyproject.toml` 新增 `[project.optional-dependencies] tui = ["textual>=0.89.0"]`。
- `uv.lock` 已更新 Textual extra 及其依赖，Textual 不再是基础依赖。
- `cli/commands/tui.py` 新增 `tui()` 命令入口。
- `cli/main.py` 注册 `etfagents tui`。
- Textual import 延迟到命令执行时，避免影响其他 CLI 命令启动。

### TUI 应用层

新增 `cli/tui/app.py`，包含以下 screen：

- `HomeScreen`：主菜单，入口包括研究分析、研究报告库、回测、模拟交易。
- `ResearchAnalysisScreen`：输入多个 ETF 代码和分析日期，按顺序执行分析队列。
- `ReportLibraryScreen`：浏览本地单 ETF 报告，按 ticker/date/section 查看 Markdown。
- `BacktestScreen`：从已有报告 ETF 中选择标的，输入回测参数并展示摘要、Sparkline 和基础表格。
- `PaperTradingScreen`：展示模拟账户净值、现金、持仓市值、盈亏和持仓表。

实现注意点：

- ETF ticker 不直接作为 Textual widget id；统一转换为安全 id 并维护映射。
- 研究分析和回测通过 Textual thread worker 运行，避免阻塞 UI。
- UI 当前是可用的 v1 骨架，已有 pilot 覆盖主菜单、报告库、研究分析、回测输入校验和模拟交易账户/持仓展示；后续继续补充交互细节。

### 服务层

新增 `cli/tui/services.py`，将非 UI 逻辑从 Textual screen 中抽离：

- `ReportRepository`
  - 扫描 `results_dir/{ticker}/{date}`。
  - 跳过 `_candidate_pools` 和 `backtest`。
  - 识别 `complete_report.md`、分 section markdown、ticker、date、rating。
  - 支持读取指定 section 内容。
  - 暴露 `invalidate()` 方法显式让 cache/扫描结果失效；由 `AnalysisRunner` 完成后或用户在 `ReportLibraryScreen` 按 `r` 时调用。
  - 提供反向映射工具（如 `IdRegistry`）：`register(ticker) -> safe_id`、`resolve(safe_id) -> ticker`、`__contains__`，让 ticker 与 widget id 的映射只在服务层做一次，避免 `app.py` 重复实现字符串转换。
- `AnalysisRunner`
  - 封装 `EtfAgentsGraph.prepare_run/stream/finalize_run`。
  - 对多 ETF 顺序执行。
  - 维护显式状态机 `dict[str, TickerState]`，状态枚举：`pending / running / section_running / section_done / done / failed / cancelled`。UI 层直接渲染该 map，避免靠"最后一个事件"反推 ticker 进度。
  - 产出 UI 友好的 `AnalysisEvent`：ticker 开始、section 更新、agent 更新、完成、失败、取消、报告已落盘。
  - 分析中实时写入 `reports/{section}.md` 时使用原子写（tempfile + `os.replace`），中途取消不会留下半截文件污染 `ReportRepository`。
  - 支持 `request_cancel()` 接口（基于 `threading.Event`）；stream loop 在每个事件之间检查 cancel flag，发出 `cancelled` 事件后退出当前 ticker 而不杀进程。
  - 完成（或失败/取消）一个 ticker 后 emit `report_persisted` 事件，由 app 层调用 `ReportRepository.invalidate()`，让报告库 screen 立即看到新结果。
  - 完成后复用现有 `save_report_to_disk()` 保存完整报告；在未安装完整 CLI 依赖的测试环境中提供最小 fallback。
- `BacktestRunner`
  - 封装 `backtest_candidate_pool()` 和 `save_backtest_result()`。
  - 支持读取 `summary.md`、`metrics.json`、`nav.csv`、`orders.csv`、`trades.csv`。**每个 artifact 单独 try/except**，缺失/损坏时 view model 字段为 None；UI 显示"N/A"或"data unavailable"，单个坏文件不阻塞整个回测视图（参考 PR #48 detail 面板的 per-vendor 降级模式）。
  - 生成简单 Sparkline 供 TUI 展示；NaV CSV 中的空行/非数字行 skip 掉，不让坏行 raise 整个 view。
- `PaperTradingViewModel`
  - 封装 `PaperTradingEngine.get_account/get_positions/get_trades/buy/sell`。
  - 为 TUI 提供账户快照和交易委托接口。

### 测试

新增 `tests/test_tui_services.py`：

- `ReportRepository`：验证单 ETF 报告扫描、rating 识别、section 读取，并跳过 `_candidate_pools`。
- `AnalysisRunner`：使用 fake graph stream 验证 section update、ticker done、report persisted、取消路径和报告落盘。
- `BacktestRunner`：验证读取 metrics/nav/orders/trades 并生成 view model，坏 artifact 字段级降级。
- `PaperTradingViewModel`：使用 fake engine 验证账户、持仓、历史和买卖委托。
- `IdRegistry`：验证 Textual-safe id 的可逆映射和碰撞处理。
- 文件顶部包含 `assert "textual" not in sys.modules`，防止服务层误导入 Textual。

新增 `tests/test_tui_ui.py`：

- 主菜单跳转。
- 报告库空状态和刷新后非空状态。
- 研究分析 fake runner section update。
- 回测整数输入校验。
- 模拟交易账户/持仓展示与 P&L 正负颜色。

已执行验证：

```bash
uv run python -m unittest tests.test_tui_services -q
uv run python -m unittest tests.test_tui_services tests.test_tui_ui tests.test_paper_trading tests.test_backtrader_engine -q
uv run python -m py_compile cli/tui/services.py cli/tui/app.py cli/commands/tui.py tests/test_tui_services.py tests/test_tui_ui.py
uv run etfagents tui --help
```

补充验证：导入 `cli.main` 后 `textual` 不应出现在 `sys.modules`。

## 模块安排

### `cli/commands/tui.py`

职责：

- 只负责 Typer 命令入口。
- 延迟导入 Textual app。
- 对 Textual 缺失给出明确错误：引导用户运行 `pip install 'etfagents[tui]'`，并提示其他 CLI 命令（`etfagents analyze / backtest / paper`）仍可用。
- `etfagents tui --help` 文本应说明：TUI 与现有 CLI 命令并存，不替换任何命令；并列出基础命令的对应关系。

不负责：

- 不放 UI 组件。
- 不放业务逻辑。
- 不直接调用 graph/backtest/paper engine。

### `cli/tui/app.py`

职责：

- 组织 Textual app、screen、widgets、事件处理。
- 调用 `cli.tui.services` 中的服务对象。
- 管理 UI 状态，例如当前 ticker、当前 section、选中报告。

不负责：

- 不解析报告目录结构。
- 不直接处理 graph stream 细节。
- 不直接读写 backtest artifact。
- 不包含可复用业务规则。

### `cli/tui/services.py`

职责：

- 放置 TUI 可复用的非 UI 服务。
- 做 deterministic transform、文件扫描、artifact 读取、runner event 封装。
- 保持可单元测试。

不负责：

- 不依赖 Textual widget。
- 不输出 Rich/Textual 组件。
- 不改变现有 CLI 保存路径和报告格式。

### 现有 `cli/main.py`

职责保持不变：

- 继续承载现有 `analyze`、`backtest`、memory、cache 等 CLI 命令。
- 暂时提供 TUI 服务复用的保存和格式化 helper，例如 `save_report_to_disk()`。

约束：

- TUI 重构期间不大规模拆分 `cli/main.py`。
- 后续如需抽离共享 helper，应单独提交，避免与 TUI 行为变更混在一起。

### 现有 `etfagents/graph/etf_graph.py`

职责保持不变：

- 继续作为研究分析和回测编排入口。
- TUI 只通过公开方法调用，不改变 graph 内部运行模型。

### 现有 `etfagents/paper_trading/engine.py`

职责保持不变：

- 继续作为模拟交易账户、持仓、交易的唯一业务入口。
- TUI 买卖操作通过 `PaperTradingViewModel` 委托，不复制交易规则。

## UI 功能细化

### 主菜单

v1：

- 显示四个入口：研究分析、研究报告库、回测、模拟交易。
- 支持 `Escape` 返回上一层，`q` 退出，`?` 显示当前 screen 的 keybinding 帮助 panel。
- `Tab` / `Shift+Tab` 在 screen 内 widget 间循环（确认 Textual 默认行为生效，且每个 screen 进入时焦点初始化正确）。
- 长内容滚动统一使用 `PgUp/PgDn` + `Home/End`，避免不同 screen 行为不一致。

后续：

- 增加状态摘要，例如报告数量、最近回测时间、当前 paper account。

### 研究分析

v1：

- 输入多个 ETF 代码，逗号分隔。
- 输入分析日期，默认当天。
- 顺序执行分析队列。
- 左侧展示 ticker 状态：等待、分析中、完成、失败。
- 右侧展示 section 列表和 Markdown 正文。
- 分析过程中收到 section update 后实时刷新正文。
- 完成后停留在界面，允许继续切换查看。

待增强：

- 增加 analyst/research depth/provider 配置项。
- 显示当前 agent 名称。
- 每个 ticker 保留独立 section 状态：等待、生成中、完成、失败。
- 修正进度显示为每个 ticker 独立累计，而不是仅依赖最后一个事件。
- 增加失败 ticker 的错误详情面板。
- 增加取消当前队列的操作。

### 研究报告库

v1：

- 扫描本地单 ETF 报告。
- 左侧显示 ticker、日期、最新评级。
- 右侧选择 section 并展示 Markdown。
- 缺失 section 时回退到完整报告或显示空状态。

待增强：

- 左侧先按 ticker 聚合，再展开日期列表。
- 默认选择每个 ticker 最新日期。
- 增加搜索 ticker。
- 增加刷新按钮。
- 对 `_candidate_pools` 增加单独 tab，而不是混入单 ETF 报告库。

### 回测

v1：

- 从已有报告 ETF 中选择 ticker。
- 输入 `start_date`、`end_date`、`rebalance_interval_days`、`top_k`。
- 调用现有 `backtest_candidate_pool()`。
- 保存到现有 `results_dir/backtest/...`。
- 读取并展示 `summary.md`、Sparkline、指标数量、订单数量、成交数量。

待增强：

- 支持多 ETF 候选池选择。
- 支持重新打开最近一次回测结果。
- 以 DataTable 展示指标、调仓、订单、成交明细。
- 增加输入校验和错误态。
- 增加 benchmark、commission、slippage、cash buffer 等参数。

### 模拟交易

v1：

- 展示账户现金、持仓市值、账户净值、未实现盈亏。
- 展示持仓表。
- `PaperTradingViewModel` 已提供 buy/sell 委托接口。

待增强：

- 展示最近交易历史表。
- 增加买入、卖出命令弹窗。
- 支持指定 user。
- 买卖后自动刷新账户快照。
- 展示 linked analysis_id。

## Section 标签安排

所有 section key 采用 `<namespace>.<name>` 结构，UI 上按 namespace 折叠成树。这样 trader / risk 子项命名风格统一，未来新增 section 不会破坏视觉层级。

分析师团队 (`analyst.*`)：

- `analyst.market_flow`：市场与资金流
- `analyst.catalyst_sentiment`：舆情与事件
- `analyst.macro_regime`：宏观框架
- `analyst.meso_commodity`：中观大宗商品
- `analyst.holdings_industry`：持仓行业
- `analyst.top_holdings`：头部持仓

研究团队 (`research.*`)：

- `research.bull`：多头
- `research.bear`：空头
- `research.manager`：研究经理综合结论

交易员 (`trader.*`)：

- `trader.logic`：配置逻辑
- `trader.execution`：配置执行计划
- `trader.rebalance`：再平衡与风险控制
- `trader.bias`：执行倾向

风险管理 (`risk.*`)：

- `risk.aggressive`：激进
- `risk.neutral`：中性
- `risk.conservative`：保守
- `risk.portfolio_manager`：投资组合经理

最终结论 (`final.*`)：

- `final.allocation_decision`：最终组合经理决策

旧的扁平 key（如 `market_flow_report`、`aggressive`）通过 `services.SectionDefinition.legacy_key` 字段保留兼容映射，避免破坏已落盘报告的目录结构和文件名。

## 后续实施顺序

**v1 production-grade（必须完成才能 close v1）：**

1. 实现显式 `TickerState` 状态机和 per-ticker/per-section 状态模型；UI 直接渲染状态 map，移除"靠最后一个事件反推进度"的 fragile 逻辑。
2. 实现 `AnalysisRunner.request_cancel()` graceful path 和 atomic file write；配套 pilot 测试验证取消后没有半截 `reports/{section}.md`。
3. 把 `textual` 移到 `[project.optional-dependencies] tui` extra；验证基础安装时其他 CLI 命令仍可用，并完善 `cli/commands/tui.py` 的安装引导文案。
4. `ReportRepository.invalidate()` 在分析完成后被自动调用；`ReportLibraryScreen` 提供 `r` 手动刷新键。
5. 抽离 `_safe_widget_id` 为 `services.IdRegistry`，附 `register/resolve/__contains__` 单测。
6. Pilot 测试覆盖 4 个 screen 的核心交互路径（不只是 mount）：主菜单跳转、报告库空/非空状态、研究分析 fake runner section update、回测输入校验、模拟交易初始账户配色。

**v1.5（核心可用性增强）：**

7. 完善研究分析 screen 的失败 ticker 错误详情面板和取消队列 UI 操作。
8. 完善报告库 ticker/date 两级选择，默认选中每个 ticker 最新日期，加搜索框。
9. 完善回测 result view：指标表、调仓表、订单表、交易表、最近结果打开、输入校验。

**v2（次级增强）：**

10. 完善模拟交易：交易历史表、买卖弹窗、指定 user。
11. 主菜单状态摘要：报告数量、最近回测时间、当前 paper account。
12. 评估是否将 `cli/main.py` 中的共享报告保存/格式化 helper 抽到独立模块。
13. 对 `_candidate_pools` 增加单独 tab，而不是混入单 ETF 报告库。

## 风险与约束

- Textual 版本 API 变化较快，所有 UI 行为必须配 pilot smoke test。
- 分析队列调用真实 LLM 和数据 vendor，不能在单元测试中直接运行。
- 多 ETF 并发会引入限流、日志隔离、checkpoint 隔离问题，v1 不做。
- 现有 `cli/main.py` 较大，TUI 复用 helper 时要避免触发命令导入副作用。
- 报告 section 的真实内容结构可能变化，`ReportRepository` 应以路径存在为准，不依赖正文标题解析。

## 完成标准

v1 完成标准：

- `etfagents tui --help` 可用；`textual` 未安装时给出明确的 `pip install 'etfagents[tui]'` 安装提示。
- TUI 主菜单可进入四个 screen，`Escape / q / ?` 三个全局键全部生效。
- 研究分析 screen：
  - 接受多个 ticker 并顺序执行 fake runner / 真实 runner。
  - 状态机覆盖 7 个状态（pending / running / section_running / section_done / done / failed / cancelled），UI 渲染该 map。
  - 取消队列的 graceful path 已实现并测试，取消后磁盘上没有半截 `reports/{section}.md`。
- 报告库能读取现有单 ETF 报告并展示 section；分析完成后 `ReportRepository.invalidate()` 被自动调用，新报告立即可见；`r` 键手动刷新可用。
- 回测 runner 能读取本地 artifacts 并生成 view model；任一 artifact 缺失或损坏时单字段降级为 None，不阻塞整个视图。
- 模拟交易 view model 能读取账户、持仓、历史；P&L 数字配色（正 green / 负 red）由 pilot 测试锁定。
- `textual` 已迁出基础依赖，进入 `[project.optional-dependencies] tui`；基础安装下 `etfagents analyze / backtest / paper` 等命令仍能跑。
- Pilot 测试覆盖 4 个 screen 的核心交互路径，不只是 mount。
- 新增服务层单元测试通过；`tests/test_tui_services.py` 顶部包含 `assert "textual" not in sys.modules` 守卫。
- `tests.test_paper_trading` 和 `tests.test_backtrader_engine` 回归通过。
