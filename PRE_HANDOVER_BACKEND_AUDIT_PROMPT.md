# Pre-Handover Backend Security & API Audit Prompt (2026-09-21)

**This supersedes `doc/PRE_HANDOVER_BACKEND_SECURITY_PROMPT.md`.** That file was written in the
Cloudflare D1 era: its environment setup (`npm run preview`, `wrangler d1 --local`,
`vega-manager/`), its test accounts, and its threat model all predate the 2026-09 migration to
Postgres on k3s. Its **finding history is still valid and referenced below** — its setup
instructions are not. Do not run it as-is.

The pre-handover set:

| Prompt | Lens | Unit | Status |
|---|---|---|---|
| `doc/Front end/PRE_HANDOVER_QA_PROMPT.md` | UI correctness, page by page | one page | 4 / 19, stale env |
| `doc/Front end/PRE_HANDOVER_E2E_JOURNEY_PROMPT.md` | Does the product work for a real user | one journey | new |
| **this file** | **What the server actually permits, and what breaks it** | one route family | new |

A hidden button is not authorisation. The UI cannot tell you what the server permits. This prompt
tests the API directly, at the HTTP layer, with security as the primary lens.

Paste everything below `## THE PROMPT` into Claude Code, working directory
`d:\Bistec Intern Project\Vega`.

---

## THE PROMPT

You are performing the **pre-handover backend security and API audit** of the Vega Construction
Manager API — all **64 route handlers** under `VegaConstruction-ManagementSystem/src/app/api/**`,
plus the shared libraries every one of them depends on. This is the last security check before the
product is delivered to the client.

Your job is to **test and report**, exhaustively, at the HTTP and source level.

### Ground rules — these override any instinct you have

1. **DO NOT FIX ANYTHING.** No source edits, no refactors, no "while I was here" cleanups. You are
   an auditor. The only files you may create or modify are the report files described below and
   test scripts under `VegaConstruction-ManagementSystem/tests/`. Finding and *describing* the
   vulnerability is the entire deliverable — a fix you slip in unreviewed is worse than the bug.
2. **Read §"Database safety" before you send a single mutating request.** `DATABASE_URL` points at
   a **shared remote Supabase Postgres**. There is no local database any more.
3. **Never deploy, never touch production.** No `npm run deploy`, no `kubectl apply`, no writes to
   a remote target beyond the audit database you chose in §Database safety. Confirm with me before
   any command that touches infrastructure.
4. **Test at the HTTP layer, not through the UI.** `curl` / `fetch` / Playwright's `request`
   fixture against the running server. A route the UI never calls with hostile input is precisely
   the route that has never *been* called with hostile input.
5. **White-box first, then black-box.** Read the handler and the SQL, form a hypothesis, then prove
   it over HTTP. Blind fuzzing this codebase is a poor use of time; reading `src/lib/pg.ts` and
   then crafting three precise requests is not.
6. **Report, don't speculate.** Every finding needs the exact request (method, path, headers,
   body), the actual response (status + body), and the `file:line` of the responsible code. If you
   suspect an issue but cannot reproduce it, file it as `Unconfirmed` and state exactly what you
   tried and what you'd need to confirm it.
7. **One report file per route family.** Never merge two families.
8. **Do not re-report closed findings as new.** See §"Already fixed" and §"Known open". Confirming
   a fix still holds is valuable; filing it fresh is noise.

### Database safety — decide this first

`VegaConstruction-ManagementSystem/.env`:

```
DATABASE_URL=postgresql://postgres.ovobnhguozluizzhramy...@aws-0-ap-northeast-1.pooler.supabase.com...
```

Shared, remote, and holding what the client is about to receive. This audit deliberately writes
junk: SQL-injection strings, XSS payloads, oversized imports, 3,000-row collection abuse. It does
not clean up after itself by nature.

**Choose one, state it at the top of every report, do not deviate:**

- **Option A (strongly preferred) — local Postgres.**
  `docker run -d -e POSTGRES_PASSWORD=vega -p 5432:5432 postgres:16`, point `.env.local`'s
  `DATABASE_URL` at it, `npm run db:migrate`, `npm run db:seed`, verify with `npm run verify:pg`.
  Destructive testing is only honest testing when you can destroy freely.
- **Option B — shared Supabase, under discipline.** Only if A cannot be made to work. Every row you
  create is prefixed `SEC ` / `sec-`; you keep a cleanup ledger; you **never** modify or delete a
  row you did not create; you do **not** run `db:reset-seed`.

Under either option, several test classes below (connection-pool exhaustion, unbounded collection
writes, bcrypt CPU exhaustion) are **destructive to availability**. Run those **only** under
Option A, or with my explicit go-ahead. Mark them `Not tested — requires Option A` otherwise; an
honest gap beats a damaged handover database.

### Environment setup

```bash
cd VegaConstruction-ManagementSystem
npm install
# set DATABASE_URL per your Option A / B choice
npm run dev            # Next 16, http://localhost:3000
```

