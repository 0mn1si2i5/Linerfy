/**
 * Keychain-backed storage for the Supabase session token.
 *
 * The token is encrypted with the operating system's secure storage (on macOS,
 * the Keychain) before it is written to disk, and never held in plaintext. The
 * renderer never sees the token — it only observes a minimal signed-in state.
 */

import { readFileSync, unlinkSync, writeFileSync } from "node:fs";

/** The encryption primitive supplied by Electron's ``safeStorage``. */
export interface SafeCrypto {
  isAvailable(): boolean;
  encrypt(plain: string): string;
  decrypt(cipher: string): string;
}

export interface TokenStore {
  save(token: string): void;
  load(): string | null;
  clear(): void;
}

interface StoredToken {
  version: 1;
  cipher: string;
}

/**
 * Build a token store. The crypto primitive is injected so the file format and
 * failure behaviour are unit-testable without Electron.
 */
export function createTokenStore(file: string, crypto: SafeCrypto): TokenStore {
  return {
    save(token: string): void {
      if (!crypto.isAvailable()) {
        // Fail closed: never persist an unencrypted session token.
        throw new Error(
          "secure storage is unavailable; refusing to store token",
        );
      }
      const payload: StoredToken = {
        version: 1,
        cipher: crypto.encrypt(token),
      };
      writeFileSync(file, JSON.stringify(payload), "utf8");
    },

    load(): string | null {
      let raw: string;
      try {
        raw = readFileSync(file, "utf8");
      } catch {
        return null;
      }
      try {
        const parsed = JSON.parse(raw) as StoredToken;
        if (parsed.version !== 1) return null;
        return crypto.decrypt(parsed.cipher);
      } catch {
        return null;
      }
    },

    clear(): void {
      try {
        unlinkSync(file);
      } catch {
        // Already gone.
      }
    },
  };
}
