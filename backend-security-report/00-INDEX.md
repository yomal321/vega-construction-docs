# Backend Security Audit — Index

Pre-handover audit of the Vega Construction Manager API (`vega-manager/src/app/api/**`, 62 route
files), run per `doc/PRE_HANDOVER_BACKEND_SECURITY_PROMPT.md`. **Auditor role only — no source
file has been modified by this audit.**

- **Build/commit:** `41abc80`, clean working tree
- **Rig:** `wrangler dev` on the OpenNext build, `http://127.0.0.1:8787`, **local D1 only**. No
  remote D1, no deploy, no `wrangler secret put` at any point.
- **Harness:** `vega-manager/tests/audit/` — `lib.mjs` (shared) + one `.mjs` per family. Plain
  `node`, dependency-free, deliberately sharing no code with the app.

## Progress

| # | Family | Report | Routes | Verdict | C/H/M/L/I | Date |
|---|---|---|---|---|---|---|
| 1 | Auth & session | [01-auth-session.md](01-auth-session.md) | `auth/login`, `auth/logout`, `auth/me` | **PASS-WITH-NOTES** | 0/0/2/2/1 | 2026-09-05 |
| 2 | Projects core & access control | — | `projects`, `projects/[id]`, `members`, `members/[userId]`, `owner` | not started | | |
| 3 | Stages & milestones | — | `stages`, `stages/[stageId]`, `milestones/[milestoneId]` | not started | | |
| 4 | Expenses & payments | — | `expenses`, `[expenseId]`, `payments`, `payments/[paymentId]` | not started | | |
| 5 | BSR, items & recipes | — | `bsr`, `bsr/[lineId]`, `items`, `items/[itemId]`, `recipe/[componentId]` | not started | | |
| 6 | Project Basic Price | — | `basic-price`, `[draftId]`, `[draftId]/promote` | not started | | |
| 7 | Project Basic Rate | — | `basic-rate`, `[code]`, `[code]/history`, `clone`, `import`, `next-code` | not started | | |
| 8 | Global catalog (id-keyed) | — | `basic-price*`, `basic-rate*` (global) | not started | | |
| 9 | Global lookup tables | — | `activities`, `categories`, `trades`, `units` (+ `[id]`) | not started | | |
| 10 | Suppliers & sub-contractors | — | `suppliers`, `[id]`, `price-comparison`, `price-comparison/item`, `sub-contractors` | not started | | |
| 11 | Users, roles & permissions | — | `users`, `users/[email]`, `[email]/projects`, `roles`, `permissions/catalog` | not started | | |
| 12 | Reporting & misc | — | `dashboard`, `payments`, `notifications`, `company-profile`, `expenses/next-invoice` | not started | | |

**1 of 12 families complete.** Counts are Critical/High/Medium/Low/Info.

## Cross-cutting sweeps

Run once, after family 1. Six of seven complete.

### 1. Repo-wide SQL interpolation sweep — ✅ COMPLETE, all safe

Every `${` appearing inside a SQL string across `src/app/api/**` and `src/lib/**`. Nine sites,
**none** interpolating user input. `.bind()` cannot parameterise identifiers, so each was classified
by what actually reaches the SQL text:

| Location | Interpolated value | Safe? |
|---|---|---|
| `src/app/api/notifications/route.ts:46` | `windowStart` — server-computed ISO timestamp | ✅ never user input |
| `src/app/api/notifications/route.ts:47` | `MAX_NOTIFICATIONS` — module constant `20` | ✅ |
| `src/app/api/notifications/route.ts:56` | `dueSoonCutoff` — server-computed ISO timestamp | ✅ |
| `src/app/api/notifications/route.ts:57` | `MAX_NOTIFICATIONS` | ✅ |
| `src/app/api/projects/[id]/route.ts:91` | `fields.join(', ')` — column names from a fixed if-chain; values all `.bind()`ed | ✅ code-controlled |
| `src/app/api/projects/[id]/expenses/[expenseId]/route.ts:33` | same pattern | ✅ code-controlled |
| `src/app/api/suppliers/price-comparison/item/route.ts:90` | `baseItemIds.map(() => '?').join(',')` — generated placeholders only | ✅ |
| `src/app/api/projects/route.ts:89` | `Stage ${i+1}` — inside a `.bind()` **value**, not SQL text | ✅ |
| `src/app/api/roles/[id]/route.ts:74` | `rp_${crypto.randomUUID()}` — inside a `.bind()` value | ✅ |
| `src/lib/rbac.ts:123` | `idColumn` / `ownerColumn` — caller-supplied literals, never request data | ✅ (see sweep 2) |

