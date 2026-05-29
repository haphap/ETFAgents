/**
 * `paper <action>` — paper trading account management.
 *
 * Phase 4.2: wraps bridge RPCs paper.register/login/logout/account/positions/trades/buy/sell.
 */

import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, RpcError } from "../../bridge/index.js";

export function registerPaper(program: Command): void {
  const paperCmd = program.command("paper").description("Paper trading account management");

  paperCmd
    .command("register <username>")
    .description("Register a paper trading account")
    .action(async (username: string) => {
      await withBridge(async (api) => {
        const result = await api.paperRegister(username);
        console.log(pc.green(`Registered: ${JSON.stringify(result)}`));
      });
    });

  paperCmd
    .command("login <username>")
    .description("Login to paper trading account")
    .action(async (username: string) => {
      await withBridge(async (api) => {
        const result = await api.paperLogin(username);
        console.log(pc.green(`Logged in: ${JSON.stringify(result)}`));
      });
    });

  paperCmd
    .command("logout")
    .description("Logout current paper trading session")
    .action(async () => {
      await withBridge(async (api) => {
        const result = await api.paperLogout();
        console.log(result);
      });
    });

  paperCmd
    .command("user")
    .description("Show current paper trading user")
    .action(async () => {
      await withBridge(async (api) => {
        const result = await api.paperCurrentUser();
        console.log(JSON.stringify(result, null, 2));
      });
    });

  paperCmd
    .command("account")
    .description("Show paper trading account summary")
    .action(async () => {
      await withBridge(async (api) => {
        const result = await api.paperGetAccount();
        console.log(JSON.stringify(result, null, 2));
      });
    });

  paperCmd
    .command("positions")
    .description("List current paper trading positions")
    .action(async () => {
      await withBridge(async (api) => {
        const result = await api.paperGetPositions();
        console.log(JSON.stringify(result, null, 2));
      });
    });

  paperCmd
    .command("trades")
    .description("List paper trading trade history")
    .action(async () => {
      await withBridge(async (api) => {
        const result = await api.paperGetTrades();
        console.log(JSON.stringify(result, null, 2));
      });
    });

  paperCmd
    .command("buy <ticker> <quantity>")
    .description("Place a paper buy order")
    .option("--price <n>", "Limit price")
    .action(async (ticker: string, quantity: string, opts: { price?: string }) => {
      await withBridge(async (api) => {
        const result = await api.paperBuy(
          ticker,
          Number(quantity),
          opts.price ? Number(opts.price) : undefined,
        );
        console.log(pc.green(JSON.stringify(result)));
      });
    });

  paperCmd
    .command("sell <ticker> <quantity>")
    .description("Place a paper sell order")
    .option("--price <n>", "Limit price")
    .action(async (ticker: string, quantity: string, opts: { price?: string }) => {
      await withBridge(async (api) => {
        const result = await api.paperSell(
          ticker,
          Number(quantity),
          opts.price ? Number(opts.price) : undefined,
        );
        console.log(pc.green(JSON.stringify(result)));
      });
    });
}

async function withBridge(fn: (api: BridgeApi) => Promise<void>): Promise<void> {
  const client = new BridgeClient();
  try {
    await client.start();
    await fn(new BridgeApi(client));
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
}
