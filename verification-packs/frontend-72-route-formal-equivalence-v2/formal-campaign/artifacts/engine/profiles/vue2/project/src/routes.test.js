import { describe, expect, it } from "vitest";
import { routes } from "./routes";

describe("generated UI route contract", () => {
  it("preserves every declared route", () => expect(routes).toHaveLength(3));
  it("keeps route paths unique", () => expect(new Set(routes.map(route => route.path)).size).toBe(routes.length));
});
