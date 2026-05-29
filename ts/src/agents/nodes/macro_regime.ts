/**
 * macro_regime analyst node.
 * Sub-step 3 — created via the shared analyst factory.
 */

import {
  buildMacroRegimeSystemMessage,
  MACRO_REGIME_REPORT_SPEC,
} from "../prompts/macro_regime.js";
import { createAnalystNode } from "./analyst_factory.js";
import type { AnalystNodeOptions } from "./market_flow.js";
import { assembleSystemFrame } from "./market_flow.js";

export function createMacroRegimeNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "macro_regime",
      stateKey: "macro_regime_report",
      buildSystemBody: buildMacroRegimeSystemMessage,
      tools: opts.tools,
      reportSpec: MACRO_REGIME_REPORT_SPEC,
      memoryRole: { role: "macro_regime" },
    },
    assembleSystemFrame,
  );
}
