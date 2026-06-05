#!/usr/bin/env node
/**
 * etfagents-ts CLI entry.
 *
 * Phase 1 commands prove the bridge plumbing end-to-end. They are not the
 * eventual user-facing commands — those land in Phase 3 alongside the Ink TUI.
 */

import { Command } from "commander";
import { registerAnalyze } from "./commands/analyze.js";
import { registerAnalyzeMini } from "./commands/analyze-mini.js";
import { registerAnalyzeCandidatePool } from "./commands/analyze-pool.js";
import { registerBacktest } from "./commands/backtest.js";
import { registerBridgePing } from "./commands/bridge-ping.js";
import { registerCache } from "./commands/cache.js";
import { registerDetail } from "./commands/detail.js";
import { registerPaper } from "./commands/paper.js";
import { registerToolCall } from "./commands/tool-call.js";
import { registerToolLoop } from "./commands/tool-loop.js";
import { registerTui } from "./commands/tui.js";

const program = new Command();

program.name("etfagents").description("ETFAgents TypeScript CLI").version("0.5.0");

registerBridgePing(program);
registerToolCall(program);
registerToolLoop(program);
registerAnalyzeMini(program);
registerAnalyze(program);
registerAnalyzeCandidatePool(program);
registerBacktest(program);
registerDetail(program);
registerPaper(program);
registerCache(program);
registerTui(program);

await program.parseAsync(process.argv);
