import { createClient } from "@supabase/supabase-js";

import { requireEnv } from "./env";

const GITHUB_PROVIDER = "github";

/**
 * The outcome of authenticating a caller against the GitHub id whitelist.
 *
 * `unauthenticated` means no valid session; `not-whitelisted` means a valid
 * session whose GitHub identity is not on the allowlist. Both are denied.
 */
export type AuthState =
  | { status: "authenticated"; githubId: string }
  | { status: "unauthenticated" }
  | { status: "not-whitelisted" };

/** The minimal slice of a Supabase user the auth boundary reads. */
export interface AuthUser {
  identities?: { provider: string; id?: string | null }[] | null;
  user_metadata?: Record<string, unknown>;
}

/** Parse a comma-separated list of numeric GitHub ids into a set. */
export function parseWhitelist(raw: string): Set<string> {
  const ids = new Set<string>();
  for (const token of raw.split(",")) {
    const id = token.trim();
    if (id !== "") ids.add(id);
  }
  return ids;
}

/** The numeric GitHub id of a user, if they signed in through GitHub. */
export function githubUserId(user: AuthUser): string | null {
  const identity = user.identities?.find(
    (entry) => entry.provider === GITHUB_PROVIDER,
  );
  if (identity?.id) return identity.id;
  // Some provider configs surface the numeric id on user_metadata instead.
  const providerId = user.user_metadata?.provider_id;
  if (typeof providerId === "string" && providerId !== "") return providerId;
  return null;
}

export function isWhitelisted(user: AuthUser, whitelist: Set<string>): boolean {
  const id = githubUserId(user);
  return id !== null && whitelist.has(id);
}

/** Read the whitelist from the environment; an empty list denies everyone. */
export function readWhitelistFromEnv(): Set<string> {
  return parseWhitelist(process.env.LINERFY_ALLOWED_GITHUB_IDS ?? "");
}

/** Extract a bearer token from an Authorization header value. */
export function bearerToken(header: string | null | undefined): string {
  if (!header) return "";
  return header.startsWith("Bearer ")
    ? header.slice("Bearer ".length).trim()
    : "";
}

/** A verifier seam: given a token, resolve the authenticated user or null. */
export type TokenVerifier = (token: string) => Promise<AuthUser | null>;

/**
 * The real verifier: validate a caller's token against Supabase Auth using the
 * publishable (anon) key. The service role key is never used on caller tokens.
 */
async function supabaseTokenVerifier(token: string): Promise<AuthUser | null> {
  const supabase = createClient(
    requireEnv("SUPABASE_URL"),
    requireEnv("SUPABASE_PUBLISHABLE_KEY"),
  );
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data.user) return null;
  return data.user as AuthUser;
}

/**
 * Classify a bearer token: `authenticated` (whitelisted), `unauthenticated`
 * (no/invalid token), or `not-whitelisted` (valid token, id not on the list).
 *
 * The verifier and whitelist are injectable so the three outcomes are unit-
 * testable without a network call; the defaults use the real Supabase check
 * and the environment whitelist.
 */
export async function resolveAuthState(
  token: string,
  verify: TokenVerifier = supabaseTokenVerifier,
  whitelist: Set<string> = readWhitelistFromEnv(),
): Promise<AuthState> {
  const user = await verify(token);
  if (!user) return { status: "unauthenticated" };

  const githubId = githubUserId(user);
  if (githubId === null || !whitelist.has(githubId)) {
    return { status: "not-whitelisted" };
  }
  return { status: "authenticated", githubId };
}
