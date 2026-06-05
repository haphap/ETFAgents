import type { LlmOptions } from "../llm/factory.js";
import type { Action, AppDispatch, AppState } from "./model.js";
import {
  ANALYST_IDS,
  buildExecutionSummary,
  dateDaysBefore,
  extractPriceRows,
  NODE_INFO,
  parseTickers,
} from "./model.js";

// ===========================================================================
// vllm model discovery
// ===========================================================================

const VLLM_BASE_URLS = ["http://127.0.0.1:8020/v1", "http://localhost:8000/v1"];

function runtimeBaseUrl(state: AppState): string | undefined {
  const url = state.backendUrl.trim();
  if (!state.provider || !/^https?:\/\//.test(url)) return undefined;
  return url;
}

function positionSizingFromConfig(config: Record<string, unknown>) {
  const budget = Number(config.max_drawdown_budget);
  return Number.isFinite(budget) && budget > 0 ? { maxDrawdownBudget: budget } : {};
}

function conciseBridgeError(error: unknown): string {
  const msg = error instanceof Error ? error.message : String(error);
  if (/Bridge call tools\.call/i.test(msg)) return "基础信息读取失败：数据工具暂不可用";
  if (/ECONNREFUSED|connect/i.test(msg)) return "基础信息读取失败：Bridge 未连接";
  return `基础信息读取失败：${msg.slice(0, 48)}`;
}

function debateCount(update: Record<string, unknown>, key: string): number | null {
  const debate = update[key];
  if (!debate || typeof debate !== "object") return null;
  const count = (debate as Record<string, unknown>).count;
  return typeof count === "number" && Number.isFinite(count) ? count : null;
}

function nodeDisplayLabel(
  node: string,
  baseLabel: string,
  update: Record<string, unknown>,
): string {
  if (node === "bull_researcher" || node === "bear_researcher") {
    const count = debateCount(update, "investment_debate_state");
    const round = count ? Math.max(1, Math.ceil(count / 2)) : 1;
    return `第 ${round} 轮 · ${baseLabel}`;
  }
  if (
    node === "aggressive_debator" ||
    node === "conservative_debator" ||
    node === "neutral_debator"
  ) {
    const count = debateCount(update, "risk_debate_state");
    const round = count ? Math.max(1, Math.ceil(count / 3)) : 1;
    return `第 ${round} 轮 · ${baseLabel}`;
  }
  return baseLabel;
}

function nodeCompletesSection(
  node: string,
  defaultCompletes: boolean,
  update: Record<string, unknown>,
  state: AppState,
): boolean {
  if (node === "bear_researcher") {
    const count = debateCount(update, "investment_debate_state");
    return count !== null && count >= 2 * state.debateRounds;
  }
  if (node === "neutral_debator") {
    const count = debateCount(update, "risk_debate_state");
    return count !== null && count >= 3 * state.riskRounds;
  }
  return defaultCompletes;
}

function mergeGraphUpdate(
  previous: Record<string, unknown>,
  update: Record<string, unknown>,
): Record<string, unknown> {
  const next = { ...previous, ...update };
  const prevSignals = previous.agent_signals;
  const nextSignals = update.agent_signals;
  if (
    prevSignals &&
    typeof prevSignals === "object" &&
    nextSignals &&
    typeof nextSignals === "object"
  ) {
    next.agent_signals = {
      ...(prevSignals as Record<string, unknown>),
      ...(nextSignals as Record<string, unknown>),
    };
  }
  return next;
}

export async function fetchVllmModels(dispatch: AppDispatch) {
  for (const baseUrl of VLLM_BASE_URLS) {
    try {
      const url = `${baseUrl}/models`;
      const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) continue;
      const data = (await res.json()) as { data?: { id: string }[] };
      const models = (data.data ?? []).map((m) => m.id);
      if (models.length > 0) {
        dispatch({ type: "vllmModelsFetched", models, baseUrl });
        return;
      }
    } catch {
      /* try next */
    }
  }
  dispatch({ type: "vllmModelsFailed" });
}

// ===========================================================================
// Analysis runner
// ===========================================================================

