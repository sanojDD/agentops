import type { Connection } from "./types";

const KEY = "agentops.connection";

/** "Remember on this device" uses localStorage; otherwise the token only lives for this tab. */
export function loadConnection(): { conn: Connection; remembered: boolean } | null {
  const stores: [Storage | undefined, boolean][] = [];
  try {
    stores.push([window.localStorage, true], [window.sessionStorage, false]);
  } catch {
    return null; // storage blocked by the browser
  }
  for (const [store, remembered] of stores) {
    try {
      const raw = store?.getItem(KEY);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      if (typeof parsed?.baseUrl === "string" && typeof parsed?.token === "string") {
        return { conn: { baseUrl: parsed.baseUrl, token: parsed.token }, remembered };
      }
    } catch {
      /* ignore corrupt entries */
    }
  }
  return null;
}

export function saveConnection(conn: Connection, remember: boolean): void {
  clearConnection();
  try {
    (remember ? window.localStorage : window.sessionStorage).setItem(KEY, JSON.stringify(conn));
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
