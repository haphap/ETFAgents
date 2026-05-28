# ETFAgents Python → TypeScript 迁移计划

> 工作主文档。每完成一项 sub-step 后更新对应章节的 **状态** + **完成时戳** +
> **追加备注**。计划超过子步骤范围的发现/决策一律先在 **待决议题** 章节记录。

---

## 0. 项目背景

ETFAgents 是 Python 多智能体 ETF 研究框架（115 文件 / ~36,700 LOC + 48 测试 /
18,210 LOC），动机是让 CLI/TUI 走 TS（Ink），同时保留 Python 量化生态
（backtrader、tushare、qlib、akshare、pandas）。

## 1. 总体架构

**方案 B：混合架构**

```
TypeScript (ts/)              JSON-RPC over stdio        Python (etfagents/)
─────────────────────         ───────────────────         ───────────────────
CLI (commander) + TUI (Ink)   newline-delimited           bridge sidecar
LangGraph.js + agent nodes ⇄  请求/响应                    ⇄ tools (langchain @tool)
LLM 客户端 (LangChain JS)                                  数据层 (tushare/qlib/yfinance)
报告/格式后处理                                              backtest (backtrader)
                                                          paper trading
                                                          cache_manager
```

**核心约束**：
- Python sidecar 对**原始代码零侵入**，只新增 `etfagents/bridge/` 包
- 工具调用边界用字符串/JSON（无跨语言 DataFrame 传输）
- 回测调用：TS 预算所有 (decision_date → signals)，单向提交，无回调
- 解释器发现：`ETFAGENTS_PYTHON` env > `<repo>/.venv/bin/python` > fail loud

## 2. 阶段总览

| 阶段 | 范围 | 状态 |
|---|---|---|
| Phase 0 | Python sidecar (`etfagents/bridge/`) + JSON-RPC + 集成测试 | ✅ 完成 |
| Phase 1 | TS 工程骨架 (`ts/`) + bridge-client + tool-loop demo | ✅ 完成 |
| Phase 2 sub-step 1 | minimal main spine (1 analyst + trader + StateGraph) | ✅ 完成 |
| Phase 2 sub-step 2 | 后处理/校验/格式化 helper 全部移植 | ✅ 完成 |
| Phase 2 sub-step 3 | 剩余 5 个 analyst + bull/bear + 3 risk + 2 manager | ⏭ 待开始 |
| Phase 2 sub-step 4 | memory + analysis_memory + reflection 全套 | ⏭ 待开始 |
| Phase 3 | Ink TUI + commander CLI（核心命令）| ⏭ 待开始 |
| Phase 4 | 回测/paper 接通 + 测试迁移 + CI 双语 | ⏭ 待开始 |

## 3. Phase 0 — Python Sidecar ✅

**新增**：`etfagents/bridge/{__init__,__main__,protocol,registry,server,handlers/{tools,config,cache,paper,backtest}}.py`，
`tests/test_bridge_protocol.py`（14 集成测试），`docs/bridge.md` + `docs/bridge_client_demo.py`。

**RPC 方法表**（21 项）：
- `tools.list` / `tools.call`（22 个 @tool 自动发现）
- `config.default` / `config.get` / `config.set`
- `cache.stats` / `cache.cleanup` / `cache.clear` / `cache.details`
- `paper.{register, login, logout, current_user, get_account, reset_account, buy, sell, get_positions, get_trades, suggest_order_from_signal}`
- `backtest.run_candidate_pool`（用 `_PrecomputedSignalGraph` shim 替代 graph）

**关键设计**：行分隔 JSON-RPC 2.0、单线程同步派发、stderr 专管日志、
`tools.call` 用 `backtest_context()` ctx-manager 自动注入回测日期 clamp。

## 4. Phase 1 — TS Skeleton + Bridge-Client ✅

**栈**：pnpm 11 + TypeScript 6 strict + biome 2.4 + Node 22 + LangChain JS v1
（zod v4）。所有依赖钉精确版本。

