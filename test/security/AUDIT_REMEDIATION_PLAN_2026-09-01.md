# Audit Remediation Plan — 2026-09-01

**Date:** 2026-09-01
**Source:** pre-handover audit of areas A–D in `BACKEND_TEST_PLAN.md` (authentication, RBAC,
project scoping/IDOR, admin surface).
**Scope:** three confirmed findings, plus one supporting change to the guard sweep that
allowed finding 2 to pass unnoticed.

**Design constraint for every task below: change only what the finding requires.** No
refactors, no renames, no reformatting of surrounding code, no new dependencies. Every task
lists its exact blast radius, and each was checked against the real callers before being
written down — see the "Verified before writing" note under each fix.

---

## Summary

| # | Finding | Severity | Files touched | Frontend change needed | Status |
|---|---|---|---|---|---|
| 1 | Cross-project milestone write (IDOR) | **Critical** | 1 | No | ✅ Done |
| 2 | Catalog write endpoints have no permission check | **High** | 6 | No | ✅ Done |
| 3 | Middleware matcher bypass on image extensions | Low-Med | 1 | No | ✅ Done |
| 4 | Guard sweep accepts `requireSession` as sufficient | Supporting | 1 | No | ✅ Done |

Total: **9 files**, all under `vega-manager/`. No schema change, no migration, no data
backfill, no dependency change.

**Update 2026-09-05 — all four fixes verified against the live tree, including runtime.**
Every file listed above matches the exact edits described in this plan, and
`node scripts/audit-guards.js` exits 0 (62 route files scanned, no unguarded handlers).
On top of that code-level re-read, the manual verification steps under each fix were run
for real against `npm run preview` (D1 bindings under the actual Workers runtime, local
`vega-manager-db`), using temporary role/membership grants that were removed afterward:

- **Fix 1 (IDOR):** as a Staff user with access to P2 only, `PATCH .../projects/p2/stages/{p2
  stage}/milestones/{a P1 milestone's id}` → **404**, P1's milestone unchanged in the DB. The
  same user's legitimate PATCH on their own P2 milestone still → 200 and the DB updated.
- **Fix 2 (catalog guards):** `GET /api/units` → 200 for a Staff user with zero permissions;
  `POST /api/units` → 403 for the same user; `PATCH /api/units/{id}` and `DELETE
  /api/trades/{id}` → 403 for both a zero-permission Staff user *and* a Staff user holding
  `projects:edit` (confirming PATCH/DELETE really is Admin-only, not just any permission);
  `POST /api/trades` and `POST /api/categories` → 200 for the `projects:edit` Staff user
  (the estimator create-path regression check). As Admin: created a unit, renamed it, and
  confirmed the rename cascaded into both a `base_items` and a `basic_price_items` row
  referencing it by name; `DELETE` on the in-use unit → 409 until the referencing rows were
  removed.
- **Fix 3 (middleware matcher):** logged out, `/login` → 200, `/logo.jpg` → 200 (root-level
  bypass still works), `/api/users/x.png` → 401.

All test fixtures (temp role/membership grants, synthetic catalog rows, synthetic
`base_items`/`basic_price_items` rows) were deleted afterward and the DB was confirmed back
to its pre-test state.

---

## Fix 1 — Cross-project milestone write (IDOR)

**Status: ✅ Done** — the join-check is in place exactly as specified below (verified 2026-09-05).

**File (the only one):**
`src/app/api/projects/[id]/stages/[stageId]/milestones/[milestoneId]/route.ts`

### The defect

Line 14 types the params as `{ id, milestoneId }` — `stageId` is present in the URL but never
destructured. Line 17 authorizes against the URL's `[id]`, then all four writes key on the
milestone alone (`:21`, `:26`, `:31`, `:32`, `:33`):

```
update milestones set status = ? where id = ?
```

`milestones` carries no `projectId`; it reaches a project only via `stageId → stages.projectId`,
and nothing in this file joins `stages`. A user with `projects:edit` on any one project can
therefore write to any milestone in the database by putting their own project id in the path.

### The change

Three edits, all inside this one file:

1. Widen the generic so `stageId` is typed:
   `apiRoute<{ id: string; milestoneId: string }>` → `apiRoute<{ id: string; stageId: string; milestoneId: string }>`
2. Destructure it: `const { id: projectId, stageId, milestoneId } = await params`
3. After `const db = await getDb()` and **before the first write**, add the ownership check:

```ts
// milestones has no projectId of its own — it belongs to a project only through its stage.
// Without this join the writes below key on milestoneId alone, so any caller with access to
// ANY project could patch a milestone belonging to another one. Mirrors the same guard the
// sibling stage route already does at stages/[stageId]/route.ts:27.
const milestone = await db
  .prepare('select m.id from milestones m join stages s on s.id = m.stageId where m.id = ? and m.stageId = ? and s.projectId = ?')
  .bind(milestoneId, stageId, projectId)
  .first<{ id: string }>()
if (!milestone) return NextResponse.json({ error: 'Not found' }, { status: 404 })
```

Placed after `parseBody`, matching the ordering the sibling `stages/[stageId]/route.ts` already
uses (auth → parse → existence check → write). Nothing else in the file changes; the four
conditional write blocks stay exactly as they are.

### Blast radius

**None on the frontend — verified, not assumed.** All four callers live in
`src/app/projects/[id]/client.tsx` (`:197`, `:221`, `:230`, `:240`) and every one of them builds
the URL from `stages[stageIdx]` and takes the milestone from *that same stage's* own
`.milestones[msIdx]` array. The stage/milestone pair is therefore always genuinely
parent/child, so the new constraint passes for every legitimate call. No client change.

### Verification

- Legitimate path: change a milestone's status, amount, cheque date and due date from the
  project page — all four still succeed, dashboard figures still update.
- Attack path: as Staff user B (owner of project P2 only), issue
  `PATCH /api/projects/{P2}/stages/{any}/milestones/{milestone id from P1}` with
  `{"status":"paid"}` — must return **404**, and P1's milestone must be unchanged in the DB.
- Regression: confirm the "mark Advance paid → auto-fills stage startDate" convenience
  (`client.tsx:206-213`) still fires, since it issues a second request after the milestone PATCH.

---

## Fix 2 — Catalog write endpoints have no permission check

**Status: ✅ Done** — `requireAnyPermission` added to `rbac.ts`, all three POST handlers use it,
all six PATCH/DELETE handlers use `requireAdmin`, and both rename cascades (units, trades) are
batched exactly as specified (verified 2026-09-05).

**Files (6):**
`src/app/api/units/route.ts`, `src/app/api/units/[id]/route.ts`,
`src/app/api/trades/route.ts`, `src/app/api/trades/[id]/route.ts`,
`src/app/api/categories/route.ts`, `src/app/api/categories/[key]/route.ts`

### The defect

All nine write handlers guard with bare `requireSession()`. Any authenticated user — including
a Staff account with zero roles and zero direct grants — can create, rename or delete the
global units, trades and categories that every project's Basic Price and Basic Rate depend on.
They back the admin-only `/settings/field-options` page, so this is the classic
UI-gated-but-API-open pattern.

### Verified before writing: the guard must be asymmetric

Grepping the real callers of `CatalogProvider`'s mutations shows **create and edit/delete have
different audiences**, and gating all nine on `requireAdmin()` would break a working non-admin
flow:

| Mutation | Called from | Audience |
|---|---|---|
| `addCategory` / `addTrade` / `addUnit` | `src/app/basic-price/page.tsx:157,226,227,268,269` and `src/app/projects/[id]/client.tsx:3204,3282,3283,3323,3324` | **Non-admin.** `offerToSaveOption()` (`basic-price/page.tsx:182`) prompts "Add *X* as a new option?" when a user types a custom Trade/Unit while adding **or editing** a Basic Price draft. |
| `updateCategory` / `updateTrade` / `updateUnit` / `delete*` | `src/app/settings/field-options/page.tsx:42-72` **only** | Admin (page sits behind the `/settings` prefix in `ADMIN_ONLY_PREFIXES`). |

So the create path is a legitimate estimator workflow and must keep working. Note also that
the **add** flow needs `projects:create` (`addDraft` → `POST /api/basic-price:58`) while the
**edit** flow needs `projects:edit` (`PATCH /api/basic-price/[draftId]:23`) — both reach
`offerToSaveOption`. Gating on either single action alone would break the other flow.

### The change

**2a — Guards.** GET stays `requireSession()` in all three files (the whole app reads these
through `CatalogProvider`, and they are non-sensitive lookup lists).

| Handler | From | To |
|---|---|---|
| `POST /api/units`, `/api/trades`, `/api/categories` | `requireSession()` | `requireAnyPermission('projects', ['create', 'edit'])` |
| `PATCH`/`DELETE` on `/api/units/[id]`, `/api/trades/[id]`, `/api/categories/[key]` | `requireSession()` | `requireAdmin()` |

Add one small helper to `src/lib/rbac.ts` beside `requirePermission` — needed because no single
existing action covers both catalog-item flows:

```ts
// Passes if the session holds ANY of the listed actions on the module. Used by the global
// lookup tables (units/trades/categories), which are written from both the add-draft flow
// (projects:create) and the edit-draft flow (projects:edit) via offerToSaveOption().
export async function requireAnyPermission(module: Module, actions: Action[]): Promise<SessionPayload> {
  const session = await requireSession()
  for (const action of actions) {
    if (await hasPermission(session, module, action)) return session
  }
  throw new AuthError(403, 'Not allowed')
}
```

If you would rather add no helper at all, the fallback is to gate the three POSTs on
`requirePermission('projects', 'edit')` and accept that a hypothetical create-only-without-edit
role loses the inline "add this option" prompt. No such role exists in the seed data, but the
helper is the option that cannot surprise anyone.

**2b — Rename cascade (units and trades only).** `PATCH` renames the row but leaves every
referencing item pointing at the old text, because these are stored by value, not by FK:

- `units.name` ← referenced by `base_items.unit` **and** `basic_price_items.unit`
- `trades.name` ← referenced by `basic_price_items.trade` only (`base_items` has no `trade` column)
- **categories need no cascade** — `basic_price_items.cat` / `base_items.cat` store the
  immutable `key`, and `PATCH /api/categories/[key]` only changes `label` and `color`
  (prefix is deliberately not editable, `categories/[key]/route.ts:18-19`). Leave this file's
  PATCH body alone; change only its guard.

For `units/[id]` and `trades/[id]`, replace the single bare `update` with a load-check-cascade,
batched so the two halves cannot land separately:

```ts
const existing = await db.prepare('select name from units where id = ?').bind(id).first<{ name: string }>()
if (!existing) return NextResponse.json({ error: 'Not found' }, { status: 404 })
if (existing.name === name) return NextResponse.json({ ok: true })

const clash = await db.prepare('select id from units where name = ? and id != ?').bind(name, id).first()
if (clash) return NextResponse.json({ error: `"${name}" already exists` }, { status: 409 })

// base_items.unit / basic_price_items.unit hold the unit by NAME, not by FK — a rename has to
// carry every referencing row with it or those rows point at a unit that no longer exists.
// Batched so the rename and its cascade can never land half-applied.
await db.batch([
  db.prepare('update units set name = ? where id = ?').bind(name, id),
  db.prepare('update base_items set unit = ? where unit = ?').bind(name, existing.name),
  db.prepare('update basic_price_items set unit = ? where unit = ?').bind(name, existing.name),
])
```

The trades version is the same shape with one cascade statement
(`update basic_price_items set trade = ? where trade = ?`).

This also closes the DELETE bypass: previously you could rename a unit, making the in-use count
for the new name zero, and then delete it — orphaning every item still on the old name. With
the cascade, the in-use count follows the rename, so `DELETE`'s existing 409 guard
(`units/[id]/route.ts:31`) does its job.

The duplicate-name check on PATCH is included because the rename cascade makes it load-bearing:
renaming "m3" onto an existing "kg" would otherwise merge two units' items silently. `POST`
already performs the equivalent check (`units/route.ts:24`).

### Blast radius

- Admin: unchanged everywhere (`requireAdmin` passes; `hasPermission` Admin-bypasses at `rbac.ts:61`).
- Estimator with `projects:create` or `projects:edit`: inline "add this Trade/Unit/Category"
  prompt keeps working exactly as now.
- Staff with no permissions: loses write access to the lookup tables — **this is the fix**.
  Read access via `CatalogProvider` is untouched, so no page breaks.
- `src/components/CatalogProvider.tsx` is **not** modified. Its mutators already surface
  `{ error }` from non-OK responses (`:144-147`, `:163-166`, `:180-183`), so a 403 renders as a
  toast rather than an unhandled rejection. `updateUnit`/`updateTrade`/`updateCategory` ignore
  the response body entirely (`:152`, `:169`, `:186`), so a 403 there fails silently in the UI —
  acceptable, since only the admin page calls them and an admin never gets a 403.

### Verification

- As Admin: add, rename and delete a unit, a trade and a category on `/settings/field-options`.
- As a Staff user with `projects:edit`: type a custom Trade and Unit on a Basic Price draft,
  confirm both prompts, confirm both save.
- As a Staff user with **no** role: `POST /api/units` → 403; `PATCH /api/units/{id}` → 403;
  `DELETE /api/trades/{id}` → 403; `GET /api/units` → 200.
- Rename cascade: create a Basic Price draft using unit "m3", rename the unit to "cu.m", then
  confirm the draft now reads "cu.m" and that deleting that unit returns 409, not success.

---

## Fix 3 — Middleware matcher bypass

**Status: ✅ Done** — matcher uses `[^/]*`, with the explanatory comment in place (verified 2026-09-05).

