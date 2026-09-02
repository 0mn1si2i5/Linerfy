import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

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
    expect(store.load()).toBeNull();
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
