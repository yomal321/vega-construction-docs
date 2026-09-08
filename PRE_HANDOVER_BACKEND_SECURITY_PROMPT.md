# Pre-Handover Backend Security Audit — API-by-API Test & Report Prompt

Companion to `doc/PRE_HANDOVER_QA_PROMPT.md`. That one audits the app **page by page** through the
UI. This one audits the **backend API surface directly** — all 62 route handlers under
`src/app/api/**` — with security as the primary lens, because a hidden button is not
authorisation and the UI cannot tell you what the server actually permits.

Paste the whole of the section below into Claude Code (from the working directory
`d:\Bistec Intern Project\vega construction`). It is written to be **resumable** — run it
repeatedly and it picks up the next untested route family each time.

---

## THE PROMPT

You are performing a **pre-handover backend security audit** of the Vega Construction Manager
API (`vega-manager/src/app/api/**`) before it is delivered to the client. Your job is to **test
and report** — route family by route family, exhaustively, at the HTTP level.

### Ground rules (read these first, they override any instinct you have)

1. **DO NOT FIX ANYTHING.** No source edits, no refactors, no "while I was here" cleanups. You
   are an auditor, not an implementer. The only files you may create or modify are the report
   files described below and test scripts under `vega-manager/tests/`.
2. **NEVER touch the remote/production database or deploy.** Run every test against the
   **local** D1 only. Do not run `npm run db:migrate:remote`, `wrangler ... --remote`,
   `npm run deploy`, or `wrangler secret put`. Confirm before any command that writes to a
   remote target.
3. **Test at the HTTP layer, not through the UI.** Use `curl`/`fetch` against the running
   Worker. A route that the UI never calls with hostile input is exactly the route that has
   never been tested with hostile input.
4. **Report, don't speculate.** Every finding needs concrete evidence: the exact request (method,
   path, headers, body), the actual response (status + body), and the `file:line` of the
   responsible code. If you suspect an issue but cannot reproduce it, file it as `Unconfirmed`
   and say exactly what you tried.
5. **One report file per route family.** Never merge two families into one report.
6. **Do not re-report already-closed findings as new.** See "Already fixed — verify, don't
   rediscover" below. Confirming a fix still holds is valuable; filing it as a fresh finding is
   noise.

### Environment setup (do this once, before testing)

```bash
cd vega-manager
npm install
npx wrangler d1 migrations apply vega-manager-db --local
npm run db:seed
npm run preview     # builds via OpenNext + serves through wrangler dev
```

**Critical:** `next dev` does **not** resolve the D1 bindings, so every API route 500s under it.
You must test against the Workers runtime (`npm run preview`, typically
`http://127.0.0.1:8787`). Note the port it prints.

**Also critical:** `.dev.vars` must contain a `SESSION_SECRET` of **at least 32 bytes**. Since
2026-09-05 the app validates this and returns 500 on every request if it is shorter — that is
intended behaviour, not a bug (see F-01-07 below).

Useful helpers that already exist — reuse them rather than rewriting:
- `vega-manager/tests/helpers.ts` — `execLocalSql()`, `queryLocalDb()`, `clearLoginThrottle()`,
  and the seeded account constants. Read the comments in it; they encode real Windows/wrangler
  traps that cost time to rediscover.
- `vega-manager/scripts/audit-guards.js` — the per-handler auth-guard sweep, already wired into CI.

### Test accounts (from `prisma/seed.ts`, password `vega123` for all)

| Email | Role | Use it to test |
|---|---|---|
| `nimal@vegahomes.lk` | Admin | full-access baseline; Admin bypasses RBAC entirely |
| `sanduni@vegahomes.lk` | Admin | second admin — concurrency, last-admin guards |
| `kasun@vegahomes.lk` | Staff | permission denial, project-scope isolation |
| `dilini@vegahomes.lk` | Staff | **the key IDOR probe** — can Dilini reach a project only Kasun owns/is a member of? |
| `ruwan@vegahomes.lk` | Staff, **Inactive** | must be refused login and must hold no usable session |

