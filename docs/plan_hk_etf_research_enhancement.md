# PLAN: 港股 ETF 研报增强 — A+H 双上市映射 + AkShare 行业主题 fallback

> 状态: DRAFT  
> 日期: 2026-05-18  
> 范围: `pyproject.toml`, `etfagents/dataflows/akshare.py`, `etfagents/agents/utils/etf_data_tools.py`, `etfagents/dataflows/tushare.py`, analysts, tests

---

## 1. 问题

当前港股 ETF 代理篮子（`_HK_BENCHMARK_PROXY_BASKETS`）的持仓全部跳过研报查询：

- `get_etf_top_holdings_research()` 对 HK proxy 仅输出 HK daily 价格快照（`etf_data_tools.py:1774-1782`），**无个股研报**
- `get_etf_industry_research()` 对 HK proxy 直接 `continue` 跳过（`etf_data_tools.py:1697-1698`），**无行业研报**

但其中部分成员在 A 股也有上市（如 00981.HK → 688981.SH 中芯国际，00939.HK → 601939.SH 建设银行），可以用 A 股代码在 Tushare 上查到个股研报。

同时，不能再依赖个股研报的 `ind_name` 来反推行业。港股持仓的行业归类应改用独立元数据来源：AkShare `stock_hk_security_profile_em(symbol="03900")` 返回的公司资料中包含 `所属行业` 字段，可作为 HK proxy 行业关键词的主来源；当前 basket 内置 `industry` 仅作为 AkShare 失败时的 fallback。

## 2. 目标

1. **A+H 双上市股**: 用其 A 股代码查询 Tushare 个股研报，获得完整研报覆盖
2. **港股行业来源**: 用 AkShare 港股公司资料的 `所属行业` 作为 HK proxy 行业关键词主来源，失败时回退到 basket 快照行业
3. **纯港股（无 A 股映射）**: 以 AkShare/basket 行业关键词拉取行业/主题研报，标注"主题相关，非逐只覆盖"
4. 保持现有 A 股 ETF 研报流程不变；仅改动 HK proxy 分支

## 3. 方案

### 3.1 新增 AkShare 港股行业元数据入口

**文件**: `pyproject.toml`, `etfagents/dataflows/akshare.py`

在项目依赖中加入 AkShare（版本下限以本地验证可用版本为准），新增轻量数据入口，避免在 ETF 工具函数中直接散落第三方 API 细节：

```python
def get_hk_security_profile(symbol: str) -> pd.DataFrame:
    """Return AkShare Eastmoney HK security profile for a 5-digit HK symbol."""
    import akshare as ak

    return ak.stock_hk_security_profile_em(symbol=symbol)
```

再提供只暴露本需求所需字段的 helper：

```python
def get_hk_security_industry(symbol: str) -> str:
    """Return AkShare '所属行业' for a 5-digit HK symbol, or '' when unavailable."""
```

解析规则要保守：

- 输入统一为 5 位港股数字代码，例如 `03900`；从 `00981.HK` 转换为 `00981`
- 优先读取名为 `所属行业` 的列
- 如果返回的是键值表，则查找字段/项目名为 `所属行业` 的行
- 空值、`nan`、`None` 返回空字符串，由调用方回退到 basket 行业
- 单元测试 mock AkShare 返回值，不打真实网络

### 3.2 新增 A+H 双上市映射

**文件**: `etfagents/agents/utils/etf_data_tools.py`

新增模块级常量 `_AH_SHARE_MAP`，作为 **唯一** A+H 映射来源。它覆盖当前 `_HK_BENCHMARK_PROXY_BASKETS` 中所有 HK proxy 成员；值为 `None` 表示当前没有可用 A 股对应标的：

