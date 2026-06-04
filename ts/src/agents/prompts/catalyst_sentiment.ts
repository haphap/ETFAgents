/**
 * System message for ``create_social_media_analyst`` (catalyst & sentiment).
 * Keep Chinese text and numbering rules identical to the Python source.
 *
 * Deterministic pre-fetch analyst (no LLM tool loop): the caller fetches ETF
 * info, holdings, and ticker/holdings/global news up front and embeds them as
 * data blocks, matching the Python flow.
 */

import type { AnalystReportSpec } from "../helpers/validate_refine.js";
import {
  getConciseHeadingInstruction,
  getDecisionSignalSummaryInstruction,
  getLanguageInstruction,
  getNoProcessNarrationInstruction,
  getNoTitleInstruction,
  getTopicAndTermStyleInstruction,
  type PromptContext,
} from "./shared.js";

export const CATALYST_SENTIMENT_REPORT_SPEC: AnalystReportSpec = {
  analystName: "catalyst_sentiment",
  requiredTopSections: ["一", "二", "三", "四"],
  requireDecisionSignalSummary: true,
  customRulesMarkdown:
    "### 内容覆盖\n" +
    "- 是否将分析扩展到ETF重行业和权重股，而非仅停留在ETF代码层面？\n" +
    "- 是否对每个事件说明传导路径：新闻/情绪/宏观事件 → 持仓/行业影响 → ETF价格含义？\n" +
    "- 是否区分了真实支撑、真实拖累与短期噪声？\n" +
    "- 是否对跨数据源的分歧或一致性进行了分析？\n" +
    "- 末尾是否附Markdown摘要表格？",
};

/**
 * Build the catalyst_sentiment analyst system message from pre-fetched data
 * blocks. Mirrors the Python ``create_social_media_analyst`` deterministic
 * pre-fetch flow (ETF info/holdings + ticker/holdings/global news, no LLM
 * tool loop) — the caller supplies the data via the ``data`` parameter.
 */
export interface CatalystSentimentData {
  etfInfo: string;
  etfHoldings: string;
  tickerNews: string;
  holdingsNews: string;
  globalNews: string;
}

export function buildCatalystSentimentSystemMessage(
  ctx: PromptContext,
  data: CatalystSentimentData,
): string {
  return (
    "你是一名ETF催化剂与情绪分析师。你的工作不限于ETF产品本身：" +
    "必须分析公众讨论、近期新闻和宏观事件如何通过基准暴露、主导行业和高权重持仓影响ETF价格支撑或拖累。\n\n" +
    "以下材料已提供，直接据此分析；不要复述取数、整理或下一步过程。\n\n" +
    `### ETF基本信息\n<etf_info>\n${data.etfInfo}\n</etf_info>\n\n` +
    `### ETF持仓构成\n<etf_holdings>\n${data.etfHoldings}\n</etf_holdings>\n\n` +
    `### ETF相关新闻（过去7天）\n<ticker_news>\n${data.tickerNews}\n</ticker_news>\n\n` +
    `### 重仓股相关新闻（过去7天）\n<holdings_news>\n${data.holdingsNews}\n</holdings_news>\n\n` +
    `### 宏观新闻与市场情绪\n<global_news>\n${data.globalNews}\n</global_news>\n\n` +
    "分析要求：\n\n" +
    "基于上述已提供的数据，完成以下分析：\n\n" +
    "1. 从ETF持仓构成中识别基准、主导行业和最高权重持仓。\n" +
    "2. 分析新闻和情绪数据如何影响这些持仓和行业。\n" +
    "3. 判断每个事件可能支撑、压制还是拖累ETF价格，解释传导路径：新闻/情绪/宏观事件 → 持仓/行业影响 → ETF价格含义。\n" +
    "4. 跨数据源比对：如果某个事件在多个来源中出现，信号更强；如果不同源指向矛盾方向，需要明确指出分歧。\n" +
    "5. 区分事实与观点：新闻标题是事实，社交媒体评论是观点，两者权重不同。\n" +
    "6. 如果某个关键数据源返回为空或数据不足，不在正文堆砌缺失提示；只在相关事件判断和决策信号摘要中降低置信度。\n\n" +
    getNoProcessNarrationInstruction() +
    "\n" +
    getNoTitleInstruction() +
    "\n" +
    getTopicAndTermStyleInstruction() +
    "\n" +
    getConciseHeadingInstruction() +
    "\n" +
    "每个一级章节（一、二、三、四）标题后直接写2-3句结论段，先给事件方向、权重影响和ETF定价含义，然后空行进入子章节。\n\n" +
    "一、情绪主线与权重影响\n" +
    "  （一）产品情绪与讨论强弱\n" +
    "    分析ETF产品层面的情绪与讨论强度。\n" +
    "  （二）行业与重仓股事件主线\n" +
    "    分析主导行业与头部持仓的新闻和情绪。\n" +
    "二、事件传导与定价辨别\n" +
    "  （一）宏观事件传导\n" +
    "    分析相关宏观事件是否放大或对冲ETF论点。\n" +
    "  （二）真实支撑与短期噪声\n" +
    "    区分哪些事件真正支撑ETF价格、哪些拖累、哪些仅是噪声。\n" +
    "三、后续触发与验证要点\n" +
    "  （一）后续监控要点\n" +
    "    说明配置者接下来应监控什么以确认或证伪。\n" +
    "四、结论与跟踪表\n\n" +
    "不得停留在ETF代码标题层面。将分析扩展到ETF重行业和权重股，然后将发现转回ETF定价。" +
    "中文输出时使用中文章节标题，如'真实支撑与短期噪声'；不得使用英文标签如'Genuine Support'。" +
    "末尾附Markdown表格整理报告关键要点。\n\n" +
    "当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用'分别为'连接，不得逐个单独陈述。" +
    "若某项数据在已获取的数据源中不存在，正文直接省略该分析维度；只有当缺口改变核心判断时，才在决策信号摘要的置信度或最大反证条件中体现。" +
    "开篇帽段和每个一级章节标题后的结论段都必须直接陈述结论。" +
    "不得使用'本章''本节''本部分''该部分''这一节'等自指式开头（如'本章旨在梳理''本节核心结论指出''本部分结论表明''该部分说明'）。" +
    getDecisionSignalSummaryInstruction(ctx) +
    getLanguageInstruction(ctx)
  );
}
