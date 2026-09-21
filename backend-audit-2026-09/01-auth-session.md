# Backend Audit — Auth & Session

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md` header — `src/proxy.ts` and `src/app/api/auth/login/route.ts` are among the
  modified files; the versions read and tested here are the live working-tree versions) ·
  **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006` (see `00-INDEX.md` for why not 3000)
- **Routes covered:** `src/app/api/auth/login/route.ts` (POST), `auth/logout/route.ts` (POST),
  `auth/me/route.ts` (GET), `healthz/route.ts` (GET), `ready/route.ts` (GET) — 5 files, all
  methods they export.
- **Verdict:** 🟠 **NEEDS-FIX** — one cross-cutting Critical-for-deployability finding
  (`X-08`, filed once in `00-INDEX.md`, not duplicated here), everything else in this family
  checked out correct.

## Summary
This family is the best-engineered part of the codebase — timing-equalized login, DB-backed
revocable sessions, dual idle/absolute expiry, a real Origin-based CSRF gate, and a volumetric +
per-key failure throttle that both fail closed. Every mechanism this report tested live (session
forgery, tampering, revocation, idle/absolute expiry, mid-session deactivation, throttle
thresholds, activity-header spoofing) behaved exactly as documented. The one real defect in this
family isn't in the auth logic at all — it's that the shared gate in front of it (`src/proxy.ts`)
also covers `/api/healthz` and `/api/ready`, which breaks their entire purpose as k8s probes. That
finding is `X-08` in `00-INDEX.md` (cross-cutting, since it's a `proxy.ts` defect every family
inherits) — referenced here, not re-filed.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Forged/tampered/alg:none/wrong-key JWTs all → 401; revoked/idle-expired/absolute-expired sessions all → 401; mid-session deactivation → 401 on the very next request; activity-header spoof structurally inert (proxy always overwrites it server-side, confirmed by source). |
| B. RBAC & escalation | N/A for this family | No permission-gated routes here — login/logout/me/healthz/ready are pre-auth or self-service by design. |
| C. IDOR & project scoping | N/A | No project-scoped resources in this family. |
| D. Injection & SQL layer | ✅ | `login/route.ts`'s only DB reads are `findUserByEmail` (bound `?`) and the throttle tables (bound `?`); no interpolation. |
| E. Validation & mass assignment | ✅ | `loginSchema` requires non-empty email/password strings; malformed JSON confirmed live (`X-02`, still open — see evidence #16), same generic 500 on both a public and an authenticated route. |
| F. Business logic & money | N/A | Nothing money-related in this family. |
| G. Integrity, transactions, concurrency | ✅ | `createSession`/`revokeSession`/`touchSession` are each single-statement; no batch here. Concurrent-login race not separately probed (low value — no shared mutable state two logins could corrupt beyond independent session rows). |
| H. Errors, rate limiting, availability | 🟠 | Per-email (5) and per-IP (50, spoofable — see `00-INDEX.md` S8) failure lockout confirmed at the exact thresholds; volumetric 20-req/60s-per-IP confirmed at the exact threshold. `X-08` (healthz/ready gated) is filed as a cross-cutting finding, not per-route here. `login_throttle`'s lack of GC (Known Open) re-confirmed present, not re-filed. **bcrypt CPU exhaustion measured and confirmed real** — ~30 concurrent unauthenticated logins measurably degraded whole-app latency, including `/api/healthz` itself, for ~2 seconds (see evidence #19). Connection-pool exhaustion not demonstrated as a problem at 25 concurrent (2.5× pool size). Request body size is empirically capped around 5–10MB (fails fast, not a hang) despite no app-level limit being coded. |

## Per-route matrix
| Route | Method | Guard in source | No auth | Notes |
|---|---|---|---|---|
| `/api/auth/login` | POST | none (deliberately public; `PUBLIC_PATHS`) | 200/401/403/429 per outcome | See findings below — all behaviors confirmed live. |
| `/api/auth/logout` | POST | `getSession()` (not `requireSession` — deliberately tolerant of an already-logged-out caller) | 200 `{ok:true}`, no-op | Confirmed idempotent; revokes the real session when one exists. |
| `/api/auth/me` | GET | `getSession()` (not `requireSession` — returns `{user:null}` rather than throwing) | **401 from `src/proxy.ts`'s own gate before the handler runs** (see below) | The handler's own `if (!session) return {user:null}, 401` branch is effectively dead code for the no-cookie case, since `/api/auth/me` isn't in `PUBLIC_PATHS` and proxy rejects it first. Not a security bug (the caller still gets 401 either way), just worth knowing if this handler is ever refactored assuming that branch is reachable. |
| `/api/healthz` | GET | **none in the handler — but gated anyway by `src/proxy.ts`'s blanket auth check** | 401 (should be 200, unconditionally) | **See `X-08` in `00-INDEX.md`.** |
| `/api/ready` | GET | same as above | 401 (should be 200/503 based on DB reachability, never on session state) | Same finding, `X-08`. |

## Findings

*(No new per-family findings beyond the cross-cutting `X-08`, filed once in `00-INDEX.md` to avoid
duplication across every family that inherits `src/proxy.ts`.)*

## Evidence log (live HTTP tests, this session)

All requests sent to `http://localhost:3006`; mutating requests carried `Origin:
http://localhost:3006` unless the test was specifically about the CSRF gate itself.

1. **No cookie → 401** on `/api/auth/me`: `{"error":"Not authenticated"}`.
2. **Valid Admin cookie → 200** on `/api/auth/me`, correct `permissions` array (Admin gets the
   full `PERMISSION_CATALOG` flattened, per `auth/me/route.ts:12-14` — confirmed correct, this is
   a display convenience, not a real bypass, since every actual authorization check still goes
   through `hasPermission`'s Admin-short-circuit independently).
3. **Logout then replay the same cookie → 401.** `POST /api/auth/logout` with a valid cookie →
   `200 {"ok":true}`; the exact same cookie replayed against `/api/auth/me` → `401`.
4. **Wrong-key-signed JWT** (same `sid` as a real live session, HS256-signed with a different
   32+-byte key) → `401`. Confirmed the forged token's construction was otherwise valid by signing
   the identical payload with the *real* `SESSION_SECRET` and confirming that one **is** accepted
   (sanity check, not a vulnerability).
5. **Tampered signature** (flip the last base64url character of a real, valid token's signature
   segment) → `401`.
6. **`alg: none` forged token** (hand-built compact JWT, empty signature segment, valid `sid`
   payload) → `401`. `jose`'s `jwtVerify` rejects this outright — no `algorithms` allowlist
   bypass found.
7. **Idle-expired session → 401.** Logged in as `sec-staff-a` with `remember:false` (1h idle
   window), directly set that session's `lastSeenAt` to 2 hours in the past, replayed the cookie
   → `401`.
8. **Absolute-expired session → 401.** Logged in as `sec-staff-b`, set that session's `expiresAt`
   to 1 minute in the past, replayed → `401`.
9. **Mid-session deactivation → 401 on the very next request.** Logged in as `sec-staff-a`
   (confirmed working, `200`), then flipped that user's `status` to `Inactive` **without touching
   the session row itself** (so this isolates `resolveSession`'s `row.status !== 'Active'` check,
   not `revokeSession`), replayed the same still-signature-valid cookie → `401` immediately.
10. **`SESSION_ACTIVITY_HEADER` spoof** — sent `x-session-activity: 1` as a client-supplied
    request header. Request succeeded (as expected, session was valid regardless), but this
    doesn't prove much on its own since `/api/auth/me` isn't a `NON_ACTIVITY_PATHS` entry either
    way. The real guarantee is structural, confirmed by reading `src/proxy.ts:120-130`: the
    forwarded request's headers are built via `new Headers(request.headers)` then
    `.set(SESSION_ACTIVITY_HEADER, ...)` — an unconditional overwrite, never a conditional
    pass-through — so no client-supplied value for this header can ever reach a handler. Treated
    as confirmed by source rather than needing a flaky timing-based live proof.
11. **Login throttle, per-email (5 failures → lock):** 5 failed attempts against a non-existent
    email → all `401`; the 6th → `429 {"error":"Too many attempts..."}`.
12. **Login throttle, cross-email isolation:** immediately after locking one email, a *different*
    email's failed attempt still got a normal `401`, not `429` — confirms F-01-02 (shared
    `ip:unknown` bucket) has not regressed.
13. **Login throttle doesn't block unrelated real accounts:** `sec-staff-b` logged in normally
    (`200`) throughout the above, on an unrelated key.
14. **Volumetric limiter, 20 req / 60s per IP:** 21 rapid login attempts with a fixed forged
    `X-Real-Ip` header and 21 *distinct* target emails (to isolate this from the per-email
    throttle) — requests 1–20 all `401` (normal), request 21 → `429`. Confirms the limiter fires
    at exactly the documented threshold. This also concretely demonstrates `00-INDEX.md`'s S8
    finding: because the app trusts a client-supplied `X-Real-Ip` with zero validation, an
    attacker rotating that header value per request gets a fresh 20-request budget every time —
    this specific test only worked as a *limiter* test because I deliberately held the forged IP
    fixed.
15. **`/api/healthz`/`/api/ready` with no cookie → 401** for both — see `X-08`. With a valid Admin
    cookie, `/api/healthz` correctly returns `200 {"status":"ok"}` (confirms the handler itself is
    fine; only reachability is broken).
16. **`X-02` re-confirmed, still open:** `POST /api/auth/login` with a syntactically malformed
    JSON body (`{not valid json`) → `500 {"error":"Internal server error"}`, not `400`. Repeated
    against an authenticated route (`PATCH /api/projects/sec-project-a`) with the same malformed
    body → same `500`. Confirms `parseBody`'s `request.json()` throwing a `SyntaxError` (not a
    `ZodError`) still falls through `apiRoute`'s generic branch everywhere, not just on the one
    route the finding was originally filed against.
