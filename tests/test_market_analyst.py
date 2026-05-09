import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.market_analyst import create_market_analyst


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _CapturingLLM:
    def __init__(self, final_content):
        self.final_content = final_content
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return _FakeResponse(self.final_content)


class _FakeTool:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def invoke(self, args):
        self.calls.append(args)
        indicator = args.get("indicator", "unknown")
        return f"## {indicator} values from 2026-03-01 to 2026-04-01:\n2026-04-01: 1.23"


class MarketAnalystTests(unittest.TestCase):
    def test_market_analyst_backfills_missing_indicators_before_final_report(self):
        llm = _CapturingLLM(
            "# 完整市场报告\n\n已覆盖 SMA、EMA、MACD、RSI、布林带 和 VWMA。"
        )
        node = create_market_analyst(llm)

        partial_result = AIMessage(content="只基于SMA和EMA给出简略报告。")
        state = {
            "company_of_interest": "300308.SZ",
            "trade_date": "2026-04-01",
            "messages": [
                HumanMessage(content="请分析 300308.SZ"),
                AIMessage(content="## close_50_sma values from 2026-03-01 to 2026-04-01:\n2026-04-01: 576.94"),
                AIMessage(content="## close_200_sma values from 2026-03-01 to 2026-04-01:\n2026-04-01: 462.10"),
                AIMessage(content="## close_10_ema values from 2026-03-01 to 2026-04-01:\n2026-04-01: 590.93"),
            ],
        }

        fake_stock_tool = _FakeTool("get_stock_data")
        fake_indicator_tool = _FakeTool("get_indicators")

        with (
            patch(
                "etfagents.agents.analysts.market_analyst.run_tool_report_chain",
                return_value=(partial_result, "只基于SMA和EMA给出简略报告。"),
            ),
            patch(
                "etfagents.agents.analysts.market_analyst.get_stock_data",
                fake_stock_tool,
            ),
            patch(
                "etfagents.agents.analysts.market_analyst.get_indicators",
                fake_indicator_tool,
            ),
        ):
            result = node(state)

        fetched_indicators = {call["indicator"] for call in fake_indicator_tool.calls}
        self.assertIn("macd", fetched_indicators)
        self.assertIn("rsi", fetched_indicators)
        self.assertIn("boll", fetched_indicators)
        self.assertIn("vwma", fetched_indicators)
        self.assertIn("VWMA", result["market_report"])
        self.assertEqual(result["messages"][0].content, result["market_report"])

    def test_market_analyst_rewrites_generic_full_coverage_report_when_it_lacks_trading_depth(self):
        llm = _CapturingLLM(
            "# 深化市场报告\n\n"
            "价格仍站在10日EMA与VWMA之上，短线承接尚未破坏；若后续回踩10日EMA后企稳且成交量不失速，可继续按趋势延续处理。"
        )
        node = create_market_analyst(llm)

        generic_report = (
            "# 市场技术报告\n\n"
            "已覆盖 SMA、EMA、MACD、RSI、布林带 和 VWMA。\n\n"
            "200日简单移动平均线：最新读数为33.27。作为长期趋势的风向标，该均线为价格提供了基础性支撑参考。\n"
            "10日指数移动平均线：最新读数为34.01。作为高灵敏度的短期均线，其数值略高于长期均线。\n"
            "50日简单移动平均线：最新读数为33.80。该指标可用于观察中期趋势。\n"
            "MACD、RSI、布林带与VWMA均已覆盖。"
        )
        full_indicator_messages = [
            HumanMessage(content="请分析 300308.SZ"),
            AIMessage(content="## close_50_sma values from 2026-03-01 to 2026-04-01:\n2026-04-01: 33.80"),
            AIMessage(content="## close_200_sma values from 2026-03-01 to 2026-04-01:\n2026-04-01: 33.27"),
            AIMessage(content="## close_10_ema values from 2026-03-01 to 2026-04-01:\n2026-04-01: 34.01"),
            AIMessage(content="## macd values from 2026-03-01 to 2026-04-01:\n2026-04-01: 0.12"),
            AIMessage(content="## macds values from 2026-03-01 to 2026-04-01:\n2026-04-01: 0.08"),
            AIMessage(content="## macdh values from 2026-03-01 to 2026-04-01:\n2026-04-01: 0.04"),
            AIMessage(content="## rsi values from 2026-03-01 to 2026-04-01:\n2026-04-01: 58.2"),
            AIMessage(content="## boll values from 2026-03-01 to 2026-04-01:\n2026-04-01: 33.60"),
            AIMessage(content="## boll_ub values from 2026-03-01 to 2026-04-01:\n2026-04-01: 34.50"),
            AIMessage(content="## boll_lb values from 2026-03-01 to 2026-04-01:\n2026-04-01: 32.70"),
            AIMessage(content="## atr values from 2026-03-01 to 2026-04-01:\n2026-04-01: 0.90"),
            AIMessage(content="## vwma values from 2026-03-01 to 2026-04-01:\n2026-04-01: 33.95"),
        ]
        partial_result = AIMessage(content=generic_report)

        with patch(
            "etfagents.agents.analysts.market_analyst.run_tool_report_chain",
            return_value=(partial_result, generic_report),
        ):
            result = node(
                {
                    "company_of_interest": "300308.SZ",
                    "trade_date": "2026-04-01",
                    "messages": full_indicator_messages,
                }
            )

        self.assertEqual(result["market_report"], llm.final_content)
        self.assertTrue(llm.prompts)
        self.assertIn("Opening paragraph requirements", llm.prompts[0])
        self.assertIn("Do not stop at textbook definitions", llm.prompts[0])

    def test_market_analyst_rewrites_boilerplate_intro_even_with_depthful_body(self):
        llm = _CapturingLLM(
            "# 改写后市场报告\n\n"
            "股价仍运行在10日EMA与50日SMA上方，短线结构偏多，但35元附近仍是需要放量突破的确认位。"
        )
        node = create_market_analyst(llm)

        report_with_boilerplate_intro = (
            "# 市场技术报告\n\n"
            "基于2026年3月31日至4月30日的交易数据，本报告对 601899.SH 的核心技术面进行结构化拆解。报告严格依据系统输出的指标数值，划分为趋势均线、动能状态、波动率区间及量能确认四大维度。\n\n"
            "价格高于10日EMA、50日SMA与200日SMA，说明趋势仍偏多；若后续跌破50日SMA，则中期支撑将明显转弱。MACD位于信号线上方且柱状图维持正值，RSI未进入超买区，表明动能尚未失真。布林带中轨与VWMA同时位于价格下方，意味着量价结构暂未破坏；但若放量跌破VWMA，则应优先等待而不是继续追价。"
        )
        indicator_messages = [
            HumanMessage(content="请分析 601899.SH"),
            AIMessage(content="## close_50_sma values from 2026-01-30 to 2026-04-30:\n2026-04-30: 35.24"),
            AIMessage(content="## close_200_sma values from 2026-01-30 to 2026-04-30:\n2026-04-30: 33.27"),
            AIMessage(content="## close_10_ema values from 2026-01-30 to 2026-04-30:\n2026-04-30: 34.01"),
            AIMessage(content="## macd values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.12"),
            AIMessage(content="## macds values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.08"),
            AIMessage(content="## macdh values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.04"),
            AIMessage(content="## rsi values from 2026-01-30 to 2026-04-30:\n2026-04-30: 58.2"),
            AIMessage(content="## boll values from 2026-01-30 to 2026-04-30:\n2026-04-30: 33.60"),
            AIMessage(content="## boll_ub values from 2026-01-30 to 2026-04-30:\n2026-04-30: 34.50"),
            AIMessage(content="## boll_lb values from 2026-01-30 to 2026-04-30:\n2026-04-30: 32.70"),
            AIMessage(content="## atr values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.90"),
            AIMessage(content="## vwma values from 2026-01-30 to 2026-04-30:\n2026-04-30: 33.95"),
        ]

        with patch(
            "etfagents.agents.analysts.market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=report_with_boilerplate_intro), report_with_boilerplate_intro),
        ):
            result = node(
                {
                    "company_of_interest": "601899.SH",
                    "trade_date": "2026-04-30",
                    "messages": indicator_messages,
                }
            )

        self.assertEqual(result["market_report"], llm.final_content)

    def test_market_analyst_rewrites_false_missing_50sma_claim(self):
        llm = _CapturingLLM(
            "# 修正后市场报告\n\n"
            "50日SMA并未缺失，当前价格仍处于中长期均线之上，但若后续跌回50日SMA下方，则中期趋势强度会明显减弱。"
        )
        node = create_market_analyst(llm)

        false_missing_report = (
            "# 市场技术报告\n\n"
            "趋势仍偏多，若回踩关键均线不破则可继续持有。\n\n"
            "200日简单移动平均线：最新读数为33.27，仍提供中长期支撑。10日指数移动平均线：最新读数为34.01，短线趋势仍偏强。"
            "50日简单移动平均线：该指标数据未提供，暂无法纳入中期趋势拐点研判。MACD位于信号线上方，若后续跌破VWMA则应等待。"
        )
        indicator_messages = [
            HumanMessage(content="请分析 601899.SH"),
            AIMessage(content="## close_50_sma values from 2026-01-30 to 2026-04-30:\n2026-04-30: 35.24"),
            AIMessage(content="## close_200_sma values from 2026-01-30 to 2026-04-30:\n2026-04-30: 33.27"),
            AIMessage(content="## close_10_ema values from 2026-01-30 to 2026-04-30:\n2026-04-30: 34.01"),
            AIMessage(content="## macd values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.12"),
            AIMessage(content="## macds values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.08"),
            AIMessage(content="## macdh values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.04"),
            AIMessage(content="## rsi values from 2026-01-30 to 2026-04-30:\n2026-04-30: 58.2"),
            AIMessage(content="## boll values from 2026-01-30 to 2026-04-30:\n2026-04-30: 33.60"),
            AIMessage(content="## boll_ub values from 2026-01-30 to 2026-04-30:\n2026-04-30: 34.50"),
            AIMessage(content="## boll_lb values from 2026-01-30 to 2026-04-30:\n2026-04-30: 32.70"),
            AIMessage(content="## atr values from 2026-01-30 to 2026-04-30:\n2026-04-30: 0.90"),
            AIMessage(content="## vwma values from 2026-01-30 to 2026-04-30:\n2026-04-30: 33.95"),
        ]

        with patch(
            "etfagents.agents.analysts.market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=false_missing_report), false_missing_report),
        ):
            result = node(
                {
                    "company_of_interest": "601899.SH",
                    "trade_date": "2026-04-30",
                    "messages": indicator_messages,
                }
            )

        self.assertEqual(result["market_report"], llm.final_content)


if __name__ == "__main__":
    unittest.main()
