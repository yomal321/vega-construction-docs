# Security Test Report: `dev` @ `e6b4d49` (S5 fix), 2026-11-13

This re-runs the OWASP security test from `SECURITY_TEST_REPORT_AFTER_FIXES_2026-11-09.md` (the
"previous run", `f0322e1`) against the current `dev` branch. It uses the same tools, ZAP plan,
authorization harness, targeted scripts, dataset and machine, so the two reports compare directly.

It also adds four new sets of checks:

1. `s5_verify.py`: the S5 fix (price comparison scoped per user).
2. `cp_verify.py`: the **Cost Plus** module. Earlier reports did not cover it beyond its permission
   check.
3. `imp_verify.py`: the **Basic Rate import** on the server side. Earlier reports did not cover it.
4. `body_size_check.py` and `pool_error_check.sh`: large request bodies, and a database connection
   that drops while the app is idle.

Everything ran against a local throwaway copy of the app and database. No shared environment
(dev, UAT, production) was touched.

What changed since the previous run (`f0322e1..e6b4d49`):

| Commit | Change |
|---|---|
| `e6b4d49` | **S5 fix:** `GET /api/suppliers/price-comparison` now applies `projectAccessClause`, so Staff see only their own projects' catalog rates. Adds `npm run verify:price-comparison-scope`. No dependency change (`package.json` gains only the script line). |

## 1. Summary

**S5 is fixed and verified. Nothing regressed. One new Low finding (N8) and two Info items (N9,
N10) were found, all in areas no earlier run had tested.**

- **S5.** Harness section D's price-comparison check moved from FAIL to PASS. It is the only one of
  the 274 verdicts that changed. `s5_verify.py` passed 84 of 84 checks:
  - all 13 Staff accounts that hold `priceComparison:view` see exactly the projects and row counts
    an independent database query gives
  - query-string and header tricks are ignored
  - the list and the item detail agree
  - a membership change applies to a session that is already logged in
- **Cost Plus (first test).** 53 / 53 pass:
  - a Staff user cannot read or change another user's Cost Plus project, expense or payment
  - this holds whether the attacker uses the foreign ids directly or pairs its own parent id with a
    foreign child id
  - smuggled `ownerId` / `recordedById` fields are ignored
- **N8 (Low, new).** Basic Rate import can **overwrite existing catalog items** (rate, name, unit,
  supplier) with only `projects:create`. The single-item edit for the same change needs
  `projects:edit`, and returned 403 for the same user (§5.1).
- **ZAP** raised the same 7 alert types as the previous run: 0 High, no SQL injection, no error
  disclosure.
- **Static scans** are identical to the previous run:
  - `npm audit`: 0
  - Trivy: 0 vulnerabilities
  - Semgrep: 2 findings, both known
  - gitleaks: 2 known false positives

| | Previous run (`f0322e1`) | This run (`e6b4d49`) |
|---|---|---|
| Authorization harness (274 checks) | 263 pass, 7 review, 4 fail (S5 + 3 false positives) | **264 pass**, 7 review, 3 fail (the same 3 false positives). 1 verdict changed: S5. |
| S3/S4 regression (`fix_verify.py`, 58) | 57 pass, 1 expected | 57 pass, the same 1 expected |
| Cheque feature (`cheque_verify.py`, 76) | 76 pass | 76 pass |
| 11-09 fixes (`fixes_verify.py`, 51) | 50 pass, 1 false positive | 50 pass, the same false positive |
| S5 checks (`s5_verify.py`, 84, new) | — | **84 / 84 pass** |
| Cost Plus checks (`cp_verify.py`, 53, new) | — | **53 / 53 pass** |
| Basic Rate import checks (`imp_verify.py`, 17, new) | — | 16 pass, **1 fail (N8)** |
| ZAP alert types | 7 (0 High, 2 Medium, 2 Low, 3 Info) | 7, the same types (0 High, 2 Medium, 2 Low, 3 Info) |
| Server errors in the ZAP scan log | 0 | 10 `ECONNRESET` on database reads, all at scan start, caused by the test machine (§4.3) |
| `npm audit` (all / `--omit=dev`) | 0 / 0 | 0 / 0 |
| Trivy vulnerabilities / misconfigurations | 0 / 8 | 0 / 8 (the same IDs, S11) |
| Semgrep (source) | 2 | 2 (the same: S9 and a false positive) |

