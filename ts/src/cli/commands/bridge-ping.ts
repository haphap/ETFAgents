import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, resolvePython } from "../../bridge/index.js";

export function registerBridgePing(program: Command): void {
  program
    .command("bridge-ping")
    .description("Verify the Python sidecar starts and answers tools.list")
    .action(async () => {
      const python = resolvePython();
      console.log(pc.dim(`python:    ${python.python}`));
      console.log(pc.dim(`source:    ${python.source}`));
      console.log(pc.dim(`repo root: ${python.repoRoot}`));

      const client = new BridgeClient({ python });
      const api = new BridgeApi(client);
      try {
        await client.start();
        const tools = await api.toolsList();
        const config = await api.configGet();
        console.log(
          pc.green(
            `\nbridge ok: ${tools.length} tools, llm_provider=${String(config.llm_provider)}, deep=${String(config.deep_think_llm)}`,
          ),
        );
        console.log(
          pc.dim(
            `first 5 tools: ${tools
              .slice(0, 5)
              .map((t) => t.name)
              .join(", ")}`,
          ),
        );
      } catch (err) {
        console.error(pc.red(`\nbridge failed: ${(err as Error).message}`));
        const tail = client.stderrTail.trim();
        if (tail) {
          console.error(pc.dim("\n--- bridge stderr (tail) ---"));
          console.error(pc.dim(tail.slice(-2000)));
        }
        process.exitCode = 1;
      } finally {
        await client.close();
      }
    });
}