**新增**：`ts/{package.json, tsconfig.json, biome.json, vitest.config.ts}`，
`ts/src/{bridge,llm,cli/{index,commands/{bridge-ping,tool-call,tool-loop}}}/`，
`ts/test/{python,client,tools}.test.ts`。

**Phase 1 Exit demo**：`pnpm dev tool-loop <ticker>` —
ChatOpenAI + 一个 bridge tool 的最小 LLM 回路。

## 5. Phase 2 sub-step 1 — Minimal Spine（路径 A）✅

**范围**：1 个 analyst (`etf_market_analyst`) + trader + StateGraph（START
→ market_flow ↔ tools → trader → END）+ `analyze-mini` CLI 命令。

**故意跳过**（明确 TODO）：所有后处理 / validate_refine / normalize / memory，
留给 sub-step 2。

**端到端验证**（Lemonade Qwopus3.6 + Tushare）✅ 跑通，输出 trader_allocation_plan
有 4 段 + 中文评级。

## 6. Phase 2 sub-step 2 — Helper 层移植 🚧

> 目标：把 market_flow → trader 主干路径上 Python 的所有后处理 / 校验 /
> 格式化逻辑等价移植到 TS。每个子阶段独立 ship，typecheck + vitest +
> Python 回归全绿。

### 6.1 Sub-step 2.1 — 工具链恢复 ✅
**Files**：`ts/src/agents/helpers/{content,process_narration,tool_report_chain}.ts`
（合计 ~590 LOC），`ts/test/{process_narration,tool_report_chain}.test.ts`。

**移植**：`extract_text_content`、`looks_like_process_narration`、
`isToolCallText`、`isProcessOnlyReportText`、`stripProcessOnlyReportPrefix`、
`looksLikeUnexecutedToolIntent`，完整版 `runToolReportChain`（接受度门槛 +
多级 fallback + 未执行工具恢复 + last_attempt 策略）。

### 6.2 Sub-step 2.2 — report_leads 中文规则 ✅
**Files**：`ts/src/agents/helpers/{report_leads,role_terms}.ts`（~330 LOC），
`ts/test/{report_leads,role_terms}.test.ts`。

**移植**：`collectTopSectionMarks`、`hasInvalidOpeningCap`、
`stripDecisionLabelArtifacts`（修复 sub-step 1 端到端验证里看到的
"最终配置建议: **持有**" 泄漏）、`stripRefinePreamble`、`stripMetaOpeners`、
`stripSelfReferentialMetaLeads`、`preJudgeClean` / `postJudgeClean` 编排，
`normalizeChineseRoleTerms` (21 条 role-term map) + `normalizeChineseManagerTerms`。

**显式延后**（在代码注释里 TODO）：`normalize_boxed_text_wrapping`、
`strip_qa_labels`、`strip_opening_term_explanations` /
`strip_inline_technical_term_explanations`、`strip_declarative_question_marks`、
以及 `normalize_chinese_role_terms` 链下的 5 个子规范化器
（`normalize_display_numbering`、`normalize_chinese_numeric_expressions`、
`normalize_chinese_finance_terms`、`_normalize_risk_recommendation_text`、
`_ensure_chinese_section_breaks`）。

### 6.3 Sub-step 2.3 — validate_and_refine ✅
**Files**：`ts/src/agents/helpers/validate_refine.ts`（401 LOC），
`ts/test/validate_refine.test.ts`。

**移植**：`AnalystReportSpec`、`StaticVerdict`、`JudgeVerdict` (zod schema)、
`staticValidate`、`validateAndRefine`（4 模式：disabled / static_only /
static_plus_llm / llm_only）、`parseJudgeJson`（容错 JSON 提取，兼容
markdown 嵌入 + legacy `pass` 字段）。`PromptContext` 加 `validationMode`
字段。

### 6.4 Sub-step 2.4 — market_flow 尾部规范化 ✅
**Files**：`ts/src/agents/helpers/market_flow_normalize.ts`（~250 LOC），
`ts/test/market_flow_normalize.test.ts`。

