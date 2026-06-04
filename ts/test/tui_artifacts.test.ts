import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Action } from "../src/tui/index.js";
import { loadLibrary } from "../src/tui/services/artifacts.js";

describe("TUI report artifacts", () => {
  it("derives and persists structured report-card summaries for legacy reports", async () => {
    const root = await mkdtemp(join(tmpdir(), "etfagents-report-summary-"));
    const previous = process.env.ETFAGENTS_RESULTS_DIR;
    process.env.ETFAGENTS_RESULTS_DIR = root;
    try {
      const reportDir = join(root, "510300.SH", "2026-06-04");
      await mkdir(reportDir, { recursive: true });
      await writeFile(
        join(reportDir, "complete_report.md"),
        [
          "# ETF配置分析报告: 510300.SH",
          "Trade Date: 2026-06-03",
          "## V. 投资组合经理决策",
          "研究结论: **增持**，资金与持仓结构改善。",
          "## 持仓建议",
          "目标仓位 20%-30%，回踩支撑后加仓。",
          "## 再平衡与风险控制",
          "跌破 3.72 元先减仓，放量跌破止损。",
        ].join("\n"),
        "utf-8",
      );
      await writeFile(
        join(reportDir, "summary.json"),
        JSON.stringify(
          {
            schemaVersion: 0,
            ticker: "510300.SH",
            reportDate: "2026-06-04",
            rating: "卖出",
            source: "markdown-derived",
          },
          null,
          2,
        ),
        "utf-8",
      );

      const actions: Action[] = [];
      await loadLibrary((action) => actions.push(action));

      const loaded = actions.find((action) => action.type === "libraryLoaded");
      expect(loaded).toBeTruthy();
      if (loaded?.type !== "libraryLoaded") throw new Error("libraryLoaded not dispatched");
      expect(loaded.reports[0]).toMatchObject({
        ticker: "510300.SH",
        date: "2026-06-04",
        analysisDate: "2026-06-03",
        rating: "增持",
        targetWeight: "20%-30%",
        priceRange: "止损 3.720",
      });

      const summary = JSON.parse(await readFile(join(reportDir, "summary.json"), "utf-8"));
      expect(summary).toMatchObject({
        schemaVersion: 1,
        ticker: "510300.SH",
        reportDate: "2026-06-04",
        rating: "增持",
        source: "markdown-derived",
      });
    } finally {
      if (previous === undefined) delete process.env.ETFAGENTS_RESULTS_DIR;
      else process.env.ETFAGENTS_RESULTS_DIR = previous;
      await rm(root, { recursive: true, force: true });
    }
  });
});
