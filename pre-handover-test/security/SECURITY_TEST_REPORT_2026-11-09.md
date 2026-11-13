# Security Test Report: `dev` @ `48ed074` (cheque payments), 2026-11-09

This re-runs the OWASP security test from 2026-11-04 against the current `dev` branch. Since the
last run (`348da81`), `dev` has gained the **cheque payment feature**: 8 commits, 12 files, one
migration. The test does two things:

1. **Regression.** It re-runs the same ZAP plan, authorization harness and static scans, on the
   same dataset and machine, so the results compare directly with
   `SECURITY_TEST_REPORT_AFTER_FIXES_2026-11-04.md` (the "previous run").
2. **New surface.** It adds 76 targeted checks (`cheque_verify.py`) for the new endpoint and the new
   cheque fields, plus a manual code review of the change.

Everything ran against a local throwaway copy of the app and database. No shared environment
(dev, UAT, production) was touched.

What changed in the code under test (`348da81..48ed074`):

| Commit | Change |
|---|---|
| `eccda9d` | Migration `20261106000000_expense_payment_cheque_dates`: `PaymentMethod` gains `Cheque`; `expense_payments` gains nullable `chequeInvoicedDate` / `chequeReleaseDate` (`DATE`) and two `CHECK` constraints |
| `75eed2b` | `POST/GET /api/projects/[id]/expenses/[expenseId]/payments` accept and return the two cheque dates |
| `007f7c5` | **New endpoint** `GET /api/payments/cheques`: every cheque expense payment the session can see |
| `6c381b2`, `81e28b6`, `06da0c0`, `cf8ce65`, `48ed074` | UI: date pickers, "Export Cheque Transactions" (Excel / PDF), report template, layout fixes |

## 1. Summary

**No new vulnerability was found. The cheque feature is correctly guarded, and every control that
passed on 2026-11-04 still passes.**

- The new `GET /api/payments/cheques` requires a session and `payments:view`, and is scoped to the
  caller's own projects. A Staff user saw their own project's cheque and never another project's,
  with or without query parameters that try to widen the scope.
- Recording a cheque payment requires `projects:edit` and access to the expense's real project. A
  foreign expense was refused through both a foreign URL and the caller's own project URL.
- Both cheque dates are validated before they reach Postgres. 46 malformed, injected or oversized
  date values all returned 400. The `pg_sleep(5)` payload caused no delay. The ordering rule
  (release ≥ invoiced) is enforced in the API and again by a database `CHECK` constraint.
- Extra fields smuggled into the request body (`id`, `recordedById`, `expenseId`) were ignored.
- The export carries stored text as plain values. No formula objects are written to Excel, and React
  escapes the on-screen view.
- **The authorization harness gave exactly the same verdicts as the previous run on all 274
  checks.**
- **No HTTP 500 was logged during the ZAP active scan.** The only `Error` lines were 2
  `ECONNRESET`s, from the scanner closing sockets.

| | Previous run (`348da81`) | This run (`48ed074`) |
|---|---|---|
| Authorization harness (274 checks) | 261 pass, 7 review, 6 fail (all triaged) | **Identical, check by check** (0 verdicts changed) |
| S3/S4 regression checks (`fix_verify.py`, 58) | 56 pass, 2 expected | 56 pass, the same 2 expected |
| Cheque feature checks (`cheque_verify.py`, new) | — | **76 / 76 pass** |
| Server errors (5xx) logged during the ZAP active scan | 1 (`ECONNRESET`) | **0** (2 `ECONNRESET`, scanner side) |
| ZAP alert types | 9 (0 High, 3 Medium, 3 Low, 3 Info) | 8 (0 High, 2 Medium, 3 Low, 3 Info) |
| `npm audit` (all deps) | 10 (0 critical, 1 high, 9 moderate) | 2 (0 critical, 1 high, 1 moderate); no dependency changed (§6) |
| Trivy vulnerabilities (critical / high) | 0 / 1 | 0 / 1 |

Status of every open item:

| ID | Severity | Status after this run |
|---|---|---|
| S1 | High | Fixed in code. **Rotation of the old UAT Admin password is still not confirmed.** Not verifiable from here. |
| S2 | High | Fixed, still holds (`next` 16.4.5, `zod` 4.6.7, `sharp` 0.35.5, `dompurify` 3.4.17) |
| S3 | Medium | Fixed, still holds. The new cheque fields follow the same pattern. |
| S4 | Medium | Fixed, still holds. A 200,000-character cheque date returns 400. |
| S5 | Low | Open (unchanged): price comparison is company-wide; its drill-down is scoped |
| S6 | Low | Open (unchanged): CSRF Origin check ignores the scheme |
| S7 | Low | Open (unchanged): `X-Powered-By: Next.js` |
| S8 | Low | Open (unchanged): CSP `style-src 'unsafe-inline'` |
| S9 | Low | Open (unchanged): DB TLS `rejectUnauthorized: false` (`src/lib/pg.ts:318`) |
| S10 | Low | Open (unchanged): `.backups/` (1 file) and `.shannon/` (17 files) still tracked |
| S11 | Low | Open (unchanged): Helm pod hardening (8 Trivy misconfigurations) |
| S12 | Info | Open (unchanged): demo password must not work on deployed environments |
| N1 | Low | Open (unchanged): `source-map-js` 1.2.1 high advisory (build-time) |
| N2 | Low | Open (unchanged): `/favicon.ico` 404 has no CSP. ZAP did not request it this run, but a manual check confirms it. |
| N3 | Info | Open (unchanged): `PATCH /api/activities/<unknown code>` returns 200 |
| N4 | Info | **New:** NUL byte in the login email returns 400, not the generic 401 |
| N5 | Info | **New:** a year-0000 cheque date passes validation and is rejected by Postgres with a generic message |
| N6 | Info | **New:** `GET /api/payments/cheques` has no row limit |
| — | — | **Closed:** the CI build-step note from the previous run. `prisma generate` is in the `Dockerfile` (line 23) and in `ci.yml` (line 44). |

## 2. Environment

| Item | Value |
|---|---|
| Code | `origin/dev` @ `48ed074` ("fix(payments): keep Excel TOTAL out of sort range; ..."). Checked out in a separate detached worktree (`../vega-sectest3`), so the local `dev` working tree (8 commits behind, with uncommitted changes) was not touched. |
| Build | `npm ci`, `npx prisma generate`, `npm run build` (clean, exit 0), then `next start -p 3201 -H 0.0.0.0` (production mode, Next.js 16.4.5), with a freshly generated throwaway `SESSION_SECRET` |
| Port | **3201**, not 3200. Port 3200 was already serving another local instance (the e2e run), which was left alone. The harness and ZAP plan were changed only in their port number. |
| Database | `vega_sec3`, a fresh clone of `vega_prod` in `vega-perf-pg` (34 projects, 26 users, 6,011 expenses), with the new migration applied by `prisma migrate deploy`. Earlier runs used their own clones (`vega_sec`, `vega_sec2`). |
| Accounts | As before: Admin `nimal@vegahomes.lk` (harness), Admin `sanduni@vegahomes.lk` (ZAP and targeted checks), Staff `perf.staff1@vegahomes.lk` (7 of 34 projects). New checks also used `perf.staff11` (no `payments:view`) and `perf.staff12` (`payments:view` but no `projects:edit`). |
| Tools | OWASP ZAP 2.17.0 (same plan, plus 3 seeded requests for the cheque feature), `authz_test.py` / `retest.py` / `fix_verify.py` (unchanged apart from the port), new `cheque_verify.py`, Semgrep, gitleaks, Trivy, `npm audit` |

**Timing note.** Every request the Python harness made took about 2 s, 401s included. `curl`
answers the same endpoints in about 3 ms. The 2 s is Python's `http.client` trying IPv6 `::1`
before IPv4 on Windows, against a server bound to `0.0.0.0`. It comes from the test client, not
the app. The time-based injection checks still work: `pg_sleep(5)` would push a request to at least
7 s, and the slowest cheque check took 2.2 s.

## 3. New surface: cheque payments

### 3.1 Code review

| Area | What the code does | Assessment |
|---|---|---|
| `GET /api/payments/cheques` (`src/app/api/payments/cheques/route.ts`) | `requirePermission('payments','view')`, then `projectAccessClause(session, 'pr.id', 'pr.ownerId')` (table-qualified, as the helper's comment requires). Bound parameters only; reads no query string. | Correct. Same gate as the Payments page. |
| Payment POST (`.../expenses/[expenseId]/payments/route.ts`) | `requirePermission('projects','edit')`. Looks up the expense, then `requireProjectAccess` on the **expense's own** project (not the URL's), then `parseBody`. Overpayment guard and insert in one statement. | Correct. A mismatched URL project cannot widen access. |
| Date validation | `dateString()` (a real calendar day) plus a strict `^\d{4}-\d{2}-\d{2}$` shape. Cheque requires both dates, with release ≥ invoiced (`src/lib/chequeDates.ts`, shared with the UI). Non-cheque methods store `null` whatever is sent. | Correct; one edge case, N5. |
| Database | Two `CHECK` constraints: dates only on `Cheque` rows, and release ≥ invoiced. Reads use `::text` / `to_char`, so no time-zone shift. | Good defence in depth. Verified present, and verified to block a direct SQL insert. |
| Export (`src/lib/chequeReport.ts`, `exportXlsx.ts`, `exportPdf.ts`) | Built in the browser from the endpoint's JSON. Excel cells are plain strings, numbers and `Date`s; no `{ formula }` objects. The PDF uses `jspdf` text and `autoTable`, not `.html()`. | No formula or HTML injection path. A payee named `=HYPERLINK(...)` is written as text. |
| Response content | Payment ID, project, payee, invoice, amount, dates, recorder's display **name**. No user IDs, emails or hashes. | Checked: no hash and no user ID in the response. |

