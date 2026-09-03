import { describe, expect, it } from "vitest";

import {
  bearerToken,
  githubUserId,
  isWhitelisted,
  parseWhitelist,
  resolveAuthState,
  type AuthUser,
} from "./auth";

function githubUser(id: string): AuthUser {
  return { identities: [{ provider: "github", id }] };
}

describe("bearerToken", () => {
  it("extracts the token from a Bearer header", () => {
    expect(bearerToken("Bearer abc.def")).toBe("abc.def");
  });

  it("returns empty for a missing or non-bearer header", () => {
    expect(bearerToken(null)).toBe("");
    expect(bearerToken(undefined)).toBe("");
    expect(bearerToken("Basic xyz")).toBe("");
  });
});

describe("resolveAuthState", () => {
  const whitelist = new Set(["123"]);

  it("returns unauthenticated for an invalid token", async () => {
    const verify = async () => null;
    expect(await resolveAuthState("bad", verify, whitelist)).toEqual({
      status: "unauthenticated",
    });
  });

  it("returns not-whitelisted for a valid but unlisted user", async () => {
    const verify = async () => githubUser("999");
    expect(await resolveAuthState("ok", verify, whitelist)).toEqual({
      status: "not-whitelisted",
    });
  });

  it("returns authenticated for a whitelisted user", async () => {
    const verify = async () => githubUser("123");
    expect(await resolveAuthState("ok", verify, whitelist)).toEqual({
      status: "authenticated",
      githubId: "123",
    });
  });

  it("denies a user with no github identity", async () => {
    const verify = async () => ({ identities: [] });
    expect(await resolveAuthState("ok", verify, whitelist)).toEqual({
      status: "not-whitelisted",
    });
  });
});

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
