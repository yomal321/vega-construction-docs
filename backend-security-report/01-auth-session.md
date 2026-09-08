# Backend Security Audit — Auth & Session

- **Audited:** 2026-09-05
- **Routes covered:** `api/auth/login/route.ts` (POST), `api/auth/logout/route.ts` (POST), `api/auth/me/route.ts` (GET). Supporting code exercised through them: `src/middleware.ts`, `src/lib/auth.ts`, `src/lib/rbac.ts`, `src/lib/loginThrottle.ts`, `src/lib/edgeRateLimit.ts`, `src/lib/password.ts`, `src/lib/securityHeaders.ts`, `src/lib/api.ts`.
- **Build/commit:** `41abc80`, clean working tree (audit harness under `vega-manager/tests/audit/` added by this audit and untracked at time of writing)
- **Test rig:** `wrangler dev` on the OpenNext build, `http://127.0.0.1:8787`, local D1 only. Harness: `vega-manager/tests/audit/01-auth-session.mjs` (+ `lib.mjs`). Final run: **50 pass · 0 fail · 10 info**.
- **Verdict:** PASS-WITH-NOTES

## Summary

These three routes are the entire authentication surface: they issue, read and destroy the only
credential the app has. The design is stronger than the norm for an app this size — the JWT is
deliberately not self-sufficient (it carries only a session id, with role and status re-read from
the database on every single request), sessions are genuinely revocable server-side, and the login
path is hardened against account enumeration by both a constant-cost bcrypt compare and a throttle
that records failures for non-existent emails.

I probed all three routes at the HTTP layer across test classes A, B, D, F and G (C and E do not
apply — no project-scoped identifiers, no money). **No new authentication or authorisation defect
was found.** Every credential-forgery attempt was refused: tampered signatures, `alg:none`
downgrades carrying a genuine live session id, tokens signed with an attacker-chosen key, and
replayed cookies from logged-out, deactivated, demoted, password-reset and deleted accounts. All
eight SQL-injection payloads against both login fields returned the same generic 401 and left the
`users` table intact at five rows.

The headline risk is **not** in these handlers. It is the two known-open cross-cutting gaps that
this family is simply where they become visible: there is **no CSRF defence beyond `SameSite=Lax`**
(B-01-01), and the CSP carries no `script-src`, so it provides no XSS mitigation at all (B-01-02).
Both were already known before this audit; both are confirmed still present, and neither has become
worse. One genuinely new item: the seeded demo password `vega123` is rejected by the application's
own password policy, so the credentials the client is handed cannot be rotated through the product's
own UI (B-01-03).

## Coverage

| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | 17 probes. No-cookie, tampered signature, `alg:none`, wrong-key HS256, garbage cookie, logout replay, inactive login, mid-session deactivation, cookie attributes. All correct. |
| B. RBAC | ✅ | 9 probes. `/api/auth/me` correctly exposes only the caller's own identity and effective permissions. Staff self-promotion, role creation and permission-catalog reads all refused 403. |
| C. IDOR & project scoping | n/a | No project-scoped identifiers in this family. Covered from family 2 onward. |
| D. Input validation & injection | ✅ | 9 probes. 8 SQLi payloads × 2 fields, 12 type-confusion shapes, mass assignment, 100 KB inputs. One known-open item confirmed (malformed JSON → 500). |
| E. Business logic & money | n/a | No money-bearing fields in this family. |
| F. Data integrity | ✅ | 6 probes. Full five-path session-revocation matrix, FK cascade on user delete, login-time sweep of expired sessions. |
| G. Errors, disclosure, rate limiting | ⚠️ | 19 probes. Headers, error-body genericity, timing oracle, throttle behaviour all correct. **CSRF and CSP remain open** (both pre-existing and known). |

## Per-route matrix

| Route | Method | Guard in source | No-auth | Zero-perm Staff | Forged/replayed token | Verdict |
|---|---|---|---|---|---|---|
| `/api/auth/login` | POST | public by design (`PUBLIC_PATHS`, `ALLOWED_PUBLIC`) | 200/401 as credentials warrant | n/a | n/a | ✅ |
| `/api/auth/login` | GET | — | 405 | — | — | ✅ |
| `/api/auth/logout` | POST | `getSession()`, middleware-gated (not in `PUBLIC_PATHS`) | 401 | 200 (own session only) | 401 | ✅ |
| `/api/auth/me` | GET | `getSession()` — identity read, intentionally open to any session | 401 | 200, own identity only | 401 | ✅ |
| `/api/auth/me` | DELETE | — | 405 | — | — | ✅ |

