# Session Idle Timeout + Shorter Absolute Expiry — Plan, 2026-09-07

**Date:** 2026-09-07
**Source:** Design review of `src/lib/auth.ts` session lifetimes. Not an audit finding — no
external report raised this; it came out of a direct question about whether a 1-day
session-only expiry is appropriate.
**Status:** 📋 PLANNED — nothing implemented yet.

**Design constraint, same as the 2026-09-01 and 2026-09-05 plans: change only what this
requires.** No refactors, no renames, no new dependencies. Every change below lists its blast
radius, and each was checked against the real callers and real runtime behaviour before being
written down — see the "Verified before writing" note under each.

---

## What changes

| Lifetime | Current | Target |
|---|---|---|
| Absolute — "Remember me" checked | 7 days | **7 days (unchanged)** |
| Absolute — "Remember me" unchecked | 24 hours | **8 hours** |
| Idle — "Remember me" checked | none | **3 days** |
| Idle — "Remember me" unchecked | none | **1 hour** |

The two absolute lifetimes already exist as constants. The two idle windows are new: today
`sessions.expiresAt` is written once at login and **never extended or re-checked against
activity**, so a session is valid for its full absolute window whether the user worked
continuously or closed the laptop five minutes in.

## Summary of changes

| # | Change | Files touched | Schema? | Frontend change |
|---|---|---|---|---|
| 1 | Add `lastSeenAt` + `remember` to `sessions` | 2 (+1 migration) | **Yes** | No |
| 2 | New idle constants; session-only absolute 24h → 8h | 1 | No | No |
| 3 | `createSession` writes the two new columns | 1 | No | No |
| 4 | `resolveSession` enforces the idle window | 1 | No | No |
| 5 | Throttled `lastSeenAt` write (≤1 per 5 min per session) | 1 | No | No |
| 6 | **Exclude background polls from counting as activity** | 2 | No | No |
| 7 | Update the comments changes 2–6 make stale | 2 | No | No |

Total: **6 source files + 1 migration**, all under `vega-manager/`. One schema change, one
migration, one **operational** step at cutover (see the end).

---

## Five design decisions, and why

### D1 — The idle window differs by session type

A single 1-hour idle applied to both would make "Remember me" a lie: the 7-day absolute would
never be reached in practice. The checkbox is an explicit, informed user choice to trade
security for convenience on a machine the user trusts; overriding it with the strict window
silently cancels that choice and generates "why do I keep getting logged out when I ticked the
box" support noise.

3 days of idle on a remembered session still reaps genuinely abandoned sessions — a remembered
session untouched for 3 days is not in use — without touching the normal overnight or weekend
gap.

Set `REMEMBERED_IDLE_SECONDS` to `null` to disable idle on remembered sessions entirely; the
check below is written to allow that.

### D2 — `remember` is stored as `Int` (0/1), not `Boolean`

`resolveSession` needs to know which idle window applies, and today **the session row does not
record whether "Remember me" was checked** — `createSession(userId, remember)` uses the flag to
compute `expiresAt` and the JWT expiry, then discards it. So it has to be persisted.

It goes on the DB row rather than into the JWT payload deliberately: `auth.ts:12-19` states that
the JWT is "deliberately NOT self-sufficient," carrying only `sid`. Adding a second claim would
drift back toward the self-sufficient token that comment exists to warn against.

It is `Int` rather than `Boolean` because **the schema currently contains zero `Boolean`
columns** (verified across all 25 models). SQLite/D1 returns `0`/`1` for a Prisma `Boolean`
while `pg` returns real `true`/`false`, so introducing the first one adds a row-mapping special
case to the D1-compatibility shim in the planned Azure/Postgres migration. `Int` behaves
identically on both. One line of comment covers the readability cost.

### D3 — The idle check runs in JS, not SQL

Expressing "is `lastSeenAt` older than N seconds" in SQL means SQLite's
`datetime(x, '+N seconds')`, which has no Postgres equivalent and would have to be rewritten
during the Azure migration. Fetching `lastSeenAt` and comparing it in a pure function is
portable, unit-testable without a database, and costs one extra column in an existing `select`.

### D4 — The `lastSeenAt` write is throttled

`resolveSession` runs in middleware on essentially every request. Writing `lastSeenAt` on each
one adds a DB write per request — a real cost on D1 (per-row-written billing plus latency) and
a needless one anywhere.

