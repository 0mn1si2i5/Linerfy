import { get } from "node:http";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  authorizeUrl,
  exchangeCodeForSession,
  generatePkce,
  generateState,
  refreshSession,
  startCallbackServer,
  stateMatches,
} from "./oauth";

const config = {
  url: "https://rcrtpapxhkqkobjcqxkd.supabase.co",
  anonKey: "anon-key",
  provider: "github",
} as const;

describe("generatePkce", () => {
  it("produces a base64url verifier and its S256 challenge", () => {
    const { verifier, challenge } = generatePkce();
    expect(verifier).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(challenge).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(challenge).not.toBe(verifier);
  });

  it("is random per call", () => {
    const a = generatePkce();
    const b = generatePkce();
    expect(a.verifier).not.toBe(b.verifier);
    expect(a.challenge).not.toBe(b.challenge);
  });
});

describe("generateState", () => {
  it("produces a base64url value and is random per call", () => {
    const a = generateState();
    const b = generateState();
    expect(a).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(b).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(a).not.toBe(b);
  });
});

describe("stateMatches", () => {
  it("accepts an equal state and rejects a mismatch or length change", () => {
    expect(stateMatches("abc", "abc")).toBe(true);
    expect(stateMatches("abc", "abd")).toBe(false);
    expect(stateMatches("abc", "abcd")).toBe(false);
  });
});

describe("authorizeUrl", () => {
  it("points at the Supabase authorize endpoint with PKCE + state params", () => {
    const url = authorizeUrl(
      config,
      "http://127.0.0.1:4000/callback",
      "challenge",
      "state-value",
    );
    const parsed = new URL(url);
    expect(parsed.origin + parsed.pathname).toBe(
      "https://rcrtpapxhkqkobjcqxkd.supabase.co/auth/v1/authorize",
    );
    expect(parsed.searchParams.get("provider")).toBe("github");
    expect(parsed.searchParams.get("redirect_to")).toBe(
      "http://127.0.0.1:4000/callback",
    );
    expect(parsed.searchParams.get("code_challenge")).toBe("challenge");
    expect(parsed.searchParams.get("code_challenge_method")).toBe("S256");
    expect(parsed.searchParams.get("state")).toBe("state-value");
  });
});

describe("exchangeCodeForSession", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("exchanges the code via the pkce grant and returns the session", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          json: async () => ({
            access_token: "at",
            refresh_token: "rt",
            expires_at: 123,
          }),
        }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    const session = await exchangeCodeForSession(config, "code", "verifier");
    expect(session).toEqual({
      access_token: "at",
      refresh_token: "rt",
      expires_at: 123,
    });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      { headers: Record<string, string>; body: string },
    ];
    expect(url).toBe(
      "https://rcrtpapxhkqkobjcqxkd.supabase.co/auth/v1/token?grant_type=pkce",
    );
    expect(init.headers.apikey).toBe("anon-key");
    expect(JSON.parse(init.body)).toEqual({
      auth_code: "code",
      code_verifier: "verifier",
    });
  });

  it("throws on a non-2xx token response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 400 }) as unknown as Response),
    );
    await expect(
      exchangeCodeForSession(config, "code", "verifier"),
    ).rejects.toThrow(/HTTP 400/);
  });
});

describe("startCallbackServer", () => {
  it("captures the code when the redirect state matches", async () => {
    const server = await startCallbackServer();
    try {
      const pending = server.waitForCallback("s3cret", 5000);
      await new Promise<void>((resolve, reject) => {
        const req = get(
          `http://127.0.0.1:${server.port}/callback?code=abc123&state=s3cret`,
          (res) => {
            res.resume();
            res.on("end", () => resolve());
          },
        );
        req.on("error", reject);
      });
      await expect(pending).resolves.toBe("abc123");
    } finally {
      server.close();
    }
  });

  it("rejects a redirect whose state does not match", async () => {
    const server = await startCallbackServer();
    try {
      const pending = server.waitForCallback("s3cret", 5000);
      // Attach the rejection handler before the redirect arrives so the
      // rejection is observed, not reported as an unhandled promise rejection.
      const assertion = expect(pending).rejects.toThrow(/state mismatch/);
      await new Promise<void>((resolve, reject) => {
        const req = get(
          `http://127.0.0.1:${server.port}/callback?code=abc123&state=wrong`,
          (res) => {
            res.resume();
            res.on("end", () => resolve());
          },
        );
        req.on("error", reject);
      });
      await assertion;
    } finally {
      server.close();
    }
  });
});

describe("refreshSession", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("exchanges a refresh token for a fresh session", async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          json: async () => ({
            access_token: "new-at",
            refresh_token: "new-rt",
            expires_at: 456,
          }),
        }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    const session = await refreshSession(config, "old-rt");
    expect(session).toEqual({
      access_token: "new-at",
      refresh_token: "new-rt",
      expires_at: 456,
    });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      { body: string },
    ];
    expect(url).toBe(
      "https://rcrtpapxhkqkobjcqxkd.supabase.co/auth/v1/token?grant_type=refresh_token",
    );
    expect(JSON.parse(init.body)).toEqual({ refresh_token: "old-rt" });
  });

  it("keeps the old refresh token when the server does not rotate it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({
            ok: true,
            json: async () => ({ access_token: "new-at", expires_at: 456 }),
          }) as unknown as Response,
      ),
    );

    const session = await refreshSession(config, "old-rt");
    expect(session.refresh_token).toBe("old-rt");
  });

  it("throws on a non-2xx refresh response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 400 }) as unknown as Response),
    );
    await expect(refreshSession(config, "old-rt")).rejects.toThrow(/HTTP 400/);
  });
});
