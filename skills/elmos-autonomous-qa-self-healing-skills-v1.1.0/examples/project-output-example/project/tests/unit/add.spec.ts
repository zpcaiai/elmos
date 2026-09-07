import { describe, expect, it } from "vitest";
import { add } from "../../src/add";

describe("add", () => {
  it("REQ-CALC-001: adds positive and negative integers", () => {
    expect(add(2, -1)).toBe(1);
  });
});
