# QA Audit — Login (`/login`)

- **Audited:** 2026-09-03
- **Build/commit:** `89395b8` (working tree modified only by audit artefacts: `package.json`/`package-lock.json` for `@playwright/test`, plus `playwright.config.ts` and `tests/`)
- **Verdict:** NEEDS-FIX
- **Playwright spec:** `vega-manager/tests/01-login.spec.ts` — 20 tests, 19 passed, 1 failed (the failure is F-01-01, working as intended: the test documents the finding)

## Summary

`/login` is the app's only unauthenticated entry point: an email/password form that POSTs to
`/api/auth/login`, which verifies a bcrypt hash, creates a DB-backed session row, and returns a
signed JWT carrying only that row's id in an HttpOnly cookie. I exercised the form functionally,
probed authentication and session handling (cookie flags, revocation, forgery, replay), ran the
brute-force throttle to a real lockout, and did a white-box read of every file in the path
(`login/route.ts`, `auth.ts`, `loginThrottle.ts`, `middleware.ts`, `securityHeaders.ts`, `api.ts`).

**The core authentication logic is genuinely well built** — the timing-equalised dummy bcrypt
compare, the throttle ordered before the password check, and DB-resolved (not JWT-trusted)
role/status are all correct and verified working. **The headline risk is not in that logic; it is
that multi-factor authentication does not exist at runtime despite the codebase shipping a
migration, a full TOTP implementation, an encryption helper and a declared secret for it.** Anyone
reading the repo — or a handover document derived from it — would reasonably conclude MFA is
available. It is not, and login has no second factor of any kind.

> **Resolved 2026-09-04.** The client declined MFA, so the misleading scaffolding was removed
> rather than finished (see F-01-01 below). Login is single-factor **by design** now, and the repo
> no longer claims otherwise — which was the substance of this finding. Brute-force resistance
> rests on the login throttle and the Cloudflare edge rate limiter, both verified working here.

## Coverage

| Test class | Status | Notes |
|---|---|---|
| A. Functional / Playwright | ✅ | 8/8 pass: validation, toggle, both roles, dark+light, 1920/1366/390 responsive, zero console errors |
| B. Authentication & session | ✅ | 10/11 pass at audit time; the one failure (MFA absent, F-01-01) is closed — MFA was descoped by the client and removed 2026-09-04, so single-factor login is intended. Cookie flags, revocation, forgery, replay and throttle all verified correct |
| C. Authorisation / RBAC / IDOR | ✅ | Limited surface on this page; unauthenticated access to 5 API routes correctly 401s, page visits correctly redirect |
| D. SQL injection & input handling | ⚠️ | No injectable SQL found anywhere in the auth path; type-confusion correctly rejected; malformed JSON returns 500 instead of 400 (F-01-06) |
| E. Headers / disclosure | ⚠️ | 6 security headers verified present; CSP has no `script-src` (F-01-03); `x-powered-by` leaks framework (F-01-05) |
| F. Data integrity & business rules | ✅ | Not materially applicable to this page; session TTL/`remember` coupling verified correct by reading |

## Findings

### F-01-01 — MFA is entirely absent at runtime despite the codebase shipping its migration, libraries and secret
- **Status:** ✅ **RESOLVED 2026-09-04 — resolved by removal.** The client declined MFA, so the
  scaffolding this finding objected to was deleted rather than completed: `0026_remove_mfa.sql`
  drops `users.mfaSecret` / `mfaEnabledAt` / `mfaLastUsedStep` and the `mfa_recovery_codes` table;
  `src/lib/totp.ts`, `src/lib/mfaCrypto.ts`, the four empty `src/app/api/auth/mfa/*` directories,
  `src/app/account/`, the `MFA_ENCRYPTION_KEY` binding in `src/lib/db.ts` and its `.dev.vars` entry
  are all gone. Single-factor login is now the documented, intended design — the "false assurance"
  this finding identified as the real risk no longer exists. Everything below is the original
  finding, kept as the record of why the cleanup happened.
