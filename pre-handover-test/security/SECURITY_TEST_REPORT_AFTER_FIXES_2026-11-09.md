# Security Test Report: after fixes (`dev` @ `f0322e1`), 2026-11-09

This re-runs the security test from `SECURITY_TEST_REPORT_2026-11-09.md` (the "previous run",
`48ed074`) against `dev` after the follow-up fixes. It uses the same tools, ZAP plan, authorization
harness, targeted scripts, dataset and machine, so the two reports compare directly. It also adds 51
checks aimed at the fixes themselves (`fixes_verify.py`).

Everything ran against a local throwaway copy of the app and database. No shared environment
(dev, UAT, production) was touched.

What changed since the previous run (`48ed074..f0322e1`):

| Commit | Change |
|---|---|
| `bd9564d` | **Security follow-ups:** S6 scheme-aware Origin check; S7 `poweredByHeader: false`; S10 `.backups/`, `.shannon/` and 5 security docs removed from the app repo and ignored; N3 activity rename 404; N4 NUL byte at login → generic 401; N5 cheque date range 1900–2100; N1 `source-map-js` and `postcss-selector-parser` overrides; N2 `public/favicon.ico`; GitHub Actions pinned to commit SHAs |
| `f5a0b23` | Feature: **Method filter on Payments now includes `Cheque`**; export button moved into the filter row |
| `f0322e1` | Test-only change (Playwright) |

## 1. Summary

**All 9 items targeted by the fixes are fixed and verified. No new vulnerability was introduced.
Nothing regressed.**

- The authorization harness gave the same verdicts as the previous run on 272 of 274 checks. The
  2 that changed are the S6 and S7 checks, which moved from FAIL to PASS.
- The ZAP active scan logged **no errors at all**: no 500s and no `ECONNRESET`. The `X-Powered-By`
  alert is gone, and no High alert was raised.
- `npm audit` is now **0 vulnerabilities**, including dev dependencies. Trivy finds 0
  vulnerabilities, and Semgrep findings fell from 10 to 2.

| | Previous run (`48ed074`) | This run (`f0322e1`) |
|---|---|---|
| Authorization harness (274 checks) | 261 pass, 7 review, 6 fail (all triaged) | **263 pass**, 7 review, 4 fail. The 4 are the same known items: S5 and 3 false positives. |
| S3/S4 regression checks (`fix_verify.py`, 58) | 56 pass, 2 expected | **57 pass**, 1 expected. N3 now passes. |
| Cheque feature checks (`cheque_verify.py`, 76) | 76 pass | 76 pass |
| Fix checks (`fixes_verify.py`, 51, new) | — | **50 pass**, 1 false positive (§3.8) |
| Server errors during the ZAP active scan | 0 (2 `ECONNRESET`) | **0** (0 `ECONNRESET`) |
| ZAP alert types | 8 (0 High, 2 Medium, 3 Low, 3 Info) | **7** (0 High, 2 Medium, 2 Low, 3 Info) |
| `npm audit` (all deps) | 2 (1 high, 1 moderate) | **0** |
| Trivy vulnerabilities | 0 critical / 1 high | **0 / 0** |
| Semgrep (source) | 10 | **2** (S9, plus the `DUMMY_PASSWORD_HASH` false positive) |

Status of every item, by severity:

| ID | Severity | Status after this run |
|---|---|---|
| S1 | High | Fixed in code. **Rotation of the old UAT Admin password is still not confirmed.** Not verifiable from here. |
| S2 | High | Fixed, still holds |
| S3 | Medium | Fixed, still holds |
| S4 | Medium | Fixed, still holds |
| S5 | Low | **Open**: price comparison is company-wide (product-owner decision) |
| S6 | Low | **Fixed, verified** (13 / 13). See the deployment note in §3.1. |
| S7 | Low | **Fixed, verified** (9 / 9; ZAP 10037 gone) |
| S8 | Low | **Open**: CSP `style-src 'unsafe-inline'` |
| S9 | Low | **Open**: DB TLS `rejectUnauthorized: false` |
| S10 | Low | **Fixed in the tree, verified.** Files are still in git history (§3.3). |
| S11 | Low | **Open**: Helm pod hardening (8 Trivy misconfigurations, unchanged) |
| S12 | Info | **Open**: demo password must not work on deployed environments |
| N1 | Low | **Fixed, verified** (`source-map-js` 1.2.2, `postcss-selector-parser` 6.1.6) |
| N2 | Low | **Fixed, verified** (`/favicon.ico` → 200 PNG) |
| N3 | Info | **Fixed, verified** (unknown code → 404) |
| N4 | Info | **Fixed, verified** (6 / 6 → generic 401) |
| N5 | Info | **Fixed, verified** (11 / 11 → field's own message) |
| N6 | Info | Open, by design: the cheque register has no row limit |
| N7 | Info | **New:** code comments and the README point to 5 docs that moved to the docs repo |
| — | Info | **Fixed:** CI GitHub Actions are pinned by commit SHA (no longer a Semgrep hit) |

## 2. Environment

| Item | Value |
|---|---|
| Code | `origin/dev` @ `f0322e1` ("test(payments): read export button and filter row in the same frame"). Checked out in a fresh detached worktree (`../vega-sectest4`). Local `dev` is now at the same commit. |
| Build | `npm ci`, `npx prisma generate`, `prisma migrate deploy`, `npm run build` (clean, exit 0), then `next start -p 3201 -H 0.0.0.0` (production mode, Next.js 16.4.5), with a freshly generated throwaway `SESSION_SECRET` |
| Port | 3201, as in the previous run. Port 3200 still serves another local instance, which was left alone. |
| Database | `vega_sec4`, a fresh clone of `vega_prod` (34 projects, 26 users, 6,011 expenses), with all migrations applied. No earlier test database was reused. |
| Accounts | As in the previous run: Admin `nimal@` (harness), Admin `sanduni@` (ZAP, targeted checks), Staff `perf.staff1` (7 of 34 projects), `perf.staff11` (no `payments:view`), `perf.staff12` (no `projects:edit`), and `perf.staff7` / `perf.staff8` for the N4 login checks |
| Tools | Same versions and plan as the previous run. The harness scripts differ from the previous run only in their database name. |

The ~2 s response time seen by the Python harness is the same client-side IPv6 fallback described
in the previous report (`curl` answers in milliseconds). It does not affect any verdict.

## 3. Verification of the fixes

### 3.1 S6: CSRF Origin check now compares the scheme

`src/proxy.ts` now works out the request's scheme the way Next.js does: `https` if
`X-Forwarded-Proto` contains `https`, otherwise `http`. It then requires the `Origin`'s scheme
**and** host to match.

| Check (`POST /api/suppliers` unless stated) | Result |
|---|---|
| `http` Origin, no `X-Forwarded-Proto` (local http) | 200, allowed |
| **`https` Origin to the `http` app (the previous run's failing case)** | **403** (was 200) |
| `https` Origin + `X-Forwarded-Proto: https` (as behind Traefik) | 200, allowed |
| **`http` Origin + `X-Forwarded-Proto: https`** (an http page on the same host posting to the https app) | **403** |
| `https` Origin + `X-Forwarded-Proto: http` | 403 |
| `https://evil.example`, prefix trick `https://localhost:3201.evil.example`, `null` (all with `X-Forwarded-Proto: https`) | 403, 403, 403 |
| Upper-case `HTTPS://LOCALHOST:3201` (normalised by `URL`) | 200, allowed |
| `X-Forwarded-Proto: https,http` (proxy chain) | 200, allowed |
| Login with a scheme-swapped Origin | 403 |
| `DELETE` with a scheme-swapped Origin | 403 |
| `GET` with a scheme-swapped Origin (not a mutating method) | 200, unaffected |
| **Total** | **13 / 13 pass** |

The harness's own "scheme swap" check (section F) moved from FAIL to PASS.

**Deployment note.** The fix assumes the app sees `X-Forwarded-Proto: https` in the deployed
environments. `deploy/helm/templates/ingress.yaml` says Traefik terminates TLS (cert-manager,
`letsencrypt-prod`), and Traefik sets that header. Two cases would break it:

- something in front of Traefik terminates TLS and reaches Traefik over plain http, or
- Traefik is configured to pass through a client-supplied value.

In either case, every save in that environment would return 403 `Cross-origin request rejected`.
This test cannot see the deployed network. **After this build reaches dev and UAT, save one record
(for example, rename a supplier) in each environment to confirm.** If it returns 403, check
Traefik's `X-Forwarded-Proto` before rolling back.

### 3.2 S7: no `X-Powered-By`

The header is absent on every response checked:

- `/login` and `/` (anonymous: 307 to `/login`)
- `/` and `/payments` (authenticated)
- `/api/auth/me` (200 and 401)
- `/api/healthz`
- a 404 page
- `/favicon.ico`

9 / 9 pass. ZAP alert 10037 dropped from 5 instances to 0. The harness's section J check moved from
FAIL to PASS.

### 3.3 S10: sensitive files out of the repo

| Check | Result |
|---|---|
| `git ls-files .backups .shannon doc/test/security` on `f0322e1` | 0 files (previously 1 DB dump, 17 pentest files, 5 security docs) |
| `.gitignore` | `.backups/`, `.shannon/` and `perf/results/` are all ignored (`git check-ignore` confirms each) |
| Semgrep | The 6 hash hits in `.backups/` and `.shannon/` are gone |
| Git history | The files are **still in history** (the dump since `2280932`, removed in `bd9564d`). Expected: history was not rewritten. As the 11-04 report noted, the dump's 5 hashes are all the public demo password, so there is no live credential. Rewriting history is optional. |

The 5 removed security docs exist in the docs repo under `vega-construction-docs/test/security/`.
See N7.

### 3.4 N1: build-tool advisories

`overrides` now pins `source-map-js@^1.2.2` (installed 1.2.2) and `postcss-selector-parser@^6.1.5`
(installed 6.1.6). `npm audit` and `npm audit --omit=dev` both report **0 vulnerabilities**, and
Trivy reports none.

### 3.5 N2: favicon

`GET /favicon.ico` → 200, `image/x-icon` (a PNG-in-ICO, 7,486 bytes). The 404 HTML page without a
CSP is no longer served for it. ZAP alert 10038 was not raised.

### 3.6 N3: unknown activity code

| Check | Result |
|---|---|
| `PATCH /api/activities/ZZZ-NOPE` | 404 `Activity not found` (was 200) |
| `PATCH /api/activities/01` to its current name | 200, unaffected |
| `ZZZ-NOPE` present afterwards | No |

`fix_verify.py` now passes this check too. Its only remaining miss is the login-truncation check,
which is behaviour by design (see the 11-04 after-fixes report).

### 3.7 N4 and N5

**N4: a NUL byte at login always ends in the generic 401.** 6 / 6 pass:

| Input | Result |
|---|---|
| NUL in an unknown email | 401 `Invalid email or password` |
| NUL **inside a real email** (`perf.staff7\u0000@vegahomes.lk`) with the **correct** password | 401, no session cookie issued |
| NUL at the end of a real email, correct password | 401, no session |
| NUL in the password | 401 |
| An email made only of NUL bytes | 401 |
| The same real user, clean input | 200, logged in normally |

Response times matched normal failed logins (~2.07 s), so the timing parity still holds. The login
`pg 22021` warning that ZAP triggered in the previous run did not appear this time.

**N5: cheque dates outside 1900–2100 get the field's own message.** 11 / 11 pass:

- `0000-01-01`, `0001-01-01`, `1899-12-31`, `2101-01-01` and `9999-12-31` on each date field →
  400 `Enter a valid date`. Previously year 0000 got the generic `One of the values entered is not
  valid.`
- The boundaries `1900-01-01` → `2100-12-31` → 200.
- No `pg 22008` warning was logged.

### 3.8 New: Cheque on the Payments Method filter

| Check | Result |
|---|---|
| `GET /api/payments?method=Cheque` | 200 |
| `method=cheque`, `Cheque'--`, `Cheque' or 1=1--`, `Cheque%00`, `Cash,Cheque` | 400 `Unknown payment method` (enum-validated, never reaches SQL) |
| Staff, `method=Cheque` | No foreign project in the result |
| Staff, `method=Cheque&project=perf_p001` (a foreign project) | 200, `rows: []`, `total: 0`. The script flagged this as FAIL because the response **echoes the requested filter** (`"filters":{"project":["perf_p001"]}`). It contains no foreign data. **False positive.** |

## 4. Regression

### 4.1 Authorization harness

`authz_test.py`, compared check by check with the previous run. 272 verdicts are unchanged and 2
changed, both for the better:

| Section | Previous run | This run |
|---|---|---|
| A. Unauthenticated (72) | 72 pass | 72 pass |
| B. IDOR, Staff → foreign project (55) | 54 pass, 1 review → pass on retest | Same |
| C. Cross-parent IDOR (24) | 19 pass, 4 review → pass on retest, 1 false positive (`L-003`) | Same |
| D. List leakage (9) | 7 pass, S5, 1 false positive | Same |
| E. Vertical privilege (32) | 32 pass | 32 pass |
| **F. CSRF (7)** | 6 pass, **S6 fail** | **7 pass** |
| G. Session (6) | 5 pass, 1 false positive (cookie-flag check) | Same |
| H. Login (9) | 9 pass | 9 pass |
| I. Injection/input (54) | 52 pass, 2 info | Same |
| **J. Headers (6)** | 5 pass, **S7 fail** | **6 pass** |

`retest.py` gave the same results as before: foreign draft promote 403/404, foreign item 404,
foreign milestone payment 404, foreign clone 403.

### 4.2 Cheque feature

`cheque_verify.py` passed 76 / 76 again:

- access control on `/api/payments/cheques`
- cross-project cheque writes
- 46 bad date values
- stored values and DB `CHECK` constraints
- mass assignment
- stored payload

The year-0000 cases now return `Enter a valid date` (N5).

### 4.3 ZAP: previous run and this run

| Alert | Previous | This run |
|---|---|---|
| 40018 SQL Injection / 90022 / 10023 | 0 | 0 |
| 10038 CSP Header Not Set | 0 | 0 |
| **10037 `X-Powered-By` (Low)** | **5** | **0** (S7 fixed) |
| 10055 CSP `style-src unsafe-inline` (Medium) | 5 | 4 (S8, same single policy) |
| 10106 HTTP Only Site (Medium) | 1 | 1 (local HTTP; not an issue) |
| 40014 XSS Weakness, Persistent in JSON (Low) | 7 | 7 (stored strings in JSON, no sink) |
| 10096 Timestamp Disclosure (Low) | 5 | 5 (false positive: amounts) |
| 10111, 10109, 10104 (Info) | 3 types | 3 types |

**Server log during the active scan:** 437 lines, **0 errors**. There were 20 one-line `pg`
warnings (`22021` NUL byte, `22007` bad datetime). `apiRoute` turns each into a 400 by design: 5 on
milestone `dueDate`, 4 on variations, 4 on price-comparison item, 6 on `next-code`, and 1 on
`/api/payments`. Timings: AJAX spider 6m05s, active scan 11m38s.

## 5. New item

### N7: references to the moved security docs (Info)

S10 removed 5 docs from `doc/test/security/` in the app repo. They still exist in the docs repo
(`vega-construction-docs/test/security/`), but 10 places in the app still use the old path:

- `README.md:50` (the migrate-job warning)
- `src/proxy.ts:27`
- `src/lib/securityHeaders.ts:18`
- `src/lib/sessionToken.ts:10`
- `src/lib/edgeRateLimit.ts:16`
- `src/app/api/auth/login/route.ts:17`
- `src/app/api/projects/[id]/owner/route.ts:30`
- `scripts/verify-rate-limit.ts:6`
- `playwright.config.ts:4,39`

This is not a security issue. A reader following a comment from a security-relevant line (CSRF,
rate limiting, login) will find nothing at that path.

**Fix:** change the prefix to `vega-construction-docs/test/security/` (or a link) in those 10 places.

## 6. Static scans: previous run and this run

| Tool | Previous | This run |
|---|---|---|
| `npm audit` (all / `--omit=dev`) | 2 / 1 | **0 / 0** |
| Trivy vulnerabilities | 0 critical / 1 high | **0 / 0** |
| Trivy misconfig | 8 (S11) | 8, the same IDs (S11) |
| Trivy secrets | 0 | 0 |
| Semgrep (source; `.next/` excluded) | 10 | **2**: `bypass-tls-verification` `src/lib/pg.ts:318` (S9) and `detected-bcrypt-hash` `src/lib/auth.ts:66` (`DUMMY_PASSWORD_HASH`, false positive). The `.backups/`/`.shannon/` hashes (S10) and both mutable CI action tags are gone. |
| gitleaks (`origin/dev` history) | 2 | 2, the same sealed-secret ciphertext false positives |

The CI workflow now pins `actions/checkout@11d5960…` and `actions/setup-node@49933ea…` (both
commented `v4.4.0`). This machine could not reach GitHub (connection reset), so **the SHAs were not
checked against the upstream tags**. Confirm once in the GitHub UI that each SHA is the `v4.4.0` tag
commit of the official `actions/*` repository.

## 7. What is still open

In priority order:

1. **S1 (High): rotation.** Confirm the UAT Admin password was changed, along with anywhere the old
   value or a variant was used. This is the only High item left, and it can only be closed by
   confirmation.
2. **S6 deployment smoke test.** After this build deploys, save one record on dev and on UAT to
   confirm the scheme check sees `https` (§3.1).
3. **S12 (Info).** Try the README demo credentials against dev, UAT and production (with approval).
4. **S5 (Low).** Product-owner decision on company-wide price comparison.
5. **S8, S9, S11 (Low).** CSP inline styles, DB certificate verification, Helm pod hardening.
6. N6 (no action needed now) and N7 (fix the doc paths). Also check the CI action SHAs (§6).

## 8. Not covered

The same limits as the previous reports:

- deployed environments, the Traefik ingress, real-hostname TLS and the cluster
- Traefik's handling of `X-Real-Ip` and, new in this run, `X-Forwarded-Proto` (see §3.1)
- the cost-plus module beyond its permission check
- malicious Excel files on the Basic Rate import
- denial of service beyond single large requests

## 9. How to reproduce

```powershell
# 1. Code under test in its own worktree
git fetch origin
git worktree add --detach ../vega-sectest4 f0322e1
cd ../vega-sectest4; npm ci; npx prisma generate

# 2. Fresh copy of the performance database, plus migrations
docker exec vega-perf-pg psql -U vega -d postgres -c "create database vega_sec4 template vega_prod"
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_sec4?sslmode=disable'
npx prisma migrate deploy; npm run build

# 3. App
$env:SESSION_SECRET='<any string of 32+ characters>'
npx next start -p 3201 -H 0.0.0.0

# 4. Tests (second terminal), from evidence-2026-11-09-after-fixes/, in this order
python -I authz_test.py <dir>
python -I retest.py <dir>
python -I fix_verify.py <dir>
python -I cheque_verify.py <dir>     # DB checks need docker access to vega-perf-pg
python -I fixes_verify.py <dir>      # uses cheque_verify.py's fixtures

# 5. ZAP and static scans: as in §9 of SECURITY_TEST_REPORT_2026-11-09.md
#    (Semgrep now also takes --exclude .next)
```

Raw output is in [`evidence-2026-11-09-after-fixes/`](evidence-2026-11-09-after-fixes/):

- `zap-report.html` / `.json`, `zap-plan.yaml` (cookie redacted), `zap_stdout.txt` (cookie redacted)
- `server-log-during-zap.txt`
- `authz_results.json`, `fix_verify_results.json`, `cheque_verify_results.json`,
  `fixes_verify_results.json` (and their `_stdout.txt`)
- `npm-audit.json`, `npm-audit-prod.json`, `semgrep.json`, `gitleaks.json` (redacted), `trivy.json`
- the five test scripts