Cross-checked against `PERMISSION_CATALOG`: none of these three routes should carry a module
permission, and none does. `/api/auth/me` returning 200 for a zero-permission Staff user is correct
— it returns that user's own name, email, role and (empty) permission list, which is precisely what
the client shell needs to render a "you have no access" state.

## Findings

### B-01-01 — No CSRF defence on state-changing routes beyond `SameSite=Lax`
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** CSRF
- **Status:** Known-open (`X-01` / `F-01-04`) — **still present, not worse**
- **Location:** `src/middleware.ts:18-45`, `src/lib/auth.ts:191-202`
- **Request:**
  ```
  POST /api/auth/logout HTTP/1.1
  Cookie: vega_session=<valid admin session>
  Origin: https://evil.example.com
  Referer: https://evil.example.com/
  ```
- **Expected:** 403 — a state-changing request whose `Origin` is a foreign site should be refused.
- **Actual:** `200 {"ok":true}`. The session was revoked server-side. The same forged `Origin` on
  `POST /api/auth/login` also returned 200 and issued a session cookie.
- **Impact:** `SameSite=Lax` is the only layer. It does block the common cross-site form POST in
  current browsers, which is why this is Medium and not High. What it does not cover: a login-CSRF
  (an attacker silently signs a victim into an attacker-controlled account so the victim's
  subsequent data entry lands in it), a forced logout as nuisance/denial, any user on a browser
  where Lax is not enforced, and any future same-site subdomain that becomes attacker-influenced.
  Every other state-changing route in the app inherits the same exposure — this is a property of
  the middleware, not of these handlers.
- **Suggested fix (describe only, not implemented):** Validate `Origin` (falling back to `Referer`)
  against an allowlist for every non-GET request in `src/middleware.ts`, rejecting a mismatch with
  403. This is a single choke point and needs no per-route change.

