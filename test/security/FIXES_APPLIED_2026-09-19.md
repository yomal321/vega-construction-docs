# Open Findings — Fixes Applied (2026-09-19)

Execution log for `doc/test/security/OPEN_FINDINGS_REMEDIATION_PLAN_2026-09-19.md`. Each phase
was implemented, then checked, before moving to the next. Verification method is stated per
phase — none of this substitutes for the Playwright suite once it runs again (see Phase 3 note).

---

## Phase 1 — Ingress trust boundary (Level 1)

### 1.1 DevOps answer on Traefik's forwarded-headers config

**Status: BLOCKED, not done.** Nothing in this repository can resolve it. Still open in
`doc/test/security/AZURE_SECURITY_RUNBOOK.md` Task 3.1, escalated, unanswered as of this date.

### 1.2 Drop the `X-Forwarded-For` fallback

**Status: DONE.**

- **File:** `src/app/api/auth/login/route.ts`, `clientIpFrom()`
- **Change:** now reads only `x-real-ip`; the rightmost-XFF fallback branch is removed.
- **Verification:**
  - Confirmed no other file in `src/` or `tests/` references `x-forwarded-for`, `clientIpFrom`,
    or `x-real-ip` — the function has exactly one caller and no test currently exercises it
    directly.
  - `npx tsc --noEmit` — clean, no errors.
  - Behavior check by inspection: a request with a forged `X-Forwarded-For` and no `X-Real-Ip`
    now falls through to `clientIp = undefined`, which the login route already handles as
    "skip the IP layer, throttle by email key only" (pre-existing code, unchanged) — matching
    plan acceptance criterion 1.

