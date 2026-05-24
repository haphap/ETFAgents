from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_commodity_cluster_data,
    get_collaboration_stop_instruction,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.report_leads import (
    collect_top_section_marks,
    contains_qa_label_artifacts,
    contains_markdown_table,
    get_concise_heading_instruction,
    get_no_process_narration_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    has_invalid_opening_cap,
    post_judge_clean,
    pre_judge_clean,
    starts_without_overview_paragraph,
)
from etfagents.agents.utils.validate_refine import AnalystReportSpec, validate_and_refine
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.agents.utils.analysis_memory import (
    build_memory_prompt_section,
    inject_memory_prompt_section,
)
from etfagents.tool_report_utils import run_tool_report_chain


_REPORT_SPEC = AnalystReportSpec(
    analyst_name="meso_commodity",
    required_top_sections=("一", "二", "三", "四"),
    require_top_section_leads=True,
    lead_required_top_sections=("一", "二", "三"),
    custom_rules_markdown=(
        "### 内容覆盖\n"
        "- 是否包含四个一级章节：一、核心矛盾与主线判断；二、矛盾推演；三、情景推演与策略启示；四、近期合约表现总览？\n"
        "- 一、二、三章标题后是否直接写结论段？四、近期合约表现总览标题后是否直接承接Markdown表格？\n"
        "- 是否将报告锁定在一个可证伪的命题上？\n"
        "- 是否按交易矛盾（而非商品品类）组织分析？\n"
        "- 是否对每个矛盾给出方向倾向和确信度（低/中/高）？\n"
        "- 是否验证了上下游成本转嫁是否完整？\n"
        "- 是否设置了情景推演（基准/替代/尾部）并给出概率估计？\n"
        "- 四、近期合约表现总览下是否附近期合约表现总览表？"
    ),
)

_MESO_COMMODITY_REQUIRED_TOP_SECTIONS = set(_REPORT_SPEC.required_top_sections)
# Anchors must match the section names emitted by the prompt template below.
_MESO_COMMODITY_REQUIRED_MARKERS = ("核心矛盾", "近期合约表现总览")


def _looks_like_markdown_table_row(line: str) -> bool:
    stripped = (line or "").strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _looks_like_markdown_table_separator(line: str) -> bool:
    stripped = (line or "").strip()
    if not _looks_like_markdown_table_row(stripped):
        return False
    body = stripped.replace("|", "").replace(":", "").replace("-", "").strip()
    return "-" in stripped and not body


def _has_meso_commodity_overview_table_section(report: str) -> bool:
    """Require section 四 to contain the overview table directly below the heading."""
    lines = (report or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "四、近期合约表现总览":
            continue

        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor + 1 >= len(lines):
            return False
        return (
            _looks_like_markdown_table_row(lines[cursor])
            and _looks_like_markdown_table_separator(lines[cursor + 1])
        )

    return False


def _looks_like_complete_meso_commodity_report(report: str) -> bool:
    """Positive contract for accepting meso-commodity output into graph state."""
    content = report or ""
    if (
        not content.strip()
        or has_invalid_opening_cap(content)
        or contains_qa_label_artifacts(content)
    ):
        return False

    section_marks = collect_top_section_marks(content)
    if not _MESO_COMMODITY_REQUIRED_TOP_SECTIONS.issubset(section_marks):
        return False

    return (
        all(marker in content for marker in _MESO_COMMODITY_REQUIRED_MARKERS)
        and contains_markdown_table(content)
        and _has_meso_commodity_overview_table_section(content)
    )


def _ensure_meso_commodity_opening_cap(report: str) -> str:
    """Restore a visible opening cap when the model starts directly at section one."""
    if not report or not starts_without_overview_paragraph(report):
        return report or ""

    lines = report.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    first_heading_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().startswith("一、")
        ),
        None,
    )
    if first_heading_index is None:
        return report

    lead_lines: list[str] = []
    in_lead = False
    for line in lines[first_heading_index + 1:]:
        stripped = line.strip()
        if not stripped:
            if in_lead:
                break
            continue
        if stripped.startswith(("（", "二、", "三、", "四、", "|", "-", "*")):
            break
        in_lead = True
        lead_lines.append(stripped)

    opening = " ".join(lead_lines).strip()
    if not opening:
        return report
    return f"{opening}\n\n{report}"