You will also need a **Staff user with zero roles and zero direct permission grants** — create
one via the API as Admin, or via `execLocalSql`. This is the account that catches
"authenticated but unauthorised" holes, which is the single most productive probe in this
codebase (it is exactly what found the unguarded catalog writes on 2026-09-01).

### Architecture you must understand before you start

Read these first — the audit is much less effective without them:

- `src/lib/api.ts` — `apiRoute()` wraps **every** handler; maps `AuthError` → its status,
  `ZodError` → 400, everything else → generic 500 (logged, not leaked). `parseBody()` validates
  against a Zod schema.
- `src/lib/rbac.ts` — **two independent authorisation layers**, and you must test both:
  1. **Module permissions** — `requirePermission(module, action)` against `PERMISSION_CATALOG`
     (`dashboard`, `projects`, `activities`, `suppliers`, `payments`, `priceComparison`).
     Admin bypasses entirely.
  2. **Project reach** — `requireProjectAccess(session, projectId)` — owner OR assigned member
     OR admin. Membership grants *visibility only*, never any module permission.
  - `projectAccessClause()` has a documented footgun: `idColumn` **must** be table-qualified
    (`'p.id'`). An unqualified `'id'` silently makes the membership branch always false, so a
    project a user is merely *assigned* to quietly vanishes while their own still shows. Grep
    every call site.
- `src/lib/db.ts` — queries go **straight to D1 as raw SQL**, not through Prisma Client. SQL
  injection is therefore a genuine risk area here, not a formality.
- `src/lib/auth.ts` — JWT carries only `{ sid }`; role/status are re-read from the DB on every
  request via `resolveSession`. Sessions are revocable (`revokedAt`).
- `src/middleware.ts` — coarse gate only (auth + `ADMIN_ONLY_PREFIXES`). **Never assume it is the
  real defence** — per-handler guards are.

### Route families to audit (12 total, 62 route files)

Work through them in this order. Each row is one report file.

| # | Family | Routes | Report file |
|---|---|---|---|
| 1 | Auth & session | `auth/login`, `auth/logout`, `auth/me` | `01-auth-session.md` |
| 2 | Projects core & access control | `projects`, `projects/[id]`, `projects/[id]/members`, `members/[userId]`, `projects/[id]/owner` | `02-projects-access.md` |
| 3 | Stages & milestones | `projects/[id]/stages`, `stages/[stageId]`, `stages/[stageId]/milestones/[milestoneId]` | `03-stages-milestones.md` |
| 4 | Expenses & payments | `projects/[id]/expenses`, `[expenseId]`, `[expenseId]/payments`, `payments/[paymentId]` | `04-expenses-payments.md` |
| 5 | BSR, items & recipes | `projects/[id]/bsr`, `bsr/[lineId]`, `items`, `items/[itemId]`, `items/[itemId]/recipe/[componentId]` | `05-bsr-items-recipes.md` |
| 6 | Project Basic Price | `projects/[id]/basic-price`, `[draftId]`, `[draftId]/promote` | `06-project-basic-price.md` |
| 7 | Project Basic Rate | `projects/[id]/basic-rate`, `[code]`, `[code]/history`, `clone`, `import`, `next-code` | `07-project-basic-rate.md` |
| 8 | Global catalog (id-keyed) | `basic-price`, `basic-price/[draftId]`, `[draftId]/promote`, `basic-rate`, `basic-rate/[itemId]`, `[itemId]/history`, `basic-rate/next-code` | `08-global-catalog.md` |
| 9 | Global lookup tables | `activities`, `activities/[code]`, `categories`, `categories/[key]`, `trades`, `trades/[id]`, `units`, `units/[id]` | `09-lookup-tables.md` |
| 10 | Suppliers & sub-contractors | `suppliers`, `suppliers/[id]`, `suppliers/price-comparison`, `price-comparison/item`, `sub-contractors`, `sub-contractors/[id]` | `10-suppliers.md` |
| 11 | Users, roles & permissions | `users`, `users/[email]`, `users/[email]/projects`, `[projectId]`, `roles`, `roles/[id]`, `permissions/catalog` | `11-users-roles.md` |
| 12 | Reporting & misc | `dashboard`, `payments`, `notifications`, `company-profile`, `expenses/next-invoice` | `12-reporting-misc.md` |