### B-01-02 — CSP has no `script-src`, so it provides no XSS mitigation
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Disclosure / defence-in-depth
- **Status:** Known-open (`X-03` / `F-01-03`) — **still present, not worse**
- **Location:** `src/lib/securityHeaders.ts:10-20`
- **Request:** `GET /api/auth/me` with a valid session.
- **Expected:** A CSP restricting script sources.
- **Actual:** `Content-Security-Policy: frame-ancestors 'none'` — clickjacking protection only.
  All five other headers are correct and present: `Strict-Transport-Security:
  max-age=63072000; includeSubDomains; preload`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
  `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- **Impact:** No browser-side backstop if a stored-XSS sink is found anywhere in the app. The
  in-source comment states the reason plainly (an inline theme script and framer-motion runtime
  styles need a report-only rollout first), so this is a deliberate, documented deferral rather
  than an oversight. It is listed here because the client should be told in writing that the
  header exists but does not cover scripts. Whether any XSS sink actually exists is a
  families 2–12 question, not answerable from this family.
- **Suggested fix (describe only):** Roll out `Content-Security-Policy-Report-Only` with a
  `script-src` including whatever nonce/hash the theme script needs, observe, then promote to
  enforcing.

### B-01-03 — Seeded demo password fails the app's own password policy
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Auth / operational
- **Status:** **New** (not in the known-open list)
- **Location:** `prisma/seed.ts:354`, policy at `src/lib/password.ts:8-19`
- **Request:**
  ```
  POST /api/users HTTP/1.1
  Cookie: <admin session>
  {"name":"Audit Policy Probe","email":"...","role":"Staff","password":"vega123"}
  ```
- **Expected:** Either the seeded password satisfies the policy, or the seed is understood not to
  ship to the client.
- **Actual:** `400 {"error":"Password must be at least 12 characters"}`. Every seeded account
  (all five share one hash) uses `vega123`, seven characters.
- **Impact:** Two practical consequences, both operational rather than exploitable. First, an
  Admin cannot reset any account *back* to the documented demo password through the product —
  `PATCH /api/users/[email]` returns 400 — which is confusing during handover and training.
  Second, and more importantly: if the client's production database is ever stood up from
  `prisma/seed.ts`, five accounts — two of them Admin — go live with a seven-character,
  publicly-documented password that the application would refuse to set through its own UI. I hit
  this during testing: the probe that verifies password-change revocation could not restore its
  fixture through the API and had to write the hash directly.
- **Suggested fix (describe only):** Either raise the seeded password to something policy-compliant,
  or make first login force a password change, or state in the handover note that the seed is for
  demo data only and must never be applied to the client's live D1. The last is the cheapest and
  may be all that is wanted.

### B-01-04 — Malformed JSON returns 500 rather than 400
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Error handling
- **Status:** Known-open (`X-02` / `F-01-06`) — **still present, not worse**
- **Location:** `src/lib/api.ts:57-60` (`parseBody` → `request.json()` throws a `SyntaxError`, which
  `apiRoute` at `src/lib/api.ts:21-26` does not special-case, so it falls to the generic branch)
- **Request:** `POST /api/auth/login` with body `{"email": "a@b.lk", "password":`
- **Expected:** `400`
- **Actual:** `500 {"error":"Internal server error"}`
- **Impact:** Cosmetic and diagnostic only. The body stays generic and leaks nothing; the practical
  cost is noise in the Cloudflare error logs (a client bug is recorded as a server fault) and a
  misleading status for any future API consumer. Applies to every route using `parseBody`, not
  just login.
- **Suggested fix (describe only):** Catch `SyntaxError` from `request.json()` in `parseBody` and
  throw a 400-mapped error, or add a `SyntaxError` branch to `apiRoute`.

### B-01-05 — `login_throttle` rows are never garbage-collected
- **Severity:** Info
- **Confidence:** Confirmed
- **Class:** Availability / housekeeping
- **Status:** Known-open — **still present, not worse**
- **Location:** `src/lib/loginThrottle.ts:33-62`
- **Evidence:** Three failed logins against three non-existent emails left three rows. A subsequent
  successful login (which does run `cleanupExpiredSessions`, `src/lib/auth.ts:144-152`) cleared
  none of them; only `resetThrottle(key)` on that exact key removes a row.
- **Impact:** Unbounded slow growth of one small table, one row per distinct email ever used in a
  failed login attempt. Not a security issue and not urgent at this app's scale — an attacker can
  inflate it, but each row is tiny and the write is already rate-limited by the edge limiter. Worth
  recording so it is a known cost rather than a surprise.
- **Suggested fix (describe only):** Extend the existing opportunistic sweep in
  `cleanupExpiredSessions()` to also delete `login_throttle` rows whose window and lock have both
  expired — the same "cheap delete on login" pattern already in place, no new scheduling needed.

## Tested and clean

Everything below was verified against the running Worker, not read from source.

**Credential forgery — every variant refused with 401:**
- A JWT with its final signature byte flipped → `401 {"error":"Not authenticated"}`.
- An `alg:none` token carrying a **real, live `sid`** read straight out of the `sessions` table →
  401. The signature is genuinely required; the session id alone is not a credential.
- A well-formed HS256 token signed with an attacker-chosen 32-byte key, real `sid` → 401.
- A non-JWT garbage cookie value → 401, no 500.

**Session revocation — all five paths confirmed (cross-cutting sweep 7):**
- **Logout:** replaying the captured cookie after logout → 401, and `sessions.revokedAt` was
  actually written (`2026-09-05T04:28:27.837Z`), not merely the cookie cleared.
- **Deactivate:** Dilini authenticated (200), Admin `PATCH {status:"Inactive"}`, her very next
  request → 401. Status is re-read per request, not trusted from the token.
- **Role change:** Admin `PATCH {role:"Admin"}` on a live Staff session → that session 401s
  immediately.
- **Password change:** `PATCH {password, currentPassword}` → 200, target's live session → 401.
- **Delete:** a throwaway user created via API, logged in, deleted → their session 401s, and
  `select count(*) from sessions where userId not in (select id from users)` returned **0**, so the
  FK cascade leaves no orphaned session rows.

**Login-path hardening:**
- Inactive user (`ruwan@vegahomes.lk`) with the **correct** password → `403`, and critically
  **no `Set-Cookie` at all** — a deactivated account cannot obtain a session by any route.
- Account enumeration: six paired trials of unknown-email vs known-email-wrong-password produced
  byte-identical status and body every time, and median latencies of **107 ms vs 106 ms**
  (ratio 0.99). The `DUMMY_PASSWORD_HASH` constant-cost compare is doing its job — there is no
  timing oracle.
- Per-email throttle: statuses across six attempts were `[401,401,401,401,401,429]` — locks at
  exactly 5.
- A locked account refuses **even the correct password** (429), so the lock is not bypassable by
  finally guessing right.
- **F-01-02 fix holds:** after five failures against `kasun@`, an unrelated login as `nimal@`
  returned 200, and the `login_throttle` table contained exactly one row —
  `email:kasun@vegahomes.lk` — with **no `ip:` key of any kind**. Separately, five failures spread
  across five *different* emails left an unrelated correct login at 200.

**Injection and input handling:**
- Eight payloads (`' OR '1'='1`, `'; DROP TABLE users;--`, `1' UNION SELECT null,sqlite_version()--`,
  `admin'--`, `%27`, `' UNION SELECT name FROM sqlite_master--`, `nimal@vegahomes.lk'--`,
  `' or 1=1--`) through the email field: all → `401 {"error":"Invalid email or password"}`, no
  cookie issued, no SQL error surfaced. The same eight through the password field: all 401.
  `select count(*) from users` still returns **5**.
