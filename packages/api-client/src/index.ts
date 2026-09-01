import { musicContextSchema, type MusicContext } from "@linerfy/domain";

export type LinerfyClientOptions = {
  baseUrl: string;
  fetcher?: typeof fetch;
};

export class LinerfyClientError extends Error {
  constructor(
    readonly code: "NOT_FOUND" | "REQUEST_FAILED" | "INVALID_RESPONSE",
    message: string,
  ) {
    super(message);
    this.name = "LinerfyClientError";
  }
}

export function createLinerfyClient({
  baseUrl,
  fetcher = fetch,
}: LinerfyClientOptions) {
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");

  return {
    async getContext(query: string): Promise<MusicContext> {
      const response = await fetcher(
        `${normalizedBaseUrl}/api/context/${encodeURIComponent(query)}`,
        { headers: { accept: "application/json" }, method: "GET" },
      );

      if (response.status === 404) {
        throw new LinerfyClientError(
          "NOT_FOUND",
          "This release has not been covered yet",
        );
      }

      if (!response.ok) {
        throw new LinerfyClientError(
          "REQUEST_FAILED",
          `Linerfy request failed with status ${response.status}`,
        );
      }

      const parsed = musicContextSchema.safeParse(await response.json());
      if (!parsed.success) {
        throw new LinerfyClientError(
          "INVALID_RESPONSE",
          "Linerfy received context without valid source provenance",
        );
      }

      return parsed.data;
    },
  };
}
