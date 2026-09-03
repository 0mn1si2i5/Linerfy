import { get } from "node:http";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  authorizeUrl,
  exchangeCodeForSession,
  generatePkce,
  startCallbackServer,
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

describe("authorizeUrl", () => {
  it("points at the Supabase authorize endpoint with PKCE params", () => {
    const url = authorizeUrl(
      config,
      "http://127.0.0.1:4000/callback",
      "challenge",
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
  it("captures the code from the loopback redirect", async () => {
    const server = await startCallbackServer();
    try {
      const pending = server.waitForCode(5000);
      await new Promise<void>((resolve, reject) => {
        const req = get(
          `http://127.0.0.1:${server.port}/callback?code=abc123`,
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
});
