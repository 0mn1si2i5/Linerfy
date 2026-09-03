"use client";

import { useEffect, useState } from "react";

import { createBrowserAuthClient } from "../lib/browser-auth";
import type { ContextResult } from "../lib/catalog";

export type AuthContextState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "error"; message: string }
  | { status: "ready"; result: ContextResult };

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const configured = Boolean(supabaseUrl && supabaseAnon);

/**
 * Read a release's context through the authenticated API using the browser's
 * session token. The catalog is never read directly here (no service-role key
 * exists in the client), so an anonymous visitor can only reach the
 * unauthenticated state.
 */
export function useAuthenticatedContext(slug: string): AuthContextState {
  const [state, setState] = useState<AuthContextState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!configured || !supabaseUrl || !supabaseAnon) {
        setState({ status: "error", message: "GitHub OAuth 未配置" });
        return;
      }
      const supabase = createBrowserAuthClient(supabaseUrl, supabaseAnon);
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) {
        if (!cancelled) setState({ status: "unauthenticated" });
        return;
      }
      try {
        const response = await fetch(`/api/context/${slug}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.status === 401 || response.status === 403) {
          if (!cancelled) setState({ status: "unauthenticated" });
          return;
        }
        const body = (await response.json()) as ContextResult;
        if (!cancelled) setState({ status: "ready", result: body });
      } catch {
        if (!cancelled) setState({ status: "error", message: "网络错误" });
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return state;
}