Families **2, 3, 4, 11** are the highest-value targets: they carry money, project scoping, and
privilege assignment. Give them proportionally more depth.

### For each route family, run all seven test classes

For **every** handler in the family, and **every** HTTP method it exports:

#### A. Authentication & session enforcement
- Call with **no cookie** → 401 (API) — never 200 with data, never an empty 200.
- Call with a **tampered/forged** JWT → 401.
- Call with a **revoked** session (log out, then replay the captured cookie) → 401.
- Call with an **Inactive** user's session (deactivate `kasun@` mid-session via Admin, then
  replay his cookie) → 401 on the very next request. Role/status must be re-read per request,
  not trusted from the token.
- Confirm the route is actually reached through `apiRoute` (an unhandled throw must not escape
  as a stack trace).

#### B. Authorisation — module permissions (RBAC)
- Call every handler as the **zero-permission Staff** account → 403, for every write method at
  minimum. Record any that return 200/201/204.
- Cross-check the guard in the source against `PERMISSION_CATALOG`: does the route enforce the
  module/action a reasonable person would expect? Flag a route guarded only by
  `requireSession()` on a write method — that is the exact class of bug found on 2026-09-01.
- Run `node scripts/audit-guards.js` and confirm it exits 0. If it passes but you found an
  unguarded handler by hand, **that is itself a finding** — the sweep has a blind spot.
- Privilege escalation: as Staff, attempt to grant yourself a role/permission
  (`/api/roles`, `/api/roles/[id]`, `/api/users/[email]`, `/api/permissions/catalog`), make
  yourself a project owner (`/api/projects/[id]/owner`) or add yourself as a member
  (`/api/projects/[id]/members`).

#### C. Authorisation — IDOR & project scoping (**highest priority**)
This codebase's characteristic bug is a nested resource that authorises against the URL's
project id but then acts on a child row **without constraining it to that parent**.

- For every route with an id in the path, log in as `dilini@` and substitute an id belonging to
  a project/user/record she has no access to. Test **GET, POST, PATCH, PUT and DELETE
  separately** — a route that guards reads but not writes is a real finding.
- **Parent/child mismatch:** call `/api/projects/{A}/stages/{stage-belonging-to-B}` and the
  equivalent for expenses, payments, items, recipe components, bsr lines, basic-price drafts and
  basic-rate codes. Expected: 404/403. Actual behaviour must be recorded per route.
- **List-endpoint leakage:** does a list route return rows from projects the caller cannot
  access? Check the SQL for a missing `projectAccessClause()`, and check that every call site
  passes a **table-qualified** `idColumn`.
- **Cross-project catalog isolation:** Basic Price/Rate items are per-project. Confirm project
  A's catalog cannot be read, edited, promoted, cloned or reassigned into by someone with access
  only to B. Codes are unique *within* a project only — confirm a code collision across projects
  is handled rather than merging records.
- Note that `F-04-02` already flags three route families that ignore the URL's project id
  without being exploitable today. Verify whether that is still true, and whether it has become
  exploitable.

#### D. Input validation & injection
- **White-box first (far more reliable than blind fuzzing):** grep the family's routes for SQL
  built by string concatenation or template interpolation rather than `.bind()`:
  search for `` `select ``/`` `insert ``/`` `update ``/`` `delete `` containing `${`, plus
  `.exec(`, plus any `order by`/`limit`/table-or-column name assembled from request input
  (`.bind()` cannot parameterise identifiers — this is the common hole even in otherwise-safe
  code). Report `file:line` for each, and whether it is safe (hardcoded whitelist) or not.
- **Black-box:** through every string field, path param and query param send
  `' OR '1'='1`, `'; DROP TABLE users;--`, `1' UNION SELECT null,sqlite_version()--`,
  `admin'--`, `%27`, and try `sqlite_master` enumeration. Watch for a raw SQL error, an
  unexpected row count, an auth bypass, or a timing spike.