```python
_AH_SHARE_MAP: dict[str, str | None] = {
    "00700.HK": None,       # 腾讯控股 — 纯港股
    "09988.HK": None,       # 阿里巴巴-W — 纯港股
    "03690.HK": None,       # 美团-W — 纯港股
    "01810.HK": None,       # 小米集团-W — 纯港股
    "01024.HK": None,       # 快手-W — 纯港股
    "09618.HK": None,       # 京东集团-SW — 纯港股
    "09999.HK": None,       # 网易-S — 纯港股
    "00981.HK": "688981.SH", # 中芯国际 — A+H
    "00005.HK": None,       # 汇丰控股 — 纯港股
    "00939.HK": "601939.SH", # 建设银行 — A+H
    "01299.HK": None,        # 友邦保险 — 纯港股，无A股对应标的
}
```

辅助函数：

```python
def _resolve_a_share_counterpart(hk_code: str) -> str | None:
    """Return the A-share ts_code for an A+H dual-listed HK stock, or None."""
    return _AH_SHARE_MAP.get(_normalize_ts_code(hk_code))
```

### 3.3 `_build_hk_benchmark_proxy_frame()` 派生 `a_share_code` 与 AkShare 行业列

**不** 在 `_HK_BENCHMARK_PROXY_BASKETS` 的 member 字典中重复维护 `a_share_code`。原因：basket 已经是一个硬编码快照，再额外维护同一映射会产生漂移风险。

`_build_hk_benchmark_proxy_frame()` 在构建每行时：

1. 调用 `_resolve_a_share_counterpart(member_code)`，把结果写入 DataFrame 的 `a_share_code` 列
2. 调用 AkShare helper 获取 `所属行业`，写入 `akshare_industry` 列
3. 将输出 `industry` 设为 `akshare_industry or metadata["industry"]`
4. 增加 `industry_source` 列，值为 `akshare 所属行业` 或 `basket fallback industry`

该函数的行构建循环（约第 397-405 行）显式构造每行，需在 `rows.append({...})` 中显式新增这些字段。

```python
akshare_industry = _lookup_akshare_hk_industry(member_code)
rows.append(
    {
        "ts_code": metadata["ts_code"],
        "name": metadata["name"],
        "industry": akshare_industry or metadata["industry"],
        "akshare_industry": akshare_industry,
        "industry_source": "akshare 所属行业" if akshare_industry else "basket fallback industry",
        "weight": ...,
        "a_share_code": _resolve_a_share_counterpart(member_code),
        **price,
    }
)
```

### 3.4 修改 `get_etf_top_holdings_research()` — 个股研报

**文件**: `etfagents/agents/utils/etf_data_tools.py:1770-1782`

将 HK proxy 分支从"直接跳过"改为三段逻辑：

```
对每个 HK 持仓:
  1. row["a_share_code"] 有结果？
     → YES: 用 A 股代码调 get_stock_reports(a_code, ...)
             get_stock_reports() 自身也有 A 股市场守卫（tushare.py:2179），
             此处传 A 股代码会正常通过
             标注 "A+H双上市，以A股代码 {a_code} 查询个股研报"
  2. 无 A 股映射，或 A 股个股研报不可用？
     → fallback: 用该持仓的 industry 关键词调 get_broker_reports(...,
                 _skip_industry_resolution=True,
                 extra_ind_names=_hk_industry_to_broker_keywords(industry))
                 其中 A+H 持仓优先传 a_share_code；纯 HK 持仓传 hk_code 并加 _skip_market_check=True
                 标注 "以下为主题相关行业研报，非成分股逐只覆盖"
  3. 行业研报也为空？
     → 保留现有 HK daily 价格快照
```

主题 fallback 需要在单次函数调用内对 `industry` 做去重缓存，避免同一轮 top holdings 中多个港股持仓重复拉取完全相同的行业主题研报。例如腾讯和阿里同属 `互联网平台`，第二只持仓应复用已获取的主题研报，或输出 "主题研报同 Holding 1，未重复拉取" 的说明。

标题中补充行业来源，避免把 AkShare 行业、basket fallback 行业和券商研报行业混为一谈：

```
## Holding 2: 腾讯控股 (00700.HK) | proxy-basket weight 10.0% | industry 互联网服务 | industry source akshare 所属行业
```

输出示例：

