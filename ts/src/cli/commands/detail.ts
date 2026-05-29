/**
 * `detail <ticker>` — print ETF info, NAV, holdings from bridge.
 *
 * Phase 3.4: quick lookup command for tushare data.
 */

import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, RpcError } from "../../bridge/index.js";

export function registerDetail(program: Command): void {
  program
    .command("detail <ticker>")
    .description("Show ETF info, NAV, and holdings from the bridge")
    .option("--date <yyyy-mm-dd>", "Trade date")
    .action(async (ticker: string, opts: { date?: string }) => {
      const tradeDate = opts.date ?? new Date().toISOString().slice(0, 10);
      const client = new BridgeClient();
      const api = new BridgeApi(client);
      try {
        await client.start();

        const info = String(await api.toolsCall("get_etf_info", { ticker, curr_date: tradeDate }));
        console.log(pc.cyan("=== ETF Info ==="));
        console.log(info);

        const nav = String(await api.toolsCall("get_etf_nav", { ticker, curr_date: tradeDate }));
        console.log(pc.cyan("\n=== NAV ==="));
        console.log(nav.slice(0, 2000));

        const holdings = String(
          await api.toolsCall("get_etf_holdings", { ticker, curr_date: tradeDate }),
        );
        console.log(pc.cyan("\n=== Holdings ==="));
        console.log(holdings.slice(0, 3000));
      } catch (err) {
        if (err instanceof RpcError) {
          console.error(pc.red(`bridge error [${err.code}]: ${err.message}`));
        } else {
          console.error(pc.red(`error: ${(err as Error).message}`));
        }
        process.exitCode = 1;
      } finally {
        await client.close();
      }
    });
}
