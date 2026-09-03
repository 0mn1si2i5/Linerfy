import { describe, expect, it } from "vitest";

import { createBrowserAuthClient } from "./browser-auth";

describe("createBrowserAuthClient", () => {
  it("starts OAuth with a PKCE challenge", async () => {
    const client = createBrowserAuthClient(
      "https://example.supabase.co",
      "publishable-key",
    );
    const { data, error } = await client.auth.signInWithOAuth({
      provider: "github",
      options: {
        redirectTo: "https://app.example/auth/callback",
        skipBrowserRedirect: true,
      },
    });

    expect(error).toBeNull();
    expect(data.url).not.toBeNull();
    if (!data.url) throw new Error("Supabase returned no authorize URL");
    const authorizeUrl = new URL(data.url);
    expect(authorizeUrl.searchParams.get("code_challenge")).toBeTruthy();
    expect(authorizeUrl.searchParams.get("code_challenge_method")).toBe("s256");
  });
});