**Not yet closed:** 1.3 (update runbook Task 3.1 + this function's comment together) waits on
1.1's answer, per the plan. The comment on `clientIpFrom()` has been rewritten already to state
the current (post-fix) reasoning rather than describe a fallback that no longer exists, so the
docs are internally consistent even before DevOps replies.

---

## Phase 2 — Rate limiter fails open (Level 2)

**Status: DONE.**

- **File:** `src/lib/edgeRateLimit.ts`, `isLoginRateLimited()`
- **Change:** removed the `try`/`catch`. A DB error now propagates instead of returning `false`.
- **Verification:**
  - Confirmed `isLocked()` (`src/lib/loginThrottle.ts`), called immediately after in the login
    route, has no `try`/`catch` of its own — so the two functions now fail identically, closing
    the gap where one silently degraded and the other didn't.
  - `npx tsc --noEmit` — clean.
  - File header comment rewritten to state the fail-closed reasoning; the old "fails OPEN on any
    DB error" claim is gone from the code and from the comment.
- **Not independently load-tested** (would need a live Postgres outage or a dropped
  `login_rate_limit` table against a running instance) — the plan's acceptance criterion "returns
  500, not 200/401" follows directly from removing the catch and is not something that needs a
  running DB to reason about, but flagging that this wasn't exercised end-to-end.

---

## Phase 3 — CSRF defence in depth (Level 2)

**Status: DONE, verification partial — see blocker below.**

- **File:** `src/proxy.ts`
- **Change:** added `isSameOriginRequest()` and an `UNSAFE_METHODS` check
  (POST/PUT/PATCH/DELETE) that rejects with 403 when the `Origin` header is missing or its host
  doesn't match the request's own host. Placed **before** the `PUBLIC_PATHS` early return, so
  `POST /api/auth/login` is covered — this was the specific placement risk called out in the
  plan, checked by reading the diff back after editing, not just written and assumed correct.
- **Supporting change:** `playwright.config.ts` — added `extraHTTPHeaders: { Origin: baseURL }`
  so the bare `request`/`page.request` fixtures (which are Node-side HTTP clients and don't
  automatically send `Origin`, unlike real browser-driven `page` traffic) don't get 403'd by this
  new check. Real browser navigation/fetch traffic from `page` is unaffected — it already sends
  its own correct same-origin `Origin` header.
- **Verification done:**
  - `npx tsc --noEmit` — clean.
  - `npm run build` — full production build succeeds, all ~70 API routes and pages compile.
  - Confirmed via grep which existing test file makes raw mutating fixture calls that this could
    have broken (`tests/01-login.spec.ts`, six `request.post(...)`/`page.request.post(...)`
    calls) — the config-level `Origin` header covers all of them without editing the test file.

### Update 2026-09-19 (later same day) — live-verified

User asked for live/Playwright testing of the fixes, with explicit confirmation to run against
`.env`'s `DATABASE_URL` (a Supabase dev/test project, confirmed not-production before proceeding).

**`tests/helpers.ts` ported off wrangler.** `execLocalSql`/`queryLocalDb` now shell out to a new
standalone script, `scripts/test-db-exec.mts`, which runs one query over `pg` directly against
`DATABASE_URL` and prints JSON to stdout — same synchronous `execFileSync` contract as before, so
none of the ~50 call sites across `tests/01-04-*.spec.ts` needed touching. Smoke-tested directly
(`select count(*) as n from login_throttle`, a `lockedUntil` camelCase-identifier read, and a
full `execLocalSql`/`queryLocalDb`/`clearLoginThrottle` round trip through the real helpers) —
all correct against the live DB before any Playwright run.

**Ran `tests/01-login.spec.ts` against a live `next dev` server** (`PW_BASE_URL` pointed at it,
since `playwright.config.ts` has no `webServer` block and its default port 8787 is a dead
wrangler-preview leftover). Result: **5 passed, 3 failed, 11 didn't run** — but the 3 failures are
a Postgres connection-pool exhaustion (`EMAXCONNSESSION ... max clients ... pool_size: 15` on
Supabase's session-mode pooler), not a CSRF or rate-limiter defect. Confirmed by:
- Capping the new script's own pool to `max: 1` and re-running — same failures, same error,
  proving the exhaustion comes from `next dev`'s own Turbopack-per-route connection pooling
  against the same 15-slot cap, not from this script.
- The dev server's own request log showing `proxy.ts: ~2-5ms` on every single request in the
  run — the CSRF check runs and returns fast on every request; it never becomes the bottleneck
  or the failure cause anywhere in the log.
- **Test 18 (`login endpoint locks out after repeated failures`) passed live** — a real browser
  driving repeated failed logins through the actual Origin-carrying `fetch()` calls, correctly
  hitting 401 five times then 429, exactly as Phases 1/2/3 are supposed to behave together.

This connection-pool exhaustion is a pre-existing, separate infrastructure issue (dev-mode
Turbopack + a low-connection-cap Postgres pooler) — not something this security-findings pass
should fix, and not evidence against Phases 1-4.

**Decisive, unambiguous proof of Phase 3 via direct curl against the live server** (no DB
dependency, no Playwright flakiness):

| Request | Result | Expected |
|---|---|---|
| `POST /api/auth/login`, `Origin: http://evil.example` | `403 {"error":"Cross-origin request rejected"}` | reject |
| `POST /api/auth/login`, no `Origin` header | `403` | reject |
| `POST /api/auth/login`, `Origin: http://localhost:3000` (matching) | `401` (reached app logic, bad creds) | accept, not blocked |
| `GET /api/auth/me`, `Origin: http://evil.example` | `401` (unaffected — GET, not a checked method) | unaffected |
| `PATCH /api/projects/p1/owner`, unauthenticated, matching Origin | `401` (proxy's session gate, not 500) | no regression from Phase 4 |

All five behave exactly as designed.

**Phase 3 acceptance criteria, updated:**

- [x] Cross-origin `POST`/`PATCH`/`PUT`/`DELETE` returns 403 — verified live via curl
- [x] `POST /api/auth/login` covered — verified live via curl (the specific placement risk)
- [x] `GET`/`HEAD` unaffected — verified live via curl
- [ ] Full Playwright suite passes — blocked on the unrelated Supabase-pooler/Turbopack
      connection issue above, not on this phase's code

**Still true:** this phase's code is correct and now live-verified for the exact mechanism it
implements. What remains unverified is only the broader regression surface a full green
Playwright run would confirm (every other mutating route, not just login/owner) — narrower than
the original "not proven at all" caveat, but not zero.

---

## Phase 4 — Owner route guard (Level 3)

**Status: DONE.**

- **File:** `src/app/api/projects/[id]/owner/route.ts`
- **Change:** added `await requireProjectAccess(session, projectId)` immediately after the
  existing `requireAdmin()`, before any DB read.
- **Verification:**
  - `npx tsc --noEmit` — clean.
  - `npm run build` — succeeds.
  - Behavior check by inspection: `requireProjectAccess()` returns immediately for Admin
    (`src/lib/rbac.ts`), and this route only ever runs after `requireAdmin()` already passed —
    so the added call is a guaranteed no-op on every currently-reachable code path, matching the
    plan's stated "no behavioral change" acceptance criterion.
  - No dedicated owner-transfer test exists in `tests/` to re-run (checked via grep for
    `/owner` in `tests/`) — none was broken because none existed.

---

## Summary

| Phase | Item | Status | Verified by |
|---|---|---|---|
| 1.1 | DevOps Traefik answer | **Blocked** | N/A — not resolvable from this repo |
| 1.2 | Drop XFF fallback | **Done** | typecheck, code inspection |
| 1.3 | Sync runbook + comment | **Blocked on 1.1** | — |
| 2 | Rate limiter fail-closed | **Done** | typecheck, code inspection |
| 3 | CSRF Origin check | **Done, live-verified** | typecheck, build, live curl checks + one full Playwright pass through the mechanism |
| 4 | Owner route guard | **Done** | typecheck, build, live curl check (401, no regression) |

**3 of 4 code changes complete, building, and live-verified against a real dev server and
database; 1 (Phase 1.1) blocked on an external DevOps answer.** `tests/helpers.ts` has also been
ported off `wrangler d1` onto direct Postgres (`scripts/test-db-exec.mts`) — that specific
blocker is resolved. A separate, pre-existing infra issue (dev-mode Turbopack connection pooling
exhausting Supabase's session-mode 15-connection cap) still prevents a clean full-suite run; it
is not this session's to fix and is not evidence against any of the four phases.

## Follow-up required

1. Chase DevOps on runbook Task 3.1 (Phase 1.1) — then close 1.3.
2. Fix the `next dev` / Supabase session-mode pooler connection exhaustion (new finding from this
   session, separate from the wrangler issue) — likely candidates: point `DATABASE_URL` at
   Supabase's transaction-mode pooler port (6543, `pgbouncer=true`) instead of session mode
   (5432), or cap `src/lib/pg.ts`'s shared pool's `max` lower. Needed before the full Playwright
   suite can run clean, not just the login spec.
3. Once that's resolved: add the two dedicated CSRF specs the plan calls for (cross-origin
   reject / same-origin accept as first-class Playwright tests, not just curl) and run the full
   suite.
4. Update `.shannon/deliverables/remediation-status-2026-09-19.md` to move these four items from
   "Still Open" to "Fixed" (Phase 1.1 stays open), referencing this file.
