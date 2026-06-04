/**
 * TraderProposal schema — Zod port of ``etfagents.agents.schemas.TraderProposal``.
 *
 * The structured-output target for the trader node. The ``rating`` field maps
 * to ``PortfolioRating``; the trigger/risk fields are arrays of the shared
 * ``Trigger`` / ``RiskRule`` schemas.
 */

import { z } from "zod";
import { PortfolioRatingSchema } from "./rating.js";
import { RiskRuleSchema, TriggerSchema } from "./trigger.js";

const ETF_ONLY_ALLOCATION_SCOPE =
  "The execution target is the ETF itself, not individual constituent stocks. " +
  "Use holdings and constituent weights only as attribution evidence; do not recommend buying, selling, trimming, clearing, or retaining named constituents.";

export const TraderProposalSchema = z.object({
  thesis: z.string().describe("Concise ETF allocation thesis explaining the proposed action."),
  execution_plan: z
    .string()
    .describe(
      "Concrete ETF allocation plan with support or resistance references, exact price or moving-average levels, " +
        "volume or fund-flow thresholds, catalyst triggers, ETF share or premium-discount checks, and explicit add, reduce, rotate, or exit conditions. " +
        "Do not say 'wait for confirmation' without numeric thresholds. " +
        "Write the numeric level inline instead of saying 'the key level in the market report'. " +
        ETF_ONLY_ALLOCATION_SCOPE,
    ),
  risk_management: z
    .string()
    .describe(
      "Risk controls, rebalance or invalidation signals, monitoring thresholds, and the actions to take when those thresholds are breached.",
    ),
  rating: PortfolioRatingSchema.describe("Trader recommendation for ETF exposure."),
  key_drivers: z
    .array(z.string())
    .default([])
    .describe(
      "Three to five concise evidence points that directly justify the ETF allocation action.",
    ),
  confidence: z
    .number()
    .min(0)
    .max(1)
    .nullable()
    .optional()
    .describe("Trader confidence in the allocation action as a 0-1 decimal."),
  target_weight_pct: z
    .number()
    .nullable()
    .optional()
    .describe(
      "Structured target portfolio weight in percent for this ETF, from 0 to 100. " +
        "Use when the execution plan implies a single target sizing.",
    ),
  target_weight_band: z
    .tuple([z.number(), z.number()])
    .nullable()
    .optional()
    .describe(
      "Structured target weight band in percent as (low, high), from 0 to 100. " +
        "Use when the plan specifies a sizing range rather than a single weight.",
    ),
  execution_timing: z
    .enum(["same_close", "next_open", "next_close"])
    .nullable()
    .optional()
    .describe(
      "Structured execution timing for the backtest signal. Use same_close, next_open, or next_close.",
    ),
  add_triggers: z
    .array(TriggerSchema)
    .default([])
    .describe(
      "Structured add triggers that increase the ETF target weight when their conditions are met.",
    ),
  reduce_triggers: z
    .array(TriggerSchema)
    .default([])
    .describe(
      "Structured reduce triggers that trim the ETF target weight when their conditions are met.",
    ),
  exit_triggers: z
    .array(TriggerSchema)
    .default([])
    .describe(
      "Structured exit triggers that close or nearly close the ETF position when their conditions are met.",
    ),
  rebalance_triggers: z
    .array(TriggerSchema)
    .default([])
    .describe(
      "Structured rebalance triggers that restore or rotate the ETF position when their conditions are met.",
    ),
  risk_controls: z
    .array(RiskRuleSchema)
    .default([])
    .describe(
      "Structured risk rules that cap, floor, or exit the ETF position when risk conditions are breached.",
    ),
});

export type TraderProposal = z.infer<typeof TraderProposalSchema>;
