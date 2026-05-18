from __future__ import annotations

import io
import logging
import os
import re
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

import pandas as pd
import requests

from langchain_core.tools import tool

from etfagents.agents.utils.daily_snapshot_cache import (
    DailySnapshotCacheError,
    get_or_build_shared_snapshot,
)
from etfagents.dataflows.exceptions import DataVendorUnavailable, MissingEtfHoldings
from etfagents.dataflows.interface import route_to_vendor
from etfagents.dataflows.tushare import (
    _get_pro_client,
    _infer_etf_asset_scope,
    _infer_etf_exposure_bucket,
    _normalize_ts_code,
    _query_pro,
    _resolve_broker_industry_keyword,
    _to_csv_with_header,
    get_broker_reports,
    get_stock_reports,
)


logger = logging.getLogger(__name__)

_ETF_INDICATOR_ALIASES = {
    "ma": "close_20_sma",
    "sma": "close_20_sma",
    "20ma": "close_20_sma",
    "ma20": "close_20_sma",
    "20sma": "close_20_sma",
    "sma20": "close_20_sma",
    "50ma": "close_50_sma",
    "ma50": "close_50_sma",
    "50sma": "close_50_sma",
    "sma50": "close_50_sma",
    "120ma": "close_120_sma",
    "ma120": "close_120_sma",
    "120sma": "close_120_sma",
    "sma120": "close_120_sma",
    "200ma": "close_200_sma",
    "ma200": "close_200_sma",
    "200sma": "close_200_sma",
    "sma200": "close_200_sma",
    "10ema": "close_10_ema",
    "ema10": "close_10_ema",
    "bollinger": "boll",
    "bollinger_middle": "boll",
    "bollinger_mid": "boll",
    "bollinger_upper": "boll_ub",
    "bollinger_lower": "boll_lb",
    "macd_signal": "macds",
    "signal": "macds",
    "macd_hist": "macdh",
    "macd_histogram": "macdh",
}

_SHARED_SNAPSHOT_SCHEMA_VERSION = {
    "macro": 1,
    "commodity": 1,
}

_MACRO_SAFE_HAVEN_SPECS = [
    ("Gold", "GC=F", False),
    ("Dollar Index", "DX-Y.NYB", False),
    ("Swiss franc safe-haven bid", "CHF=X", True),
    ("Japanese yen safe-haven bid", "JPY=X", True),
    ("Dry-bulk / shipping stress proxy", "BDRY", False),
]

_COMMODITY_SPECS = [
    ("贵金属 · 金", "AU", "SHFE", "沪金主力", "Fiat trust, real rates, systemic risk premium"),
    ("贵金属 · 银", "AG", "SHFE", "沪银主力", "Industrial + monetary hybrid, solar demand"),
    ("工业金属 · 铜", "CU", "SHFE", "沪铜主力", "Global manufacturing resilience and real new-infrastructure demand"),
    ("工业金属 · 铝", "AL", "SHFE", "沪铝主力", "China smelting capacity, power-grid capex, export tariffs"),
    ("工业金属 · 铅", "PB", "SHFE", "沪铅主力", "Lead-acid battery demand, recycled metal supply, and power-storage capex"),
    ("工业金属 · 镍", "NI", "SHFE", "沪镍主力", "Stainless steel demand vs battery-grade NPI substitution"),
    ("工业金属 · 锌", "ZN", "SHFE", "沪锌主力", "Galvanized steel demand, infrastructure and auto body"),
    ("能源 · 原油", "SC", "INE", "原油主力", "Recession risk, OPEC+ elasticity, and policy tightening room"),
    ("转型金属 · 碳酸锂", "LC", "GFEX", "碳酸锂主力", "Energy-transition profit pools and industry-clearing speed"),
    ("黑色 · 螺纹钢", "RB", "SHFE", "螺纹钢主力", "China investment-cycle strength, PPI turning points, policy intervention"),
    ("黑色 · 热卷", "HC", "SHFE", "热卷主力", "Automotive and manufacturing demand, downstream steel consumption strength"),
    ("黑色 · 铁矿石", "I", "DCE", "铁矿石主力", "Steel-mill margins, blast-furnace utilization, import dependency"),
    ("黑色 · 焦煤", "JM", "DCE", "焦煤主力", "Coking cost pass-through, safety-driven supply disruption"),
    ("化工 · PTA", "TA", "CZCE", "PTA主力", "Polyester chain pricing anchor, textile export demand, and refining margin pass-through"),
    ("化工 · 甲醇", "MA", "CZCE", "甲醇主力", "Coal-chemical cost anchor, MTO demand, and fuel-alternative policy"),
    ("化工 · 聚乙烯", "L", "DCE", "聚乙烯主力", "Plastic packaging and film demand, petrochemical margin cycle"),
    ("油脂油料 · 豆粕", "M", "DCE", "豆粕主力", "Feed demand anchor for hog/poultry cycle, crush margin, and soybean import dependency"),
    ("油脂油料 · 玉米", "C", "DCE", "玉米主力", "Grain security, ethanol mandate, and deep-processing capacity"),
    ("油脂油料 · 棕榈油", "P", "DCE", "棕榈油主力", "Global edible-oil balance, biodiesel mandate, and tropical supply risk"),
    ("软商品 · 纸浆", "SP", "SHFE", "纸浆主力", "Climate shocks, substitution, and logistics-driven inflation"),
    ("软商品 · 天然橡胶", "RU", "SHFE", "天然橡胶主力", "Tire demand, auto production cycle, Southeast Asia supply"),
    ("工业品 · 工业硅", "SI", "GFEX", "工业硅主力", "Polysilicon and silicone demand, capacity overhang"),
    ("工业品 · 尿素", "UR", "CZCE", "尿素主力", "Fertilizer seasonality, coal-chemical cost, export policy"),
    ("工业品 · PVC", "V", "DCE", "PVC主力", "Real estate piping demand, calcium-carbide cost curve"),
    ("工业品 · 纯碱", "SA", "CZCE", "纯碱主力", "Glass production demand, photovoltaic expansion, capacity cycle"),
]

