import { describe, expect, it, vi } from "vitest";

import { featuredContext } from "@linerfy/domain/fixtures";

import { createLinerfyClient } from "./index";

describe("createLinerfyClient", () => {
  it("fetches and validates a context without mutating it", async () => {
    const fetcher = vi.fn(async () =>
      Promise.resolve(
        new Response(JSON.stringify(featuredContext), { status: 200 }),
      ),
    );
    const client = createLinerfyClient({
      baseUrl: "https://linerfy.example",
      fetcher,
    });

    await expect(client.getContext("norman fucking rockwell")).resolves.toEqual(
      featuredContext,
    );
    expect(fetcher).toHaveBeenCalledWith(
      "https://linerfy.example/api/context/norman%20fucking%20rockwell",
      { headers: { accept: "application/json" }, method: "GET" },
    );
  });

  it("surfaces a typed not-found error", async () => {
    const client = createLinerfyClient({
      baseUrl: "https://linerfy.example/",
      fetcher: async () => Promise.resolve(new Response(null, { status: 404 })),
    });

    await expect(client.getContext("unknown")).rejects.toMatchObject({
      code: "NOT_FOUND",
    });
  });
});
