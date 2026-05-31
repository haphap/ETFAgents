/**
 * catalyst_sentiment analyst node.
 *
 * Tool-loop analyst (matching Python's create_social_media_analyst): the model
 * gathers ETF info, holdings, and news via its bound tools, then writes the
 * report. Built through the shared analyst factory like the other analysts.
 */

import {
  buildCatalystSentimentSystemMessage,
  CATALYST_SENTIMENT_REPORT_SPEC,
} from "../prompts/catalyst_sentiment.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createCatalystSentimentNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "catalyst_sentiment",
      stateKey: "catalyst_sentiment_report",
      buildSystemBody: buildCatalystSentimentSystemMessage,
      tools: opts.tools,
      reportSpec: CATALYST_SENTIMENT_REPORT_SPEC,
      memoryRole: { role: "catalyst_sentiment", aliases: ["social"] },
    },
    assembleSystemFrame,
  );
}
