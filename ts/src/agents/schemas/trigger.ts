/**
 * Trigger / RiskRule schemas — shared between trader and managers.
 * Mirrors ``etfagents.agents.schemas.Trigger`` and ``RiskRule``.
 */

import { z } from "zod";

const Threshold = z.union([z.number(), z.tuple([z.number(), z.number()])]);

export const TriggerSchema = z.object({
  metric: z
    .string()
    .describe(
      "Metric to evaluate, e.g. close, open, high, low, volume, sma_20, close_50_sma, volume_ratio_20d, pnl_pct, or weight_pct.",
    ),
  op: z
    .enum(["<", "<=", ">", ">=", "==", "in_range"])
    .describe("Comparison operator for the trigger."),
  threshold: Threshold.describe("Threshold value or inclusive range for the trigger."),
  action: z
    .enum(["add", "reduce", "exit", "rebalance", "hold"])
    .describe("Action to take when the trigger fires."),
  delta_pct: z
    .number()
    .nullable()
    .optional()
    .describe(
      "Optional percentage-point change in target portfolio weight when the trigger fires.",
    ),
  target_weight_pct: z
    .number()
    .nullable()
    .optional()
    .describe(
      "Optional target portfolio weight in percent to set directly when the trigger fires.",
    ),
  note: z.string().default("").describe("Short explanation of the trigger and why it matters."),
});

export const RiskRuleSchema = z.object({
  metric: z
    .string()
    .describe(
      "Risk metric to evaluate, e.g. close, low, pnl_pct, weight_pct, or volume_ratio_20d.",
    ),
  op: z
    .enum(["<", "<=", ">", ">=", "==", "in_range"])
    .describe("Comparison operator for the risk rule."),
  threshold: Threshold.describe("Threshold value or inclusive range for the risk rule."),
  action: z
    .enum(["cap", "floor", "exit", "hold"])
    .describe("Risk action to take when the rule fires."),
  max_weight_pct: z
    .number()
    .nullable()
    .optional()
    .describe("Optional maximum portfolio weight in percent after the rule fires."),
  min_weight_pct: z
    .number()
    .nullable()
    .optional()
    .describe("Optional minimum portfolio weight in percent after the rule fires."),
  note: z.string().default("").describe("Short explanation of the risk rule and why it matters."),
});

export type Trigger = z.infer<typeof TriggerSchema>;
export type RiskRule = z.infer<typeof RiskRuleSchema>;
