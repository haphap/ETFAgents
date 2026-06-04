import type { Command } from "commander";

export function registerTui(program: Command): void {
  program
    .command("tui")
    .description("Launch the interactive Ink terminal dashboard")
    .action(async () => {
      const { runTui } = await import("../../tui/index.js");
      runTui();
    });
}
