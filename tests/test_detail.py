from io import StringIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import etfagents.dataflows.interface
from rich.console import Console
from rich.text import Text

from etfagents.detail import (
    _parse_csv_first_row,
    _parse_csv_last_row,
    _parse_csv_rows,
    get_etf_detail,
    get_etf_history_reports,
)


class CsvParsingTests(unittest.TestCase):
    def test_parse_csv_last_row_with_preamble(self):
        csv_text = (
            "# ETF price data for 510300.SH\n"
            "# Total records: 2\n"
            "\n"
            "trade_date,open,high,low,close,vol,amount,pct_chg\n"
            "20260519,4.10,4.15,4.09,4.12,12345,50700,1.25\n"
            "20260520,4.12,4.18,4.11,4.15,13000,54000,0.73\n"
        )
        row = _parse_csv_last_row(csv_text)
        self.assertIsNotNone(row)
        self.assertEqual(row["trade_date"], "20260520")
        self.assertEqual(row["close"], "4.15")

    def test_parse_csv_last_row_empty(self):
        self.assertIsNone(_parse_csv_last_row(""))
        self.assertIsNone(_parse_csv_last_row("No data found."))

    def test_parse_csv_rows_with_limit(self):
        csv_text = (
            "# Holdings\n"
            "symbol,stk_name,stk_mkv_ratio\n"
            "600519,贵州茅台,5.23\n"
            "000858,五粮液,3.12\n"
            "000333,美的集团,2.50\n"
        )
        rows = _parse_csv_rows(csv_text, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["symbol"], "600519")

    def test_parse_csv_rows_with_zero_limit(self):
        csv_text = (
            "# Holdings\n"
            "symbol,stk_name,stk_mkv_ratio\n"
            "600519,贵州茅台,5.23\n"
        )
        self.assertEqual(_parse_csv_rows(csv_text, limit=0), [])

    def test_parse_csv_rows_empty(self):
        self.assertEqual(_parse_csv_rows(""), [])

    def test_parse_csv_rows_with_summary_lines(self):
        csv_text = (
            "# ETF price data for 510300.SH\n"
            "# Total records: 1\n"
            "# Data retrieved on: 2026-05-21 12:00:00\n"
            "\n"
            "# Key snapshot\n"
            "Ticker: 510300.SH\n"
            "Trade Date: 20260520\n"
            "Close: 4.12\n"
            "Pct Change: +1.25%\n"
            "\n"
            "trade_date,open,high,low,close,vol,amount,pct_chg\n"
            "20260520,4.10,4.15,4.09,4.12,12345,50700,1.25\n"
        )
        rows = _parse_csv_rows(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], "4.12")
        self.assertEqual(rows[0]["trade_date"], "20260520")

    def test_parse_csv_last_row_with_summary_lines(self):
        csv_text = (
            "# ETF NAV for 510300.SH\n"
            "# Total records: 2\n"
            "\n"
            "# Key snapshot\n"
            "Ticker: 510300.SH\n"
            "Unit NAV: 4.128\n"
            "\n"
            "ts_code,end_date,unit_nav\n"
            "510300.SH,20260519,4.125\n"
            "510300.SH,20260520,4.128\n"
        )
        row = _parse_csv_last_row(csv_text)
        self.assertIsNotNone(row)
        self.assertEqual(row["unit_nav"], "4.128")
        self.assertEqual(row["end_date"], "20260520")

    def test_parse_csv_first_row_returns_newest_row(self):
        csv_text = (
            "# ETF NAV for 510300.SH\n"
            "# Total records: 2\n"
            "\n"
            "# Key snapshot\n"
            "Ticker: 510300.SH\n"
            "Unit NAV: 4.128\n"
            "\n"
            "ts_code,end_date,unit_nav\n"
            "510300.SH,20260520,4.128\n"
            "510300.SH,20260519,4.125\n"
        )
        row = _parse_csv_first_row(csv_text)
        self.assertIsNotNone(row)
        self.assertEqual(row["unit_nav"], "4.128")
        self.assertEqual(row["end_date"], "20260520")