**移植**：`looksLikeCompleteMarketFlowReport`（严格接受度门槛：非空 +
valid opening cap + 一/二/三 + 表格分隔符）、
`normalizeMarketFlowTailSections`（合并 3 种 legacy 尾段形态 → 单一
"四、综合结论和指标总览" + 段落 + 表格）。market_flow 节点把接受度作为
`runToolReportChain` 的 `acceptanceCheck`。

### 6.5 Sub-step 2.5a — trader 后处理（heading 规范 + 成分股纪律）✅
**Files**：`ts/src/agents/helpers/trader_format.ts`（~250 LOC 第一版），
`ts/test/trader_format.test.ts`。

**移植**：`demoteTraderH1Headings`、`normalizeTraderConfigLogicHeading`、
`restoreTraderExecutionBiasSection`、`stripConstituentTradeInstructions`
（含 ETF 层级声明插入）。trader 节点链式调用 5 个 helper（顺序与 Python
一致）。

### 6.6 Sub-step 2.5b — Chinese 编号格式化 ✅
**Files**：`trader_format.ts` 扩展（+~140 LOC），`render.ts` 重写。

**移植**：`stripNumberedHeadingPrefix`、`splitSentences`、`hasNumberedBlocks`、
`compactText`、`hasUnnegatedKeyword`、`traderBlockKey` (initial/add/reduce/
monitor 四桶分类)、`traderBlockLabel` (execution/risk 两套标题)、
`formatTraderNumberedBlocks`、`formatTraderThesisBody`。
`renderTraderProposal` 中文模式按 Python 顺序应用：
`stripNumberedHeadingPrefix → formatTraderThesisBody`（thesis），
`formatTraderNumberedBlocks("execution"/"risk")`。

### 6.7 Sub-step 2.5c-1 — 市场价位 inline ✅
**Files**：`ts/src/agents/helpers/market_levels.ts`（~210 LOC），
`ts/test/market_levels.test.ts`。

**移植**：`extractMarketLevelAnchors`、`marketLevelPriority` +
`prioritizeAnchors`、`primaryAnchor` / `anchorClause` /
`extractAnchorMap`、`inlineContextualMarketLevels`。
`renderTraderProposal` 接收 `contextText` 参数（=
`state.market_flow_report`），在中文模式下对 execution_plan 注入。

### 6.8 Sub-step 2.5c-2 — sanitize-section 家族 ✅
**目标**：当 LLM 返回的某个 section 文本太短/太空时，用预定义默认文本兜底，
避免下游消费空字段。

**待移植 Python 函数**（`etfagents/agents/schemas.py`）：
| 函数 | 行数 | 作用 |
|---|---|---|
| `_default_execution_plan(rating, context_text)` | ~80 | 按评级 + 市场上下文生成兜底执行计划文本 |
| `_default_research_positioning_guidance` | ~40 | research-manager 默认仓位建议 |
| `_sanitize_section(text, default, rating, **opts)` | ~50 | 若过短/与默认相同/缺乏行动动词，融合或替换 |
| `_section_needs_detail` / `_compact_text` | ~20 | 长度 + sentence count 阈值检测 |
| `_missing_execution_thresholds(text)` | ~30 | 检测是否缺数值/价位/百分比阈值 |
| `_merge_sparse_section_with_default(content, default)` | ~30 | 把默认文本融合到稀疏段落（保留原文 + 追加默认） |
| `_sanitize_trader_thesis(thesis, execution_plan, rating, heading_aliases)` | ~60 | 防止 thesis 与 execution_plan 重复；强制 thesis 给"为什么"而非"做什么" |
| `_sanitize_trader_risk_management(...)` | ~50 | 同上，针对 risk_management |
| `_strip_recommendation_restating_sentences` | ~30 | 剥离"评级: **持有**" 类重复评级行 |
| `_remove_overlapping_sentences(text, reference)` | ~20 | 句子相似度 (SequenceMatcher) 去重 |
| `_sentence_similarity(left, right)` | ~15 | difflib SequenceMatcher → JS 端可用 `js-levenshtein` 或自写 LCS |
| `_default_action_logic` / `_default_debate_conclusion` | ~30 | research-manager 默认 |

