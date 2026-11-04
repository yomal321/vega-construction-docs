# Post-k3s Hardening — Implementation Plan (2026-09-18)

**Source:** review of the two fixes recorded in `K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md`.
**Driver:** one of those two fixes is correct; the other is wired up but does not actually
enforce its policy. This plan closes that, plus the two gaps the same review surfaced, plus
the Cloudflare decommission the client confirmed on 2026-09-18 ("nothing to do with
Cloudflare").

---

## Review outcome — what this plan is and isn't reacting to

### `src/proxy.ts` session check — correct, no change planned

**Do not "improve" this.** The restored DB check was verified end to end by reading
`resolveSession` rather than trusting the comment: it rejects all four states the JWT-only
gate was blind to — revoked (`revokedAt is null`), absolutely expired (`expiresAt > ?`),
deactivated (`status !== 'Active'`) and idle-expired (`isIdleExpired`).

Two things that look like bugs and are not, recorded so nobody reverts them:

- **`touch: false` is deliberate.** `getSession()` owns the idle-clock touch, driven by the
  `x-session-activity` header the proxy always overwrites. If the proxy also touched, every
  request would double-write; if neither did, active sessions would idle-expire. The split is
  correct.
- **Not restoring `ADMIN_ONLY_PREFIXES` is genuinely UX-only, and this was verified, not
  assumed.** Every admin page is `'use client'`, and grepping all `page.tsx` files for
  `requireAdmin|requireSession|getSession|getDb` returns nothing — no admin data is
  server-rendered, so a demoted admin loading the shell gets 403s and no data. It stays a
  cosmetic gap.

One cost, noted but **not** addressed here: API requests now resolve the session twice (once
in the proxy, once in the route handler via `requireSession()`). That is a real 2x on the hot
path, but deduplicating it means either a request-scoped cache or passing identity from proxy
to handler via a header — both meaningfully more complex than the problem justifies at this
app's scale (single-digit-to-dozens of internal users). Phase 1's task 1.1 happens to remove
one query per login attempt, which partly offsets it. Revisit only if a real latency
complaint appears, not speculatively.

### `src/lib/edgeRateLimit.ts` login rate limiter — does not enforce its policy

This is the actual defect and the reason this plan exists. The fix is task 1.1; what follows is
why it is a defect at all, because the code looks correct and passes every obvious test.

#### What the code does today

`isPostgresRateLimited` is supposed to enforce "at most 20 login attempts per IP per 60
seconds". It does it in three separate steps:

1. `select "windowStart", count from login_rate_limit where key = ?` — read the counter
2. decide, **in JavaScript**: `const count = row.count + 1` … `return count > LIMIT`
3. `update login_rate_limit set count = ? where key = ?` — write the new counter back

Steps 1 and 3 are two separate round trips to Postgres. Nothing holds a lock between them.
That gap is the bug: the value the decision is based on can already be out of date by the time
the decision is made. This is the standard *check-then-act* race (TOCTOU — time-of-check to
time-of-use).

#### The everyday version

Picture a shared notebook with a number in it, and a rule: no more than 20 sign-ins per minute.
Each person must (1) read the number, (2) add one in their head, (3) write it back.

One person at a time, this works perfectly — 1, 2, 3 … 20, and the 21st is turned away.

Now twenty people walk up **at the same moment**. All twenty read the same number. All twenty
add one. All twenty write back the same result. Twenty sign-ins happened; the notebook went up
by one; nobody was turned away. Nobody did anything wrong — they all just read the number
*before* anyone else had written theirs.

#### Worked example — two simultaneous requests

Say the counter is at 5 and two login attempts arrive together:

| Step | Request A | Request B | Row in DB |
|---|---|---|---|
| 1 | `select` → reads `count = 5` | | `count = 5` |
| 2 | | `select` → reads `count = 5` | `count = 5` |
| 3 | computes `5 + 1 = 6`; `6 > 20`? no → **allow** | | `count = 5` |
| 4 | | computes `5 + 1 = 6`; `6 > 20`? no → **allow** | `count = 5` |
| 5 | `update count = 6` | | `count = 6` |
| 6 | | `update count = 6` | `count = 6` |

Two attempts were made. The counter advanced by **one**. Request B never saw A's increment,
because A had not written it yet when B read.

Scale that to an attacker firing 25 requests in parallel at a key with no row yet, which is the
realistic case:

- all 25 run their `select` before any runs its write → all 25 read "no row"
- all 25 therefore compute `windowExpired = true`
- all 25 run the `insert … on conflict do update set count = 1` — note this sets `count = 1`
  unconditionally, **not** `count + 1`, so no matter how many land here the row ends at `1`
- all 25 return `false` (not limited)

**25 attempts allowed against a limit of 20, and the counter reads 1.** The limiter did not
slow anything down.

#### Why this is worse than it sounds

- **Concurrency is the normal case for the traffic this exists to stop.** A sequential attacker
  politely awaiting each response is not a real threat model; every credential-stuffing and
  load-testing tool fires in parallel by default. So the limiter is closest to a no-op in
  precisely the scenario it was built for, and closest to correct in the scenario nobody needed
  it for.
- **The guarantee was silently downgraded.** Cloudflare's `LOGIN_RATE_LIMITER.limit()` is
  atomic — it is a managed primitive built for exactly this. Replacing it with a hand-rolled
  read-then-write kept the same function name, the same signature and the same call site, so
  nothing at the call site hints that the policy got weaker.
- **This is why it passed review.** Any single sequential test — click login six times, run
  `curl` in a loop — shows it behaving perfectly. Task 1.2 therefore requires writing the
  concurrency test *first* and watching it fail against the current code, so the test is proven
  to detect the bug rather than passing vacuously.

#### What the fix changes

Task 1.1 collapses steps 1–3 into a single `insert … on conflict do update … returning count`.
Postgres takes a row-level lock on the conflicting key, so simultaneous callers queue behind
each other and each one's read reflects the previous one's increment. The same two-request
timeline becomes:

| Step | Request A | Request B | Row in DB |
|---|---|---|---|
| 1 | one statement: increment, get back `6` → allow | *(waits on the row lock)* | `count = 6` |
| 2 | | one statement: increment, get back `7` → allow | `count = 7` |

Two attempts, counter reads 7. At 25 parallel attempts the counter reads 25 and everything past
the 20th is refused — which is the policy as written. It is also one round trip instead of two.

---

## Scope

**In scope:** the rate limiter's correctness (atomicity, the identity it keys on, table
growth), and removing Cloudflare from the repo now that k3s is the only target.

