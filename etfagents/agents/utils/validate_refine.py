"""Self-critique + refine pipeline for analyst reports.

Pipeline (per analyst):

  1. Static validation: cheap regex / substring checks driven by ``AnalystReportSpec``.
     Catches missing top sections, missing required tokens, markdown ``#``/``##``
     headings and label-style artifacts deterministically.
  2. LLM judge: when the chosen mode allows it, the judge runs as a structured
     output call (Pydantic ``JudgeVerdict``) so we no longer rely on a fragile
     ``\\{[\\s\\S]*\\}`` regex over a free-text response.
  3. Refine: only invoked when the merged verdict reports issues.

The ``validation_mode`` config flag (``static_only`` / ``static_plus_llm`` /
``llm_only`` / ``disabled``) selects which steps run, defaulting to
``static_plus_llm`` to preserve current behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from etfagents.content_utils import extract_text_content
from etfagents.tool_report_utils import TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX
from etfagents.agents.utils.report_leads import (
    collect_top_section_marks,
    contains_meta_openers,
    contains_qa_label_artifacts,
    contains_self_referential_meta_leads,
    find_top_sections_missing_leads,
    starts_without_overview_paragraph,
)
from etfagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_with_result,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spec / verdict models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalystReportSpec:
    """Structured validation spec consumed by both static and LLM checks."""

    analyst_name: str
    required_top_sections: tuple[str, ...] = ()
    """Top-level section markers that must appear, e.g. ``("一", "二", "三")``."""

    required_indicator_tokens: tuple[str, ...] = ()
    """Case-insensitive substrings that must appear somewhere in the report."""

    required_tail_tokens: tuple[str, ...] = ()
    """Substrings expected near the end of the report (table headers, etc.)."""

    require_top_section_leads: bool = False
    """Whether every required top-level section must include a prose lead.

    Only meaningful together with ``required_top_sections``; otherwise all
    detected top-level sections are checked.
    """

    custom_rules_markdown: str = ""
    """Free-form rules forwarded verbatim to the LLM judge prompt."""


@dataclass
class StaticVerdict:
    """Result of the regex / substring static validator."""

    critical_issues: list[str] = field(default_factory=list)
    missing_elements: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.critical_issues) or bool(self.missing_elements)


class JudgeVerdict(BaseModel):
    """Schema for the LLM judge response."""

    score: int = Field(0, ge=0, le=10)
    passed: bool = False
    critical_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)
    general_comment: str = ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_VALID_MODES = {"disabled", "static_only", "static_plus_llm", "llm_only"}


def _resolve_validation_mode(value: Optional[str]) -> str:
    if value is None:
        try:
            from etfagents.dataflows.config import get_config

            value = get_config().get("validation_mode")
        except Exception:  # pragma: no cover - config layer may be unavailable in tests
            value = None
    mode = (value or "static_plus_llm").strip().lower()
    if mode not in _VALID_MODES:
        logger.warning("Unknown validation_mode %r; defaulting to static_plus_llm", mode)
        return "static_plus_llm"
    return mode


def _coerce_spec(spec: AnalystReportSpec | str | None) -> AnalystReportSpec:
    if isinstance(spec, AnalystReportSpec):
        return spec
    if isinstance(spec, str):
        return AnalystReportSpec(
            analyst_name="legacy",
            custom_rules_markdown=spec,
        )
    return AnalystReportSpec(analyst_name="unknown")


def validate_and_refine(
    report: str,
    llm,
    spec: AnalystReportSpec | str,
    *,
    score_threshold: int = 7,
    validation_mode: Optional[str] = None,
) -> str:
    """Judge report quality and refine if needed.

    Args:
        report: The analyst report to validate.
        llm: The LLM instance (quick-thinking, no tools bound).
        spec: ``AnalystReportSpec`` describing the analyst-specific contract.
            For backward compatibility a raw markdown rules string is also
            accepted and wrapped in a spec carrying it as ``custom_rules_markdown``.
        score_threshold: Minimum score to pass (default 7).
        validation_mode: Override the configured mode. When omitted, reads
            ``validation_mode`` from the global config, defaulting to
            ``static_plus_llm``.

    Returns:
        Corrected report when issues are found, original report otherwise.
        Falls back to the original report on any unexpected error.
    """
    if not report or not report.strip():
        return report
    if report.lstrip().startswith(TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX):
        return report

    mode = _resolve_validation_mode(validation_mode)
    if mode == "disabled":
        return report

    resolved_spec = _coerce_spec(spec)

    static_verdict = (
        static_validate(report, resolved_spec)
        if mode != "llm_only"
        else StaticVerdict()
    )

    llm_verdict: JudgeVerdict | None = None
    if mode != "static_only":
        llm_verdict = _run_llm_judge(llm, report, resolved_spec)

    final_verdict = _merge_verdicts(
        mode=mode,
        static=static_verdict,
        llm=llm_verdict,
        score_threshold=score_threshold,
    )

    if final_verdict is None:
        # LLM judge failed and we have no static issues to act on.
        return report

    if final_verdict.passed and final_verdict.score >= score_threshold:
        return report

    logger.info(
        "Report validation triggered refine (mode=%s, score=%s, critical=%d, missing=%d)",
        mode,
        final_verdict.score,
        len(final_verdict.critical_issues),
        len(final_verdict.missing_elements),
    )

    refined = _run_llm_refine(llm, report, final_verdict)
    return refined or report


# ---------------------------------------------------------------------------
# Static validation
# ---------------------------------------------------------------------------


_MARKDOWN_H2_RE = re.compile(r"(?m)^\s*##\s+\S")
_MARKDOWN_H1_RE = re.compile(r"(?m)^\s*#\s+\S")


def static_validate(report: str, spec: AnalystReportSpec) -> StaticVerdict:
    """Run cheap structural / token checks. Never calls an LLM."""
    if not report:
        return StaticVerdict()

    issues: list[str] = []
    missing: list[str] = []

    section_marks = collect_top_section_marks(report)
    for need in spec.required_top_sections:
        if need not in section_marks:
            missing.append(f"缺少一级章节『{need}、…』")

    if spec.require_top_section_leads:
        for mark in find_top_sections_missing_leads(report, spec.required_top_sections):
            missing.append(f"一级章节『{mark}、…』缺少章节导语")

    if _MARKDOWN_H1_RE.search(report):
        issues.append("出现 markdown # H1 标题（应改为正文或中文一级编号）")
    if _MARKDOWN_H2_RE.search(report):
        issues.append("出现 markdown ## 二级标题（应使用 中文『（一）』格式）")
    if starts_without_overview_paragraph(report):
        issues.append("缺少开篇概述帽段，报告直接以标题、章节、列表或表格开头")

    lowered = report.lower()
    for token in spec.required_indicator_tokens:
        if token.lower() not in lowered:
            missing.append(f"未覆盖关键指标 / 数据『{token}』")

    if spec.required_tail_tokens:
        tail_window = report[-1500:] if len(report) > 1500 else report
        for tail in spec.required_tail_tokens:
            if tail not in tail_window:
                missing.append(f"末尾缺少元素『{tail}』")

    if contains_qa_label_artifacts(report):
        issues.append("出现『判断：』『证据：』『结论：』等标签式结构")
    if contains_self_referential_meta_leads(report):
        issues.append("出现自指式元叙述（如『本节锁定…』『本部分聚焦…』）")
    if contains_meta_openers(report):
        issues.append("段落以『本报告将…』『This report provides…』等元描述开头")

    return StaticVerdict(critical_issues=issues, missing_elements=missing)


# ---------------------------------------------------------------------------
# LLM judge (structured output) + free-text fallback
# ---------------------------------------------------------------------------


_JUDGE_BASE_RULES = (
    "你是一名报告质量审核员。请严格按以下标准评审报告，并以结构化方式返回评审结果。\n\n"
    "## 通用评审标准\n\n"
    "### 结构完整性\n"
    "- 报告是否以2-4句概述段落开头（不得以标题或列表开头）？\n"
    "- 一级标题是否使用「一、」「二、」「三、」格式，且标题中不得包含英文翻译或括号注释？\n"
    "- 不得出现连续重复的一级标题。\n"
    "- 每个一级章节是否以2-3句概括性导语开头，且导语高于子章节层面（不重复子章节内容）？\n"
    "- 不得出现 ## 或其他 markdown 标题格式（应使用中文编号）。\n\n"
    "### 术语解释\n"
    "- 所有中文技术术语首次出现时是否用通俗语言解释并说明交易含义？\n"
    "- 不得出现未解释的行话。\n\n"
    "### 可操作性\n"
    "- 是否在每个主要信号后回答了「这意味着什么」和「对交易应该怎么做」？\n"
    "- 开篇第一句是否直接陈述核心结论或判断（偏多/偏空/中性及原因），而非「本报告将…」等场景设置？\n\n"
    "### 禁止内容\n"
    "- 章节导语和段落开头不得使用任何自指式元叙述（「本节锁定…」「本部分聚焦…」等）。\n"
    "- 不得使用「判断：」「证据：」「关键价位：」「条件情景：」等标签式结构。\n"
    "- 不得讨论数据源分类噪声、券商标签噪声、搜索错配或检索伪影。\n\n"
    "### 段落质量\n"
    "- 连续三个以上裸数据片段后是否有解释性语句？\n"
    "- 是否避免了「值得注意的是」「深度挂钩」「全面覆盖」等填充语？\n\n"
)

_JUDGE_OUTPUT_GUIDE = (
    "## 评分标准\n"
    "- 9-10：完全满足所有标准，passed=true\n"
    "- 7-8：仅有 minor_issues 而无 critical_issues，passed=true\n"
    "- 6 及以下：存在 critical_issues，passed=false\n"
    "- 任何结构错误、缺少关键章节、多处无解释术语 → critical_issue → passed=false。\n"
)

_REFINE_PROMPT_TEMPLATE = (
    "你的报告存在以下问题，请重新生成完整报告以修正所有缺陷。保留原有正确部分，但必须完全满足评审标准。\n\n"
    "## 评审结果\n\n"
    "{verdict_json}\n\n"
    "## 原始报告\n\n"
    "{report}\n\n"
    "## 要求\n"
    "- 重新生成完整报告，不是补丁。\n"
    "- 逐一修正 critical_issues 中列出的所有问题。\n"
    "- 补充 missing_elements 中列出的缺失内容。\n"
    "- 保留原报告中正确的分析和数据。\n"
    "- 严格遵守所有结构、术语、可操作性和风格要求。\n\n"
    "直接输出修正后的完整报告，不要附带任何前言或元描述。"
)


def _build_judge_prompt(report: str, spec: AnalystReportSpec) -> str:
    custom = spec.custom_rules_markdown.strip()
    custom_block = f"## 分析师专属标准\n\n{custom}\n\n" if custom else ""
    return (
        _JUDGE_BASE_RULES
        + custom_block
        + _JUDGE_OUTPUT_GUIDE
        + "\n## 评审报告\n\n"
        + report
    )


_JSON_OBJECT_RE = re.compile(r"\{")


def _parse_judge_json(text: Any) -> JudgeVerdict | None:
    """Robustly parse the first balanced JSON object containing a ``score`` field."""
    if not isinstance(text, str) or not text:
        return None
    decoder = json.JSONDecoder()
    for match in _JSON_OBJECT_RE.finditer(text):
        try:
            payload, _ = decoder.raw_decode(text, match.start())
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict) or "score" not in payload:
            continue
        # Backward-compat: legacy callers / tests emit ``"pass"`` instead of ``"passed"``.
        if "pass" in payload and "passed" not in payload:
            payload = dict(payload)
            payload["passed"] = payload.pop("pass")
        try:
            return JudgeVerdict(**payload)
        except (TypeError, ValueError):
            continue
    return None


def _run_llm_judge(llm, report: str, spec: AnalystReportSpec) -> JudgeVerdict | None:
    structured_llm = bind_structured(llm, JudgeVerdict, "Report Judge")
    prompt = _build_judge_prompt(report, spec)
    try:
        rendered, structured_result = invoke_structured_or_freetext_with_result(
            structured_llm,
            llm,
            prompt,
            lambda v: v.model_dump_json(),
            "Report Judge",
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Judge invocation failed: %s", exc)
        return None

    if isinstance(structured_result, JudgeVerdict):
        return structured_result
    return _parse_judge_json(rendered)


def _run_llm_refine(llm, report: str, verdict: JudgeVerdict) -> str:
    refine_payload = {
        "score": verdict.score,
        "passed": verdict.passed,
        "critical_issues": verdict.critical_issues,
        "missing_elements": verdict.missing_elements,
        "general_comment": verdict.general_comment,
    }
    prompt = _REFINE_PROMPT_TEMPLATE.format(
        verdict_json=json.dumps(refine_payload, ensure_ascii=False, indent=2),
        report=report,
    )
    try:
        response = llm.invoke(prompt)
        return extract_text_content(getattr(response, "content", response)) or ""
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Refine invocation failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Verdict merging
# ---------------------------------------------------------------------------


def _merge_verdicts(
    *,
    mode: str,
    static: StaticVerdict,
    llm: JudgeVerdict | None,
    score_threshold: int,
) -> JudgeVerdict | None:
    """Combine static and LLM verdicts according to the active mode."""
    if mode == "static_only":
        if not static.has_issues:
            return JudgeVerdict(
                score=10,
                passed=True,
                critical_issues=[],
                missing_elements=[],
                general_comment="static_only: no structural issues detected",
            )
        return JudgeVerdict(
            score=4,
            passed=False,
            critical_issues=list(static.critical_issues),
            missing_elements=list(static.missing_elements),
            general_comment="static_only: failures detected by structural checks",
        )

    if llm is None:
        if static.has_issues:
            return JudgeVerdict(
                score=4,
                passed=False,
                critical_issues=list(static.critical_issues),
                missing_elements=list(static.missing_elements),
                general_comment="llm judge unavailable; relying on static checks",
            )
        return None

    if mode == "llm_only":
        return llm

    merged_critical = list(dict.fromkeys([*llm.critical_issues, *static.critical_issues]))
    merged_missing = list(dict.fromkeys([*llm.missing_elements, *static.missing_elements]))
    passed = llm.passed and not static.has_issues and llm.score >= score_threshold
    return JudgeVerdict(
        score=llm.score if not static.has_issues else min(llm.score, score_threshold - 1),
        passed=passed,
        critical_issues=merged_critical,
        minor_issues=list(llm.minor_issues),
        missing_elements=merged_missing,
        general_comment=llm.general_comment,
    )