**接入点**：在 `renderTraderProposal` 中文/英文路径上，按 Python 顺序应用：
1. `_sanitize_section(execution_plan, default_execution_plan, rating, ...)`
2. `inlineContextualMarketLevels(execution_plan, context_text)` ← 已有
3. `stripConstituentTradeInstructions(execution_plan)` ← 已有
4. 若 `_missing_execution_thresholds(execution_plan) && default 不在 execution_plan` → `_merge_sparse_section_with_default`
5. `_sanitize_trader_thesis(thesis, execution_plan, rating, heading_aliases)`
6. `_sanitize_trader_risk_management(...)`

**估算**：~600 LOC TS + ~25 测试。1–2 turns。

**风险**：`_sentence_similarity` 用 Python 的 SequenceMatcher，TS 没原生
等价。两个选项：
- (A) 实现 LCS-based ratio（与 SequenceMatcher 行为接近）
- (B) 引入 `string-similarity` 或 `js-levenshtein` 包
推荐 (A)，避免新依赖。

### 6.9 Sub-step 2.5c-3 — invoke_structured_or_freetext 完整版 ✅
**目标**：把当前 trader 节点里粗糙的 try/catch + free-text fallback 替换成
Python 的细致版本。

**待移植**（`etfagents/agents/utils/structured.py`）：
| 函数 | 行数 | 作用 |
|---|---|---|
| `bind_structured(llm, schema, agent_name)` | ~30 | 兼容多种 LangChain backend 的结构化绑定，处理 schema 不支持时 fallback |
| `build_structured_output_prompt(prompt, schema)` | ~40 | 在 prompt 后追加 schema 要求 |
| `build_prose_only_fallback_prompt(prompt, extra)` | ~30 | 已部分移植 (stripStructuredOnlyText)，需补 extra 注入逻辑 |
| `invoke_structured_or_freetext_with_result(...)` | ~80 | 主入口：先 structured，失败/空字段触发 free-text，返回 `(rendered, structured)` 元组 |
| `_strip_structured_only_text` | 已移植 | — |
| `_transform_prompt_strings` | ~15 | 递归替换 prompt 树字符串 |

**估算**：~250 LOC TS + ~12 测试。1 turn。

### 6.10 Sub-step 2.6 — build_trader_backtest_signal ⏭ 待开始
**目标**：从 trader 输出（rendered prose + structured TraderProposal）抽取
出 framework-agnostic 的 `BacktestSignal` dict，供 `backtest.run_candidate_pool`
RPC 消费。

**待移植**（`etfagents/backtest/signals.py` ~680 LOC）：
| 函数 / 类 | 作用 |
|---|---|
| `BacktestSignal` dataclass | TS 端定义为 zod schema |
| `build_trader_backtest_signal(asset, trade_date, rendered, structured)` | 主入口 |
| `build_state_backtest_signal(state)` | 候选池路径用，从 final_state 抽取 |
| `build_candidate_backtest_signal(item, trade_date)` | 候选池排名后用 |
| `build_portfolio_backtest_signal(portfolio_decision)` | risk/manager 路径 |
| `_extract_target_weight(text, structured)` | 从 prose 抽 `target_weight_pct` |
| `_extract_target_weight_band` | 从 prose 抽区间 |
| `_extract_execution_timing(text)` | same_close / next_open / next_close |
| `_extract_triggers(text, kind)` | 从 prose 抽 add/reduce/exit/rebalance triggers |
| `_extract_risk_rules(text)` | 从 prose 抽 risk_controls |
| `_normalize_metric_name(text)` | close_50_sma / volume_ratio_20d 标准化 |
| `_parse_threshold(text)` | "3.58 元" → 3.58, "1.3 倍" → 1.3, "30%" → 30, range "3.58-3.60" → (3.58,3.60) |
| `signal_text_snapshot` 字段保留原始 prose | |