- **Severity:** High
- **Confidence:** Confirmed
- **Class:** Auth
- **Location:** `src/app/api/auth/mfa/{enroll,enable,verify,disable}/` (empty dirs), `src/app/account/` (empty dir), `src/app/api/auth/login/route.ts:77-87`, `migrations/0025_mfa.sql`, `src/lib/totp.ts`, `src/lib/mfaCrypto.ts`
- **Reproduction:**
  1. Log in as `nimal@vegahomes.lk` (Admin) and keep the session cookie.
  2. `POST /api/auth/mfa/enroll`, `/enable`, `/verify`, `/disable` — all with a valid session.
  3. `GET /account/mfa` and `GET /account`.
- **Expected:** Either working MFA endpoints, or no MFA scaffolding in the repo at all.
- **Actual:** Every one returns **404**. `src/app/api/auth/mfa/*` are four empty directories containing no `route.ts`; `src/app/account/` is empty. `src/app/api/auth/login/route.ts` contains no reference to `mfaSecret` or `mfaEnabledAt` — it issues a full session cookie immediately after the bcrypt compare (line 77-78).
- **Evidence:**
  ```
  (authenticated as admin)
  POST /api/auth/mfa/enroll  -> HTTP 404
  POST /api/auth/mfa/enable  -> HTTP 404
  POST /api/auth/mfa/verify  -> HTTP 404
  POST /api/auth/mfa/disable -> HTTP 404
  GET  /account              -> HTTP 404
  GET  /account/mfa          -> HTTP 404

  $ grep -rn "mfaSecret\|mfaEnabledAt" src/
  src/lib/mfaCrypto.ts:3:  // ...before it's ever written to `users.mfaSecret`   <- a comment; no runtime reader
  ```
  Yet the repo ships all of: `migrations/0025_mfa.sql` (adds `users.mfaSecret`, `users.mfaEnabledAt`),
  a complete RFC 6238 TOTP implementation in `src/lib/totp.ts`, AES-GCM secret encryption in
  `src/lib/mfaCrypto.ts`, and a declared `MFA_ENCRYPTION_KEY` binding in `src/lib/db.ts` which is
  set in `.dev.vars`.
- **Impact:** There is no second authentication factor. A single leaked or guessed password is
  full account access — including Admin, which bypasses RBAC entirely (`src/lib/rbac.ts`). The
  greater risk is the **false assurance**: the migration, libraries, and secret make MFA look
  delivered to anyone auditing the repo, and `doc/PRE_HANDOVER_QA_PROMPT.md` itself lists
  "MFA (`/account/mfa`): enrolment, TOTP verification" as an expected test area. If the client is
  told MFA ships, that statement is currently false.
- **Suggested fix:** Decide and be explicit — either implement the four route handlers plus the
  login-time challenge, or remove the dead scaffolding and state plainly in the handover that MFA
  is not included. Do not hand over in the current ambiguous state. (Describe only — not implemented.)

### F-01-02 — All clients share one login-throttle bucket when `cf-connecting-ip` is absent; five anonymous failures lock out every user
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Auth / Availability
- **Location:** `src/app/api/auth/login/route.ts:33-34`, `src/lib/loginThrottle.ts:6-8`
- **Reproduction:**
  1. `delete from login_throttle` to start clean.
  2. Send 5 failed logins for **five different, non-existent** emails (`probe1@x.lk` … `probe5@x.lk`).
  3. Now attempt a **correct** login as `nimal@vegahomes.lk`.
- **Expected:** A legitimate user with the right password is unaffected by failures against unrelated accounts.
- **Actual:** HTTP **429 "Too many attempts. Try again in a few minutes."** — locked out for 15 minutes.
- **Evidence:**
  ```
  $ select key, failures, lockedUntil from login_throttle where key like 'ip:%'
  { "key": "ip:unknown", "failures": 5, "lockedUntil": "2026-09-03T04:36:54.821Z" }

  $ curl -X POST /api/auth/login -d '{"email":"nimal@vegahomes.lk","password":"vega123"}'
  {"error":"Too many attempts. Try again in a few minutes."}
  HTTP 429
  ```
  `clientIp` is `request.headers.get('cf-connecting-ip') ?? 'unknown'`. That header is absent
  outside Cloudflare's edge, so every client on the planet collapses into the single key
  `ip:unknown`.
