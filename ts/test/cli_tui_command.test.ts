import { Command } from "commander";
import { describe, expect, it } from "vitest";
import { registerTui } from "../src/cli/commands/tui.js";

describe("TS CLI TUI command", () => {
  it("registers the tui command in Commander help", () => {
    const program = new Command();
    program.name("etfagents");
    registerTui(program);

    const help = program.helpInformation();
    expect(help).toContain("tui");
    expect(help).toContain("interactive Ink terminal dashboard");
  });
});
