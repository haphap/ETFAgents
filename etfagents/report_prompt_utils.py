def get_no_process_narration_instruction() -> str:
    return (
        " Do NOT narrate your workflow, tool usage, data retrieval, or report-writing process. "
        "Do not say that data has been fetched, collected, organized, or is ready, and do not announce that you are about to write, continue, or present the analysis. "
        "Never begin with process lead-ins such as '数据已获取完毕', '报告已就绪', '现在我来', '接下来', '下面', '我将', 'Now let me', 'I will', or 'Next'. "
        "Do NOT mirror prompt scaffolding like '数据获取', '数据来源', '分析指引', '第一步', or 'Step 1' as headings in the final report."
    )
