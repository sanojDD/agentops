import type { Connection } from "./types";

const KEY = "agentops.connection";

/** Owner sessions can be remembered (localStorage). Demo sessions never are:
 *  they live in sessionStorage and are ignored once they have expired. */
export function loadConnection(): { conn: Connection; remembered: boolean } | null {
  const stores: [Storage, boolean][] = [];
  try {
    stores.push([window.localStorage, true], [window.sessionStorage, false]);
  } catch {
    return null; // storage blocked by the browser
  }
  for (const [store, remembered] of stores) {
    try {
      const raw = store.getItem(KEY);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      if (typeof parsed?.baseUrl !== "string" || typeof parsed?.token !== "string") continue;

      const role = parsed.role === "visitor" ? "visitor" : "admin";
      const expiresAt = typeof parsed.expiresAt === "number" ? parsed.expiresAt : undefined;
      if (role === "visitor" && (expiresAt === undefined || expiresAt < Date.now())) {
        store.removeItem(KEY);
        continue;
      }
      return { conn: { baseUrl: parsed.baseUrl, token: parsed.token, role, expiresAt }, remembered };
    } catch {
      /* ignore corrupt entries */
    }
  }
  return null;
}

export function saveConnection(conn: Connection, remember: boolean): void {
  clearConnection();
  const persist = remember && conn.role !== "visitor";
  try {
    (persist ? window.localStorage : window.sessionStorage).setItem(KEY, JSON.stringify(conn));
  } catch {
    /* storage blocked: the app still works for this session */
  }
}

export function clearConnection(): void {
  try {
    window.localStorage.removeItem(KEY);
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
