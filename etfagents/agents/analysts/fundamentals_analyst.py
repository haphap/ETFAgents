import re

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_collaboration_stop_instruction,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
    get_output_language,
    normalize_display_numbering,
    normalize_chinese_role_terms,
    truncate_for_prompt,
)
from etfagents.tool_report_utils import run_tool_report_chain


_REQUIRED_FUNDAMENTAL_TOOLS = ("get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement")
_FUNDAMENTAL_TOOL_OUTPUT_MARKERS = {
    "get_fundamentals": ("# tushare fundamentals for ", "# company fundamentals for "),
    "get_balance_sheet": ("# tushare balance sheet for ", "# balance sheet data for "),
    "get_cashflow": ("# tushare cashflow for ", "# cash flow data for "),
    "get_income_statement": ("# tushare income statement for ", "# income statement data for "),
}
_INCOMPLETE_FUNDAMENTALS_MARKERS = (
    "无法直接计算资产负债率",
    "估值数据缺失",
    "无股价",
    "股价缺失",
    "当前数据源未提供总资产",
    "当前数据源未提供总负债",
    "当前数据源未提供总资产、总负债、资产负债率及期末现金余额",
    "当前数据源中未提供明确的同业样本数据",
    "无直接同业样本",
    "亦无前瞻盈利预测值",
    "暂无晚于",
    "无业绩预告，无前瞻pe数据",
    "missing total assets",
    "missing total liabilities",
    "missing price",
    "valuation data missing",
    "unable to calculate debt to assets",
    "缺少具体的 total assets",
    "缺少具体的 total liabilities",
)
_CHINESE_SECTION_TITLES = {
    "Fundamentals Overview and Valuation Snapshot": "核心概览与估值快照",
    "Balance Sheet Analysis": "资产负债表分析",
    "Income Statement Analysis": "利润表分析",
    "Cash Flow Analysis": "现金流分析",
    "Growth, R&D, and Business Composition Analysis": "增长、研发与主营业务分析",
    "Earnings Guidance and Forward Valuation": "业绩预告与前瞻估值",
    "Peer Comparison": "同业对比",
}


def _message_text(message) -> str:
    return extract_text_content(getattr(message, "content", None))


def _collected_fundamentals_context(messages) -> str:
    return "\n\n".join(filter(None, (_message_text(message) for message in messages)))


def _collected_fundamental_tool_names(messages) -> set[str]:
    collected = set()
    for message in messages:
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = tool_call.get("name")
            if name in _REQUIRED_FUNDAMENTAL_TOOLS:
                collected.add(name)

        normalized = _message_text(message).lower()
        for tool_name, markers in _FUNDAMENTAL_TOOL_OUTPUT_MARKERS.items():
            if any(marker in normalized for marker in markers):
                collected.add(tool_name)

    return collected


def _missing_fundamental_tools(messages) -> list[str]:
    collected = _collected_fundamental_tool_names(messages)
    return [tool_name for tool_name in _REQUIRED_FUNDAMENTAL_TOOLS if tool_name not in collected]


def _report_has_full_fundamentals_coverage(report: str) -> bool:
    normalized = (report or "").lower()
    if any(marker in normalized for marker in _INCOMPLETE_FUNDAMENTALS_MARKERS):
        return False
    required_keyword_groups = (
        ("balance sheet", "资产负债表"),
        ("income statement", "利润表", "revenue", "营收", "net income", "净利润"),
        ("cash flow", "cashflow", "现金流"),
        ("roe",),
        ("gross margin", "毛利率"),
        ("net margin", "净利率"),
        ("debt to assets", "资产负债率", "leverage", "杠杆"),
        ("free cash flow", "自由现金流"),
        ("growth", "增速", "增长"),
    )
    return all(any(keyword in normalized for keyword in group) for group in required_keyword_groups)


def _tool_context_has_any(messages, *tokens: str) -> bool:
    context = _collected_fundamentals_context(messages)
    return any(token in context for token in tokens)


def _report_contradicts_available_fundamental_data(report: str, messages) -> bool:
    normalized_report = (report or "").lower()
    if not normalized_report:
        return True

    contradictions = (
        (
            _tool_context_has_any(messages, "Total Assets:", "总资产", "Asset-Liability Ratio:", "Debt to Assets:", "Cash:"),
            (
                "当前数据源未提供总资产",
                "当前数据源未提供总负债",
                "当前数据源未提供总资产、总负债、资产负债率及期末现金余额",
                "missing total assets",
                "missing total liabilities",
            ),
        ),
        (
            _tool_context_has_any(messages, "Latest Forecast Announcement Date:", "Forecast Summary:", "Forecast Reason:"),
            (
                "当前数据源中暂无晚于",
                "无业绩预告",
                "亦无前瞻盈利预测值",
                "no current earnings guidance",
                "no earnings guidance",
            ),
        ),
        (
            _tool_context_has_any(messages, "Peer Sample Basis:", "Peer Sample:", "Target vs Peer Median:"),
            (
                "当前数据源中未提供明确的同业样本数据",
                "无直接同业样本",
                "未提供明确的同业样本数据",
                "no peer sample",
                "peer sample unavailable",
            ),
        ),
    )

    return any(
        available and any(marker in normalized_report for marker in markers)
        for available, markers in contradictions
    )


