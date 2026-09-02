"use client";

import { createClient } from "@supabase/supabase-js";
import { useState } from "react";

// The OAuth sign-in page. Requires the GitHub provider to be enabled in
// Supabase Auth and the browser env vars below to be set (see .env.example).
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const configured = Boolean(supabaseUrl && supabaseAnon);
const supabase = configured ? createClient(supabaseUrl!, supabaseAnon!) : null;

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
      <main>
        <p>
          GitHub OAuth 未配置：缺少 NEXT_PUBLIC_SUPABASE_URL 或
          NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY。
        </p>
      </main>
    );
  }

  return (
    <main>
      <h1>登录 Linerfy</h1>
      <p>使用 GitHub 账号登录，以读取乐评语境。</p>
      <button type="button" onClick={() => void signIn()}>
        使用 GitHub 登录
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </main>
  );
}