Traps that will each cost you an hour:

- **`next dev` works now.** The old prompt says API routes 500 under it — that was the D1-binding
  era. Postgres is reached directly. Ignore every `wrangler` / `npm run preview` / "Workers
  runtime" instruction anywhere in `doc/`.
- **`src/middleware.ts` does not exist.** Next 16 renamed it. The global gate is **`src/proxy.ts`**.
- **Mutating requests are Origin-checked** (`src/proxy.ts`, added 2026-09-19). A bare `curl -X POST`
  with no `Origin` header gets **403 before reaching the handler**. Every mutating probe you send
  must carry `Origin: http://localhost:3000` or you will misread a CSRF defence as a broken route.
  *Testing that check itself is a separate exercise — see sweep S7.*
- **Playwright's `baseURL` defaults to the dead wrangler port 8787.** Use
  `PW_BASE_URL=http://localhost:3000`.
- **`tests/helpers.ts` is half-ported** — `playwright.config.ts` carries a KNOWN BROKEN banner
  saying it shells out to wrangler, but the helper now runs `scripts/test-db-exec.mts` over
  `DATABASE_URL`. Verify which is true and record it; "the security test suite does/doesn't run"
  is itself a handover fact.
- **`SESSION_SECRET` must be ≥ 32 bytes** (RFC 7518 §3.2, enforced in `src/lib/sessionToken.ts`).
  A short secret makes every request 500. That is intended behaviour (F-01-07), not a bug.
- **Login throttle: 5 failures / 15 min per email.** Clear `login_throttle` after any deliberate
  bad-login test or you will lock the account you need next and misdiagnose it.

### Accounts

| Email | Password | Role | Use for |
|---|---|---|---|
| `yomaltheekshana66@gmail.com` | `yomal8899` | Admin | baseline; Admin bypasses RBAC entirely |
| `csp-test-staff@vegahomes.lk` | `yomal8899` | Staff, **zero** roles & permissions | the single most productive probe in this codebase |

The demo accounts in the old prompt (`nimal@`, `sanduni@`, `kasun@`, `dilini@`, `ruwan@`) were
**deleted 2026-09-11**. Ignore every reference to them.

You must create, as Admin, before starting family 2:
- **`sec-staff-a@vegahomes.lk`** — Staff, one role granting `projects:view/create/edit` only
- **`sec-staff-b@vegahomes.lk`** — Staff, same role, **owner of a different project**
  → this pair is your **IDOR probe**: can B reach A's project?
- **`sec-inactive@vegahomes.lk`** — Staff, then set Inactive → must be refused login and hold no
  usable session
- Two projects, `SEC Project A` (owned by staff-a) and `SEC Project B` (owned by staff-b), each
  with at least one stage, milestone, expense, payment, BSR line, item, basic-price draft and
  basic-rate item — you need real child rows to test parent/child mismatch.

Note the ordering trap: `assertAssignableUser` (`src/lib/rbac.ts`) refuses to make a
zero-permission Staff user a project owner or member. Create and assign the role **first**.

---

## Architecture you must understand before you start

Read these six files before writing a single probe. The audit is dramatically less effective
without them, and three of them are themselves prime finding territory.

### 1. `src/lib/pg.ts` — **the highest-risk file in the application**

The D1→Postgres migration did not rewrite the ~48 files of raw SQL. Instead this module
reimplements D1's `prepare/bind/all/first/run/batch` surface over `pg`, and **rewrites the SQL text
of every query in the application** via a hand-written tokenizer, `rewritePlaceholders()`. Every
single database call in this product passes through that function. Treat it accordingly.

It does two transformations in one scan, skipping `'...'` literals, `"..."` identifiers, `--` line
comments and `/* */` block comments:

1. **Placeholders.** `?` → `$n`, and `?N` → `$N`. It deliberately reproduces SQLite's rule that a
   bare `?` takes *one greater than the largest number already assigned*. This is **load-bearing for
   authorisation**: `projectAccessClause()` emits `?1` twice (one bound value, two references) and
   call sites append their own bare `?` afterwards, which must become `$2`. Get this wrong and it
   does not throw — it **silently binds the wrong value into an access-control predicate**.
2. **Identifier case.** Any bare word containing an uppercase letter is wrapped in double quotes,
   because Prisma's DDL quotes camelCase columns and Postgres folds unquoted identifiers to
   lowercase. The safety argument is "every keyword and table name in this codebase's raw SQL is
   lowercase" — an assumption held by convention, not enforced by anything.

**Verify the tokenizer's completeness.** Postgres syntax it does *not* appear to handle:
dollar-quoted strings (`$$ ... $$`, `$tag$ ... $tag$`), `E'...'` escape-string literals with
backslash escapes, and **nested** block comments (Postgres allows `/* /* */ */`; this scanner exits
at the first `*/`). For each: determine whether any query in the codebase can reach it, whether
request data can ever reach the SQL *text* (as opposed to a bound value), and what happens if it
does. A tokenizer that mis-identifies where a literal ends is an injection primitive.