def _is_chinese_fundamentals_output() -> bool:
    return get_output_language().strip().lower() in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


def _normalize_fundamentals_report_text(report: str) -> str:
    normalized = normalize_chinese_role_terms(report) if report else report
    if not normalized:
        return normalized

    for filler in (
        "根据最新工具输出数据，",
        "根据最新工具输出数据",
        "基于最新工具输出数据，",
        "基于最新工具输出数据",
        "According to the latest tool output, ",
        "According to the latest tool output,",
    ):
        normalized = normalized.replace(filler, "")

    if _is_chinese_fundamentals_output():
        normalized = re.sub(
            r"(?m)^(\s*(?:#{1,6}\s*)?(?:(?:[一二三四五六七八九十]+|\d+)[、.．]\s*)?)[A-Za-z][A-Za-z0-9,&/ \-]*\(([^()\n]+)\)\s*$",
            lambda match: f"{match.group(1)}{match.group(2).strip()}",
            normalized,
        )
        for english, chinese in _CHINESE_SECTION_TITLES.items():
            normalized = re.sub(
                rf"(?m)^(\s*(?:#{1,6}\s*)?(?:(?:[一二三四五六七八九十]+|\d+)[、.．]\s*)?){re.escape(english)}\s*$",
                rf"\1{chinese}",
                normalized,
            )

    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalize_display_numbering(normalized).strip()


def _rewrite_expectations() -> str:
    if _is_chinese_fundamentals_output():
        return """你必须使用以下中文标题，且只保留中文标题，不要出现英文标题或“英文+中文括号”：
一、核心概览与估值快照
二、资产负债表分析
三、利润表分析
四、现金流分析
五、增长、研发与主营业务分析
六、业绩预告与前瞻估值
七、同业对比

写作要求：
- 每一节都要先引用关键数据，再解释这些数据意味着什么，以及它们对盈利质量、估值安全边际、成长持续性、竞争格局和交易判断的影响。
- 禁止只罗列数字或把工具结果改写成数据清单。
        - 如果提供了 PEG、研发强度、主营业务构成、业绩预告、前瞻市盈率或同业样本，就必须纳入分析。
- 研发部分要讨论研发费用规模、研发强度、对利润率的短期影响，以及对技术壁垒和产品竞争力的中长期意义。
        - 主营业务部分要结合公司概况 / 主营业务 / 业务结构，分析收入来源、业务集中度、结构变化与盈利弹性。
        - 业绩预告与前瞻估值部分：若存在晚于最新财报期的业绩预告并能计算前瞻市盈率，就给出数值并解释；若没有，就明确说明暂无可用的前瞻指引。
- 同业对比部分：结合提供的 peer sample，比较至少两个维度（如 PE/PB/ROE/净利润增速），说明公司相对同业是溢价还是折价，以及这种定价是否合理。
- 若工具结果中已经出现资产负债表关键快照、业绩预告字段或同业样本，不得写成“数据源未提供”。
- 若存在历史业绩预告，但 `Forward PE Status` 明确说明该预告不晚于最新财报期，要准确表述为“有历史业绩预告，但不足以计算当前前瞻市盈率”，不要误写成“没有业绩预告”。
- 若出现 `Peer Sample Basis`、`Peer Sample` 或 `Target vs Peer Median`，必须明确使用这些同业样本，不得写成“无同业样本”。
- 避免套话，例如“根据最新工具输出数据”。
- 末尾必须附上 Markdown 总结表，列至少包括：维度、关键数据、分析结论。
"""

    return """Use these section titles in the final report:
1. Fundamentals Overview and Valuation Snapshot
2. Balance Sheet Analysis
3. Income Statement Analysis
4. Cash Flow Analysis
5. Growth, R&D, and Business Composition Analysis
6. Earnings Guidance and Forward Valuation
7. Peer Comparison

Writing requirements:
- Every section must cite the key metrics and then interpret what those numbers mean for quality, valuation, growth durability, competitive position, and trading implications.
- Do not merely list numbers or restate tool output as a data dump.
- If PEG, R&D intensity, business mix, earnings guidance, forward PE, or peer samples are present, incorporate them into the analysis.
- The R&D section must discuss spending scale, R&D intensity, near-term margin impact, and long-term moat implications.
- The business mix section must use company profile / main business / segment mix to analyze revenue drivers, concentration, mix shift, and earnings sensitivity.
- The guidance section must calculate and interpret forward PE when a forward-looking earnings guide newer than the latest reported period exists; otherwise say that no current guidance is available.
- The peer section must compare at least two dimensions from the provided peer sample (for example PE/PB/ROE/net profit growth) and explain whether the company deserves a premium or discount.
- If the tool output already includes balance-sheet key snapshots, earnings-guidance fields, or peer-sample fields, do not claim the data source failed to provide them.
- If historical earnings guidance exists but `Forward PE Status` says that the forecast is not newer than the latest reported financial period, state that historical guidance exists but is insufficient for a current forward-PE calculation; do not claim there is no earnings guidance at all.
- If `Peer Sample Basis`, `Peer Sample`, or `Target vs Peer Median` appears in the tool output, you must use that peer sample rather than writing that no peer sample is available.
- Avoid filler phrases such as 'According to the latest tool output'.
- End with a markdown summary table with at least: Dimension, Key Data, Analytical Takeaway.
"""


