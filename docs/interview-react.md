# Interview Guide — React & Frontend (grounded in this codebase)

Deep, interview-ready React knowledge tied to the real `apps/ui/` app **plus** the production wiring you'll add next. Stack: **React 19 · TypeScript · Vite · react-router 7 · Recharts · lucide-react**. Structure per topic: **What → In our code → Why → Interview Q&A**, then a **"Wire it to the backend"** section (fetch, SSE, JWT) — the highest-value learning here.

> **Status:** the UI is **fully wired to the live backend** — real JWT login (`src/auth/AuthContext.tsx`), typed fetch client (`src/lib/api.ts`), real incident list + working "Simulate Incident" submit (`src/pages/Incidents.tsx`), a **live SSE timeline** + working approve/reject (`src/pages/IncidentDetail.tsx`), and real contracts (`src/pages/Contracts.tsx`). The patterns in §8 below are the *actual* implementations — open those files and read along.

---

## 0. The 60-second frontend pitch
> "It's a React 19 + TypeScript SPA built with Vite. A single `<BrowserRouter>` renders a persistent sidebar layout with client-side routes for Dashboard, Incidents, and Contracts. Charts use Recharts, icons are lucide-react, and the design system is CSS custom properties (glassmorphism). Data currently comes from mocks; the production version fetches from the FastAPI API and subscribes to a **Server-Sent Events** stream for live workflow updates, with JWT auth in an `Authorization` header."

---

## 1. Build tooling — Vite + TypeScript project references
**Files:** `vite.config.ts`, `package.json`, `tsconfig*.json`

### In our code
- **Vite** (`@vitejs/plugin-react`) — dev server with HMR + Rollup production build. Scripts: `dev`, `build` (`tsc -b && vite build`), `preview`, `lint` (oxlint).
- **TS project references** — `tsconfig.json` has `"files": []` and references `tsconfig.app.json` (browser code) + `tsconfig.node.json` (Vite config). `tsc -b` builds them as a graph.
- Build output: `dist/` (hashed assets) — served by any static host or by FastAPI.