- **Zod coverage and *ranges*, not just types** (this is finding X-06): send negative numbers,
  `0`, absurdly large numbers (`1e308`, `Number.MAX_SAFE_INTEGER`), and huge strings/arrays where
  only sane values make sense — quantities, amounts, rates, percentages, `stages` counts.
  `F-03-04` recorded one request writing 3,000 milestone rows; confirm whether any collection
  input is still unbounded.
- **Type confusion:** send an array/object/`null` where a string or number is expected, and a
  deeply nested payload.
- **Mass assignment:** add `id`, `role`, `ownerId`, `isAdmin`, `createdAt`, `projectId`,
  `passwordHash` to PATCH/POST bodies and check whether any are persisted.
- **Stored XSS reaching other surfaces:** store `<script>alert(1)</script>` and
  `<img src=x onerror=alert(1)>` in free-text fields (names, descriptions, notes) and confirm
  where they surface — including the **Excel and PDF exports**, which are generated from live API
  data.
- **Import route specifically** (`projects/[id]/basic-rate/import`): wrong MIME type, 50 MB file,
  malformed XLSX/CSV, formula-injection cells (`=cmd|...`), zip bomb, path traversal in filenames.

#### E. Business-logic & money integrity
The category the client notices first, and where several findings already exist.
- Recompute derived figures by hand for one real dataset and diff against the API: project
  income, ROI, outstanding balances, stage values, milestone amounts, BSR item rates.
- **Negative and zero amounts** — `F-03-03` (negative contract value corrupts the company-wide
  outstanding total) and `F-04-01` (negative payment understates paid expense, inflates ROI,
  defeats the over-allocation guard). Confirm current behaviour on every money-accepting route.
- **Paid vs committed** — ROI and the expenses/payments views must use `expensePaid`, not
  `expenseCommitted`. `F-02-01` records ROI reading as large profit when nothing is paid.
- **Over-allocation:** pay more than an expense's total; pay a fully-paid expense again.
- **Rounding/precision:** confirm summed columns match their rows; look for float artefacts.
- **BSR recipe engine:** `analysisQty` ("basis isn't always 1 unit"), `floorMultiplier`, and
  percentage allowance lines. Verify against a hand-computed figure — `04-project-detail.md`
  records this arithmetic as **not yet exercised**, so it is genuinely untested.
- **Price history:** `PriceHistoryEntry` must be written on **every** rate change, with the right
  actor and timestamp.

#### F. Data integrity
- **Cascade/orphans:** delete a parent (project, supplier, activity, stage, expense, user) and
  then query **every** child table for surviving rows. `doc/ORPHANED_ROWS_FIX_PROMPT.md` is prior
  art claiming this is handled — verify it actually holds, per entity.
- **Referential integrity:** create a child pointing at a non-existent parent id.
- **Unique constraints:** duplicate emails, duplicate codes within a project, duplicate
  names where uniqueness is expected.
- **Atomicity:** the codebase uses `db.batch([...])` in places (e.g. the unit/trade rename
  cascade). Confirm a failure mid-batch leaves no half-applied state.
- **Concurrency:** two simultaneous PATCHes to the same record — lost update or last-write-wins?
  Fire the same POST twice rapidly — duplicate rows? Especially on anything allocating a code or
  invoice number (`basic-rate/next-code`, `expenses/next-invoice`).

#### G. Error handling, disclosure & rate limiting
- **No internals in any error body** — no stack traces, SQL fragments, table/column names, file
  paths or library versions. Force a 500 and inspect.
- **Correct status codes** — 400 vs 401 vs 403 vs 404 vs 409 vs 422; and specifically whether
  malformed JSON still returns 500 rather than 400 (`X-02`, known open at time of writing).
- **Login throttle** (`src/lib/loginThrottle.ts`) — this was changed on 2026-09-05; see below.
  Confirm: per-email lock still fires at 5 failures; failures against *different* emails do not
  lock an unrelated account; no `ip:unknown` row is ever created.
- **Edge rate limiter** (`src/lib/edgeRateLimit.ts`, `LOGIN_RATE_LIMITER`) — confirm it is
  applied and that it is never called with a placeholder key.
