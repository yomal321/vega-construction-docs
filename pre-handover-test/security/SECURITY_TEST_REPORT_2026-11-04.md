# Security Test Report (`dev` @ `0e15246`), 2026-11-04

This is a pre-handover security test of the Vega Construction Manager. It covers the OWASP Top 10
web risks with OWASP ZAP and with a scripted authorization test (the Burp "Autorize" method). It
also runs static scans on the code, dependencies, git history, Dockerfile and Helm chart.

Everything ran against a local throwaway copy of the app and database. No shared environment
(dev, UAT, production) was touched.

## 1. Summary

**No critical vulnerability was found in the app's own code.** The access-control model held
under every test:

- Unauthenticated requests get 401 on all 64 API route/method pairs tested.
- A Staff user cannot read or change another project's data. This held for 55 direct requests
  and 24 "own project in the URL, foreign record in the path" requests.
- A Staff user cannot use Admin-only or ungranted actions (32 requests).
- CSRF protection, session revocation, login throttling and login timing parity all work.
- ZAP's active scan found no exploitable injection. Its one "SQL Injection" alert is a false
  positive (§4, S3).

The open items are mostly hygiene and hardening. Two need action before handover:

| ID | Severity | Finding | Action |
|---|---|---|---|
| S1 | **High** | A UAT Admin password is committed in plain text in `prisma/seed-user.ts` and pushed to every remote branch, including `production` | Rotate it now; read it from an env var |
| S2 | **High** (patch) | Next.js 16.3.5 has 3 critical and 2 high advisories. None is reachable in this app today (checked) | Upgrade to `next@>=16.4.1`, and bump `zod`, `sharp`, `dompurify` |
| S3 | Medium | Unvalidated input reaches Postgres and returns HTTP 500 (bad dates, NUL bytes, FK violations, malformed JSON); 1,803 server errors during the scan | Validate in zod; map DB errors to 4xx |
| S4 | Medium | About 30 route schemas have no maximum string length; a 200,000-character supplier name was accepted | Add `.max()` everywhere |
| S5 | Low | Price comparison shows rates and names for all projects to anyone with `priceComparison:view`; its `/item` drill-down is scoped | Product-owner decision; make the two consistent |
| S6 | Low | The CSRF Origin check compares host only, not scheme | Compare the full origin |
| S7 | Low | `X-Powered-By: Next.js` header | `poweredByHeader: false` |
| S8 | Low | CSP allows `style-src 'unsafe-inline'` | Accept and document, or move to nonces |
| S9 | Low | DB TLS is used with `rejectUnauthorized: false` | Confirm the production DB path; verify the certificate |
| S10 | Low | Repo hygiene: a DB backup, a previous pentest's exploit evidence, and perf-test session tokens are in git | Remove from the repo; add to `.gitignore` |
| S11 | Low | Helm pod hardening gaps (writable root FS, empty default `resources`) | Set `readOnlyRootFilesystem`, default limits |
| S12 | Info | The demo password `VegaDemo-2026!` is published in the README | Confirm no deployed environment still uses it |

## 2. Scope and environment

| Item | Value |
|---|---|
| Code | `dev` @ `0e15246`, the same build as the after-fixes performance report |
| App | `next start -p 3200` (production build, Next.js 16.3.5), single process, fresh throwaway `SESSION_SECRET` |
| Database | `vega_sec`, a clone of `vega_prod` (`create database vega_sec template vega_prod`) in the `vega-perf-pg` container. Same rows as the performance test: 34 projects, 26 users, 6,011 expenses. The performance database itself was not modified. |
| Accounts | Admin `nimal@vegahomes.lk` (harness), Admin `sanduni@vegahomes.lk` (ZAP only), Staff `perf.staff1@vegahomes.lk` (role "Perf Project Manager", 7 of 34 projects), plus `perf.staff2`-`perf.staff6` and `perf.staff20` (inactive) for session/login tests |
| Not in scope | dev / UAT / production k3s environments, Traefik ingress, TLS on the real hostname, the cluster itself, the cost-plus module's data (no rows in the dataset) |