class GetEtfDetailTests(unittest.TestCase):
    PRICE_CSV = (
        "# ETF price data\n"
        "# Total records: 1\n"
        "\n"
        "trade_date,open,high,low,close,vol,amount,pct_chg\n"
        "20260520,4.10,4.15,4.09,4.12,12345,50700,1.25\n"
    )
    NAV_CSV = (
        "# ETF NAV\n"
        "# Total records: 1\n"
        "\n"
        "ts_code,end_date,unit_nav\n"
        "510300.SH,20260520,4.128\n"
    )
    INFO_CSV = (
        "# ETF profile\n"
        "# Total records: 1\n"
        "\n"
        "ts_code,name,market,fund_type,found_date,benchmark,management\n"
        "510300.SH,沪深300ETF,a_share,指数型,20120101,沪深300指数,华泰柏瑞\n"
    )
    HOLDINGS_CSV = (
        "# ETF holdings\n"
        "\n"
        "symbol,stk_name,stk_mkv_ratio\n"
        "600519,贵州茅台,5.23\n"
        "000858,五粮液,3.12\n"
    )
    SHARE_CSV = (
        "# ETF share\n"
        "\n"
        "ts_code,end_date,fd_share\n"
        "510300.SH,20260520,125.3\n"
        "510300.SH,20260519,122.5\n"
    )

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_full_detail(self, mock_vendor):
        def _vendor_side_effect(method, *args, **kwargs):
            return {
                "get_etf_price_data": self.PRICE_CSV,
                "get_etf_nav": self.NAV_CSV,
                "get_etf_info": self.INFO_CSV,
                "get_etf_holdings": self.HOLDINGS_CSV,
                "get_etf_share": self.SHARE_CSV,
            }[method]

        mock_vendor.side_effect = _vendor_side_effect
        result = get_etf_detail("510300.SH", curr_date="2026-05-20")

        mock_vendor.assert_any_call("get_etf_price_data", "510300.SH", "2025-05-20", "2026-05-20")

        self.assertEqual(result["ticker"], "510300.SH")
        self.assertEqual(result["name"], "沪深300ETF")
        self.assertEqual(result["market"], "a_share")
        self.assertEqual(result["close"], 4.12)
        self.assertEqual(result["pct_chg"], 1.25)
        self.assertEqual(result["unit_nav"], 4.128)
        self.assertIsNotNone(result["premium_discount_bps"])
        self.assertEqual(len(result["holdings"]), 2)
        self.assertEqual(result["holdings"][0]["code"], "600519")
        self.assertEqual(result["fund_share"], 125.3)
        self.assertIsNotNone(result["share_change_pct"])

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_holdings_name_does_not_fall_back_to_code(self, mock_vendor):
        def _vendor_side_effect(method, *args, **kwargs):
            data = {
                "get_etf_price_data": self.PRICE_CSV,
                "get_etf_nav": self.NAV_CSV,
                "get_etf_info": self.INFO_CSV,
                "get_etf_holdings": (
                    "# ETF holdings\n\n"
                    "symbol,stk_name,stk_mkv_ratio\n"
                    "600519,,5.23\n"
                ),
                "get_etf_share": self.SHARE_CSV,
            }
            return data[method]

        mock_vendor.side_effect = _vendor_side_effect

        result = get_etf_detail("510300.SH", curr_date="2026-05-20")

        self.assertEqual(result["holdings"][0]["code"], "600519")
        self.assertEqual(result["holdings"][0]["name"], "")

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_graceful_degradation_on_vendor_failure(self, mock_vendor):
        mock_vendor.side_effect = Exception("API down")
        result = get_etf_detail("INVALID.TICKER", curr_date="2026-05-20")
        self.assertEqual(result["ticker"], "INVALID.TICKER")
        self.assertIsNone(result["name"])
        self.assertIsNone(result["close"])

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_non_a_share_ticker(self, mock_vendor):
        def _vendor_side_effect(method, *args, **kwargs):
            if method == "get_etf_info":
                return self.INFO_CSV.replace("a_share", "us")
            if method == "get_etf_price_data":
                return self.PRICE_CSV
            return "No data found."

        mock_vendor.side_effect = _vendor_side_effect
        result = get_etf_detail("SPY", curr_date="2026-05-20")
        self.assertEqual(result["market"], "us")

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_premium_discount_calculation(self, mock_vendor):
        def _vendor_side_effect(method, *args, **kwargs):
            if method == "get_etf_price_data":
                return self.PRICE_CSV
            if method == "get_etf_nav":
                return self.NAV_CSV
            return "No data found."

        mock_vendor.side_effect = _vendor_side_effect
        result = get_etf_detail("510300.SH", curr_date="2026-05-20")
        # close=4.12, nav=4.128 → (4.12-4.128)/4.128*10000 = -19.38 bps
        self.assertAlmostEqual(result["premium_discount_bps"], -19.38, places=1)

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_holdings_empty_when_no_data(self, mock_vendor):
        def _vendor_side_effect(method, *args, **kwargs):
            if method == "get_etf_info":
                return self.INFO_CSV
            return "No data found."

        mock_vendor.side_effect = _vendor_side_effect
        result = get_etf_detail("510300.SH", curr_date="2026-05-20")
        self.assertIsNone(result["holdings"])

    @patch("etfagents.dataflows.interface.route_to_vendor")
    def test_share_change_allows_zero_latest_share(self, mock_vendor):
        def _vendor_side_effect(method, *args, **kwargs):
            if method == "get_etf_share":
                return (
                    "# ETF share\n"
                    "\n"
                    "ts_code,end_date,fd_share\n"
                    "510300.SH,20260520,0\n"
                    "510300.SH,20260519,122.5\n"
                )
            return "No data found."

        mock_vendor.side_effect = _vendor_side_effect
        result = get_etf_detail("510300.SH", curr_date="2026-05-20")
        self.assertEqual(result["fund_share"], 0.0)
        self.assertEqual(result["share_change_pct"], -100.0)