Persist only when the stored value is more than `IDLE_WRITE_THROTTLE_SECONDS` (5 min) stale.
That caps it at **≤1 write per 5 minutes per active session** while keeping the idle window
accurate to within 5 minutes — immaterial against a 1-hour window. Because the write is
throttled to that rate, it can simply be `await`ed; no platform-specific `ctx.waitUntil()` is
needed, which also keeps this portable to Azure.

### D5 — Background polls must NOT count as activity ⚠

**This is the change the feature fails silently without.**

`src/components/Header.tsx:190,272-273` polls `/api/notifications` on a
`NOTIFICATIONS_REFRESH_MS = 60_000` SWR `refreshInterval`, and `Header` is rendered by every
authenticated page (verified: 10+ page-level render sites; it is not in `AppShell`, but every
non-login page imports it).

So **any open tab issues an authenticated request every 60 seconds indefinitely.** If that
request refreshes `lastSeenAt`, a session on an unattended machine with a browser tab left open
never goes idle — precisely the scenario this whole change exists to catch. The idle timeout
would be decorative.

SWR's `refreshWhenHidden` defaults to `false`, so polling does pause on a hidden or minimised
tab. That does not help the main case: a tab left open and visible on an unlocked desk keeps
polling.

The fix is a **server-side path allowlist** in middleware — polling endpoints authenticate
normally but do not touch `lastSeenAt`. It is deliberately server-side rather than a
client-sent `X-Background-Poll` header: a client-controlled flag is spoofable in the
session-extending direction, which would let XSS keep a stolen session alive indefinitely.

Initial list: `/api/notifications`. Anything added later on a timer must be added here too —
change 7 puts a comment at the constant saying so.

---

## Change 1 — Add `lastSeenAt` and `remember` to `sessions`

**Files:** `prisma/schema.prisma`, `migrations/0029_session_idle_timeout.sql` (new)

### Verified before writing

`model Session` (schema.prisma:160-169) currently holds `id`, `userId`, `expiresAt`,
`createdAt`, `revokedAt` and an index on `userId`. Grep for `expiresAt` across `src/` returns
exactly 4 sites: the insert (`auth.ts:76`), the validity check (`auth.ts:117`), the cleanup
delete (`auth.ts:149`), and the computation itself (`auth.ts:75`). Nothing else reads or writes
session lifetime, so the blast radius of adding to this table is confined to `auth.ts`.

### The change

```prisma
model Session {
  id        String    @id @default(cuid())
  userId    String
  user      User      @relation(fields: [userId], references: [id], onDelete: Cascade)
  expiresAt DateTime
  createdAt DateTime  @default(now())
  revokedAt DateTime? // NULL = still valid (subject to expiresAt); set = invalidated
  // Last request that counted as user activity — see NON_ACTIVITY_PATHS in src/middleware.ts
  // for what deliberately does not count. Written at most once per
  // IDLE_WRITE_THROTTLE_SECONDS per session, so it lags real activity by up to 5 minutes;
  // immaterial against the smallest idle window (1 hour).
  lastSeenAt DateTime
  // 1 = "Remember me" was checked at login, 0 = not. Selects which idle window applies
  // (see auth.ts). Int, not Boolean, on purpose: this schema has no other Boolean column,
  // and D1 returns 0/1 where pg returns true/false — keeping it Int avoids a row-mapping
  // special case in the planned Postgres migration.
  remember  Int       @default(1)

  @@index([userId])
  @@map("sessions")
}
```

Migration `0029_session_idle_timeout.sql`:

```sql
-- SQLite cannot ADD COLUMN with a non-constant default, so both land nullable-or-defaulted
-- and are backfilled in the same migration.
ALTER TABLE "sessions" ADD COLUMN "lastSeenAt" DATETIME;
ALTER TABLE "sessions" ADD COLUMN "remember" INTEGER NOT NULL DEFAULT 1;
UPDATE "sessions" SET "lastSeenAt" = CURRENT_TIMESTAMP WHERE "lastSeenAt" IS NULL;
```

Backfilling to `CURRENT_TIMESTAMP` rather than `createdAt` is deliberate: backfilling from
`createdAt` would mark every pre-existing session as idle since login and log the entire user
base out the instant the migration lands. See the cutover section — the plan handles
pre-existing sessions explicitly instead, and does not rely on this backfill for it.

### Blast radius

