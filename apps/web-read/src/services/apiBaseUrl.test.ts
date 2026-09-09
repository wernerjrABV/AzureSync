import { describe, expect, test } from "vitest";

import { API_BASE_URL } from "./apiBaseUrl";

describe("API_BASE_URL", () => {
  test("defaults to the api-read local development port in Vitest", () => {
    expect(API_BASE_URL).toBe("http://127.0.0.1:5001");
  });
});