```
## Holding 1: 中芯国际 (00981.HK → 688981.SH) | proxy-basket weight 6.0% | industry 半导体
[A+H双上市，以A股代码688981.SH查询个股研报]
<get_stock_reports("688981.SH", ...) 的输出>

## Holding 2: 腾讯控股 (00700.HK) | proxy-basket weight 10.0% | industry 互联网平台
[纯港股，以下为主题相关行业研报，非成分股逐只覆盖]
<get_broker_reports(..., extra_ind_names=("互联网",)) 的输出>
```

### 3.5 修改 `get_etf_industry_research()` — 行业研报

**文件**: `etfagents/agents/utils/etf_data_tools.py:1686-1698`

当前 HK proxy 分支在循环中直接 `continue` 跳过行业研报。改为：

1. 用持仓的 `industry` 字段作为行业关键词
2. 同行业内优先选择有 `a_share_code` 的成员作为 representative；若多个成员都有 A 股映射，仍按权重降序选择
3. 如果 representative 有 A 股映射，用 A 股代码触发 `get_broker_reports()`，但仍传入 AkShare/basket 行业关键词，并设置 `_skip_industry_resolution=True`，不再调用个股研报解析行业
4. 如果该行业没有任何 A 股映射，用 `_skip_market_check=True, _skip_industry_resolution=True` 触发 `get_broker_reports()`（仅按传入 `ind_name` 关键词搜索）
5. 同行业只查一次（保留现有 representatives 去重逻辑，但补充 A+H 优先选择规则）
6. 输出标注 "主题相关行业研报（基于港股代理持仓行业映射）"

当前 `金融` 行业是关键验证场景：港股宽基 basket 中汇丰控股权重 8.0、建设银行权重 6.0。若只按权重选 representative，会选中无 A 股映射的汇丰控股，导致 `00939.HK → 601939.SH` 的 A+H 路径被跳过。实现时必须在 HK proxy 分支把有 A 股映射的成员排在同业候选前面。

移除/修改当前第 1686-1690 行的警告消息，改为更精确的说明：

```
"本文档包含港股ETF代理持仓的行业研报增强。A+H双上市持仓以其A股代码查询；
港股行业归类优先来自AkShare所属行业，纯港股持仓以行业关键词查询主题研报（非成分股逐只覆盖）。"
```

### 3.6 放开 `get_broker_reports()` 的显式行业关键词路径

**文件**: `etfagents/dataflows/tushare.py`

当前有两处守卫需要处理：

1. **市场守卫** (`tushare.py:2012-2014`): `_classify_market(ts_code) != "a_share"` 直接抛异常
2. **行业关键词解析** (`tushare.py:2017`): `_resolve_broker_industry_keyword(pro, ts_code, ...)` 依赖个股研报 `ind_name` 和 `stock_basic.industry` 推断行业。HK proxy 场景不能再依赖这条路径，必须允许调用方显式传入行业关键词

改动方案：

```python
def get_broker_reports(ticker, start_date, end_date,
                       max_reports=30, extra_ind_names=None,
                       *, _skip_market_check=False,
                       _skip_industry_resolution=False):
```

逻辑：

```python
if not _skip_market_check and _classify_market(ts_code) != "a_share":
    raise DataVendorUnavailable(...)

normalized_extra_ind_names = normalize(extra_ind_names)

if _skip_industry_resolution:
    if not normalized_extra_ind_names:
        raise DataVendorUnavailable("Explicit industry keywords are required when skipping industry resolution.")
    industry = normalized_extra_ind_names[0]
    industry_source = "explicit industry keywords"
    basic_industry = ""
elif _skip_market_check and _classify_market(ts_code) != "a_share":
    raise DataVendorUnavailable("Explicit industry keywords are required for non-A-share broker report search.")
else:
    industry, industry_source, basic_industry = _resolve_broker_industry_keyword(
        pro, ts_code, start_date, end_date,
    )
```

当 `_skip_industry_resolution=True` 时，`candidate_industries` 只能来自 `extra_ind_names`，不得追加 `_resolve_broker_industry_keyword()` 的结果。

当 HK proxy 场景传入行业关键词查询时：

- A+H representative: `get_broker_reports(a_share_code, ..., extra_ind_names=keywords, _skip_industry_resolution=True)`
- 纯 HK representative: `get_broker_reports(hk_code, ..., extra_ind_names=keywords, _skip_market_check=True, _skip_industry_resolution=True)`