**Explicitly out of scope:**

- **Merging `src/lib/sessionToken.ts` back into `src/lib/auth.ts`.** That file split exists
  only because of the Workers constraint, so Phase 2 technically makes it unnecessary. It is
  also harmless, and unpicking it means touching the working session layer — every
  `@/lib/auth` re-export, the proxy, and the login route — for zero functional gain. Leave it.
- **The two other deferred items in `K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md`** (the
  never-built `-migrate` image tag, item 1). That is a pipeline defect with its own blast
  radius and belongs in its own change. Item 2 of that doc *is* covered here, as Phase 0.
- **Audit logging / alerting for rate-limit trips.** Still deferred by client decision, same
  as in `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md`.

---

## Phase ordering and why

| Phase | Closes | Effort | Risk |
|---|---|---|---|
| 0 — Retire the Workers deploy | Active double-deploy | 10 min | **None** (CI only) |
| 1 — Rate limiter correctness | The real defect + 2 gaps | 0.5–1 day | Low |
| 2 — Cloudflare code removal | Dead branches, dev-env friction | 0.5 day | **Medium** (see 2.2/2.3) |
| 3 — Ingress trust boundary | The XFF assumption | — | Needs cluster access |

The ordering is not arbitrary:

- **Phase 0 first** because it is the only item causing active harm right now (every merge to
  `main` deploys to both Cloudflare and k3s), it takes minutes, and it is a **precondition for
  Phase 2 being safe** — once nothing deploys to Workers, deleting Workers code cannot break a
  live deployment.
- **Phase 1 before Phase 2** because it is the security fix and must not wait on a cleanup.
  Tasks 1.1 and 1.2 are *one change, not two*: an atomic counter keyed on a spoofable identity
  is only half a fix, since the correct count would be counting the wrong thing. Land them
  together.
- **Phase 2 ordered by blast radius ascending**, riskiest last, each independently revertable.
- **Phase 3 last** because it needs cluster access nobody has had during this work, and
  task 1.2 is written specifically so the app no longer *depends* on its outcome.

---

