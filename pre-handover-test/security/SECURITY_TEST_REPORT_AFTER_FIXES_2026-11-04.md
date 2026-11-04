# Security Test Report: after fixes (`dev` @ `348da81`), 2026-11-04

This re-runs the security test from `SECURITY_TEST_REPORT_2026-11-04.md` (the "before" report)
against `dev` after PR 1338 was merged. PR 1338 fixes S1–S4. It uses the same tools, ZAP plan,
authorization harness, dataset and machine, so the two reports compare directly. It also adds 58
targeted checks for the S3 and S4 fixes.

Fixes included (`dev` @ `348da81`, PR 1338):

| ID | Finding | Fix |
|---|---|---|
| S1 | UAT Admin password committed in `prisma/seed-user.ts` | Script reads `SEED_USER_PASSWORD` and refuses to run without it (`396a792`) |
| S2 | Next.js 16.3.5 critical/high advisories; `zod`, `sharp`, `dompurify` | `next@^16.4.1` (installed 16.4.5), `zod@^4.6.6` (4.6.7), `sharp@^0.35.5`, `dompurify@^3.4.17` override (`e526f23`) |
| S3 | Unvalidated input returned HTTP 500 | Shared `text`/`optionalDate` schemas, `SyntaxError` → 400, Postgres `23503` → 409 and `22P02`/`22007`/`22008`/`22021` → 400, enum payment method, activity existence checks (`170911b`, `9486293`) |
| S4 | No maximum string length on ~30 routes | `.max()` on every string field, capped arrays (`6b32c88`, `ef2d50d`, `079dcdd`, `f2bbbf8`, `486af24`) |

S5–S12 were not part of PR 1338 and are re-reported here unchanged.

## 1. Summary

**S2, S3 and S4 are fixed and verified. S1 is fixed in code, but the password rotation still has
to be confirmed.** No new vulnerability was introduced, and every access-control check that
passed before still passes.

| | Before (`0e15246`) | After (`348da81`) |
|---|---|---|
| Server errors logged during the ZAP active scan | **1,803** | **1** (`ECONNRESET`, scanner hung up) |
| ZAP alert types | 11 (1 High, 2 Medium, 5 Low, 3 Info) | 9 (0 High, 3 Medium, 3 Low, 3 Info) |
| ZAP "SQL Injection" / "Application Error Disclosure" / "Debug Error Messages" | Raised | **Gone** |
| `npm audit` (all deps) | 2 critical, 3 high, 9 moderate | **0 critical, 1 high**, 9 moderate |
| Authorization harness (274 checks), after manual triage | All access-control checks pass | All access-control checks pass |
| Injection/input checks in the harness | 3 FAIL (malformed JSON 500, 200,000-char name accepted, 15 MB body 500) | **0 FAIL** |
| S3/S4 targeted checks (new) | — | 56 / 58 pass; the 2 misses are expected behaviour (§3) |

| ID | Severity | Status after this run |
|---|---|---|
| S1 | High | **Fixed in code, verified.** The old value is still in git history (`f261fb6`, `396a792`). **Rotation not verified by this test; confirm it was done.** |
| S2 | High | **Fixed, verified.** `next` 16.4.5, `zod` 4.6.7, `sharp` 0.35.5, `dompurify` 3.4.17. One high remains in `source-map-js` (build-time; see N1) |
| S3 | Medium | **Fixed, verified.** 1,803 → 1 server errors; 36/36 targeted S3 checks pass |
| S4 | Medium | **Fixed, verified.** 20/20 targeted length/array caps return 400; login truncates by design |
| S5 | Low | Open (unchanged): price comparison is company-wide, drill-down is scoped |
| S6 | Low | Open (unchanged): CSRF Origin check ignores scheme |
| S7 | Low | Open (unchanged): `X-Powered-By: Next.js` |
| S8 | Low | Open (unchanged): CSP `style-src 'unsafe-inline'` |
| S9 | Low | Open (unchanged): DB TLS `rejectUnauthorized: false` |
| S10 | Low | Open (unchanged): `.backups/`, `.shannon/` still tracked |
| S11 | Low | Open (unchanged): Helm pod hardening |
| S12 | Info | Open (unchanged): demo password must not work on deployed environments |
| N1 | Low | **New:** `source-map-js` 1.2.1 high advisory remains |
| N2 | Low | **New:** `/favicon.ico` 404 page served without CSP |
| N3 | Info | **New:** `PATCH /api/activities/<unknown code>` returns 200 |