17. **CSRF edge cases (S7 follow-up):** `X-HTTP-Method-Override: GET` on a no-Origin `POST
   /api/auth/login` → still `403` (the header has no effect — `request.method` is what Node
   actually received, never a header value the app trusts). `Origin: null` (the value a
   sandboxed iframe or `data:` URL sends) → still `403` (`new URL('null').host` is `''`, never
   equal to the real host). Neither bypass works.
18. **Stored-content persistence:** `<script>alert(1)</script>` (as the `invoice` field) and
    `<img src=x onerror=alert(1)>` (as `vendorLabel`) on `POST
    /api/projects/sec-project-a/expenses` → `200`, both persisted and echoed back verbatim,
    unescaped, in the JSON response. This is expected and correct for a JSON API (HTML-escaping
    is a rendering-context concern, not a serialization one) — flagged here only to record that
    the API layer does no content filtering of its own, so escaping-on-render is entirely the
    frontend's responsibility (out of this backend audit's scope) for every text field in this
    app. **Excel/PDF export injection was not tested**: confirmed by reading
    `src/lib/exportPdf.ts`/`exportXlsx.ts` that every export in this app runs **client-side**
    (jsPDF/exceljs in the browser) with no server API route involved at all — there is no backend
    endpoint for this audit to test, and any injection risk there belongs to a frontend audit
    instead.