## Phase 0 — Retire the Cloudflare deploy workflow — ✅ done 2026-09-18

### 0.1 Stop `main` deploying to Workers

- **File:** `.github/workflows/deploy.yml`
- **Current state:** triggers on `push: branches: [main]` **and** `workflow_dispatch`, so
  every merge to `main` updates the Cloudflare deployment at the same time as
  `CI-CD_Pipelines/Vega-OnPrem-k3s.yml` updates k3s `dev`.
- **Change:** delete the file. Given the client's 2026-09-18 decision, gating it to
  `workflow_dispatch`-only (the softer option `K3S_MIGRATION_KNOWN_ISSUES` offered) is keeping
  a loaded foot-gun for a target nobody is shipping to. Delete it and let git history hold it.
- **Acceptance:** a merge to `main` triggers exactly one deployment pipeline. Confirm in the
  Actions tab that no Cloudflare job runs.

---

## Phase 1 — Rate limiter correctness — ✅ done 2026-09-18

### 1.1 Make the counter atomic

- **File:** `src/lib/edgeRateLimit.ts` (`isPostgresRateLimited`)
- **The defect:** `select` → compute in JavaScript → `update`, as three separate round trips
  with no lock held across them, so concurrent callers all decide from the same stale count.
  Full explanation and worked timelines in **"login rate limiter — does not enforce its
  policy"** above; read that first if this task is being picked up cold.
- **Change:** collapse all three steps into one statement. `insert ... on conflict do update`
  takes a row-level lock, so concurrent callers serialize on it instead of all reading the same
  snapshot. Also drops 2 round trips to 1.

  ```ts
  async function isPostgresRateLimited(ip: string): Promise<boolean> {
    const key = `ip:${ip}`
    try {
      const db = await getDb()
      const now = new Date()
      const cutoff = new Date(now.getTime() - WINDOW_MS).toISOString()
      // ONE statement on purpose — see this task in the plan. A select-then-update pair lets
      // concurrent callers all read the same pre-increment count and all pass the limit.
      // ON CONFLICT DO UPDATE locks the row, so simultaneous attempts queue and each sees the
      // previous one's increment. The CASE arms are what make the fixed window work without a
      // second query: a row whose window has aged out is reset to 1 rather than incremented.
      const row = await db
        .prepare(
          `insert into login_rate_limit (key, "windowStart", count) values (?, ?, 1)
           on conflict(key) do update set
             "windowStart" = case when login_rate_limit."windowStart" < ? then excluded."windowStart" else login_rate_limit."windowStart" end,
             count         = case when login_rate_limit."windowStart" < ? then 1 else login_rate_limit.count + 1 end
           returning count`
        )
        .bind(key, now.toISOString(), cutoff, cutoff)
        .first<{ count: number }>()
      return (row?.count ?? 0) > LIMIT
    } catch (e) {
      console.error('Postgres login rate limit check failed, failing open:', e)
      return false
    }
  }
  ```

- **Three gotchas in this SQL, all checked against `src/lib/pg.ts` before writing it:**
  - **Bind count must be exactly 4.** `compile()` throws a loud `Bind count mismatch` rather
    than letting a mismatched bind reach Postgres — good, but it means adding or removing a
    `?` without updating `.bind()` fails at runtime, not typecheck.
  - **`"windowStart"` must stay double-quoted; `count`, `key`, `excluded` and
    `login_rate_limit` must stay lowercase and unquoted.** `rewritePlaceholders` quotes any
    bare identifier containing an uppercase letter and skips anything already quoted, so this
    exact casing is what makes the statement resolve against Prisma's quoted DDL.
  - **`count` is `int4`, so `pg` hands back a JS number.** It does *not* go through the OID-20
    parser that rescues `count(*)` (int8, returned as a string). If anyone ever widens this
    column to `bigint`, `row.count > LIMIT` becomes a string/number comparison that is
    silently always false — i.e. the limiter turns off with no error. Leave it `int4`.
- **Acceptance — must be a concurrency test, not a sequential one.** Sequential passing is
  what let the bug ship.
  - Primary: call `isPostgresRateLimited('1.2.3.4')` 25 times via a single `Promise.all`
    against a local Postgres, then read the row. Expect `count = 25` exactly, and at least
    one `true` returned. Run the same test against the *current* implementation first and
    watch it report `count = 1` and zero `true`s — confirms the test actually detects the bug
    rather than passing vacuously.
  - End to end: 25 parallel `POST /api/auth/login` from one source; expect ≥1 `429`.
  - Note the pool caps at `max: 10` (`src/lib/pg.ts`), so 25 calls run 10-at-a-time rather
    than truly 25-wide. That is still genuinely concurrent and is enough to demonstrate both
    the old failure and the new correctness — do not read a passing test as proof of 25-way
    parallelism.

