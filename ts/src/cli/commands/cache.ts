/**
 * `cache <action>` — manage bridge cache.
 *
 * Phase 3.5: wraps bridge RPCs cache.stats / cache.cleanup / cache.clear.
 */

import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, RpcError } from "../../bridge/index.js";

export function registerCache(program: Command): void {
  const cacheCmd = program.command("cache").description("Manage bridge cache");

  cacheCmd
    .command("stats")
    .description("Show cache statistics")
    .action(async () => {
      const client = new BridgeClient();
      const api = new BridgeApi(client);
      try {
        await client.start();
        const stats = await api.cacheStats();
        console.log(JSON.stringify(stats, null, 2));
      } catch (err) {
        handleError(err);
      } finally {
        await client.close();
      }
    });

  cacheCmd
    .command("cleanup")
    .description("Remove stale cache entries")
    .option("--days <n>", "Remove entries older than N days", "30")
    .action(async (opts: { days: string }) => {
      const client = new BridgeClient();
      const api = new BridgeApi(client);
      try {
        await client.start();
        const result = await api.cacheCleanup(Number(opts.days));
        console.log(result);
      } catch (err) {
        handleError(err);
      } finally {
        await client.close();
      }
    });

  cacheCmd
    .command("clear")
    .description("Clear all cached data")
    .option("--type <type>", "Cache type to clear", "all")
    .option("--yes", "Skip confirmation")
    .action(async (opts: { type: string; yes?: boolean }) => {
      if (!opts.yes) {
        console.log(
          pc.yellow(`This will clear all '${opts.type}' cache entries. Use --yes to confirm.`),
        );
        return;
      }
      const client = new BridgeClient();
      const api = new BridgeApi(client);
      try {
        await client.start();
        const result = await api.cacheClear(opts.type as "all");
        console.log(result);
      } catch (err) {
        handleError(err);
      } finally {
        await client.close();
      }
    });
}

function handleError(err: unknown): void {
  if (err instanceof RpcError) {
    console.error(pc.red(`bridge error [${err.code}]: ${err.message}`));
  } else {
    console.error(pc.red(`error: ${(err as Error).message}`));
  }
  process.exitCode = 1;
}