## 2. Environment

| Item | Value |
|---|---|
| Code | `origin/dev` @ `348da81` ("Merged PR 1338: Security: fix pre-handover findings S1–S4 ..."), checked out in a separate git worktree so the local `dev` working tree was not touched |
| Build | `npm ci`, `npx prisma generate`, `npm run build`, then `next start -p 3200` (production mode, Next.js 16.4.5) |
| Database | `vega_sec2`, a fresh clone of `vega_prod` in `vega-perf-pg` (same 34 projects, 26 users, 6,011 expenses). The before run used a separate clone (`vega_sec`), so neither run saw the other's test data. |
| Accounts | Same as the before run: Admin `nimal@vegahomes.lk` (harness), Admin `sanduni@vegahomes.lk` (ZAP and targeted checks), Staff `perf.staff1@vegahomes.lk` |
| Tools | Same versions and configuration as the before run: OWASP ZAP 2.17.0 (identical plan, 89 seeded requests), `authz_test.py` (unchanged, byte-identical), Semgrep, gitleaks, Trivy, `npm audit` |

**Build note:** the first `npm run build` in the fresh worktree failed type-checking at
`prisma/reset-and-reseed.ts:403` (`Parameter 'x' implicitly has an 'any' type`). Running `npx
prisma generate` fixed it, so the cause was the missing generated client, not the code. Any CI job
that builds from a clean checkout must run `prisma generate` before `next build`. The current
Dockerfile and pipeline should be checked for this step.

## 3. Verification of S1–S4

### S1: committed password

| Check | Result |
|---|---|
| `git grep -nE "PASSWORD\s*=\s*'" prisma/` | Only `prisma/seed.ts:388` (the public demo password, S12). The UAT literal is gone. |
| `npx tsx prisma/seed-user.ts` with `SEED_USER_PASSWORD` unset | Exit 1: `SEED_USER_PASSWORD is not set; refusing to seed a user with a built-in password`. No DB connection attempted. |
| Success log line | `Seeded user: <email>`, no password |
| Git history | The old value is still in `f261fb6` (added) and `396a792` (removed), on every remote branch. **Expected**, since history was not rewritten. Removing the file does not make the old value secret again. |
| Rotation on UAT | **Not verified.** This test does not touch UAT. The owner must confirm the UAT password was changed, along with any other place that value or a variant was used. |

### S2: dependencies

| Package | Before | After | Status |
|---|---|---|---|
| `next` | 16.3.5 | 16.4.5 | Fixed: all 3 critical and 2 high advisories, plus the medium and low ones up to 16.3.8 |
| `zod` | 4.6.5 | 4.6.7 | Fixed |
| `sharp` | 0.35.4 | 0.35.5 | Fixed |
| `dompurify` (via `jspdf`) | 3.4.15 | 3.4.17 | Fixed |
| `source-map-js` (via `postcss`) | 1.2.1 | 1.2.1 | **Not fixed** (N1) |
| `exceljs` chain | moderate | moderate | Unchanged, as planned |

Trivy agrees: 0 critical, 1 high (`source-map-js`), 2 medium (`minimatch`).

### S3: input reaching Postgres

The first run's server log had 1,803 errors under the same ZAP scan. This run had 1, an
`ECONNRESET` from the scanner closing a socket. No zod-passed input reached Postgres and failed
there.

Targeted checks (`fix_verify.py`, all as Admin so validation, not access control, is what's
tested):

| Check | Requests | Result |
|---|---|---|
| Bad dates (`'`, `not-a-date`, `2026-13-45`, `...'; select pg_sleep(5)--`, `x start-sleep -s 15`) on stage `startDate`/`completionDate`, milestone `dueDate`, project `start` (PATCH and POST), expense payment `date` | 26 | All 400 |
| Payment method not in enum (`S4feV4lu3`, `Cheque` on an expense payment) | 2 | 400 `Choose a valid payment method` |
| NUL byte in supplier and trade names | 2 | 400 |
| Malformed JSON (`{not json`, a PHP payload, a Java class-loader payload) on POST and PATCH | 3 | 400 `Invalid request body` |
| 15 MB body | 1 | 400 (was 500) |
| Basic Price draft with an unknown activity code | 1 | 400 |
| Delete an activity used by 133 Basic Price drafts | 1 | 409 `This activity is used by 133 Basic Price draft(s)...` (was 500) |
| **Total S3** | **36** | **36 pass** |

