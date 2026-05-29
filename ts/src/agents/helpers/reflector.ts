/**
 * Post-trade reflection node.
 *
 * Port of ``etfagents.graph.reflection.Reflector``.
 *
 * Sub-step 4: generates a concise post-trade reflection for the
 * memory log when raw and alpha returns become available.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { HumanMessage, SystemMessage } from "@langchain/core/messages";
import { extractTextContent } from "./content.js";

export interface ReflectionInput {
  llm: BaseChatModel;
  finalDecision: string;
  rawReturn: number;
  alphaReturn: number;
}

export async function reflectOnFinalDecision(opts: ReflectionInput): Promise<string> {
  const systemPrompt =
    "You are reviewing a completed trading decision. Explain in 3-5 sentences what was right or wrong, " +
    "which evidence mattered most, and one concrete lesson to repeat or avoid next time.";

  const userPrompt =
    `Final decision:\n${opts.finalDecision}\n\n` +
    `Outcome:\n- Raw return: ${(opts.rawReturn * 100).toFixed(1)}%\n` +
    `- Alpha vs benchmark: ${(opts.alphaReturn * 100).toFixed(1)}%`;

  const response = await opts.llm.invoke([
    new SystemMessage(systemPrompt),
    new HumanMessage(userPrompt),
  ]);

  return typeof response.content === "string"
    ? response.content.trim()
    : extractTextContent(response.content);
}
