import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { requireApiKey } from "../src/api";

const ENV_VAR = "TS_SONIOX_API_KEY_TEST";
let originalValue: string | undefined;

beforeEach(() => {
  originalValue = process.env[ENV_VAR];
  delete process.env[ENV_VAR];
});

afterEach(() => {
  if (originalValue !== undefined) {
    process.env[ENV_VAR] = originalValue;
  } else {
    delete process.env[ENV_VAR];
  }
});

describe("requireApiKey", () => {
  it("loads API key from .env file", () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-"));
    const envPath = path.join(tempDir, ".env");
    fs.writeFileSync(envPath, `${ENV_VAR}=from-env-file\n`, { encoding: "utf-8" });

    const apiKey = requireApiKey(ENV_VAR, { searchPaths: [envPath] });

    expect(apiKey).toBe("from-env-file");
    expect(process.env[ENV_VAR]).toBe("from-env-file");
  });

  it("throws when key missing", () => {
    expect(() => requireApiKey("TS_MISSING_KEY", { searchPaths: [] })).toThrowError();
  });
});