- Twelve malformed body shapes — array/object/null/number email, boolean password, missing fields,
  empty email, array body, string body, null body, non-boolean `remember` — **all 400, and not one
  issued a session**. The NoSQL-style `{"$ne": null}` object is rejected on type, not coerced.
- Mass assignment: `{email, password, role:"Admin", isAdmin:true, id:"u_forged", userId:"u_forged"}`
  → login succeeded as expected but `/api/auth/me` still reported `role: "Staff"`. Zod strips
  unknown keys; none were honoured.
- 100 KB email and password → 401 in 85 ms. No 500, no hang.

**Privilege escalation attempts as Staff — all refused:**
- `PATCH /api/users/kasun@vegahomes.lk {"role":"Admin"}` → 403, and the role in the database was
  still `Staff` afterwards.
- `POST /api/roles {"name":"audit-escalation","permissions":["projects:delete"]}` → 403.
- `GET /api/permissions/catalog` → 403.

**Middleware:**
- `GET /api/users` with no cookie → 401 (not an empty 200).
- **Matcher-bypass fix holds:** `GET /api/users/x.png` logged out → 401. The `[^/]*` matcher is
  still doing its job at depth.
- Security headers are present on all three response paths, including the two that bypass Next's
  `headers()` config: a normal API 200, a middleware 401 short-circuit, and the `/login` 307
  redirect (`x-content-type-options: nosniff` confirmed on each).
- `x-powered-by` is **absent** — `F-01-05` appears **resolved**; recorded here rather than as a
  finding since it was on the known-open list.

**`SESSION_SECRET` validation (the 2026-09-05 F-01-07 fix) — verified end to end.** With
`.dev.vars` temporarily set to an 8-byte secret and the Worker restarted:
- `POST /api/auth/login` → `500 {"error":"Internal server error"}`.
- `GET /api/auth/me` **with a cookie** → 500, **not** a `/login` redirect. This is the exact
  regression the fix targets: a broken deployment now fails loudly instead of presenting as
  "everyone is silently logged out".
- `GET /api/auth/me` with **no** cookie → still 401, because middleware short-circuits before the
  secret is ever touched. Correct.
- The server log carried the full diagnostic —
  `SESSION_SECRET is 8 bytes; at least 32 are required. Set it with: wrangler secret put SESSION_SECRET`
  — while the client body leaked none of it (no `SESSION_SECRET`, no `wrangler secret put`, no
  stack frames, no `.ts:NN`).
- `.dev.vars` was restored byte-identically from backup and the server re-verified at 200
  immediately afterwards.

**Cookie attributes:** `HttpOnly` ✓, `SameSite=lax` ✓, `Max-Age=604800` when `remember:true` ✓,
**no** `Max-Age` when `remember:false` (a true browser-session cookie) ✓. `Secure` is absent over
plain http, which is correct and deliberate — `sessionCookieOptions` derives it from the request
protocol, so it will be set over the HTTPS edge. **This is the one attribute this local rig cannot
prove; see "Not tested".**

