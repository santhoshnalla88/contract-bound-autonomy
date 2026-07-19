// Typed API client with JWT handling.
// All calls go through `api<T>()`, which attaches the Bearer token, parses
// JSON, and surfaces the FastAPI `detail` message on errors. On a 401 it clears
// the token and notifies AuthContext so the app can bounce to /login.

const TOKEN_KEY = 'gaap_token';

let TOKEN = localStorage.getItem(TOKEN_KEY) ?? '';
let onUnauthorized: (() => void) | null = null;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const getToken = () => TOKEN;
export function setToken(t: string) {
  TOKEN = t;
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  TOKEN = '';
  localStorage.removeItem(TOKEN_KEY);
}
export function setOnUnauthorized(fn: () => void) {
  onUnauthorized = fn;
}

export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
      ...(opts.headers ?? {}),
    },
  });

  if (res.status === 401) {
    clearToken();
    onUnauthorized?.();
    throw new ApiError(401, 'Session expired — please sign in again.');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// EventSource cannot set headers, so the JWT rides as a query param.
export function eventStreamUrl(incidentId: string): string {
  return `/api/incidents/${encodeURIComponent(incidentId)}/events?token=${encodeURIComponent(TOKEN)}`;
}