Also in this file: `types.setTypeParser(20, Number)` coerces bigint to JS number — the code's own
comments state the **last-active-Admin guard** and the **"is this row still in use?" delete guards**
depend on it. `getPool` sets **`ssl: { rejectUnauthorized: false }`** with a comment saying to pin a
CA "before this handles production data". Pool is `max: 10`.

### 2. `src/lib/rbac.ts` — two independent authorisation layers, both must be tested

- **Module permissions** — `requirePermission(module, action)` against `PERMISSION_CATALOG`:
  `dashboard:view` · `projects:view|create|edit|delete|promote` · `activities:view|create|edit|delete`
  · `suppliers:view|create|edit|delete` · `payments:view` · `priceComparison:view`.
  Effective permissions = union(role permissions, direct `user_permissions` grants).
  **Admin short-circuits with no DB read at all.**
  Basic Price / Basic Rate are **not** separate modules — they fold into `projects`, with `promote`
  as the draft→rate action.
- **Project reach** — `requireProjectAccess()`: Admin, owner, or assigned member. Membership grants
  *visibility only* and never implies any module permission.
- **`projectAccessClause()` documented footgun:** `idColumn` **must** be table-qualified (`'p.id'`).
  Unqualified, the `EXISTS` subquery resolves against `project_members`' own `id` and the
  membership branch is silently always false — owned projects still appear, *assigned* ones
  vanish. `dashboard/route.ts` had exactly this bug once. **Grep every call site.**

### 3. `src/lib/auth.ts` — sessions are DB-backed and revocable

JWT carries only `{ sid }`. Role and status are re-read from the `users` row on **every** request
(`resolveSession`). Absolute TTL: 7 days remembered / 8 hours session-only. **Idle timeout now
exists** (1 hour session-only, 3 days remembered) — this closes the previously-open AUTH-VULN-05;
verify it rather than assuming either state. `lastSeenAt` writes are throttled to ~1 per 5 min.
`bcrypt.hashSync` / `compareSync` at cost 10 — **synchronous, on the Node event loop** (see H).

### 4. `src/proxy.ts` — the global gate

Origin-based CSRF check on POST/PUT/PATCH/DELETE (**missing Origin is rejected**), applied *before*
the public-path allowlist so `POST /api/auth/login` is covered. Unauthenticated → 401 (API) or
redirect (page). Then a **full DB session resolution on every matched request**. Per-request CSP
nonce; the matcher's `[^/]*\.(svg|png|…)$` is deliberately root-level-only (an earlier `.*` version
let `/api/users/x.png` skip the gate entirely — do not let a "simplification" reintroduce that).

### 5. `src/lib/api.ts` — `apiRoute()` wraps every handler

`AuthError` → its status · `ZodError` → 400 with the first issue's message · everything else →
generic 500, logged server-side, no stack trace to the client. `parseBody()` calls
`request.json()` — **a malformed body throws `SyntaxError`, not `ZodError`, so it falls through to
500** (that is X-02, still open). There is **no visible request body size limit** anywhere in this
chain.

### 6. `src/app/api/auth/login/route.ts` — the most carefully-reasoned route in the app

Volumetric IP limiter (20/60s) → per-key failure throttle (email 5, ip 50) → user lookup → bcrypt
compare **always**, against `DUMMY_PASSWORD_HASH` when no user exists (timing-equalised
enumeration defence) → generic error. `Inactive` is disclosed **only after** the correct password
is verified. Client IP comes from **`x-real-ip` only**, set by Traefik from the socket; when absent
the IP layer is **skipped entirely** rather than falling back to a shared bucket (that fallback was
F-01-02, an unauthenticated DoS in 5 requests). Verify the current behaviour of all of this.

---

## Part 1 — Cross-cutting sweeps (run these FIRST, once, before any family)

These cover the shared layers every route inherits. Record them in `00-INDEX.md`, not in a family
report. Several are the highest-value work in this entire audit.

- **S1 — `rewritePlaceholders` correctness and completeness.** The single most important sweep.
  Unit-test the function directly (`tsx`, no server needed) against: `?1` reused twice then a bare
  `?`; `?` inside `'...'`, inside `"..."`, inside `--` and `/* */`; `$$dollar quoted$$`;
  `E'\'' `; nested block comments; a `?` in the middle of an identifier; an identifier that is a
  reserved word with an uppercase letter. For each, state whether the output SQL is correct and
  whether any real query in `src/**` can reach that shape. Then prove the authorisation case end to
  end over HTTP: does `projectAccessClause`'s `?1`-plus-trailing-`?` actually bind the values the
  handler intends? Verify with a query log or by observing behaviour that can only be explained by
  correct binding.
- **S2 — Bind-count mismatch behaviour.** `compile()` throws a plain `Error` on mismatch → generic
  500. Find whether any code path can produce a mismatch from request input (a conditional clause
  built per-request). One that can is a remotely-triggerable 500.