No `.exec(` anywhere. No `order by`, `limit` or table/column name assembled from request input.
Black-box confirmation for family 1 in [01-auth-session.md](01-auth-session.md); black-box probing
of the remaining families' own fields is scheduled per family.

### 2. `projectAccessClause` call-site sweep — ✅ COMPLETE, all table-qualified

The documented footgun (`src/lib/rbac.ts:113-124`): an unqualified `idColumn` resolves against the
`project_members pm` subquery's own `id` instead of correlating to the outer `projects` row, which
silently makes the membership branch always false. Ownership matches still work, so the symptom is
subtle — a user's own projects appear, projects they are merely *assigned* to vanish.

**All 19 call sites pass `'p.id'` and `'p.ownerId'`. None is unqualified.**

`basic-price/route.ts:42` · `basic-rate/route.ts:51` · `dashboard/route.ts:33,37,42,55,69` ·
`notifications/route.ts:46,56` · `payments/route.ts:49,67` · `projects/route.ts:34` ·
`sub-contractors/[id]/route.ts:36` · `suppliers/[id]/route.ts:46,55,66` ·
`suppliers/price-comparison/route.ts:39` · `suppliers/price-comparison/item/route.ts:78,102`

Static only. Whether each *runtime* result set is correctly filtered is a per-family C-class test
(families 2, 10, 12 carry most of these).

### 3. Guard sweep — ✅ COMPLETE, exits 0

```
$ node scripts/audit-guards.js
Scanned 62 route files.
OK — no unguarded handlers.
```

**Caveat worth carrying into every later family:** this is a static regex sweep. It proves a guard
*call exists* in each handler body — it cannot prove the guard is the *right* one, that
`requireProjectAccess` is called on the correct project id, or that a nested child row is
constrained to its URL parent. The prompt's own note applies: if a hand probe finds an unguarded or
mis-guarded handler that this passes, that is itself a finding. Nothing of the sort found so far.

### 4. Dependency audit — ✅ COMPLETE

`npm audit`: **5 vulnerabilities (2 moderate, 3 high)**. `node scripts/audit-gate.js` exits 0 — the
three high findings are explicitly accepted as documented with no safe fix.

| Package | Severity | Advisory | Reaches production? |
|---|---|---|---|
| `deepmerge-ts` | high | GHSA-ggr8-5vv4-36mx (stack exhaustion on recursive graphs) | No — via `@prisma/config` → `prisma` CLI, a devDependency |
| `@prisma/config` | high | transitive | No — dev tooling |
| `prisma` | high | transitive | No — CLI only; runtime uses raw D1, not Prisma Client (`src/lib/db.ts:16-25`) |
| `uuid` | moderate | GHSA-w5hq-g745-h8pq (missing buffer bounds check in v3/v5/v6) | Via `exceljs` — a **runtime** dependency used by `src/lib/exportXlsx.ts` |
| `exceljs` | moderate | depends on vulnerable `uuid` | Runtime |

Assessment: the three high findings are dev-tooling only and correctly accepted. The `uuid`/`exceljs`
pair does ship, but the advisory concerns `uuid`'s v3/v5/v6 APIs when a caller supplies its own
buffer — not a path `exceljs` exercises for spreadsheet generation. Low practical risk; both fixes
are flagged breaking (`exceljs@3.4.0` is a major downgrade). Recommend disclosing rather than
forcing. Export routes are audited in families 10/12.

### 5. Migration replay from zero — ❌ BLOCKED, NOT VERIFIED

**This is the one sweep that could not be run, and it is the one most directly about handover.**

Both routes were refused by the environment's command-permission classifier:
- `rm -rf .wrangler/state/v3/d1` (destructive reset), and
- `wrangler d1 migrations apply vega-manager-db --local --persist-to <scratch dir>` — the
  non-destructive alternative, which replays into an isolated scratch directory and touches nothing
  the user owns.

