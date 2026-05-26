# TUI 分析界面优化实施计划

## Summary

优化 `AnalysisRunScreen`，把当前“顶部四个大看板 + 左侧元数据 + 右侧文本墙”改成“左侧基本信息 + 右侧顶部紧凑 Tabs + 核心执行摘要 + 报告正文”的布局。核心执行摘要直接消费 backtest 模块已有结构化策略，不新增 LLM 调用。

目标布局：

```text
┌───────────────────────────────┬────────────────────────────────────────────────────────────────────┐
│ 📊 基本信息                    │ [📊 分析团队 4/6 ▾] [📖 研究 1/2 ▾] [⚠️ 风险 0/2 ▾] [🎯 决策 0/1 ▾] │
├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤
│ ETF 价格、成交量、份额、持仓    │ 📈 核心执行摘要                                                     │
│ 分析元数据、研究队列            │ 结构化评级、仓位、目标/止损、价格位置、报告正文                       │
└───────────────────────────────┴────────────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### 1. 梳理现有分析页组件边界

- 目标文件：`cli/tui/screens/research.py`、`cli/tui/services.py`、`cli/tui/app.py`、`tests/test_tui_ui.py`、`tests/test_tui_runner_contracts.py`。
- 保留左侧 ETF detail 获取链路：`_load_etf_detail()`、`_update_etf_card()`、`_format_detail_rich()`。
- 将右上四列看板从视觉结构中移除，改为轻量 Tabs。
- 成功标准：只影响分析运行页，不改输入页、配置弹窗、报告库、回测和模拟交易。

### 2. 把顶部四大看板压缩为右侧 Tabs

- 新增四个 Tab 按钮：
  - `#rtab-analysts`: `📊 分析团队 x/y ▾`
  - `#rtab-research`: `📖 研究 x/y ▾`
  - `#rtab-risk`: `⚠️ 风险 x/y ▾`
  - `#rtab-decision`: `🎯 决策 x/y ▾`
- 点击 Tab 后打开章节选择弹窗。
- 弹窗条目显示章节状态：`✓` 已完成、`▒` 运行中、`○` 未开始、`✗` 失败。
- 选择章节后更新 `current_section` 并刷新正文。
- 成功标准：顶部区域高度压缩为一行，章节切换仍支持鼠标和键盘选择。

### 3. 重构左侧栏为 PM 视角信息区

- `基本信息` 展示 ETF 代码/名称、现价、成交量、份额和 TOP5 持仓。
- `分析元数据` 压缩展示日期、模型、深度。
- `研究队列` 展示整体状态和 ETF 队列。
- 成功标准：左侧第一眼看到 ETF 本身，而不是后台配置参数。

### 4. 将结构化 backtest signal 传入 TUI

- 扩展 `SectionDone`，增加 `backtest_signal: dict[str, Any] | None = None`。
- `AnalysisRunner._detect_section_updates()` 从 accumulated state 中读取：
  - `backtest_signal`
  - `portfolio_backtest_signal`
  - `trader_backtest_signal`
- `AnalysisRunScreen` 保存每个 ticker 的最新 signal。
- 成功标准：核心执行摘要不新增模型调用，只消费已有结构化策略。

### 5. 增加核心执行摘要面板

- 新增 `#ra_execution_summary`。
- 展示结构化字段：评级、推荐仓位、仓位区间、加仓触发、减仓触发、风险规则、执行延迟。
- 当前价来自 ETF detail；目标/止损价仅在结构化字段可可靠识别时显示。
- 成功标准：组合经理完成后，用户不用读完整文本墙也能看到核心动作。

### 6. 报告正文数字高亮

- 新增 Markdown 高亮纯函数。
- 对价格、百分比、仓位、日期等数字加粗。
- 跳过 fenced code block、Markdown table、inline code。
- 成功标准：长报告里的关键数字更容易扫读，表格和代码块不被破坏。

### 7. 更新 CSS 视觉系统

- `#ra_sections` 改为低高度 tab bar。
- 新增 `.section-tab`、`.section-tab-active`、`.execution-summary`、`.section-picker`。
- 左侧卡片压缩边距，避免大块空白。
- 成功标准：顶部没有大块空框，终端窄宽度下文字不消失。

### 8. 更新测试

- 更新 TUI 测试：
  - Tabs 存在和计数更新。
  - 点击 Tab 打开章节选择弹窗。
  - 选择章节刷新正文。
  - 结构化摘要渲染。
  - 数字高亮跳过表格和代码块。
- 更新 runner contract 测试：
  - `SectionDone.backtest_signal` 默认兼容。
  - accumulated state 有 signal 时事件带出 signal。

## Verification

```bash
uv run python -m unittest tests.test_tui_ui tests.test_tui_runner_contracts -q
uv run python -m unittest tests.test_backtest_signals -q
uv run python -m py_compile cli/tui/screens/research.py cli/tui/services.py cli/tui/app.py
git diff --check
```

如改动触及更宽的 TUI 服务行为，再补跑：

```bash
uv run python -m unittest tests.test_tui_services -q
```

## Assumptions

- 本轮只优化分析运行界面，不重构输入 ETF 界面和配置弹窗。
- 核心执行摘要只使用现有结构化策略，不新增 LLM 摘要调用。
- 元数据默认压缩展示，不做展开/折叠。
- 价格目标、止损价格只有在结构化数据可靠存在时展示；缺失时不从正文强行猜测。
- 顶部 Tabs 的弹出选择框是本轮唯一新增交互模式。