The table gains two columns. Nothing outside `auth.ts` selects from `sessions`.

---

## Change 2 — Idle constants; session-only absolute 24h → 8h

**File:** `src/lib/auth.ts`

```ts
const REMEMBERED_TTL_SECONDS = 60 * 60 * 24 * 7 // 7 days — "Remember me" checked
// Unchecked: 8 hours. Not a true tab-close session — some browsers restore session cookies
// across a restart (Chrome/Edge "continue where you left off"), so a short hard expiry is the
// real backstop; the missing `maxAge` below is what makes most browsers actually drop it on
// close in the common case. Was 24h until 2026-09-07; 8h bounds it to a single working day.
const SESSION_ONLY_TTL_SECONDS = 60 * 60 * 8

// Idle windows — how long a session may go WITHOUT activity, independent of the absolute
// caps above. Both are enforced; whichever expires first ends the session. Differs by
// session type on purpose: a single strict window would make "Remember me" meaningless,
// since its 7-day absolute would never be reached. See the plan's decision D1.
const SESSION_ONLY_IDLE_SECONDS = 60 * 60 // 1 hour
const REMEMBERED_IDLE_SECONDS: number | null = 60 * 60 * 24 * 3 // 3 days; null disables

// lastSeenAt is only persisted when it is at least this stale — caps the write rate at
// ~1 per 5 min per active session instead of one per request. See decision D4.
const IDLE_WRITE_THROTTLE_SECONDS = 5 * 60
```

### Blast radius

`SESSION_ONLY_TTL_SECONDS` feeds both `createSession` (DB `expiresAt`) and `signSessionToken`
(JWT `exp`) from the single constant, so the two stay in lockstep automatically — the existing
`auth.ts:65-66` comment about keeping them together still holds and needs no change.

**Already-issued** session-only tokens keep their stored 24-hour `expiresAt`; the shorter cap
applies only to sessions created after deploy. Self-healing within 24h, and moot if the cutover
step below is taken.

---

## Change 3 — `createSession` writes the new columns

**File:** `src/lib/auth.ts`

```ts
export async function createSession(userId: string, remember = true): Promise<string> {
  const db = await getDb()
  const sid = `sess_${crypto.randomUUID()}`
  const ttlSeconds = remember ? REMEMBERED_TTL_SECONDS : SESSION_ONLY_TTL_SECONDS
  const now = new Date().toISOString()
  const expiresAt = new Date(Date.now() + ttlSeconds * 1000).toISOString()
  await db
    .prepare('insert into sessions (id, userId, expiresAt, lastSeenAt, remember) values (?, ?, ?, ?, ?)')
    .bind(sid, userId, expiresAt, now, remember ? 1 : 0)
    .run()
  return signSessionToken(sid, remember)
}
```

---

## Change 4 — `resolveSession` enforces the idle window

**File:** `src/lib/auth.ts`

Add a pure, exported helper so the rule is unit-testable without a database or time travel:

```ts
// Exported for tests. `null` idleSeconds = no idle limit for this session type.
export function isIdleExpired(lastSeenAt: string, idleSeconds: number | null, now: Date): boolean {
  if (idleSeconds === null) return false
  return now.getTime() - new Date(lastSeenAt).getTime() > idleSeconds * 1000
}
```

`resolveSession` gains `s.lastSeenAt` and `s.remember` in its `select`, then after the existing
row/status checks:

```ts
const idleWindow = row.remember === 1 ? REMEMBERED_IDLE_SECONDS : SESSION_ONLY_IDLE_SECONDS
if (isIdleExpired(row.lastSeenAt, idleWindow, new Date())) return null
```

Returning `null` — not throwing — matches the four existing "not authenticated" cases the
`auth.ts:88-91` comment enumerates (missing, revoked, expired, user not Active). Idle-expired is
a fifth of exactly the same kind, and middleware already handles `null` correctly for both API
(401) and page (redirect to `/login`) requests. **No middleware change is needed for this part**
— only for change 6.

Optionally have `revokeSession(sid)` fire on the idle-expiry path so the row is marked rather
than left to `cleanupExpiredSessions`. Not required for correctness — the check is enforced on
every read regardless — and it adds a write to a request that is already being rejected. Left
out; noted so it is a decision rather than an oversight.

### Blast radius

Every authenticated request. This is the enforcement point, so a bug here is a mass logout (too
strict) or a no-op feature (too lax) — hence the unit tests in T8, which cover both boundary
directions.