### 1.2 Key the limiter on an identity the client cannot set

- **File:** `src/app/api/auth/login/route.ts`
- **The defect:** `request.headers.get('x-forwarded-for')?.split(',')[0]` takes the
  **leftmost** XFF entry, which is the client-controlled end. XFF is a list each proxy
  *appends* to, so a client sending `X-Forwarded-For: 1.2.3.4` gets `1.2.3.4, <realIp>` and
  leftmost returns the attacker's value. Consequences: rotate a fake header to evade the
  per-IP throttle entirely, or forge a colleague's address to push *their* bucket toward the
  50-failure lockout.
- **Change:** prefer `x-real-ip` (Traefik writes it from the socket, so it is not
  client-settable), fall back to the **rightmost** XFF hop, and drop `cf-connecting-ip` as
  part of Phase 2's decommission.

  ```ts
  // Traefik (deploy/helm/templates/ingress.yaml) sets X-Real-Ip from the connecting socket,
  // not by copying a request header, so a client cannot influence it. Prefer it.
  //
  // XFF fallback is read RIGHTMOST, not leftmost: each proxy APPENDS, so the leftmost entry is
  // whatever the original client sent (spoofable) and the rightmost is what the nearest trusted
  // proxy added. Reading leftmost is what made this spoofable in the first place.
  //
  // ASSUMPTION, written down because it fails silently if infra changes: exactly ONE trusted
  // hop (Traefik). Put a load balancer in front of it and the rightmost entry becomes the LB's
  // address, not the client's — that needs real trusted-hop counting, not a tweak here.
  function clientIpFrom(headers: Headers): string | undefined {
    const realIp = headers.get('x-real-ip')?.trim()
    if (realIp) return realIp
    const hops = headers.get('x-forwarded-for')?.split(',').map(h => h.trim()).filter(Boolean)
    return hops?.at(-1)
  }
  ```

- **Keep** the existing "no IP header at all → skip the IP layer entirely, log a warning"
  behaviour. Do **not** reintroduce a placeholder key like `ip:unknown`: that bucketed every
  unidentified client together and made 5 failures from any one of them lock out all of them
  (F-01-02). Omitting the layer is strictly safer than fabricating an identity.
- **Keep it local to this route.** One call site today; moving it to `src/lib/` is premature.
  If a second call site ever appears, move it then.
- **Acceptance:** a request carrying `X-Forwarded-For: 9.9.9.9` from a real client at
  `10.0.0.5` throttles against `10.0.0.5`, not `9.9.9.9` — verified by reading the
  `login_throttle` / `login_rate_limit` keys directly, not just by response codes.

### 1.3 Give `login_rate_limit` a reclamation path

- **File:** `src/lib/edgeRateLimit.ts`, called from `src/app/api/auth/login/route.ts`
- **The gap:** nothing ever deletes from this table. Confirmed by grep — the only statements
  touching it are the counter's own. `sessions` has `cleanupExpiredSessions()`;
  `login_throttle` at least gets `resetThrottle()` on a successful login. This table has
  neither, so every distinct client IP that ever reaches the login page leaves a permanent row.
- **Change:** add a sweep and await it at login beside the existing session sweep.

  ```ts
  // Housekeeping only: the upsert already treats an aged-out row as "start a fresh window", so
  // deleting one loses nothing. This exists because NOTHING else removes rows from this table.
  export async function cleanupExpiredRateLimits(): Promise<void> {
    const db = await getDb()
    const cutoff = new Date(Date.now() - WINDOW_MS).toISOString()
    await db.prepare('delete from login_rate_limit where "windowStart" < ?').bind(cutoff).run()
  }
  ```

- **Why a separate function rather than folding it into `cleanupExpiredSessions()`:** each
  module owns its own table's lifecycle. Burying a rate-limit delete inside a function named
  for sessions is the kind of thing that gets lost in a later refactor.
