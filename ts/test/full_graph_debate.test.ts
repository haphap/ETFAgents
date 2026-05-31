import { AIMessage } from "@langchain/core/messages";
import { describe, expect, it } from "vitest";
import type { SpineStateType, SpineStateUpdate } from "../src/agents/state.js";
import { withDebateTurn } from "../src/graph/full_graph.js";
import { routeDebate, routeRiskDebate } from "../src/graph/routing.js";

/**
 * Simulate the conditional-edge loop the graph runs: start at the first
 * speaker, and after each turn increment count + set latestSpeaker (exactly
 * what withDebateTurn does), then ask the router for the next node.
 */
function runResearchDebate(maxRounds: number): string[] {
  const state = { count: 0, latestSpeaker: "", history: "" };
  const seq: string[] = [];
  let current: "Bull Researcher" | "Bear Researcher" = "Bull Researcher";
  for (let i = 0; i < 20; i += 1) {
    seq.push(current);
    state.count += 1;
    state.latestSpeaker = current.startsWith("Bull") ? "Bull" : "Bear";
    const next = routeDebate(state, maxRounds);
    if (next === "Research Manager") break;
    current = next;
  }
  return seq;
}

function runRiskDebate(maxRounds: number): string[] {
  const state = { count: 0, latestSpeaker: "", history: "" };
  const seq: string[] = [];
  let current: "Aggressive Analyst" | "Conservative Analyst" | "Neutral Analyst" =
    "Aggressive Analyst";
  for (let i = 0; i < 30; i += 1) {
    seq.push(current);
    state.count += 1;
    state.latestSpeaker = current.split(" ")[0] ?? "";
    const next = routeRiskDebate(state, maxRounds);
    if (next === "Portfolio Manager") break;
    current = next;
  }
  return seq;
}

describe("multi-round debate routing", () => {
  it("runs a single bull→bear pass when maxDebateRounds is 1", () => {
    expect(runResearchDebate(1)).toEqual(["Bull Researcher", "Bear Researcher"]);
  });

  it("loops bull↔bear for maxDebateRounds rounds", () => {
    expect(runResearchDebate(2)).toEqual([
      "Bull Researcher",
      "Bear Researcher",
      "Bull Researcher",
      "Bear Researcher",
    ]);
  });

  it("runs aggressive→conservative→neutral once when maxRiskRounds is 1", () => {
    expect(runRiskDebate(1)).toEqual([
      "Aggressive Analyst",
      "Conservative Analyst",
      "Neutral Analyst",
    ]);
  });

  it("loops the three risk analysts for maxRiskRounds rounds", () => {
    expect(runRiskDebate(2)).toEqual([
      "Aggressive Analyst",
      "Conservative Analyst",
      "Neutral Analyst",
      "Aggressive Analyst",
      "Conservative Analyst",
      "Neutral Analyst",
    ]);
  });
});

describe("withDebateTurn accumulation", () => {
  const baseState = {
    investment_debate_state: { count: 0, latestSpeaker: "", history: "" },
    risk_debate_state: { count: 0, latestSpeaker: "", history: "" },
  } as unknown as SpineStateType;

  it("increments count, records the speaker, and appends history per turn", async () => {
    const inner = async (): Promise<SpineStateUpdate> =>
      ({ messages: [new AIMessage("bull argument")] }) as SpineStateUpdate;
    const wrapped = withDebateTurn(inner, "Bull", "investment_debate_state");

    const update = (await wrapped(baseState)) as unknown as {
      investment_debate_state: Record<string, unknown>;
    };
    expect(update.investment_debate_state).toMatchObject({
      count: 1,
      latestSpeaker: "Bull",
      history: "Bull: bull argument",
      bullHistory: "Bull: bull argument",
      currentBullResponse: "Bull: bull argument",
      currentResponse: "Bull: bull argument",
    });
  });

  it("does not advance the counter on a tool round", async () => {
    const toolMsg = new AIMessage("");
    toolMsg.tool_calls = [{ name: "t", args: {}, id: "1" }];
    const inner = async (): Promise<SpineStateUpdate> =>
      ({ messages: [toolMsg] }) as SpineStateUpdate;
    const wrapped = withDebateTurn(inner, "Aggressive", "risk_debate_state");

    const update = (await wrapped(baseState)) as {
      risk_debate_state?: { count: number };
    };
    // The wrapper returns the inner update unchanged (no debate-state advance).
    expect(update.risk_debate_state).toBeUndefined();
  });
});