**Disclosure:** no error body in this family contained a stack frame, a SQL fragment, a table or
column name, a file path or a library version. Method routing is correct — `GET /api/auth/login`
→ 405, `DELETE /api/auth/me` → 405, neither falling through to a handler.

## Cross-cutting sweeps completed (recorded in full in `00-INDEX.md`)

1. **SQL interpolation sweep** — complete, 9 sites, all safe.
2. **`projectAccessClause` call-site sweep** — complete, 19 call sites, all table-qualified.
3. **Guard sweep** — `node scripts/audit-guards.js` → *"Scanned 62 route files. OK — no unguarded
   handlers."*, exit 0.
4. **Dependency audit** — complete; 5 vulnerabilities, 3 high, all in dev-only tooling.
5. **Migration replay from zero** — **BLOCKED**, see below.
6. **Secret scan** — complete, clean.
7. **Session-revocation matrix** — complete, all five paths pass (evidence above).

## Not tested / blocked

- **Cross-cutting sweep 5 (migration replay from zero) is BLOCKED and remains unverified.** Both
  the destructive-reset route (`rm -rf .wrangler/state/v3/d1`) and the safer isolated route
  (`wrangler d1 migrations apply --local --persist-to <scratch>`, which touches nothing the user
  owns) were refused by the environment's command-permission classifier. The user's local D1 was
  backed up first and is confirmed intact and untouched — the delete never ran. **Consequence: it
  is still unknown whether the 28 migrations replay cleanly from an empty database.** This matters
  for handover specifically, because that is the exact path the client's own environment will take.
  Needs an explicit Bash permission grant, or a human to run it.
- **`Secure` cookie flag over HTTPS** cannot be proven on this rig — the local Worker serves plain
  http, and `sessionCookieOptions` correctly derives `secure` from the request protocol. Verifying
  it requires one request against a deployed HTTPS origin, which rule 2 (never touch remote) puts
  out of scope for this audit. Source review says it is right; that is not the same as evidence.
- **The edge rate limiter (`LOGIN_RATE_LIMITER`, 20 req/60 s) was never exercised.** It is gated
  behind `cf-connecting-ip`, which is absent on every local request by design — `src/lib/edgeRateLimit.ts`
  is deliberately never called with a placeholder key. I confirmed the *guard* (no `ip:` throttle
  row was ever created, and the route logs a warning instead of fabricating an identity), but the
  limiter's own 20/60 s behaviour is only reachable through Cloudflare's edge. Unverifiable locally.
- **Prisma schema drift (`F-01-08`) appears RESOLVED, not merely untested.** `grep -i mfa
  prisma/schema.prisma` returns nothing, so the claim that the schema still declares
  `users.mfaSecret` is stale. I could not confirm the downstream half — that `npm run db:reset-seed`
  therefore now succeeds — because that command drops and rebuilds the local D1 and is covered by
  the same blocked permission as sweep 5.
- **Concurrency on login** (two simultaneous logins for one account; a race between
  `recordFailure` and `resetThrottle`) was not probed. Class F concurrency is scheduled against
  the code-allocating routes (`basic-rate/next-code`, `expenses/next-invoice`) in families 7 and 4,
  where the consequence is a duplicate identifier rather than an extra session row.
- **MFA** was not tested or reported, per the prompt's explicit instruction — removed 2026-09-04,
  single-factor is the intended design.

## Fixture state after this audit

The harness restores what it changes, but two things are worth recording so a later session does
not misread them:

- `dilini@vegahomes.lk`'s password hash was rewritten directly via SQL (copied from
  `kasun@vegahomes.lk`, which is the same seeded hash) because the API refuses to set it back to
  `vega123` — see B-01-03. All five seeded accounts verified sharing one hash afterwards, and
  login as Dilini re-verified at 200.
- Throwaway rows created and left behind: users matching `audit-del-*@vegahomes.lk` (deleted by the
  probe itself) and `audit-policy-*@vegahomes.lk` (never created — the request 400s by design).
  `login_throttle` is cleared at the end of every run.