**估算**：~700 LOC TS + ~30 测试。**最复杂的一段**，2–3 turns。

**TS 端落点**：
- 新文件 `ts/src/agents/helpers/backtest_signal.ts`
- `BacktestSignalSchema` (zod) 复用 `Trigger`/`RiskRule` schemas
- trader 节点 `trader_backtest_signal` 字段从 `{}` 占位改为真实 build 结果
- mini_spine 测试 mock 应同时返回 structured 字段，验证 build 输出形态

**风险**：Python 的 prose 抽取依赖大量正则（每种 trigger metric 不同），
直接照搬约 60+ 个 regex 常量。需要保持与 Python 行为一致以保证回测对账。

### 6.11 Sub-step 2.7 — memory 注入 ⏭ 待开始
**目标**：让 analyst / trader prompt 能注入 lesson / continuity / method
context（现状是占位空段），与 Python 行为一致。

**待移植**：
| 模块 | 行数 | 作用 |
|---|---|---|
| `etfagents/agents/utils/analysis_memory.py` 部分 | ~876 全文，估 300 行可移 | `build_memory_prompt_section(state, role, aliases)`、`inject_memory_prompt_section(system_message, section)`，外加 SQLite 读路径 |
| `etfagents/agents/utils/memory.py` | ~250 | `TradingMemoryLog` 读路径（写路径暂不需要） |

**注意**：memory 写路径（reflect_and_remember / build_outcome_lesson / 等）
留给 Phase 2 sub-step 4 一并完成（涉及 `Reflector` 和 deferred update 流水
线，较复杂）。

**TS 端落点**：
- 新文件 `ts/src/agents/helpers/memory.ts`（读 + prompt 注入）
- bridge 新增 `analysis_memory.read_for_role` RPC，让 TS 不直接读 SQLite
  （或：用 `better-sqlite3` 直接读，保持文件位置一致）
- market_flow / trader 系统 prompt 在 buildSystemMessage 里调用
  `injectMemoryPromptSection`（替换当前 path A 的占位）

**估算**：~400 LOC TS + ~15 测试 + bridge handler 新增 1 个。1–2 turns。

### 6.12 Sub-step 2 完成标准
1. market_flow → trader 端到端跑通，输出与 Python 同 ticker/同日期的报告
   diff 只剩 LLM 随机性
2. trader_backtest_signal 有真实结构（不再是 `{}`）
3. memory section 注入有效（如果有可用 lesson 文件）
4. 全部 typecheck + biome + vitest + Python 回归绿色

### 6.13 Sub-step 1 遗留 bug 复查
**约定**：sub-step 2 全部做完后，重跑端到端，对照 sub-step 1 时观察到的：
- ✅ "最终配置建议: **持有**" 泄漏 → 2.2 已修
- ⚠️ trader thesis 与 rating 矛盾（thesis 偏空但 rating 买入）→ 2.5c-2 的
  `_sanitize_trader_thesis` 应能缓解；如仍存在，加 prompt 一致性约束
- ⚠️ trader 报告里 trade_date 错乱（写了 2026 年日期）→ 2.7 之后 trader
  prompt 直接接收 trade_date

---

## 7. Phase 2 sub-step 3 — 剩余 5 analyst + 辩论 + 决策 ⏭ 待开始

> 这是 Phase 2 最大的一段（~7,000 LOC Python prompt + 节点逻辑），按
> 子阶段拆分。每个 analyst 的后处理已在 sub-step 2 通过统一 helper 解决，
> 这里只剩 prompt + 节点 + spec。