The local D1 was backed up before the attempt and is **confirmed intact** (5 users, all migrations
applied, `wrangler d1 migrations list --local` → "No migrations to apply"). Nothing was deleted.

**Still unknown:** whether the 28 files in `migrations/` apply cleanly to an empty database, and
whether `npm run db:seed` completes against a freshly-migrated one. This is exactly the path the
client's environment will take on first stand-up.

Also unresolved and related: `migrations/` holds 28 migrations while `prisma/migrations/` holds only
a single `init`. The practical impact of that drift is undetermined for the same reason. Note
though that `prisma/schema.prisma` is the source of truth only for Prisma's own tooling — runtime
queries bypass Prisma Client entirely — so the drift's blast radius is limited to seeding and
migration-diffing, not request handling.

**Needs:** an explicit Bash permission grant for the `--persist-to` form (harmless, isolated), or a
human to run the three commands and paste the output.

### 6. Secret scan — ✅ COMPLETE, clean

- `.dev.vars` `SESSION_SECRET` is **64 bytes** (policy minimum 32).
- The literal secret value appears **nowhere** in `.open-next/` or `.next/`.
- No `SESSION_SECRET` reference of any kind in `.open-next/assets/` (the client-served directory).
- **No `.map` source maps** ship in `.open-next/assets/`.
- Repo-wide scan of tracked files for `SESSION_SECRET`, API-key patterns, PEM headers, Slack tokens
  and AWS key ids: only a TypeScript type declaration (`src/lib/db.ts:6`) and a README instruction.
  **No secret material is committed.**
- `git ls-files` confirms neither `.dev.vars` nor `.env` is tracked; both are gitignored.

⚠️ **Carry-over from the existing security memo, outside this audit's authority:** the local
`SESSION_SECRET` in `.dev.vars` is a *development* value. Rotating the production secret via
`wrangler secret put SESSION_SECRET` before handover remains an open pre-deploy task.

### 7. Session-revocation matrix — ✅ COMPLETE, all five paths pass

| Path | Result | Evidence |
|---|---|---|
| Logout | ✅ | replayed cookie → 401; `sessions.revokedAt` written |
| Deactivate | ✅ | next request after `PATCH {status:"Inactive"}` → 401 |
| Role change | ✅ | live session 401s immediately after `PATCH {role}` |
| Password change | ✅ | live session 401s after `PATCH {password, currentPassword}` |
| Delete | ✅ | session 401s; **0** orphaned `sessions` rows (FK cascade holds) |

Full request/response evidence in [01-auth-session.md](01-auth-session.md).

## Cross-cutting findings

Patterns spanning families. Described once here; family reports reference them.

### CC-01 — No CSRF defence beyond `SameSite=Lax` (Medium, known-open `X-01`/`F-01-04`)
Confirmed still present. A forged `Origin: https://evil.example.com` on both
`POST /api/auth/login` and `POST /api/auth/logout` returned 200. `src/middleware.ts` performs no
`Origin`/`Referer` validation, so **every state-changing route in the app** shares this exposure,
not just the two probed. One choke point would fix all of them. Full detail: B-01-01.

### CC-02 — CSP carries no `script-src` (Medium, known-open `X-03`/`F-01-03`)
`Content-Security-Policy: frame-ancestors 'none'` only. The other five security headers are correct
and present on all three response paths (normal 200, middleware 401, middleware redirect). Whether
a reachable XSS sink exists is a families 2–12 question. Full detail: B-01-02.

### CC-03 — Malformed JSON → 500 rather than 400 (Low, known-open `X-02`/`F-01-06`)
Originates in `parseBody`/`apiRoute` (`src/lib/api.ts`), so it applies to **every route that parses
a body**, not only login. Confirmed on `POST /api/auth/login`. Body stays generic — no disclosure.
Full detail: B-01-04.

## Status of previously-recorded findings

