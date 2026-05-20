"""ETF detail data aggregation."""

from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _parse_csv_last_row(csv_text: str) -> dict[str, str] | None:
    if not csv_text or csv_text.startswith("No "):
        return None
    clean = []
    for line in csv_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            clean.append(line)
    if not clean:
        return None
    reader = csv.DictReader(io.StringIO("\n".join(clean)))
    rows = list(reader)
    return rows[-1] if rows else None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_etf_detail(ticker: str, curr_date: str | None = None) -> dict:
    """Aggregate ETF detail data from vendor APIs.

    Each API is called independently; failures do not block others.
    Missing fields default to None.
    """
    from etfagents.dataflows.config import get_config, set_config
    from etfagents.dataflows.interface import route_to_vendor
    from etfagents.default_config import DEFAULT_CONFIG
    import copy

    if not get_config():
        set_config(copy.deepcopy(DEFAULT_CONFIG))

    if curr_date is None:
        curr_date = date.today().isoformat()

    result: dict[str, Any] = {
        "ticker": ticker,
        "name": None,
        "market": None,
        "latest_date": None,
        "open": None, "high": None, "low": None,
        "close": None, "pct_chg": None,
        "volume": None, "amount": None,
        "unit_nav": None,
        "nav_date": None,
        "premium_discount_bps": None,
        "fund_share": None,
        "share_change_pct": None,
        "holdings": None,
        "fund_type": None,
        "establish_date": None,
        "manager": None,
        "benchmark": None,
    }

    # 1. Price data (uses start_date/end_date range)
    try:
        start_date = str(int(curr_date.replace("-", "")) - 10000)
        end_date = curr_date.replace("-", "")
        csv_text = route_to_vendor("get_etf_price_data", ticker, start_date, end_date)
        row = _parse_csv_last_row(csv_text)
        if row:
            result["latest_date"] = row.get("trade_date")
            result["open"] = _safe_float(row.get("open"))
            result["high"] = _safe_float(row.get("high"))
            result["low"] = _safe_float(row.get("low"))
            result["close"] = _safe_float(row.get("close"))
            result["pct_chg"] = _safe_float(row.get("pct_chg"))
            result["volume"] = _safe_float(row.get("vol"))
            result["amount"] = _safe_float(row.get("amount"))
    except Exception as exc:
        logger.warning("get_etf_price_data failed for %s: %s", ticker, exc)

    # 2. NAV data
    try:
        csv_text = route_to_vendor("get_etf_nav", ticker, curr_date)
        row = _parse_csv_last_row(csv_text)
        if row:
            result["unit_nav"] = _safe_float(row.get("unit_nav"))
            nav_d = row.get("end_date") or row.get("nav_date")
            if nav_d:
                result["nav_date"] = nav_d
            if result["unit_nav"] is not None and result["close"] is not None and result["unit_nav"] != 0:
                result["premium_discount_bps"] = round(
                    (result["close"] - result["unit_nav"]) / result["unit_nav"] * 10000, 2
                )
    except Exception as exc:
        logger.warning("get_etf_nav failed for %s: %s", ticker, exc)

    # 3. Fund info
    try:
        csv_text = route_to_vendor("get_etf_info", ticker, curr_date)
        row = _parse_csv_last_row(csv_text)
        if row:
            result["name"] = row.get("name")
            result["market"] = row.get("market")
            result["fund_type"] = row.get("fund_type")
            result["establish_date"] = row.get("found_date") or row.get("list_date")
            result["manager"] = row.get("management")
            result["benchmark"] = row.get("benchmark")
    except Exception as exc:
        logger.warning("get_etf_info failed for %s: %s", ticker, exc)

    # 4. Holdings
    try:
        csv_text = route_to_vendor("get_etf_holdings", ticker, curr_date)
        rows = _parse_csv_rows(csv_text, limit=10)
        if rows:
            result["holdings"] = [
                {
                    "code": r.get("symbol") or r.get("stk_code", ""),
                    "name": r.get("stk_name", ""),
                    "weight_pct": _safe_float(r.get("stk_mkv_ratio")),
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("get_etf_holdings failed for %s: %s", ticker, exc)

    # 5. Share data
    try:
        csv_text = route_to_vendor("get_etf_share", ticker, curr_date)
        rows = _parse_csv_rows(csv_text, limit=2)
        if rows:
            latest = rows[0]
            result["fund_share"] = _safe_float(latest.get("fd_share") or latest.get("fund_share"))
            if len(rows) >= 2:
                prev_share = _safe_float(rows[1].get("fd_share") or rows[1].get("fund_share"))
                if result["fund_share"] and prev_share and prev_share != 0:
                    result["share_change_pct"] = round(
                        (result["fund_share"] - prev_share) / prev_share * 100, 2
                    )
    except Exception as exc:
        logger.warning("get_etf_share failed for %s: %s", ticker, exc)

    return result


def _parse_csv_rows(csv_text: str, limit: int | None = None) -> list[dict[str, str]]:
    """Parse CSV text (with # comment preamble) into list of row dicts."""
    if not csv_text or csv_text.startswith("No "):
        return []
    clean = []
    for line in csv_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            clean.append(line)
    if not clean:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(clean)))
    rows = list(reader)
    if limit:
        rows = rows[:limit]
    return rows


def get_etf_history_reports(ticker: str, results_dir: str) -> list[dict]:
    """Scan results directory for historical analysis reports of a ticker.

    Returns:
        [{"date": str, "path": str, "rating": str | None, "size_kb": float}]
    """
    from etfagents.agents.utils.rating import parse_rating

    results_path = Path(results_dir)
    if not results_path.exists():
        return []

    reports: list[dict] = []

    for report_path in results_path.glob(f"**/{ticker}/**/complete_report.md"):
        try:
            stat = report_path.stat()
        except OSError:
            continue

        # Extract date from path segments
        parts = report_path.parts
        date_str = ""
        for i, p in enumerate(parts):
            if p == ticker and i + 1 < len(parts):
                date_str = parts[i + 1]
                break
        if not date_str:
            date_str = date.fromtimestamp(stat.st_mtime).isoformat()

        rating = None
        try:
            content = report_path.read_text(encoding="utf-8", errors="ignore")[:4000]
            rating = parse_rating(content)
        except Exception:
            pass

        reports.append({
            "date": date_str,
            "path": str(report_path),
            "rating": rating,
            "size_kb": round(stat.st_size / 1024, 1),
        })

    reports.sort(key=lambda r: r["date"], reverse=True)
    return reports
