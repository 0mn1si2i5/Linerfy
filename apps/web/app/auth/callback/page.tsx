"use client";

import { LinerfyMark } from "@linerfy/ui";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { createBrowserAuthClient } from "../../../lib/browser-auth";

// Exchanges the OAuth authorization code for a session. This must run in the
// browser: the PKCE code verifier lives in localStorage, set during sign-in.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const configured = Boolean(supabaseUrl && supabaseAnon);

function Exchange() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = searchParams.get("code");
  const oauthError =
    searchParams.get("error_description") ?? searchParams.get("error");
  const [message, setMessage] = useState(
    !configured
      ? "GitHub OAuth 未配置。"
      : oauthError
        ? `GitHub 登录失败：${oauthError}`
        : code
          ? "正在完成登录…"
          : "缺少授权 code。",
  );

  useEffect(() => {
    if (!configured || !code || oauthError) return;
    const supabase = createBrowserAuthClient(supabaseUrl!, supabaseAnon!);
    void supabase.auth.exchangeCodeForSession(code).then(({ error }) => {
      if (error) {
        setMessage(error.message);
      } else {
        router.push("/");
      }
    });
  }, [code, oauthError, router]);

  return (
    <div className="auth-card compact">
      <LinerfyMark />
      <p>{message}</p>
      {!code || oauthError ? (
        <Link className="quiet-link" href="/login">
          回到登录
        </Link>
      ) : null}
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <main className="auth-shell">
      <Suspense
        fallback={
          <div className="auth-card compact">
            <p>正在完成登录…</p>
          </div>
        }
      >
        <Exchange />
      </Suspense>
    </main>
  );
}
