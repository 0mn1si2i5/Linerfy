"use client";

import { createClient } from "@supabase/supabase-js";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

// Exchanges the OAuth authorization code for a session. This must run in the
// browser: the PKCE code verifier lives in localStorage, set during sign-in.
export const dynamic = "force-dynamic";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const configured = Boolean(supabaseUrl && supabaseAnon);

export default function AuthCallbackPage() {
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

  return (
    <main>
      <p>{message}</p>
    </main>
  );
}
