"""Self-critique + refine pipeline for analyst reports.

Two-step process:
1. Judge: LLM evaluates the report against structured rules, outputs JSON verdict
2. Refine: If issues found, LLM fixes the report using specific defects from verdict
"""

import json
import logging
import re

from etfagents.content_utils import extract_text_content

logger = logging.getLogger(__name__)

_JUDGE_PROMPT_TEMPLATE = (
    "你是一名报告质量审核员。请严格按以下标准评审报告，并以JSON格式输出评审结果。\n\n"
    "## 通用评审标准\n\n"
    "### 结构完整性\n"
    "- 报告是否以2-4句概述段落开头（不得以标题或列表开头）？\n"
    "- 一级标题是否使用\"一、\"\"二、\"\"三、\"格式，且标题中不得包含英文翻译或括号注释？\n"
    "- 不得出现连续重复的一级标题\n"
    "- 每个一级章节是否以2-3句概括性导语开头，且导语高于子章节层面（不重复子章节内容）？\n"
    "- 第二部分（如有）是否直接写正文、未插入独立导语或帽段？\n"
    "- 不得出现\"##\"或其他markdown标题格式（应使用\"一、\"中文编号）\n\n"
    "### 术语解释\n"
    "- 所有中文技术术语（如\"多头排列\"\"金叉\"\"背离\"\"发散\"\"放量突破\"）首次出现时是否用通俗语言解释并说明交易含义？\n"
    "- 不得出现未解释的行话（如\"标准多头发散形态\"）\n\n"
    "### 可操作性\n"
    "- 是否在每个主要信号后回答了\"这意味着什么\"和\"对交易应该怎么做\"？\n"
    "- 开篇第一句是否直接陈述核心结论或判断（偏多/偏空/中性及原因），而非\"本报告将…\"等场景设置？\n\n"
    "### 禁止内容\n"
    "- 章节导语和段落开头不得使用任何自指式元叙述，包括但不限于：\"本部分结论表明\"\"该部分说明\"\"这一节意味着\"\"本节核心结论指出\"\"本节锁定\"\"本节聚焦\"\"本节讨论\"\"本节围绕\"\"本段核心观点是\"。正确做法是直接陈述结论，不提及\"本节\"\"本部分\"\"本段\"。\n"
    "- 不得使用\"判断：\"\"证据：\"\"关键价位：\"\"条件情景：\"等标签式结构\n"
    "- 不得出现\"结论依据\"scaffold标签\n"
    "- 不得讨论数据源分类噪声、券商标签噪声、搜索错配或检索伪影\n\n"
    "### 段落质量\n"
    "- 连续出现三个以上裸数据片段后是否有解释性语句？\n"
    "- 是否避免了\"值得注意的是\"\"深度挂钩\"\"全面覆盖\"等填充语？\n\n"
    "{analyst_specific_rules}\n\n"
    "## 评审报告\n\n"
    "{report}\n\n"
    "## 输出格式（严格JSON，不要输出其他内容）\n\n"
    "{{\n"
    '  "score": 0-10,\n'
    '  "pass": true/false,\n'
    '  "critical_issues": [\n'
    '    "具体问题描述（结构错误、缺少关键部分、多处无解释术语等）"\n'
    "  ],\n"
    '  "minor_issues": [\n'
    '    "次要问题（措辞不够精炼、个别数据缺解释等）"\n'
    "  ],\n"
    '  "missing_elements": ["缺失的具体元素"],\n'
    '  "general_comment": "总体评审意见，若合格则肯定优点"\n'
    "}}\n\n"
    "评分标准：\n"
    "- 9-10分：完全满足所有标准，pass=true\n"
    "- 7-8分：有minor_issues但无critical_issues，pass=true\n"
    "- 6分以下：存在critical_issues，pass=false\n"
    "- 任何结构错误、缺少关键章节、多处无解释术语 → critical_issue → pass=false"
)

_REFINE_PROMPT_TEMPLATE = (
    "你的报告存在以下问题，请重新生成完整报告以修正所有缺陷。保留原有正确部分，但必须完全满足评审标准。\n\n"
    "## 评审结果\n\n"
    "{judge_json}\n\n"
    "## 原始报告\n\n"
    "{report}\n\n"
    "## 要求\n"
    "- 重新生成完整报告，不是补丁\n"
    "- 逐一修正critical_issues中列出的所有问题\n"
    "- 补充missing_elements中列出的缺失内容\n"
    "- 保留原报告中正确的分析和数据\n"
    "- 严格遵守所有结构、术语、可操作性和风格要求\n\n"
    "直接输出修正后的完整报告。"
)

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_judge_json(text: str) -> dict | None:
    """Extract JSON verdict from judge response, tolerant of markdown fences."""
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def validate_and_refine(
    report: str,
    llm,
    analyst_specific_rules: str,
    *,
    score_threshold: int = 7,
) -> str:
    """Judge report quality and refine if needed.

    Args:
        report: The analyst report to validate.
        llm: The LLM instance (quick-thinking, no tools bound).
        analyst_specific_rules: Analyst-specific validation rules as markdown text.
        score_threshold: Minimum score to pass (default 7).

    Returns:
        Corrected report if score < threshold, original report otherwise.
        Returns original on any error.
    """
    if not report or not report.strip():
        return report

    # Step 1: Judge
    judge_prompt = _JUDGE_PROMPT_TEMPLATE.format(
        analyst_specific_rules=analyst_specific_rules,
        report=report,
    )
    try:
        judge_response = llm.invoke(judge_prompt)
        judge_text = extract_text_content(getattr(judge_response, "content", None))
    except Exception as exc:
        logger.warning("Validation judge failed: %s", exc)
        return report

    if not judge_text:
        return report

    verdict = _parse_judge_json(judge_text)
    if not verdict:
        logger.warning("Could not parse judge JSON from: %s", judge_text[:200])
        return report

    score = verdict.get("score", 0)
    passed = verdict.get("pass", False)
    critical = verdict.get("critical_issues", [])
    missing = verdict.get("missing_elements", [])

    logger.info(
        "Report validation: score=%s, pass=%s, critical=%d, missing=%d",
        score, passed, len(critical), len(missing),
    )

    if passed and score >= score_threshold:
        return report

    # Step 2: Refine
    logger.info("Report needs refinement: %s", "; ".join(critical[:3]))
    refine_prompt = _REFINE_PROMPT_TEMPLATE.format(
        judge_json=json.dumps(verdict, ensure_ascii=False, indent=2),
        report=report,
    )
    try:
        refined_response = llm.invoke(refine_prompt)
        refined_text = extract_text_content(getattr(refined_response, "content", None))
    except Exception as exc:
        logger.warning("Validation refine failed: %s", exc)
        return report

    return refined_text if refined_text else report