def create_etf_structure_analyst(llm):
    def etf_structure_node(state):
        current_date = state.get("trade_date") or state.get("analysis_date")
        if not current_date:
            raise KeyError("trade_date")
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        memory_section = build_memory_prompt_section(state, role="meso_commodity", aliases=("etf_structure",))
        tools = [get_commodity_cluster_data]

        system_message = inject_memory_prompt_section((
            "你是一名中观商品分析师。核心使命是从商品价格异常和跨市场信号中发现宏观经济与产业层面的机会和问题。\n\n"
            + "优先使用Tushare期货和仓单的直接证据，而非股票或ETF代理工具。\n\n"
            "## 分析原则\n"
            "1. **冲突驱动，非目录驱动**：不得逐一罗列商品。识别2-3个跨商品矛盾（如'上游通胀 vs 下游通缩'、'制造业复苏 vs 投机性囤库'），追溯每个矛盾在多个合约上的表现。每个矛盾就是一个论点，不是数据堆砌。\n"
            "2. **强制跨链验证**：当上下游商品同时可得（如原油→PTA→聚酯；焦煤→焦炭→钢铁；豆粕→饲料），必须验证成本转嫁是否完整。将'上游涨、下游跌'标记为结构性宏观问题。\n"
            "3. **矛盾信号需要方向判断**：当价格、持仓量和仓单发出矛盾信号时，不得分别罗列各项事实。明确指出核心矛盾并给出方向倾向和确信度（低/中/高）。\n"
            "4. **每个异常必须回答两个问题**：(a) 这是机会信号还是风险信号？(b) 确信度多高？（低/中/高）\n"
            "5. **产业链断裂即宏观矛盾**：当上下游成本传导断裂（如上游涨但下游跌），将其从产业问题提升为宏观矛盾（如'内需不足'）。这是中观分析的核心价值——连接产业信号与宏观制度。\n"
            "6. **段落式表达**：所有结论必须写成连贯段落。不得使用'判断：'、'证据：'、'合约信号：'、'这意味着什么：'等问答式标签。数据自然融入句子，使输出读起来像专业策略报告而非工作底稿。\n\n"
            "## 多品种覆盖\n"
            "可访问以下按经济功能分类的合约：\n"
            "- 贵金属：金 (AU)、银 (AG)\n"
            "- 工业金属：铜 (CU)、铝 (AL)、铅 (PB)、镍 (NI)、锌 (ZN)\n"
            "- 能源：原油 (SC)\n"
            "- 新能源金属：碳酸锂 (LC)\n"
            "- 黑色链：螺纹钢 (RB)、热卷 (HC)、铁矿石 (I)、焦煤 (JM)\n"
            "- 化工链：PTA (TA)、甲醇 (MA)、聚乙烯 (L)\n"
            "- 农产品链：豆粕 (M)、玉米 (C)、棕榈油 (P)\n"
            "- 软商品：纸浆 (SP)、天然橡胶 (RU)\n"
            "- 工业品：工业硅 (SI)、尿素 (UR)、PVC (V)、纯碱 (SA)\n\n"
            "覆盖规则：所有发出异常信号的合约必须被提及。无异常信号的合约可省略以保持主线聚焦——不得为了填充内容而稀释叙述。\n\n"
            "## 报告结构\n"
            + get_no_process_narration_instruction() + "\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "报告含四个一级章节（一、二、三、四）。一、二、三章标题后直接写2-3句结论段，先给主导矛盾、传导路径和配置含义，然后空行进入子章节。四、近期合约表现总览标题后直接放Markdown表格，不写结论段、子章节或其他标题。不得以原始合约数据或孤立标签开篇。\n\n"
            "一、核心矛盾与主线判断\n"
            "开篇直接抛出一个可证伪的命题，而非模糊概述。"
            "必须明确关键路标：两周内，铜与热卷的需求强势能否驱动焦煤仓单去化？"
            "用该路标判断利润是沿产业链上移还是被上游成本压力吸收。"
            "自洽性必须清晰：超配逻辑仅在'量增大于价压'时成立；"
            "若焦煤仓单未能按时去化，应明确表示首要动作是减仓。\n"
            "整篇报告都围绕这一命题展开——下文所有内容都必须服务于它。\n\n"
            "二、矛盾推演\n"
            "按交易矛盾组织，而非按商品品类。每个子章节必须独占一行，前面有空行。"
            "各矛盾之间必须有逻辑联系——解释它们如何相互强化或矛盾"
            "（如'复苏驱动原材料需求 → 成本上升 → 中游利润压缩 → 最终抑制复苏'——一个反馈环）。\n"
            "每个矛盾的分析应为一个或多个连贯段落。在段落中自然编织：\n"
            "- 该组合约指向的共同信号\n"
            "- 价格/持仓量/仓单中的异常数据\n"
            "- 该信号是机会还是风险，对宏观/产业配置的含义\n"
            "- 确信度判断与跨链验证结果\n"
            "不得使用'判断：'、'证据：'、'合约信号：'、'这意味着什么：'等显式标签。\n"
            "当数据支撑时，必须深入剖析成本转嫁失败的结构性原因。"
            "例如，若聚乙烯库存持续极端，不能止步于'需求疲弱'；要解释这如何映射到居民消费信心不足"
            "和PPI向CPI传导失败，从而支撑'成本推升型通胀被证伪'的宏观结论。\n"
            "当数据支撑时，还必须设置证伪检查点。例如，若白银强势被解读为工业需求，"
            "必须明确说仓单必须同步下降；价格、持仓与仓单的背离是区分投机与真实去库的关键检验。\n\n"
            "（一）[矛盾名称，如'制造业复苏与上游需求']\n"
            "  - 以连贯段落书写，而非分段式标签。\n"
            "  - 矛盾、方向倾向、证据链、宏观含义和确信度融为一体。\n"
            "  - 以验证上游→中游→下游成本转嫁是否完整收尾。\n\n"
            "（二）[下一矛盾，如'成本承压与利润压缩']\n"
            "  - 同样段落式结构，末尾含跨链验证。\n\n"
            "（三）[下一矛盾，如有]\n\n"
            "三、情景推演与策略启示\n"
            "标题后先写2-3句结论段，概括基准情景、最大替代风险和ETF配置动作，再进入子章节。"
            "以情景框架替代旧式要点列表。每个情景必须写成完整段落，非标签式清单。"
            "每个情景段落必须包含：概率与核心逻辑、主导产业链与传导路径、可量化的触发或证伪条件、以及概率赋值的简要理由。\n\n"
            "（一）基准情景 — 概率估计 (%)\n"
            "  - 路径必须明确，如：'制造业景气 → 铜与热卷坚挺 → 钢厂提价成功转移成本 → 产业链价格中枢上移'。\n"
            "  - 解释为何此路径意味着基准情景下量增仍大于价压。\n\n"
            "（二）替代情景 — 概率估计 (%)\n"
            "  - 使用领先触发条件而非滞后总结。优选示例：'沪铜持仓一周内降幅超10%且现货升水收敛至平水'作为早期撤退信号。\n\n"
            "（三）尾部风险 — 概率估计 (%)\n"
            "  - 聚焦高杠杆合约如碳酸锂或原油的低估崩盘风险，触发条件如'3日跌幅超5%且价跌仓降'。\n\n"
            "四之前先说明：四、近期合约表现总览标题下一行必须是Markdown表格第一行，"
            "除空行外禁止任何说明文字、结论段、子章节或其他标题。"
            "该表使用商品快照作为事实附录，包含讨论过的关键合约及工具提供的精确字段，"
            "如最新水平、近期价格表现、持仓变化、仓单变化和简短信号备注；不得编造不可用的指标。\n\n"
            "四、近期合约表现总览\n"
            "| 合约 | 最新水平 | 近期价格表现 | 持仓变化 | 仓单变化 | 信号备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| 示例合约 | 依工具数据填写 | 依工具数据填写 | 依工具数据填写 | 依工具数据填写 | 依工具数据填写 |\n\n"
            "## 风格要求\n"
            "- 正文第一段必须是独立开篇帽段，位于'一、核心矛盾与主线判断'之前；帽段直接写一中的核心矛盾论点，不得以'本报告将…'、'以下是…'、'本分析基于…'等元描述开头。\n"
            "- 开篇帽段不得使用括号插入名词解释、术语解释、英文简称或白话注释；若必须解释术语，直接融入句子，不要写成'（……）'。\n"
            "- 当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用'分别为'连接，不得逐个单独陈述。\n"
            "- 若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出'数据缺失''数据不足'等提示。\n"
            "- 开篇帽段和每个一级章节标题后的结论段都必须直接陈述结论。不得使用'本章''本节''本部分''该部分''这一节'等自指式开头（如'本章旨在梳理''本节核心结论指出''本部分结论表明''该部分说明'）。\n"
            "- 不要写'本节锁定'、'本节聚焦'、'本节讨论'、'本节围绕'、'该节…'、'这一节…'等自我指代句式，直接把矛盾、证据链和配置含义写成结论句。\n"
            "- 标题后的结论段必须高于子章节层面：综合主导矛盾、传导路径和ETF配置含义。"
            "不得简单复述即将在子章节中出现的相同合约观察。\n"
            "- 每句话必须传达具体数据点、异常或配置含义。删除'深度挂钩'、'全面覆盖'、'值得注意的是'、'it is worth noting'等填充语。\n"
            "- 连续出现三个以上裸数据片段后必须立即解释其揭示的矛盾和配置含义。\n"
            "- 不得用平行句式逐一罗列合约。将它们归入2-3个矛盾主题，解释为何这些矛盾对ETF配置重要。\n"
            "- 替换重复用词如'反噬'，使用'利润挤压'、'成本倒逼'、'负反馈'等精确替代表述。\n"
            "- 反面示例（禁止）：'判断：方向偏多。合约信号：沪铜30D +6.28%... 这意味着：价涨仓增形态...'\n"
            "- 正面示例（目标风格）：'本期沪铜以6.28%的涨幅配合近50%的仓单骤降，是典型的价量齐升去库组合，确认了下游实物需求的强劲接货意愿。这组信号整体偏多，确信度中等，但需留意高杠杆资金的短期扰动。'\n"
            "- 引用数字时必须成对呈现（如'30D +8%, 90D -2%'）以显示动量背景。\n"
            "- 像向只想看结论的投资组合经理汇报一样写作。"
            + get_language_instruction()
        ), memory_section)

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
                        + " For your reference, the current date is {current_date}. {instrument_context}"
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
            tool_names=", ".join(tool.name for tool in tools),
            current_date=current_date,
            instrument_context=instrument_context,
            report_acceptance_check=_looks_like_complete_meso_commodity_report,
            unexecuted_tool_recovery={
                "trigger_tool_names": [tool.name for tool in tools],
                "tool_payloads": [
                    {
                        "tool": get_commodity_cluster_data,
                        "payload": {"curr_date": current_date, "look_back_days": 240},
                    },
                ],
            },
        )
        report = normalize_chinese_role_terms(report) if report else report
        report = pre_judge_clean(report) if report else report
        report = validate_and_refine(report, llm, _REPORT_SPEC) if report else report
        report = post_judge_clean(report) if report else report
        report = _ensure_meso_commodity_opening_cap(report) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "meso_commodity_report": report,
        })

    return etf_structure_node
