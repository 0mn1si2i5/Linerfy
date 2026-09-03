/**
 * GitHub OAuth via Supabase Auth, driven entirely from the Electron main
 * process. The renderer never touches the session: it only asks main to
 * "sign in" and observes a minimal signed-in/signed-out state.
 *
 * Flow (PKCE, per Supabase Auth):
 *   1. generate a code_verifier + S256 code_challenge,
 *   2. open the system browser to the authorize URL,
 *   3. capture the redirect code on a loopback server on 127.0.0.1,
 *   4. exchange the code for a session with the token endpoint,
 *   5. hand the session back to main, which encrypts it via safeStorage.
 */

import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { createServer, type Server } from "node:http";

/** The subset of the Supabase session main persists (encrypted) in the store. */
export interface SupabaseSession {
  access_token: string;
  refresh_token: string;
  expires_at?: number;
}

export interface OAuthConfig {
  /** Supabase project URL, e.g. https://<ref>.supabase.co */
  url: string;
  /** The publishable (anon) key — enough to run the auth flow, not to read RLS-guarded rows. */
  anonKey: string;
  provider: "github";
  /** Loopback port for the redirect; must be allow-listed in Supabase Auth. */
  redirectPort?: number;
}

export interface PkcePair {
  verifier: string;
  challenge: string;
}

function base64Url(input: Buffer): string {
  return input.toString("base64url");
}

/** A PKCE S256 verifier/challenge pair, random on every call. */
export function generatePkce(): PkcePair {
  const verifier = base64Url(randomBytes(32));
  const challenge = base64Url(createHash("sha256").update(verifier).digest());
  return { verifier, challenge };
}

/** A random CSRF `state` value, unique per authorization attempt. */
export function generateState(): string {
  return base64Url(randomBytes(16));
}

/** Constant-time compare so a mismatched OAuth `state` is rejected safely. */
export function stateMatches(expected: string, received: string): boolean {
  if (expected.length !== received.length) return false;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(received));
}

/** The authorize URL the system browser is sent to. */
export function authorizeUrl(
  config: OAuthConfig,
  redirectTo: string,
  challenge: string,
  state: string,
): string {
  const params = new URLSearchParams({
    provider: config.provider,
    redirect_to: redirectTo,
    code_challenge: challenge,
    code_challenge_method: "S256",
    state,
  });
  return `${config.url.replace(/\/+$/, "")}/auth/v1/authorize?${params}`;
}

/** Exchange the authorization code for a session (GoTrue PKCE grant). */
export async function exchangeCodeForSession(
  config: OAuthConfig,
  code: string,
  verifier: string,
): Promise<SupabaseSession> {
  const res = await fetch(
    `${config.url.replace(/\/+$/, "")}/auth/v1/token?grant_type=pkce`,
    {
      method: "POST",
      headers: {
        apikey: config.anonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ auth_code: code, code_verifier: verifier }),
    },
  );
  if (!res.ok) {
    throw new Error(`token exchange failed: HTTP ${res.status}`);
  }
  const data = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_at?: number;
  };
  if (!data.access_token || !data.refresh_token) {
    throw new Error("token exchange returned no session");
  }
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: data.expires_at,
  };
}

/** Refresh an expired access token using the persisted refresh token (GoTrue). */
export async function refreshSession(
  config: OAuthConfig,
  refreshToken: string,
): Promise<SupabaseSession> {
  const res = await fetch(
    `${config.url.replace(/\/+$/, "")}/auth/v1/token?grant_type=refresh_token`,
    {
      method: "POST",
      headers: {
        apikey: config.anonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    },
  );
  if (!res.ok) {
    throw new Error(`token refresh failed: HTTP ${res.status}`);
  }
  const data = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_at?: number;
  };
  if (!data.access_token) {
    throw new Error("token refresh returned no access token");
  }
  return {
    access_token: data.access_token,
    // Supabase may rotate the refresh token on refresh; keep the new one.
    refresh_token: data.refresh_token ?? refreshToken,
    expires_at: data.expires_at,
  };
}

export interface CallbackServer {
  port: number;
  /**
   * Resolve with the authorization code once the redirect arrives, after
   * verifying its `state` matches the value this flow generated. Rejects on
   * timeout, a missing code, or a state mismatch (a forged redirect).
   */
  waitForCallback(expectedState: string, timeoutMs?: number): Promise<string>;
  close(): void;
}

interface CallbackPayload {
  code: string;
  state: string;
}

/**
 * A loopback HTTP server on 127.0.0.1 that captures the OAuth redirect. It
 * answers the callback with a short "you may close this tab" page, so the code
 * and state land back in the main process only.
 */
export function startCallbackServer(port = 0): Promise<CallbackServer> {
  return new Promise((resolve, reject) => {
    let settled = false;
    let settle: (payload: CallbackPayload) => void = () => {};
    const payloadPromise = new Promise<CallbackPayload>((res) => {
      settle = res;
    });

    const server: Server = createServer((req, res) => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      if (url.pathname === "/callback") {
        const code = url.searchParams.get("code");
        const state = url.searchParams.get("state");
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(
          '<!doctype html><meta charset="utf-8"><title>Linerfy</title>' +
            "<p>登录完成，可以关闭此窗口。</p>",
        );
        if (!settled) {
          settled = true;
          settle({ code: code ?? "", state: state ?? "" });
        }
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    server.on("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const address = server.address();
      const port =
        typeof address === "object" && address !== null ? address.port : 0;
      resolve({
        port,
        waitForCallback(expectedState, timeoutMs = 120_000) {
          return new Promise<string>((res, rej) => {
            const timer = setTimeout(() => {
              if (!settled) {
                settled = true;
                rej(new Error("login timed out"));
              }
            }, timeoutMs);
            void payloadPromise.then(
              (payload) => {
                clearTimeout(timer);
                if (!payload.code) {
                  rej(new Error("authorization returned no code"));
                } else if (!stateMatches(expectedState, payload.state)) {
                  rej(new Error("OAuth state mismatch"));
                } else {
                  res(payload.code);
                }
              },
              () => {
                clearTimeout(timer);
                rej(new Error("login failed"));
              },
            );
          });
        },
        close() {
          server.close();
        },
      });
    });
  });
}

/** Run the whole flow and return the session, or throw on any failure. */
export async function performOAuthFlow(
  config: OAuthConfig,
  openExternal: (url: string) => Promise<void>,
): Promise<SupabaseSession> {
  const { verifier, challenge } = generatePkce();
  const state = generateState();
  const server = await startCallbackServer(config.redirectPort ?? 4862);
  try {
    const redirectTo = `http://127.0.0.1:${server.port}/callback`;
    await openExternal(authorizeUrl(config, redirectTo, challenge, state));
    const code = await server.waitForCallback(state);
    return await exchangeCodeForSession(config, code, verifier);
  } finally {
    server.close();
  }
}
