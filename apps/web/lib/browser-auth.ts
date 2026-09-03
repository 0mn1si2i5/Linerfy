import { createClient } from "@supabase/supabase-js";

/**
 * Browser auth uses an explicit PKCE exchange on `/auth/callback`.
 *
 * `detectSessionInUrl` stays off so client initialization cannot race the
 * callback page's single `exchangeCodeForSession` call.
 */
export function createBrowserAuthClient(url: string, publishableKey: string) {
  return createClient(url, publishableKey, {
    auth: {
      flowType: "pkce",
      detectSessionInUrl: false,
    },
  });
}
