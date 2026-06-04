export const ENTER_FULLSCREEN = "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l";
export const EXIT_FULLSCREEN = "\x1b[?25h\x1b[?1049l";

export type TtyWriter = {
  isTTY?: boolean;
  write: (chunk: string) => unknown;
};

export type TerminalScreen = {
  enabled: boolean;
  restore: () => void;
};

export function enterFullscreen(stdout: TtyWriter = process.stdout): TerminalScreen {
  if (stdout.isTTY === false) {
    return { enabled: false, restore: () => {} };
  }

  let active = true;
  const restore = () => {
    if (!active) return;
    active = false;
    stdout.write(EXIT_FULLSCREEN);
    process.off("exit", restore);
  };

  stdout.write(ENTER_FULLSCREEN);
  process.once("exit", restore);
  return { enabled: true, restore };
}