### 7.1 剩余 analyst（5 个 × prompt + spec + 节点 + tools 配置）
| analyst | 工具 | spec required_top_sections | 估算 |
|---|---|---|---|
| catalyst_sentiment | get_etf_info, get_etf_holdings, get_news, get_global_news | 一/二/三/四 | 1 turn |
| macro_regime | get_etf_info, get_etf_holdings, get_macro_regime_data, get_global_news, get_news | 一/二/三/四 | 1 turn |
| meso_commodity | get_commodity_cluster_data | 一/二/三/四 | 1 turn |
| holdings_industry | get_etf_holdings, get_etf_industry_research | 一/二/三 | 1 turn |
| top_holdings | get_etf_holdings, get_etf_top_holdings_research | 一/二/三 | 1 turn |

**模式统一**：每个 analyst 复用 `runToolReportChain` + `validateAndRefine` +
`pre/post_judge_clean`（共享的统一通道），各自只需提供：
1. prompt 字符串（中英双语，从 Python 原样移植）
2. `unexecuted_tool_recovery` 的 tool_payloads 配置
3. `AnalystReportSpec`（required_top_sections / required_indicator_tokens / tail）
4. 可选的 analyst-specific normalize（如果有，类似 `_normalize_market_flow_tail_sections`）

### 7.2 bull/bear/research_manager（辩论流）
**Python**：`agents/researchers/{bull_researcher,bear_researcher}.py` +
`agents/managers/research_manager.py` + `graph/conditional_logic.py`。

**新增**：
- `InvestDebateState` Annotation 在 `state.ts`
- 节点：bull → bear → research_manager（条件循环 max_debate_rounds 次）
- prompts/researchers/{bull,bear}.ts、prompts/managers/research_manager.ts
- schemas/research_plan.ts（`ResearchPlan` zod schema）
- helper: `extract_feedback_snapshot` / `strip_all_feedback_snapshots`
  （在 agent_utils.py 已读过，可借 sub-step 2.5c 的 sanitize 一并完成）

**估算**：3 turns（含 helper、schema、节点、conditional 路由）。

### 7.3 3 个 risk debator + portfolio_manager
**Python**：`agents/risk_mgmt/{aggressive,conservative,neutral}_debator.py`
+ `agents/managers/portfolio_manager.py`。

**新增**：
- `RiskDebateState` Annotation
- 节点：aggressive → conservative → neutral → portfolio_manager（循环
  max_risk_discuss_rounds 次）
- prompts、`PortfolioDecision` schema、render 函数

**估算**：3 turns。

### 7.4 graph 全套：reflection / signal_processing / propagation
**Python**：`graph/{reflection,signal_processing,propagation,
conditional_logic}.py`（共 ~600 行）。

**估算**：1 turn（大多是机械翻译）。

### 7.5 Sub-step 3 完整图集成
**最终图**：6 analyst（并行/顺序，与 Python `etf_setup.py` 对齐）→ bull/bear
（带 ToolNode）→ research_manager → trader → 3 risk debator →
portfolio_manager → END，含全部 conditional edges + max_round 控制 +
checkpoint hook。

**估算**：1 turn。

**Phase 2 sub-step 3 总估算**：约 9–11 turns。

---

## 8. Phase 2 sub-step 4 — memory 写路径 + reflection ⏭ 待开始

**Python**：
- `agents/utils/analysis_memory.py` 写路径：`AnalysisMemoryStore`、
  `MemoryContextBuilder`、`build_outcome_lesson_entry`、
  `build_method_playbook_entry`、`create_memory_writer`
- `agents/utils/memory.py` 写路径：`TradingMemoryLog.store_decision`、
  `batch_update_with_outcomes`
- `graph/reflection.py`：`Reflector.reflect_on_final_decision`

**新增**：
- `ts/src/agents/helpers/memory_writer.ts`
- `ts/src/agents/nodes/memory_writer.ts`（图 END 之前的最后节点）
- bridge 新增 `analysis_memory.{store_decision, append_analysis,
  append_outcome, append_playbook, get_pending}` 等 RPC
- 或直接 TS 端用 `better-sqlite3` 读写（与 Python 共享同一文件）

