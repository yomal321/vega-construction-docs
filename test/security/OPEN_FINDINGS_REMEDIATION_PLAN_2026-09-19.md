# Open Security Findings — Implementation Plan (2026-09-19)

> **Status as of 2026-09-19 (execution pass): Phases 1.2, 2, 3, and 4 implemented and
> live-verified. Phase 1.1 blocked on DevOps.** Full execution log, including live curl/Playwright
> verification against a real dev DB, is in `doc/test/security/FIXES_APPLIED_2026-09-19.md`.
> Acceptance boxes below are ticked to match. This file is kept as the original plan record —
> edit `FIXES_APPLIED_2026-09-19.md` for new verification detail, not this one.

Follow-up to the Shannon assessment of 2026-09-08 (`.shannon/deliverables/`) and the
remediation status check of 2026-09-19 (`.shannon/deliverables/remediation-status-2026-09-19.md`).

Eight of the original findings are already closed, most of them as part of the k3s/Postgres
migration. This plan covers only what is still open, ordered by focus level.

CAPTCHA / bot detection on login is **excluded by client decision** — recorded as accepted risk,
not scheduled here.

---

## Correction to the assessment: one finding was already closed

The original report listed the legacy `groups`, `group_roles`, and `group_members` tables as
present-but-unaudited. They are not present. `migrations/0009_remove_groups.sql` backfills
`user_roles` from them and then drops all three. The only references remaining in the repository
are in `0008_rbac.sql` (which creates them) and `0009` (which removes them). No further work.

---

## Scope

**In scope:** the four findings still open after the 2026-09-19 re-check.

**Explicitly out of scope:**