The k6 performance run had finished before this test started, so the two did not overlap.

## 3. Method and tools

| Layer | Tool | What it did |
|---|---|---|
| DAST | **OWASP ZAP 2.17.0** (`zaproxy/zap-stable`, Automation Framework) | Authenticated as Admin via a header replacer (session cookie + matching `Origin`). 21 pages and 63 API requests seeded with valid bodies, then spider, AJAX spider (Firefox headless), passive scan, full active scan. Plan: `evidence-2026-11-04/zap-plan.yaml`. |
| Authorization | Python harness `authz_test.py` + `retest.py` (stdlib only) | The Burp Autorize method: every route replayed with no cookie, with a Staff cookie against a foreign project, with an owned project in the URL but a foreign record ID in the path, and against Admin-only actions. Also CSRF, session, login, injection, headers. 274 checks. |
| SAST | Semgrep (`p/typescript`, `p/nextjs`, `p/javascript`, `p/owasp-top-ten`, `p/secrets`) | 10 results |
| Dependencies | `npm audit`, Trivy `fs` | 14 vulnerable packages |
| Secrets | gitleaks (139 commits, full history), Trivy secret scanner | 17 + 4 hits |
| IaC | Trivy misconfig (Dockerfile, Helm) | 8 hits |

Every tool hit was checked by hand before going into §4. Hits that turned out not to be issues
are listed in §6.

## 4. Findings

### S1: UAT Admin password committed in plain text (High)

`prisma/seed-user.ts:9` holds the plain-text password for an Admin account. The file's own
comment says it is for UAT: "safe to run against a database that already has real data (e.g.
uat)". It was added in `f261fb6` (2026-09-22) and is on `origin/main`, `origin/dev`,
`origin/production`, `origin/release_prod` and `origin/perf/production-fixes`. Anyone with read
access to the repo can log in to UAT as an Admin. The password value is not repeated in this
report.

The script also resets that account's password on every run (`update: { passwordHash: ... }`).
So rotating the password in the UI alone would be undone by the next seed run.

**Fix:**

1. Change the password on UAT now.
2. Change it anywhere else it, or a variant of it, is used.
3. Make the script read the password from an env var (`SEED_USER_PASSWORD`) and refuse to run
   without one.
4. Treat the old value as public. Rewriting git history is optional; rotating is not.

### S2: Next.js and other dependency advisories (High, patch)

`npm audit` reports 14 vulnerable packages (2 critical, 3 high, 9 moderate). Trivy agrees. The
ones that matter:

| Package | Installed | Advisory | Reachable here? |
|---|---|---|---|
| `next` | 16.3.5 | GHSA-2464-fhr4-w9xw, RCE in Image Optimization with SVG (critical) | **No.** `images.unoptimized: true`, so `/_next/image` returns 404 (tested) |
| `next` | 16.3.5 | GHSA-673q-mjm6-r5xr, RCE in `use cache` functions (critical) | **No.** No `use cache` in `src/` |
| `next` | 16.3.5 | GHSA-vcvr-r3jv-pc5j, RCE in `next/og` `ImageResponse` (critical) | **No.** `next/og` not imported |
| `next` | 16.3.5 | CVE-2026-94482, Server Actions DoS (high) | **No.** No `'use server'` in `src/` |
| `next` | 16.3.5 | CVE-2026-94483, SSRF in Image Optimization (high) | **No.** Same as the first row |
| `zod` | 4.6.5 | Memory exhaustion validating oversized constrained collections (high) | Partly. Bodies are capped at 10 MB by Next, but see S4 |
| `sharp` | 0.35.4 | librsvg CVE-2026-96889 (high) | No image processing at runtime |
| `dompurify` | 3.4.15 (via `jspdf`) | GHSA-cg2g-xh64-v4q7 and others | No. Only used by `jspdf`'s `.html()`, which the app does not call |
| `exceljs` chain | 4.4.0 | `archiver`/`glob`/`minimatch` moderate advisories | Build/runtime ZIP writing only, no user-controlled globs |

