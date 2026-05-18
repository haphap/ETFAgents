import re


PROCESS_DATA_READY_FRAGMENT = (
    r"(?:(?:全部|所有|必要|所需)?(?:数据|资料|信息).{0,20}?(?:已经|已)?(?:全部|所有|必要|所需)?"
    r".{0,20}?(?:获取|收集|拿到|完成|掌握|到位|就绪|齐备)(?:完毕)?"
    r"|(?:已经|已).{0,20}?(?:获取|收集|拿到|完成|掌握|到位|就绪|齐备).{0,20}?(?:数据|资料|信息))"
)
PROCESS_REPORT_READY_FRAGMENT = (
    r"(?:报告|分析|内容).{0,12}(?:已|已经)?(?:就绪|完成|生成|整理好|准备好)"
)
PROCESS_REPORT_ACTION_FRAGMENT = (
    r"(?:以下|下面|现在|接下来|下一步|随后|开始|将|马上|准备|继续|直接|正式|可以|能够).{0,80}?"
    r"(?:撰写|生成|输出|写|整合|展开|梳理|汇总|组织|呈现|给出|形成|进入)"
    r"[^。！？!?；;\n]{0,60}?"
    r"(?:分析报告|研究报告|诊断报告|研究分析|报告|分析|诊断|研究|正文|结论|观点|判断|框架)"
    r"[^。！？!?；;\n]{0,20}"
)
PROCESS_PRESENTATION_FRAGMENT = (
    r"(?:以下|下面)(?:是|为).{0,100}?"
    r"(?:分析报告|研究报告|诊断报告|研究分析|报告|分析|诊断|研究|正文|结论|观点|判断|框架|计划|决策|配置)"
)

OPENING_DELIVERY_PREAMBLE_RE = re.compile(
    r"^\s*(?:"
    + PROCESS_REPORT_READY_FRAGMENT
    + r"[。！!；;，,]?\s*"
    + r"(?:"
    + PROCESS_REPORT_ACTION_FRAGMENT
    + r"|"
    + PROCESS_PRESENTATION_FRAGMENT
    + r"|(?:以下|下面|现在|接下来|下一步)"
    + r")"
    + r"|"
    + PROCESS_DATA_READY_FRAGMENT
    + r"[。！!；;，,]?\s*"
    + r"(?:"
    + PROCESS_REPORT_ACTION_FRAGMENT
    + r"|"
    + PROCESS_PRESENTATION_FRAGMENT
    + r")"
    + r"|以下(?:是|为).{0,60}(?:报告|分析)"
    + r")"
)


def first_nonempty_line(text: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return next((line.strip() for line in lines if line.strip()), "")


def looks_like_process_narration(text: str) -> bool:
    """Detect leading workflow/status narration rather than report content."""
    first_line = first_nonempty_line(text)
    return bool(
        first_line
        and len(first_line) <= 240
        and OPENING_DELIVERY_PREAMBLE_RE.match(first_line)
    )