- **No index on `windowStart`, deliberately.** The sweep runs on every login, which keeps the
  table small, which keeps a sequential scan cheap — self-limiting. If the sweep ever moves to
  a schedule, add the index at the same time.
- **Not fixed here:** `login_throttle` has the same unbounded-growth shape for keys that never
  succeed (a probed non-existent email leaves a row forever). Pre-existing, not introduced by
  the fix under review, and fixing it means deciding a retention policy for lockout history.
  Flagged as a follow-up rather than folded in.

---

## Phase 2 — Remove Cloudflare from the repo — ✅ done 2026-09-18

Ordered by blast radius ascending. Each task is separately committable and separately
revertable. **Phase 0 must be done first** so none of this can break a live deployment.

### 2.1 `src/lib/edgeRateLimit.ts` — drop the Workers branch

Delete `isCloudflareRateLimited`, the module-scope `isWorkers` const, and the
`import { getEnv } from '@/lib/cfEnv'`. `isLoginRateLimited` becomes the Postgres
implementation directly. Lowest risk: the deleted branch is already unreachable on k3s.

### 2.2 `src/proxy.ts` — drop the Workers branch and the dynamic import

Delete `isWorkersRuntime()` and the signature-only fallback, then convert
`await import('@/lib/auth')` to a normal static `import`. Drop the now-unused
`verifySessionToken` import (keep the export in `sessionToken.ts` — `resolveSession` still
uses it internally).

**This is the highest-consequence change in the plan.** The dynamic import exists to keep
`pg` out of the Workers middleware bundle, and getting that wrong historically produced
`Method Promise.prototype.then called on incompatible receiver`, which 500'd *every route the
matcher covers* — the entire app except static assets. On a Node runtime a static import of
`pg` is completely ordinary, so this should be a non-event; "should be" is exactly the phrase
that earned that outage, so verify rather than assume:

- **Acceptance:** `npm run build` with `BUILD_TARGET=container` succeeds, then run the image
  and confirm an authenticated page load, an authenticated API call, an unauthenticated
  redirect to `/login`, and a revoked-session rejection. A smoke test of one page is not
  enough — the original failure was per-response-type.

### 2.3 `src/lib/db.ts` — remove the Hyperdrive path

Delete `getHyperdriveConnectionString()` and its call, leaving `getDb()` as
`process.env.DATABASE_URL` → `createDb(url)`. Then delete `src/lib/cfEnv.ts`, which has no
importers left once 2.1 and 2.3 land.

Worth doing rather than leaving dormant: that helper runs a `try { await import(...) } catch`
on **every** `getDb()` call, and `getDb()` is now called several times per request (proxy
resolve, route resolve, throttle, rate limit). It is a per-request dynamic-import-and-throw
for a platform that no longer exists.

**Highest-risk file in the repo** — every query goes through it. Land it alone, verify
against a real pod, and keep it trivially revertable.

### 2.4 Build config and dependency

- `next.config.ts` — remove the `initOpenNextCloudflareForDev()` import and its
  `NODE_ENV === 'development'` guard. **This is a local-dev improvement, not just deletion:**
  it is what currently forces `CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE` into
  `.env` for `next dev` to start at all. Removing it deletes a required local env var.
- `next.config.ts` — the `BUILD_TARGET === 'container'` guard on `output: 'standalone'` can
  become unconditional, since the only reason it was gated was OpenNext tracing a conflicting
  output tree. **Keep `BUILD_TARGET` set in the Dockerfile either way** until this is verified
  — an unexpected `standalone` output is a silent image-shape change, not a build error.
- Delete `open-next.config.ts`, `wrangler.toml`, `deploy.sh`, `.dev.vars`.
- `package.json` — remove the `preview`/`predeploy`/`deploy` scripts and the
  `@opennextjs/cloudflare` dependency. Keep `prebuild`'s `vendor-pdf-worker.js`: that is a CSP
  requirement (`worker-src 'self'`), unrelated to Cloudflare.
- Update the stale Cloudflare rationale comments now describing a dead platform:
  `src/lib/pg.ts`'s Workers pooling block, `src/lib/sessionToken.ts`'s file-header,
  `src/lib/auth.ts`'s `wrangler secret put` hint (→ the sealed secret), and the Dockerfile's
  `initOpenNextCloudflareForDev` note.