- **Security headers** on API responses — `X-Content-Type-Options`, `Referrer-Policy`, HSTS,
  and the current CSP state (`X-03`: `frame-ancestors` only, known open).
- **CSRF** (`X-01`, known open): confirm whether state-changing methods accept a forged
  `Origin`. `SameSite=Lax` is currently the only layer.

### Already fixed — verify these still hold, do NOT file them as new findings

| Was | Fixed | Verify |
|---|---|---|
| Milestone IDOR (cross-project write) | 2026-09-01 | `PATCH /api/projects/{mine}/stages/{any}/milestones/{other project's}` → 404 |
| Catalog writes guarded only by `requireSession` | 2026-09-01 | zero-permission Staff: `POST /api/units` → 403, `GET /api/units` → 200 |
| Middleware matcher bypass on image extensions | 2026-09-01 | logged out, `GET /api/users/x.png` → 401 from middleware |
| Shared `ip:unknown` login-throttle bucket | 2026-09-05 | 5 failures across 5 different emails → an unrelated correct login still 200 |
| Office-NAT lockout (IP threshold was 5) | 2026-09-05 | `ip:` keys now lock at 50, `email:` still at 5 |
| `SESSION_SECRET` unvalidated / silent logout | 2026-09-05 | short secret → 500 with a clear server log, **not** a `/login` redirect; body stays generic |
| MFA scaffolding | removed 2026-09-04 | **Do not test or report MFA.** The client declined it; single-factor is the intended design. |

### Known-open findings — confirm current state, don't re-litigate

`X-01`/`F-01-04` CSRF · `X-02`/`F-01-06` malformed JSON → 500 · `X-03`/`F-01-03` CSP has no
`script-src` · `F-01-05` `x-powered-by` · `F-01-08` `prisma/schema.prisma` drift (it still
declares `users.mfaSecret`, dropped by `0026_remove_mfa.sql` — this currently breaks
`npm run db:reset-seed`) · `F-02-01`/`F-03-03`/`F-04-01` money-sign issues · `F-03-04` unbounded
`stages` · `F-04-02` three route families ignore the URL project id · `login_throttle` never
garbage-collected · no self-service password change.

For each: state in your report whether it is **still present**, **now worse**, or **has been
resolved**, with evidence. New *instances* of these patterns in routes not previously audited
**are** new findings — report them and cross-reference the pattern.

### Cross-cutting sweeps (run ONCE, not per family)

Do these after family 1, and record them in the index rather than a family report:

1. **Repo-wide SQL interpolation sweep** — every `${` inside a SQL string across
   `src/app/api/**` and `src/lib/**`, classified safe/unsafe with `file:line`.
2. **`projectAccessClause` call-site sweep** — every call, and whether `idColumn` is
   table-qualified. An unqualified one is a silent membership-access bug.
3. **Guard sweep** — `node scripts/audit-guards.js` exits 0.
4. **Dependency audit** — `npm audit` and `node scripts/audit-gate.js`.
5. **Migration replay from zero** — drop the local D1, apply `migrations/` in order, run
   `npm run db:seed`. Must complete clean. Note that `prisma/migrations/` holds only a single
   `init` migration while `migrations/` holds 28+ — record the drift's practical impact.
6. **Secret scan** — no secrets in the repo or in `.open-next/assets`; confirm `SESSION_SECRET`
   never reaches the client bundle; confirm no source maps ship.
7. **Session-revocation matrix** — confirm all five revoke paths still work: role change,
   deactivate, password change, delete, logout.

### Report format

Write reports to **`doc/backend-security-report/`** (create it). One `.md` per family, named per
the table above. Use exactly this structure:

```markdown
# Backend Security Audit — <Family Name>

- **Audited:** <YYYY-MM-DD>
- **Routes covered:** <list every route file + methods, e.g. `projects/[id]` (GET, PATCH, DELETE)>
- **Build/commit:** <git rev-parse --short HEAD, or "uncommitted working tree">
- **Verdict:** BLOCKER / NEEDS-FIX / PASS-WITH-NOTES / PASS

## Summary
<3–5 sentences: what these routes do, what you tested, the headline risk.>

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ / ⚠️ / ❌ | |
| B. RBAC | | |
| C. IDOR & project scoping | | |
| D. Input validation & injection | | |
| E. Business logic & money | | |
| F. Data integrity | | |
| G. Errors, disclosure, rate limiting | | |

## Per-route matrix
| Route | Method | Guard in source | No-auth | Zero-perm Staff | Cross-project id | Verdict |
|---|---|---|---|---|---|---|
| `/api/projects/[id]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess` | 401 | 403 | 404 | ✅ |

## Findings

### B-<family#>-01 — <short title>
- **Severity:** Critical / High / Medium / Low / Info
- **Confidence:** Confirmed / Unconfirmed
- **Class:** Auth | Authorisation | IDOR | Injection | XSS | CSRF | Disclosure | Data integrity | Business logic | Availability
- **Location:** `path/to/route.ts:123`
- **Request:**
  ```
  PATCH /api/... HTTP/1.1
  Cookie: <staff session>
  {"...":"..."}
  ```
- **Expected:** …
- **Actual:** …  (status + body)
- **Impact:** <what a real attacker or a careless user gets out of this>
- **Suggested fix:** <one or two lines — DESCRIBE ONLY, do not implement>

<repeat, numbered sequentially>

## Tested and clean
<Specific, evidenced bullets — as valuable to the client as the findings.
"Dilini's PATCH to /api/projects/{kasun's}/expenses/{id} returned 403" beats "authorisation OK".>

## Not tested / blocked
<Anything you could not cover, and why. An unexamined area silently reported as clean is worse
than an admitted gap.>
```

Severity guide: **Critical** = auth bypass, SQLi, cross-tenant data access, data loss.
**High** = privilege escalation, stored XSS, broken money calculation. **Medium** = missing
validation, integrity gap with a workaround, missing header. **Low** = cosmetic/minor.
**Info** = observation only.

### Also maintain an index

`doc/backend-security-report/00-INDEX.md` — update it after **each** family so progress survives
a session restart:

- A table: family | report file | routes | verdict | Critical/High/Medium/Low counts | date.
- A **Cross-cutting sweeps** section holding the seven one-time sweep results.
- A **Cross-cutting findings** section for patterns spanning families (describe once, reference
  from the family files).
- A **Handover readiness** section: the ranked shortlist of what must be fixed before the client
  sees this, and what should be disclosed in writing instead of fixed.

### Working method

Do **one family at a time**, start to finish: probe it, write its report file, update the index —
then move to the next. Do not batch all 12 families' testing and leave the writing to the end; a
session that ends early must still leave completed reports behind.

Before starting a family, check `00-INDEX.md` — if it already has a verdict, skip to the next
unaudited one. When all 12 are done, review the whole set for cross-cutting patterns and
finalise the Handover readiness list.

Tell me at the start of each family which one you are on, and at the end give me a one-line
verdict with the finding counts.

---

## Notes on using this

- **It is deliberately resumable.** 62 routes will not fit in one context window. Run the
  prompt, let it work, re-paste it when the session ends — `00-INDEX.md` is what makes the next
  run pick up where the last one stopped.
- **Run it against a scratch copy of the local D1.** The audit deliberately creates junk rows
  (XSS payloads, injected SQL strings, oversized imports) and does not clean up after itself.
  Note that `npm run db:reset-seed` currently **fails** due to the F-01-08 Prisma drift, so the
  reliable reset is: delete `.wrangler/state/v3/d1`, re-apply `migrations/`, then `npm run db:seed`.
- **The high-value classes are B, C and E** — the app has a two-layer permission model, raw SQL
  against D1, and it moves money. Authorisation gaps, identifier-level injection and money-sign
  bugs are where real findings will be.
- **This complements, does not replace, `PRE_HANDOVER_QA_PROMPT.md`.** That one covers UI
  behaviour, rendering, exports and accessibility page by page (4 of 19 pages done as of
  2026-09-05). Where the two overlap, this one is authoritative on what the *server* permits.
- If you would rather parallelise, the families are independent: run the prompt in several
  sessions with the family table narrowed to a slice each (1–4, 5–8, 9–12), then merge the
  indexes by hand.
