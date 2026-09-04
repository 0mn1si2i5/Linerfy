"use client";

import { LinerfyMark } from "@linerfy/ui";
import Link from "next/link";
import { useState } from "react";

import { createBrowserAuthClient } from "../../lib/browser-auth";

// The OAuth sign-in page. Requires the GitHub provider to be enabled in
// Supabase Auth and the browser env vars below to be set (see .env.example).
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const configured = Boolean(supabaseUrl && supabaseAnon);
const supabase = configured
  ? createBrowserAuthClient(supabaseUrl!, supabaseAnon!)
  : null;

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  async function signIn() {
    if (!supabase) return;
    setError(null);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) setError(error.message);
  }

  if (!configured) {
    return (
      <main className="auth-shell">
        <div className="auth-card">
          <LinerfyMark />
          <p role="alert">登录配置缺失</p>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-shell">
      <div className="auth-card">
        <LinerfyMark />
        <button
          className="button primary auth-action"
          type="button"
          onClick={() => void signIn()}
        >
          使用 GitHub 登录
        </button>
        <Link className="quiet-link" href="/">
          返回
        </Link>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </main>
  );
}
