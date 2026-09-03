import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { requireEnv } from "./env";

/** A server-only client that bypasses RLS via the service role key. */
export function serviceClient(): SupabaseClient {
  return createClient(
    requireEnv("SUPABASE_URL"),
    requireEnv("SUPABASE_SERVICE_ROLE_KEY"),
  );
}
