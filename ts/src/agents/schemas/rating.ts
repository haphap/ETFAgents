/**
 * Portfolio rating enum + Chinese/English term mapping.
 * Mirrors ``etfagents.agents.schemas.PortfolioRating`` and the relevant
 * subset of ``etfagents.agents.utils.rating``.
 */

import { z } from "zod";

export const PortfolioRatingSchema = z.enum(["Buy", "Overweight", "Hold", "Underweight", "Sell"]);
export type PortfolioRating = z.infer<typeof PortfolioRatingSchema>;

const CHINESE_RATING: Record<PortfolioRating, string> = {
  Buy: "买入",
  Overweight: "增持",
  Hold: "持有",
  Underweight: "减持",
  Sell: "卖出",
};

export function localizeRating(rating: PortfolioRating, language: string): string {
  return isChinese(language) ? CHINESE_RATING[rating] : rating.toUpperCase();
}

const CHINESE_OUTPUT_VALUES = new Set(["chinese", "中文", "zh", "zh-cn", "zh-hans"]);
export function isChinese(language: string | undefined): boolean {
  if (!language) return false;
  return CHINESE_OUTPUT_VALUES.has(language.trim().toLowerCase());
}