### Why
- Vite = fast (esbuild dev transform, Rollup prod). Project references keep browser vs. node type environments separate (browser code shouldn't see Node types and vice-versa).

### Interview Q&A
- **Q: Vite vs. Create React App / Webpack?**
  A: Vite uses native ESM + esbuild in dev (no bundling → instant startup/HMR) and Rollup for optimized prod builds. CRA (Webpack) bundles everything up-front — slower cold start.
- **Q: What does `tsc -b` do before `vite build`?**
  A: Type-checks via project references. Vite itself only *transpiles* (strips types, doesn't type-check), so we run `tsc` to catch type errors in CI/build.
- **Q: The 599KB bundle warning — how would you fix it?**
  A: Route-based **code splitting** with `React.lazy(() => import('./pages/Dashboard'))` + `<Suspense>`, and manual chunks for heavy deps (Recharts). Ships less JS on first paint.

---

## 2. React 19 fundamentals (as used)
**Files:** `src/main.tsx`, `src/App.tsx`

### In our code
```tsx
createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>
)
```
- **`createRoot`** — React 18/19 concurrent root API (replaces `ReactDOM.render`).
- **`StrictMode`** — dev-only: double-invokes renders/effects to surface impure logic and unsafe side effects. Ships nothing to prod.
- **Function components + JSX** everywhere; `export default` per page.
- The `!` in `getElementById('root')!` is a **TS non-null assertion** — "trust me, this exists."

### Interview Q&A
- **Q: Why does StrictMode render twice / run effects twice in dev?**
  A: To detect side effects that aren't idempotent and effects that don't clean up. It's dev-only and intentional — if your code breaks under it, your code has a bug (e.g., missing effect cleanup).
- **Q: What changed with React 19?**
  A: Highlights: the new `use()` hook, Actions/`useActionState`, `useOptimistic`, ref-as-a-prop (no more `forwardRef` for many cases), and built-in document metadata. (We use a conservative subset here.)

---

## 3. Client-side routing — react-router 7
**File:** `src/App.tsx`

### In our code
```tsx
<BrowserRouter>
  <AppLayout/>            {/* persistent sidebar */}
</BrowserRouter>

<Routes>
  <Route path="/" element={<Navigate to="/dashboard" replace />} />
  <Route path="/dashboard" element={<Dashboard />} />
  <Route path="/incidents" element={<Incidents />} />
  <Route path="/contracts" element={<Contracts />} />
</Routes>

<NavLink to="/incidents"
  className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
```
- **`BrowserRouter`** uses the History API (clean URLs). **`Routes/Route`** map path → element. **`NavLink`** gives an `isActive` render-prop for styling the current tab. **`<Navigate replace>`** redirects `/` → `/dashboard` without a history entry.
- The layout (`AppLayout`) sits *outside* `<Routes>`, so the sidebar persists while only `<main>` swaps — the classic **persistent shell** pattern.

### Why
- SPA routing = no full-page reloads; instant view swaps; shared layout state preserved.

### Interview Q&A
- **Q: `BrowserRouter` vs `HashRouter`?**
  A: BrowserRouter uses real paths (`/incidents`) via History API — needs the server to serve `index.html` for all routes (SPA fallback). HashRouter uses `#/incidents` — works on dumb static hosts with no fallback config.
- **Q: Why is the redirect `replace`?**
  A: So `/` doesn't land in history; the back button from `/dashboard` doesn't bounce through `/`.
- **Q: How would you protect routes (auth)?**
  A: A `<ProtectedRoute>` wrapper that checks a token from context and renders `<Navigate to="/login">` if absent — see the wiring section.

---

## 4. Component composition & props
**Files:** `src/App.tsx` (`AppLayout`), `src/pages/*`

### In our code
- `App` → `BrowserRouter` → `AppLayout` → (`<aside>` sidebar + `<main>` `<Routes>`). Pages are leaf components returning JSX.
- **Lists + keys:** `MOCK_INCIDENTS.map(inc => <tr key={inc.id}>…)` — the `key` gives React stable identity for efficient reconciliation.
- **Conditional rendering:** `{inc.status === 'PENDING_APPROVAL' && <Clock/>}` and ternaries for the action button.

### Interview Q&A
- **Q: Why `key` on list items, and why not the array index?**
  A: Keys let React match elements across renders (minimal DOM diffing, preserved state). Index keys break when the list reorders/filters — use a stable id.
- **Q: Reconciliation in one sentence?**
  A: React diffs the new element tree against the previous one and mutates only what changed, using keys and element type to decide reuse vs. remount.

---

## 5. Data visualization — Recharts
**File:** `src/pages/Dashboard.tsx`

### In our code
```tsx
<ResponsiveContainer width="100%" height="100%">
  <AreaChart data={data}>
    <defs><linearGradient id="colorResolved">…</linearGradient></defs>
    <CartesianGrid/> <XAxis dataKey="time"/> <YAxis/> <Tooltip/>
    <Area type="monotone" dataKey="resolved" fill="url(#colorResolved)"/>
  </AreaChart>
</ResponsiveContainer>
```
- **`ResponsiveContainer`** makes the chart fluidly fill its parent (needs a sized parent — here `height:300px`).
- Declarative SVG components; `dataKey` maps object fields to axes/series; gradient `<defs>` referenced by `fill="url(#id)"`.

### Interview Q&A
- **Q: Why Recharts over hand-rolled SVG/D3?**
  A: Declarative React components, composable, responsive out of the box; good enough for dashboards. D3 is for bespoke/complex viz where you need full control.
- **Q: Chart not showing?**
  A: 90% of the time `ResponsiveContainer`'s parent has no height. Give the parent an explicit height.

---

## 6. Styling system — CSS custom properties (design tokens)
**Files:** `src/index.css`, `src/App.css`

### In our code
- **Design tokens** in `:root`: `--bg-primary`, `--accent-gradient`, `--status-success/warning/error`, `--radius-*`, `--border-subtle`, `--shadow-glass`. Components reference `var(--…)`.
- **Glassmorphism:** `background: rgba(255,255,255,.03)` + `backdrop-filter: blur(20px)` + subtle border (`.glass-panel`).
- Mix of **CSS classes** (structure/theme) and **inline `style={{}}`** (one-off tweaks).

### Interview Q&A
- **Q: CSS variables vs. a CSS-in-JS lib (styled-components) vs. Tailwind?**
  A: CSS custom properties are zero-runtime, themeable (change `:root`, everything updates), and cascade natively — great for a design system. Tailwind = utility-first speed; CSS-in-JS = colocated dynamic styles at a runtime cost. This app chose plain CSS tokens = simplest, fastest.
- **Q: Downside of inline `style` objects?**
  A: No pseudo-classes/media queries, new object each render (minor), and they win specificity battles awkwardly. Fine for dynamic one-offs; prefer classes for anything reusable.

---

## 7. TypeScript in React
- **Typed data shapes:** define interfaces for API objects (`interface Incident { incident_id: string; status: string; risk_level: string | null; … }`).
- **Typed props:** `function StatCard({ title, value }: { title: string; value: string })`.
- **Event/DOM types:** `React.ChangeEvent<HTMLInputElement>`, non-null assertions (`!`), and render-prop param typing (`({isActive}: {isActive: boolean})`).

### Interview Q&A
- **Q: `type` vs `interface`?**
  A: Both describe object shapes; `interface` is extendable/mergeable (good for public API contracts), `type` does unions/intersections/mapped types. Pick one convention; `interface` for object props is common.
- **Q: How do you type a component's children?**
  A: `{ children: React.ReactNode }`.

---

## 8. ★ Wire it to the backend (the real learning) ★
The API is fully working (JWT + REST + SSE). Here's exactly how to connect the UI. **This is what turns a mock into a product — and the strongest thing to demo/explain.**

### 8.1 Dev proxy (avoid CORS in dev)
```ts
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000', '/health': 'http://localhost:8000' } },
})
```
Now `fetch('/api/...')` from `localhost:5173` is proxied to the API. (The backend also already allows `http://localhost:5173` via CORS.)

### 8.2 A typed API client with JWT
```ts
// src/lib/api.ts
let token = localStorage.getItem('token') ?? '';
export const setToken = (t: string) => { token = t; localStorage.setItem('token', t); };

export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json',
               ...(token ? { Authorization: `Bearer ${token}` } : {}),
               ...opts.headers },
  });
  if (res.status === 401) { /* redirect to login */ }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json() as Promise<T>;
}
```

### 8.3 Login → token
```tsx
const { access_token, role } = await api<{access_token:string; role:string}>(
  '/api/auth/login', { method:'POST', body: JSON.stringify({ email, password }) });
setToken(access_token);
```

### 8.4 Fetching data with `useEffect` + `useState` (or a custom hook)
```tsx
function useIncidents() {
  const [data, setData] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string|null>(null);
  useEffect(() => {
    let cancelled = false;
    api<{incidents: Incident[]}>('/api/incidents')
      .then(r => { if (!cancelled) setData(r.incidents); })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };   // cleanup guards against setState after unmount
  }, []);
  return { data, loading, error };
}
```
Then `const { data, loading } = useIncidents()` replaces `MOCK_INCIDENTS`.

### 8.5 ★ Real-time updates via Server-Sent Events (SSE) ★
The backend streams live workflow events at `GET /api/incidents/{id}/events` (`?token=` because `EventSource` can't set headers).
```tsx
function useIncidentStream(id: string) {
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  useEffect(() => {
    const es = new EventSource(`/api/incidents/${id}/events?token=${encodeURIComponent(token)}`);
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data) as WorkflowEvent;
      setEvents(prev => [...prev, ev]);
      if (ev.terminal) es.close();
    };
    es.onerror = () => es.close();
    return () => es.close();     // cleanup closes the stream on unmount
  }, [id]);
  return events;
}
```

### Interview Q&A (this section wins interviews)
- **Q: SSE vs. WebSockets vs. polling?**
  A: SSE = one-way server→client over plain HTTP, auto-reconnect, simple — perfect for a live event/timeline feed. WebSockets = bidirectional, more setup, needed for chat/collab. Polling wastes requests and adds latency. We stream server→client, so SSE fits.
- **Q: Why can't `EventSource` send an `Authorization` header, and how do you auth it?**
  A: The `EventSource` API has no header option. We pass the JWT as a `?token=` query param (backend accepts header OR query param OR cookie). Trade-off: tokens can leak into logs; acceptable for short-lived JWTs, or use a cookie.
- **Q: Why the cleanup function in `useEffect`?**
  A: It runs on unmount and before re-running the effect. For fetches we set a `cancelled` flag (avoid `setState` on an unmounted component); for SSE/subscriptions we `es.close()` to prevent leaks and duplicate streams. **Missing cleanup = memory leaks + duplicate connections**, and StrictMode's double-invoke will expose it.
- **Q: `useEffect` dependency array?**
  A: `[]` = run once on mount. `[id]` = re-run when `id` changes (and clean up the previous). Omitting it = run every render (usually a bug).
- **Q: Would you add React Query / TanStack Query?**
  A: For anything beyond trivial: yes. It gives caching, dedup, background refetch, and request-state (`isLoading/isError`) for free, replacing hand-rolled `useEffect` fetching. The vision doc lists it as the target.
- **Q: How would you manage auth/user state app-wide?**
  A: `AuthContext` via `createContext` + `useContext`, storing `{token, user, login, logout}`; a `<ProtectedRoute>` reads it. For larger state, Zustand/Redux — but context is enough here.

---

## 9. State & hooks cheat-sheet (rapid fire)
- **`useState`** — local component state; setter triggers re-render. Use functional updates (`setX(prev => …)`) when new state depends on old.
- **`useEffect`** — side effects (fetch, subscriptions, timers) after render; return a cleanup fn; declare deps.
- **`useContext`** — read shared state without prop-drilling.
- **`useMemo` / `useCallback`** — memoize expensive values / stable function identities to avoid needless re-renders/effect re-runs.
- **`useRef`** — mutable value that doesn't trigger re-render (DOM refs, timers, "latest value").
- **Custom hooks** — extract reusable stateful logic (`useIncidents`, `useIncidentStream`); must start with `use`.
- **Rules of hooks** — only call at the top level, only in components/hooks (so React can match calls to state slots across renders).

---

## 10. Performance & correctness talking points
- **Re-render triggers:** state change, prop change, parent re-render, context change. Control with memoization + splitting components.
- **Keys** for lists (stable ids). **Code splitting** with `React.lazy`/`Suspense`. **Avoid new object/array literals** in props of memoized children.
- **Accessibility:** semantic elements (`<nav> <main> <table>`), `aria-*`, keyboard focus. (Current UI leans on `<div>`s + inline styles — an easy improvement to mention.)
- **Error boundaries** for render-time crashes; **loading/empty/error states** for every async view.

---

## 11. What to say about *this* UI honestly
- **Strengths:** React 19 + TS + Vite; routing with a protected persistent shell; **JWT auth via Context**; a typed fetch client with 401 handling; **live Server-Sent Events** timeline; role-gated actions (approve/reject); real design-token system; Recharts driven by live data. Typechecks + builds green; verified against the running API.
- **How data flows:** `AuthProvider` (Context) holds the user + token → `ProtectedRoute` gates routes → pages call `api<T>()` (attaches `Authorization: Bearer`) in `useEffect` → `IncidentDetail` opens an `EventSource` for live updates and cleans it up on unmount → approve/reject POSTs to `/api/approvals/{id}` (gated by `hasRole('approver')`).
- **Remaining polish (name these):** route-level **code splitting** (`React.lazy`) for the 615 KB bundle; adopt **TanStack Query** to replace hand-rolled `useEffect` fetching (caching/dedup/refetch); **a11y** (semantic elements over `div`s); component tests (Vitest + Testing Library).
- **Senior framing:** "The control plane is a typed React SPA wired to the governance API over REST + SSE with Context-based JWT auth and RBAC-gated actions; next I'd add TanStack Query and code-splitting."