None is exploitable in the current code. All of them become exploitable as soon as someone uses
the affected feature, so upgrade now rather than tracking each one.

**Fix:** `next@>=16.4.1` (also fixes the medium and low Next CVEs up to 16.3.8), `zod@>=4.6.6`,
`sharp@>=0.35.5` (already in `overrides`; raise it), and `dompurify@>=3.4.17` through an
override. Run the Playwright suite afterwards. Leave the `exceljs` downgrade suggested by `npm
audit` (to 4.1.1) alone; it is older, not safer.

### S3: Unvalidated input returns HTTP 500 (Medium)

During the ZAP active scan the server logged 1,803 errors. Every one came from input that passed
zod validation and then failed in Postgres or in JavaScript:

| Server error (count) | Cause | Example route |
|---|---|---|
| FK violation `basic_price_items_activityCode_fkey` (791) | `activity` code not checked before insert | `POST /api/projects/[id]/basic-price` |
| `RangeError: Invalid time value` (382), `DateTimeParseError` (236), `invalid input syntax for type timestamp` | Date fields are `z.string()` with no format check | `PATCH .../stages/[stageId]` (`startDate`, `completionDate`), `.../milestones/[milestoneId]` (`dueDate`), `POST /api/projects` (`start`), expense `date` |
| `SyntaxError ... is not valid JSON` (121) | `parseBody` calls `request.json()` without catching `SyntaxError`; `apiRoute` maps it to 500 | every POST/PATCH route |
| FK violation on `DELETE activities` (30) | Deleting an activity that a Basic Price draft still uses | `DELETE /api/activities/[code]` |
| `invalid byte sequence for encoding "UTF8": 0x00` (40) | NUL byte in a string field | various |
| `invalid input value for enum "PaymentMethod"` | Payment method not an enum in zod | expense payments |

The response body is always the generic `{"error":"Internal server error"}`, so nothing leaks.
The impact is:

- Real errors are buried in log noise.
- Every malformed request writes a stack trace to the pod log, a cheap way to flood it.
- The UI shows a generic failure where it should name the bad field.
- ZAP reads the 500 on `startDate='` as a possible SQL injection.

**This is not SQL injection.** All of these values are bound parameters. They were tested by hand
on `PATCH /api/projects/perf_p004/stages/perf_p004_s1`:

| `startDate` | Status | Time |
|---|---|---|
| `'` | 500 | 9 ms |
| `2026-01-05' or '1'='1` | 400 | 21 ms |
| `2026-01-05'; select pg_sleep(5)--` | 400 | 7 ms (no delay) |

The stored value was unchanged afterwards. Log lines like `time zone "start-sleep" not
recognized` show the payload being parsed as a timestamp literal, not executed.

**Fix:**

- Catch `SyntaxError` in `parseBody` and return 400 "Invalid request body".
- Use the existing `dateString()` helper (`src/lib/incomePayments.ts:22`) for every date field.
- Make payment method a `z.enum`.
- Reject `\u0000` in a shared string schema.
- In `apiRoute`, map Postgres `23503` (FK) to 409 and `22P02`/`22007`/`22008` to 400.
- Check that the activity exists before inserting a Basic Price draft, and return a clear 409
  when deleting an activity that is in use.

### S4: No maximum length on most text fields (Medium)

`POST /api/suppliers` accepted a 200,000-character `name` (HTTP 200, stored). About 30 route
files define `z.string()` fields with no `.max()`, including:

- suppliers and sub-contractors
- activities, categories, trades and units
- Basic Price and Basic Rate (global and per-project)
- items and recipes
- roles
- company profile
- login (`email`, `password`)

`/api/projects` already does this correctly with `MAX_TEXT_LENGTH = 120`.

