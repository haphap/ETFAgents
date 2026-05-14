import functools
from langchain_core.messages import AIMessage

from etfagents.agents.schemas import TraderProposal, render_trader_proposal
from etfagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_with_result,
)
from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_localized_execution_bias_instruction,
    get_language_instruction,
    get_output_language,
    normalize_chinese_manager_terms,
    truncate_for_prompt,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value, with_state_aliases
from etfagents.backtest.signals import build_trader_backtest_signal


def _trader_detail_instruction() -> str:
    if get_output_language().strip().lower() in {'chinese', '中文', 'zh', 'zh-cn', 'zh-hans'}:
        return (
            '对于 ETF 配置执行计划和风险控制，不能只写”等待支撑””观察成交量””关注资金流”这类泛化表述而不给解释。'
            '每个论据必须引用上方报告中的具体数据，不能只写泛化判断。请明确什么算关键支撑或阻力，并优先引用市场报告中的具体类型和数值'
            '（例如50日均线位于X元、布林中轨位于Y元、前低位于Z元）；'
            '不要写“市场报告中的关键位”“前文提到的50日均线”这类让读者回头查找的表述，必须把数值直接重写在当前句子里。'
            '同时说明成交量或资金流改善应相对近5日或20日均量达到什么程度（如”成交量需达到近20日均量的1.3倍以上”）；'
            '以及什么样的宏观、风格或结构催化确认才足以支持加仓、持有、减仓、轮动或退出（如利率决议时间、指数成分调整窗口、资金流向阈值）；'
            '还需要说明 ETF 结构验证的具体指标（如份额变化幅度、溢折价偏离百分比、跟踪误差、前十大持仓集中度百分比）。'
            '这两部分必须写成完整分析段落，并给出清晰阈值与触发条件。'
            '若没有上方报告里的具体价位、均线数值、量能基数或份额/溢折价数据，就不要下加仓、减仓或回补指令。'
            '优先写成“2.08元的50日均线、2.05元的布林中轨、成交量回到20日均量的1.3倍、份额连续2日净申购”这种可执行格式。'
        )
    return (
        "For the ETF allocation execution plan and risk controls, do not use generic phrases such as 'wait for support', 'watch volume', or 'monitor fund flows' without explanation. "
        "Every argument must quote specific data from the reports above — do not rely on generic judgments. "
        "Spell out what counts as key support or resistance by referencing the market report with exact numbers (e.g., 50-day SMA at X, Bollinger mid-band at Y, prior swing low at Z), "
        "and restate those numbers inline in the same sentence instead of telling the reader to look back at the market report. "
        "what level of volume or fund-flow recovery counts as improvement (e.g., 'volume must reach 1.3x the 20-day average of N shares'), "
        "what specific macro, style, or structure catalyst confirmation would justify adding, holding, reducing, rotating, or exiting (e.g., rate decision dates, index rebalancing windows, fund-flow thresholds), "
        "and what ETF structure checks matter (e.g., share change magnitude, premium-discount deviation percentage, tracking error, top-10 holdings concentration percentage). "
        "Write these sections as full analytical paragraphs with explicit thresholds and trigger conditions. "
        "If you cannot cite concrete price levels, moving-average values, volume baselines, or ETF share / premium-discount data from the reports above, do not issue add, reduce, or rebuild instructions."
    )


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        investment_plan = truncate_for_prompt(get_state_value(state, "research_allocation_plan", ""))
        market_flow_report = truncate_for_prompt(get_state_value(state, "market_flow_report", ""))
        catalyst_sentiment_report = truncate_for_prompt(get_state_value(state, "catalyst_sentiment_report", ""))
        macro_regime_report = truncate_for_prompt(get_state_value(state, "macro_regime_report", ""))
        meso_commodity_report = truncate_for_prompt(get_state_value(state, "meso_commodity_report", ""))
        holdings_industry_report = get_state_value(state, "holdings_industry_report", "")
        top_holdings_report = get_state_value(state, "top_holdings_report", "")

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an ETF allocation view tailored for {asset_symbol}. {instrument_context} This view incorporates insights from current technical market trends, macroeconomic indicators, commodity signals, market flows, event-driven sentiment, industry structure, and constituent-level research. Use this view as a foundation for evaluating your next ETF allocation decision.\n\nProposed Allocation View: {investment_plan}\n\nMacro regime analysis: {macro_regime_report}\nMeso commodity analysis: {meso_commodity_report}\nMarket and flow analysis: {market_flow_report}\nSentiment and catalyst impact analysis: {catalyst_sentiment_report}\nETF holdings-industry research: {holdings_industry_report}\nETF top holdings research: {top_holdings_report}\n\nLeverage these insights to make an informed and disciplined ETF allocation decision.",
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an ETF allocation strategist analyzing market data to make ETF exposure decisions. "
                    "Provide a clear allocation thesis, an execution plan, and explicit rebalance and risk controls. "
                    "Your first sentence in each section must state the current base-case view rather than circling around it. "
                    "The three sections must open with DIFFERENT sentences — never use the same or near-identical first sentence across sections. "
                    "In the ETF allocation thesis (section 一), the opening sentence must state WHY the evidence supports this stance (e.g., '当前宏观压制边际缓和、行业盈利改善信号同步出现，偏多逻辑更完整'); do not mention sizing, levels, or execution steps. "
                    "In the execution plan (section 二), the opening sentence must state WHAT to do and at what levels (e.g., '先以目标仓位的20%—30%建立试探仓，价格站回50日均线上方后逐步加仓'); do not restate the thesis rationale. "
                    "In rebalance and risk controls (section 三), focus on failure conditions, rebalance triggers, cut or restore rules, and what must be monitored next; do not repeat the thesis or execution sentence verbatim. "
                    "Do not stack multiple rating labels with different wording. "
                    "If you mention timing in Chinese output, translate it as 时机 or 节奏 instead of leaving the English word. "
                    "For ordinary lists, use Arabic numerals such as 1. 2. 3.; if you use Chinese section headings, keep forms like 一、二、三. "
                    f"{_trader_detail_instruction()} "
                    f"{get_localized_execution_bias_instruction()}{get_language_instruction()}"
                ),
            },
            context,
        ]

        rendered_result, structured_result = invoke_structured_or_freetext_with_result(
            structured_llm,
            llm,
            messages,
            functools.partial(render_trader_proposal, context_text=market_flow_report),
            "Trader",
        )
        rendered_result = normalize_chinese_manager_terms(rendered_result)
        trader_backtest_signal = build_trader_backtest_signal(
            asset_symbol,
            str(state.get("trade_date", "")),
            rendered_result,
            structured_result,
        )

        return with_state_aliases({
            "messages": [AIMessage(content=rendered_result)],
            "trader_allocation_plan": rendered_result,
            "trader_backtest_signal": trader_backtest_signal,
            "sender": name,
        })

    return functools.partial(trader_node, name="Trader")