---

## Change 5 — Throttled `lastSeenAt` write

**File:** `src/lib/auth.ts`

```ts
async function touchSession(sid: string, lastSeenAt: string, now: Date): Promise<void> {
  if (now.getTime() - new Date(lastSeenAt).getTime() < IDLE_WRITE_THROTTLE_SECONDS * 1000) return
  const db = await getDb()
  await db.prepare('update sessions set lastSeenAt = ? where id = ?').bind(now.toISOString(), sid).run()
}
```

`resolveSession` takes a new option and calls it **after** the idle check, so the check always
reads the pre-touch value:

```ts
export async function resolveSession(token: string, opts: { touch?: boolean } = {}): Promise<SessionPayload | null>
```

Two concurrent requests both past the throttle will both write. Harmless: same column,
near-identical value, last write wins.

### Verified before writing

`resolveSession` has exactly two call paths — `src/middleware.ts:36` and `getSession()`
(`auth.ts:155`), the latter used only by `/api/auth/logout` and `/api/auth/me`. Middleware runs
on every authenticated request (its matcher excludes only `_next/static`, `_next/image`,
`favicon.ico` and root-level image files, none of which are authenticated), so **middleware is
the single chokepoint** and the only place that should touch.

`getSession()` therefore passes `touch: false` — its two callers are both already behind
middleware, which has touched for that same request. The throttle would swallow the second write
anyway; passing `false` makes it explicit rather than incidental.

---

## Change 6 — Exclude background polls from counting as activity ⚠

**Files:** `src/middleware.ts`, `src/lib/auth.ts` (the `touch` option from change 5)

See decision D5 for why this is load-bearing rather than an optimisation.

```ts
// Endpoints hit on a timer by an idle browser tab rather than by a person. They authenticate
// normally, but must NOT refresh the session's idle clock — otherwise a tab left open on an
// unattended machine keeps its session alive forever and the idle timeout in src/lib/auth.ts
// does nothing at all.
//
// /api/notifications is polled every 60s by src/components/Header.tsx
// (NOTIFICATIONS_REFRESH_MS), which every authenticated page renders.
//
// ANY new endpoint put on a client-side timer MUST be added here.
//
// Server-side allowlist, deliberately not a client-sent header: a client-controlled "this is
// only a poll" flag is spoofable in the session-EXTENDING direction, which would let XSS keep
// a stolen session alive indefinitely.
const NON_ACTIVITY_PATHS = ['/api/notifications']
```

In `middleware`:

```ts
const isActivity = !NON_ACTIVITY_PATHS.some(p => pathname === p)
const session = await resolveSession(token, { touch: isActivity })
```

Exact match, not `startsWith` — a prefix match would let `/api/notifications-something-else`
silently inherit the exemption.

### Blast radius

Middleware, every request. A path wrongly on this list becomes invisible to the idle clock; a
polling path wrongly left off defeats the feature. Both are covered in T8.

---

## Change 7 — Update the comments changes 2–6 make stale

**Files:** `src/lib/auth.ts`, `src/components/Header.tsx`

- `auth.ts:8-11` — says "still 1 day"; becomes 8 hours (folded into change 2 above).
- `auth.ts:12-19` — the "JWT is deliberately NOT self-sufficient" block should note that
  `remember` now lives on the row, and why it went there rather than into the JWT payload (D2).
- `auth.ts:88-91` — the "four cases" comment in `resolveSession` becomes five.
- `sessionCookieOptions` (`auth.ts:191-201`) — its "Omitting maxAge entirely" comment still
  reads correctly, but the surrounding reasoning references the old 1-day backstop. Update the
  number only.
- `Header.tsx:188-191` — add a one-line pointer to `NON_ACTIVITY_PATHS`, so anyone changing the
  poll interval sees that this endpoint is deliberately exempt from the idle clock.

---

## Task breakdown

| # | Task | Files | Depends on |
|---|---|---|---|
| T1 | Migration `0029_session_idle_timeout.sql` + `schema.prisma` | 2 | — |
| T2 | Idle constants; session-only 24h → 8h | `auth.ts` | — |
| T3 | `createSession` writes `lastSeenAt` + `remember` | `auth.ts` | T1, T2 |
| T4 | `isIdleExpired` helper + `resolveSession` enforcement | `auth.ts` | T2, T3 |
| T5 | `touchSession` + `resolveSession({ touch })` | `auth.ts` | T4 |
| T6 | `NON_ACTIVITY_PATHS` + middleware wiring | `middleware.ts` | T5 |
| T7 | Stale comments | `auth.ts`, `Header.tsx` | T2–T6 |
| T8 | Tests | see below | T6 |
| T9 | Cutover (operational) | — | T1–T8 deployed |