### S4: length and size caps

| Check | Requests | Result |
|---|---|---|
| 200,000-character name on create: suppliers, sub-contractors, activities, trades, units, categories, roles, projects, Basic Price, Basic Rate, filter presets, users | 12 | All 400 (`Name must be ... characters or fewer`) |
| 200,000-character field on update: supplier, company profile, project client, user name | 4 | All 400 |
| Role with 501 permissions | 1 | 400 (cap 500) |
| Basic Rate clone with 100,000 codes | 1 | 400 |
| Normal-sized supplier create still works | 1 | 200 |
| Valid stage date still accepted | 1 | 200 `{"ok":true}` |
| Login with a 100,000-character email and password | 1 | 401 `Invalid email or password`, **by design** (see below) |
| **Total S4** | **21** | **20 pass, 1 expected** |

The login route does not reject over-long input with 400. It truncates to `EMAIL_MAX` /
`PASSWORD_MAX` and returns the same generic 401 as any failed login
(`src/app/api/auth/login/route.ts:45-47`). That is the right choice: a distinct 400 would tell an
attacker something about the input that the generic message is designed to hide. The check's
expectation was wrong, not the code.

The other targeted miss is not an S3/S4 item; see N3.

## 4. Regression: authorization harness

`authz_test.py` ran unchanged (byte-identical to the before run's copy). Results after the same
manual triage as before:

| Section | Before | After |
|---|---|---|
| A. Unauthenticated (64 API pairs, 5 pages, 3 forged tokens) | 72 pass | 72 pass |
| B. IDOR, Staff → foreign project (55) | 54 pass, 1 review → pass on retest | Same |
| C. Cross-parent IDOR (24) | 19 pass, 4 review → pass on retest, 1 false positive (`L-003`) | Same |
| D. List leakage (9) | 7 pass, S5, 1 false positive (missing query param) | Same |
| E. Vertical privilege (32) | 32 pass | 32 pass |
| F. CSRF (7) | 6 pass, S6 | Same |
| G. Session (6) | 5 pass, 1 false positive (cookie-flag check) | Same |
| H. Login (9) | 9 pass | 9 pass |
| I. Injection/input (54) | 49 pass, **3 fail** (S3/S4), 2 info | **52 pass**, 2 info |
| J. Headers (6) | 5 pass, S7 | Same |

`retest.py` (valid bodies for the review items) gave the same results as before:

- Foreign draft promote → 403/404
- Foreign item patch → 404
- Foreign milestone payment cheque status → 404
- Clone from a foreign project → 403

The new validation did not open or move any access-control check.

## 5. ZAP: before and after

| Alert | Before | After |
|---|---|---|
| 40018 SQL Injection (High, low confidence; false positive) | 1 | **0** |
| 90022 Application Error Disclosure (Low) | 3 | **0** |
| 10023 Information Disclosure – Debug Error Messages (Low) | 3 | **0** |
| 10055 CSP: `style-src unsafe-inline` (Medium) | 5 | 1 (S8, unchanged) |
| 10038 CSP Header Not Set (Medium) | 0 | **1** (N2) |
| 10106 HTTP Only Site (Medium) | 1 | 1 (local HTTP; not an issue) |
| 40014 XSS Weakness, Persistent in JSON Response (Low) | 3 | 7 (stored strings in JSON; no sink; see before report §4 "Also noted") |
| 10037 `X-Powered-By` (Low) | 5 | 5 (S7, unchanged) |
| 10096 Timestamp Disclosure (Low) | 5 | 5 (false positive: amounts) |
| 10111, 10109, 10104 (Info) | 3 types | 3 types |

The scan took about the same time as before (AJAX spider 5m38s, active scan 7m14s).

## 6. New items

### N1: `source-map-js` high advisory remains (Low)

`source-map-js@1.2.1` (CVE-2026-93749, event-loop DoS via indexed source-map section offsets)
comes in through `postcss@8.5.28`. It is used when CSS is built, not when requests are served,
so a request cannot reach it. It is the only remaining high in `npm audit`.

**Fix:** add `"source-map-js": "^1.2.2"` to `overrides`.

### N2: `/favicon.ico` 404 page has no CSP (Low)

`src/proxy.ts` sets the CSP and its matcher excludes `favicon.ico`. The repo has no favicon file
(neither `src/app/favicon.ico` nor `public/favicon.ico`), so the request falls through to Next's
built-in 404 HTML page, served with `X-Frame-Options` and `nosniff` but no
`Content-Security-Policy`. The page reflects nothing user-controlled, so it cannot be used for
injection.

This was probably present before too; the before run's spider just didn't request it.

**Fix:** add a favicon file (which also stops the browser's 404 on every page load), or set a
static CSP for non-proxied paths in `next.config.ts` `headers()`.

### N3: activity rename returns 200 for an unknown code (Info)

`PATCH /api/activities/ZZZ-NOPE` with `{"name":"x"}` returns 200 `{"code":"ZZZ-NOPE","name":"x"}`.
No row is created (checked: 0 rows). The `update` affects nothing and the route echoes the input.
This is a correctness bug, not a security one: it needs `activities:edit`, and nothing is
written.

**Fix:** check the update's row count, or `select` first, and return 404.

## 7. Static scans: before and after

| Tool | Before | After |
|---|---|---|
| `npm audit` (all) | 14 (2 critical, 3 high, 9 moderate) | 10 (0 critical, 1 high, 9 moderate) |
| `npm audit --omit=dev` | — | 9 (0 critical, 1 high, 8 moderate) |
| Trivy vulnerabilities (critical/high) | 4 / 5 | **0 / 1** |
| Trivy misconfig | 8 (S11) | 8 (S11, unchanged) |
| Semgrep | 10 | 10, the same items (S9, S10, `DUMMY_PASSWORD_HASH` false positive, CI action tags) |
| gitleaks | 17 (local repo, all refs and stash) | 2 on `origin/dev` history (sealed-secret ciphertext, false positives). The perf-result JWTs from the before run were only in a local stash and untracked files. |

gitleaks' default rules never flagged the S1 password, before or after. It was found by reading
the code. Secret scanning alone would not have caught it, so keep a manual review step.

## 8. What is still open

In priority order:

1. **S1 rotation.** Confirm the UAT Admin password was changed, along with anywhere the old value
   or a variant was used. Until then, S1 is not closed.
2. **S12.** Try the README demo credentials against dev, UAT and production (with approval).
3. **CI build step.** Make sure clean-checkout builds run `prisma generate` (§2 build note).
4. N1 `source-map-js` override, N2 favicon, S7 `poweredByHeader: false`: one-line changes each.
5. S5 product-owner decision on price comparison; S6 full-origin CSRF check.
6. S8–S11 hardening and repo hygiene.

## 9. How to reproduce

```powershell
# 1. Fixed code in its own worktree (leaves the main working tree alone)
git worktree add --detach ../vega-sectest origin/dev
cd ../vega-sectest; npm ci; npx prisma generate; npm run build

# 2. Fresh copy of the performance database
docker exec vega-perf-pg psql -U vega -d postgres -c "create database vega_sec2 template vega_prod"

# 3. App
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_sec2?sslmode=disable'
$env:SESSION_SECRET='<any string of 32+ characters>'
npx next start -p 3200 -H 0.0.0.0

# 4. Tests (second terminal), from a folder holding authz_test.py, retest.py and fix_verify.py
python -I authz_test.py <dir>
python -I retest.py <dir>
python -I fix_verify.py <dir>

# 5. ZAP and static scans: identical to §8 of the before report
```

Raw output is in [`evidence-2026-11-04-after-fixes/`](evidence-2026-11-04-after-fixes/):

- `zap-report.html` / `.json`
- `authz_results.json`, `fix_verify_results.json`
- `npm-audit.json`, `semgrep.json`
- `gitleaks.json`, `trivy.json` (secret values redacted)
- `fix_verify.py`, `authz_test.py`

The session cookie in `zap-plan.yaml` is redacted.
