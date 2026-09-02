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

/**
 * Verify a bearer token and check it against the whitelist.
 *
 * The token is validated against Supabase Auth using the publishable (anon)
 * key, which is the correct key for verifying a user's own JWT; the service
 * role key is never used on caller-supplied tokens.
 */
export async function resolveAuthState(token: string): Promise<AuthState> {
  const supabase = createClient(
    requireEnv("SUPABASE_URL"),
    requireEnv("SUPABASE_PUBLISHABLE_KEY"),
  );
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data.user) return { status: "unauthenticated" };

  const user: AuthUser = data.user;
  const githubId = githubUserId(user);
  if (githubId === null || !readWhitelistFromEnv().has(githubId)) {
    return { status: "not-whitelisted" };
  }
  return { status: "authenticated", githubId };
}
