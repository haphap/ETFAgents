"""ETF detail data aggregation."""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_SUMMARY_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z\s]*:\s")


def _parse_csv_rows(csv_text: str, limit: int | None = None) -> list[dict[str, str]]:
    """Parse CSV text with # comment preamble and un-commented summary lines.

    Vendor output via _to_csv_with_header() looks like:
        # Title
        # Total records: N
        # Key snapshot
        Ticker: 510300.SH          <-- summary line (Label: value)
        Close: 4.12                <-- summary line
        trade_date,open,close      <-- real CSV header
        20260520,4.10,4.12         <-- data row
    """
    if not csv_text or csv_text.startswith("No "):
        return []
    # Find the first real CSV header: a line containing a comma and
    # at least one of the expected Tushare column names
    csv_header_fields = {
        "trade_date", "ts_code", "symbol", "stk_code", "end_date",
        "nav_date", "name", "open", "close", "unit_nav", "fd_share",
        "fund_share", "stk_mkv_ratio", "pct_chg",
    }
    header_idx = None
    lines = csv_text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or _SUMMARY_LINE_RE.match(stripped):
            continue
        if "," in stripped:
            fields = {f.strip().lower() for f in stripped.split(",")}
            if fields & csv_header_fields:
                header_idx = i
                break
    if header_idx is None:
        return []
    data_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(data_text))
    rows = list(reader)
    if limit is not None:
        rows = rows[:limit] if limit > 0 else []
    return rows


def _parse_csv_first_row(csv_text: str) -> dict[str, str] | None:
    rows = _parse_csv_rows(csv_text, limit=1)
    return rows[0] if rows else None


def _parse_csv_last_row(csv_text: str) -> dict[str, str] | None:
    rows = _parse_csv_rows(csv_text)
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
    from etfagents.dataflows.interface import route_to_vendor

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

    # 1. Price data (uses start_date/end_date range in yyyy-mm-dd)
    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=365)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = curr_date
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
        row = _parse_csv_first_row(csv_text)
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
                    "name": (r.get("stk_name") or "").strip(),
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
                if result["fund_share"] is not None and prev_share is not None and prev_share != 0:
                    result["share_change_pct"] = round(
                        (result["fund_share"] - prev_share) / prev_share * 100, 2
                    )
    except Exception as exc:
        logger.warning("get_etf_share failed for %s: %s", ticker, exc)

    return result


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
            # Read tail of file since ratings tend to live in the conclusion
            content = report_path.read_text(encoding="utf-8", errors="ignore")
            rating = parse_rating(content[-4000:])
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