class GetEtfHistoryReportsTests(unittest.TestCase):
    def test_no_results_dir(self):
        reports = get_etf_history_reports("510300.SH", "/nonexistent/path")
        self.assertEqual(reports, [])

    def test_finds_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir) / "510300.SH" / "2026-05-20"
            report_dir.mkdir(parents=True)
            report_file = report_dir / "complete_report.md"
            report_file.write_text("# Report\nRating: BUY\nSome content", encoding="utf-8")

            reports = get_etf_history_reports("510300.SH", tmpdir)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]["date"], "2026-05-20")
            self.assertEqual(reports[0]["rating"], "BUY")
            self.assertGreaterEqual(reports[0]["size_kb"], 0)

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reports = get_etf_history_reports("510300.SH", tmpdir)
            self.assertEqual(reports, [])

    def test_reports_sorted_by_date_desc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for d in ["2026-05-18", "2026-05-20", "2026-05-19"]:
                report_dir = Path(tmpdir) / "510300.SH" / d
                report_dir.mkdir(parents=True)
                (report_dir / "complete_report.md").write_text("Report", encoding="utf-8")

            reports = get_etf_history_reports("510300.SH", tmpdir)
            self.assertEqual(len(reports), 3)
            self.assertEqual(reports[0]["date"], "2026-05-20")
            self.assertEqual(reports[2]["date"], "2026-05-18")


class DetailCliTests(unittest.TestCase):
    def test_detail_command_registered(self):
        from typer.testing import CliRunner
        from cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["detail", "--help"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("ticker", result.output.lower())

    @patch("cli.commands.detail.get_etf_history_reports")
    @patch("cli.commands.detail.get_etf_detail")
    def test_detail_renders_rating_as_plain_text(self, mock_get_detail, mock_get_history):
        mock_get_detail.return_value = {
            "ticker": "510300.SH",
            "name": "沪深300ETF",
            "market": "a_share",
            "latest_date": "20260520",
            "open": None,
            "high": None,
            "low": None,
            "close": 4.12,
            "pct_chg": None,
            "volume": None,
            "amount": None,
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
        mock_get_history.return_value = [{"date": "2026-05-20", "rating": "[bold]BUY[/bold]", "size_kb": 1.0}]

        from cli.commands import detail as detail_module

        output = StringIO()
        original_add_row = detail_module.Table.add_row
        captured_rating_cells = []

        def _capturing_add_row(table, *cells, **kwargs):
            if getattr(table, "title", None) == "历史分析报告" and len(cells) >= 2:
                captured_rating_cells.append(cells[1])
            return original_add_row(table, *cells, **kwargs)

        with (
            patch.object(detail_module, "_console", Console(file=output, force_terminal=False, width=120)),
            patch.object(detail_module.Table, "add_row", autospec=True, side_effect=_capturing_add_row),
        ):
            detail_module.detail("510300.SH")

        self.assertTrue(captured_rating_cells)
        self.assertIsInstance(captured_rating_cells[0], Text)
        self.assertEqual(captured_rating_cells[0].plain, "[bold]BUY[/bold]")
        self.assertIn("[bold]BUY[/bold]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
