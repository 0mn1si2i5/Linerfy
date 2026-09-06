import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { createTokenStore, type SafeCrypto } from "./token-store";

function fakeCrypto(): SafeCrypto {
  return {
    isAvailable: () => true,
    encrypt: (plain) => Buffer.from(plain, "utf8").toString("base64"),
    decrypt: (cipher) => Buffer.from(cipher, "base64").toString("utf8"),
  };
}

function tempFile(): string {
  return join(mkdtempSync(join(tmpdir(), "linerfy-token-")), "token.json");
}

describe("createTokenStore", () => {
  it("round-trips a token through encryption", () => {
    const file = tempFile();
    const store = createTokenStore(file, fakeCrypto());
    store.save("session-token");
    expect(store.load()).toBe("session-token");
  });

  it("does not persist the token in plaintext", () => {
    const file = tempFile();
    createTokenStore(file, fakeCrypto()).save("session-token");
    expect(readFileSync(file, "utf8")).not.toContain("session-token");
  });

  it("returns null when no token is stored", () => {
    expect(createTokenStore(tempFile(), fakeCrypto()).load()).toBeNull();
  });

  it("returns null on a corrupt file", () => {
    const file = tempFile();
    const store = createTokenStore(file, fakeCrypto());
    store.save("session-token");
    writeFileSync(file, "not json");
    expect(createTokenStore(file, fakeCrypto()).load()).toBeNull();
  });

  it("decrypts only once per process and updates the cache on save/clear", () => {
    const file = tempFile();
    createTokenStore(file, fakeCrypto()).save("session-token");
    const crypto = fakeCrypto();
    const decrypt = vi.fn(crypto.decrypt);
    const store = createTokenStore(file, { ...crypto, decrypt });
    expect(store.load()).toBe("session-token");
    expect(store.load()).toBe("session-token");
    store.save("refreshed-token");
    expect(store.load()).toBe("refreshed-token");
    store.clear();
    expect(store.load()).toBeNull();
    expect(decrypt).toHaveBeenCalledTimes(1);
  });

  it("does not repeatedly prompt after secure storage access is denied", () => {
    const file = tempFile();
    createTokenStore(file, fakeCrypto()).save("session-token");
    const decrypt = vi.fn(() => {
      throw new Error("access denied");
    });
    const store = createTokenStore(file, { ...fakeCrypto(), decrypt });
    expect(store.load()).toBeNull();
    expect(store.load()).toBeNull();
    expect(decrypt).toHaveBeenCalledTimes(1);
    store.save("new-login");
    expect(store.load()).toBe("new-login");
  });

  it("clears the stored token", () => {
    const file = tempFile();
    const store = createTokenStore(file, fakeCrypto());
    store.save("session-token");
    store.clear();
    expect(store.load()).toBeNull();
  });

  it("refuses to save when secure storage is unavailable", () => {
    const unavailable: SafeCrypto = {
      isAvailable: () => false,
      encrypt: (plain) => plain,
      decrypt: (cipher) => cipher,
    };
    expect(() =>
      createTokenStore(tempFile(), unavailable).save("token"),
    ).toThrow(/unavailable/);
  });
});