_AGRICULTURE_RESEARCH_KEYWORDS = ("农牧饲渔", "养殖业")
_AGRICULTURE_RESEARCH_TRIGGERS = ("农牧饲渔", "养殖", "饲料", "生猪", "动物保健", "农产品加工")
# Representative A-share producer baskets used only when a commodity ETF has no disclosed
# equity holdings. Constituents are liquid, broker-covered producers chosen as a correlated
# research reference; the proxy weights are illustrative rather than ETF replication weights.
# TODO: refresh the constituents and illustrative weights at least annually.
_COMMODITY_PRODUCER_PROXY_BASKETS = (
    {
        "label": "黄金",
        "keywords": ("黄金", "gold", "au"),
        "members": (
            {"ts_code": "600547.SH", "name": "山东黄金", "industry": "有色金属", "weight": 40.0},
            {"ts_code": "600489.SH", "name": "中金黄金", "industry": "有色金属", "weight": 35.0},
            {"ts_code": "601899.SH", "name": "紫金矿业", "industry": "有色金属", "weight": 25.0},
        ),
    },
    {
        "label": "白银",
        "keywords": ("白银", "silver", "ag"),
        "members": (
            {"ts_code": "601899.SH", "name": "紫金矿业", "industry": "有色金属", "weight": 40.0},
            {"ts_code": "000426.SZ", "name": "兴业银锡", "industry": "有色金属", "weight": 35.0},
            {"ts_code": "600362.SH", "name": "江西铜业", "industry": "有色金属", "weight": 25.0},
        ),
    },
    {
        "label": "原油",
        "keywords": ("原油", "oil", "crude"),
        "members": (
            {"ts_code": "600938.SH", "name": "中国海油", "industry": "石油石化", "weight": 40.0},
            {"ts_code": "601857.SH", "name": "中国石油", "industry": "石油石化", "weight": 35.0},
            {"ts_code": "600028.SH", "name": "中国石化", "industry": "石油石化", "weight": 25.0},
        ),
    },
    {
        "label": "锂",
        "keywords": ("锂", "碳酸锂", "lithium"),
        "members": (
            {"ts_code": "002460.SZ", "name": "赣锋锂业", "industry": "有色金属", "weight": 40.0},
            {"ts_code": "002466.SZ", "name": "天齐锂业", "industry": "有色金属", "weight": 35.0},
            {"ts_code": "002738.SZ", "name": "中矿资源", "industry": "有色金属", "weight": 25.0},
        ),
    },
    {
        "label": "工业金属",
        "keywords": ("有色", "工业金属", "铜", "铝", "metal"),
        "display_label": "工业金属（铜偏重代理）",
        "members": (
            {"ts_code": "601899.SH", "name": "紫金矿业", "industry": "有色金属", "weight": 40.0},
            {"ts_code": "603993.SH", "name": "洛阳钼业", "industry": "有色金属", "weight": 35.0},
            {"ts_code": "600362.SH", "name": "江西铜业", "industry": "有色金属", "weight": 25.0},
        ),
    },
)
_GENERIC_COMMODITY_PRODUCER_PROXY_BASKET = {
    "label": "商品",
    "members": (
        {"ts_code": "601899.SH", "name": "紫金矿业", "industry": "有色金属", "weight": 40.0},
        {"ts_code": "603993.SH", "name": "洛阳钼业", "industry": "有色金属", "weight": 35.0},
        {"ts_code": "600938.SH", "name": "中国海油", "industry": "石油石化", "weight": 25.0},
    ),
}
_HK_BENCHMARK_PROXY_BASKETS = (
    {
        "label": "恒生科技",
        "keywords": ("恒生科技", "hang seng tech", "hstech"),
        "members": (
            {"ts_code": "00700.HK", "name": "腾讯控股", "industry": "互联网平台", "weight": 10.0},
            {"ts_code": "09988.HK", "name": "阿里巴巴-W", "industry": "互联网平台", "weight": 10.0},
            {"ts_code": "03690.HK", "name": "美团-W", "industry": "本地生活", "weight": 9.0},
            {"ts_code": "01810.HK", "name": "小米集团-W", "industry": "智能硬件", "weight": 8.0},
            {"ts_code": "01024.HK", "name": "快手-W", "industry": "互联网内容", "weight": 7.0},
            {"ts_code": "09618.HK", "name": "京东集团-SW", "industry": "电商", "weight": 7.0},
            {"ts_code": "09999.HK", "name": "网易-S", "industry": "游戏娱乐", "weight": 6.0},
            {"ts_code": "00981.HK", "name": "中芯国际", "industry": "半导体", "weight": 6.0},
        ),
    },
    {
        "label": "港股宽基",
        "keywords": ("恒生", "港股", "香港", "hong kong", "hang seng"),
        "members": (
            {"ts_code": "00700.HK", "name": "腾讯控股", "industry": "互联网平台", "weight": 10.0},
            {"ts_code": "09988.HK", "name": "阿里巴巴-W", "industry": "互联网平台", "weight": 9.0},
            {"ts_code": "00005.HK", "name": "汇丰控股", "industry": "金融", "weight": 8.0},
            {"ts_code": "03690.HK", "name": "美团-W", "industry": "本地生活", "weight": 7.0},
            {"ts_code": "00939.HK", "name": "建设银行", "industry": "金融", "weight": 6.0},
            {"ts_code": "01299.HK", "name": "友邦保险", "industry": "保险", "weight": 6.0},
        ),
    },
)


def _normalize_indicator_token(indicator: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", indicator.strip().lower()).strip("_")
    collapsed = normalized.replace("_", "")
    return _ETF_INDICATOR_ALIASES.get(normalized) or _ETF_INDICATOR_ALIASES.get(collapsed) or normalized


def _parse_trade_date(curr_date: str) -> datetime:
    return datetime.strptime(curr_date, "%Y-%m-%d")


def _safe_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}{suffix}"


def _load_etf_profile_row(ticker: str) -> tuple[str, pd.Series]:
    ts_code = _normalize_ts_code(ticker)
    profile = _query_pro("fund_basic", ts_code=ts_code)
    if profile is None or profile.empty:
        return ts_code, pd.Series(dtype=object)
    row = profile.iloc[0].copy()
    row["asset_scope"] = row.get("asset_scope") or _infer_etf_asset_scope(row)
    row["exposure_bucket"] = row.get("exposure_bucket") or _infer_etf_exposure_bucket(row)
    return ts_code, row


def _match_commodity_proxy_basket(profile_row: pd.Series) -> dict[str, object] | None:
    if profile_row is None or getattr(profile_row, "empty", False):
        return None
    asset_scope = str(profile_row.get("asset_scope", "") or "").strip().lower()
    exposure_bucket = str(profile_row.get("exposure_bucket", "") or "").strip().lower()
    text = " ".join(
        str(profile_row.get(column, "") or "")
        for column in ("name", "benchmark", "fund_type", "invest_type", "market")
    ).lower()
    if asset_scope != "commodity" and exposure_bucket != "commodity_real_asset":
        return None
    for basket in _COMMODITY_PRODUCER_PROXY_BASKETS:
        if any(keyword.lower() in text for keyword in basket["keywords"]):
            return basket
    return _GENERIC_COMMODITY_PRODUCER_PROXY_BASKET


def _build_commodity_producer_proxy_frame(
    ticker: str,
    curr_date: str,
    limit: int,
) -> tuple[str, str, pd.DataFrame]:
    ts_code, profile_row = _load_etf_profile_row(ticker)
    basket = _match_commodity_proxy_basket(profile_row)
    if not basket:
        return ts_code, "", pd.DataFrame()

    frame = pd.DataFrame(basket["members"][: max(1, int(limit))]).copy()
    if frame.empty:
        return ts_code, "", pd.DataFrame()
    frame.attrs["source"] = "commodity_producer_proxy"
    frame.attrs["proxy_label"] = basket["label"]
    frame.attrs["display_label"] = basket.get("display_label", basket["label"])
    frame.attrs["source_note"] = (
        f"No equity holdings are disclosed for {ts_code}; this commodity ETF primarily tracks the underlying "
        f"{basket['label']} price reference. The basket below lists representative A-share "
        f"{basket.get('display_label', basket['label'])} producers as a correlated research reference only. "
        "Proxy weights are illustrative and do not reflect the ETF's actual exposure structure; "
        "commodity ETFs typically track a price reference rather than equity holdings. "
        f"Producer-stock returns can decouple from spot {basket['label']} due to operating leverage, hedging, "
        "and idiosyncratic risk, so treat these producer theses as supplementary rather than ETF top-holding analysis."
    )
    return ts_code, f"proxy basket as of {curr_date}", frame


def _render_commodity_producer_proxy_holdings(
    ts_code: str,
    curr_date: str,
    proxy_frame: pd.DataFrame,
) -> str:
    if proxy_frame is None or proxy_frame.empty:
        return f"No ETF holdings data found for '{ts_code}' up to {curr_date}."
    proxy_label = str(proxy_frame.attrs.get("display_label", proxy_frame.attrs.get("proxy_label", "商品")))
    source_note = str(proxy_frame.attrs.get("source_note", "")).strip()
    output = proxy_frame.rename(columns={"weight": "proxy_weight_illustrative_pct"}).reset_index(drop=True)
    summary_lines = [
        f"Ticker: {ts_code}",
        f"Proxy basket: A-share {proxy_label} producers",
    ]
    if source_note:
        summary_lines.append(f"Note: {source_note}")
    return _to_csv_with_header(
        output,
        f"ETF holdings proxy basket for {ts_code}",
        summary_lines,
    )


def _match_hk_benchmark_proxy_basket(profile_row: pd.Series) -> dict[str, object] | None:
    if profile_row is None or getattr(profile_row, "empty", False):
        return None
    asset_scope = str(profile_row.get("asset_scope", "") or "").strip().lower()
    text = " ".join(
        str(profile_row.get(column, "") or "")
        for column in ("name", "benchmark", "fund_type", "invest_type", "market", "asset_scope")
    ).lower()
    if asset_scope != "cross_border" and not any(token in text for token in ("港股", "香港", "恒生", "hong kong", "hang seng")):
        return None
    for basket in _HK_BENCHMARK_PROXY_BASKETS:
        if any(keyword.lower() in text for keyword in basket["keywords"]):
            return basket
    return None


def _lookup_hk_metadata(ts_code: str, fallback_name: str, fallback_industry: str) -> dict[str, str]:
    try:
        basic = _query_pro("hk_basic", ts_code=ts_code)
    except Exception:
        basic = pd.DataFrame()
    if basic is None or basic.empty:
        return {"ts_code": ts_code, "name": fallback_name or ts_code, "industry": fallback_industry or "Hong Kong equity"}
    row = basic.iloc[0]
    return {
        "ts_code": str(row.get("ts_code", ts_code) or ts_code),
        "name": str(row.get("name", fallback_name or ts_code) or fallback_name or ts_code),
        "industry": fallback_industry or str(row.get("market", "Hong Kong equity") or "Hong Kong equity"),
    }