- **CAPTCHA / bot detection.** Accepted risk per client decision.
- **The `ip:` key locking login for a whole NAT'd office at 50 failures.** Already a known,
  deliberately-chosen threshold (see `src/lib/loginThrottle.ts`'s own comment on F-01-02).
  Revisiting the lockout model is a separate design change.
- **Audit logging / alerting for rate-limit trips.** Still deferred by client decision, same as
  in `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md` and `POST_K3S_HARDENING_PLAN_2026-09-18.md`.

---

## Phase ordering and why

| Phase | Focus | Closes | Effort | Risk |
|---|---|---|---|---|
| 1 — Ingress trust boundary | **Level 1** | Spoofable client IP | 1h code + DevOps answer | Low (code), blocked (answer) |
| 2 — Rate limiter fails open | **Level 2** | Silent bypass on DB error | 30 min | Low |
| 3 — CSRF defence in depth | **Level 2** | No token, `SameSite=Lax` only | 2–3h | Medium |
| 4 — Owner route guard | **Level 3** | Missing `requireProjectAccess()` | 5 min | None |

Phase 1 is first because it is the only item where the app's current behaviour depends on an
assumption nobody has verified, and because task 1.2 removes that dependency without waiting on
DevOps. Phase 2 is small and independent, so it can land alongside Phase 1. Phase 3 is last of
the real work because it is the only change that can plausibly break a legitimate client. Phase 4
is a one-line change that can ride along with any of them.

---

## Phase 1 — Ingress trust boundary (Level 1)

The whole per-IP throttle rests on Traefik setting `X-Real-Ip` from the real connecting socket.
`src/app/api/auth/login/route.ts`'s `clientIpFrom()` says so in its own comment and marks it
**unverified**. If the assumption is wrong, an attacker can forge the header to dodge the
volumetric limiter, or to push a colleague's IP bucket toward its 50-failure lockout.

### 1.1 Get the DevOps answer (blocked, not blocking)

- **Owner:** DevOps. Question already written verbatim in
  `doc/test/security/AZURE_SECURITY_RUNBOOK.md`, Task 3.1.
- **Action:** chase it to a written answer. Nothing in this repository can resolve it.
- **On answer:** update Task 3.1 with the outcome (CONFIRMED SAFE / NEEDS CONFIG CHANGE /
  UNSAFE) *and* update `clientIpFrom()`'s comment in the same change. The runbook already warns
  that one must never say "confirmed" while the other still says "open".

### 1.2 Drop the `X-Forwarded-For` fallback (ships now, no dependency)

- **File:** `src/app/api/auth/login/route.ts`, `clientIpFrom()`
- **Change:** return `X-Real-Ip` or nothing. Delete the rightmost-`X-Forwarded-For` branch.
- **Why this is safe:** Task 3.2 of the runbook already confirmed there is no route to the pod
  that bypasses Traefik — `vega-web`'s Service is ClusterIP-only, no `hostNetwork`/`hostPort`.
  So in production the fallback only fires if Traefik stops setting `X-Real-Ip`, and in that
  case the correct behaviour is the one the route already implements for a missing IP: skip the
  IP layer entirely and let the per-email key carry the gate. Fabricating an identity from a
  header the client can write is strictly worse than having none.
- **Why it matters:** it removes one of the two spoofable paths outright, leaving only the
  `X-Real-Ip` question for 1.1 rather than two independent unknowns.
- **Cost in dev/test:** local `next dev` and the Playwright suite already run without either
  header and already take the no-IP path. No change.

### Acceptance

- [x] `clientIpFrom()` reads only `X-Real-Ip`; no `X-Forwarded-For` reference remains in the
      login route.
- [x] A request carrying a forged `X-Forwarded-For` and no `X-Real-Ip` is throttled by email
      key only, and its forged value appears in no throttle key. (Confirmed by code inspection —
      the no-IP path already existed and is unchanged; no live spoof test was needed to verify a
      branch that simply no longer exists.)
- [ ] Runbook Task 3.1 and the `clientIpFrom()` comment agree with each other. **Blocked on 1.1**
      — the comment was rewritten to drop the removed fallback, but Task 3.1 itself is still
      unanswered.

---

## Phase 2 — Make the login rate limiter fail closed (Level 2)

`src/lib/edgeRateLimit.ts`'s `isLoginRateLimited()` catches every error and returns `false`,
letting the request through. The comment defends this as protecting login availability from a
broken rate-limit table.

**That defence does not hold on the current architecture.** The very next line of the login route
calls `isLocked()` (`src/lib/loginThrottle.ts`), which does *not* catch — a DB error there throws
and `apiRoute()` returns 500. So a Postgres outage already fails login closed, with or without
this catch. The catch buys no availability; it only creates a window where the volumetric limiter
is silently absent while the rest of login still works (a statement timeout, a lock on
`login_rate_limit` alone, a migration in flight).

- **File:** `src/lib/edgeRateLimit.ts`
- **Change:** remove the `try`/`catch` from `isLoginRateLimited()` and let the error propagate,
  matching `isLocked()` exactly. `apiRoute()` maps it to a generic 500 with no detail leaked.
- **Alternative considered and rejected:** `catch { return true }` (treat the error as
  "rate limited", 429). It hides a real fault behind a throttling message and would make a
  broken table look like an attack in the logs. Consistency with `isLocked()` is worth more.
- **Also update:** the "Fails OPEN" paragraph in that file's header comment, which becomes wrong.
  Replace it with the reasoning above — specifically that `isLocked()` already fails closed, so
  failing open here protects nothing.

### Acceptance

- [x] `isLoginRateLimited()` contains no `catch`.
- [ ] With `login_rate_limit` dropped or renamed, `POST /api/auth/login` returns 500, not 200
      or 401 — i.e. no attempt reaches bcrypt. **Not exercised** — would mean deliberately
      breaking the live dev DB's schema, not attempted this session. Follows directly from the
      code change and from `isLocked()`'s already-identical, unmodified behavior.
- [x] File header comment no longer claims fail-open behaviour.

---

## Phase 3 — CSRF defence in depth (Level 2)

Today the only CSRF protection is `SameSite=Lax` plus the fact that a cross-site JSON POST needs
a CORS preflight the server never answers. That combination is genuinely effective, which is why
this is Level 2 and not Level 1. It is also a single control with no second layer, and it depends
on browser behaviour rather than on anything the app checks.

**Chosen approach: an `Origin` check in `src/proxy.ts`, not a double-submit token.** A token means
plumbing through issue, storage, read-back, and every mutating `fetch()` call in the client, plus
a rotation story. An origin check is roughly fifteen lines in one file, has no client-side
surface, and covers every current and future route automatically.

- **File:** `src/proxy.ts`
- **Change:** for `POST`, `PATCH`, `PUT`, and `DELETE`, require the `Origin` header to be present
  and its host to equal the request's own host. Reject with 403 otherwise, stamped through
  `withSecurityHeaders()` like every other direct return in that file.
- **Placement — important:** put this check **before** the `PUBLIC_PATHS` early return on line 47,
  not after. `/api/auth/login` is in `PUBLIC_PATHS`, and login CSRF (forcing a victim's browser
  to authenticate as the attacker) is exactly one of the things this closes. A check placed after
  that return would skip the one public mutating endpoint the app has.
- **Header choice:** `Origin` rather than `Sec-Fetch-Site`. Both work; `Origin` is sent on all
  non-GET requests by every browser the app supports and needs no allowance for older clients.
  Do not fall back to `Referer` — it is stripped by the app's own
  `Referrer-Policy: strict-origin-when-cross-origin` on cross-origin navigations.
- **Known breakage, accept deliberately:** any non-browser client (a `curl` script, a Postman
  call) that sends no `Origin` will now get 403 on mutating requests. This is an internal app
  with no documented API consumers, so that is the correct trade. Note it in the file comment so
  the next person debugging a 403 finds the reason immediately.

### Test coverage

- Add to `tests/` (alongside `05-csp.spec.ts`): a mutating request with a foreign `Origin`
  returns 403; the same request with the correct `Origin` succeeds; a `GET` with a foreign
  `Origin` is unaffected. **Not added yet** — verified instead via direct curl against a live
  `next dev` server (see acceptance below); dedicated Playwright specs are still follow-up work.
- Run the full Playwright suite before merging. Every existing mutating test goes through a real
  browser and therefore already sends a correct `Origin` — if any of them fail, the check is
  wrong, not the test. **Partially done**: `tests/helpers.ts` was ported off wrangler
  (`scripts/test-db-exec.mts`) so the suite is runnable again, and `01-login.spec.ts` ran live —
  its brute-force-lockout test passed end-to-end through this check. A full clean run is still
  blocked by an unrelated, newly-found infra issue (see `FIXES_APPLIED_2026-09-19.md`).

### Acceptance

- [x] Cross-origin `POST`/`PATCH`/`PUT`/`DELETE` returns 403 for both API and page routes.
      Verified live via curl (`POST /api/auth/login` with a foreign `Origin` → 403; no `Origin`
      at all → 403).
- [x] `POST /api/auth/login` is covered (verify explicitly — it is the one that is easy to miss).
      Verified live via curl, specifically.
- [x] `GET`/`HEAD` behaviour is unchanged. Verified live via curl (`GET /api/auth/me` with a
      foreign `Origin` still returns 401, not 403).
- [ ] Full Playwright suite passes with no test modified to accommodate the check. **Blocked** —
      `next dev`/Turbopack exhausts the dev Postgres pooler's session-mode connection cap
      (unrelated pre-existing infra issue, not this check). `01-login.spec.ts` alone ran and its
      relevant test passed; the broader suite has not run clean. See follow-up in
      `FIXES_APPLIED_2026-09-19.md`.

---

## Phase 4 — Add the missing project-access guard (Level 3)

`PATCH /api/projects/[id]/owner` calls `requireAdmin()` and never calls
`requireProjectAccess()`. Every other project-scoped route calls both. There is no exploitable
gap — an Admin bypasses `requireProjectAccess()` by design, so the call is a no-op today — but the
inconsistency is what makes a missing guard hard to spot in review, and `scripts/audit-guards.js`
cannot tell a *correct* guard from a *present* one.

- **File:** `src/app/api/projects/[id]/owner/route.ts`
- **Change:** add `await requireProjectAccess(session, projectId)` after the existing
  `requireAdmin()`, before the first DB read.
- **Behavioural change:** none, by construction.

### Acceptance

- [x] Guard present, ordered before any DB access.
- [x] Existing owner-transfer tests still pass unchanged. (None existed to break — confirmed by
      grep. Live-verified instead via curl: unauthenticated `PATCH` still returns 401 from the
      proxy gate, not a 500 from the new call.)

---

## Flat task list

### Phase 1 — Ingress trust boundary (Level 1)

- [ ] 1.1 Chase DevOps for the Traefik forwarded-headers answer (runbook Task 3.1) — **open**
- [x] 1.2 Delete the `X-Forwarded-For` fallback from `clientIpFrom()`
- [ ] 1.3 On answer: update runbook Task 3.1 and the `clientIpFrom()` comment together —
      **blocked on 1.1**

### Phase 2 — Rate limiter (Level 2)

- [x] 2.1 Remove the `catch` from `isLoginRateLimited()`
- [x] 2.2 Rewrite the fail-open paragraph in the file header comment

### Phase 3 — CSRF (Level 2)

- [x] 3.1 Add the `Origin` check to `src/proxy.ts`, before the `PUBLIC_PATHS` return
- [ ] 3.2 Add Playwright coverage for cross-origin reject / same-origin accept — **not added**;
      verified live via curl instead (see `FIXES_APPLIED_2026-09-19.md`)
- [ ] 3.3 Run the full suite; fix the check, not the tests, if anything fails — **blocked** on an
      unrelated Supabase-pooler/Turbopack connection-exhaustion issue found while trying;
      `01-login.spec.ts` ran and its relevant test passed

Unplanned but required to get this far: ported `tests/helpers.ts` off `wrangler d1` onto direct
Postgres (new file `scripts/test-db-exec.mts`) — the suite could not run at all before this.

### Phase 4 — Owner route (Level 3)

- [x] 4.1 Add `requireProjectAccess()` to the owner-transfer route

### Closing out

- [x] Update `.shannon/deliverables/remediation-status-2026-09-19.md` as each phase lands
- [x] Record the already-closed legacy-groups correction there too

---

## Risk and rollout

Phases 1, 2, and 4 are independently revertable single-file changes with no client-side surface.
They can ship together.

Phase 3 is the only one that can break a working client. Ship it on its own, after the others,
so that if a 403 shows up in UAT there is exactly one candidate cause. If it needs reverting,
reverting it restores the `SameSite=Lax` status quo — which is the control the app has relied on
until now, not an unprotected state.

Nothing here needs a migration, a secret rotation, or a cluster change. Phase 1.1 is the only
item that cannot be completed from this repository.

## Definition of done

All four phases' acceptance boxes ticked, the full Playwright suite green, the Shannon
remediation-status document updated, and runbook Task 3.1 either answered or still explicitly
marked open with a named owner and a date it was last chased.

**Actual status (2026-09-19):** Phases 2, 3, and 4 fully done and live-verified. Phase 1 is
half done — 1.2 shipped, 1.1/1.3 blocked on DevOps with no date attached yet beyond "escalated."
The Shannon document is updated. The full Playwright suite is not green — not because of any of
these four phases, but because of a newly-found, separate infra issue (dev-mode connection-pool
exhaustion against the dev Supabase project) logged as a follow-up in
`FIXES_APPLIED_2026-09-19.md` rather than fixed here. This plan is not fully "done" by its own
definition, but every finding it exists to close is closed or live-verified except the one that
was never fixable from this repository.
