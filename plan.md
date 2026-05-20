# ETFAgents 借鉴 TradingAgents-CN 功能增强计划

> 借鉴来源: https://github.com/hsliuping/TradingAgents-CN (v1.0.1)
> 编制日期: 2026-05-20
> 持久化方案: SQLite
> 实施顺序: 基础设施优先 (P1→P2→P3) → 交互功能 (P4→P5→P6)

---

## 目录

1. [现状差距分析](#1-现状差距分析)
2. [P1: 缓存管理系统](#p1-缓存管理系统)
3. [P2: 自选股(ETF池)管理](#p2-自选股etf池管理)
4. [P3: 智能模型选择](#p3-智能模型选择)
5. [P4: ETF详情页](#p4-etf详情页)
6. [P5: 批量分析增强](#p5-批量分析增强)
7. [P6: 模拟交易系统](#p6-模拟交易系统)
8. [文件变更总览](#8-文件变更总览)
9. [测试策略](#9-测试策略)
10. [风险与依赖](#10-风险与依赖)

---

## 1. 现状差距分析

### 1.1 功能对比

| 功能维度 | TradingAgents-CN | ETFAgents 现状 | 差距 |
|---------|-----------------|---------------|------|
| **个股详情页** | FastAPI+Vue3, 4子端点(quote/fundamentals/kline/news), 前端Tabs展示 | CLI扁平报告, 无交互drill-down | 大 |
| **智能模型选择** | 能力分级(1-5)+深度约束+自动推荐quick+deep模型对+聚合厂商解析 | 9个provider但手动选择, model_catalog仅有(display_name, model_id) | 中 |
| **自选股管理** | MongoDB `user_favorites`集合, tags/notes/价格提醒, CRUD API | 每次手动输入ticker, 无持久化 | 大 |
| **批量分析** | asyncio并发+WebSocket进度推送+三级结果存储(内存/MongoDB/文件) | 顺序candidate_pool分析, 无进度推送 | 中 |
| **缓存管理** | 文件/MongoDB/Redis三级缓存, API管理(stats/cleanup/clear/details) | 4类缓存分散, 无统一管理界面, 存在多个正确性bug | 中 |
| **模拟交易** | 多币种/多市场纸盘账户, T+1规则, 佣金计算, 分析报告关联 | Backtrader回测引擎仅历史回放, 无实时模拟 | 大 |

### 1.2 现有缓存基础设施

| 缓存类型 | 存储位置 | 管理方式 | 线程安全 | 主要问题 |
|---------|---------|---------|---------|---------|
| Tushare API 响应 | `~/.etfagents/cache/` (变量) | 无管理 | 无 | `lru_cache`死导入, `_cached_pro_client`非线程安全 |
| 回测信号 | `~/.etfagents/logs/backtest_cache/{hash}/{ticker}/{date}.json` | `--force-refresh` | 无 | 非原子写, config_hash不含prompt版本, 无清理 |
| 每日快照 | `~/.etfagents/cache/shared_snapshots/{kind}/{date}.json` + `.lock` | 无管理 | 部分(文件锁) | 损坏文件永久毒化key, schema容错不够 |
| Checkpoint | `~/.etfagents/cache/checkpoints/{TICKER}.db` (SQLite) | `--clear-checkpoints` | 部分(SQLite) | `clear_checkpoint`留空.db文件, 无过期清理 |

### 1.3 现有dataflows可复用的ETF数据接口

| 接口 | 路由方法 | 返回类型 | 数据源 |
|-----|---------|---------|-------|
| OHLCV | `route_to_vendor("get_etf_price_data", ticker, start, end)` | str(CSV) | tushare |
| 技术指标 | `route_to_vendor("get_etf_indicators", ticker, indicator, date, lookback)` | str(Markdown) | tushare |
| ETF档案 | `route_to_vendor("get_etf_info", ticker, date)` | str(CSV) | tushare |
| NAV历史 | `route_to_vendor("get_etf_nav", ticker, date)` | str(CSV) | tushare |
| 持仓 | `route_to_vendor("get_etf_holdings", ticker, date)` | str(CSV) | tushare |
| 份额变动 | `route_to_vendor("get_etf_share", ticker, date)` | str(CSV) | tushare |
| ETF因子快照 | `_latest_etf_factor_snapshot(ticker, date)` (私有) | dict | tushare |

### 1.4 CLI子命令注册模式

```python
# 已有模式(以memory为例):
memory_app = typer.Typer(help="Structured analysis memory utilities.")
app.add_typer(memory_app, name="memory")

@memory_app.command("promote-playbook")
def promote_playbook(...): ...
```

### 1.5 关键约定

- 所有config必须 `copy.deepcopy(DEFAULT_CONFIG)` 后才可修改
- 使用 `_normalize_ticker_list()` 解析逗号分隔的ticker
- 使用 `_localize_cli_label()` / `_localize_cli_section_title()` 做i18n
- 使用 `console.print()` 输出, `raise typer.Exit(code=1)` 报错退出
- 子命令名用 kebab-case (如 `promote-playbook`)

---

## P1: 缓存管理系统 ✅ 已完成

> PR: https://github.com/haphap/ETFAgents/pull/42

### 目标

修复现有缓存模块的正确性问题，统一管理4类缓存，新增 `etfagents cache` 子命令组。

### 第一层：模块修复（影响正确性，改动量小）

#### F1: `BacktestSignalStore.put()` 改原子写

**涉及文件**: `etfagents/backtest/cache.py` (`BacktestSignalStore.put`，约 line 39-42)

**问题**: `path.write_text(json.dumps(...))` 非原子写，断电或并发读可产生截断JSON。

**修复**: 复用 `daily_snapshot_cache.py` 已有的 `_write_snapshot_file()` 中的 tempfile+`os.replace` 模式。

```python
# before (BacktestSignalStore.put, around line 39-42):
path.write_text(
    json.dumps(dict(payload), ensure_ascii=False, indent=2),
    encoding="utf-8",
)

# after:
import os
import tempfile

temp_path = None
try:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                     dir=path.parent, encoding="utf-8") as tmp:
        json.dump(dict(payload), tmp, ensure_ascii=False, indent=2, default=str)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = tmp.name
    os.replace(temp_path, path)
finally:
    if temp_path and os.path.exists(temp_path):
        os.unlink(temp_path)
```

#### F2: 损坏快照文件自动恢复

**涉及文件**: `etfagents/agents/utils/daily_snapshot_cache.py` (`_load_snapshot_file`，约 line 73-97)

**问题**: `_load_snapshot_file` 遇到坏JSON/结构错误时抛 `DailySnapshotCacheError`，但不管损坏文件。后续调用永久命中同一损坏文件。

**修复**: 遇到损坏文件时重命名为唯一 `.corrupt.<timestamp>` 文件，下次调用自动重建。若重命名失败（如权限问题），记录 warning 后继续抛出 `DailySnapshotCacheError`，避免静默复用坏文件。

```python
# 在 _load_snapshot_file 的 except json.JSONDecodeError / except DailySnapshotCacheError 块中:
corrupt_path = path.with_suffix(path.suffix + f".corrupt.{int(time.time())}")
try:
    path.rename(corrupt_path)
except OSError as exc:
    logger.warning("Failed to quarantine corrupt snapshot %s: %s", path, exc)
    raise
return None  # 触发重建
```

> **实现偏差说明**: 实际实现选择了 `raise DailySnapshotCacheError` 而非 `return None`。原因: 现有测试 `test_corrupted_cache_raises_explicit_error` 锁定了"损坏缓存必须抛异常"的契约，改为 `return None` 会破坏向后兼容。实现仍会隔离损坏文件，下次调用时自动重建成功。详见 `_quarantine_corrupt_snapshot()` 文档字符串。

#### F3: `_is_usable_snapshot` 类型容错

**涉及文件**: `etfagents/agents/utils/daily_snapshot_cache.py` (`_is_usable_snapshot`，约 line 100-115)

**问题**: `coverage_days` 非int时抛 `DailySnapshotCacheError` 而非返回 `False`，caller期望返回False后重建。

**修复**: `isinstance(metadata.get("coverage_days"), int)` 不匹配时返回 `False`（而非抛异常）。

```python
# before:
coverage_days = metadata["coverage_days"]
if coverage_days < min_coverage_days:
    return False

# after:
coverage_days = metadata.get("coverage_days")
if not isinstance(coverage_days, int):
    return False  # 触发重建
if coverage_days < min_coverage_days:
    return False
```

#### F4: config_hash 加入 prompt 版本

**涉及文件**: `etfagents/backtest/cache.py` (`BacktestSignalStore._config_hash`，约 line 56)

**问题**: `_config_hash()` 包含LLM配置但不含prompt模板版本。prompt更新后静默命中旧缓存。

**修复**: 新增明确的 `BACKTEST_SIGNAL_PROMPT_VERSION` 模块级常量并纳入 hash。该常量在影响 backtest signal 语义的 prompt / signal extraction 变更时手动递增；不在运行时扫描或 hash prompt 文件内容。

```python
# 在 hash_material 中新增:
"backtest_signal_prompt_version": BACKTEST_SIGNAL_PROMPT_VERSION,
```

#### F5: 删除 tushare 死导入

**涉及文件**: `etfagents/dataflows/tushare.py` (line 7)

**问题**: `from functools import lru_cache` 导入但从未使用。注意：`_cached_pro_client` 全局变量的线程安全问题（见"不在 P1 范围"表）是独立问题，本修复仅清理死代码。

**修复**: 删除该 import 行。

### 第二层：统一缓存管理（对外功能）

#### 架构

不新增存储。`CacheManager` 聚合现有缓存目录，负责统计、分页查看、按类别清理和清空。

#### `etfagents/cache_manager.py`

```python
"""Unified cache management for ETFAgents."""

class CacheManager:
    CATEGORIES = ("api", "signals", "snapshots", "checkpoints")

    def __init__(self, config: dict):
        self._config = config
        self._api_cache_dir: Path = Path(config["data_cache_dir"])
        self._signal_cache_dir: Path = Path(config["results_dir"]) / "backtest_cache"
        self._snapshot_cache_dir: Path = Path(config["data_cache_dir"]) / "shared_snapshots"
        self._checkpoint_dir: Path = Path(config["data_cache_dir"]) / "checkpoints"

    def stats(self) -> dict:
        """各类缓存的文件数和总大小(MB)。

        Returns:
            {
                "api": {"count": int, "size_mb": float, "subdirs": [str]},
                "signals": {"count": int, "size_mb": float},
                "snapshots": {"count": int, "size_mb": float, "kinds": [str]},
                "checkpoints": {"count": int, "size_mb": float, "tickers": [str]},
                "total_mb": float,
            }
        """
        ...

    def cleanup(self, days: int, category: str = "all") -> dict:
        """删除修改时间超过 days 天的缓存文件。

        Args:
            days: 0=清空全部, >0=清理N天前
            category: "api" | "signals" | "snapshots" | "checkpoints" | "all"

        Returns:
            {"deleted_files": int, "freed_mb": float, "by_category": {...}}
        """
        ...

    def clear(self, category: str) -> dict:
        """清空指定类别。

        Args:
            category: "api" | "signals" | "snapshots" | "checkpoints" | "all"

        Returns:
            {"deleted_files": int, "freed_mb": float}
        """
        ...

    def details(self, category: str, page: int = 1, page_size: int = 20) -> dict:
        """分页列出缓存条目。

        Returns:
            {"total": int, "page": int, "entries": [
                {"path": str, "size_kb": float, "modified": str}
            ]}
        """
        ...

    # --- 内部 ---
    def _walk_dir(self, root: Path, pattern: str = "*") -> list[Path]: ...
    def _dir_stats(self, root: Path) -> tuple[int, float]: ...      # (count, MB)
    def _is_older_than(self, path: Path, days: int) -> bool: ...
```

**实现要点**:
- `stats()` 对每类目录执行 `_walk_dir()` 计算文件数和总大小
- `cleanup(days, category)` 用 `path.stat().st_mtime` 判断文件年龄，并只清理指定类别
- `clear("checkpoints")` 调用 `clear_all_checkpoints(config["data_cache_dir"])` 复用现有函数
- `details()` 仅列出文件名+大小+修改时间，不打开文件内容
- `clear("signals")` 删除 `backtest_cache/` 整个目录树
- `clear("api")` 保留 `shared_snapshots/` 与 `checkpoints/` 子目录，仅删除 API cache 根目录下其他文件

#### `cli/commands/cache.py`

```python
cache_app = typer.Typer(help="Cache management utilities.")

@cache_app.command("stats")
def cache_stats(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """Show cache statistics across all categories."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    mgr = CacheManager(config)
    s = mgr.stats()
    # Rich Table: Category | Files | Size (MB)
    # 总计行
    ...

@cache_app.command("cleanup")
def cache_cleanup(
    days: int = typer.Option(7, "--days", min=0,
        help="Remove entries older than N days. 0=clear all."),
    category: Optional[str] = typer.Option(None, "--type",
        help="api|signals|snapshots|checkpoints. Default: all."),
):
    """Remove old cache entries."""
    ...

@cache_app.command("clear")
def cache_clear(
    category: str = typer.Option("all", "--type",
        help="api|signals|snapshots|checkpoints|all"),
    confirm: bool = typer.Option(False, "--yes", "-y",
        help="Skip confirmation prompt."),
):
    """Clear all entries in a cache category."""
    ...
```

### 修改文件

#### `etfagents/default_config.py`

新增缓存TTL配置键：

```python
"snapshot_max_age_days": 30,          # 快照缓存最大保留天数
"backtest_cache_max_age_days": 90,    # 回测信号缓存最大保留天数
"checkpoint_max_age_days": 30,        # checkpoint最大保留天数
```

#### `cli/main.py`

在 `memory_app` 注册之后新增:

```python
from cli.commands.cache import cache_app
app.add_typer(cache_app, name="cache")
```

### 不在 P1 范围

| 功能 | 原因 |
|------|------|
| `route_to_vendor` 响应缓存 | 影响面大（所有数据请求），需独立设计和测试 |
| `_cached_pro_client` 线程安全 | 当前单进程顺序执行，不紧急 |
| `route_to_vendor` 重试/断路器 | 接口层改动较大，需与 vendor fallback 链协调 |
| Tushare 限流 | 涉及外部API配额，需用户配置 tier |
| Checkpointer 孤儿.db检测 | 功能完善性改进，非正确性问题 |

### 验证标准

- [ ] `etfagents cache stats` 正确显示四类缓存的文件数和大小
- [ ] `etfagents cache stats --json` 输出合法JSON
- [ ] `etfagents cache cleanup --days 0` 清空后 `stats` 显示全部归零
- [ ] `etfagents cache clear --type signals` 仅清空回测信号缓存
- [ ] `etfagents cache clear --type all` 需要确认(除非 `--yes`)
- [ ] 缓存目录不存在时不报错, 返回零值
- [ ] F1: 中途杀进程不会产生截断JSON文件
- [ ] F2: 损坏快照文件被自动重命名为 `.corrupt`，下次调用重建
- [ ] F3: `coverage_days` 为非int类型时不抛异常，返回False触发重建

---

## P2: 自选股(ETF池)管理

### 目标

SQLite持久化自选股，支持分组/标签，与candidate pool分析打通。

### 数据库设计

文件: `~/.etfagents/watchlist.db`

```sql
CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker      TEXT    NOT NULL,
    name        TEXT    NOT NULL DEFAULT '',
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    tags        TEXT    DEFAULT '[]',           -- JSON array of strings
    notes       TEXT    DEFAULT '',
    added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, group_id)              -- 同一ticker可在多个分组
);

CREATE INDEX IF NOT EXISTS idx_watchlist_group ON watchlist(group_id);

-- 初始默认分组
INSERT OR IGNORE INTO groups (id, name, sort_order) VALUES (1, 'default', 0);
```

**设计决策**:
- `PRIMARY KEY (ticker, group_id)` 允许同一ETF在多个分组(如"宽基"和"大盘")
- `tags` 用JSON数组存储，避免额外tag表(标签数量有限)
- `sort_order` 支持分组排序
- 不做 `alert_price_high/low`: CLI无后台推送，价格提醒无意义
- `ON DELETE CASCADE`: 删分组时自动删其下条目

### 新增文件

#### `etfagents/watchlist.py`

```python
"""SQLite-backed ETF watchlist management."""

class WatchlistManager:
    DB_PATH = Path(os.path.expanduser("~/.etfagents/watchlist.db"))

    def __init__(self, db_path: Path | None = None):
        self._db = db_path or self.DB_PATH
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """建表+默认分组(如不存在)。"""

    def _connect(self) -> sqlite3.Connection:
        """返回已设置 row_factory=sqlite3.Row 的连接。"""

    # ---- 分组操作 ----
    def list_groups(self) -> list[dict]:
        """[{"id": int, "name": str, "count": int, "sort_order": int}]"""

    def add_group(self, name: str, sort_order: int | None = None) -> int:
        """新增分组, 返回group_id。重复name抛ValueError。"""

    def remove_group(self, name: str) -> int:
        """删除分组及其下条目(CASCADE)。返回受影响行数。"""

    def rename_group(self, old_name: str, new_name: str) -> None:
        """重命名分组。"""

    # ---- 自选股操作 ----
    def add(self, ticker: str, group: str = "default",
            tags: list[str] | None = None, notes: str = "",
            name: str = "") -> None:
        """添加自选股。已存在则更新tags/notes/name。"""

    def remove(self, ticker: str, group: str | None = None) -> int:
        """移除。group=None时从所有分组移除。返回删除行数。"""

    def list_tickers(self, group: str | None = None,
                     tags: list[str] | None = None) -> list[dict]:
        """[{"ticker": str, "name": str, "group": str,
           "tags": list, "notes": str, "added_at": str}]"""

    def get_tickers_for_analysis(self, group: str) -> list[str]:
        """指定分组的ticker列表, 用于candidate pool分析。"""

    def update(self, ticker: str, group: str = "default",
               tags: list[str] | None = None,
               notes: str | None = None) -> None:
        """更新tags/notes(仅更新非None字段)。"""

    def all_tags(self) -> list[str]:
        """所有使用中的标签(去重排序)。"""

    # ---- 内部 ----
    def _resolve_group_id(self, name: str) -> int | None: ...
    def _auto_fill_name(self, ticker: str) -> str:
        """尝试从route_to_vendor("get_etf_info")获取ETF名称, 失败则返回ticker。"""
```

`_auto_fill_name()` 实现:
- 调用 `route_to_vendor("get_etf_info", ticker, curr_date)` 获取CSV
- 解析第一行的基金名称字段
- 失败时返回ticker自身
- **重要**: 需在调用前通过 `set_config(copy.deepcopy(DEFAULT_CONFIG))` 初始化dataflows配置。
  若在 `watchlist add` CLI命令中调用(发生在任何 `analyze` 之前), 命令handler需自行初始化config,
  否则 `route_to_vendor` 会因为config未设置而失败

#### `cli/commands/watchlist.py`

```python
watchlist_app = typer.Typer(help="ETF watchlist management.")

@watchlist_app.command("add")
def watchlist_add(
    tickers: str = typer.Argument(..., help="Comma-separated ETF tickers."),
    group: str = typer.Option("default", "--group", "-g", help="Group name."),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags."),
    notes: str = typer.Option("", "--notes", "-n", help="Notes."),
):
    """Add ETF(s) to watchlist."""

@watchlist_app.command("remove")
def watchlist_remove(
    tickers: str = typer.Argument(..., help="Comma-separated ETF tickers."),
    group: Optional[str] = typer.Option(None, "--group", "-g",
        help="Remove from specific group only. Default: all groups."),
):
    """Remove ETF(s) from watchlist."""

@watchlist_app.command("list")
def watchlist_list(
    group: Optional[str] = typer.Option(None, "--group", "-g",
        help="Filter by group."),
    tags: Optional[str] = typer.Option(None, "--tags", "-t",
        help="Filter by tags (comma-separated, any match)."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """List watchlist entries. Rich Table: Ticker | Name | Group | Tags | Added"""

@watchlist_app.command("group")
def watchlist_group_cmd(
    action: str = typer.Argument(..., help="add|remove|rename|list"),
    name: str = typer.Argument("", help="Group name (empty for list)."),
    new_name: Optional[str] = typer.Option(None, "--rename",
        help="New name for rename action."),
):
    """Manage watchlist groups."""
```

### 修改文件

#### `cli/main.py`

1. 注册子命令:

```python
from cli.commands.watchlist import watchlist_app
app.add_typer(watchlist_app, name="watchlist")
```

2. `analyze` 命令新增 `--watchlist` 选项:

在 `analyze()` 函数签名中新增:
```python
watchlist: Optional[str] = typer.Option(None, "--watchlist", "-w",
    help="Analyze ETFs from a watchlist group instead of manual input."),
```

在 `run_analysis()` 开头新增逻辑:
```python
if watchlist:
    from etfagents.watchlist import WatchlistManager
    wl = WatchlistManager()
    tickers_from_wl = wl.get_tickers_for_analysis(watchlist)
    if not tickers_from_wl:
        console.print(f"[red]Watchlist group '{watchlist}' is empty.[/red]")
        raise typer.Exit(code=1)
    # 跳过手动ticker输入步骤, 直接用tickers_from_wl
    selections = get_user_selections(preselected_tickers=tickers_from_wl)
    ...
```

需修改 `get_user_selections()` 函数签名, 新增 `preselected_tickers: list[str] | None = None` 参数:
- 若 `preselected_tickers` 非空, 跳过Step 1(ticker输入)
- 若 `len(preselected_tickers) > 1`, 直接设置 `analysis_mode = "candidate_pool"`

3. `backtest` 命令同理新增 `--watchlist` 选项。当前 `--tickers` 为必需参数(`typer.Option(..., ...)`),
   需改为 `tickers: Optional[str] = typer.Option(None, "--tickers")` 使 `--tickers` 可选,
   并在函数体内验证 `--tickers` 与 `--watchlist` 互斥(二者皆无或皆有均报错)。

### 验证标准

- [ ] `etfagents watchlist add 510300.SH --group 宽基` 成功, 自动获取ETF名称
- [ ] `etfagents watchlist add 510300.SH,159915.SZ --group 宽基` 批量添加
- [ ] `etfagents watchlist list` 显示所有自选股(Rich Table)
- [ ] `etfagents watchlist list --group 宽基` 仅显示该分组
- [ ] `etfagents watchlist list --tags 大盘,蓝筹` 按标签过滤
- [ ] `etfagents watchlist remove 510300.SH` 从所有分组移除
- [ ] `etfagents watchlist remove 510300.SH --group 宽基` 仅从该分组移除
- [ ] `etfagents watchlist group add 行业` 新增分组
- [ ] `etfagents watchlist group list` 显示分组列表及计数
- [ ] `etfagents analyze --watchlist 宽基` 读取分组tickers启动分析
- [ ] `etfagents backtest --watchlist 宽基 --start-date ...` 同理
- [ ] `--watchlist` 与手动 `--tickers` 互斥, 同时指定报错

---

## P3: 智能模型选择

### 目标

为已知模型添加能力元数据，根据研究深度自动推荐quick+deep模型对。

### 数据模型

#### 扩展 `etfagents/llm_clients/model_catalog.py`

**关于 provider 名称**: `MODEL_OPTIONS` 当前共有 9 个 provider key，必须使用以下规范化字符串作为 `recommend_models(depth, provider)` 的 `provider` 参数：

| Provider key | 说明 |
|--------------|------|
| `openai` | OpenAI GPT 系列 |
| `anthropic` | Anthropic Claude 系列（**不是** `"claude"`） |
| `google` | Google Gemini 系列（**不是** `"gemini"`） |
| `xai` | xAI Grok 系列（**不是** `"grok"`） |
| `minimax` | MiniMax 系列（小写，**不是** `"MiniMax"`） |
| `deepseek` | DeepSeek 系列 |
| `openrouter` | OpenRouter（动态模型，运行时获取，不在 MODEL_CAPABILITIES 中） |
| `vllm` | 本地 vLLM 部署（自定义模型，跳过推荐） |
| `ollama` | 本地 Ollama / llama.cpp（自定义模型，跳过推荐） |

新增能力常量:

```python
from enum import IntEnum
from typing import Literal

class CapabilityLevel(IntEnum):
    BASIC = 1
    STANDARD = 2
    ADVANCED = 3
    PROFESSIONAL = 4
    FLAGSHIP = 5

ModelFeature = Literal[
    "tool_calling", "long_context", "reasoning",
    "fast_response", "cost_effective",
]

MODEL_CAPABILITIES: dict[str, dict] = {
    "gpt-5.4-mini": {
        "level": 2, "roles": ["quick", "deep"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 2,
    },
    "gpt-5.4-nano": {
        "level": 1, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 1,
    },
    "gpt-5.4": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 3, "cost": 3, "quality": 4,
    },
    "gpt-5.4-pro": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 1, "cost": 1, "quality": 5,
    },
    "claude-haiku-4-5": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 4, "quality": 2,
    },
    "claude-sonnet-4-5": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 3, "cost": 3, "quality": 4,
    },
    "claude-sonnet-4-6": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 4, "cost": 3, "quality": 4,
    },
    "claude-opus-4-5": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 1, "cost": 1, "quality": 5,
    },
    "claude-opus-4-6": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 2, "cost": 1, "quality": 5,
    },
    "gemini-2.5-flash": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 2,
    },
    "gemini-2.5-pro": {
        "level": 4, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 2, "cost": 2, "quality": 4,
    },
    "gemini-3-flash-preview": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 4, "cost": 4, "quality": 3,
    },
    "deepseek-v4-flash": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 4, "cost": 5, "quality": 2,
    },
    "deepseek-chat": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 3,
    },
    "deepseek-reasoner": {
        "level": 4, "roles": ["deep"],
        "features": ["reasoning", "long_context"],
        "speed": 1, "cost": 3, "quality": 4,
    },
    "grok-4-fast-non-reasoning": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 4, "cost": 3, "quality": 2,
    },
    "grok-4-1-fast-reasoning": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "reasoning"],
        "speed": 3, "cost": 2, "quality": 3,
    },
    "MiniMax-M2.7-highspeed": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 1,
    },
    "MiniMax-M2.7": {
        "level": 3, "roles": ["deep"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 3,
    },
}

# 约束: MODEL_CAPABILITIES 应覆盖 MODEL_OPTIONS 中所有云端 provider (openai/anthropic/google/xai/minimax/deepseek)
# 的非 "custom" 静态模型ID。上方示例为最常用模型的初始集，正式实现时需补齐当前 MODEL_OPTIONS 中尚未列出的
# 模型条目（如 gpt-4.1、gpt-5.2、gemini-3.1-flash-lite-preview、gemini-2.5-flash-lite、gemini-3.1-pro-preview、
# grok-4-1-fast-non-reasoning、grok-4-0709、grok-4-fast-reasoning、MiniMax-M2.5-highspeed、MiniMax-M2.5、
# MiniMax-M2.1、MiniMax-M2、deepseek-v4-pro 等），并由 tests/test_model_recommend.py 中的覆盖测试锁定。
# openrouter 动态模型与 vllm/ollama 本地自定义模型显式跳过推荐，但不能导致手动选择失效。

RESEARCH_DEPTH_REQUIREMENTS: dict[str, dict] = {
    "快速": {"min_level": 1, "quick_min": 1, "deep_min": 1,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 0, "risk_rounds": 0},
    "基础": {"min_level": 1, "quick_min": 1, "deep_min": 2,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 1, "risk_rounds": 0},
    "标准": {"min_level": 2, "quick_min": 2, "deep_min": 3,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 1, "risk_rounds": 1},
    "深度": {"min_level": 3, "quick_min": 2, "deep_min": 4,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 2, "risk_rounds": 2},
    "全面": {"min_level": 3, "quick_min": 3, "deep_min": 5,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling", "reasoning"],
             "debate_rounds": 3, "risk_rounds": 3},
}
```

新增推荐函数:

```python
def recommend_models(
    depth: str,
    provider: str | None = None,
) -> dict:
    """根据研究深度推荐最优quick+deep模型对。

    算法:
    1. 从 MODEL_CAPABILITIES 筛选:
       - quick候选: "quick" in roles 且 level >= depth_req["quick_min"]
       - deep候选:  "deep" in roles 且 level >= depth_req["deep_min"]
       - quick候选必须包含 depth_req["quick_required_features"] 全部feature
       - deep候选必须包含 depth_req["deep_required_features"] 全部feature
    2. 若指定provider, 仅保留 MODEL_OPTIONS[provider] 中出现的模型；
       若provider=None, 跨全部provider搜索(按模型自身能力排序, 不限制provider)
    3. quick候选排序: (level DESC, cost DESC, speed DESC) → 取第一个
    4. deep候选排序:  (level DESC, quality DESC, cost DESC) → 取第一个
    5. 若provider=None且候选为空, 返回 None 表示无可用模型

    Returns:
        {
            "quick_model": str | None,
            "deep_model": str | None,
            "quick_reason": str,
            "deep_reason": str,
            "depth": str,
        }
    """

def get_depth_config(depth: str) -> dict | None:
    """返回深度对应的debate/risk轮次配置。"""
    return RESEARCH_DEPTH_REQUIREMENTS.get(depth)
```

### 修改文件

#### `etfagents/llm_clients/model_catalog.py`

- 新增 `CapabilityLevel`, `MODEL_CAPABILITIES`, `RESEARCH_DEPTH_REQUIREMENTS`
- 新增 `recommend_models()`, `get_depth_config()`
- **不修改**现有 `get_model_options()`, `get_known_models()`, `MODEL_OPTIONS`
- 新增测试约束：`MODEL_CAPABILITIES` 应覆盖当前 `MODEL_OPTIONS` 中所有云端 provider (openai/anthropic/google/xai/minimax/deepseek) 的非 `custom` 静态模型ID；动态 provider (`openrouter`) 与本地自定义模型 (`vllm` / `ollama`) 显式排除推荐

#### `etfagents/default_config.py`

新增键:

```python
"research_depth_name": "标准",     # 快速|基础|标准|深度|全面
```

**注意**: `research_depth_name` 是用户可见的深度名称，`max_debate_rounds`/`max_risk_discuss_rounds` 是具体轮数。
`get_depth_config(depth)` 将深度名称映射为轮数，在交互式 `run_analysis()` 构建config时调用。
旧字段 `max_debate_rounds`/`max_risk_discuss_rounds` 保留在 `DEFAULT_CONFIG` 中供向后兼容；非交互 `backtest --research-depth` 继续保持现有 int 轮数语义，暂不改成中文深度名，避免破坏脚本。
交互式配置构建时必须用 `get_depth_config()` 的返回值覆盖这两个字段，避免新旧值冲突。

#### `cli/utils.py`

1. 新增研究深度选择步骤(插在Step 2日期选择之后):

```python
def select_research_depth_name() -> str:
    """交互式选择研究深度。"""
    depths = list(RESEARCH_DEPTH_REQUIREMENTS.keys())
    return questionary.select(
        "Research depth / 研究深度:",
        choices=[
            {"name": f"{d} ({_depth_desc(d)})", "value": d}
            for d in depths
        ],
        default="标准",
    ).ask()

def _depth_desc(depth: str) -> str:
    req = RESEARCH_DEPTH_REQUIREMENTS[depth]
    return f"debate×{req['debate_rounds']}, risk×{req['risk_rounds']}"
```

注意：`cli/utils.py` 中已有 `select_research_depth() -> int`，用于旧的轮数式研究深度选择。新增函数必须命名为 `select_research_depth_name()`，不得覆盖或改写旧函数；`cli/utils.py` 也不应调用 `cli/main.py` 中的 `_localize_cli_label()` 私有函数，避免循环导入。这里使用双语固定提示或在 `cli/utils.py` 内部新增独立的轻量标签函数。

2. 修改模型选择步骤(Step 6-7), 在手动选择前增加"智能推荐"选项:

```python
def select_model_strategy(depth: str, provider: str) -> dict:
    """Step: 选择模型策略。

    选项:
    1. 智能推荐 (N深度)  ← 默认
    2. 手动选择
    """
    choice = questionary.select(...).ask()
    if choice == "智能推荐":
        rec = recommend_models(depth, provider)
        confirm = questionary.confirm("Accept recommendation?").ask()
        if confirm:
            return {"quick": rec["quick_model"], "deep": rec["deep_model"]}
    # fallback to existing manual selection
    return manual_model_selection(provider)
```

3. 修改 `get_user_selections()`, 将 `research_depth_name` 和模型策略串联起来:

```python
# 新增步骤
selections["research_depth_name"] = select_research_depth_name()
# 覆盖debate/risk轮次
depth_cfg = get_depth_config(selections["research_depth_name"])
config["max_debate_rounds"] = depth_cfg["debate_rounds"]
config["max_risk_discuss_rounds"] = depth_cfg["risk_rounds"]
# 模型选择改为策略式
models = select_model_strategy(selections["research_depth_name"], selected_llm_provider)
config["quick_think_llm"] = models["quick"]
config["deep_think_llm"] = models["deep"]
```

### 验证标准

- [ ] `recommend_models("标准", "openai")` 返回合法quick+deep模型对
- [ ] `recommend_models("全面", "anthropic")` 的 deep_model 优先推荐含reasoning能力的模型；quick_model 仍只要求 tool_calling
- [ ] 推荐的模型名存在于 `MODEL_OPTIONS["openai"]` / `MODEL_OPTIONS["anthropic"]` 中（使用规范 provider key，不是 `"claude"` / `"gemini"` / `"grok"` / `"MiniMax"` 等别名）
- [ ] 对 `provider="openrouter"`、`provider="vllm"`、`provider="ollama"` 调用应显式跳过推荐（返回 None 或保留手动选择路径）
- [ ] CLI选择"智能推荐"后 quick_think_llm/deep_think_llm 自动填充
- [ ] 研究深度"快速"设置 debate_rounds=0, risk_rounds=0
- [ ] 研究深度"全面"设置 debate_rounds=3, risk_rounds=3
- [ ] 手动选择路径不受影响(向后兼容)
- [ ] 未指定provider时, 从所有provider的模型中推荐

---

## P4: ETF详情页

### 目标

CLI下 `etfagents detail <ticker>` 展示ETF全景信息面板。

### 新增文件

#### `etfagents/detail.py`

```python
"""ETF detail data aggregation."""

def get_etf_detail(ticker: str, curr_date: str | None = None) -> dict:
    """聚合ETF详情数据。

    数据源: 全部通过现有 route_to_vendor() 获取
    任一接口失败不阻塞其他, 对应字段返回None

    Returns:
        {
            "ticker": str,
            "name": str,
            "market": str,

            # 行情
            "latest_date": str,
            "open": float, "high": float, "low": float,
            "close": float,
            "pct_chg": float | None,
            "volume": float,
            "amount": float,

            # 净值
            "unit_nav": float | None,
            "nav_date": str | None,
            "premium_discount_bps": float | None,

            # 份额
            "fund_share": float | None,
            "share_change_pct": float | None,

            # 持仓Top-10
            "holdings": [
                {"code": str, "name": str, "weight_pct": float}
            ] | None,

            # 基本信息
            "fund_type": str | None,
            "establish_date": str | None,
            "manager": str | None,
            "benchmark": str | None,
        }
    """
    # 实现: 依次调用 route_to_vendor
    # 1. get_etf_price_data → OHLCV 最新一行
    # 2. get_etf_nav → NAV 最新一行
    # 3. get_etf_info → 基金档案
    # 4. get_etf_holdings → 持仓
    # 5. get_etf_share → 份额变动
    ...

def get_etf_history_reports(ticker: str, results_dir: str) -> list[dict]:
    """扫描results/目录获取该ticker的历史分析报告列表。

    Returns:
        [{"date": str, "path": str, "rating": str | None, "size_kb": float}]
    """
    ...
```

数据解析: `route_to_vendor()` 返回 `str`(CSV或Markdown)。实现需:
- CSV: `io.StringIO` + `csv.DictReader`, 取最新(最后一行)或满足日期的行
- 持仓CSV: 取前10行, 解析 code/name/weight 列
- 每个接口单独 try/except, 失败字段为 None
- vendor 函数导入方式必须与测试 patch 路径一致：推荐在 `etfagents/detail.py` 中 `from etfagents.dataflows.interface import route_to_vendor`，测试 patch `etfagents.detail.route_to_vendor`

`get_etf_history_reports()` 实现:
- 扫描 `Path(results_dir)/*/*{ticker}*/complete_report.md` (覆盖单ticker分析目录
  `<date>/<ticker>/complete_report.md` 和候选池目录 `_candidate_pools/<slug>/<date>/<ticker>/complete_report.md`)
- 读取文件的修改时间和大小
- 尝试从报告内容中提取rating(复用公共 `etfagents.agents.utils.rating.parse_rating()`，不要依赖 backtest 模块里的私有解析函数)

#### `cli/commands/detail.py`

```python
def detail(
    ticker: str = typer.Argument(..., help="ETF ticker, e.g. 510300.SH"),
    date: Optional[str] = typer.Option(None, "--date", "-d",
        help="As-of date (YYYY-MM-DD). Default: today."),
):
    """Show comprehensive ETF detail panel."""
```

该模块只导出普通 `detail()` 函数，不直接引用 `app` 或使用 `@app.command()`；由 `cli/main.py` 统一注册为顶级命令。

Rich Layout设计:

```
┌──────────────────────────────────────────────────────────┐
│ 510300.SH  沪深300ETF                    a_share          │
│ 2026-05-20  收盘: 4.123  涨跌: +1.25%                    │
├──────────────────────┬───────────────────────────────────┤
│ 行情与净值            │ 基金档案                           │
│ 成交量: 1.23亿        │ 类型: 指数型                      │
│ 成交额: 5.07亿        │ 成立日: 2012-01-01                │
│ 单位净值: 4.128      │ 基金经理: 张三                     │
│ 溢价率: -0.12%       │ 业绩基准: 沪深300指数              │
│ 份额: 125.3亿份      │                                   │
│ 份额变化: +2.3%      │                                   │
├──────────────────────┴───────────────────────────────────┤
│ Top-10 持仓                                              │
│ Code       | Name         | Weight(%)                     │
│ 600519.SH  | 贵州茅台      | 5.23                          │
│ ...                                                      │
├──────────────────────────────────────────────────────────┤
│ 历史分析报告                                              │
│ Date        | Rating   | Size                            │
│ 2026-05-18  | HOLD     | 12.3 KB                         │
│ ...                                                      │
│ 暂无分析记录 (若不存在)                                    │
└──────────────────────────────────────────────────────────┘
```

### 修改文件

#### `cli/main.py`

```python
from cli.commands.detail import detail as detail_command
app.command(name="detail")(detail_command)
```

注册为顶级命令, 与 `analyze`/`backtest` 同级(非子命令组)。

### 验证标准

- [ ] `etfagents detail 510300.SH` 显示完整面板(行情+净值+持仓+报告)
- [ ] 非A股ticker优雅降级, 仅显示可获取的字段
- [ ] 不存在的ticker给出明确错误 `Tushare API returned empty`
- [ ] `--date 2026-01-15` 指定历史日期时获取对应数据
- [ ] 无历史报告时不报错, "暂无分析记录"
- [ ] 面板宽度适配终端, 不截断

---

## P5: 批量分析增强

### 目标

保持顺序执行，增强candidate pool的进度可视化和结果展示。

**注意: 不实现多进程并发。** 保持现有顺序分析逻辑不变。

### 范围

| 功能 | 是否实现 | 说明 |
|------|---------|------|
| 批量摘要对比表 | ✅ | 多ticker分析结果并排比较 |
| 进度可视化增强 | ✅ | 每个ticker分析阶段的文本提示 |
| 多进程并发 | ❌ | 不实现, 保持顺序执行 |
| BatchProgressTracker | ❌ | 不需要(无并发) |

### 修改文件

#### `cli/main.py`

candidate pool 流程增强:

1. 分析开始前显示ticker列表和预估顺序:

```
╭─ Candidate Pool Analysis ────────────────────╮
│ Tickers: 510300.SH, 159915.SZ, 510500.SH    │
│ Date: 2026-05-20                              │
│ Analysts: Market, Macro, Holdings, ...        │
│ Progress: sequential (1/3)                    │
╰───────────────────────────────────────────────╯

[1/3] Analyzing 510300.SH ─ [analysts] → [debate] → [risk] → [DONE] (2m34s)
[2/3] Analyzing 159915.SZ ─ [analysts]... (running)
```

2. 完成后新增批量摘要对比表:

```
╭─ Candidate Pool Summary ───────────────────────────────────╮
│ Ticker       | Rating      | Weight | Time   │
│ 510300.SH    | BUY         | 35%    | 2m34s  │
│ 159915.SZ    | HOLD        | 25%    | 1m58s  │
│ 510500.SH    | OVERWEIGHT  | 40%    | 3m12s  │
╰────────────────────────────────────────────────────────────╯
```

#### `etfagents/default_config.py`

不新增键（无并发相关配置）。

### 验证标准

- [ ] 顺序分析3个ticker, 每个完成时显示 `[N/3] Analyzing TICKER → DONE`
- [ ] 批量摘要对比表正确显示rating/weight/time
- [ ] 某ticker分析失败时显示 `FAILED` + 错误原因, 其他ticker继续
- [ ] 与当前行为完全向后兼容

---

## P6: 模拟交易系统

### 目标

CLI纸盘交易，多用户支持，买入/卖出/持仓/盈亏追踪，与分析报告联动。

### 与 Backtest 模块的关系

```
                    ┌─→ signals.py → Backtrader引擎 → 历史回放
分析输出 AgentState ─┤
                    └─→ signals.py → 信号→订单建议 → Paper Trading引擎 → 即时执行
```

- Paper Trading 和 Backtest 是**平行的两个执行通道**
- 共享信号提取层 (`backtest/signals.py`)
- Paper trading 不会合并到 Backtrader 引擎中
- Paper trading 有自己的轻量 SQLite 执行引擎

### 数据库设计

文件: `~/.etfagents/paper_trading.db`

```sql
-- 用户
CREATE TABLE IF NOT EXISTS users (
    username        TEXT    PRIMARY KEY,
    password_hash   TEXT    NOT NULL DEFAULT '', -- bcrypt; default用户为空=免密
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO users (username) VALUES ('default');

-- 账户（每用户一个）
CREATE TABLE IF NOT EXISTS account (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(username),
    cash            REAL    NOT NULL DEFAULT 1000000.0,
    realized_pnl    REAL    NOT NULL DEFAULT 0.0,
    total_commission REAL   NOT NULL DEFAULT 0.0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id)
);

-- 持仓
CREATE TABLE IF NOT EXISTS positions (
    user_id         TEXT    NOT NULL REFERENCES users(username),
    ticker          TEXT    NOT NULL,
    name            TEXT    NOT NULL DEFAULT '',
    quantity        INTEGER NOT NULL DEFAULT 0,
    available_qty   INTEGER NOT NULL DEFAULT 0,   -- T+1: 可卖数量
    avg_cost        REAL    NOT NULL DEFAULT 0.0,
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, ticker)
);

-- 成交记录
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL REFERENCES users(username),
    ticker          TEXT    NOT NULL,
    name            TEXT    NOT NULL DEFAULT '',
    side            TEXT    NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity        INTEGER NOT NULL,
    price           REAL    NOT NULL,
    amount          REAL    NOT NULL,              -- price * quantity
    commission      REAL    NOT NULL DEFAULT 0.0,
    pnl             REAL    DEFAULT NULL,          -- 仅sell有值
    analysis_id     TEXT    DEFAULT NULL,          -- 关联分析报告目录名
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(user_id, ticker);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(user_id, created_at DESC);
```

**设计决策**:
- 所有业务表加 `user_id` 列，同一DB文件内按用户隔离
- `default` 用户无密码自动登录
- `analysis_id` 存报告目录路径，支持从分析报告直接关联交易
- `pnl` 仅sell成交时计算: `(sell_price - avg_cost) * quantity - commission`
- 无order表: 仅支持市价即时成交，无挂单/撤单

### 认证机制

#### Session 文件

`~/.etfagents/paper_session.json`:

```json
{"username": "alice", "login_at": "2026-05-20T10:30:00"}
```

#### 认证流程

| 步骤 | 命令 | 说明 |
|------|------|------|
| 注册 | `etfagents paper register <username>` | 输入密码2次 → bcrypt存哈希到 users 表 |
| 登录 | `etfagents paper login <username>` | 输入密码 → 验证 → 写 session 文件 |
| 注销 | `etfagents paper logout` | 删除 session 文件 |
| 自动 | (无session时) | 使用 `default` 用户的账户（免密） |
| 切换 | `etfagents paper --user alice buy ...` | 需要已 login 为该用户 |

**密码处理**: 使用 `bcrypt>=4.0` 库（加入 `pyproject.toml` 依赖），`default` 用户的 `password_hash=''` 表示免密自动登录。
Session 文件写入必须使用 tempfile + `os.replace()` 原子替换，避免两个进程同时登录时产生截断 JSON。

**Engine 获取当前用户逻辑**:

```python
def _get_current_user(self) -> str:
    """读取session文件获取当前用户，无session返回'default'。"""
    session_path = Path(os.path.expanduser("~/.etfagents/paper_session.json"))
    if session_path.exists():
        data = json.loads(session_path.read_text())
        return data["username"]
    return "default"
```

### 交易规则

文件: `etfagents/paper_trading/rules.py`

```python
"""A-share ETF trading rules."""

COMMISSION_RATE = 0.00025      # 佣金万2.5
MIN_COMMISSION = 5.0           # 最低佣金5元
STAMP_DUTY_RATE = 0.0          # ETF免印花税
LOT_SIZE = 100                  # 最小交易单位100份

def calc_commission(amount: float) -> float:
    """max(amount * 0.00025, 5.0)"""

def calc_stamp_duty(amount: float) -> float:
    """ETF免印花税, 返回0.0"""

def validate_quantity(quantity: int) -> None:
    """必须为100的整数倍, 否则抛ValueError"""

def get_t1_available(quantity: int, today_bought: int) -> int:
    """T+1: 可卖数量 = 总持仓 - 当日买入量"""

def estimate_trade_cost(price: float, quantity: int, side: str) -> dict:
    """预估交易成本。"""
```

### 新增文件

#### `etfagents/paper_trading/__init__.py`

空文件, 导出 `PaperTradingEngine`, `suggest_order_from_signal`。

#### `etfagents/paper_trading/engine.py`

```python
class PaperTradingEngine:
    DB_PATH = Path(os.path.expanduser("~/.etfagents/paper_trading.db"))
    SESSION_PATH = Path(os.path.expanduser("~/.etfagents/paper_session.json"))

    def __init__(self, db_path: Path | None = None, config: dict | None = None):
        self._db = db_path or self.DB_PATH
        self._config = config or copy.deepcopy(DEFAULT_CONFIG)
        self._ensure_schema()
        self._ensure_session_consistency()

    # ---- 认证 ----
    def register(self, username: str, password: str) -> None:
        """注册新用户。内部 `import bcrypt` (延迟导入避免default用户无bcrypt时报错)。"""

    def login(self, username: str, password: str) -> bool:
        """验证密码，写入session文件。内部 `import bcrypt`。返回True/False。"""

    def logout(self) -> None:
        """删除session文件。"""

    def _get_current_user(self) -> str:
        """读取session → 当前用户; 无session → 'default'。"""

    def _verify_password(self, username: str, password: str) -> bool: ...

    # ---- 账户 ----
    def get_account(self, user_id: str | None = None) -> dict:
        """{"cash", "realized_pnl", "total_commission",
           "market_value", "total_assets", "unrealized_pnl",
           "updated_at"}"""

    def reset_account(self, user_id: str | None = None,
                      initial_cash: float = 1_000_000.0) -> None:
        """清空该用户所有数据，重建初始账户。"""

    # ---- 交易 ----
    def buy(self, ticker: str, quantity: int, user_id: str | None = None,
            analysis_id: str | None = None) -> dict:
        """市价买入。

        流程:
        1. validate_quantity(quantity)
        2. _get_current_price(ticker)
        3. calc_commission(amount)
        4. 检查 cash >= amount + commission
        5. UPDATE positions: avg_cost = weighted_avg, quantity += qty
        6. UPDATE account: cash -= (amount + commission)
        7. INSERT trades (available_qty不变 → T+1)

        Returns: {"ticker", "side", "quantity", "price",
                  "amount", "commission", "total_cost"}
        """

    def sell(self, ticker: str, quantity: int, user_id: str | None = None,
             analysis_id: str | None = None) -> dict:
        """市价卖出。

        流程:
        1. validate_quantity(quantity)
        2. 检查 available_qty >= quantity
        3. _get_current_price(ticker)
        4. calc_commission(amount)
        5. PnL = (price - avg_cost) * quantity - commission
        6. UPDATE positions: quantity -= qty
        7. 若 quantity=0 → DELETE positions
        8. UPDATE account: cash += amount - commission, realized_pnl += pnl
        9. INSERT trades

        Returns: {..., "pnl": float}
        """

    # ---- 查询 ----
    def get_positions(self, user_id: str | None = None) -> list[dict]:
        """[{"ticker", "name", "quantity", "available_qty",
           "avg_cost", "current_price", "market_value",
           "unrealized_pnl", "pnl_pct"}]"""

    def get_trades(self, user_id: str | None = None, limit: int = 50) -> list[dict]:
        """最近N笔成交记录。"""

    # ---- 信号联动 ----
    def suggest_order_from_signal(self, ticker: str, state: dict,
                                  user_id: str | None = None) -> dict | None:
        """从分析结果提取信号，生成下单建议。

        复用 backtest/signals.py 的 build_state_backtest_signal()
        将 target_weight 换算为具体股数。

        Returns:
            {"ticker": str, "side": "buy"|"sell", "quantity": int, "price": float,
             "target_weight_pct": float, "rating": str}
            或 None (无需调整)
        """
        from etfagents.backtest.signals import BacktestSignal, build_state_backtest_signal
        signal_dict = build_state_backtest_signal(state)
        signal = BacktestSignal(**signal_dict) if signal_dict else None
        if not signal or not signal.target_weight_pct:
            return None

        uid = user_id or self._get_current_user()
        account = self.get_account(uid)
        price = self._get_current_price(ticker)
        target_value = account["total_assets"] * signal.target_weight_pct / 100
        current_value = self._position_market_value(ticker, uid)
        delta_value = target_value - current_value

        if delta_value > 0:
            qty = int(delta_value / price / 100) * 100
            if qty >= 100:
                return {"ticker": ticker, "side": "buy", "quantity": qty, "price": price,
                        "target_weight_pct": signal.target_weight_pct,
                        "rating": signal.rating}
        elif delta_value < 0:
            qty = int(abs(delta_value) / price / 100) * 100
            avail = self._available_qty(ticker, uid)  # T+1约束
            qty = min(qty, avail)
            if qty >= 100:
                return {"ticker": ticker, "side": "sell", "quantity": qty, "price": price,
                        "target_weight_pct": signal.target_weight_pct,
                        "rating": signal.rating}
        return None

    # ---- 内部 ----
    def _execute_suggestion(self, suggestion: dict, user_id: str | None = None,
                            analysis_id: str | None = None) -> dict:
        """根据建议执行买/卖。"""
        if suggestion["side"] == "buy":
            return self.buy(suggestion["ticker"], suggestion["quantity"],
                           user_id=user_id, analysis_id=analysis_id)
        else:
            return self.sell(suggestion["ticker"], suggestion["quantity"],
                           user_id=user_id, analysis_id=analysis_id)

    def _get_current_price(self, ticker: str) -> float:
        """从route_to_vendor("get_etf_price_data")获取最新收盘价。"""

    def _update_day_barrier(self, user_id: str) -> None:
        """新的一天 → available_qty = quantity (T+1解冻)。"""

    def _auto_fill_name(self, ticker: str) -> str: ...
    def _ensure_schema(self) -> None: ...
    def _ensure_session_consistency(self) -> None:
        """确保session用户存在于数据库中。"""
    def _connect(self) -> sqlite3.Connection: ...
    def _position_market_value(self, ticker: str, user_id: str) -> float: ...
    def _available_qty(self, ticker: str, user_id: str) -> int: ...
```

T+1实现:
- `buy()` 后: `quantity += qty`, 但 `available_qty` 不变
- `sell()` 后: `quantity -= qty`, `available_qty -= qty`
- `_update_day_barrier()` 在每次交易前检查日期是否变化 → 新的一天: `available_qty = quantity`

#### `etfagents/paper_trading/rules.py`

（上方"交易规则"节的内容）

#### `cli/commands/paper.py`

```python
paper_app = typer.Typer(help="Paper trading simulation.")

@paper_app.command("register")
def paper_register(
    username: str = typer.Argument(..., help="Username to register."),
):
    """Register a new paper trading user."""
    # 用questionary.password两次输入密码
    # bcrypt哈希 → users表

@paper_app.command("login")
def paper_login(
    username: str = typer.Argument(..., help="Username to login as."),
):
    """Login to paper trading account."""
    # 输入密码 → 验证 → 写session

@paper_app.command("logout")
def paper_logout():
    """Logout from paper trading account."""

@paper_app.command("account")
def paper_account(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """Show paper trading account overview."""

@paper_app.command("buy")
def paper_buy(
    ticker: str = typer.Argument(..., help="ETF ticker."),
    quantity: int = typer.Argument(..., help="Number of shares (multiple of 100)."),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    analysis_id: Optional[str] = typer.Option(None, "--analysis-id",
        help="Link to analysis report directory."),
):
    """Buy ETF at market price."""

@paper_app.command("sell")
def paper_sell(
    ticker: str = typer.Argument(..., help="ETF ticker."),
    quantity: int = typer.Argument(..., help="Number of shares (multiple of 100)."),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    analysis_id: Optional[str] = typer.Option(None, "--analysis-id",
        help="Link to analysis report directory."),
):
    """Sell ETF at market price."""

@paper_app.command("positions")
def paper_positions(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """List all positions with live P&L."""

@paper_app.command("history")
def paper_history(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent trades."),
):
    """Show trade history."""

@paper_app.command("reset")
def paper_reset(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    confirm: bool = typer.Option(False, "--yes", "-y",
        help="Skip confirmation. This deletes ALL paper trading data."),
    cash: float = typer.Option(1_000_000.0, "--cash",
        help="Initial cash after reset."),
):
    """Reset paper trading account."""
```

### 修改文件

#### `cli/main.py`

1. 注册子命令:

```python
from cli.commands.paper import paper_app
app.add_typer(paper_app, name="paper")
```

2. 分析完成后提示(在 `display_complete_report()` 之后):

```python
# 仅在交互模式(analyze命令)下提示
from etfagents.agents.utils.rating import parse_rating

final_decision = get_state_value(final_state, "final_allocation_decision", "")
if analysis_mode == "single" and final_decision:
    rating = parse_rating(str(final_decision))
    if rating in ("BUY", "OVERWEIGHT"):
        from etfagents.paper_trading.engine import PaperTradingEngine
        engine = PaperTradingEngine()
        suggestion = engine.suggest_order_from_signal(ticker, final_state)
        if suggestion:
            console.print(Panel(
                f"模拟交易建议: {suggestion['side'].upper()} {ticker}"
                f" {suggestion['quantity']}份 "
                f"(@ {suggestion['price']:.3f}, "
                f"目标权重 {suggestion['target_weight_pct']}%)",
                title="Paper Trade Suggestion"
            ))
            execute = questionary.confirm("Execute?").ask()
            if execute:
                engine._execute_suggestion(suggestion)
```

### 验证标准

- [ ] `etfagents paper register alice` 注册 → 密码存为bcrypt哈希
- [ ] `etfagents paper login alice` 正确密码成功 / 错误密码失败
- [ ] `etfagents paper logout` 清除session
- [ ] 无session时使用 `default` 用户账户
- [ ] `etfagents paper account` 显示初始账户(100万)
- [ ] `etfagents paper buy 510300.SH 1000` 成交
- [ ] `etfagents paper positions` 显示持仓(含浮盈浮亏)
- [ ] `etfagents paper sell 510300.SH 500` 成交, 计算盈亏
- [ ] 当日买入的份额不可卖出(T+1)
- [ ] 次日(或重启引擎后) 可卖数量自动解冻
- [ ] 不足100份的买入被拒绝
- [ ] 现金不足的买入被拒绝
- [ ] 持仓不足的卖出被拒绝
- [ ] `etfagents paper history` 正确显示买卖记录
- [ ] `etfagents paper reset --yes` 清空后账户回到初始状态
- [ ] 佣金计算正确: max(amount*0.00025, 5.0)
- [ ] ETF无印花税
- [ ] `--analysis-id` 正确关联到成交记录
- [ ] `--user alice` 和 `--user bob` 操作不同的账户数据
- [ ] `suggest_order_from_signal()` 从BUY信号生成正确的买入建议，返回值必须包含 `ticker`，可直接传给 `_execute_suggestion()`

---

## 8. 文件变更总览

### 新增文件 (11个)

| 文件路径 | 阶段 | 说明 |
|---------|------|------|
| `cli/commands/__init__.py` | P1 | CLI命令包初始化 |
| `etfagents/cache_manager.py` | P1 | 缓存统计/清理聚合器 |
| `cli/commands/cache.py` | P1 | cache子命令组 |
| `etfagents/watchlist.py` | P2 | 自选股SQLite管理 |
| `cli/commands/watchlist.py` | P2 | watchlist子命令组 |
| `etfagents/detail.py` | P4 | ETF详情数据聚合 |
| `cli/commands/detail.py` | P4 | detail顶级命令 |
| `etfagents/paper_trading/__init__.py` | P6 | 模拟交易包 |
| `etfagents/paper_trading/engine.py` | P6 | 模拟交易引擎 |
| `etfagents/paper_trading/rules.py` | P6 | A股ETF交易规则 |
| `cli/commands/paper.py` | P6 | paper子命令组 |

### 修改文件 (8个)

| 文件路径 | 阶段 | 变更内容 |
|---------|------|---------|
| `cli/main.py` | P1-P6 | 注册4个子命令组(cache/watchlist/paper)+1个顶级命令(detail); analyze/backtest新增`--watchlist`选项; 分析后paper交易建议提示 |
| `etfagents/llm_clients/model_catalog.py` | P3 | 新增CapabilityLevel/MODEL_CAPABILITIES/RESEARCH_DEPTH_REQUIREMENTS/recommend_models()/get_depth_config() |
| `etfagents/default_config.py` | P1,P3 | 新增research_depth_name/snapshot_max_age_days/backtest_cache_max_age_days/checkpoint_max_age_days键 |
| `cli/utils.py` | P3 | 新增select_research_depth_name()/select_model_strategy(); 修改get_user_selections()支持preselected_tickers |
| `etfagents/backtest/cache.py` | P1 | put()改原子写; config_hash新增BACKTEST_SIGNAL_PROMPT_VERSION |
| `etfagents/agents/utils/daily_snapshot_cache.py` | P1 | 损坏文件自动恢复; _is_usable_snapshot类型容错 |
| `etfagents/dataflows/tushare.py` | P1 | 删除死import lru_cache |
| `pyproject.toml` | P6 | 新增 `bcrypt>=4.0` 依赖 |

### 不修改的文件

- `etfagents/agents/` — 无需改动(除P1模块修复)
- `etfagents/graph/setup.py` — 图拓扑不变
- `etfagents/graph/etf_graph.py` — 不实现并发
- `etfagents/dataflows/interface.py` — 仅调用, 不改接口
- `etfagents/llm_clients/factory.py` — provider路由不变
- `etfagents/backtest/backtrader_engine.py` — 不改变回测执行逻辑；P1 仅修改 `etfagents/backtest/cache.py` 的原子写和hash

---

## 9. 测试策略

### 测试文件规划

| 测试文件 | 阶段 | 覆盖内容 |
|---------|------|---------|
| `tests/test_cache_manager.py` | P1 | CacheManager.stats/cleanup/clear/details/mocked目录结构 |
| `tests/test_watchlist.py` | P2 | WatchlistManager CRUD/分组/标签/边界(TemporaryDirectory临时DB) |
| `tests/test_model_recommend.py` | P3 | recommend_models各级深度/各provider/边界; MODEL_CAPABILITIES覆盖MODEL_OPTIONS静态模型 |
| `tests/test_detail.py` | P4 | get_etf_detail mock vendor返回值解析 |
| `tests/test_paper_trading.py` | P6 | Engine buy/sell/T+1/佣金/余额检查/reset/多用户/suggest_order_from_signal |
| `tests/test_candidate_pool_progress.py` | P5 | candidate pool顺序进度提示与摘要表渲染（新增独立文件，不复用现有 `tests/test_cli_round_formatting.py` 以免与既有的 round-formatting 测试混淆） |

### 测试要点

- **SQLite测试**: 使用 `tempfile.TemporaryDirectory()` 创建临时DB, 不污染 `~/.etfagents/`；保持当前 `unittest` 测试风格
- **vendor mock**: P4的detail测试 patch `etfagents.detail.route_to_vendor`（前提是 `detail.py` 直接导入该函数）；若实现改为模块导入，则同步调整patch路径
- **多用户隔离**: P6验证 `--user alice` 和 `--user bob` 的数据完全隔离
- **T+1解冻**: P6测试模拟跨日场景
- **边界case**: 空watchlist、空缓存目录、不存在的ticker、零余额买入、100份整数倍检查
- **向后兼容**: P3测试验证手动选择路径不受影响

### 运行命令

```bash
python -m unittest discover -s tests -q
python -m unittest tests.test_cache_manager.CacheManagerTests.test_stats_empty_dir -q
python -m unittest tests.test_paper_trading.PaperTradingTests.test_t1_restriction -q
```

---

## 10. 风险与依赖

### 风险

| 风险 | 影响 | 缓解 |
|-----|------|------|
| bcrypt依赖未安装 | P6 | 将 `bcrypt>=4.0` 加入 `pyproject.toml`; 运行时仍捕获 ImportError 并给出安装提示 |
| 两个用户同时写session文件 | P6 | 写入时使用 tempfile + `os.replace()` 原子操作 |
| 损坏JSON文件的重命名失败 | P1(F2) | 捕获 `OSError` 记录 warning 并继续抛出，避免静默复用坏文件 |
| model_catalog中模型名过时 | P3 | 能力表覆盖所有静态模型并用测试锁定; 动态/本地模型允许手动选择 |
| Tushare API不可用时suggest_order_from_signal失败 | P6 | 捕获DataVendorUnavailable, 返回None无建议 |

### 依赖

| 依赖 | 版本 | 用途 |
|-----|------|------|
| Python | 3.10+ | 已有 |
| sqlite3 | 标准库 | P2/P6 持久化 |
| Typer | 已有 | CLI |
| Rich | 已有 | 终端渲染 |
| questionary | 已有 | 交互选择 |
| bcrypt | >=4.0 | P6 密码哈希（新增到 `pyproject.toml`） |
| hashlib | 标准库 | P1 config_hash |

**新增外部依赖**: `bcrypt>=4.0` (P6)，必须写入 `pyproject.toml`。仅此一项。

### 实施时间线

| 阶段 | 预估天数 | 依赖 |
|------|---------|------|
| P1 缓存管理 | 1-2天 | 无 |
| P2 自选股 | 2天 | 无 |
| P3 智能模型选择 | 1.5天 | P2(仅CLI集成顺序) |
| P4 ETF详情页 | 2天 | P1(复用缓存统计展示历史报告) |
| P5 批量分析增强 | 1天 | P2(watchlist作为ticker来源) |
| P6 模拟交易 | 3-4天 | P4(获取价格接口复用) |
| **总计** | **10.5-12.5天** | |
