
import unittest
from unittest.mock import patch

import pandas as pd

from etfagents.dataflows.tushare import (
    _build_balance_sheet_summary,
    _build_cashflow_summary,
    _build_income_statement_summary,
    _filter_statement,
    get_balance_sheet,
    get_fundamentals,
)

class _FakePro:
    def stock_basic(self, **kwargs):
        if kwargs.get("ts_code"):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "300750.SZ",
                        "symbol": "300750",
                        "name": "宁德时代",
                        "area": "福建",
                        "industry": "电气设备",
                        "market": "创业板",
                        "list_date": "20180611",
                        "list_status": "L",
                    }
                ]
            )
        return pd.DataFrame(
            [
                {"ts_code": "300750.SZ", "name": "宁德时代", "industry": "电气设备", "market": "创业板", "list_status": "L"},
                {"ts_code": "300014.SZ", "name": "亿纬锂能", "industry": "电气设备", "market": "创业板", "list_status": "L"},
                {"ts_code": "300274.SZ", "name": "阳光电源", "industry": "电气设备", "market": "创业板", "list_status": "L"},
                {"ts_code": "600406.SH", "name": "国电南瑞", "industry": "电气设备", "market": "主板", "list_status": "L"},
            ]
        )

    def daily_basic(self, **kwargs):
        if kwargs.get("trade_date"):
            return pd.DataFrame(
                [
                    {"ts_code": "300750.SZ", "close": 389.99, "pe": 24.6524, "pb": 5.2787, "ps": 4.2009, "total_mv": 177993685.4233},
                    {"ts_code": "300274.SZ", "close": 123.80, "pe": 19.0668, "pb": 5.5065, "ps": 2.8779, "total_mv": 25666362.0},
                    {"ts_code": "600406.SH", "close": 25.96, "pe": 27.3983, "pb": 4.2365, "ps": 3.6314, "total_mv": 20850440.0},
                    {"ts_code": "300014.SZ", "close": 65.11, "pe": 33.0293, "pb": 3.1622, "ps": 2.2215, "total_mv": 13655330.0},
                ]
            )
        return pd.DataFrame(
            [
                {
                    "trade_date": "20260409",
                    "close": 389.99,
                    "turnover_rate": 1.2345,
                    "pe": 24.6524,
                    "pb": 5.2787,
                    "ps": 4.2009,
                    "dv_ratio": 0.85,
                    "total_mv": 177993685.4233,
                    "circ_mv": 146214715.5171,
                }
            ]
        )

    def fina_indicator(self, **kwargs):
        ts_code = kwargs.get("ts_code")
        rows = {
            "300750.SZ": [
                {
                    "ts_code": "300750.SZ",
                    "ann_date": "20260310",
                    "end_date": "20251231",
                    "roe": 24.7249,
                    "roa": 9.2724,
                    "grossprofit_margin": 26.2728,
                    "netprofit_margin": 18.1227,
                    "debt_to_assets": 61.9393,
                    "ocf_to_or": 31.4432,
                    "or_yoy": 17.0406,
                    "netprofit_yoy": 42.2834,
                    "dt_netprofit_yoy": 43.37,
                    "q_sales_yoy": 36.5765,
                    "q_op_qoq": 33.2901,
                }
            ],
            "300274.SZ": [
                {"ts_code": "300274.SZ", "ann_date": "20260310", "end_date": "20251231", "roe": 29.12, "netprofit_yoy": 45.80}
            ],
            "600406.SH": [
                {"ts_code": "600406.SH", "ann_date": "20260310", "end_date": "20251231", "roe": 17.35, "netprofit_yoy": 12.40}
            ],
            "300014.SZ": [
                {"ts_code": "300014.SZ", "ann_date": "20260310", "end_date": "20251231", "roe": 18.52, "netprofit_yoy": 35.11}
            ],
        }
        return pd.DataFrame(rows[ts_code])

    def balancesheet(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "end_date": "20251231",
                    "ann_date": "20260315",
                    "update_flag": "1",
                    "total_assets": 974827544000.0,
                    "total_liab": 603801220000.0,
                    "total_hldr_eqy_exc_min_int": 337107747000.0,
                    "total_cur_assets": 638482337000.0,
                    "total_cur_liab": 399625964000.0,
                    "money_cap": 333512927000.0,
                    "accounts_receiv": 76403158000.0,
                    "inventories": 94525980000.0,
                    "contract_liab": 4483962000.0,
                }
            ]
        )

    def income(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": "300750.SZ",
                    "ann_date": "20260310",
                    "end_date": "20251231",
                    "total_revenue": 423702965000.0,
                    "operate_profit": 89518931000.0,
                    "total_profit": 89527000000.0,
                    "n_income": 76786309000.0,
                    "n_income_attr_p": 72201282000.0,
                    "rd_exp": 22146518000.0,
                    "ebit": 75968000000.0,
                    "ebitda": 102905000000.0,
                },
                {
                    "ts_code": "300750.SZ",
                    "ann_date": "20250315",
                    "end_date": "20241231",
                    "total_revenue": 362499000000.0,
                    "operate_profit": 74201022000.0,
                    "total_profit": 74290000000.0,
                    "n_income": 52000000000.0,
                    "n_income_attr_p": 44121205000.0,
                    "rd_exp": 18654002000.0,
                    "ebit": 64000000000.0,
                    "ebitda": 88000000000.0,
                },
            ]
        )

    def stock_company(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": "300750.SZ",
                    "introduction": "公司是全球领先的动力电池与储能系统企业，具备电池材料、电池系统、电池回收等产业链能力。",
                    "business_scope": "动力电池、储能系统、电池材料及回收业务。",
                    "main_business": "公司主要产品包括动力电池系统、储能系统和锂电池材料。",
                    "employees": 185839,
                }
            ]
        )

    def fina_mainbz(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": "300750.SZ", "end_date": "20251231", "bz_item": "动力电池系统", "bz_sales": 316506400000.0, "bz_profit": 75441970000.0, "bz_cost": 241064400000.0, "curr_type": "CNY"},
                {"ts_code": "300750.SZ", "end_date": "20251231", "bz_item": "电池材料及回收", "bz_sales": 21860940000.0, "bz_profit": 5961123000.0, "bz_cost": 15899810000.0, "curr_type": "CNY"},
                {"ts_code": "300750.SZ", "end_date": "20251231", "bz_item": "储能系统", "bz_sales": 5840000000.0, "bz_profit": 1030000000.0, "bz_cost": 4810000000.0, "curr_type": "CNY"},
            ]
        )

    def forecast(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": "300750.SZ",
                    "ann_date": "20260405",
                    "end_date": "20261231",
                    "p_change_min": 18.0,
                    "p_change_max": 28.0,
                    "net_profit_min": 5000000.0,
                    "net_profit_max": 5200000.0,
                    "summary": "预计2026年净利润5000000-5200000万元",
                    "change_reason": "动力电池与储能需求延续增长，研发驱动新品放量。",
                    "update_flag": "1",
                }
            ]
        )

    def express(self, **kwargs):
        return pd.DataFrame()

