import { afterEach, describe, expect, it } from "vitest";
import { clearConnection, loadConnection, saveConnection } from "./storage";

afterEach(() => {
  clearConnection();
  localStorage.clear();
  sessionStorage.clear();
});

describe("storage", () => {
  it("remembers an owner connection in localStorage only when asked", () => {
    saveConnection({ baseUrl: "https://a", token: "t", role: "admin" }, true);
    expect(localStorage.getItem("agentops.connection")).toContain('"token":"t"');
    expect(sessionStorage.getItem("agentops.connection")).toBeNull();
    expect(loadConnection()?.remembered).toBe(true);

    saveConnection({ baseUrl: "https://a", token: "t", role: "admin" }, false);
    expect(localStorage.getItem("agentops.connection")).toBeNull();
    expect(loadConnection()?.remembered).toBe(false);
  });

  it("never persists a demo session beyond the tab, even if remember is true", () => {
    saveConnection(
      { baseUrl: "https://a", token: "v1.x", role: "visitor", expiresAt: Date.now() + 60_000 },
      true,
    );
    expect(localStorage.getItem("agentops.connection")).toBeNull();
    expect(loadConnection()?.conn.role).toBe("visitor");
  });

  it("ignores and removes an expired demo session", () => {
    saveConnection(
      { baseUrl: "https://a", token: "v1.x", role: "visitor", expiresAt: Date.now() - 1000 },
      false,
    );
    expect(loadConnection()).toBeNull();
    expect(sessionStorage.getItem("agentops.connection")).toBeNull();
  });

  it("treats a connection saved before demo mode as an owner connection", () => {
    localStorage.setItem("agentops.connection", JSON.stringify({ baseUrl: "https://a", token: "t" }));
    expect(loadConnection()?.conn.role).toBe("admin");
  });
});