**关键设计决策**：是 **TS 直接读写 SQLite**（共享 ~/.etfagents/memory.db）
还是 **走 RPC**？前者快但需谨慎并发；后者简单但每次调用过 IPC。**建议
走 RPC**，与 paper trading 一致。

**估算**：3 turns。

---

## 9. Phase 3 — Ink TUI + Commander CLI ⏭ 待开始

> 这是迁移**最初动机**所在。Phase 2 完成时框架已能跑端到端 analysis；
> Phase 3 把它包装成与现有 Python CLI 等价或更好的 TUI 体验。

### 9.1 范围决议
**核心命令**（已确认）：tui、analyze、backtest、detail、cache。
**留 Python**：watchlist、memory、paper（Phase 3 末再决策是否补迁）。

### 9.2 子阶段
| 子阶段 | 内容 | 估算 |
|---|---|---|
| 3.1 | commander 子命令骨架（analyze、analyze --candidate-pool、detail、cache） | 1 turn |
| 3.2 | analyze 单 ticker 走 mini_spine（已有）+ rich 输出 | 1 turn |
| 3.3 | analyze 候选池：循环 ticker + 排名 + 候选签名缓存（接 Python `BacktestSignalStore`） | 2 turns |
| 3.4 | detail 命令：tushare 行情/NAV/holdings 表格 | 1 turn |
| 3.5 | cache stats/cleanup/clear（直接调 bridge `cache.*`） | 0.5 turn |
| 3.6 | Ink TUI 骨架 + 路由（分屏：Models/Analysis/Logs，与 Python `cli/tui` 对齐） | 2 turns |
| 3.7 | Ink 各 screen 实现（research, detail, cache, paper, settings） | 4–6 turns |
| 3.8 | TUI 状态机 + service 层（与 Python `cli/tui/services.py` 1267 行对齐）| 3 turns |

**Phase 3 总估算**：约 14–17 turns。

### 9.3 Ink 设计原则
- 与 React 习惯一致（Hook + Context）
- 每个 screen 是独立组件，路由用本地 reducer
- LLM 调用统一通过 `BridgeApi` + `LangGraph.invoke` 抽象
- 进度条/动画统一组件库

---

## 10. Phase 4 — 回测/Paper 接通 + 测试迁移 ⏭ 待开始

### 10.1 回测接通
**TS 端**：候选池分析 → 收集每个 (rebalance_date, ticker) 的 signal →
组装成 `BacktestSignalsByDate` → 调 `backtest.run_candidate_pool` RPC →
渲染结果（NAV 曲线 / 排名 / metrics）。

**新增**：
- `ts/src/cli/commands/backtest.ts`
- `ts/src/cli/render/backtest_result.ts`（rich 表格 + simple ASCII chart）
- `ts/src/agents/graph/replay.ts`（候选池 replay 模式，对齐 Python
  `graph/replay.py`）

**估算**：3 turns。

### 10.2 Paper 接通
TS 端调 `paper.*` RPC，输出表格。仅 CLI（不进 TUI）。

**估算**：1 turn。

### 10.3 测试迁移策略
- **保留 Python**：vendor routing、tushare/qlib/yfinance 集成、backtest
  engine、paper_trading 业务规则、cache_manager — 这些直接调 sidecar 测试
- **迁 Vitest**：纯逻辑测试（report_leads、validate_refine、trader_format
  等已迁的 helper）。Python 对应测试改为"调 bridge 接口"或保留双份
- **CI**：单 workflow 同时跑 `python -m unittest` + `pnpm test`，互为参考

**估算**：3 turns。

### 10.4 文档与发布
- 更新 `README.md`、`docs/usage.md` 描述 TS CLI 用法
- 新增 `docs/migration_status.md` 标注 Python/TS 对应表
- 内部使用，**不发 npm**

**估算**：1 turn。

**Phase 4 总估算**：约 8 turns。

---

## 11. 风险与未决议题