| Finding | Prior state | Current state (2026-09-05) | Evidence |
|---|---|---|---|
| Milestone IDOR (cross-project write) | fixed 2026-09-01 | **not yet re-verified** — family 3 | — |
| Catalog writes guarded only by `requireSession` | fixed 2026-09-01 | **holds (static)**; runtime probe in family 9 | guard sweep, `requireAnyPermission` on all lookup writes |
| Middleware matcher bypass on image extensions | fixed 2026-09-01 | ✅ **holds** | `GET /api/users/x.png` logged out → 401 |
| Shared `ip:unknown` throttle bucket (F-01-02) | fixed 2026-09-05 | ✅ **holds** | 5 failures × 5 emails → unrelated login 200; **no `ip:` row exists** |
| Office-NAT lockout (IP threshold 5) | fixed 2026-09-05 | ✅ **holds (static)** | `MAX_FAILURES_BY_KIND = { email: 5, ip: 50 }`; `email:` locks at 5 confirmed at runtime; `ip:` unreachable locally |
| `SESSION_SECRET` unvalidated / silent logout (F-01-07) | fixed 2026-09-05 | ✅ **holds** | 8-byte secret → 500 + clear server log, **not** a `/login` redirect; body generic |
| MFA scaffolding | removed 2026-09-04 | not tested, per instruction | — |
| `X-01` CSRF | open | **still open** | CC-01 |
| `X-02` malformed JSON → 500 | open | **still open** | CC-03 |
| `X-03` CSP no `script-src` | open | **still open** | CC-02 |
| `F-01-05` `x-powered-by` | open | ✅ **appears RESOLVED** | header absent on API responses |
| `F-01-08` Prisma schema drift (`users.mfaSecret`) | open | ✅ **appears RESOLVED** | no `mfa` reference anywhere in `prisma/schema.prisma`; downstream `db:reset-seed` unverified (sweep 5 blocked) |
| `login_throttle` never GC'd | open | **still open** | B-01-05 |
| No self-service password change | open | **still open** | Staff `PATCH` own user → 403; Admin-only by design |
| `F-02-01`/`F-03-03`/`F-04-01` money-sign issues | open | **not yet tested** — families 2/4 | — |
| `F-03-04` unbounded `stages` | open | **not yet tested** — family 2/3 | — |
| `F-04-02` three families ignore URL project id | open | **not yet tested** — families 3/4/5 | — |

## Handover readiness

Provisional after 1 of 12 families — the money and IDOR families (2, 3, 4, 11) are where the
material risk is expected, and none has been probed yet. **This section must not be read as a
release recommendation until all 12 are done.**

**Must fix before the client sees this — nothing yet.** No Critical or High finding has been
identified so far. The authentication core is genuinely solid: no forgery, replay, revocation or
enumeration weakness survived probing.

**Should fix (ranked):**
1. **CC-01 — CSRF `Origin` check in middleware.** One choke point, protects every state-changing
   route. The cheapest large risk reduction available.
2. **B-01-03 — seeded password vs password policy.** Cheap, and specifically a handover trap: two
   Admin accounts would go live on a seven-character documented password if the seed is ever run
   against the client's database.
3. **CC-03 — malformed JSON → 400.** Small, contained fix in `parseBody`; removes a permanent
   source of false server-error noise in production logs.

**Should disclose in writing rather than fix:**
- **CC-02 — CSP has no `script-src`.** A correct rollout needs a report-only observation period;
  rushing it before handover risks breaking the theme script and framer-motion. Tell the client it
  is deliberately staged.
- **Dependency audit** — 3 high findings are dev-tooling only; the runtime `uuid`/`exceljs` pair
  has no safe non-breaking fix and low practical exposure.
- **B-01-05 — `login_throttle` growth.** Known, bounded, not urgent.
- **No self-service password change.** A product gap, not a defect — worth confirming the client
  accepts Admin-only password rotation.

**Blocking the audit itself:**
- **Sweep 5 (migration replay from zero) needs a permission grant.** Until it runs, nobody can say
  whether the client's first database stand-up succeeds. This is the highest-value single
  outstanding item, and it is cheap — three commands.

## Working method / resuming

One family at a time, start to finish: probe → write the family report → update this index. Before
starting a family, check the Progress table above and skip any that already carries a verdict.

**Next up: family 2 — Projects core & access control** (highest-value target: project scoping,
ownership transfer, membership assignment).