def _lookup_hk_latest_price(ts_code: str, curr_date: str) -> dict[str, object]:
    end_dt = _parse_trade_date(curr_date)
    start_api = (end_dt - timedelta(days=40)).strftime("%Y%m%d")
    end_api = end_dt.strftime("%Y%m%d")
    try:
        daily = _query_pro("hk_daily", ts_code=ts_code, start_date=start_api, end_date=end_api)
    except Exception:
        daily = pd.DataFrame()
    if daily is None or daily.empty:
        return {}
    if "trade_date" in daily.columns:
        daily = daily[daily["trade_date"].astype(str) <= end_api].sort_values("trade_date", ascending=False)
    if daily.empty:
        return {}
    row = daily.iloc[0]
    return {
        "latest_trade_date": row.get("trade_date"),
        "latest_close": _safe_float(row.get("close")),
        "latest_pct_chg": _safe_float(row.get("pct_chg")),
    }


def _build_hk_benchmark_proxy_frame(
    ticker: str,
    curr_date: str,
    limit: int,
) -> tuple[str, str, pd.DataFrame]:
    ts_code, profile_row = _load_etf_profile_row(ticker)
    basket = _match_hk_benchmark_proxy_basket(profile_row)
    if not basket:
        return ts_code, "", pd.DataFrame()

    rows: list[dict[str, object]] = []
    latest_trade_date = ""
    for member in basket["members"][: max(1, int(limit))]:
        member_code = _normalize_ts_code(str(member["ts_code"]))
        metadata = _lookup_hk_metadata(
            member_code,
            str(member.get("name", "")),
            str(member.get("industry", "")),
        )
        price = _lookup_hk_latest_price(member_code, curr_date)
        if price.get("latest_trade_date") and not latest_trade_date:
            latest_trade_date = str(price["latest_trade_date"])
        rows.append(
            {
                "ts_code": metadata["ts_code"],
                "name": metadata["name"],
                "industry": metadata["industry"],
                "weight": _safe_float(member.get("weight")) or 0.0,
                **price,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return ts_code, "", frame
    label = str(basket["label"])
    frame.attrs["source"] = "hk_benchmark_proxy"
    frame.attrs["proxy_label"] = label
    frame.attrs["display_label"] = label
    frame.attrs["source_note"] = (
        f"No disclosed fund_portfolio holdings were available for {ts_code}. "
        f"This fallback uses a representative Hong Kong equity basket for the {label} benchmark exposure, "
        "enriched with Tushare hk_basic and hk_daily where available. "
        "Weights are illustrative proxy weights, not official ETF holdings or index weights."
    )
    return ts_code, latest_trade_date or curr_date.replace("-", ""), frame


def _render_hk_benchmark_proxy_holdings(
    ts_code: str,
    curr_date: str,
    proxy_frame: pd.DataFrame,
) -> str:
    if proxy_frame is None or proxy_frame.empty:
        return f"No ETF holdings data found for '{ts_code}' up to {curr_date}."
    proxy_label = str(proxy_frame.attrs.get("display_label", proxy_frame.attrs.get("proxy_label", "港股")))
    source_note = str(proxy_frame.attrs.get("source_note", "")).strip()
    output = proxy_frame.rename(
        columns={
            "weight": "proxy_weight_illustrative_pct",
            "latest_close": "latest_hk_close",
            "latest_pct_chg": "latest_hk_pct_chg",
        }
    ).reset_index(drop=True)
    summary_lines = [
        f"Ticker: {ts_code}",
        f"Proxy basket: Hong Kong {proxy_label} constituents",
    ]
    if source_note:
        summary_lines.append(f"Note: {source_note}")
    return _to_csv_with_header(
        output,
        f"ETF holdings proxy basket for {ts_code}",
        summary_lines,
    )


def _nearest_observation(series: pd.Series, target_dt: datetime) -> float | None:
    if series is None or series.empty:
        return None
    eligible = series.loc[:pd.Timestamp(target_dt)]
    if eligible.empty:
        return None
    return _safe_float(eligible.iloc[-1])


def _frame_to_series(df: pd.DataFrame, date_column: str, value_column: str) -> pd.Series:
    if df is None or df.empty or date_column not in df.columns or value_column not in df.columns:
        return pd.Series(dtype=float)
    normalized = df[[date_column, value_column]].copy()
    normalized[date_column] = pd.to_datetime(normalized[date_column], errors="coerce")
    normalized[value_column] = pd.to_numeric(normalized[value_column], errors="coerce")
    normalized = normalized.dropna(subset=[date_column, value_column]).sort_values(date_column)
    if normalized.empty:
        return pd.Series(dtype=float)
    return normalized.set_index(date_column)[value_column]


def _load_fred_csv_series(series_id: str, curr_date: str, look_back_days: int = 540) -> pd.Series:
    end_dt = _parse_trade_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={
                "id": series_id,
                "cosd": start_dt.strftime("%Y-%m-%d"),
                "coed": end_dt.strftime("%Y-%m-%d"),
            },
            timeout=15,
        )
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
    except Exception:
        return pd.Series(dtype=float)
    if df.empty or "DATE" not in df.columns:
        return pd.Series(dtype=float)
    value_column = next((column for column in df.columns if column != "DATE"), None)
    if value_column is None:
        return pd.Series(dtype=float)
    return _frame_to_series(df, "DATE", value_column)


def _load_fred_series(series_id: str, curr_date: str, look_back_days: int = 540) -> pd.Series:
    end_dt = _parse_trade_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    api_key = (
        os.getenv("FRED_API_KEY")
        or os.getenv("FRED_API_TOKEN")
        or os.getenv("FRED_KEY")
    )
    if api_key:
        try:
            response = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": start_dt.strftime("%Y-%m-%d"),
                    "observation_end": end_dt.strftime("%Y-%m-%d"),
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            observations = payload.get("observations", [])
            df = pd.DataFrame(
                [
                    {"DATE": item.get("date"), "VALUE": item.get("value")}
                    for item in observations
                    if item.get("value") not in (None, ".", "")
                ]
            )
            series = _frame_to_series(df, "DATE", "VALUE")
            if not series.empty:
                return series
        except Exception:
            pass
    return _load_fred_csv_series(series_id, curr_date, look_back_days)


def _load_tushare_series(
    api_name: str,
    curr_date: str,
    value_column: str,
    date_column: str,
    look_back_days: int = 540,
    **params,
) -> pd.Series:
    end_dt = _parse_trade_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    try:
        df = _query_pro(
            api_name,
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            **params,
        )
    except DataVendorUnavailable:
        return pd.Series(dtype=float)
    return _frame_to_series(df, date_column, value_column)


@lru_cache(maxsize=32)
def _load_cn_schedule_frame(curr_date: str) -> pd.DataFrame:
    current_dt = _parse_trade_date(curr_date)
    months = []
    for offset_days in (-31, 0, 31):
        month = (current_dt + timedelta(days=offset_days)).strftime("%Y%m")
        if month not in months:
            months.append(month)
    frames: list[pd.DataFrame] = []
    for month in months:
        try:
            frame = _query_pro("cn_schedule", m=month)
        except DataVendorUnavailable:
            continue
        if frame is None or frame.empty:
            continue
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    if "publish_date" not in merged.columns:
        return pd.DataFrame()
    merged = merged.copy()
    merged["publish_date"] = pd.to_datetime(merged["publish_date"], errors="coerce")
    merged = merged.dropna(subset=["publish_date"]).sort_values("publish_date")
    if merged.empty:
        return pd.DataFrame()
    keep_columns = [column for column in ("publish_date", "title", "issuing_org", "data_api") if column in merged.columns]
    merged = merged[keep_columns].drop_duplicates()
    return merged.reset_index(drop=True)


def _load_china_policy_rate_series(curr_date: str, look_back_days: int = 540) -> pd.Series:
    lpr_series = _load_tushare_series(
        "shibor_lpr",
        curr_date,
        "1y",
        "date",
        look_back_days,
    )
    if not lpr_series.empty:
        return lpr_series
    return _load_tushare_series(
        "shibor",
        curr_date,
        "3m",
        "date",
        look_back_days,
    )


def _load_china_ten_year_yield_series(curr_date: str, look_back_days: int = 540) -> pd.Series:
    series = _load_tushare_series(
        "yc_cb",
        curr_date,
        "yield",
        "trade_date",
        look_back_days,
        ts_code="1001.CB",
        curve_type="0",
        curve_term=10,
    )
    if not series.empty:
        return series
    return _load_fred_series("IRLTLT01CNM156N", curr_date, look_back_days)


def _load_yfinance_close(symbol: str, curr_date: str, look_back_days: int = 240) -> pd.Series:
    try:
        import yfinance as yf
    except ImportError:
        return pd.Series(dtype=float)

    end_dt = _parse_trade_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    try:
        history = yf.download(
            symbol,
            start=start_dt.strftime("%Y-%m-%d"),
            end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            actions=False,
            threads=False,
        )
    except Exception:
        return pd.Series(dtype=float)
    if history is None or history.empty or "Close" not in history:
        return pd.Series(dtype=float)
    close = history["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if close.empty:
        return pd.Series(dtype=float)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def _series_latest_and_delta(series: pd.Series, curr_date: str, days_back: int) -> tuple[float | None, float | None]:
    latest = _nearest_observation(series, _parse_trade_date(curr_date))
    previous = _nearest_observation(
        series,
        _parse_trade_date(curr_date) - timedelta(days=days_back),
    )
    if latest is None or previous is None:
        return latest, None
    return latest, latest - previous


def _series_latest_and_pct(series: pd.Series, curr_date: str, days_back: int) -> tuple[float | None, float | None]:
    latest = _nearest_observation(series, _parse_trade_date(curr_date))
    previous = _nearest_observation(
        series,
        _parse_trade_date(curr_date) - timedelta(days=days_back),
    )
    if latest is None or previous in (None, 0):
        return latest, None
    return latest, (latest / previous - 1) * 100


@lru_cache(maxsize=64)
def _load_tushare_futures_main_frame(
    fut_code: str,
    exchange: str,
    curr_date: str,
    look_back_days: int = 240,
) -> pd.DataFrame:
    start_dt = _parse_trade_date(curr_date) - timedelta(days=look_back_days)
    start_api = start_dt.strftime("%Y%m%d")
    end_api = _parse_trade_date(curr_date).strftime("%Y%m%d")
    try:
        contracts = _query_pro(
            "fut_basic",
            exchange=exchange,
            fut_code=fut_code,
            fields="ts_code,symbol,name,list_date,delist_date",
        )
    except DataVendorUnavailable:
        return pd.DataFrame()
    if contracts is None or contracts.empty:
        return pd.DataFrame()

    catalog = contracts.copy()
    if "list_date" in catalog.columns:
        catalog = catalog[catalog["list_date"].astype(str) <= end_api]
    if "delist_date" in catalog.columns:
        catalog = catalog[catalog["delist_date"].astype(str) >= start_api]
    if catalog.empty:
        return pd.DataFrame()

    if "delist_date" in catalog.columns:
        catalog = catalog.sort_values("delist_date")
    catalog = catalog.tail(12)

    frames: list[pd.DataFrame] = []
    for ts_code in catalog.get("ts_code", pd.Series(dtype=str)).dropna().astype(str).tolist():
        try:
            frame = _query_pro(
                "fut_daily",
                ts_code=ts_code,
                start_date=start_api,
                end_date=end_api,
                fields="ts_code,trade_date,close,settle,vol,oi",
            )
        except DataVendorUnavailable:
            continue
        if frame is None or frame.empty:
            continue
        frames.append(frame)
    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    if "trade_date" not in merged.columns:
        return pd.DataFrame()
    merged["trade_date"] = pd.to_datetime(merged["trade_date"], errors="coerce")
    for column in ("close", "settle", "vol", "oi"):
        if column not in merged.columns:
            merged[column] = pd.NA
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged = merged.dropna(subset=["trade_date"]).sort_values(["trade_date", "oi", "vol"])
    if merged.empty:
        return pd.DataFrame()

    main = (
        merged.sort_values(
            ["trade_date", "oi", "vol"],
            ascending=[True, False, False],
        )
        .drop_duplicates(subset=["trade_date"], keep="first")
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    return main


@lru_cache(maxsize=64)
def _load_tushare_warehouse_series(
    symbol: str,
    exchange: str,
    curr_date: str,
    look_back_days: int = 240,
) -> pd.Series:
    start_dt = _parse_trade_date(curr_date) - timedelta(days=look_back_days)
    try:
        frame = _query_pro(
            "fut_wsr",
            symbol=symbol,
            exchange=exchange,
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=_parse_trade_date(curr_date).strftime("%Y%m%d"),
        )
    except DataVendorUnavailable:
        return pd.Series(dtype=float)
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    if "trade_date" not in frame.columns or "vol" not in frame.columns:
        return pd.Series(dtype=float)
    aggregated = frame.copy()
    aggregated["trade_date"] = pd.to_datetime(aggregated["trade_date"], errors="coerce")
    aggregated["vol"] = pd.to_numeric(aggregated["vol"], errors="coerce")
    aggregated = aggregated.dropna(subset=["trade_date", "vol"])
    if aggregated.empty:
        return pd.Series(dtype=float)
    totals = aggregated.groupby("trade_date")["vol"].sum().sort_index()
    totals.index = pd.to_datetime(totals.index).tz_localize(None)
    return totals


def _describe_commodity_anomaly(
    price_30d: float | None,
    oi_30d: float | None,
    warehouse_30d: float | None,
) -> str:
    notes: list[str] = []
    if price_30d is not None and abs(price_30d) >= 8:
        notes.append(f"30D price move {price_30d:+.1f}% is large versus the recent baseline")
    if oi_30d is not None and abs(oi_30d) >= 15:
        notes.append(f"open interest {oi_30d:+.1f}% signals a meaningful positioning change")
    if price_30d is not None and oi_30d is not None:
        if price_30d > 0 and oi_30d > 0:
            notes.append("price and open interest are rising together, suggesting fresh long participation")
        elif price_30d < 0 and oi_30d > 0:
            notes.append("price is falling while open interest rises, suggesting new shorts rather than simple profit-taking")
        elif price_30d > 0 and oi_30d < 0:
            notes.append("price is rising while open interest falls, so the move may reflect short covering more than durable demand")
    if warehouse_30d is not None and abs(warehouse_30d) >= 15:
        direction = "inventory pressure" if warehouse_30d > 0 else "inventory tightening"
        notes.append(f"warehouse receipts {warehouse_30d:+.1f}% point to {direction}")
    if not notes:
        return "No single anomaly dominates; watch whether price starts moving without open-interest or warehouse confirmation."
    return "; ".join(notes)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header_line = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([header_line, divider, body])


def _json_safe_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (str, bool, int, float)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


def _serialize_series(series: pd.Series) -> list[dict[str, Any]]:
    if series is None or series.empty:
        return []
    normalized = series.dropna().sort_index()
    records: list[dict[str, Any]] = []
    for index, value in normalized.items():
        timestamp = pd.Timestamp(index)
        records.append(
            {
                "date": timestamp.strftime("%Y-%m-%d"),
                "value": _safe_float(value),
            }
        )
    return records


def _deserialize_series(records: list[dict[str, Any]] | None) -> pd.Series:
    if not records:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(records)
    return _frame_to_series(frame, "date", "value")


def _serialize_frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                str(key): _json_safe_scalar(value)
                for key, value in row.items()
            }
        )
    return records


def _deserialize_schedule_frame(records: list[dict[str, Any]] | None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records)
    if "publish_date" in frame.columns:
        frame["publish_date"] = pd.to_datetime(frame["publish_date"], errors="coerce")
    return frame


def _validate_cached_payload(
    payload: dict[str, Any],
    snapshot_kind: str,
    key: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise DailySnapshotCacheError(
            f"Corrupted {snapshot_kind} shared snapshot payload: root payload must be an object."
        )
    value = payload.get(key)
    if not isinstance(value, list):
        raise DailySnapshotCacheError(
            f"Corrupted {snapshot_kind} shared snapshot payload: '{key}' must be a list."
        )
    return value


def _load_cached_snapshot_payload(
    snapshot_kind: str,
    curr_date: str,
    look_back_days: int,
    builder,
) -> dict[str, Any]:
    payload, cache_hit = get_or_build_shared_snapshot(
        snapshot_kind=snapshot_kind,
        curr_date=curr_date,
        min_coverage_days=look_back_days,
        schema_version=_SHARED_SNAPSHOT_SCHEMA_VERSION[snapshot_kind],
        builder=builder,
    )
    logger.debug(
        "%s %s shared snapshot for %s (coverage=%s days)",
        "Reused cached" if cache_hit else "Built",
        snapshot_kind,
        curr_date,
        look_back_days,
    )
    return payload


def _build_macro_snapshot_payload(
    curr_date: str,
    look_back_days: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rate_specs = [
        ("United States", lambda: _load_fred_series("FEDFUNDS", curr_date, look_back_days), lambda: _load_fred_series("DGS10", curr_date, look_back_days)),
        ("Euro Area / Germany proxy", lambda: _load_fred_series("ECBDFR", curr_date, look_back_days), lambda: _load_fred_series("IRLTLT01DEM156N", curr_date, look_back_days)),
        ("Japan", lambda: _load_fred_series("IR3TIB01JPM156N", curr_date, look_back_days), lambda: _load_fred_series("IRLTLT01JPM156N", curr_date, look_back_days)),
        ("China", lambda: _load_china_policy_rate_series(curr_date, look_back_days), lambda: _load_china_ten_year_yield_series(curr_date, look_back_days)),
    ]
    rates = [
        {
            "economy": economy,
            "policy_short_series": _serialize_series(short_loader()),
            "ten_year_series": _serialize_series(long_loader()),
        }
        for economy, short_loader, long_loader in rate_specs
    ]
    safe_havens = [
        {
            "label": label,
            "symbol": symbol,
            "invert_pct": invert,
            "close_series": _serialize_series(
                _load_yfinance_close(symbol, curr_date, look_back_days)
            ),
        }
        for label, symbol, invert in _MACRO_SAFE_HAVEN_SPECS
    ]
    start_date, end_date = _date_window(curr_date, look_back_days)
    return (
        {
            "rates": rates,
            "tips_real_series": _serialize_series(
                _load_fred_series("DFII10", curr_date, look_back_days)
            ),
            "ccc_spread_series": _serialize_series(
                _load_fred_series("BAMLH0A3HYC", curr_date, look_back_days)
            ),
            "safe_havens": safe_havens,
            "china_calendar": _serialize_frame_records(
                _load_cn_schedule_frame(curr_date)
            ),
        },
        {
            "coverage_start_date": start_date,
            "coverage_end_date": end_date,
            "source_summary": "FRED, Tushare, YFinance, cn_schedule",
        },
    )


def _render_macro_snapshot(curr_date: str, payload: dict[str, Any]) -> str:
    rate_rows: list[list[str]] = []
    rate_levels: dict[str, tuple[float | None, float | None]] = {}
    for item in _validate_cached_payload(payload, "macro", "rates"):
        economy = str(item.get("economy", "Unknown"))
        short_values = _deserialize_series(item.get("policy_short_series"))
        long_values = _deserialize_series(item.get("ten_year_series"))
        short_level, short_delta = _series_latest_and_delta(short_values, curr_date, 30)
        long_level, long_delta = _series_latest_and_delta(long_values, curr_date, 30)
        rate_levels[economy] = (short_level, long_level)
        rate_rows.append(
            [
                economy,
                _format_number(short_level, suffix="%"),
                _format_number(short_delta, suffix="ppt"),
                _format_number(long_level, suffix="%"),
                _format_number(long_delta, suffix="ppt"),
            ]
        )

    us_short, us_ten = rate_levels.get("United States", (None, None))
    cn_short, cn_ten = rate_levels.get("China", (None, None))
    de_short, de_ten = rate_levels.get("Euro Area / Germany proxy", (None, None))
    jp_short, jp_ten = rate_levels.get("Japan", (None, None))

    tips_real = _deserialize_series(payload.get("tips_real_series"))
    ccc_spread = _deserialize_series(payload.get("ccc_spread_series"))
    tips_level, tips_delta = _series_latest_and_delta(tips_real, curr_date, 30)
    ccc_level, ccc_delta = _series_latest_and_delta(ccc_spread, curr_date, 30)

    safe_haven_rows: list[list[str]] = []
    safe_haven_changes: dict[str, float | None] = {}
    gold_series = pd.Series(dtype=float)
    for item in _validate_cached_payload(payload, "macro", "safe_havens"):
        label = str(item.get("label", "Unknown"))
        symbol = str(item.get("symbol", "N/A"))
        invert_pct = bool(item.get("invert_pct", False))
        series = _deserialize_series(item.get("close_series"))
        latest, pct_change = _series_latest_and_pct(series, curr_date, 30)
        if pct_change is not None and invert_pct:
            pct_change = -pct_change
        safe_haven_changes[label] = pct_change
        if label == "Gold":
            gold_series = series
        safe_haven_rows.append(
            [
                label,
                symbol,
                _format_number(latest),
                _format_number(pct_change, suffix="%"),
            ]
        )

    gold_latest, gold_pct_3m = _series_latest_and_pct(gold_series, curr_date, 90)
    _, tips_delta_3m = _series_latest_and_delta(tips_real, curr_date, 90)

    divergence_note = "Gold / real-rate divergence is inconclusive."
    if gold_pct_3m is not None and tips_delta_3m is not None:
        if gold_pct_3m > 5 and tips_delta_3m >= 0:
            divergence_note = (
                "Gold has appreciated even as 10Y TIPS real yields held firm or rose, "
                "which points to a structural/systemic risk premium rather than a simple easing narrative."
            )
        elif gold_pct_3m < 0 and tips_delta_3m > 0:
            divergence_note = (
                "Gold has softened while real yields moved up, which is more consistent with a conventional tightening shock."
            )

    liquidity_note = "10Y TIPS data unavailable."
    if tips_level is not None:
        if tips_level < 0.5:
            liquidity_note = (
                "US 10Y real yields remain low, so nominal rate pressure still looks partly inflation-driven rather than fully restrictive."
            )
        elif tips_level < 1.5:
            liquidity_note = (
                "US 10Y real yields are positive but not yet at obviously extreme levels; liquidity is tightening, though not frozen."
            )
        else:
            liquidity_note = (
                "US 10Y real yields are high enough to signal meaningfully restrictive real funding costs and tighter global liquidity."
            )

    spread_rows = [
        ["US - China short-rate spread", _format_number((us_short - cn_short) if us_short is not None and cn_short is not None else None, suffix="ppt")],
        ["US - China 10Y spread", _format_number((us_ten - cn_ten) if us_ten is not None and cn_ten is not None else None, suffix="ppt")],
        ["US - Germany 10Y spread", _format_number((us_ten - de_ten) if us_ten is not None and de_ten is not None else None, suffix="ppt")],
        ["US - Japan 10Y spread", _format_number((us_ten - jp_ten) if us_ten is not None and jp_ten is not None else None, suffix="ppt")],
    ]
    macro_anomalies: list[list[str]] = []
    us_cn_short_spread = (us_short - cn_short) if us_short is not None and cn_short is not None else None
    us_cn_ten_spread = (us_ten - cn_ten) if us_ten is not None and cn_ten is not None else None
    if us_cn_short_spread is not None and abs(us_cn_short_spread) >= 1.0:
        macro_anomalies.append([
            "US-China short-rate spread",
            _format_number(us_cn_short_spread, suffix="ppt"),
            "Large short-rate gaps are a live capital-flow driver and can distort growth-style ETF valuation."
        ])
    if us_cn_ten_spread is not None and abs(us_cn_ten_spread) >= 1.0:
        macro_anomalies.append([
            "US-China 10Y spread",
            _format_number(us_cn_ten_spread, suffix="ppt"),
            "A wide long-end spread changes global duration pricing and cross-border risk appetite."
        ])
    if tips_delta is not None and abs(tips_delta) >= 0.2:
        macro_anomalies.append([
            "US 10Y TIPS real-yield shock",
            _format_number(tips_delta, suffix="ppt"),
            "A fast real-yield move changes the true funding cost facing long-duration and growth-sensitive ETFs."
        ])
    if ccc_delta is not None and abs(ccc_delta) >= 40:
        macro_anomalies.append([
            "CCC HY spread repricing",
            _format_number(ccc_delta, suffix="bps"),
            "A large HY spread move is often the cleanest early warning that risk capital is tightening or re-opening."
        ])
    haven_moves = [
        safe_haven_changes.get("Gold"),
        safe_haven_changes.get("Dollar Index"),
        safe_haven_changes.get("Swiss franc safe-haven bid"),
        safe_haven_changes.get("Japanese yen safe-haven bid"),
    ]
    if all(value is not None and value > 0 for value in haven_moves):
        macro_anomalies.append([
            "Safe-haven synchrony",
            "Gold/DXY/CHF/JPY all positive",
            "This is unusual enough to treat as a broad de-risking signal rather than an isolated market move."
        ])
    if gold_pct_3m is not None and tips_delta_3m is not None and gold_pct_3m > 5 and tips_delta_3m >= 0:
        macro_anomalies.append([
            "Gold-vs-real-yield divergence",
            f"Gold {_format_number(gold_pct_3m, suffix='%')} with TIPS Δ {_format_number(tips_delta_3m, suffix='ppt')}",
            "Gold rising despite firmer real yields implies a systemic-risk premium rather than a simple easing trade."
        ])

    schedule_df = _deserialize_schedule_frame(payload.get("china_calendar"))
    calendar_rows: list[list[str]] = []
    if schedule_df is not None and not schedule_df.empty:
        current_dt = _parse_trade_date(curr_date)
        window = schedule_df[
            (schedule_df["publish_date"] >= pd.Timestamp(current_dt - timedelta(days=7)))
            & (schedule_df["publish_date"] <= pd.Timestamp(current_dt + timedelta(days=35)))
        ].head(12)
        for _, row in window.iterrows():
            publish_date = row.get("publish_date")
            calendar_rows.append(
                [
                    publish_date.strftime("%Y-%m-%d") if hasattr(publish_date, "strftime") else str(publish_date),
                    str(row.get("title", "N/A")),
                    str(row.get("issuing_org", "N/A")),
                    str(row.get("data_api", "N/A")),
                ]
            )

    return "\n\n".join(
        [
            f"# Global Macro Regime Snapshot ({curr_date})",
            "Data sources: overseas policy/benchmark rates and sovereign yields are pulled from FRED; China short-rate and 10Y government-bond data are pulled from Tushare (LPR / 中债国债收益率曲线, with a FRED fallback only if the Tushare curve is unavailable). China macro release scheduling is pulled from Tushare cn_schedule (used here as the eco-calendar feed).",
            "## Global rate map",
            _markdown_table(
                ["Economy", "Policy / Short Rate", "30D Δ", "10Y Yield", "30D Δ"],
                rate_rows,
            ),
            "## Cross-market spreads",
            _markdown_table(["Spread", "Latest"], spread_rows),
            "## Key anomalies",
            _markdown_table(
                ["Anomaly", "Evidence", "Why it matters for ETF allocation"],
                macro_anomalies or [["None dominant", "N/A", "Current macro signals are notable but not yet extreme enough to dominate ETF allocation by themselves."]],
            ),
            "## China macro release calendar (eco-calendar) around the next rebalance window",
            _markdown_table(
                ["Publish date", "Release", "Issuing org", "Tushare API"],
                calendar_rows or [["N/A", "No cn_schedule entries available around this date", "N/A", "N/A"]],
            ),
            "## Real rates and credit risk pricing",
            _markdown_table(
                ["Signal", "Latest", "30D Δ", "Interpretation"],
                [
                    [
                        "US 10Y TIPS real yield",
                        _format_number(tips_level, suffix="%"),
                        _format_number(tips_delta, suffix="ppt"),
                        liquidity_note,
                    ],
                    [
                        "CCC HY credit spread",
                        _format_number(ccc_level, suffix="bps"),
                        _format_number(ccc_delta, suffix="bps"),
                        (
                            "A fast widening here is the cleanest sign that capital is leaving risky assets."
                            if ccc_level is not None
                            else "N/A"
                        ),
                    ],
                ],
            ),
            "## Geopolitical stress / safe-haven proxies",
            _markdown_table(
                ["Proxy", "Symbol", "Latest", "30D %"],
                safe_haven_rows,
            ),
            "## Capital-flow inference",
            (
                "When gold, DXY, CHF, and JPY proxies rise together, global capital is usually rotating away from growth-sensitive exposures "
                "toward neutrality and protection. Current proxy moves: "
                f"gold {_format_number(safe_haven_changes.get('Gold'), suffix='%')}, "
                f"DXY {_format_number(safe_haven_changes.get('Dollar Index'), suffix='%')}, "
                f"CHF {_format_number(safe_haven_changes.get('Swiss franc safe-haven bid'), suffix='%')}, "
                f"JPY {_format_number(safe_haven_changes.get('Japanese yen safe-haven bid'), suffix='%')}."
            ),
            "## Structural-fragmentation pricing check",
            f"Gold 3M move: {_format_number(gold_pct_3m, suffix='%')} at spot {_format_number(gold_latest)}. {divergence_note}",
        ]
    )


def _build_macro_snapshot(curr_date: str, look_back_days: int = 365) -> str:
    payload = _load_cached_snapshot_payload(
        "macro",
        curr_date,
        look_back_days,
        _build_macro_snapshot_payload,
    )
    return _render_macro_snapshot(curr_date, payload)


def _build_commodity_snapshot_payload(
    curr_date: str,
    look_back_days: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for cluster, symbol, exchange, reference, macro_variable in _COMMODITY_SPECS:
        close_series = pd.Series(dtype=float)
        oi_series = pd.Series(dtype=float)
        warehouse_series = pd.Series(dtype=float)
        try:
            frame = _load_tushare_futures_main_frame(
                symbol,
                exchange,
                curr_date,
                look_back_days,
            )
            close_series = _frame_to_series(frame, "trade_date", "close")
            oi_series = _frame_to_series(frame, "trade_date", "oi")
            warehouse_series = _load_tushare_warehouse_series(
                symbol,
                exchange,
                curr_date,
                look_back_days,
            )
        except Exception:
            pass
        contracts.append(
            {
                "cluster": cluster,
                "symbol": symbol,
                "exchange": exchange,
                "reference": reference,
                "macro_variable": macro_variable,
                "close_series": _serialize_series(close_series),
                "oi_series": _serialize_series(oi_series),
                "warehouse_series": _serialize_series(warehouse_series),
            }
        )
    start_date, end_date = _date_window(curr_date, look_back_days)
    return (
        {"contracts": contracts},
        {
            "coverage_start_date": start_date,
            "coverage_end_date": end_date,
            "source_summary": "Tushare futures daily and warehouse receipts",
        },
    )


def _render_commodity_snapshot(curr_date: str, payload: dict[str, Any]) -> str:
    rows: list[list[str]] = []
    anomaly_rows: list[list[str]] = []
    for item in _validate_cached_payload(payload, "commodity", "contracts"):
        cluster = str(item.get("cluster", "Unknown"))
        reference = str(item.get("reference", "N/A"))
        macro_variable = str(item.get("macro_variable", "N/A"))
        close_series = _deserialize_series(item.get("close_series"))
        oi_series = _deserialize_series(item.get("oi_series"))
        warehouse_series = _deserialize_series(item.get("warehouse_series"))
        latest_price, pct_30d = _series_latest_and_pct(close_series, curr_date, 30)
        _, pct_90d = _series_latest_and_pct(close_series, curr_date, 90)
        _, oi_30d = _series_latest_and_pct(oi_series, curr_date, 30)
        _, warehouse_30d = _series_latest_and_pct(warehouse_series, curr_date, 30)
        anomaly = _describe_commodity_anomaly(pct_30d, oi_30d, warehouse_30d)
        rows.append(
            [
                cluster,
                reference,
                _format_number(latest_price),
                _format_number(pct_30d, suffix="%"),
                _format_number(pct_90d, suffix="%"),
                _format_number(oi_30d, suffix="%"),
                _format_number(warehouse_30d, suffix="%"),
                macro_variable,
            ]
        )
        anomaly_rows.append(
            [
                cluster,
                anomaly,
                "Use price/positioning/inventory anomalies as evidence for macro regime and industry-cycle judgment, not as standalone trading trivia.",
            ]
        )

    return "\n\n".join(
        [
            f"# Commodity Cluster Snapshot ({curr_date})",
            "Data sources: Tushare futures daily data stitched across the most active contracts, plus Tushare warehouse-receipt data where available. "
            "This replaces equity / ETF proxy instruments so the commodity read-through is anchored in directly traded commodity pricing and physical-inventory evidence.",
            _markdown_table(
                ["Cluster", "Reference", "Latest", "30D %", "90D %", "30D OI %", "30D WSR %", "Key macro variable signaled"],
                rows,
            ),
            "## Key anomalies",
            _markdown_table(
                ["Cluster", "Anomaly evidence", "How to use it"],
                anomaly_rows,
            ),
            "Interpret the clusters as evidence chains: precious and industrial metals map financial pricing into growth expectations; crude and lithium map policy and transition stress into margin pressure; "
            "rebar and pulp help judge China demand, inventory stress, and cost-push inflation. The goal is to isolate which anomalies are strong enough to change the ETF's macro and industry regime assessment.",
        ]
    )


def _build_commodity_snapshot(curr_date: str, look_back_days: int = 240) -> str:
    payload = _load_cached_snapshot_payload(
        "commodity",
        curr_date,
        look_back_days,
        _build_commodity_snapshot_payload,
    )
    return _render_commodity_snapshot(curr_date, payload)


def _load_latest_etf_holdings_frame(ticker: str, curr_date: str) -> tuple[str, pd.DataFrame]:
    ts_code = _normalize_ts_code(ticker)
    df = _query_pro("fund_portfolio", ts_code=ts_code)
    if "end_date" in df.columns:
        df = df[df["end_date"].astype(str) <= _parse_trade_date(curr_date).strftime("%Y%m%d")]
    if df.empty:
        raise MissingEtfHoldings(f"No ETF holdings data found for '{ts_code}' up to {curr_date}.")
    sort_columns = [col for col in ("end_date", "ann_date", "stk_mkv_ratio") if col in df.columns]
    ordered = (
        df.sort_values(by=sort_columns, ascending=[False] * len(sort_columns))
        if sort_columns
        else df.copy()
    )
    latest_end_date = str(ordered.iloc[0].get("end_date", ""))
    latest = ordered[ordered["end_date"].astype(str) == latest_end_date].copy() if "end_date" in ordered.columns else ordered.copy()
    latest["holding_weight"] = pd.to_numeric(latest.get("stk_mkv_ratio"), errors="coerce")
    latest = latest.dropna(subset=["holding_weight"]).sort_values("holding_weight", ascending=False)
    return ts_code, latest


def _normalize_constituent_code(raw_code: object) -> str | None:
    text = str(raw_code or "").strip().upper()
    if not text or text in {"NAN", "NONE"}:
        return None
    try:
        normalized = _normalize_ts_code(text)
    except DataVendorUnavailable:
        return None
    return normalized if normalized.endswith((".SH", ".SZ", ".BJ", ".HK")) else None


def _lookup_constituent_metadata(ts_code: str) -> dict[str, str]:
    if ts_code.endswith(".HK"):
        return _lookup_hk_metadata(ts_code, ts_code, "Hong Kong equity")
    try:
        basic = _get_pro_client().stock_basic(
            ts_code=ts_code,
            fields="ts_code,name,industry",
        )
    except Exception:
        basic = pd.DataFrame()
    if basic is None or basic.empty:
        return {"ts_code": ts_code, "name": ts_code, "industry": "Unknown"}
    row = basic.iloc[0]
    return {
        "ts_code": str(row.get("ts_code", ts_code)),
        "name": str(row.get("name", ts_code)),
        "industry": str(row.get("industry", "Unknown") or "Unknown"),
    }


def _lookup_a_share_metadata(ts_code: str) -> dict[str, str]:
    return _lookup_constituent_metadata(ts_code)


def _build_constituent_frame(ticker: str, curr_date: str, limit: int) -> tuple[str, str, pd.DataFrame]:
    ts_code = _normalize_ts_code(ticker)
    try:
        ts_code, holdings = _load_latest_etf_holdings_frame(ticker, curr_date)
    except MissingEtfHoldings:
        hk_ts_code, latest_trade_date, hk_proxy_frame = _build_hk_benchmark_proxy_frame(
            ticker,
            curr_date,
            limit,
        )
        if not hk_proxy_frame.empty:
            return hk_ts_code, latest_trade_date, hk_proxy_frame
        proxy_ts_code, latest_end_date, proxy_frame = _build_commodity_producer_proxy_frame(
            ticker,
            curr_date,
            limit,
        )
        if not proxy_frame.empty:
            return proxy_ts_code, latest_end_date, proxy_frame
        raise
    latest_end_date = str(holdings.iloc[0].get("end_date", "")) if not holdings.empty else ""
    enriched_rows: list[dict[str, object]] = []
    for _, row in holdings.head(max(limit, 1) * 3).iterrows():
        constituent_code = _normalize_constituent_code(row.get("symbol") or row.get("stk_code"))
        if not constituent_code:
            continue
        metadata = _lookup_constituent_metadata(constituent_code)
        enriched_rows.append(
            {
                "ts_code": metadata["ts_code"],
                "name": metadata["name"],
                "industry": metadata["industry"],
                "weight": _safe_float(row.get("holding_weight")) or 0.0,
            }
        )
    return ts_code, latest_end_date, pd.DataFrame(enriched_rows)


def _enrich_constituents_with_broker_industry(
    constituents: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if constituents is None or constituents.empty:
        return pd.DataFrame()
    try:
        pro = _get_pro_client()
    except DataVendorUnavailable:
        pro = None

    enriched = constituents.copy()
    for idx, row in enriched.iterrows():
        default_industry = str(row.get("industry", "Unknown") or "Unknown")
        keyword = default_industry
        source = "stock_basic industry"
        basic_industry = default_industry
        if pro is not None:
            try:
                resolved_keyword, source, resolved_basic = _resolve_broker_industry_keyword(
                    pro,
                    str(row.get("ts_code", "")),
                    start_date,
                    end_date,
                )
                if resolved_keyword:
                    keyword = resolved_keyword
                if resolved_basic:
                    basic_industry = resolved_basic
            except DataVendorUnavailable:
                pass
        enriched.at[idx, "research_industry"] = keyword
        enriched.at[idx, "research_industry_source"] = source
        enriched.at[idx, "base_industry"] = basic_industry
    return enriched


def _related_broker_industry_keywords(row: pd.Series | dict[str, object]) -> list[str]:
    """Return adjacent tushare industry keywords for broad agriculture sleeves."""
    text = " ".join(
        str(row.get(key, "") or "")
        for key in ("industry", "research_industry", "base_industry")
    )
    if not any(trigger in text for trigger in _AGRICULTURE_RESEARCH_TRIGGERS):
        return []

    return [keyword for keyword in _AGRICULTURE_RESEARCH_KEYWORDS if keyword]


def _format_holdings_summary(
    rows: pd.DataFrame,
    label: str,
    weight_header: str = "Weight",
) -> str:
    if rows is None or rows.empty:
        return f"No eligible A-share {label.lower()} could be derived from the latest ETF holdings disclosure."
    table_rows = [
        [
            str(idx + 1),
            str(row.get("industry", "")) if label == "Industry" else str(row.get("name", "")),
            str(row.get("name", "")),
            str(row.get("ts_code", "")),
            _format_number(_safe_float(row.get("weight")), suffix="%"),
        ]
        for idx, (_, row) in enumerate(rows.iterrows())
    ]
    return _markdown_table(
        ["Rank", label, "Representative", "Ticker", weight_header],
        table_rows,
    )


def _is_hk_proxy_frame(constituents: pd.DataFrame) -> bool:
    return str(getattr(constituents, "attrs", {}).get("source", "")) == "hk_benchmark_proxy"


def _date_window(curr_date: str, look_back_days: int) -> tuple[str, str]:
    end_dt = _parse_trade_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


@tool
def get_etf_price_data(
    symbol: Annotated[str, "ETF ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve ETF OHLCV price history for a given ticker."""
    return route_to_vendor("get_etf_price_data", symbol, start_date, end_date)


@tool
def get_etf_indicators(
    symbol: Annotated[str, "ETF ticker symbol"],
    indicator: Annotated[str, "technical indicator to retrieve"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "How many calendar days to look back"],
) -> str:
    """Retrieve ETF technical indicators from the configured vendor."""
    indicators = [item.strip() for item in indicator.split(",") if item.strip()]
    results = []
    for item in indicators:
        canonical = _normalize_indicator_token(item)
        try:
            results.append(
                route_to_vendor(
                    "get_etf_indicators",
                    symbol,
                    canonical,
                    curr_date,
                    look_back_days,
                )
            )
        except ValueError as exc:
            results.append(str(exc))
    return "\n\n".join(results)


@tool
def get_etf_info(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"] = None,
) -> str:
    """Retrieve ETF basic profile, mandate, benchmark, and fee metadata."""
    return route_to_vendor("get_etf_info", ticker, curr_date)


@tool
def get_etf_nav(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve ETF NAV history and latest NAV snapshot."""
    return route_to_vendor("get_etf_nav", ticker, curr_date)


@tool
def get_etf_holdings(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve disclosed ETF holdings and benchmark exposure clues."""
    try:
        result = route_to_vendor("get_etf_holdings", ticker, curr_date)
    except MissingEtfHoldings as exc:
        try:
            ts_code, _, hk_proxy_frame = _build_hk_benchmark_proxy_frame(ticker, curr_date, limit=8)
        except DataVendorUnavailable:
            hk_proxy_frame = pd.DataFrame()
            ts_code = ""
        if not hk_proxy_frame.empty:
            return _render_hk_benchmark_proxy_holdings(ts_code, curr_date, hk_proxy_frame)
        try:
            ts_code, _, proxy_frame = _build_commodity_producer_proxy_frame(ticker, curr_date, limit=5)
        except DataVendorUnavailable:
            return str(exc)
        if not proxy_frame.empty:
            return _render_commodity_producer_proxy_holdings(ts_code, curr_date, proxy_frame)
        return str(exc)
    return result


@tool
def get_etf_share(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve ETF share / scale changes for flow analysis."""
    return route_to_vendor("get_etf_share", ticker, curr_date)


@tool
def get_etf_universe(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"] = None,
    market: Annotated[str, "Optional exchange filter such as SH or SZ"] = None,
    asset_scope: Annotated[str, "Optional scope filter: broad_equity, sector_theme, bond, commodity, cross_border, or all"] = None,
    limit: Annotated[int, "Maximum number of ETFs to return"] = 50,
) -> str:
    """Retrieve a filtered ETF universe snapshot for candidate-pool construction."""
    return route_to_vendor("get_etf_universe", curr_date, market, asset_scope, limit)


@tool
def get_macro_regime_data(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "How many calendar days of macro history to scan"] = 365,
) -> str:
    """Build a cross-asset macro regime snapshot covering global rates, real yields, credit spreads, and safe-haven proxies."""
    return _build_macro_snapshot(curr_date, look_back_days)


@tool
def get_commodity_cluster_data(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "How many calendar days of commodity history to scan"] = 240,
) -> str:
    """Build a commodity-cluster snapshot for precious metals, industrial metals, energy, ferrous materials, and soft commodities."""
    return _build_commodity_snapshot(curr_date, look_back_days)


@tool
def get_etf_industry_research(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    top_n: Annotated[int, "How many dominant industries to analyze"] = 3,
    look_back_days: Annotated[int, "How many calendar days of broker reports to review"] = 120,
    max_reports_per_industry: Annotated[int, "Maximum broker reports per industry"] = 5,
) -> str:
    """Aggregate the ETF's dominant A-share industries and pull broker industry research for representative holdings."""
    ts_code, latest_end_date, constituents = _build_constituent_frame(ticker, curr_date, top_n)
    if constituents.empty:
        return (
            f"No eligible A-share constituents were found in the latest disclosed holdings for {ts_code}, "
            "so industry research could not be derived automatically."
        )
    start_date, end_date = _date_window(curr_date, look_back_days)
    is_hk_proxy = _is_hk_proxy_frame(constituents)
    if not is_hk_proxy:
        constituents = _enrich_constituents_with_broker_industry(constituents, start_date, end_date)
    industry_column = "industry" if is_hk_proxy else "research_industry"
    industry_view = (
        constituents.groupby(industry_column, dropna=False)["weight"]
        .sum()
        .reset_index()
        .rename(columns={industry_column: "industry", "weight": "industry_weight"})
        .sort_values("industry_weight", ascending=False)
        .head(max(1, int(top_n)))
    )
    representatives = []
    for _, industry_row in industry_view.iterrows():
        industry_name = industry_row["industry"]
        candidates = constituents[constituents[industry_column] == industry_name].sort_values("weight", ascending=False)
        if candidates.empty:
            continue
        representative = candidates.iloc[0].to_dict()
        representative["industry"] = industry_name
        representative["weight"] = _safe_float(industry_row["industry_weight"]) or 0.0
        representatives.append(representative)
    reps_df = pd.DataFrame(representatives)
    source_note = str(constituents.attrs.get("source_note", "")).strip()
    weight_header = "Proxy weight (illustrative)" if source_note else "Weight"
    aggregated_weight_label = "aggregated proxy weight (illustrative)" if source_note else "aggregated weight"
    sections = [
        f"# ETF industry research for {ts_code}",
        f"Latest holdings disclosure date: {latest_end_date or 'N/A'}",
        (
            "## Dominant Hong Kong proxy industries derived from benchmark exposure"
            if is_hk_proxy
            else "## Dominant industries derived from top holdings and broker-report industry keywords"
        ),
        _format_holdings_summary(reps_df, "Industry", weight_header=weight_header),
    ]
    if source_note:
        sections.insert(2, source_note)
    if is_hk_proxy:
        sections.append(
            "Tushare broker-report industry search is A-share only; for this Hong Kong ETF proxy, "
            "use the hk_basic/hk_daily-enriched basket above as the holdings exposure reference."
        )
    for idx, (_, row) in enumerate(reps_df.iterrows(), 1):
        base_industry = str(row.get("base_industry", "")).strip()
        industry_source = str(row.get("research_industry_source", "")).strip()
        sections.append(
            f"## Industry {idx}: {row['industry']} | {aggregated_weight_label} {_format_number(_safe_float(row.get('weight')), suffix='%')} | representative {row['name']} ({row['ts_code']})"
        )
        if is_hk_proxy:
            continue
        if industry_source:
            sections.append(f"Keyword source: {industry_source}")
        if base_industry and base_industry != str(row.get("industry", "")).strip():
            sections.append(f"Stock basic industry fallback / comparison: {base_industry}")
        extra_ind_names = _related_broker_industry_keywords(row)
        if extra_ind_names:
            sections.append(
                "Related industry keywords searched: " + ", ".join(extra_ind_names)
            )
        try:
            broker_report_kwargs = {"max_reports": max_reports_per_industry}
            if extra_ind_names:
                broker_report_kwargs["extra_ind_names"] = extra_ind_names
            sections.append(
                get_broker_reports(
                    row["ts_code"],
                    start_date,
                    end_date,
                    **broker_report_kwargs,
                )
            )
        except DataVendorUnavailable as exc:
            sections.append(f"No broker industry research was available for this sleeve: {exc}")
    return "\n\n".join(section for section in sections if section)


@tool
def get_etf_top_holdings_research(
    ticker: Annotated[str, "ETF ticker symbol"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    top_n: Annotated[int, "How many top holdings to analyze"] = 3,
    look_back_days: Annotated[int, "How many calendar days of stock reports to review"] = 120,
    max_reports_per_stock: Annotated[int, "Maximum stock reports per holding"] = 5,
) -> str:
    """Pull recent stock research for the ETF's top disclosed A-share holdings."""
    ts_code, latest_end_date, constituents = _build_constituent_frame(ticker, curr_date, top_n)
    if constituents.empty:
        return (
            f"No eligible A-share top holdings were found in the latest disclosed holdings for {ts_code}, "
            "so top-holdings stock research could not be derived automatically."
        )
    top_holdings = constituents.sort_values("weight", ascending=False).head(max(1, int(top_n))).reset_index(drop=True)
    start_date, end_date = _date_window(curr_date, look_back_days)
    source_note = str(constituents.attrs.get("source_note", "")).strip()
    is_hk_proxy = _is_hk_proxy_frame(constituents)
    weight_header = "Proxy weight (illustrative)" if source_note else "Weight"
    per_holding_weight_label = "proxy weight (illustrative)" if source_note else "portfolio weight"
    holdings_heading = (
        "## Proxy Hong Kong benchmark basket"
        if is_hk_proxy
        else "## Proxy A-share producer basket"
        if source_note
        else "## Top disclosed holdings"
    )
    sections = [
        f"# ETF top-holdings stock research for {ts_code}",
        f"Latest holdings disclosure date: {latest_end_date or 'N/A'}",
        holdings_heading,
        _format_holdings_summary(top_holdings, "Holding", weight_header=weight_header),
    ]
    if source_note:
        sections.insert(2, source_note)
    if is_hk_proxy:
        sections.append(
            "Tushare stock research reports are A-share only; for this Hong Kong ETF proxy, "
            "use hk_basic/hk_daily fields in the proxy basket for constituent-level context."
        )
    for idx, (_, row) in enumerate(top_holdings.iterrows(), 1):
        sections.append(
            f"## Holding {idx}: {row['name']} ({row['ts_code']}) | {per_holding_weight_label} {_format_number(_safe_float(row.get('weight')), suffix='%')} | industry {row['industry']}"
        )
        if is_hk_proxy:
            latest_close = _safe_float(row.get("latest_close"))
            latest_pct = _safe_float(row.get("latest_pct_chg"))
            latest_date = str(row.get("latest_trade_date", "") or "N/A")
            sections.append(
                "Tushare HK daily snapshot: "
                f"latest trade date {latest_date}, close {_format_number(latest_close)}, pct_chg {_format_number(latest_pct, suffix='%')}."
            )
            continue
        try:
            sections.append(
                get_stock_reports(
                    row["ts_code"],
                    start_date,
                    end_date,
                    max_reports=max_reports_per_stock,
                )
            )
        except DataVendorUnavailable as exc:
            sections.append(f"No stock research was available for this holding: {exc}")
    return "\n\n".join(section for section in sections if section)
