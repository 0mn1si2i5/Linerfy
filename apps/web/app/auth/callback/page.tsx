"use client";

import { createClient } from "@supabase/supabase-js";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

// Exchanges the OAuth authorization code for a session. This must run in the
// browser: the PKCE code verifier lives in localStorage, set during sign-in.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const configured = Boolean(supabaseUrl && supabaseAnon);

function Exchange() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = searchParams.get("code");
  const [message, setMessage] = useState(
    !configured
      ? "GitHub OAuth 未配置。"
      : code
        ? "正在完成登录…"
        : "缺少授权 code。",
  );

  useEffect(() => {
    if (!configured || !code) return;
    const supabase = createClient(supabaseUrl!, supabaseAnon!);
    void supabase.auth.exchangeCodeForSession(code).then(({ error }) => {
      if (error) {
        setMessage(error.message);
      } else {
        router.push("/");
      }
    });
  }, [code, router]);

  return <p>{message}</p>;
}

export default function AuthCallbackPage() {
  return (
    <main>
      <Suspense fallback={<p>正在完成登录…</p>}>
        <Exchange />
      </Suspense>
    </main>
  );
}