### T8 — Tests

Unit tests against the pure helper, which need no server and no waiting:

| Case | `remember` | `lastSeenAt` age | Expect |
|---|---|---|---|
| Fresh session-only | 0 | 5 min | valid |
| Session-only just inside | 0 | 59 min | valid |
| Session-only just outside | 0 | 61 min | **rejected** |
| Remembered, overnight gap | 1 | 14 h | valid |
| Remembered just outside | 1 | 3 d + 1 min | **rejected** |
| Idle disabled | 1 | 30 d | valid (`REMEMBERED_IDLE_SECONDS = null`) |

Integration, in the existing dependency-free `tests/audit/` harness (which already drives the
API over plain `fetch`): log in, backdate the row with
`wrangler d1 execute vega-manager-db --local --command "update sessions set lastSeenAt = ..."`,
then assert the next request 401s. Backdating beats waiting an hour.

Two behavioural tests that guard the parts most likely to silently rot:

1. **Poll does not extend.** Log in, backdate `lastSeenAt` to 58 min, hit `/api/notifications`
   twice, re-read the row — confirm `lastSeenAt` did **not** move and the session still expires
   on schedule. This is the D5 regression test; without it, someone adds a new polling endpoint
   and nobody notices the idle timeout quietly stopped working.
2. **Real request does extend.** Same setup against `/api/projects` — confirm `lastSeenAt` moved
   and the session survives past the original 1-hour mark.

Also re-run the existing `tests/audit/01-auth-session.mjs` unchanged; nothing in this plan should
alter its results.

---

## T9 — Cutover ⚠ operational

**Revoke all existing sessions when this deploys.**

```sql
update sessions set revokedAt = CURRENT_TIMESTAMP where revokedAt is null;
```

Why, rather than relying on the `lastSeenAt` backfill: pre-existing rows have no honest
`remember` value (change 1 defaults them all to `1`, the *lenient* window) and session-only rows
still carry the old 24-hour `expiresAt`. Both resolve themselves within a day, but for that day
the new policy is not actually in force — an unsatisfying state for a security tightening. One
`update` makes the policy uniform from minute one.

Cost is a single forced re-login for everyone. **Deploy outside working hours** — this is an
active client system, and a mass logout mid-afternoon is a support call.

If a forced re-login is unacceptable, skip it: the backfill is safe on its own and the policy
becomes fully effective within 24 hours. Document which option was taken.

---

## Ordering, and what is deliberately NOT in this plan

Do T1–T7 in order (each builds on the last), T8 before deploying, T9 at deploy.

**Relationship to the Azure migration.** Nothing here blocks or is blocked by it, and the design
choices above (D2 `Int` over `Boolean`, D3 JS over SQL date arithmetic, D4 no `ctx.waitUntil()`)
are specifically so this ports with zero rework. If the Azure move is imminent, doing it
**after** is slightly cheaper — `touchSession`'s throttled write is a cheaper operation on
Postgres than on D1, and the migration would otherwise be written twice. Doing it first is fine
too; it just pays the D1 write cost for however long that lasts.

**Not in scope:**

- **A "your session is about to expire" warning.** A 1-hour idle window will surprise users at
  first. A client-side warning at ~55 minutes with a "stay signed in" button is the usual
  companion, but it needs a real activity-ping endpoint and UI, and it is a separate change with
  its own frontend blast radius. Worth doing next; not folded in here.
- **Absolute-lifetime changes to remembered sessions.** 7 days stays.
- **Session rotation on privilege change.** `revokeAllSessionsForUser` already covers
  demote / deactivate / password-reset.
- **Any change to `cleanupExpiredSessions`.** It is called on login (`login/route.ts:96`) and its
  existing `expiresAt < now` sweep still catches idle-expired rows once their absolute cap
  passes. Rows idle-expired but not yet absolute-expired linger until then — harmless, since
  every read enforces the idle check anyway.
- **CSP, edge WAF, or `SESSION_SECRET` rotation.** Tracked separately.
