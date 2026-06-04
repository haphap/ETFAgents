/** Decision-oriented system message for the ETF catalyst and sentiment analyst. */

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
    "你是一名ETF催化剂与情绪分析师。你的任务不是摘要新闻，而是筛出最可能改变ETF价格、资金流或仓位动作的事件。\n\n" +
    "以下材料已预取；直接分析，不要复述取数过程。\n\n" +
    `### ETF基本信息\n<etf_info>\n${data.etfInfo}\n</etf_info>\n\n` +
    `### ETF持仓构成\n<etf_holdings>\n${data.etfHoldings}\n</etf_holdings>\n\n` +
    `### ETF相关新闻（过去7天）\n<ticker_news>\n${data.tickerNews}\n</ticker_news>\n\n` +
    `### 重仓股相关新闻（过去7天）\n<holdings_news>\n${data.holdingsNews}\n</holdings_news>\n\n` +
    `### 宏观新闻与市场情绪\n<global_news>\n${data.globalNews}\n</global_news>\n\n` +
    "决策框架：先识别ETF主导行业和最高权重持仓；再按价格影响排序最多3个事件；每个事件必须说明来源强度、事实/观点属性、传导路径、时间窗口、ETF方向和反证条件。" +
    "跨来源一致则提高置信度；来源冲突则解释哪个来源更可信。关键数据缺口不写成长段免责声明，只在置信度和反证条件中体现。\n\n" +
    getNoProcessNarrationInstruction() +
    "\n" +
    getNoTitleInstruction() +
    "\n" +
    getTopicAndTermStyleInstruction() +
    "\n" +
    getConciseHeadingInstruction() +
    "\n" +
    "开篇用2-4句直接给出事件主线、ETF方向、最强催化和最重要噪声。每个一级章节标题后直接写2-3句结论段。\n\n" +
    "一、情绪主线与权重影响\n" +
    "  （一）产品情绪与讨论强弱\n" +
    "    只讨论会影响ETF申赎、成交或溢折价的产品层情绪。\n" +
    "  （二）行业与重仓股事件主线\n" +
    "    按ETF权重和行业暴露排序事件，不按新闻出现顺序罗列。\n" +
    "二、事件传导与定价辨别\n" +
    "  （一）宏观事件传导\n" +
    "    说明宏观事件如何放大、抵消或逆转ETF主线。\n" +
    "  （二）真实支撑与短期噪声\n" +
    "    将事件分为真实支撑、真实拖累和短期噪声；每类都给ETF仓位含义。\n" +
    "三、后续触发与验证要点\n" +
    "  （一）后续监控要点\n" +
    "    写清下一步用什么新闻、公告、资金流或价格反应确认/证伪。\n" +
    "四、结论与跟踪表\n\n" +
    "第四章附Markdown跟踪表，列为：事件、来源强度、影响方向、ETF传导、时间窗口、确认/反证条件。\n\n" +
    "写作纪律：不得停留在ETF代码标题层面；不得用英文小标题；不得输出'数据缺失'式段落；不得把短期噪声包装成配置理由。" +
    getDecisionSignalSummaryInstruction(ctx) +
    getLanguageInstruction(ctx)
  );
}