class TushareStatementSummaryTests(unittest.TestCase):
    def test_filter_statement_keeps_latest_updated_row_per_end_date(self):
        df = pd.DataFrame(
            [
                {
                    "end_date": "20250331",
                    "ann_date": "20250415",
                    "update_flag": "0",
                    "total_assets": 100.0,
                },
                {
                    "end_date": "20250331",
                    "ann_date": "20250418",
                    "update_flag": "1",
                    "total_assets": 120.0,
                },
                {
                    "end_date": "20241231",
                    "ann_date": "20250301",
                    "update_flag": "1",
                    "total_assets": 90.0,
                },
            ]
        )

        filtered = _filter_statement(df, "quarterly", "2025-04-20")

        self.assertEqual(filtered["end_date"].tolist(), ["20250331", "20241231"])
        self.assertEqual(filtered.iloc[0]["total_assets"], 120.0)

    def test_balance_sheet_summary_includes_core_totals_and_ratios(self):
        df = pd.DataFrame(
            [
                {
                    "end_date": "20251231",
                    "total_assets": 974827544000.0,
                    "total_liab": 603801220000.0,
                    "total_hldr_eqy_exc_min_int": 337107747000.0,
                    "total_cur_assets": 638482337000.0,
                    "total_cur_liab": 399625964000.0,
                    "money_cap": 333512927000.0,
                }
            ]
        )

        summary = "\n".join(_build_balance_sheet_summary(df))

        self.assertIn("Total Assets: 9748.28亿 CNY", summary)
        self.assertIn("Total Liabilities: 6038.01亿 CNY", summary)
        self.assertIn("Asset-Liability Ratio: 61.94%", summary)
        self.assertIn("Current Ratio: 1.60x", summary)
        self.assertIn("Cash: 3335.13亿 CNY", summary)

    def test_cashflow_and_income_statement_summaries_surface_key_metrics(self):
        cashflow_df = pd.DataFrame(
            [
                {
                    "end_date": "20251231",
                    "n_cashflow_act": 133219982000.0,
                    "n_cashflow_inv_act": -94476299175.3736,
                    "n_cash_flows_fnc_act": -6309607926.27637,
                    "free_cashflow": 87114682973.5947,
                    "c_cash_equ_end_period": 299929459246.0,
                }
            ]
        )
        income_df = pd.DataFrame(
            [
                {
                    "end_date": "20251231",
                    "total_revenue": 423702965000.0,
                    "operate_profit": 89518931000.0,
                    "n_income_attr_p": 72201282000.0,
                    "rd_exp": 22146518000.0,
                },
                {
                    "end_date": "20241231",
                    "total_revenue": 400917983000.0,
                    "operate_profit": 74201022000.0,
                    "n_income_attr_p": 44121205000.0,
                    "rd_exp": 18654002000.0,
                },
            ]
        )

        cashflow_summary = "\n".join(_build_cashflow_summary(cashflow_df))
        income_summary = "\n".join(_build_income_statement_summary(income_df))

        self.assertIn("Operating Cash Flow: 1332.20亿 CNY", cashflow_summary)
        self.assertIn("Free Cash Flow: 871.15亿 CNY", cashflow_summary)
        self.assertIn("Ending Cash and Cash Equivalents: 2999.29亿 CNY", cashflow_summary)
        self.assertIn("Total Revenue: 4237.03亿 CNY", income_summary)
        self.assertIn("Parent Net Income: 722.01亿 CNY", income_summary)
        self.assertIn("Revenue YoY (same period): 5.68%", income_summary)
        self.assertIn("Parent Net Income YoY (same period): 63.64%", income_summary)

    def test_public_tools_include_human_readable_price_growth_business_and_peer_snapshots(self):
        with patch("etfagents.dataflows.tushare._get_pro_client", return_value=_FakePro()):
            fundamentals = get_fundamentals("300750.SZ", "2026-04-09")
            balance_sheet = get_balance_sheet("300750.SZ", "quarterly", "2026-04-09")

        self.assertIn("Latest Close Price: 389.99 CNY/share", fundamentals)
        self.assertIn("PE: 24.65x", fundamentals)
        self.assertIn("Total Market Value: 17799.37亿 CNY", fundamentals)
        self.assertIn("Debt to Assets: 61.94%", fundamentals)
        self.assertIn("PEG (using Net Profit YoY): 0.58x", fundamentals)
        self.assertIn("R&D Intensity: 5.23%", fundamentals)
        self.assertIn("Main Business Summary: 公司主要产品包括动力电池系统、储能系统和锂电池材料。", fundamentals)
        self.assertIn("Segment: 动力电池系统", fundamentals)
        self.assertIn("Forward PE (market cap / forecast net profit midpoint): 34.90x", fundamentals)
        self.assertIn("Peer Sample Basis: same Tushare industry '电气设备'", fundamentals)
        self.assertIn("亿纬锂能 (300014.SZ)", fundamentals)
        self.assertIn("Target vs Peer Median:", fundamentals)
        self.assertIn("# Key snapshot", balance_sheet)
        self.assertIn("Total Assets: 9748.28亿 CNY", balance_sheet)
        self.assertIn("Asset-Liability Ratio: 61.94%", balance_sheet)

if __name__ == "__main__":
    unittest.main()
