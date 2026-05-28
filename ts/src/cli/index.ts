#!/usr/bin/env node
/**
 * etfagents-ts CLI entry.
 *
 * Phase 1 commands prove the bridge plumbing end-to-end. They are not the
 * eventual user-facing commands — those land in Phase 3 alongside the Ink TUI.
 */

import { Command } from "commander";
import { registerAnalyzeMini } from "./commands/analyze-mini.js";
import { registerBridgePing } from "./commands/bridge-ping.js";
import { registerToolCall } from "./commands/tool-call.js";
import { registerToolLoop } from "./commands/tool-loop.js";

const program = new Command();

program
  .name("etfagents")
  .description("ETFAgents TypeScript CLI (Phase 1: bridge plumbing)")
  .version("0.0.1");

registerBridgePing(program);
registerToolCall(program);
registerToolLoop(program);
registerAnalyzeMini(program);

await program.parseAsync(process.argv);