- **Acceptance:** `npm ci && npx prisma generate && npm run build` clean from a fresh
  `node_modules`; `next dev` starts with no Hyperdrive env var present; `node scripts/audit-gate.js`
  and `node scripts/audit-guards.js` both still pass.

---

## Phase 3 — Ingress trust boundary — ⚠️ PARTIALLY done 2026-09-18 (3.2 confirmed, 3.1 escalated)

Task 1.2 makes the app read a header Traefik controls rather than one the client controls,
which is a genuine improvement on its own. It does not *prove* the ingress cannot be bypassed.
Carrying forward item 3 of `K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md`, two things needed
confirming with cluster access (`entra:yomal@bistecglobal.com`, read-only kubectl in
`vega-dev`, connected 2026-09-18):

- **3.2, confirmed directly, not assumed:** `kubectl get svc -n vega-dev` shows `vega-web` as
  **ClusterIP only** (no `EXTERNAL-IP`, no NodePort); `kubectl get deploy vega-web -o
  jsonpath='{.spec.template.spec.hostNetwork}'` is empty and its container port carries no
  `hostPort`; and it's the only Service/Ingress pair in the namespace. There is no Kubernetes-
  level path from outside the cluster to the pod except through Traefik's two Ingress
  addresses — full detail and the exact commands run are in
  `doc/test/security/AZURE_SECURITY_RUNBOOK.md`.
- **3.1, still open — genuinely blocked, not just unattempted.** Traefik's own controller
  config (`forwardedHeaders.trustedIPs` or equivalent) runs in a platform-owned namespace this
  app's kubectl access cannot reach, and a `Middleware` CRD lookup inside `vega-dev` itself was
  denied outright. Tried the obvious workaround — test it live — and it wouldn't have worked
  even with full access: the pod currently deployed to `vega-dev` is running commit `80f251b`,
  which predates `clientIpFrom()` (and even predates the SESSION_SECRET fix this whole branch
  started from) — it never reads `x-real-ip` at all, so spoofing against it would answer a
  question about code already being replaced, not this code. Escalated as a specific written
  question to DevOps in `AZURE_SECURITY_RUNBOOK.md`, "Task 3.1" — that question and this
  section must be updated together once answered, so neither drifts into claiming a
  confirmation the other doesn't have.

Until 3.1 is answered, treat IP-based throttling as "as strong as Traefik's actual behaviour
turns out to be," not an independently verified guarantee — same posture
`K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md` already recorded. Recorded in
`doc/test/security/AZURE_SECURITY_RUNBOOK.md` (new). **Do not edit
`CLOUDFLARE_SECURITY_RUNBOOK.md`** — it stays as the historical record.

---

## Risk and rollout

- **No forced logout.** Nothing here changes the JWT shape or the `sessions` schema, unlike
  Phase 2 and the idle-timeout cutover. Users stay logged in across this deploy.
- **Migration:** none. `login_rate_limit` already exists
  (`prisma/migrations/20260918000000_login_rate_limit/`, correctly named `migration.sql`).
  Phase 1 changes only how it is written to.
- **Rollback:** Phase 1 is one file plus one function in the login route. Phase 2's tasks are
  each independently revertable, which is the reason for splitting them at all.
- **Deploy Phase 2.2 and 2.3 separately from each other**, and not at the end of a day. Both
  touch code on every single request, and their failure modes (total 500, or no DB) are the
  loud kind you want to be awake for.

---

## Flat task list

### Phase 0 — Retire the Workers deploy
- [ ] 0.1 Delete `.github/workflows/deploy.yml`; confirm one pipeline runs per merge to `main`

### Phase 1 — Rate limiter correctness — ✅ done 2026-09-18
- [x] 1.1 Replace the select→compute→update sequence with the single atomic upsert + `returning`
- [x] 1.2 Write the failing concurrency test FIRST; confirm it reports `count = 1` against the
      current code before fixing (a test that passes vacuously proves nothing) — actual result
      against a real dev Postgres was `count = 2, blocked = 0` (pool timing, not exactly the
      worst-case trace, but the same failure: most of 25 concurrent attempts vanished)
- [x] 1.3 Re-run the concurrency test after 1.1; expect `count = 25` and ≥1 `true` — got
      `count = 25, blocked = 5` exactly (25 fired, limit 20, 5 over → 5 blocked)
