/**
 * Unit tests for structured output module (sub-step 2.5c-3).
 */

import { describe, expect, it } from "vitest";
import {
  buildProseOnlyFallbackPrompt,
  buildStructuredOutputPrompt,
  stripStructuredOnlyText,
} from "../src/agents/helpers/structured_output.js";
import {
  STRUCTURED_FIELD_POPULATION_INSTRUCTION,
  STRUCTURED_FIELD_VISIBILITY_INSTRUCTION,
  STRUCTURED_TRIGGER_METRICS_INSTRUCTION,
} from "../src/agents/prompts/trader.js";

describe("stripStructuredOnlyText", () => {
  it("removes structured-only sentences", () => {
    const text = `Normal system prompt. ${STRUCTURED_FIELD_POPULATION_INSTRUCTION} More text.`;
    const result = stripStructuredOnlyText(text);
    expect(result).toContain("Normal system prompt");
    expect(result).toContain("More text");
    expect(result).not.toContain("target_weight_pct");
  });

  it("collapses excess newlines", () => {
    const text = `A\n\n\n\nB`;
    const result = stripStructuredOnlyText(text);
    expect(result).not.toMatch(/\n{3,}/);
  });

  it("handles empty text", () => {
    expect(stripStructuredOnlyText("")).toBe("");
    expect(stripStructuredOnlyText(undefined as unknown as string)).toBe("");
  });
});

describe("buildStructuredOutputPrompt", () => {
  it("builds Chinese structured prompt pair", () => {
    const [sys, user] = buildStructuredOutputPrompt(
      "TraderProposal",
      ["thesis", "execution_plan", "risk_management", "rating"],
      "original system",
      "source material",
      "Chinese",
    );
    expect(sys.content).toContain("TraderProposal");
    expect(sys.content).toContain("thesis, execution_plan, risk_management, rating");
    expect(sys.content).toContain("Chinese");
    expect(user.content).toContain("source material");
  });

  it("builds English structured prompt pair", () => {
    const [sys, user] = buildStructuredOutputPrompt(
      "TraderProposal",
      ["thesis", "rating"],
      "orig",
      "data",
      "English",
    );
    expect(sys.content).not.toContain("Chinese");
    expect(sys.content).toContain("Structured-output mode");
    expect(user.content).toContain("data");
  });
});

describe("buildProseOnlyFallbackPrompt", () => {
  it("strips structured text and appends fallback instruction", () => {
    const system = `You are an analyst. ${STRUCTURED_FIELD_VISIBILITY_INSTRUCTION} Provide report.`;
    const result = buildProseOnlyFallbackPrompt(system, "Free-text fallback mode.");
    expect(result).toContain("You are an analyst");
    expect(result).toContain("Provide report");
    expect(result).toContain("Free-text fallback mode");
    expect(result).not.toContain("Never expose machine-readable");
  });

  it("returns stripped text without extra when no instruction", () => {
    const system = `Base. ${STRUCTURED_TRIGGER_METRICS_INSTRUCTION} End.`;
    const result = buildProseOnlyFallbackPrompt(system);
    expect(result).toContain("Base");
    expect(result).toContain("End");
    expect(result).not.toContain("prefer supported metrics");
  });
});