### 11.1 已知风险
1. **LangGraph.js v1 ↔ Python 检查点行为差异**
   - Python 用 `langgraph-checkpoint-sqlite`，TS 有 `@langchain/langgraph-checkpoint-sqlite`
   - **缓解**：Phase 2 sub-step 3 末验证 thread_id 化检查点；不行就 TS 自己写 SQLite checkpoint

2. **结构化输出语义差异**
   - LangChain Python `bind_tools(schema)` vs LangChain JS `withStructuredOutput`
   - 当前 `withStructuredOutput` 在 Lemonade Qwen 下工作良好；但其他 backend（Anthropic 直接 SDK）可能需要不同绑定
   - **缓解**：sub-step 2.5c-3 完整移植 `bind_structured`

3. **正则跨语言一致性**
   - 中文文本规则正则非常多（report_leads、trader_format、market_levels
     合计 ~80 个 regex 常量），Python re ↔ JS RegExp 行为差异（如
     `\b` 在 CJK 上、命名捕获组、lookbehind）
   - **缓解**：每个移植后写镜像测试用例对照行为

4. **memory 跨语言并发**
   - 若 TS 和 Python 同时读写 ~/.etfagents/memory.db 会出现 SQLite 锁
   - **缓解**：走 bridge RPC，单进程访问

5. **大模型上下文长度**
   - market_flow_report 完整版接近 16K chars；trader prompt 把所有
     analyst 报告都拼进 system message，容易爆 context
   - **缓解**：`truncateForPrompt` 已就位，按 `report_context_char_limit`
     裁剪；端到端跑时观察实际 token 用量

### 11.2 未决议题
1. **memory 是否走 RPC**？倾向 RPC，但若性能瓶颈明显可改 TS 直读
2. **是否在 Phase 2 sub-step 3 把英文输出（`output_language=English`）
   也跑一遍验证**？目前所有移植以 Chinese 路径为主。建议至少 sub-step 3
   末跑一次 English smoke test
3. **paper_trading 是否真要迁 TS**？延后到 Phase 3 末决策，看 TUI 出来后
   表格 UX 收益是否值得
4. **回测的进度上报**？Python 的 backtest 可能跑很久，TS 端需要异步轮询
   或 SSE。RPC 当前是同步调用——后续需要 streaming RPC 支持

---

## 12. 当前里程碑（更新于 2026-05-28）

**已完成**：
- Phase 0（21 RPC 方法 + 14 集成测试）
- Phase 1（TS 工程 + Phase 1 Exit demo）
- Phase 2 sub-step 1（minimal main spine）
- Phase 2 sub-step 2.1 / 2.2 / 2.3 / 2.4 / 2.5a / 2.5b / 2.5c-1 / 2.5c-2 / 2.5c-3

**TS 测试**：259/259 通过；**Python 回归**：14/14 通过。

**端到端验证**：单 ticker（510300.SH @ 2024-06-01）跑通，
trader_allocation_plan 中文 4 段格式 + 真实 Tushare 价格数据。

**接下来**：sub-step 2.6（build_trader_backtest_signal，最复杂的一段）→
2.7（memory 注入读路径）→ 进入 sub-step 3（剩余 analyst + 辩论 + 决策）。

---

## 13. 工作流约定

每个子任务完成后：
1. `pnpm typecheck` clean
2. `pnpm lint`（biome）clean
3. `pnpm test` 全绿
4. `python -m unittest tests.test_bridge_protocol -q` 全绿
5. 更新本文档对应章节状态 + 完成时戳
6. 在用户能验证的 checkpoint 处暂停

**何时回归端到端**：每完成一个 sub-step（2.5/2.6/2.7/3.x）末做一次
`pnpm dev analyze-mini 510300.SH --provider ollama --base-url ...
--max-tokens 16000`，观察输出是否相对上次有可见改进；记录 LLM
凭证依赖（TUSHARE_TOKEN、本地 Lemonade 端点）的最低运行要求。

---