### 3.2 Targeted checks (`cheque_verify.py`)

| Group | Checks | Result |
|---|---|---|
| **C1** Fixtures: Admin records one cheque on a Staff-accessible project (`perf_p004`) and one on a foreign project (`perf_p001`) | 2 | 2 pass |
| **C2** `GET /api/payments/cheques`: no cookie → 401; forged `alg:none` cookie → 401; Staff without `payments:view` → 403; `POST` → 405; Admin sees both cheques; **Staff sees its own cheque and not the foreign one**; every Staff row belongs to a project Staff can open; `?project=perf_p001&projectId=perf_p001` is ignored; no hash or user ID in the response | 9 | 9 pass |
| **C3** Cheque write and read: Staff → foreign expense via the foreign URL (403) and via its **own** project URL (403); Staff reads a foreign expense's payments (403); user without `projects:edit` (403); foreign `Origin` (403); no `Origin` (403); Staff on its own expense (200) | 7 | 7 pass |
| **C4** Validation: no dates, only one date, release before invoiced (exact message), method `cheque` (lower case), malformed JSON, overpayment, negative amount, and each of 19 bad values on **each** of the two date fields: `2026-02-30`, `2026-1-5`, ISO with time, `2026-01-05 10:00`, `05/01/2026`, `not-a-date`, `'`, `2026-01-05'; select pg_sleep(5)--`, trailing NUL, 200,000 × `A`, `0000-01-01`, `99999-01-01`, `+002026-01-05`, `2026-W01-1`, number, array, `{"$gt": ""}`, `true`, `null` | 46 | 46 return 400, all under 2.3 s |
| **C5** Stored values: same-day cheque and post-dated cheque accepted; Cash payment sent with cheque dates stores `null` for both; smuggled `id` / `recordedById` / `expenseId` ignored (the DB row has a server-generated ID, the real caller and the URL's expense); both `CHECK` constraints present; a direct SQL insert of cheque dates on a Cash row is rejected | 10 | 10 pass |
| **C6** Stored payload: supplier named `<img src=x onerror=alert(1)>=HYPERLINK("http://evil.example","x")`, linked to a cheque expense. The endpoint returns it as an inert JSON string with `Content-Type: application/json`. | 2 | 2 pass |
| **Total** | **76** | **76 pass** |

## 4. Regression

### 4.1 Authorization harness

`authz_test.py` was unchanged apart from the port. Every one of the 274 checks gave the same verdict
as the previous run (compared check by check, 0 differences):

| Section | Previous run | This run |
|---|---|---|
| A. Unauthenticated (64 API pairs, 5 pages, 3 forged tokens) | 72 pass | 72 pass |
| B. IDOR, Staff → foreign project (55) | 54 pass, 1 review → pass on retest | Same |
| C. Cross-parent IDOR (24) | 19 pass, 4 review → pass on retest, 1 false positive (`L-003`) | Same |
| D. List leakage (9) | 7 pass, S5, 1 false positive (missing query param) | Same |
| E. Vertical privilege (32) | 32 pass | 32 pass |
| F. CSRF (7) | 6 pass, S6 | Same |
| G. Session (6) | 5 pass, 1 false positive (cookie-flag check) | Same |
| H. Login (9) | 9 pass | 9 pass |
| I. Injection/input (54) | 52 pass, 2 info | 52 pass, 2 info |
| J. Headers (6) | 5 pass, S7 | Same |

`retest.py` (valid bodies for the review items) also matched the previous run:

- Foreign draft promote → 403/404
- Foreign item patch → 404
- Foreign milestone payment cheque status → 404 (×3)
- Clone from a foreign project → 403

The price comparison list still returns all 34 projects to a Staff user with 7 (S5).

### 4.2 S3/S4 fixes (`fix_verify.py`)

56 of 58 pass, the same as the previous run. The 2 misses are the same known items: N3 (unknown
activity code returns 200) and login truncation, which is by design.

One check now passes for a different reason. "Payment method `Cheque` on an expense payment"
used to return 400 because `Cheque` was not a valid method. `Cheque` is now valid, so it returns
400 `Cheque Invoiced Date is required` because the request has no dates. The expectation (400) still
holds.

### 4.3 ZAP: previous run and this run

| Alert | Previous | This run |
|---|---|---|
| 40018 SQL Injection | 0 | 0 |
| 90022 Application Error Disclosure | 0 | 0 |
| 10023 Debug Error Messages | 0 | 0 |
| 10038 CSP Header Not Set (Medium) | 1 (N2, `/favicon.ico`) | 0. The spider did not request `/favicon.ico` this time; N2 is still present (§5). |
| 10055 CSP: `style-src unsafe-inline` (Medium) | 1 | 5 instances, same single policy (S8) |
| 10106 HTTP Only Site (Medium) | 1 | 1 (local HTTP; not an issue) |
| 40014 XSS Weakness, Persistent in JSON Response (Low) | 7 | 7 (stored strings in JSON, no sink; same URLs) |
| 10037 `X-Powered-By` (Low) | 5 | 5 (S7) |
| 10096 Timestamp Disclosure (Low) | 5 | 5 (false positive: amounts) |
| 10111, 10109, 10104 (Info) | 3 types | 3 types |

The cheque endpoints were seeded into the scan (a cheque POST, the payment list GET and
`/api/payments/cheques`). They raised no alerts.

**Server log during the active scan:** 464 lines, 0 HTTP 500s. The two `Error` lines are
`read ECONNRESET` (scanner closing sockets). The rest are 22 one-line `pg` warnings
(`22021` NUL byte, `22007` bad datetime), which `apiRoute` turns into 400s by design: 5 on milestone
`dueDate`, 4 on variations, 4 on price-comparison item, 6 on `next-code`, 1 on `/api/payments`, 1 on
login. Timings: AJAX spider 6m08s, active scan 9m18s (previously 5m38s / 7m14s).

## 5. New items

### N4: NUL byte in the login email returns 400 (Info)

`POST /api/auth/login` with `"email": "a\u0000@x.lk"` returns 400 `One of the values entered is not
valid.` (Postgres `22021`, mapped by `apiRoute`). An unknown but well-formed email returns the
generic 401 `Invalid email or password`. The 400 reveals nothing about any account, because the
error happens before any user can match. But it is the one login input that does not get the
generic answer, and it writes a `pg` warning to the log.

**Fix:** reject `\u0000` in the login schema and return the same generic 401, as the route already
does for over-long input.

### N5: year-0000 cheque date reaches Postgres (Info)

`chequeInvoicedDate: "0000-01-01"` passes `dateString()`, because JavaScript accepts year 0. Postgres
then rejects it (`22008`), and the caller gets the generic 400 `One of the values entered is not
valid.` rather than `Enter a valid date` on the field. Nothing is stored and nothing breaks. The
user just gets a vaguer message. (`99999-01-01` is already rejected by the shape check.)

**Fix:** give `isoDate` a sensible range, for example year 1900–2100.

### N6: cheque register has no row limit (Info)

`GET /api/payments/cheques` returns every cheque payment the caller can see in one response. That is
deliberate (the export is the full register), and it needs `payments:view`. Today it is small: the
dataset had no cheque payments before this feature. It will grow without bound, and every export
click runs the full query.

**Fix:** none needed now. If the register reaches thousands of rows, add a date range or a hard cap.

### N2 re-check (still open)

`GET /favicon.ico` → `404` with `X-Powered-By: Next.js` and no `Content-Security-Policy` (checked
with `curl`). There is still no `src/app/favicon.ico` or `public/favicon.ico`.

## 6. Static scans: previous run and this run

| Tool | Previous | This run |
|---|---|---|
| `npm audit` (all) | 10 (0 critical, 1 high, 9 moderate) | **2** (0 critical, 1 high `source-map-js`, 1 moderate `postcss-selector-parser`) |
| `npm audit --omit=dev` | 9 | 1 (high) |
| Trivy vulnerabilities (critical / high) | 0 / 1 | 0 / 1 (`source-map-js`, CVE-2026-93749) |
| Trivy misconfig | 8 (S11) | 8, the same IDs (S11) |
| Trivy secrets | 0 | 0 |
| Semgrep | 10 | 10 in source, the same items: S9, S10 (5 hashes in `.backups/`, 1 in `.shannon/`), `DUMMY_PASSWORD_HASH` false positive, 2 CI action tags. A further 13 hits are in the `.next/` build output, which was not on disk at the previous scan: compiled copies of the same dummy hash, and React internals. |
| gitleaks (`origin/dev` history) | 2 | 2, the same sealed-secret ciphertext false positives |

**About the `npm audit` drop:** `package.json` and `package-lock.json` did not change between
`348da81` and `48ed074`. The same `exceljs` → `archiver` / `glob` / `minimatch` versions are
installed. The 8 moderates that disappeared were dropped by the advisory database, not by a code
change. The remaining two are both PostCSS build tooling: `source-map-js` (N1) and
`postcss-selector-parser` 6.1.4 (GHSA-rj75-hqrm-r3gf, quadratic CPU on crafted selectors; build-time
only, the CSS is the app's own).

**Fix (both):** add `"source-map-js": "^1.2.2"` and `"postcss-selector-parser": "^6.1.5"` to
`overrides`.

## 7. What is still open

In priority order:

1. **S1 rotation.** Confirm the UAT Admin password was changed, along with anywhere the old value
   or a variant was used. Until then, S1 is not closed.
2. **S12.** Try the README demo credentials against dev, UAT and production (with approval).
3. One-line changes:
   - N1 and `postcss-selector-parser` overrides
   - N2 favicon
   - S7 `poweredByHeader: false`
   - N4 NUL byte at login
   - N5 date range
4. S5 product-owner decision on price comparison; S6 full-origin CSRF check.
5. S8–S11 hardening and repo hygiene.

## 8. Not covered

The same limits as before:

- deployed environments, the Traefik ingress, real-hostname TLS and the cluster
- Traefik's handling of `X-Real-Ip`
- the cost-plus module beyond its permission check
- malicious Excel files on the Basic Rate import
- denial of service beyond single large requests

Also not covered: the generated `.xlsx` / `.pdf` files were reviewed in code, but not opened from a
real browser download in this run. The Playwright test `tests/11-cheque-payments.spec.ts` covers
that flow functionally.

## 9. How to reproduce

```powershell
# 1. Code under test in its own worktree (leaves the main working tree alone)
git fetch origin
git worktree add --detach ../vega-sectest3 origin/dev     # 48ed074
cd ../vega-sectest3; npm ci; npx prisma generate; npm run build

# 2. Fresh copy of the performance database, plus the new migration
docker start vega-perf-pg
docker exec vega-perf-pg psql -U vega -d postgres -c "create database vega_sec3 template vega_prod"
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_sec3?sslmode=disable'
npx prisma migrate deploy

# 3. App (port 3201; 3200 was in use)
$env:SESSION_SECRET='<any string of 32+ characters>'
npx next start -p 3201 -H 0.0.0.0

# 4. Tests (second terminal), from evidence-2026-11-09/
python -I authz_test.py <dir>
python -I retest.py <dir>
python -I fix_verify.py <dir>
python -I cheque_verify.py <dir>      # needs docker access to vega-perf-pg for the DB checks

# 5. ZAP: log in as sanduni@vegahomes.lk, put the vega_session value into a copy of zap-plan.yaml, then
docker run --rm --add-host=host.docker.internal:host-gateway -v "<dir>:/zap/wrk:rw" -u zap zaproxy/zap-stable zap.sh -cmd -autorun /zap/wrk/<plan copy>.yaml

# 6. Static (as in the 2026-11-04 report; Trivy now also skips .next)
npm audit --json
docker run --rm -v "<worktree>:/src:ro" semgrep/semgrep semgrep scan --config p/typescript --config p/nextjs --config p/javascript --config p/owasp-top-ten --config p/secrets /src
docker run --rm -v "<repo>:/repo:ro" zricethezav/gitleaks:latest git /repo --redact --log-opts="origin/dev"
docker run --rm -v "<worktree>:/src:ro" aquasec/trivy:latest fs --scanners vuln,misconfig,secret --skip-dirs node_modules --skip-dirs .next /src
```

Raw output is in [`evidence-2026-11-09/`](evidence-2026-11-09/):

- `zap-report.html` / `.json`, `zap-plan.yaml` (session cookie redacted), `zap_stdout.txt`
- `server-log-during-zap.txt`
- `authz_results.json`, `authz_stdout.txt`, `retest_stdout.txt`
- `fix_verify_results.json`, `cheque_verify_results.json` (and their `_stdout.txt`)
- `npm-audit.json`, `semgrep.json`, `gitleaks.json` (redacted), `trivy.json`
- the four test scripts
