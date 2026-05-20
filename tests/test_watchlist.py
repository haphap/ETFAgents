import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from etfagents.watchlist import WatchlistManager
from cli.commands.watchlist import watchlist_app


class WatchlistManagerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "watchlist.db"
        self.wl = WatchlistManager(db_path=self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_default_group_exists(self):
        groups = self.wl.list_groups()
        names = [g["name"] for g in groups]
        self.assertIn("default", names)

    def test_add_and_list_tickers(self):
        self.wl.add("510300.SH", group="default", name="沪深300ETF")
        entries = self.wl.list_tickers()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ticker"], "510300.SH")
        self.assertEqual(entries[0]["name"], "沪深300ETF")
        self.assertEqual(entries[0]["group"], "default")

    def test_add_with_tags(self):
        self.wl.add("510300.SH", group="default", tags=["大盘", "蓝筹"])
        entries = self.wl.list_tickers()
        self.assertEqual(entries[0]["tags"], ["大盘", "蓝筹"])

    def test_add_duplicate_updates(self):
        self.wl.add("510300.SH", group="default", name="沪深300ETF")
        self.wl.add("510300.SH", group="default", name="沪深300ETF更新", tags=["大盘"])
        entries = self.wl.list_tickers()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "沪深300ETF更新")
        self.assertEqual(entries[0]["tags"], ["大盘"])

    def test_remove_from_all_groups(self):
        self.wl.add("510300.SH", group="default")
        self.wl.add_group("宽基")
        self.wl.add("510300.SH", group="宽基")
        removed = self.wl.remove("510300.SH")
        self.assertEqual(removed, 2)
        self.assertEqual(len(self.wl.list_tickers()), 0)

    def test_remove_from_specific_group(self):
        self.wl.add_group("宽基")
        self.wl.add("510300.SH", group="default")
        self.wl.add("510300.SH", group="宽基")
        removed = self.wl.remove("510300.SH", group="宽基")
        self.assertEqual(removed, 1)
        entries = self.wl.list_tickers()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["group"], "default")

    def test_same_ticker_in_multiple_groups(self):
        self.wl.add_group("宽基")
        self.wl.add("510300.SH", group="default", tags=["大盘"])
        self.wl.add("510300.SH", group="宽基", tags=["蓝筹"])
        entries = self.wl.list_tickers()
        self.assertEqual(len(entries), 2)

    def test_list_filter_by_group(self):
        self.wl.add_group("宽基")
        self.wl.add("510300.SH", group="default")
        self.wl.add("159915.SZ", group="宽基")
        entries = self.wl.list_tickers(group="宽基")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ticker"], "159915.SZ")

    def test_list_filter_by_tags(self):
        self.wl.add("510300.SH", group="default", tags=["大盘", "蓝筹"])
        self.wl.add("159915.SZ", group="default", tags=["成长"])
        entries = self.wl.list_tickers(tags=["大盘"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ticker"], "510300.SH")

    def test_get_tickers_for_analysis(self):
        self.wl.add("510300.SH", group="default")
        self.wl.add("159915.SZ", group="default")
        tickers = self.wl.get_tickers_for_analysis("default")
        self.assertEqual(tickers, ["510300.SH", "159915.SZ"])

    def test_get_tickers_for_empty_group(self):
        tickers = self.wl.get_tickers_for_analysis("nonexistent")
        self.assertEqual(tickers, [])

    def test_add_group(self):
        gid = self.wl.add_group("行业")
        self.assertIsInstance(gid, int)
        groups = self.wl.list_groups()
        names = [g["name"] for g in groups]
        self.assertIn("行业", names)

    def test_add_duplicate_group_raises(self):
        self.wl.add_group("行业")
        with self.assertRaises(ValueError):
            self.wl.add_group("行业")

    def test_remove_group_cascades(self):
        self.wl.add_group("行业")
        self.wl.add("512660.SH", group="行业")
        self.wl.remove_group("行业")
        self.assertEqual(len(self.wl.list_tickers()), 0)

    def test_rename_group(self):
        self.wl.add_group("行业")
        self.wl.rename_group("行业", "行业ETF")
        groups = self.wl.list_groups()
        names = [g["name"] for g in groups]
        self.assertIn("行业ETF", names)
        self.assertNotIn("行业", names)

    def test_update_tags(self):
        self.wl.add("510300.SH", group="default", tags=["大盘"])
        self.wl.update("510300.SH", group="default", tags=["大盘", "蓝筹"])
        entries = self.wl.list_tickers()
        self.assertEqual(entries[0]["tags"], ["大盘", "蓝筹"])

    def test_update_notes(self):
        self.wl.add("510300.SH", group="default")
        self.wl.update("510300.SH", group="default", notes="测试备注")
        entries = self.wl.list_tickers()
        self.assertEqual(entries[0]["notes"], "测试备注")

    def test_all_tags(self):
        self.wl.add("510300.SH", group="default", tags=["大盘", "蓝筹"])
        self.wl.add("159915.SZ", group="default", tags=["成长", "蓝筹"])
        tags = self.wl.all_tags()
        self.assertEqual(tags, ["大盘", "成长", "蓝筹"])

    def test_group_count(self):
        self.wl.add("510300.SH", group="default")
        self.wl.add("159915.SZ", group="default")
        groups = self.wl.list_groups()
        default = next(g for g in groups if g["name"] == "default")
        self.assertEqual(default["count"], 2)

    def test_empty_db_returns_zero_stats(self):
        groups = self.wl.list_groups()
        self.assertEqual(len(groups), 1)
        entries = self.wl.list_tickers()
        self.assertEqual(len(entries), 0)

    def test_rename_group_nonexistent_raises(self):
        with self.assertRaises(ValueError):
            self.wl.rename_group("不存在", "新名")

    def test_rename_default_group_raises(self):
        with self.assertRaises(ValueError):
            self.wl.rename_group("default", "其他")

    def test_remove_default_group_raises(self):
        with self.assertRaises(ValueError):
            self.wl.remove_group("default")

    def test_rename_group_duplicate_name_raises(self):
        self.wl.add_group("行业")
        self.wl.add_group("宽基")
        with self.assertRaises(ValueError):
            self.wl.rename_group("行业", "宽基")

    def test_tag_wildcard_escaped(self):
        self.wl.add("510300.SH", group="default", tags=["大盘"])
        entries = self.wl.list_tickers(tags=["大盘%"])
        self.assertEqual(len(entries), 0)

    def test_auto_fill_name_fallback(self):
        name = self.wl._auto_fill_name("INVALID.TICKER")
        self.assertEqual(name, "INVALID.TICKER")

    def test_auto_fill_name_with_preamble(self):
        csv_with_comments = (
            "# Tushare ETF profile for 560860.SH\n"
            "# Total records: 1\n"
            "\n"
            "ts_code,name\n"
            "560860.SH,工业有色ETF万家\n"
        )
        import unittest.mock
        with unittest.mock.patch("etfagents.dataflows.interface.route_to_vendor", return_value=csv_with_comments):
            with unittest.mock.patch("etfagents.dataflows.config.get_config", return_value=True):
                name = self.wl._auto_fill_name("560860.SH")
        self.assertEqual(name, "工业有色ETF万家")

    def test_list_tags_any_match(self):
        self.wl.add("510300.SH", group="default", tags=["大盘"])
        self.wl.add("159915.SZ", group="default", tags=["成长"])
        entries = self.wl.list_tickers(tags=["大盘", "成长"])
        self.assertEqual(len(entries), 2)


class WatchlistCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "watchlist.db"
        self.runner = CliRunner()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_group_rename_positional_args(self):
        with patch("cli.commands.watchlist.WatchlistManager", lambda: WatchlistManager(db_path=self.db_path)):
            self.wl = WatchlistManager(db_path=self.db_path)
            self.wl.add_group("行业")
            result = self.runner.invoke(watchlist_app, ["group", "rename", "行业", "行业ETF"])
            self.assertEqual(0, result.exit_code, result.output)
            groups = self.wl.list_groups()
            names = [g["name"] for g in groups]
            self.assertIn("行业ETF", names)
            self.assertNotIn("行业", names)


if __name__ == "__main__":
    unittest.main()