- **S3 — SQL interpolation sweep.** Every `${` inside a SQL string across `src/app/api/**` and
  `src/lib/**`. Classify each safe (hardcoded whitelist / literal) or unsafe, with `file:line`.
  Pay special attention to anything assembling `order by`, `limit`, a table name or a column name
  from request input — `.bind()` cannot parameterise an identifier, and the identifier-quoting pass
  in `pg.ts` will happily quote an attacker-influenced word into a valid identifier.
- **S4 — `projectAccessClause` call-site sweep.** Every call, and whether `idColumn` is
  table-qualified. Each unqualified one is a silent membership-access bug; prove it at runtime for
  at least one.
- **S5 — Guard sweep.** `node scripts/audit-guards.js` must exit 0. Then find its **blind spots**:
  it matches guard *names*, so it cannot tell that a route checks the *wrong* module or action.
  Manually cross-check every handler's guard against what a reasonable person would expect for that
  resource. A route guarded by `requirePermission('suppliers','view')` on a projects write is
  invisible to the script and is a real finding.
- **S6 — Session revocation matrix.** All five paths must invalidate a live session immediately:
  logout, role change, deactivate, password change, user delete. Test by capturing a cookie, then
  performing the action as Admin, then replaying the cookie.
- **S7 — CSRF Origin check.** Confirm: absent `Origin` → 403; cross-origin `Origin` → 403;
  same-origin → passes; the check covers `POST /api/auth/login`; it cannot be bypassed by
  `X-HTTP-Method-Override`, by a `HEAD`/`OPTIONS` preflight trick, or by a `null` origin from a
  sandboxed iframe or `data:` URL.
- **S8 — `x-real-ip` trust boundary.** Can a client set `x-real-ip` and be believed? If yes, that
  is **two** findings: the attacker evades the IP limiter by rotating it, *and* they can poison an
  arbitrary victim IP's throttle bucket to lock others out. Test locally, then reason about the
  Traefik path (`deploy/helm/templates/ingress.yaml`) and state whether the deployed topology
  actually prevents it. `AZURE_SECURITY_RUNBOOK.md` Task 3.1 records this as previously unverified.
- **S9 — Transport & secrets.** `rejectUnauthorized: false` on the DB connection — confirm, assess,
  and report as a finding with the code's own TODO as evidence. Scan the repo and the built output
  for secrets; confirm `SESSION_SECRET` never reaches the client bundle; confirm no source maps
  ship; check `.env` is gitignored and that no credential is committed.
- **S10 — Security headers.** On both API and page responses, and specifically on `proxy.ts`'s
  direct-return branches (401/403/redirect), which bypass `next.config.ts`'s `headers()`. Confirm
  HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, the enforcing CSP
  with a fresh per-request nonce, and `Cache-Control: no-store` on the three auth endpoints.
  Confirm **`unsafe-eval` never appears in a production build's CSP** (dev-only by design).
  Confirm `x-powered-by` is gone (F-01-05).
- **S11 — Dependency & CI gate.** `npm audit`, `node scripts/audit-gate.js`, and read
  `.github/workflows/ci.yml` — does CI actually block a merge on these, or only report?
- **S12 — Migration replay.** Against a scratch database only: migrate from zero, then
  `npm run db:seed`. Must complete clean. Record any Prisma schema drift (F-01-08 previously broke
  `db:reset-seed`) and the practical impact for whoever inherits this.
- **S13 — Route inventory.** Enumerate all 64 `route.ts` files and every method each exports.
  Cross-check against the family table below; anything not covered by a family is a coverage gap
  you must add. Flag any empty route directory (a half-built feature — the X-04 pattern;
  `src/app/api/dashboard/cashflow/` was one).

---

## Part 2 — Route family audit (12 families, 64 route files)

One report file each. Work in this order.

| # | Family | Routes | Report file |
|---|---|---|---|
| 1 | Auth & session | `auth/login`, `auth/logout`, `auth/me`, `healthz`, `ready` | `01-auth-session.md` |
| 2 | Projects core & access control | `projects`, `projects/[id]`, `members`, `members/[userId]`, `owner` | `02-projects-access.md` |
| 3 | Stages & milestones | `projects/[id]/stages`, `stages/[stageId]`, `…/milestones/[milestoneId]` | `03-stages-milestones.md` |
| 4 | Expenses & payments | `projects/[id]/expenses`, `[expenseId]`, `payments`, `payments/[paymentId]`, `expenses/next-invoice` | `04-expenses-payments.md` |
| 5 | BSR, items & recipes | `projects/[id]/bsr`, `bsr/[lineId]`, `items`, `items/[itemId]`, `recipe/[componentId]` | `05-bsr-items-recipes.md` |
| 6 | Project Basic Price | `projects/[id]/basic-price`, `[draftId]`, `[draftId]/promote` | `06-project-basic-price.md` |
| 7 | Project Basic Rate | `projects/[id]/basic-rate`, `[code]`, `[code]/history`, `clone`, `import`, `next-code` | `07-project-basic-rate.md` |
| 8 | Global catalog | `basic-price`, `basic-price/[draftId]`, `promote`, `basic-rate`, `[itemId]`, `history`, `next-code` | `08-global-catalog.md` |
| 9 | Global lookup tables | `activities`, `activities/[code]`, `categories`, `[key]`, `trades`, `[id]`, `units`, `[id]` | `09-lookup-tables.md` |
| 10 | Suppliers & sub-contractors | `suppliers`, `[id]`, `price-comparison`, `price-comparison/item`, `sub-contractors`, `[id]` | `10-suppliers.md` |
| 11 | Users, roles & permissions | `users`, `users/[email]`, `[email]/projects`, `[projectId]`, `roles`, `roles/[id]`, `permissions/catalog` | `11-users-roles.md` |
| 12 | Reporting & misc | `dashboard`, `payments`, `notifications`, `company-profile` | `12-reporting-misc.md` |