def _fetch_missing_fundamental_data(symbol: str, current_date: str, missing_tools: list[str]) -> str:
    tool_map = {
        get_fundamentals.name: get_fundamentals,
        get_balance_sheet.name: get_balance_sheet,
        get_cashflow.name: get_cashflow,
        get_income_statement.name: get_income_statement,
    }
    tool_args = {
        "get_fundamentals": {"ticker": symbol, "curr_date": current_date},
        "get_balance_sheet": {"ticker": symbol, "freq": "quarterly", "curr_date": current_date},
        "get_cashflow": {"ticker": symbol, "freq": "quarterly", "curr_date": current_date},
        "get_income_statement": {"ticker": symbol, "freq": "quarterly", "curr_date": current_date},
    }

    outputs = []
    for tool_name in missing_tools:
        outputs.append(
            f"### {tool_name}\n{tool_map[tool_name].invoke(tool_args[tool_name])}"
        )
    return "\n\n".join(outputs)


def _rewrite_fundamentals_report(
    llm,
    symbol: str,
    current_date: str,
    instrument_context: str,
    messages,
    missing_tools: list[str],
) -> str:
    existing_context = truncate_for_prompt(
        _collected_fundamentals_context(messages),
        default_limit=24000,
    )
    additional_fundamental_data = _fetch_missing_fundamental_data(symbol, current_date, missing_tools)
    rewrite_prompt = f"""You are a trading assistant writing the final fundamentals report.
Use only the fundamentals and financial statement data supplied below. Do not invent values.

You must explicitly cover the fundamentals overview, balance sheet, income statement, cash flow, growth, R&D, business mix, earnings guidance / forward valuation, and peer comparison in the final report when the data is available.
{_rewrite_expectations()}

The tool outputs may include `# Key snapshot` blocks with already-extracted figures. Prefer those concrete values first, then use the raw CSV for extra detail.
If a value appears anywhere in the provided data, do not claim it is missing. In particular, do not say price, valuation, total assets, total liabilities, debt-to-assets, or ending cash are unavailable when they are present in the tool output.
Only say a metric is unavailable when it truly does not appear in any provided tool result.
Do not output tool calls. Write a detailed, data-backed markdown report and end with a markdown summary table.
{instrument_context}{get_language_instruction()}

Current date: {current_date}

Existing conversation data:
{existing_context}

Additional statement data fetched to complete the report:
{additional_fundamental_data}
"""
    return _normalize_fundamentals_report_text(extract_text_content(llm.invoke(rewrite_prompt).content))


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Your fundamental analysis must rely only on the structured accounting and financial statement data returned by the fundamentals tools. Do not use news flow, sentiment, rumors, or macro headlines to justify accounting conclusions. Before writing the final report, you must gather data from all of these tools unless a tool explicitly fails: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, and `get_income_statement`. The final report must explicitly cover the balance sheet, income statement, cash flow statement, and core indicators such as ROE, margins, leverage, cash flow quality, growth, PEG when available, R&D, business composition, earnings guidance / forward valuation, and peer comparison where the data allows it. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Do not just list figures; explain what the figures imply. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction()
        )

        prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " Use the provided tools to progress towards answering the question."
                        " If you are unable to fully answer, that's OK; another assistant with different tools"
                        " will help where you left off. Execute what you can to make progress."
                        + get_collaboration_stop_instruction()
                        + " You have access to the following tools: {tool_names}.\n{system_message}"
                        + "For your reference, the current date is {current_date}. {instrument_context}"
                    ),
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        result, report = run_tool_report_chain(
            prompt_template,
            llm,
            tools,
            state["messages"],
            system_message=system_message,
            tool_names=", ".join([tool.name for tool in tools]),
            current_date=current_date,
            instrument_context=instrument_context,
        )
        report = _normalize_fundamentals_report_text(report) if report else report

        report_messages = [*state["messages"], result]
        if not getattr(result, "tool_calls", None):
            missing_tools = _missing_fundamental_tools(report_messages)
            completed_report = _rewrite_fundamentals_report(
                llm,
                state["company_of_interest"],
                current_date,
                instrument_context,
                report_messages,
                missing_tools,
            )
            if completed_report:
                result = AIMessage(content=completed_report)
                report = completed_report
        elif report:
            result = AIMessage(content=report)

        final_messages = [*state["messages"], result]
        if report and (
            not _report_has_full_fundamentals_coverage(report)
            or _report_contradicts_available_fundamental_data(report, final_messages)
        ):
            completed_report = _rewrite_fundamentals_report(
                llm,
                state["company_of_interest"],
                current_date,
                instrument_context,
                final_messages,
                _missing_fundamental_tools(final_messages),
            )
            if completed_report:
                result = AIMessage(content=completed_report)
                report = completed_report

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
