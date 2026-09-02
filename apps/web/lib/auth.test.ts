import { describe, expect, it } from "vitest";

import {
  githubUserId,
  isWhitelisted,
  parseWhitelist,
  type AuthUser,
} from "./auth";

function githubUser(id: string): AuthUser {
  return { identities: [{ provider: "github", id }] };
}

describe("parseWhitelist", () => {
  it("splits and trims comma-separated ids", () => {
    expect(parseWhitelist("123, 456 ,789")).toEqual(
      new Set(["123", "456", "789"]),
    );
  });

  it("returns an empty set for empty or whitespace input", () => {
    expect(parseWhitelist("")).toEqual(new Set());
    expect(parseWhitelist("  , , ")).toEqual(new Set());
  });
});

describe("githubUserId", () => {
  it("reads the numeric id from the github identity", () => {
    expect(githubUserId(githubUser("987654"))).toBe("987654");
  });

  it("ignores non-github identities", () => {
    const user: AuthUser = { identities: [{ provider: "google", id: "1" }] };
    expect(githubUserId(user)).toBeNull();
  });

  it("falls back to provider_id on user_metadata", () => {
    const user: AuthUser = { user_metadata: { provider_id: "42" } };
    expect(githubUserId(user)).toBe("42");
  });

  it("returns null when no github identity exists", () => {
    expect(githubUserId({})).toBeNull();
    expect(githubUserId({ identities: [] })).toBeNull();
  });
});

describe("isWhitelisted", () => {
  it("allows a whitelisted github id", () => {
    expect(isWhitelisted(githubUser("123"), new Set(["123"]))).toBe(true);
  });

  it("denies a github id not on the list", () => {
    expect(isWhitelisted(githubUser("999"), new Set(["123"]))).toBe(false);
  });

  it("denies a user with no github identity", () => {
    expect(isWhitelisted({}, new Set(["123"]))).toBe(false);
  });
});