**Families 2, 4, 6 and 11 are the highest-value targets** — they carry project scoping, money,
the documented double-promotion vulnerability class, and privilege assignment. Give them more depth.

### For every handler and every method it exports, run all eight test classes

#### A. Authentication & session
- No cookie → 401 (never 200, never an empty 200, never a redirect for an API route).
- Forged / tampered / `alg: none` JWT → 401. A JWT signed with a different key → 401.
- Revoked session (logout, then replay the cookie) → 401.
- Deactivated user mid-session (Admin sets Inactive, then replay) → 401 on the **very next** request.
- Idle-expired session → 401. Absolute-expired session → 401.
- Can the `SESSION_ACTIVITY_HEADER` be spoofed by a client to keep a session alive indefinitely
  without real activity? `proxy.ts` always `set`s it — confirm no path reaches a handler with a
  client-supplied value.
- Confirm no unhandled throw escapes `apiRoute` as a stack trace.

#### B. Authorisation — module permissions
- Every handler as the **zero-permission Staff** account. Every write method must 403. Record any
  that return 2xx — that is the bug class that found the unguarded catalog writes on 2026-09-01.
- Cross-check each guard against `PERMISSION_CATALOG`: is it the module and action a reasonable
  person would expect? Flag any write method guarded only by `requireSession`/`getSession`.
- **Privilege escalation:** as Staff, attempt to grant yourself a role or permission
  (`/api/roles`, `/api/roles/[id]`, `/api/users/[email]`, `/api/permissions/catalog`), promote
  yourself to Admin, make yourself a project owner (`/api/projects/[id]/owner`), or add yourself as
  a member (`/api/projects/[id]/members`).
- **Last-admin guard:** can the final Admin demote or delete themselves, leaving the system with no
  administrator? Note this guard depends on the bigint→Number type parser (see §pg.ts).
- `assertKnownPermission` — can an unknown or malformed `module:action` string be persisted?

#### C. IDOR & project scoping — **highest priority**
This codebase's characteristic bug is a nested resource that authorises against the URL's project
id but then acts on a child row **without constraining it to that parent**.

- For every route with an id in the path: as `sec-staff-b`, substitute an id belonging to
  `SEC Project A`. Test **GET, POST, PATCH, PUT and DELETE separately** — a route that guards reads
  but not writes is a real finding.
- **Parent/child mismatch:** `/api/projects/{B}/stages/{stage belonging to A}`, and the equivalent
  for milestones, expenses, payments, items, recipe components, BSR lines, basic-price drafts,
  basic-rate codes. Expected 403/404. Record actual, per route.
- **List leakage:** does any list endpoint return rows from a project the caller cannot reach?
  Check the dashboard and payments aggregates especially — a total that silently includes
  inaccessible projects is a leak even when no row is returned.
- **Cross-project catalog isolation:** basic price/rate codes are unique *within* a project only.
  Confirm a code collision across projects does not merge records, and that clone/import/promote
  cannot pull from or write into a project the caller cannot reach.
- **Membership vs permission:** a user who is a project *member* but holds no module permission
  must still be refused every action. Membership is visibility only.
- `F-04-02` recorded three route families that ignore the URL's project id without being
  exploitable. Verify whether that is still true and whether it has become exploitable.

#### D. Injection & the SQL translation layer
- Apply S1/S3's findings here concretely: for each route, can request data reach the SQL **text**
  rather than a bound value? Through a sort field, a filter column, a table selector, a dynamically
  built `in (...)` list, or a conditionally appended clause?
- Black-box every string field, path param and query param with: `' OR '1'='1`,
  `'; drop table users;--`, `1' union select null,version()--`, `admin'--`, `%27`,
  `$$`, `E'\''`, `/* /* */ */`, a `?` and a `$1` inside a string value, and a value containing a
  double quote (against the identifier-quoting pass). Watch for a raw SQL error, an unexpected row
  count, an auth bypass, or a timing spike.