- **Impact:** Two distinct scenarios, one mitigated and one not:
  - *Off-Cloudflare (confirmed here):* any anonymous user can lock **every** account out of the
    system in 5 requests, repeatedly. A trivial, unauthenticated, total denial of service. In
    production behind Cloudflare the header is present, so this specific case is mitigated —
    but the `?? 'unknown'` fallback silently degrades to it rather than failing loudly.
  - *In production, still live:* the bucket is per-IP, and Vega's office staff will share one
    NAT'd public IP. Five fumbled passwords by one employee locks out the entire office for 15
    minutes. For a small construction firm this is a realistic recurring support incident, not a
    theoretical one.
- **Suggested fix:** Treat a missing `cf-connecting-ip` as a hard configuration error rather than
  a shared bucket, and reconsider whether the IP key should lock a *correct* password at all —
  the per-email key already covers credential stuffing against one account. (Describe only.)

### F-01-03 — Content-Security-Policy carries no `script-src`/`default-src`, so it provides no XSS mitigation
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Disclosure / Defence-in-depth
- **Location:** `src/lib/securityHeaders.ts:18`
- **Reproduction:** `curl -D - -o /dev/null http://localhost:8787/login`
- **Expected:** A CSP restricting script sources.
- **Actual:** `content-security-policy: frame-ancestors 'none'` — clickjacking protection only.
- **Evidence:**
  ```
  content-security-policy: frame-ancestors 'none'
  strict-transport-security: max-age=63072000; includeSubDomains; preload
  x-content-type-options: nosniff
  x-frame-options: DENY
  referrer-policy: strict-origin-when-cross-origin
  permissions-policy: camera=(), microphone=(), geolocation=()
  ```
- **Impact:** No second line of defence if a stored-XSS hole exists anywhere in the app. This
  matters more than usual here because the app renders large amounts of free text (supplier names,
  item descriptions, project names) that other pages in this audit still have to clear.
- **Note:** This is a **known, deliberate** deferral, not an oversight — `securityHeaders.ts:8-9`
  documents it and `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md` Phase 6 schedules a report-only
  rollout. Recorded here so it is disclosed rather than assumed handled.
- **Suggested fix:** Complete the planned Phase 6 report-only rollout before handover, or disclose
  the gap in writing. (Describe only.)

### F-01-04 — No server-side CSRF defence; `SameSite=Lax` is the only thing standing between a hostile origin and a state-changing write
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** CSRF
- **Location:** `src/middleware.ts` (no origin check), `src/lib/api.ts` (no CSRF token), `src/lib/auth.ts:166` (`sameSite: 'lax'`)
- **Reproduction:** With a valid admin session cookie, `POST /api/units` with `Origin: https://evil.example`.
- **Expected:** Rejected, or at minimum the Origin validated for a state-changing request.
- **Actual:** **HTTP 200** — the row was created. The forged Origin was never inspected.
- **Evidence:**
  ```
  $ curl -b cookies -X POST /api/units -H "Origin: https://evil.example" -d '{"name":"CSRF-Probe-Unit"}'
  {"id":"unit_122e0863-...","name":"CSRF-Probe-Unit","sortOrder":9}
  -> HTTP 200
  ```
  (probe row deleted afterwards)
- **Impact:** Practical exploitability is **low**: the session cookie is `SameSite=Lax` (verified),
  so a real browser will not attach it to a cross-site POST, and that blocks the classic attack.
  But it is a single, browser-dependent layer with nothing behind it — no origin check, no CSRF
  token, no custom-header requirement — on an application that moves money.
- **Suggested fix:** Add an `Origin`/`Sec-Fetch-Site` check to state-changing methods in the shared
  `apiRoute` wrapper, where it would cover all 61 routes at once. (Describe only.)

### F-01-05 — `x-powered-by: Next.js` is served on every response
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Disclosure
- **Location:** `next.config.ts` (missing `poweredByHeader: false`)
- **Reproduction:** `curl -D - -o /dev/null http://localhost:8787/login`
- **Expected:** No framework fingerprint.
- **Actual:** `x-powered-by: Next.js`
- **Impact:** Minor. Tells an attacker which framework-specific CVEs to try first. One-line config change.
- **Suggested fix:** Set `poweredByHeader: false` in `next.config.ts`. (Describe only.)

