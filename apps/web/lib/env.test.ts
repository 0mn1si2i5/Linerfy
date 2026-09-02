import { afterEach, describe, expect, it } from "vitest";

import { requireEnv } from "./env";

describe("requireEnv", () => {
  const original = process.env;

  afterEach(() => {
    process.env = original;
  });

  it("returns a present value", () => {
    process.env = { ...original, SUPABASE_URL: "https://example.supabase.co" };
    expect(requireEnv("SUPABASE_URL")).toBe("https://example.supabase.co");
  });

  it("fails fast naming the key but never the value", () => {
    process.env = { ...original, SUPABASE_URL: "" };
    expect(() => requireEnv("SUPABASE_URL")).toThrow(/SUPABASE_URL/);
    expect(() => requireEnv("SUPABASE_URL")).not.toThrow(/supabase\.co/);
  });
});