- Attempt `pg_catalog` / `information_schema` enumeration and `pg_sleep()` time-based injection.
- **Stored XSS reaching other surfaces:** persist `<script>alert(1)</script>` and
  `<img src=x onerror=alert(1)>` in free-text fields and trace where they surface — including the
  **PDF and Excel exports**, which are generated from live API data. Note the CSP's accepted
  `style-src 'unsafe-inline'` concession when rating severity.
- **CSV/formula injection** in Excel export: a cell beginning `=`, `+`, `-`, `@`, or a tab/CR.
- **Import route** (`projects/[id]/basic-rate/import`): wrong MIME type, 50 MB file, malformed
  XLSX, zip bomb, formula cells, path traversal in the filename, and a sheet with 1,000,000 rows.

#### E. Input validation, types & mass assignment
- **Ranges, not just types** (this is X-06): negative numbers, `0`, `1e308`,
  `Number.MAX_SAFE_INTEGER`, `-0`, `NaN`, `Infinity` into every money, quantity, rate, percentage
  and count field. `F-03-04` recorded one request writing 3,000 milestone rows — confirm whether any
  collection input is still unbounded.
- **Type confusion:** array / object / `null` / boolean where a string or number is expected;
  deeply nested payloads; `__proto__` and `constructor.prototype` keys (prototype pollution).
- **Mass assignment:** add `id`, `role`, `ownerId`, `status`, `isAdmin`, `createdAt`, `projectId`,
  `passwordHash` to POST/PATCH bodies and check whether any is persisted.
- **Unicode and length:** very long strings, null bytes (`\u0000` — Postgres rejects these in text
  and will 500), RTL overrides, emoji, Sinhala text, and homoglyph emails.
- **Date handling:** `'not a date'`, `'0000-00-00'`, a date in year 99999 — X-06 records unguarded
  `new Date(...).toISOString()` throwing a 500.
- **Content-Type confusion:** send a valid JSON body as `text/plain`, `multipart/form-data`, and
  with no Content-Type at all.

#### F. Business logic & money
The category the client notices first.
- Recompute by hand against one real dataset and diff against the API: project income received /
  outstanding, ROI, stage values, milestone amounts, BSR derived rates, dashboard totals.
- **Negative and zero amounts** — `F-03-03` (negative contract corrupts the company-wide
  outstanding total) and `F-04-01` (negative payment understates paid expense, inflates ROI,
  defeats the over-allocation guard). Confirm on every money-accepting route.
- **Paid vs committed** — ROI must use `expensePaid`, not `expenseCommitted` (`F-02-01`).
- **Over-allocation:** pay more than an expense's total; pay a fully-paid expense again.
- **BSR recipe engine:** `analysisQty` ≠ 1, `floorMultiplier`, percentage allowance lines. Verify
  against a hand-computed figure — the page audit records this arithmetic as **never exercised**.
- **Promote semantics (AUTHZ-VULN-01 / 02):** promote the same Basic Price draft twice, via both
  the project-scoped and the global endpoint, sequentially and concurrently. Duplicate rate items?
- **Price history:** written on every rate change, with the correct actor and timestamp, and not
  forgeable by the caller.
- **Rounding:** summed columns match their rows; no float artefacts.

#### G. Data integrity, transactions & concurrency
- **`db.batch()` is a real Postgres transaction** (BEGIN/COMMIT/ROLLBACK on one pooled client).
  Force a mid-batch failure on each of the ~24 batch call sites you can reach (promote, clone,
  import, owner transfer, the unit/trade rename cascade) and confirm **nothing** is half-applied.
- **Cascades and orphans:** delete a parent (project, supplier, activity, stage, expense, user) and
  query **every** child table for survivors. `doc/Front end/ORPHANED_ROWS_FIX_PROMPT.md` claims this
  is handled — prove it per entity.
- **Referential integrity:** create a child pointing at a non-existent parent id.
- **Unique constraints:** duplicate emails (including case-variant — note the login route does a
  case-*sensitive* lookup but a case-*insensitive* throttle key; is a case-variant duplicate account
  possible, and what happens at login?), duplicate codes within a project, duplicate names.
- **Concurrency — TOCTOU (AUTHZ-VULN-03):** fire the same request twice simultaneously at
  `expenses/[expenseId]/payments`, at both promote endpoints, and at `next-code` /
  `next-invoice`. Duplicate rows? A code allocated twice? An over-allocation that each request
  individually believed was within budget?
- **Lost update:** two concurrent PATCHes to the same record.

#### H. Errors, disclosure, rate limiting & availability
- **No internals in any error body** — no stack traces, SQL fragments, table or column names, file
  paths, library versions, or the `Bind count mismatch: … SQL: <full query>` message. Force a 500
  and inspect the exact body.
- **Correct status codes** — 400 / 401 / 403 / 404 / 409 / 422 / 429. Specifically: malformed JSON
  still returns **500 instead of 400** (X-02) because `request.json()` throws `SyntaxError`, which
  `apiRoute` does not special-case. Confirm, and check every route.