export async function runAnalysis(
  state: AppState,
  dispatch: AppDispatch,
  isCurrent: () => boolean,
  signal: AbortSignal,
) {
  const dispatchIfCurrent = (action: Action) => {
    if (isCurrent()) dispatch(action);
  };
  const ensureActive = () => {
    if (signal.aborted) throw new Error("分析已取消。");
    return isCurrent();
  };

  const tickers = state.tickers.length > 0 ? state.tickers : parseTickers(state.ticker);
  dispatchIfCurrent({ type: "appendLog", msg: `开始分析 ${tickers.join(", ")}` });
  try {
    const [{ HumanMessage }] = await Promise.all([import("@langchain/core/messages")]);
    const { BridgeApi, BridgeClient, pickBridgeTools } = await import("../bridge/index.js");
    const { buildFullGraph } = await import("../graph/full_graph.js");
    const { buildEffectiveMemoryConfig } = await import("../agents/nodes/memory_writer.js");
    const { ANALYST_TOOLS, fetchMemoryContext } = await import("../cli/commands/shared_tools.js");
    const { createLlmFromConfig } = await import("../llm/factory.js");
    const { saveAnalysisReportArtifact } = await import("./services/artifacts.js");

    dispatchIfCurrent({ type: "appendLog", msg: "── 连接 Bridge…" });
    const client = new BridgeClient();
    await client.start();
    try {
      if (!ensureActive()) return;
      const api = new BridgeApi(client);
      const config = await api.configGet();
      if (!ensureActive()) return;
      const llmOpts: LlmOptions = { tier: "deep" };
      if (state.provider) llmOpts.provider = state.provider;
      if (state.model) llmOpts.model = state.model;
      const baseUrl = runtimeBaseUrl(state);
      if (baseUrl) llmOpts.baseUrl = baseUrl;
      dispatchIfCurrent({
        type: "appendLog",
        msg: `── LLM: ${llmOpts.provider ?? config.llm_provider}/${llmOpts.model ?? "default"}`,
      });

      const llmHandle = createLlmFromConfig(config, llmOpts);
      // Quick-tier LLM for analysts/researchers/risk debators. Reuse an explicit
      // model override for both tiers (single-model setups like vLLM); otherwise
      // the quick tier uses the config's quick_think_llm.
      const quickOpts: LlmOptions = { tier: "quick" };
      if (state.provider) quickOpts.provider = state.provider;
      if (state.model) quickOpts.model = state.model;
      if (baseUrl) quickOpts.baseUrl = baseUrl;
      const quickHandle = createLlmFromConfig(config, quickOpts);
      dispatchIfCurrent({ type: "setBackend", url: llmHandle.baseUrl ?? "OpenAI SDK default" });

      // Effective config for memory write-back: overlay the TUI's provider/
      // model/round overrides so the stored entry's config hash describes the
      // run that actually executed (not the unmodified bridge config).
      const effectiveConfig = buildEffectiveMemoryConfig(config as Record<string, unknown>, {
        provider: state.provider,
        model: state.model,
        ...(llmHandle.baseUrl ? { baseUrl: llmHandle.baseUrl } : {}),
        debateRounds: state.debateRounds,
        riskRounds: state.riskRounds,
      });

      // Resolve each analyst's tool set (deduped) for the full pipeline.
      const uniqueToolNames = Array.from(
        new Set<string>([
          ...ANALYST_TOOLS.marketFlow,
          ...ANALYST_TOOLS.macroRegime,
          ...ANALYST_TOOLS.mesoCommodity,
          ...ANALYST_TOOLS.catalystSentiment,
          ...ANALYST_TOOLS.holdingsIndustry,
          ...ANALYST_TOOLS.topHoldings,
        ]),
      );
      const allTools = await pickBridgeTools(api, uniqueToolNames);
      if (!ensureActive()) return;
      const byName = new Map(allTools.map((t) => [t.name, t] as const));
      const pick = (names: ReadonlyArray<string>) =>
        names.map((n) => byName.get(n)).filter((t): t is NonNullable<typeof t> => t !== undefined);
      dispatchIfCurrent({ type: "appendLog", msg: `── 已加载 ${allTools.length} 个数据工具` });
      dispatchIfCurrent({ type: "setStats", stats: { tool_calls: allTools.length } });

      const charLimit = Number(config.report_context_char_limit);
      const promptContext = {
        language: String(config.output_language ?? "Chinese"),
        ...(Number.isFinite(charLimit) && charLimit > 0
          ? { reportContextCharLimit: charLimit }
          : {}),
      };

      const selectedAnalystList = ANALYST_IDS.filter((id) => state.selectedAnalysts[id] !== false);

      const graph = buildFullGraph({
        llm: llmHandle.llm,
        quickLlm: quickHandle.llm,
        tools: {
          marketFlow: pick(ANALYST_TOOLS.marketFlow),
          macroRegime: pick(ANALYST_TOOLS.macroRegime),
          mesoCommodity: pick(ANALYST_TOOLS.mesoCommodity),
          catalystSentiment: pick(ANALYST_TOOLS.catalystSentiment),
          holdingsIndustry: pick(ANALYST_TOOLS.holdingsIndustry),
          topHoldings: pick(ANALYST_TOOLS.topHoldings),
          bullBear: [],
          riskDebate: [],
        },
        promptContext,
        positionSizing: positionSizingFromConfig(config as Record<string, unknown>),
        maxDebateRounds: state.debateRounds,
        maxRiskRounds: state.riskRounds,
        selectedAnalysts: selectedAnalystList,
        // Forward the effective runtime config (with TUI provider/model/round
        // overrides) so memory write-back's config hash matches the actual run.
        memoryConfig: effectiveConfig,
        persistMemory: async (payload) => {
          const res = await api.memoryAppendAnalysis(
            payload as {
              state: Record<string, unknown>;
              selected_analysts?: readonly string[] | null;
              config?: Record<string, unknown>;
            },
          );
          return res.entry;
        },
      });

      let lastDecision = "";
      for (const [index, ticker] of tickers.entries()) {
        if (!ensureActive()) return;
        dispatchIfCurrent({ type: "queueTickerStarted", index });
        dispatchIfCurrent({ type: "appendLog", msg: `开始分析 ${ticker}` });

        // Load the ETF basic-info card via the same bridge connection.
        // NOTE: get_etf_price_data's parameter is `symbol`, not `ticker`.
        try {
          const detailResult = await api.toolsCall("get_etf_price_data", {
            symbol: ticker,
            start_date: dateDaysBefore(state.date, 365),
            end_date: state.date,
          });
          const rows = extractPriceRows(detailResult.text);
          const last = rows[rows.length - 1];
          const prev = rows[rows.length - 2];
          if (last) {
            const close = last.close;
            const pctChg = last.pctChg;
            const high = last.high;
            const low = last.low;
            const volume = last.volume;
            const prevVolume = prev?.volume;
            const volumeChangePct =
              volume !== undefined && prevVolume !== undefined && prevVolume !== 0
                ? ((volume - prevVolume) / prevVolume) * 100
                : undefined;
            dispatchIfCurrent({
              type: "etfDetailLoaded",
              ...(last.name ? { name: last.name } : { name: ticker }),
              ...(close !== undefined ? { close } : {}),
              ...(pctChg !== undefined ? { pctChg } : {}),
              ...(high !== undefined ? { high } : {}),
              ...(low !== undefined ? { low } : {}),
              ...(volume !== undefined ? { volume } : {}),
              ...(volumeChangePct !== undefined ? { volumeChangePct } : {}),
              history: rows.map((row) => row.close).filter((v): v is number => v !== undefined),
              priceRows: rows.slice(-60),
            });
          } else {
            dispatchIfCurrent({ type: "etfDetailLoaded", name: ticker });
          }
        } catch (e) {
          dispatchIfCurrent({ type: "etfDetailError", error: conciseBridgeError(e) });
        }
        if (!ensureActive()) return;

        dispatchIfCurrent({
          type: "appendLog",
          msg: "── 启动完整流水线：分析师 → 辩论 → 交易 → 风控 → 决策",
        });

        // Stream the graph so the dashboard updates per node instead of waiting
        // for the whole pipeline. Each chunk is { nodeName: stateUpdate }.
        const memCtx = await fetchMemoryContext(
          api,
          ticker,
          state.date,
          effectiveConfig,
          selectedAnalystList,
        );
        const stream = await graph.stream(
          {
            messages: [new HumanMessage(ticker)],
            asset_of_interest: ticker,
            trade_date: state.date,
            ...memCtx,
          },
          { recursionLimit: 100, signal } as { recursionLimit: number; signal: AbortSignal },
        );

        let finalState: Record<string, unknown> = {};
        try {
          for await (const chunk of stream) {
            if (!ensureActive()) return;
            for (const [node, update] of Object.entries(chunk as Record<string, unknown>)) {
              if (!update || typeof update !== "object") continue;
              finalState = mergeGraphUpdate(finalState, update as Record<string, unknown>);
              const info = NODE_INFO[node];
              if (!info) continue; // tool-loop node (e.g. *_tools) — no UI section
              dispatchIfCurrent({ type: "sectionStarted", sectionId: info.section });
              const body = (update as Record<string, unknown>)[info.key];
              const hasBody = typeof body === "string" && body.trim().length > 0;
              // Analyst nodes re-enter via their ToolNode while fetching data; those
              // intermediate passes only carry { messages } and no report body, so
              // skip them — we only advance the UI once real output is produced.
              if (!hasBody) continue;
              dispatchIfCurrent({
                type: "sectionReport",
                sectionId: info.section,
                nodeLabel:
                  tickers.length > 1
                    ? `${ticker} · ${nodeDisplayLabel(node, info.label, update as Record<string, unknown>)}`
                    : nodeDisplayLabel(node, info.label, update as Record<string, unknown>),
                body: body as string,
              });
              dispatchIfCurrent({ type: "setStats", stats: { llm_calls: 1 } });
              if (
                nodeCompletesSection(node, info.completes, update as Record<string, unknown>, state)
              ) {
                dispatchIfCurrent({ type: "sectionDone", sectionId: info.section });
              }
              dispatchIfCurrent({ type: "appendLog", msg: `✓ ${ticker} · ${info.label}` });
              // Surface the trader rating as soon as the trader node lands.
              if (node === "trader") {
                const traderSignal = (update as Record<string, unknown>).trader_backtest_signal as
                  | Record<string, unknown>
                  | undefined;
                const rating = traderSignal?.rating;
                if (typeof rating === "string" && rating) {
                  dispatchIfCurrent({ type: "setRating", rating });
                }
              }
            }
          }
          const summary = buildExecutionSummary(finalState);
          if (summary) dispatchIfCurrent({ type: "setExecutionSummary", summary });
          const decision =
            (finalState.final_allocation_decision as string) ||
            (finalState.trader_allocation_plan as string) ||
            "(无最终决策)";
          try {
            const reportPath = await saveAnalysisReportArtifact({
              ticker,
              tradeDate: state.date,
              state: finalState,
              config: config as Record<string, unknown>,
            });
            dispatchIfCurrent({ type: "appendLog", msg: `✓ 研报已保存: ${reportPath}` });
          } catch (e) {
            dispatchIfCurrent({
              type: "appendLog",
              msg: `✗ 研报保存失败: ${(e as Error).message.slice(0, 80)}`,
            });
          }
          lastDecision = decision;
          dispatchIfCurrent({ type: "queueTickerDone", index });
        } catch (e) {
          const msg = (e as Error).message;
          dispatchIfCurrent({ type: "queueTickerFailed", index, msg });
          throw e;
        }
      }

      dispatchIfCurrent({ type: "appendLog", msg: "✓ 流水线完成" });
      dispatchIfCurrent({ type: "analysisDone", result: lastDecision || "(无最终决策)" });
    } finally {
      await client.close();
    }
  } catch (err) {
    const error = err as Error;
    const msg = error.message;
    if (signal.aborted || msg === "分析已取消。") {
      dispatchIfCurrent({ type: "appendLog", msg: "✗ 分析已取消" });
      dispatchIfCurrent({ type: "queueCancelled" });
      return;
    }
    dispatchIfCurrent({ type: "appendLog", msg: `✗ 错误: ${msg.slice(0, 120)}` });
    // P6: preserve a structured detail object for the error overlay.
    dispatchIfCurrent({
      type: "setErrorDetail",
      detail: {
        message: msg,
        ...(state.tickers[0] ? { ticker: state.tickers[0] } : {}),
        ...(error.stack ? { stack: error.stack } : {}),
        timestamp: new Date().toISOString(),
      },
    });
    dispatchIfCurrent({
      type: "analysisError",
      msg:
        msg.includes("ECONNREFUSED") || msg.includes("connect")
          ? "Bridge 未运行。请先启动 Python bridge。"
          : msg,
    });
  }
}