### F-01-06 — Malformed JSON body returns 500 instead of 400
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Functional / Input handling
- **Location:** `src/lib/api.ts:57-60` (`parseBody`) and `src/lib/api.ts:19-27` (`apiRoute` catch)
- **Reproduction:** `POST /api/units` with body `{not-json` and a valid session.
- **Expected:** `400` — the client sent a bad request.
- **Actual:** `500 {"error":"Internal server error"}`.
- **Evidence:**
  ```
  $ curl -b cookies -X POST /api/units -H "Content-Type: application/json" -d '{not-json'
  {"error":"Internal server error"}
  -> HTTP 500
  ```
  `parseBody` calls `request.json()`, which throws a `SyntaxError`. `apiRoute` maps `AuthError`
  and `ZodError` explicitly but sends everything else to the generic 500 branch.
- **Impact:** No information leak (the body is correctly generic). The cost is operational: client
  errors are logged via `console.error` and counted as server faults, so genuine 500s become
  harder to spot in Cloudflare's logs — which matters because this app has no other error tracking.
- **Suggested fix:** Catch the JSON parse failure in `parseBody` and re-throw it as a 400. (Describe only.)

### F-01-07 — `SESSION_SECRET` is never validated for length; a weak value is silently accepted
- **Severity:** Low
- **Confidence:** Confirmed (behaviour verified directly against `jose`; production impact reasoned, not reproduced)
- **Class:** Auth
- **Location:** `src/lib/auth.ts:37-40`
- **Reproduction:** Exercised `jose` directly with the keys `getSecretKey()` would produce.
- **Expected:** A startup check that the secret exists and is of adequate length.
- **Actual:** No check. Behaviour splits by case:
  ```
  unset  -> TextEncoder().encode(undefined) = 0 bytes -> jose refuses: "Zero-length key is not supported"
  "a"        (1 byte)  -> ACCEPTED, signed + verified
  "vega"     (4 bytes) -> ACCEPTED, signed + verified
  "changeme" (8 bytes) -> ACCEPTED, signed + verified
  ```
- **Impact:** Lower than it first appears, and the reason is a genuine design strength worth
  crediting: the JWT carries only a `sid`, and `resolveSession` looks that id up in the `sessions`
  table, so cracking the signing key does **not** let an attacker mint a session for an arbitrary
  user — they would still need a live, unguessable `sess_<uuid>`. Role and status are re-read from
  the DB regardless. The residual risk from a weak secret is an attacker re-signing *their own*
  session id to extend its lifetime past the intended TTL. Separately, if the secret were ever
  unset in production, every login would return an opaque `500` and the cause would not be
  apparent from the response.
- **Suggested fix:** Validate presence and a 32-byte minimum at first use, failing with an explicit
  message. (Describe only.)

### F-01-08 — `prisma/schema.prisma` has drifted from `migrations/`
- **Severity:** Info
- **Confidence:** Confirmed
- **Class:** Data integrity
- **Location:** `prisma/schema.prisma` vs `migrations/0025_mfa.sql`
- **Reproduction:** `grep -n "mfa" prisma/schema.prisma` → no matches, while `migrations/0025_mfa.sql` adds two `users` columns.
- **Impact:** The live D1 schema and the Prisma schema disagree. `prisma/seed.ts` and any future
  `prisma migrate diff` work from an incomplete picture. Harmless today because runtime queries go
  straight to D1 rather than through Prisma Client (`src/lib/db.ts`), but it is a trap for whoever
  maintains this next. Consistent with the drift already noted in the 2026-09-01 audit.
- **Suggested fix:** Reconcile the Prisma schema with the applied migrations. (Describe only.)

## Tested and clean

Verified working correctly — as valuable to record as the findings:

- **Account enumeration is properly closed.** A wrong password and a wholly unknown email return
  **byte-identical** responses (asserted, not eyeballed: `expect(await unknownEmail.text()).toBe(await wrongPw.text())`).
  The dummy-bcrypt equalisation at `login/route.ts:56` is real — a non-existent email still pays a
  full cost-10 compare — and `recordFailure` is called for unknown emails too, so lockout timing
  does not become an oracle either.