- **Login throttle:** per-email lock fires at 5; per-IP at 50; failures against different emails do
  not lock an unrelated account; no `ip:unknown` row is ever created; a successful login resets the
  counters; the lock actually expires after 15 minutes.
- **Volumetric limiter:** 20 requests / 60s per IP, `insert … on conflict` so concurrent callers
  cannot all read a stale count (the code documents a prior version where 25 concurrent calls left
  the counter at 2). Re-verify that concurrently. Confirm it **fails closed** on a DB error.
- **Availability (Option A only — destructive):**
  - **bcrypt event-loop blocking.** `hashSync`/`compareSync` at cost 10 blocks the Node event loop
    for tens of milliseconds per call, and login runs one on **every** attempt including for
    non-existent users. Measure it, then measure concurrent unauthenticated login attempts from
    distinct IPs (the per-IP limiter does not aggregate) against whole-app latency. Quantify
    whether this is a practical CPU-exhaustion lever.
  - **Connection pool exhaustion.** `max: 10`, and `proxy.ts` performs a DB session resolution on
    **every** matched request. Determine the concurrent authenticated request count at which the
    app stalls, and whether a slow query can hold the pool.
  - **Unbounded request body.** No size limit is visible in `parseBody`. Send 100 MB of JSON.
  - **Unbounded collections.** The `stages` finding (`F-03-04`); look for the same shape elsewhere.
- **Table growth:** `login_throttle` has **no garbage collection** (`login_rate_limit` and
  `sessions` are swept opportunistically at login; `login_throttle` is not). Confirm and rate it.

---

## Already fixed — verify these hold, do NOT file as new

| Was | Fixed | Verify |
|---|---|---|
| Milestone IDOR (cross-project write) | 2026-09-01 | `PATCH /api/projects/{mine}/stages/{any}/milestones/{other project's}` → 404 |
| Catalog writes guarded only by `requireSession` | 2026-09-01 | zero-perm Staff: `POST /api/units` → 403, `GET /api/units` → 200 |
| Proxy matcher bypass on image extensions | 2026-09-01 | logged out, `GET /api/users/x.png` → 401 from the gate |
| Shared `ip:unknown` throttle bucket | 2026-09-05 | 5 failures across 5 different emails → an unrelated correct login still 200 |
| Office-NAT lockout | 2026-09-05 | `ip:` locks at 50, `email:` at 5 |
| `SESSION_SECRET` unvalidated | 2026-09-05 | short secret → 500 with a server log, generic body, **not** a `/login` redirect |
| Session carried role/status in the JWT | Phase 2 | demote a user mid-session → next request reflects it immediately |
| No CSRF defence | 2026-09-19 | missing/cross-origin `Origin` on a mutation → 403 |
| CSP `frame-ancestors` only | 2026-09-11 | full enforcing policy with a per-request nonce |
| No session idle timeout (AUTH-VULN-05) | 2026-09-07 | idle past 1h (session-only) → 401 |
| Proxy did signature/expiry check only | 2026-09-18 | revoked session rejected at the gate, not just at the handler |

**MFA was removed 2026-09-04 at the client's request. Do not test or report it.** Single-factor is
the intended design.

## Known open — confirm current state, don't re-litigate