- [x] 1.4 `clientIpFrom()`: prefer `x-real-ip`, fall back to **rightmost** XFF — landed with 1.1;
      `cf-connecting-ip` dropped from this call site entirely rather than kept as a first
      preference, since nothing on k3s will ever set it
- [x] 1.5 Verify a forged `X-Forwarded-For` does not change the throttle key — verified with a
      standalone script exercising `clientIpFrom()` directly: `x-real-ip` wins over a forged
      XFF, the rightmost XFF hop is used (not the client-supplied leftmost one), and a sanity
      check confirmed the OLD leftmost logic really would have returned the attacker's forged
      value — i.e. the test would have caught the original bug, not just passed vacuously
- [x] 1.6 Add `cleanupExpiredRateLimits()`; await it at login beside `cleanupExpiredSessions()`
      — done as `Promise.all([...])` rather than two sequential awaits, since neither cleanup
      depends on the other
- [x] 1.7 Fix the stale "cheapest (no D1 round trip)" comment at `login/route.ts:56` — on k3s
      this check is a Postgres round trip, so the stated ordering rationale was wrong even
      though the order itself is still right

**Verification artifact kept in the repo:** `scripts/verify-rate-limit.ts` (`npm run
verify:rate-limit`), following the existing `scripts/verify-pg.ts` convention — env-gated on
`DATABASE_URL`, uses `203.0.113.1` (TEST-NET-3, RFC 5737, never a real client address) as its
test key, deletes that row before and after. Required applying the
`20260918000000_login_rate_limit` migration to the dev DB first, via `npx prisma migrate
deploy` — it existed on disk but had not been applied yet. Typecheck and both CI gates
(`scripts/audit-guards.js`: 64/64 routes; `scripts/audit-gate.js`: 3 accepted, 0 unaccepted)
pass after this phase.

### Phase 2 — Cloudflare removal — ✅ done 2026-09-18
- [x] 2.1 `edgeRateLimit.ts`: delete the Workers branch, `isWorkers`, the `getEnv` import
- [x] 2.2 `proxy.ts`: delete the Workers branch; static-import `@/lib/auth`; verify all four
      response types against a real pod, not one page — verified against the real standalone
      container build (not `next dev`): unauthenticated page redirect, unauthenticated API
      401, garbage-cookie rejection, and — the case that specifically proves the PROXY's own
      DB check works, not just the route-handler layer — a disposable test user logged in,
      confirmed a 200 on a page route with no server-side check of its own, then revoked
      server-side and confirmed that SAME page route redirects to `/login` on the next request
- [x] 2.3 `db.ts`: delete the Hyperdrive path; delete `cfEnv.ts`; land alone, verify alone —
      re-ran the full task-2.2 smoke test plus the rate-limit concurrency test plus both audit
      gates after this change, since every query in the app goes through this file
- [x] 2.4 `next.config.ts`, `open-next.config.ts`, `wrangler.toml`, `deploy.sh`,
      `package.json` scripts + dependency, `tsconfig.json`'s `@cloudflare/workers-types` —
      verified with a genuinely clean install (`rm -rf node_modules package-lock.json && npm
      install`), not just an edited manifest: typecheck, a full container build, and both
      audit gates all pass from that fresh tree. `.dev.vars` deliberately NOT deleted — it's
      gitignored, untracked, already inert once `initOpenNextCloudflareForDev()` is gone, and
      deleting a local file holding live secrets for zero repo benefit isn't worth it.