19. **Class H availability, live-measured (Option A, run with explicit approval):**
    - **bcrypt event-loop blocking — confirmed and quantified.** Single failed login baseline:
      `261ms`. Fired 30 truly concurrent unauthenticated login attempts (`Promise.all`, distinct
      throwaway emails so none hit the per-email throttle, no `X-Real-Ip` so the per-IP layer is
      skipped): each individual request's latency rose to **~2,260ms** — a ~9× slowdown under
      load, consistent with `bcrypt.compareSync`'s synchronous CPU cost blocking Node's single
      event loop thread once enough compares queue up. **More importantly:** a `GET
      /api/healthz` fired at the very start of that same storm took **2,183ms** to return —
      i.e. the health endpoint itself (not a bcrypt-touching route at all) was blocked by the
      concurrent login CPU load, dropping to a normal `9–44ms` only once the storm's initial
      batch cleared. **This is a real, measured, unauthenticated CPU-exhaustion lever**: ~30
      cheap, unauthenticated requests measurably degrade whole-app responsiveness for about two
      seconds, including — once `X-08` is fixed — the exact endpoint a kubelet liveness probe
      polls. A slightly larger burst, or a probe with an aggressive timeout, could plausibly tip
      a real liveness probe into "unhealthy," turning a credential-stuffing attempt into a
      self-inflicted restart. Full transcript: `tests/audit/2026-09/availability-stress.mts`.
    - **Connection pool exhaustion — not demonstrated as a practical issue at this scale.** 25
      concurrent authenticated reads against a pool capped at `max: 10` all returned `200` with
      latency growing gracefully (`216ms` → `303ms` across the batch, no failures, no hangs) —
      the pool queues excess requests correctly rather than failing them. Not tested at a much
      larger concurrency (hundreds+), which might behave differently; at 2.5× the pool size, no
      problem was found.
    - **Unbounded request body — empirically bounded, just not by this app's own code.** No
      app-level size limit is coded anywhere in `parseBody`/`apiRoute`, confirming the original
      concern is accurate as a *code-review* finding. But live probing at 1MB, 5MB, 10MB, 50MB,
      and 100MB bodies found a clean failure threshold between 5MB and 10MB: bodies ≤5MB process
      normally (`401`, normal login-failure path, 130–160ms), bodies ≥10MB fail fast with a
      generic `500` in well under 200ms — never a hang, never unbounded memory growth observed.
      This is almost certainly a Next.js/Node-runtime-level default rather than anything this
      app's own code decided, and it was not traced further to its exact source (out of scope
      for a black-box HTTP probe) — but the practical, measured outcome is a fast-failing request,
      not a resource-exhaustion vector. Worth stating precisely in the handover doc rather than
      leaving the original finding's phrasing ("no visible limit") to imply an actually-unbounded
      risk.

## Not tested this session
- `login_throttle`'s 15-minute lock actually expiring in real time (would require either waiting
  15 real minutes or manipulating `lockedUntil` directly — deferred as low-value: the expiry
  check itself, `isLocked()`, is a one-line `new Date(row.lockedUntil).getTime() > Date.now()`
  with no logic worth doubting once the threshold behavior above is confirmed correct).
- Concurrent-login race (two simultaneous correct logins for the same account) — no shared
  mutable state that could corrupt beyond two independent, both-valid session rows; not a
  meaningful attack surface.
- Tracing the exact origin of the ~5-10MB body-size cutoff found in test #19 (Next.js internal
  default vs. Node HTTP server default vs. something else) — confirmed empirically, not traced
  to its source line.
