import { describe, expect, it } from "vitest";
import type { TtyWriter } from "../src/tui/terminal.js";
import { ENTER_FULLSCREEN, EXIT_FULLSCREEN, enterFullscreen } from "../src/tui/terminal.js";

class FakeStdout {
  isTTY?: boolean;
  chunks: string[] = [];

  constructor(isTTY?: boolean) {
    if (isTTY !== undefined) this.isTTY = isTTY;
  }

  write(chunk: string | Uint8Array): boolean {
    this.chunks.push(String(chunk));
    return true;
  }

  get output(): string {
    return this.chunks.join("");
  }
}

describe("TUI terminal fullscreen", () => {
  it("enters alternate screen and restores it once", () => {
    const stdout = new FakeStdout(true);
    const screen = enterFullscreen(stdout satisfies TtyWriter);

    expect(screen.enabled).toBe(true);
    expect(stdout.output).toBe(ENTER_FULLSCREEN);

    screen.restore();
    screen.restore();

    expect(stdout.output).toBe(`${ENTER_FULLSCREEN}${EXIT_FULLSCREEN}`);
  });

  it("does not emit fullscreen sequences for non-TTY output", () => {
    const stdout = new FakeStdout(false);
    const screen = enterFullscreen(stdout satisfies TtyWriter);

    expect(screen.enabled).toBe(false);
    screen.restore();
    expect(stdout.output).toBe("");
  });
});