Impact: storage abuse by any user with create rights, and broken PDF/Excel exports (the same
overflow the projects route's comment describes). Combined with the `zod` advisory in S2, large
arrays also cost memory to validate.

**Fix:** a shared `text(max)` schema helper in `src/lib/api.ts`, applied to every string field.
Also cap array lengths (`recipe`, `codes`, `permissions`, import rows).

### S5: Price comparison shows every project to any holder of `priceComparison:view` (Low, design decision)

`GET /api/suppliers/price-comparison` returned, to a Staff user with access to 7 projects, rates
and project names for all 34 projects (1,031 item groups, 282 KB). The route's comment says this
is deliberate: "Company-wide ... project-level ownership/membership plays no part in this
rollup."

The drill-down `GET /api/suppliers/price-comparison/item` *is* scoped by `projectAccessClause`.
So the same user sees a project's rate in the list but cannot open its history.

**Fix:** have the product owner confirm the company-wide intent in writing. If confirmed, document
it in the Roles editor next to the permission. Otherwise, scope the list with
`projectAccessClause` like the drill-down.

### S6: CSRF Origin check ignores the scheme (Low)

`src/proxy.ts` `isSameOriginRequest` compares `new URL(origin).host` with the `Host` header. A
request with `Origin: https://localhost:3200` to `http://localhost:3200` was accepted (HTTP 200,
supplier created). Exploiting this needs an attacker who can serve pages on the same host and
port under the other scheme, which is effectively a network attacker on plain HTTP. All other
variants were rejected with 403: missing Origin, `evil.example`, `null`, and the
`localhost:3200.evil.example` prefix trick.

**Fix:** compare the full origin (`scheme://host`) and take the scheme from `x-forwarded-proto`
as set by Traefik. Production should only ever see `https`.

### S7: `X-Powered-By: Next.js` (Low)

HTML responses carry `X-Powered-By: Next.js` (ZAP 10037; API responses do not).
**Fix:** `poweredByHeader: false` in `next.config.ts`.

### S8: CSP allows inline styles (Low)

The CSP is otherwise strong:

- `default-src 'self'`
- nonce-based `script-src` with no `unsafe-inline` or `unsafe-eval`
- HSTS `max-age=63072000; includeSubDomains; preload`

`style-src 'self' 'unsafe-inline'` remains (ZAP 10055). This is common with React inline styles
and `framer-motion`. It only matters if an HTML injection is found, and none was.

**Fix:** accept and record the decision, or move styles to nonces/hashes.

### S9: DB TLS without certificate verification (Low)

`src/lib/pg.ts:318` uses `ssl: { rejectUnauthorized: false }` whenever TLS is on. The comment
says this is for Supabase in local development. If the deployed app reaches its database over a
network it does not fully control, an attacker on that path could intercept DB traffic.

**Fix:** confirm how the deployed pods reach Postgres. If TLS is used outside a trusted
in-cluster network, pass the CA (`ssl: { ca }`) and verify it.

### S10: Sensitive files in the repo (Low)

| Path | Contents | Where |
|---|---|---|
| `.backups/remote-backup-2026-08-18.sql` | Full D1-era DB dump, including 5 users' bcrypt hashes. **All 5 hashes were checked and are the published demo password**; no session rows. | Tracked; on all remote branches (`2280932`) |
| `.shannon/deliverables/*` | A previous automated pentest's working files, including `*_exploitation_evidence.md` and exploitation queues | Tracked (`cb7695c`) |
| `perf/results/**/*.json` | k6 summaries containing session JWTs (gitleaks: 14, Trivy: 4) | In a local git stash (`894bfea`) and untracked on disk; not pushed. Tokens were issued by local throwaway instances. |

Nothing here is a live credential today. Each file gives a future reader a map (exploit notes)
or a habit (dumps in git) that will eventually leak something real.

**Fix:**

- `git rm` the first two.
- Move the pentest deliverables to the docs repo if they are still wanted.
- Add `.backups/`, `.shannon/` and `perf/results/` to `.gitignore`.
- Strip cookies from k6 summaries before saving them.

### S11: Helm pod hardening (Low)

Trivy on `deploy/helm/charts/vega-web` reports these gaps:

- `readOnlyRootFilesystem` not set (KSV-0014)
- UID/GID at or below 10000 (KSV-0020/21)
- no `HEALTHCHECK` in the Dockerfile (DS-0026; the k8s probes cover this)
- `values.yaml` defaults to `resources: {}`. The template's comment says limits are required
  (H001), so check that every `values-<env>.yaml` sets them.

`runAsNonRoot: true` is already set.

**Fix:** `readOnlyRootFilesystem: true` with an `emptyDir` for `/tmp` and `.next/cache`, a
non-default UID above 10000, and default requests/limits in `values.yaml`.

### S12: Demo password is public (Info)

`README.md` publishes `VegaDemo-2026!` for every seeded user, and `prisma/seed.ts` uses it. This
is fine for local development. It is a full compromise if any deployed environment was seeded
with `npm run db:seed` and those accounts are still active. This test did not touch deployed
environments, so it was **not checked**.

**Fix:** before handover, try the README credentials against dev, UAT and production (with
written approval). Deactivate or rotate any account that still accepts them.

### Also noted (Info)

- `.github/workflows/ci.yml` pins GitHub Actions by mutable tag (Semgrep). Pin by commit SHA.
- Stored HTML and SQL strings (`<img src=x onerror=alert(1)>`, `x'); drop table users;--`) are
  accepted and stored verbatim, which is correct for a JSON API. No execution sink was found:
  - React escapes output.
  - The only `dangerouslySetInnerHTML` is the nonce'd theme script.
  - PDF export uses `jspdf` text, not `.html()`.
  - ExcelJS writes strings as text, not formulas.

  ZAP's "XSS Weakness (Persistent in JSON Response)" alerts on `/api/projects` and
  `/api/trades` are this same case.
- Login responds in ~2.1 s for both valid and unknown emails (median 2,104 ms vs 2,105 ms), which
  is correct for timing parity. Add a comment explaining the deliberate delay if there isn't one.

## 5. Controls that passed

| Area | Checks | Result |
|---|---|---|
| Unauthenticated access | 64 API route/method pairs → 401; 5 pages → redirect to `/login`; forged tokens (garbage, `alg: none`, tampered signature) → 401 | All pass |
| Horizontal access (IDOR) | 55 requests as Staff against project `p1` and its stages, milestones, payments, expenses, BSR lines, items, recipe components, drafts, Basic Rate items, variations; global-path routes resolved by record ID | All 401/403/404 |
| Cross-parent IDOR | 24 requests with an *owned* project in the URL and a *foreign* record ID in the path (e.g. own milestone + foreign payment ID) | All 403/404. Every nested route checks the record belongs to the URL's project. |
| List endpoints | `/api/projects`, `/api/dashboard`, `/api/payments`, `/api/basic-rate`, `/api/basic-price`, `/api/notifications`, `/api/expenses/other-payees`, `/api/payments/other-payees/history` return no foreign project IDs to Staff | Pass (price comparison: see S5) |
| Vertical access | 32 Staff requests to Admin-only or ungranted actions: users, roles, permissions catalog, company profile, categories/trades/units admin, project owner/members, project delete, activity edit/delete, supplier create/delete, cost-plus, another user's filter preset | All 403/404 |
| Mass assignment | Staff `PATCH` of own project with `ownerId`/`id` smuggled in | Ignored; owner unchanged |
| Data exposure | `/api/auth/me` and `/api/users` return no password hashes | Pass |
| CSRF | Missing, foreign, `null` and prefix-trick `Origin` → 403; login CSRF → 403; no CORS headers on cross-origin GET | Pass (scheme: see S6) |
| Session | Cookie `HttpOnly; Secure; SameSite=lax; Path=/`; logout revokes server-side; deactivating a user kills their live session immediately; inactive user cannot log in; login replaces a pre-set cookie (no fixation) | All pass |
| Login | Same message for real and unknown emails; timing parity; throttled to 429 from the 6th wrong attempt, and the correct password is also refused while throttled; SQL/NoSQL injection payloads rejected | All pass |
| Injection (query strings) | 45 SQLi payloads across 9 filter parameters (incl. `pg_sleep`) | No 5xx, no delay, no DB error text |
| Other input | Path traversal in IDs → 404; negative contract and payment → 400; overpayment → 400 | Pass |
| Headers | CSP (nonce scripts), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS on HTML and API | Present |

The security fixes recorded in `test/security/FIXES_APPLIED_2026-09-19.md` (CSRF Origin check,
owner-route guard, rate limiter fail-closed, no `X-Forwarded-For` trust) were all observed
working.

## 6. Tool hits that turned out not to be issues

| Tool hit | Why it isn't one |
|---|---|
| ZAP 40018 "SQL Injection" (High, low confidence) on `startDate` | Bound parameter; manual time-based and boolean tests negative (S3) |
| ZAP 90022 / 10023 "Application Error Disclosure" | Body is the generic `Internal server error`; real cause is S3 |
| ZAP 10106 "HTTP Only Site" | Local test over plain HTTP by design; the ingress serves HTTPS and HSTS is set |
| ZAP 10096 "Timestamp Disclosure" | Numbers in BSR/dashboard data (amounts), not timestamps |
| Semgrep `detected-bcrypt-hash` in `src/lib/auth.ts:66` | `DUMMY_PASSWORD_HASH`, a deliberate dummy for timing parity |
| gitleaks `generic-api-key` in `deploy/helm/sealed-secrets/*` | `kind: SealedSecret`; values are ciphertext only the cluster can decrypt |
| Harness "IDOR" on `PATCH /api/projects/perf_p004/basic-rate/L-003` (200) | Basic Rate codes are per-project; `perf_p004` has its own `L-003`. `p1`'s `L-003` was unchanged (rate 3500). |
| Harness "cookie flags" | Bug in the check's case handling; flags are correct |

## 7. Not covered

- Deployed environments (dev, UAT, production), the Traefik ingress, real-hostname TLS and the
  k3s cluster (kube-bench / kubescape).
- Whether Traefik really overwrites `X-Real-Ip`, which the IP-based login throttle relies on.
  Locally there is no Traefik, so only the per-email throttle was exercised.
- The cost-plus module beyond its permission check (no data in the dataset).
- File upload and import (`/api/projects/[id]/basic-rate/import`) with malicious Excel files.
- Denial of service beyond single large requests.

## 8. How to reproduce

```powershell
# 1. Throwaway copy of the performance database (the perf data is left untouched)
docker exec vega-perf-pg psql -U vega -d postgres -c "create database vega_sec template vega_prod"

# 2. App (dev @ 0e15246, already built)
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_sec?sslmode=disable'
$env:SESSION_SECRET='<any string of 32+ characters>'
npx next start -p 3200 -H 0.0.0.0

# 3. Authorization harness (second terminal)
python -I evidence-2026-11-04/authz_test.py <output dir>
python -I evidence-2026-11-04/retest.py <dir containing authz_test.py>

# 4. ZAP: log in as sanduni@vegahomes.lk, put the vega_session value into zap-plan.yaml, then
docker run --rm -v "<dir>:/zap/wrk:rw" -u zap zaproxy/zap-stable zap.sh -cmd -autorun /zap/wrk/zap-plan.yaml

# 5. Static
npm audit --json
docker run --rm -v "<repo>:/src:ro" semgrep/semgrep semgrep scan --config p/typescript --config p/nextjs --config p/javascript --config p/owasp-top-ten --config p/secrets /src
docker run --rm -v "<repo>:/repo:ro" zricethezav/gitleaks:latest git /repo --redact
docker run --rm -v "<repo>:/src:ro" aquasec/trivy:latest fs --scanners vuln,misconfig,secret --skip-dirs node_modules /src
```

Raw output is in [`evidence-2026-11-04/`](evidence-2026-11-04/):

- `zap-report.html` / `.json`
- `authz_results.json`
- `npm-audit.json`, `semgrep.json`
- `gitleaks.json`, `trivy.json` (secret values redacted)

The ZAP plan's session cookie is redacted.