`X-02` malformed JSON → 500 · `X-06` Zod validates types but not ranges · `X-07` / `F-02-01` /
`F-03-03` / `F-04-01` the money-sign cluster · `F-03-04` unbounded `stages` · `F-04-02` three route
families ignore the URL project id · `F-01-08` Prisma schema drift · `login_throttle` never
garbage-collected · no self-service password change · `style-src 'unsafe-inline'` (accepted
concession, task 6.18) · `rejectUnauthorized: false` on the DB connection (code's own TODO) ·
`x-real-ip` trust boundary unverified (AZURE_SECURITY_RUNBOOK Task 3.1) · AUTHZ-VULN-01/02
double-promotion · AUTHZ-VULN-03 payment TOCTOU.

For each: **still present / now worse / resolved**, with evidence. A *new instance* of one of these
patterns in a route not previously audited **is** a new finding — report it and cross-reference.

Also read, don't duplicate: `doc/test/security/OPEN_FINDINGS_REMEDIATION_PLAN_2026-09-19.md`,
`FIXES_APPLIED_2026-09-19.md`, `K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md`,
`POST_K3S_HARDENING_PLAN_2026-09-18.md`, `AZURE_SECURITY_RUNBOOK.md`, and the
`.shannon/deliverables/` analysis set.

---

## Report format

Write to **`doc/backend-audit-2026-09/`** (new directory — do not overwrite the older
`doc/backend-security-report/`, which holds the prior audit's history).

One `.md` per family, named per the table. Structure:

```markdown
# Backend Audit — <Family Name>

- **Audited:** <YYYY-MM-DD> · **Build:** <git short sha> · **DB:** Option A local / Option B shared
- **Routes covered:** <every route file + every method>
- **Verdict:** 🔴 BLOCKER / 🟠 NEEDS-FIX / 🟡 PASS-WITH-NOTES / 🟢 PASS

## Summary
<3–5 sentences: what these routes do, what you tested, the headline risk.>

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ / ⚠️ / ❌ | |
| B. RBAC & escalation | | |
| C. IDOR & project scoping | | |
| D. Injection & SQL layer | | |
| E. Validation & mass assignment | | |
| F. Business logic & money | | |
| G. Integrity, transactions, concurrency | | |
| H. Errors, rate limiting, availability | | |

## Per-route matrix
| Route | Method | Guard in source | No auth | Zero-perm Staff | Cross-project id | Verdict |
|---|---|---|---|---|---|---|
| `/api/projects/[id]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess` | 401 | 403 | 404 | ✅ |

## Findings

### B-<family#>-01 — <short title>
- **Severity:** Critical / High / Medium / Low / Info
- **Confidence:** Confirmed / Unconfirmed
- **Class:** Auth | Authorisation | IDOR | Injection | XSS | CSRF | Disclosure | Data integrity | Business logic | Availability | Cryptography | Configuration
- **CWE:** <e.g. CWE-639 Authorization Bypass Through User-Controlled Key>
- **Location:** `src/app/api/…/route.ts:123`
- **Request:**
  ```http
  PATCH /api/... HTTP/1.1
  Origin: http://localhost:3000
  Cookie: vega_session=<zero-perm staff>
  Content-Type: application/json

  {"...":"..."}
  ```
- **Response:** `<status>` + body
- **Expected:** … **Actual:** …
- **Impact:** <what a real attacker or a careless user gets out of this>
- **Suggested fix:** <one or two lines — DESCRIBE ONLY, do not implement>
```

**Severity guide.** **Critical** = auth bypass, SQL injection, cross-tenant data access, data loss,
privilege escalation to Admin. **High** = IDOR within a tenant, stored XSS, broken money
calculation, remotely-triggerable crash, secret exposure. **Medium** = missing validation,
integrity gap with a workaround, missing header, information disclosure. **Low** = cosmetic or
defence-in-depth. **Info** = observation.

Rate severity by **impact on this client's deployment**, not by generic CVSS instinct. An internal
tool behind an office VPN with 20 named users weights availability differently from a public SaaS —
say so explicitly when it changes a rating, rather than silently inflating or deflating.

### Maintain `doc/backend-audit-2026-09/00-INDEX.md` after **every** family

- Progress table: family | file | routes | verdict | Critical/High/Medium/Low counts | date
- **Cross-cutting sweeps** — the S1–S13 results, each with a verdict
- **Cross-cutting findings** — patterns spanning families, described once and referenced
- **Handover readiness** — ranked: what must be fixed before the client sees this, what should be
  disclosed in writing instead of fixed, and what is knowingly accepted

### Final deliverable

When all 13 sweeps and 12 families are done, write
`doc/backend-audit-2026-09/BACKEND_SECURITY_REPORT.md`: executive summary a non-technical
stakeholder can read, the full finding register sorted by severity, the security posture by layer
(transport → gate → auth → authz → data → output), residual risk, and a sign-off paragraph stating
exactly what this audit does and does not certify.

---

## Working method

Do the **sweeps first** — S1 through S13 — because their results change how you read every family.
S1 in particular may reclassify the whole injection surface.

Then **one family at a time**, start to finish: probe it → write its report → update `00-INDEX.md` →
next. Do not batch all twelve and leave the writing to the end; a session that ends early must
still leave completed reports behind.

Before starting a family, check `00-INDEX.md` — if it has a verdict, skip to the next.

Tell me at the start of each family which one you are on, and at the end give me a one-line verdict
with the finding counts by severity.

---

## Notes on using this prompt

- **Resumable by design.** 64 routes will not fit in one context window. Re-paste when a session
  ends; `00-INDEX.md` is what makes the next run pick up cleanly.
- **S1 is the highest-value hour in this audit.** `rewritePlaceholders()` rewrites the SQL text of
  every query in the product, it was hand-written during a migration, and its own comments state
  that getting the placeholder numbering wrong "does not throw; it silently binds the wrong value
  into an access-control predicate". Nothing else in this codebase has that blast radius. Do it
  first and do it properly.
- **The zero-permission Staff account is the most productive single probe.** It is what found the
  unguarded catalog writes. Point it at every write method in the app before doing anything cleverer.
- **Option A matters more here than in the frontend audit.** Class H is genuinely destructive and
  class D deliberately writes hostile strings. Running this against the shared handover database is
  how a security audit becomes a security incident.
- **Parallelising:** families are independent once the sweeps and fixture accounts exist. Split
  1–4 / 5–8 / 9–12 across sessions and merge the indexes by hand. The sweeps must not be split —
  they inform everything.