这两个参数以 `_` 前缀标记为内部使用，不暴露给 LangChain tool 接口。

测试需验证 `_skip_industry_resolution=True` 时，不调用 `stock_basic()`，也不调用用于解析个股 `ind_name` 的 `research_report(ts_code=...)`，只调用 `research_report(ind_name=...)`。

### 3.7 港股行业关键词映射

新增辅助常量，将 AkShare/basket 的港股 `industry` 字段映射为 Tushare 研报可识别的行业关键词。注意 AkShare `所属行业` 可能比当前 basket 行业更细或用词不同，因此该表既覆盖当前 basket 行业，也覆盖 AkShare 常见行业名：

```python
_HK_INDUSTRY_TO_BROKER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "互联网平台": ("互联网", "传媒"),
    "互联网服务": ("互联网", "传媒"),
    "本地生活": ("餐饮旅游", "社会服务"),
    "智能硬件": ("电子", "消费电子"),
    "互联网内容": ("传媒", "互联网"),
    "电商": ("商贸零售", "电子商务"),
    "游戏娱乐": ("传媒", "游戏"),
    "半导体": ("半导体", "电子"),
    "金融": ("银行", "非银金融"),
    "保险": ("保险", "非银金融"),
}
```

辅助函数：

```python
def _hk_industry_to_broker_keywords(industry: str) -> tuple[str, ...]:
    return _HK_INDUSTRY_TO_BROKER_KEYWORDS.get(industry, (industry,))
```

两个入口的接入方式：

- **`get_etf_top_holdings_research()`** — level-2 fallback 处调用 `_hk_industry_to_broker_keywords(row["industry"])`，结果传入 `get_broker_reports(..., _skip_industry_resolution=True, extra_ind_names=...)`；纯 HK 持仓额外传 `_skip_market_check=True`
- **`get_etf_industry_research()`** — 移除现有 `if is_hk_proxy: continue` 跳过逻辑后，在行业代表循环中分支处理：有 `a_share_code` 时用 A 股代码调用 `get_broker_reports(a_share_code, ..., _skip_industry_resolution=True, extra_ind_names=...)`；没有 A 股映射时调用 `_hk_industry_to_broker_keywords(row["industry"])`，并传入 `get_broker_reports(row["ts_code"], ..., _skip_market_check=True, _skip_industry_resolution=True, extra_ind_names=...)`

注意现有 `_related_broker_industry_keywords()`（`etf_data_tools.py:1464`）仅处理农业板块触发词，返回空列表给其他行业。`_hk_industry_to_broker_keywords()` 是独立的 HK proxy 专用路径，不修改 `_related_broker_industry_keywords()`。

### 3.8 分析师提示词

**不需要修改**。

当前 `etf_stock_research_analyst.py` 和 `etf_industry_research_analyst.py` 的系统提示词是工具无关的——它们仅指示调用工具并交叉分析返回内容，不提及 A 股/H 股限制。HK proxy 数据来源差异已由第 3.3-3.4 节的工具输出标注覆盖（`[A+H双上市…]`、`[纯港股…]`），分析师 LLM 会自然据此区分数据来源，无需额外的提示词引导。

### 3.9 测试

**文件**: `tests/test_etf_extensions.py`, `tests/test_broker_research.py`