Status of every item:

| ID | Severity | Status after this run |
|---|---|---|
| S1 | High | **Closed.** Fixed in code; the project team confirmed on 2026-11-13 that the old UAT Admin password has been rotated. (Confirmed by the team, not verified by this test, which cannot reach UAT.) |
| S2 | High | Fixed, still holds (`npm audit` 0) |
| S3 | Medium | Fixed, still holds |
| S4 | Medium | Fixed, still holds |
| S5 | Low | **Fixed in `e6b4d49`, verified** (harness D, and `s5_verify.py` 84 / 84) |
| S6 | Low | Fixed, still holds (13 / 13). **The deployment smoke test from the previous report is still not confirmed** (§7). |
| S7 | Low | Fixed, still holds (9 / 9; ZAP 10037 absent) |
| S8 | Low | Open: CSP `style-src 'unsafe-inline'` |
| S9 | Low | Open: DB TLS `rejectUnauthorized: false` (`src/lib/pg.ts:318`) |
| S10 | Low | Fixed in the tree, still holds. Files are still in git history. |
| S11 | Low | Open: Helm pod hardening (8 Trivy misconfigurations) |
| S12 | Info | Open: demo password must not work on deployed environments |
| N1–N5 | Low / Info | Fixed, still hold |
| N6 | Info | Open, by design: the cheque register has no row limit |
| N7 | Info | Open, unchanged: all 10 places named in the previous report still point at `doc/test/security/` |
| **N8** | **Low** | **New:** Basic Rate import updates existing items without `projects:edit` (§5.1) |
| **N9** | Info | **New:** request bodies up to 10 MB are buffered in memory before any check (§5.2) |
| **N10** | Info | **New:** the `pg` pool has no `'error'` listener; a dropped idle connection writes a ~100-line object dump to the log (§5.3) |

## 2. Environment

| Item | Value |
|---|---|
| Code | `origin/dev` @ `e6b4d49` ("fix(security): scope price comparison to the caller's projects (S5)"). Checked out in a fresh detached worktree (`../vega-sectest5`). The local `dev` working tree was not touched. |
| Build | `npm ci`, `npx prisma generate`, `prisma migrate deploy`, `npm run build` (clean, exit 0), then `next start -p 3201 -H 0.0.0.0` (production mode, Next.js 16.4.5), with a freshly generated throwaway `SESSION_SECRET` (48 random bytes) |
| Port | 3201, as in the previous runs |
| Database | `vega_sec5`, a fresh clone of `vega_prod` in `vega-perf-pg` (34 projects, 26 users, 6,011 expenses, 1,114 catalog items), with all migrations applied. No earlier test database was reused. |
| Accounts | As in the previous runs: Admin `nimal@` (harness), Admin `sanduni@` (ZAP, targeted checks), Staff `perf.staff1` (member of 7 projects, owner of none), `perf.staff11`, `perf.staff12` (no `priceComparison:view`, no `projects:create`). New: all 13 active Staff accounts holding `priceComparison:view`, `perf.staff13` (owner of 3 projects, member of none), and three accounts created by the scripts (§8). |
| Tools | OWASP ZAP 2.17.0 (`zaproxy/zap-stable`, the same image as the previous run, same plan), the five harness scripts from the previous run (changed only in their database name), four new scripts, Semgrep, gitleaks, Trivy, `npm audit` |

The ~2 s response time seen by the Python scripts is the same client-side IPv6 fallback described
in the 11-09 report (`curl` answers in milliseconds). It does not affect any verdict.

## 3. Verification of the S5 fix

### 3.1 Code review

`src/app/api/suppliers/price-comparison/route.ts` now:

- keeps the `requirePermission('priceComparison', 'view')` gate
- adds `where 1=1${projectAccessClause(session, 'p.id', 'p.ownerId')}` (table-qualified, as the
  helper's comment requires)
- binds `session.userId` for non-Admin callers only

This is the same pattern as the item detail route (`./item/route.ts`) and the supplier detail route
(`/api/suppliers/[id]`). The handler still reads no query parameter. The response shape did not
change.

### 3.2 Targeted checks (`s5_verify.py`)

The script works out which projects each user may see with its own owner-or-member SQL, not with
`projectAccessClause` (the code under test). It then compares the API response with that answer.

| Group | Checks | Result |
|---|---|---|
| **P1** Gate: no cookie → 401; forged `alg:none` cookie → 401; `x-middleware-subrequest` bypass header (both the `middleware` and `src/proxy` forms) without a cookie → 401; Staff without `priceComparison:view` → 403 on the list and on the item detail; `POST` → 405 | 7 | 7 pass |
| **P2** Admin still sees every catalog item (1,114 rows) and every project that has one | 2 | 2 pass |
| **P3** For each of the **13** active Staff accounts holding `priceComparison:view`: no foreign project in the response; row count equals the database; rows with no supplier are kept. Plus: the member branch (`perf.staff1`, member-only) and the owner branch (`perf.staff13`, owner-only) are each exercised. | 41 | 41 pass |
| **P4** `perf.staff1`: 9 query strings (`?projectId=perf_p001`, repeated `project=`, `?all=1`, `?scope=all`, `?role=Admin`, `?userId=<admin id>`, `?projectId=' or 1=1--`, `?projectId[]=`, a 4,000-character parameter) and 4 headers (`X-User-Id`, `X-Role`, `X-Forwarded-For`, `x-middleware-subrequest`) each return a byte-identical body to the plain request | 13 | 13 pass |
| **P5** List and detail agree: for 10 groups that also exist on foreign projects, the item detail returns exactly the list's projects, and its audit and usage entries stay inside the caller's projects. A group that exists only on foreign projects (`Cement`) is absent from the list and returns 404 on the detail. | 13 | 13 pass |
| **P6** A new Staff user with `priceComparison:view` and no projects gets `200 []`, and 404 on the detail | 3 | 3 pass |
| **P7** Admin adds `perf.staff13` to a foreign project: the **same, already logged-in** session sees it on the next request. Admin removes the membership: the next request no longer shows it. | 4 | 4 pass |
| Cleanup | 1 | pass |
| **Total** | **84** | **84 pass** |

Rows seen per account, compared with the database (from `s5_verify_stdout.txt`):

| Account | Projects reachable | Projects in response | Rows | Rows in DB | Projects hidden |
|---|---|---|---|---|---|
| `perf.staff1` | 7 | 7 | 245 | 245 | 27 |
| `perf.staff5` | 9 | 9 | 329 | 329 | 25 |
| `perf.staff10` | 1 | 1 | 34 | 34 | 33 |
| `perf.staff13` | 3 | 3 | 104 | 104 | 31 |
| 9 more accounts | 3–8 | equal | equal | equal | 26–31 |

Before the fix, the previous run measured the Staff user receiving all 34 projects' rows here.

The harness's own section D check moved from FAIL to PASS. `retest.py` now prints the same 7
project ids for the Staff user's price-comparison response and for its accessible projects.

## 4. Regression

### 4.1 Authorization harness

`authz_test.py`, compared check by check with the previous run. 273 verdicts are unchanged. 1
changed: section D, `GET /api/suppliers/price-comparison`, moved from FAIL to PASS (S5).

| Section | Previous run | This run |
|---|---|---|
| A. Unauthenticated (72) | 72 pass | 72 pass |
| B. IDOR, Staff → foreign project (55) | 54 pass, 1 review → pass on retest | Same |
| C. Cross-parent IDOR (24) | 19 pass, 4 review → pass on retest, 1 false positive (`L-003`) | Same |
| **D. List leakage (9)** | 7 pass, **S5 fail**, 1 false positive | **8 pass**, 1 false positive |
| E. Vertical privilege (32) | 32 pass | 32 pass |
| F. CSRF (7) | 7 pass | 7 pass |
| G. Session (6) | 5 pass, 1 false positive (cookie-flag check) | Same |
| H. Login (9) | 9 pass | 9 pass |
| I. Injection/input (54) | 52 pass, 2 info | Same |
| J. Headers (6) | 6 pass | 6 pass |

The 3 remaining FAILs are the same false positives as in every earlier run:

- **`L-003`.** That code also exists in the Staff user's own project, so the PATCH edits the
  caller's own item.
- **`/api/payments/other-payees/history`.** It returns 400 for a missing required parameter, with
  no data.
- **The cookie-flag check.** It mis-parses `SameSite=lax`. The cookie is `Secure; HttpOnly;
  SameSite=lax`.

`retest.py` gave the same results as before:

- foreign draft promote → 403/404
- foreign item → 404
- foreign milestone payment → 404 (×3)
- foreign clone → 403

### 4.2 Targeted scripts from the earlier runs

| Script | Previous | This run |
|---|---|---|
| `fix_verify.py` (S3/S4) | 57 / 58, 1 expected (login truncation, by design) | Same |
| `cheque_verify.py` (cheque feature) | 76 / 76 | 76 / 76 |
| `fixes_verify.py` (S6, S7, N2–N5, Cheque method filter) | 50 / 51, 1 false positive | Same. The false positive is the response echoing the requested `project` filter, with `rows: []`. |

### 4.3 ZAP: previous run and this run

| Alert | Previous | This run |
|---|---|---|
| 40018 SQL Injection / 90022 Application Error Disclosure / 10023 Debug Error Messages | 0 | 0 |
| 10038 CSP Header Not Set / 10037 `X-Powered-By` | 0 | 0 |
| 10055 CSP `style-src unsafe-inline` (Medium) | 4 | 5 (S8, the same single policy, on one more page) |
| 10106 HTTP Only Site (Medium) | 1 | 1 (local HTTP; not an issue) |
| 40014 XSS Weakness, Persistent in JSON (Low) | 7 | 7 (stored strings in JSON, no sink; same URLs) |
| 10096 Timestamp Disclosure (Low) | 5 | 5 (false positive: amounts) |
| 10111, 10109, 10104 (Info) | 3 types | 3 types |

Timings: AJAX spider 6m07s, active scan 8m03s (previously 6m05s / 11m38s).

**First attempt discarded.** The first ZAP run ended with exit code 2 inside its report job. Its
active scan lasted 17 s, and it wrote an empty HTML report and no JSON. It was re-run with the
identical plan and image, and only the second, complete run is reported above. The ZAP log of the
first run was not kept (the container was started with `--rm`).

**Server log during the active scan:** 571 lines.

- **19 one-line `pg` warnings** (`22021` NUL byte, `22007` bad datetime). `apiRoute` turns each into
  a 400 by design, the same mix as the previous run's 20:
  - 5 on milestone `dueDate`
  - 4 on variations
  - 4 on price-comparison item
  - 6 on `next-code`
- **10 `Error: read ECONNRESET`, which were HTTP 500s.** These are not scanner sockets. Each is a
  Postgres read in `src/lib/rbac.ts` → `pg.ts` `first()` that lost its connection. The evidence
  points to the test machine, not the app:
  - All 10 are in the first 125 log lines. The first attack payload appears at line 193.
  - Postgres logged no client disconnect at all.
  - The first ZAP attempt showed the same pattern (1 reset, at its start), and so did the 11-09 run
    (2 resets).
  - The app reaches Postgres through Docker Desktop's forwarded port `55432`. Starting a new
    container (`--add-host=host.docker.internal:host-gateway`) appears to reset the connections
    already open through it.

  The app returned 500 for those requests and carried on; the scan and every later request worked.
  This is the right behaviour, and the app needs no change for it. A deployed pod reaches Postgres
  on the cluster network, not through Docker Desktop.

## 5. New items

### 5.1 N8: Basic Rate import updates existing items without `projects:edit` (Low)

`POST /api/projects/[id]/basic-rate/import` (`src/app/api/projects/[id]/basic-rate/import/route.ts`)
requires `projects:create` (line 39) and project access (line 40). A row that carries the `id` of an
existing item in that project is **updated**: name, category, unit, rate and supplier (line 88). It
also writes a price-history entry and syncs the promoted-from draft's price. Every other route that
changes an existing catalog item requires `projects:edit`:

- `PATCH /api/projects/[id]/basic-rate/[code]`
- `PATCH /api/basic-rate/[itemId]`

Reproduced (`imp_verify.py`, group E):

| Step | Result |
|---|---|
| Admin creates a Staff user with `projects:view` + `projects:create` only, and adds it to `perf_p004` | 200, 200 |
| That user: `PATCH /api/projects/perf_p004/basic-rate/L-001` `{"rate": 1.23}` | **403** `Missing permission: projects:edit` |
| That user: `POST /api/projects/perf_p004/basic-rate/import` with `{"rows":[{"id":"perf_p004_bi005", "name":…, "cat":…, "unit":…, "rate":1.23}]}` | **200** `{"created":0,"updated":1,"errors":[]}`. In the database, the rate went from 22235.9 to **1.23**. |

The rate was restored afterwards. The change stays inside a project the user can already reach (an
`id` from another project is refused; see below). The impact is that a "create but not edit" role
cannot be enforced. No account in today's dataset has that combination: all 19 Staff accounts with
`projects:create` also have `projects:edit`. It becomes real as soon as an Admin defines such a role,
for example a data-entry role.

**Fix:** in the import route, if any row has an `id`, also require
`hasPermission(session, 'projects', 'edit')`. Either return 403 for the request, or refuse those
rows with a per-row error so that new rows still import.

The rest of the import route held up (16 checks):

- no session → 401; `projects:view` only → 403; a foreign project → 403
- the caller's own project URL with a **foreign project's item id** → row refused ("This item no
  longer exists in this project"); the foreign rate did not change
- 19 hostile rows in one request, every one refused and nothing written:
  - name: a number, an object, blank, 500 characters, or containing NUL
  - code: a number, containing NUL, 100 characters, or an existing code
  - category: SQL text, or an array
  - unit: unknown
  - rate: a string, negative, zero, or `null`
  - supplier: unknown
  - id: unknown, or an object
- `rows` missing, empty, not an array, 5,001 rows, or a non-object row → 400; a 200,000-character
  description → refused per row
- a formula-looking description (`=HYPERLINK(…)`) is stored as plain text; the exports write it as
  text (as reviewed on 11-09)

The `.xlsx` / `.pdf` file itself is parsed in the browser (`src/lib/importCatalog.ts`, exceljs and
pdfjs-dist 6.2.108). A malicious file can only affect the browser of the user who opens it. The
server never sees the file.

### 5.2 N9: request bodies up to 10 MB are buffered in memory (Info)

`parseBody()` (`src/lib/api.ts:98`) calls `request.json()` with no size limit of its own. The only
limit is Next.js's `experimental.proxyClientMaxBodySize`, which defaults to **10 MB** because
`src/proxy.ts` is in the request path. Next.js clones and buffers each body up to that size in
memory before the route runs.

Measured as Admin on `POST /api/suppliers` (`body_size_check.py`):

| Body | Result | Server memory (working set, before → after) |
|---|---|---|
| 1 MB | 400 `Name must be 120 characters or fewer` | 215 → 218 MB |
| 10 MB | 400 `Invalid request body` (cut at 10 MB, so no longer valid JSON) | 218 → 182 MB |
| 50 MB | 400 `Invalid request body` | 182 → 170 MB |
| 100 MB | 400 `Invalid request body` | 169 → 180 MB |
| 50 MB unauthenticated login | 400 `Invalid request body` | — |

`/api/healthz` stayed 200 after each. Each over-limit request logs one line, `Request body exceeded
10MB for /api/suppliers. Only the first 10MB will be available unless configured.`

Nothing failed, and the cap holds. But any caller, including an unauthenticated one on
`/api/auth/login`, can make the server buffer 10 MB per request. The largest legitimate body is a
5,000-row Basic Rate import, which is well under 1 MB.

**Fix (optional hardening):** set `experimental: { proxyClientMaxBodySize: '2mb' }` in
`next.config.ts` (see `node_modules/next/dist/docs/.../proxyClientMaxBodySize.md`), after checking the
largest real import. A body limit on the Traefik ingress would do the same job, earlier.

### 5.3 N10: no `'error'` listener on the `pg` pool (Info)

`getPool()` (`src/lib/pg.ts:297–330`) creates the `Pool` without `pool.on('error', …)`. node-postgres
emits an error on the pool when an **idle** pooled connection is closed by the server (for example a
Postgres restart, a failover, or an administrator ending the connection). With no listener, that is
an uncaught exception.

Tested (`pool_error_check.sh`):

- 6 parallel requests opened 4 idle connections
- `pg_terminate_backend` ended all 4
- **Result:** the process **did not exit**, and `/api/healthz` and `/api/ready` both answered 200
  three seconds later. Next.js's server catches the uncaught exception and logs it.

The log entry for each dropped connection is a ~100-line dump of the `pg` `Client` object. It
includes the database host, port, user and database name. The password is **not** in it, because
node-postgres keeps it non-enumerable (checked: no match for the password or `connectionString` in
the full server log).

This is not exploitable. It means the app survives an idle disconnect only because of framework
behaviour, and a Postgres restart floods the log. A future runtime change could also turn it into a
process exit.

**Fix:** add `pool.on('error', e => console.warn('pg idle client error', (e as { code?: string }).code ?? ''))`
where the pool is created.

### 5.4 Cost Plus module (first test, no finding)

The dataset has no Cost Plus data, and no user holds `costPlus:*`. `cp_verify.py` therefore creates
its fixtures over the API:

- **Project A:** Admin creates it, with an expense, a cheque expense payment and a cheque client
  payment.
- **Project B:** a new Staff user holding only `costPlus:view/create/edit/delete` creates it, with
  the same children.

| Group | What was tried | Checks | Result |
|---|---|---|---|
| **V** No `costPlus` permission (`perf.staff1`) | list, read, create, delete, and each child list | 8 | all 403; no session → 401 |
| **H** Staff → Admin's project A by its own ids | portfolio list (A absent); read / patch / delete A; list / create / patch / delete its expense; list / create / patch / delete its expense payment; list / create / patch / delete its client payment | 16 | all 403 |
| **X** Own parent + foreign child | `expense-payments?expenseId=<B>&paymentId=<A's>` (PATCH, DELETE); `client-payments?projectId=<B>&paymentId=<A's>` (PATCH, DELETE); an extra `projectId=<B>` on A's expense and project | 7 | all 403/404. A's project, expense and both payments unchanged in the database (cheque status still `received`). |
| **M** Mass assignment | create with `id`, `ownerId=<admin>`, `marginAmount`; patch with `ownerId`; payment with `recordedById`, `expenseId` | 3 | all ignored (server id, the caller as owner, margin computed; recorder = the caller, expense = the URL's) |
| **I** Input | negative or 1,000,000% margin, `2026-02-30`, a 200,000-character name, unknown status, category or method, amount over the 100 billion cap, negative amount, SQL in `supplierId`, overpaying an expense, a client payment over the project total, an unknown cheque status, malformed JSON, a missing or unknown `projectId`, `id=' or 1=1--` | 17 | all 400/404 with the field's own message |
| Fixtures, cleanup | | 2 | pass |
| **Total** | | **53** | **53 pass** |

Code review agrees. Every handler resolves the parent first: an expense handler looks up the
expense's **own** project before `requireCostPlusAccess`. The shared ledger helpers in
`src/lib/incomePayments.ts` (`paymentMethodOf`, `deletePayment`) match the payment id **and** its
parent foreign key. Payment inserts are capped in the same transaction (`select … for update`).

## 6. Static scans

| Tool | Previous | This run |
|---|---|---|
| `npm audit` (all / `--omit=dev`) | 0 / 0 | 0 / 0 |
| Trivy vulnerabilities | 0 / 0 | 0 / 0 |
| Trivy misconfigurations | 8 (S11) | 8, the same IDs: `DS-0026`, `KSV-0011`, `KSV-0014` (High: root file system not read-only), `KSV-0015`, `KSV-0016`, `KSV-0018`, `KSV-0020`, `KSV-0021` |
| Trivy secrets | 0 | 0 |
| Semgrep (source; `.next/` and `node_modules/` excluded) | 2 | 2, the same: `bypass-tls-verification` `src/lib/pg.ts:318` (S9) and `detected-bcrypt-hash` `src/lib/auth.ts:66` (`DUMMY_PASSWORD_HASH`, false positive) |
| gitleaks (`origin/dev` history, 136 commits) | 2 | 2, the same sealed-secret ciphertext false positives |

## 7. What is still open

No High item is open. S1 was closed on 2026-11-13, when the team confirmed that the UAT Admin
password had been rotated. If the old value or a variant of it was also used anywhere else, change
it there too.

In priority order:

1. **S6 deployment smoke test.** After the current build deploys, save one record (for example,
   rename a supplier) on dev and on UAT. A 403 `Cross-origin request rejected` means Traefik is not
   passing `X-Forwarded-Proto: https`. This test cannot see the deployed network.
2. **N8 (Low).** Require `projects:edit` for import rows that update an existing item. This is a
   small change in one route.
3. **S12 (Info).** Try the README demo credentials against dev, UAT and production (with approval).
4. **S8, S9, S11 (Low).** CSP inline styles, DB certificate verification, Helm pod hardening.
5. **N7, N9, N10 (Info).** Fix the doc paths; lower `proxyClientMaxBodySize`; add the pool error
   listener. N6 needs no action now. The CI action SHAs from the previous report are still
   unconfirmed against GitHub.

## 8. Not covered

The same limits as the previous reports:

- deployed environments, the Traefik ingress, real-hostname TLS and the cluster
- Traefik's handling of `X-Real-Ip` and `X-Forwarded-Proto`
- denial of service beyond single large requests

No longer on this list:

- **The Cost Plus module.** Now covered (§5.4).
- **Malicious Excel files on the Basic Rate import.** The server side is now covered (§5.1). The
  file is parsed only in the user's own browser.

**Test data left in `vega_sec5`** (a throwaway clone):

- 2 created Staff accounts that could not be deleted, because they had audit records (409 by design)
- 3 Cost Plus projects
- 1 imported catalog row with a formula-looking name
- the records ZAP created

A third created account was deleted. The temporary membership was removed.

## 9. How to reproduce

```powershell
# 1. Code under test in its own worktree
git fetch origin
git worktree add --detach ../vega-sectest5 e6b4d49
cd ../vega-sectest5; npm ci; npx prisma generate

# 2. Fresh copy of the performance database, plus migrations
docker start vega-perf-pg
docker exec vega-perf-pg psql -U vega -d postgres -c "create database vega_sec5 template vega_prod"
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_sec5?sslmode=disable'
npx prisma migrate deploy; npm run build

# 3. App
$env:SESSION_SECRET='<any string of 32+ characters>'
npx next start -p 3201 -H 0.0.0.0

# 4. Tests (second terminal), from evidence-2026-11-13/, in this order
python -I authz_test.py <dir>
python -I retest.py <dir>
python -I fix_verify.py <dir>
python -I cheque_verify.py <dir>     # DB checks need docker access to vega-perf-pg
python -I fixes_verify.py <dir>      # uses cheque_verify.py's fixtures
python -I s5_verify.py <dir>         # new
python -I cp_verify.py <dir>         # new
python -I imp_verify.py <dir>        # new
python -I body_size_check.py <dir> <server pid>
sh pool_error_check.sh <server pid> <server log>

# 5. ZAP: log in as sanduni@vegahomes.lk, put the vega_session value into a copy of zap-plan.yaml
#    (keep the copy outside the docs repo), then
docker run --rm --add-host=host.docker.internal:host-gateway -v "<dir>:/zap/wrk:rw" -u zap zaproxy/zap-stable zap.sh -cmd -autorun /zap/wrk/<plan copy>.yaml

# 6. Static
npm audit --json; npm audit --omit=dev --json
docker run --rm -v "<worktree>:/src:ro" semgrep/semgrep semgrep scan --config p/typescript --config p/nextjs --config p/javascript --config p/owasp-top-ten --config p/secrets --exclude .next --exclude node_modules --json --metrics=off /src
docker run --rm -v "<repo>:/repo:ro" -v "<out>:/out" zricethezav/gitleaks:latest git /repo --redact --log-opts="origin/dev" --report-format json --report-path /out/gitleaks.json
docker run --rm -v "<worktree>:/src:ro" aquasec/trivy:latest fs --scanners vuln,misconfig,secret --skip-dirs node_modules --skip-dirs .next --format json /src
```

Raw output is in [`evidence-2026-11-13/`](evidence-2026-11-13/):

- `zap-report.html` / `.json`, `zap-plan.yaml` (cookie redacted), `zap_stdout.txt`
- `server-log-during-zap.txt`, `server-log-full.txt` (the whole run)
- `authz_results.json`, `fix_verify_results.json`, `cheque_verify_results.json`,
  `fixes_verify_results.json`, `s5_verify_results.json`, `cp_verify_results.json`,
  `imp_verify_results.json`, `body_size_results.json` (and each script's `_stdout.txt`)
- `pool_error_check_stdout.txt`
- `npm-audit.json`, `npm-audit-prod.json`, `semgrep.json`, `gitleaks.json` (redacted), `trivy.json`
- the ten test scripts