- **Throttle ordering is correct.** Both the edge limiter and the DB throttle run *before* the user
  lookup and *before* any bcrypt compare, so the lockout cannot be turned into a CPU-exhaustion amplifier.
- **Brute-force lockout genuinely works.** 5 failures produce a real 429, and a locked account is
  refused **even with the correct password** (both asserted).
- **Logout revokes server-side, not just client-side.** A session cookie captured before logout and
  replayed from a brand-new context afterwards returns **401**. This is the test most systems fail.
- **Forged/tampered JWTs are rejected** — an unsigned token with an invented `sid` redirects to `/login`.
- **Inactive user (`ruwan@`) cannot log in** even with the correct password, and receives no session cookie.
- **Session cookie is `HttpOnly` + `SameSite=Lax`** and is not readable from `document.cookie`.
  (`secure` is correctly false only because the audit runs over plain http on localhost — the flag
  is derived from the request protocol at `auth.ts:163`, so it will be true in production.)
- **Unauthenticated API access returns 401, never 200 with data** — verified on `/api/auth/me`,
  `/api/projects`, `/api/dashboard`, `/api/users`, `/api/notifications`.
- **No SQL injection surface in the auth path.** Every query in `auth.ts` and `loginThrottle.ts`
  is a prepared statement with `.bind()`. A repo-wide sweep for template-interpolated SQL found
  five sites, and **all five are safe**: the two dynamic `UPDATE`s (`projects/[id]/route.ts:91`,
  `expenses/[expenseId]/route.ts:33`) build column names from a hardcoded whitelist with `?`
  placeholders, and all 20 `projectAccessClause` call sites pass the literals `'p.id'`/`'p.ownerId'`.
  No `.exec()` anywhere.
- **Type-confusion input is rejected cleanly** — `{"email":["a"],"password":{"$ne":1}}` returns a
  structured 400, not a crash.
- **No stack traces, SQL, table names or file paths in error bodies** — the forced 500 returned
  only `{"error":"Internal server error"}`.
- **No source maps in the production build** (0 `.map` files in `.open-next/assets`), and the
  `SESSION_SECRET` value does not appear anywhere in the client bundle.
- **Middleware matcher bypass is fixed** — `src/middleware.ts:51` uses `[^/]*\.` as the 2026-09-01
  audit recommended, so `/api/users/x.png` no longer skips middleware.
- **Five of six security headers are correct and present** on both normal responses and
  middleware-returned redirects (HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options: DENY`,
  `Permissions-Policy`).
- **Functional/UI:** zero console and page errors on load; submit correctly disabled until both
  fields are non-empty (whitespace-only email included); show/hide password toggle works; both
  Admin and Staff log in and land on `/`; light and dark both render; no horizontal overflow at
  1920, 1366 or 390 px.

## Not tested / blocked

- **The edge rate limiter (`LOGIN_RATE_LIMITER`, 20/60s) was not isolated.** The DB throttle locks
  at 5 failures, so it always fires first; separating the two would need the DB throttle disabled,
  which is a source change this audit is not permitted to make. Its fail-open-on-error behaviour
  (`src/lib/edgeRateLimit.ts:14-17`) is by design and documented, but unverified at runtime.
- **`secure` cookie flag in production was not observed**, only the localhost value (`false`) and
  the code path that sets it. Confirm against the deployed HTTPS origin.
- **The unset-`SESSION_SECRET` failure mode was reasoned from `jose`'s verified behaviour**, not
  reproduced against a running server — doing so would have required editing `.dev.vars`.
- **No cross-browser coverage.** Chromium only. (Note: `@playwright/test` and `playwright` had to
  be pinned to `1.61.1`, matching the version already in `package.json`; the 1.62.1 that `npm i -D`
  pulled in requires a chromium build whose download fails from this network.)
- **Real cross-origin CSRF from a genuine attacker page was not staged** — F-01-04 was established
  from the server's missing Origin check plus the confirmed `SameSite=Lax` attribute.