**File:** `src/middleware.ts` (line 48)

### The defect

```
matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|webp)$).*)']
```

`.` matches `/` in JavaScript regex, so `.*\.(?:svg|png|jpg|jpeg|webp)$` matches any path
ending in one of those extensions **at any depth** — including `/api/users/x.png`, which
therefore skips middleware entirely. Not currently exploitable, because every handler carries
its own guard, but the outer layer is thinner than it appears.

### The change

One character class:

```
.*\\.(?:svg|png|jpg|jpeg|webp)$   →   [^/]*\\.(?:svg|png|jpg|jpeg|webp)$
```

`[^/]*` cannot cross a path separator, so the exclusion now only matches a **root-level**
filename. `/logo.jpg` still bypasses middleware; `/api/users/x.png` no longer does.

### Blast radius

`public/` contains exactly one file, `logo.jpg`, and it is referenced from
`src/app/layout.tsx:23` (favicon), `src/app/login/page.tsx:54` and `src/components/Sidebar.tsx:113`.
The login page is unauthenticated, so `/logo.jpg` **must** keep bypassing middleware — and it
does, being root-level. `_next/static`, `_next/image` and `favicon.ico` keep their own separate
exclusions, untouched.

Worth a one-line comment above the matcher recording why it is `[^/]*` and not `.*`, so nobody
"simplifies" it back.

### Verification

- Log out, load `/login`, confirm the logo renders and the favicon appears.
- Logged out, `GET /api/users/x.png` → 401 from middleware (previously it reached the handler
  and 401'd there — either way it is refused, but the outer layer should now be the one doing it).
- Confirm normal page navigation and API calls are unaffected.

---

## Fix 4 — Tighten the guard sweep (supporting)

**Status: ✅ Done** — `WRITE_GUARD_RE`/`WRITE_METHODS` in place, `requireAnyPermission` covered
by both regexes, and `node scripts/audit-guards.js` exits 0 against the fixed tree (verified 2026-09-05).

**File:** `scripts/audit-guards.js`

Finding 2 passed the existing sweep because `GUARD_RE` (line 25) accepts **any** of
`requireSession|requireAdmin|requirePermission|getSession`. A write handler guarded only by
`requireSession` is therefore reported as fine.

Change: keep the current regex for `GET`, and require a *stronger* guard for mutating methods:

```js
const GUARD_RE = /require(Session|Admin|Permission)|requireAnyPermission|getSession/
const WRITE_GUARD_RE = /requireAdmin|requirePermission|requireAnyPermission/
const WRITE_METHODS = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])
```

and select which to test per handler by method. `requireAnyPermission` must be added to both,
or Fix 2's three POST handlers will be reported as unguarded.

This would have caught finding 2 on its own, and it is the thing that stops the class from
reappearing — the sweep already runs in CI beside the `npm audit` gate.

---

## Ordering, and what is deliberately NOT in this plan

Do them in this order; each is independent, so a problem with one does not block the others:

1. **Fix 1** — critical, smallest, no decisions needed.
2. **Fix 3** — one character, no decisions needed.
3. **Fix 2** — largest; needs the `requireAnyPermission` vs. single-action decision made first.
4. **Fix 4** — last, so the tightened sweep runs against the already-fixed tree and exits 0.

After all four: run `node scripts/audit-guards.js` (must exit 0), then the manual verification
steps listed under each fix against `npm run preview` — **not** `next dev`, since D1 bindings
only resolve under the Workers runtime.

**Explicitly out of scope here** (tracked separately, not to be folded into these commits):
CSP (Phase 6) and edge rate limiting (Phase 7) from `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md`;
`SESSION_SECRET` presence/length validation; the shared `ip:unknown` throttle bucket; the
missing self-service password change; `login_throttle` garbage collection; the drift between
`prisma/migrations/` and the live `migrations/` set; and ~~the dead MFA leftovers
(`src/lib/totp.ts`, `src/lib/mfaCrypto.ts`, empty `src/app/account/mfa/`, migration `0025`)~~.
Each is real; none belongs in a security-fix commit for these three findings.

**Update 2026-09-04 — the dead-MFA item is closed.** The client declined MFA outright, so it was
removed rather than completed: `0026_remove_mfa.sql` drops the three `users` columns and the
`mfa_recovery_codes` table, and `src/lib/totp.ts`, `src/lib/mfaCrypto.ts`,
`src/app/api/auth/mfa/*` and `src/app/account/` are deleted. This audit's read of the situation
was correct — the code advertised a feature it never served. A side benefit: since
`prisma/schema.prisma` had never declared 0025's columns, dropping them also closed that piece of
schema drift instead of widening it.