| 测试名 | 验证点 |
|--------|--------|
| `test_ah_share_map_keys_match_basket_members` | `_AH_SHARE_MAP` 覆盖所有 basket 成员，且 basket member 不重复维护 `a_share_code` |
| `test_akshare_hk_security_industry_extracts_profile_field` | 从 AkShare profile 返回值中提取 `所属行业` |
| `test_hk_proxy_frame_derives_a_share_code_and_akshare_industry` | `_build_hk_benchmark_proxy_frame()` 从 `_AH_SHARE_MAP` 派生 `a_share_code`，并优先使用 AkShare `所属行业` |
| `test_hk_proxy_frame_falls_back_to_basket_industry_when_akshare_missing` | AkShare 为空/异常时保留 basket 行业并标注 fallback 来源 |
| `test_hk_proxy_top_holdings_uses_a_share_for_dual_listed` | A+H 股调 `get_stock_reports(a_code)` |
| `test_hk_proxy_top_holdings_uses_industry_fallback_for_hk_only` | 纯港股走 `get_broker_reports()` 行业 fallback，并对相同行业主题研报去重 |
| `test_hk_proxy_industry_research_fetches_broker_reports` | HK proxy 不再跳过行业研报 |
| `test_hk_proxy_industry_research_prefers_a_share_representative` | 同一行业内有 A+H 与纯港股成员时，优先用 A 股映射触发行业研报 |
| `test_get_broker_reports_skip_industry_resolution_uses_explicit_keywords` | `_skip_industry_resolution=True` 只按 `extra_ind_names` 查行业研报 |
| `test_get_broker_reports_skip_industry_resolution_avoids_stock_keyword_resolution` | 不调用 `stock_basic()` 或 `research_report(ts_code=...)` |
| `test_get_broker_reports_skip_industry_resolution_requires_extra_keywords` | `_skip_industry_resolution=True` 但无 `extra_ind_names` 时失败并说明缺少行业关键词 |
| `test_hk_industry_to_broker_keywords_mapping` | 行业关键词映射覆盖所有 basket 中的行业 |

## 4. 不做的事

- **不** 动态调用 Tushare `hk_hold` 做实时 A+H 映射（保持硬编码惯例，与 `_HK_BENCHMARK_PROXY_BASKETS` 一致）
- **不** 为纯港股做逐只个股研报覆盖（Tushare 不支持）
- **不** 使用 Tushare 个股研报 `ind_name` 反推 HK proxy 行业
- **不** 修改 A 股 ETF 的任何研报逻辑
- **不** 增加 LLM 调用（Rule 5: 模型仅用于判断）
- **不** 修改分析师提示词 — 数据来源差异已由工具输出标注自然传达，无需额外的 prompt 引导

## 5. 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `pyproject.toml` | 新增 AkShare 依赖 |
| `etfagents/dataflows/akshare.py` | 新增 AkShare 港股 profile / `所属行业` helper |
| `etfagents/agents/utils/etf_data_tools.py` | 新增 `_AH_SHARE_MAP`（修正01299.HK映射为None）、`_resolve_a_share_counterpart()`、`_HK_INDUSTRY_TO_BROKER_KEYWORDS`、`_hk_industry_to_broker_keywords()`；`_build_hk_benchmark_proxy_frame()` 从 `_AH_SHARE_MAP` 派生 `a_share_code`，并从 AkShare 派生 `industry`/`industry_source`；修改 `get_etf_top_holdings_research()` 的 HK proxy 分支并去重相同行业 fallback；修改 `get_etf_industry_research()` 的 HK proxy 分支并优先选择 A+H representative |
| `etfagents/dataflows/tushare.py` | `get_broker_reports()` 增加 `_skip_market_check` 与 `_skip_industry_resolution` 参数；当 `_skip_industry_resolution=True` 时只使用显式行业关键词，避免用个股研报反推行业 |
| `tests/test_etf_extensions.py` | 新增 HK proxy 映射、AkShare 行业、A+H representative、top-holdings fallback 去重测试 |
| `tests/test_broker_research.py` | 新增 `_skip_industry_resolution` 行为测试，覆盖显式 `ind_name` 查询路径 |

## 6. 实施顺序

1. `pyproject.toml` + `etfagents/dataflows/akshare.py` — 增加 AkShare 依赖和港股 `所属行业` helper
2. `etfagents/dataflows/tushare.py` — `_skip_market_check` + `_skip_industry_resolution` 参数，支持显式行业关键词路径
3. `etfagents/agents/utils/etf_data_tools.py` — 映射表（修正01299.HK）+ `_build_hk_benchmark_proxy_frame` 派生 `a_share_code`/AkShare 行业 + 两个 tool 函数 HK proxy 分支修改
4. 测试
5. `python -m unittest discover -s tests -q` 全量验证