- [x] 2.5 Update the stale Cloudflare comments — went beyond the four files this task named,
      via a repo-wide sweep (`git ls-files | grep -i cloudflare\|wrangler\|opennextjs`) rather
      than assuming the four were the only ones. Found and fixed several more:
      `src/data/mock.ts`, `src/lib/api.ts`, `src/lib/exportPdf.ts`, `src/lib/securityHeaders.ts`
      (the HSTS comment, which now correctly cites Traefik/cert-manager instead of Cloudflare's
      edge, with a hedge back to Phase 3's still-open trust-boundary question), and — the
      largest single one — **`README.md`**, which was the project's primary onboarding doc and
      was describing an entirely dead architecture (Next.js 15, Cloudflare Workers, D1,
      `wrangler` commands, `npm run deploy`) rather than a historical record; rewritten to
      describe the real k3s/Postgres/Helm/ArgoCD setup. One claim caught and NOT made: the
      README was going to say the Helm migrate Job "runs automatically," which is what it's
      *supposed* to do — corrected to flag that its image is confirmed NOT currently built by
      the pipeline (K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md item 1) rather than asserting
      something known to be false. `deploy/helm/values-{dev,uat}.yaml`'s "Cloudflare token" and
      `scripts/vendor-pdf-worker.js`'s `cdnjs.cloudflare.com` were checked and correctly left
      alone — the former is cert-manager's DNS-01 challenge provider (an unrelated, still-live
      use of Cloudflare as a DNS host, not the app's own hosting), the latter is just a public
      CDN domain name in a comment.
- [x] 2.6 Confirm `next dev` starts with no Hyperdrive env var, and both audit scripts pass —
      confirmed; `next dev` was up in under a second reading only `.env`

**Two things found during the 2.5 sweep, deliberately NOT fixed here — flagged instead:**
- **The Playwright e2e suite (`tests/*.spec.ts`) cannot currently run at all**, for a deeper
  reason than `playwright.config.ts`'s own stale comment suggested. That comment only pointed
  at the deleted `npm run preview` script; the real problem is worse — every spec's
  setup/teardown goes through `tests/helpers.ts`, whose DB-assertion helpers (`execLocalSql`,
  `clearLoginThrottle`, ...) shell out to `node_modules/wrangler/bin/wrangler.js d1 execute
  --local`, a binary and a database that no longer exist in this repo at all. Fixing the
  config alone would silently imply the suite works when it would still crash on the first
  helper call. `playwright.config.ts`'s comment now says this plainly rather than describing a
  process that no longer exists. Porting `tests/helpers.ts` onto a direct Postgres connection
  is real, separate scope — not attempted here.
- **`prisma/clone-local-to-remote.ts` is dead code**, built entirely around `wrangler d1
  execute --local`/`--remote`. Unlike the items above, this wasn't broken by anything in this
  phase — it was already non-functional from the earlier D1-to-Postgres migration, before this
  review started. Left untouched and unflagged-as-fixed; whether to delete it or rewrite it as
  a Postgres-to-Postgres data sync is a call for whoever still needs that workflow, not
  something to decide as a side effect of a Cloudflare cleanup.

**Full verification, repeated after every sub-task in this phase, not just once at the end:**
typecheck clean; a real container build (`BUILD_TARGET=container`, matching the Dockerfile)
succeeds; both CI gates (`audit-guards.js` 64/64, `audit-gate.js` 3 accepted/0 unaccepted)
pass; the standalone build actually runs (`node server.js`) and was exercised live — not just
built — for every change in this phase.

### Phase 3 — Ingress — ⚠️ partially done 2026-09-18 (3.2, 3.3 done; 3.1 escalated to DevOps)
- [ ] 3.1 Confirm or configure Traefik's trusted-hop behaviour — **blocked**, not skipped:
      Traefik's own config is outside this app's namespace access, and a live test against the
      currently-deployed pod (commit `80f251b`, predates `clientIpFrom()`) would not have
      answered it either. Specific written question sent to DevOps, recorded in
      `AZURE_SECURITY_RUNBOOK.md`
- [x] 3.2 Confirm the pod is not directly reachable, bypassing Traefik — confirmed via direct
      `kubectl` evidence, not assumption: `vega-web`'s Service is ClusterIP-only (no
      EXTERNAL-IP, no NodePort), no `hostNetwork`/`hostPort` on the pod, and it's the only
      Service/Ingress pair in the namespace
- [x] 3.3 Write `AZURE_SECURITY_RUNBOOK.md` (k3s/Traefik, not Front Door); leave
      `CLOUDFLARE_SECURITY_RUNBOOK.md` as history

---

## Definition of done

| Item | Closed by |
|---|---|
| Login rate limit enforced under concurrency | 1.1, verified by 1.2/1.3 |
| Rate limit keyed on a non-spoofable identity | 1.4, verified by 1.5 |
| `login_rate_limit` bounded | 1.6 |
| One deployment target | 0.1, Phase 2 |
| Local dev needs no Cloudflare env vars | 2.4 |
| Ingress trust boundary verified | Phase 3 — **open, needs cluster access** |

Still open by explicit client decision, unchanged from
`UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md`: audit logging, alerting, access reviews,
penetration testing, CSRF tokens. The `-migrate` image-tag defect
(`K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md` item 1) also remains open and is not covered here.
</content>
