# Pre-Handover QA Audit — Page-by-Page Test & Report Prompt

Paste the whole of the section below into Claude Code (from the working directory
`d:\Bistec Intern Project\vega construction`). It is written to be **resumable** — run it
repeatedly and it picks up the next untested page each time.

---

## THE PROMPT

You are performing a **pre-handover QA audit** of the Vega Construction Manager app
(`vega-manager/`) before it is delivered to the client. Your job is to **test and report** —
page by page, exhaustively.

### Ground rules (read these first, they override any instinct you have)

1. **DO NOT FIX ANYTHING.** No source edits, no refactors, no "while I was here" cleanups.
   You are an auditor, not an implementer. The only files you may create or modify are the
   report files described below and the Playwright test files under `vega-manager/tests/`.
2. **NEVER touch the remote/production database.** Run every test against the **local** D1
   database only. Do not run `npm run db:migrate:remote`, `wrangler ... --remote`, or
   `npm run deploy`. If a test needs a clean slate, use `npm run db:reset-seed` (local).
   Confirm before any command that writes to a remote target.
3. **Report, don't speculate.** Every finding needs concrete evidence: the exact request or
   UI steps, the actual response/behaviour observed, and the file:line of the responsible
   code. If you suspect an issue but cannot reproduce it, file it as `Unconfirmed` and say
   exactly what you tried.
4. **One report file per page.** Never merge two pages into one report.

### Environment setup (do this once, before testing)

```bash
cd vega-manager
npm install
npm install -D @playwright/test          # only `playwright` is installed; the test runner is not
npx playwright install chromium
npx wrangler d1 migrations apply vega-manager-db --local
npm run db:seed
```

**Critical:** `next dev` does **not** resolve the D1 bindings, so API route handlers fail
under it. You must test against the Workers runtime:

```bash
npm run preview     # builds via OpenNext + serves through wrangler dev
```

Note the port it prints and point Playwright's `baseURL` at it. Create
`vega-manager/playwright.config.ts` if it does not exist. Do **not** wire `webServer` to
`next dev`.

### Test accounts (from `prisma/seed.ts`, password `vega123` for all)

| Email | Role | Use it to test |
|---|---|---|
| `nimal@vegahomes.lk` | Admin | full-access happy path |
| `sanduni@vegahomes.lk` | Admin | second admin (concurrency / audit attribution) |
| `kasun@vegahomes.lk` | Staff | permission denial, project-scope isolation |
| `dilini@vegahomes.lk` | Staff | second staff — **the key IDOR probe**: can Dilini reach a project only Kasun is a member of? |
| `ruwan@vegahomes.lk` | Staff, **Inactive** | must be refused login entirely |

### Pages to audit (19 total)

Work through them in this order. Each row is one report file.

| # | Page | Route | Report file |
|---|---|---|---|
| 1 | Login | `/login` | `01-login.md` |
| 2 | Dashboard | `/` | `02-dashboard.md` |
| 3 | Projects list | `/projects` | `03-projects-list.md` |
| 4 | Project detail (all tabs) | `/projects/[id]` | `04-project-detail.md` |
| 5 | Activities | `/activities` | `05-activities.md` |
| 6 | Basic Price (global) | `/basic-price` | `06-basic-price.md` |
| 7 | Basic Rate (global) | `/basic-rate` | `07-basic-rate.md` |
| 8 | Payments | `/payments` | `08-payments.md` |
| 9 | Suppliers list | `/suppliers` | `09-suppliers-list.md` |
| 10 | Supplier detail | `/suppliers/[id]` | `10-supplier-detail.md` |
| 11 | Supplier compare | `/suppliers/compare` | `11-supplier-compare.md` |
| 12 | Supplier compare — item | `/suppliers/compare/item` | `12-supplier-compare-item.md` |
| 13 | Sub-contractor detail | `/sub-contractors/[id]` | `13-sub-contractor-detail.md` |
| 14 | Users list | `/users` | `14-users-list.md` |
| 15 | User detail | `/users/[email]` | `15-user-detail.md` |
| 16 | Roles | `/roles` | `16-roles.md` |
| 17 | Settings | `/settings` | `17-settings.md` |
| 18 | Settings — Field Options | `/settings/field-options` | `18-settings-field-options.md` |
| 19 | Settings — Project Access | `/settings/project-access` | `19-settings-project-access.md` |

Page 4 (`/projects/[id]`) is by far the largest — it carries the BSR, Stages & Payments,
Expenses, Stage-costs, Basic Price and Basic Rate tabs. Give it proportionally more depth
and use `## Tab: <name>` sections inside its single report file.

### For each page, run all six test classes

#### A. Functional / Playwright
Write real Playwright specs in `vega-manager/tests/<page-slug>.spec.ts`. Cover:
- Page loads for an authorised user; no console errors; no unhandled promise rejections.
- Every interactive control: button, link, modal open/close, tab switch, dropdown, search
  box, sort, pagination, expand/collapse row, export button.
- Full CRUD where the page offers it — create, read, update, delete — and verify the change
  **persisted** (reload and re-assert; do not trust the optimistic UI).
- Form validation: empty required fields, wrong types, negative numbers, zero, absurdly
  large numbers, very long strings, leading/trailing whitespace, duplicate
  codes/names/emails, non-ASCII and Sinhala text.
- Cancel/abort paths: does closing a modal mid-edit leave stale state or a partial write?
- Deletes with dependents: deleting a project/supplier/activity that is referenced
  elsewhere — is it blocked, cascaded, or does it orphan rows? (`doc/ORPHANED_ROWS_FIX_PROMPT.md`
  is prior art here; verify it actually holds.)
- Excel/PDF export buttons: file actually downloads, is non-empty, and contains the values
  shown on screen.
- Money and date formatting: correct currency from the Settings page, no `NaN`, no
  `Invalid Date`, no floating-point artefacts like `1234.5600000001`. Cross-check totals —
  do the rows sum to the displayed total?
- Empty states (no data), single-row states, and large-data states.
- Dark mode and light mode both render legibly.
- Responsive: 1920px, 1366px, and 390px mobile width — check for horizontal overflow and
  unreachable controls.

#### B. Authentication & session
- Unauthenticated access to the page → redirected to `/login` (not a flash of content
  first, not a blank shell).
- Unauthenticated access to each of the page's API routes → `401`, not `200` with data.
- Inactive user (`ruwan@`) cannot log in.
- Logout genuinely invalidates the session — replay the old cookie afterwards and confirm
  it is rejected server-side, not merely cleared client-side.
- Session cookie flags: `HttpOnly`, `Secure`, `SameSite`.
- Tampered/forged/expired session cookie is rejected.
- **Do not test MFA — it does not exist and is not meant to.** The client declined
  multi-factor authentication (2026-09-04) and `0026_remove_mfa.sql` removed the partial
  implementation, so single-factor login is the intended design. Any finding of the form
  "no second factor at login" is out of scope, not a defect.
- Login throttling (`src/lib/loginThrottle.ts`): brute-force the login endpoint and confirm
  it actually locks out; check whether the lockout is per-account or per-IP and whether it
  can be bypassed by varying headers.

#### C. Authorisation / RBAC / IDOR — **highest priority**
- Log in as Staff (`kasun@`) and attempt every admin-only action the page exposes, both
  through the UI and by calling the API directly with `fetch`. A hidden button is **not**
  authorisation — the server must refuse.
- **IDOR sweep:** for every API route the page calls that takes an id in the path
  (`/api/projects/[id]/...`, `/api/suppliers/[id]`, `/api/users/[email]`,
  `.../stages/[stageId]`, `.../milestones/[milestoneId]`, `.../expenses/[expenseId]`,
  `.../payments/[paymentId]`, `.../items/[itemId]`, `.../recipe/[componentId]`,
  `/api/basic-rate/[itemId]`, `/api/basic-price/[draftId]`), substitute an id belonging to
  **another project or another user** and confirm it is refused. Test GET, PATCH/PUT, POST
  and DELETE — a route that guards reads but not writes is a real finding.
- Verify nested resources check the **parent** too: does
  `/api/projects/A/stages/<stage-belonging-to-project-B>` reject, or does it only check
  access to project A and then act on B's row?
- Project-scope isolation: `dilini@` must not see or mutate a project she is not a member
  or owner of — check list endpoints for leaked rows as well as detail endpoints.
- Privilege escalation: can a Staff user grant themselves a role or permission via
  `/api/roles`, `/api/users/[email]`, `/api/permissions/catalog`, or the project-members
  routes?
- Can a user delete or demote the last remaining admin, or change a project's owner to
  themselves?

#### D. SQL injection & input-handling
This app queries **Cloudflare D1 directly with raw SQL** (`src/lib/db.ts`) rather than
through Prisma Client at runtime, so this is a genuine risk area, not a formality. Do both:

- **White-box (do this first, it is far more reliable than blind fuzzing):** grep every
  API route this page calls for SQL that is built by string concatenation or template
  interpolation instead of a prepared statement with `.bind()`. Search for
  `` `SELECT ``/`` `INSERT ``/`` `UPDATE ``/`` `DELETE `` containing `${`, plus `.exec(`,
  and any `ORDER BY`/`LIMIT`/table-or-column name assembled from request input (a common
  hole even in otherwise-parameterised code, since `.bind()` cannot parameterise
  identifiers). Report the file:line of each.
- **Black-box:** send classic payloads through every text field, search box, sort/filter
  param, query string and JSON body the page touches:
  `' OR '1'='1`, `'; DROP TABLE users;--`, `1' UNION SELECT null,sqlite_version()--`,
  `admin'--`, `%27`, `\'`, and a `1 AND randomblob(100000000)` style timing probe. Watch
  for a raw SQL error message, an unexpected row count, an auth bypass, or a response-time
  spike. Note that D1 also permits `sqlite_master` enumeration — try it.
- Check `zod` validation coverage: which routes validate their body/params and which trust
  input directly? Try type-confusion — send an array or object where a string is expected,
  `null`, and a deeply nested payload.
- **XSS:** store `<script>alert(1)</script>`, `<img src=x onerror=alert(1)>` and
  `javascript:` URLs in every free-text field (supplier name, activity name, item
  description, notes, project name), then view every page that renders that field —
  including the Excel and PDF exports. Look for `dangerouslySetInnerHTML` in the codebase.
- **CSRF:** can a state-changing POST/PATCH/DELETE be triggered cross-origin with only the
  session cookie? Check whether `SameSite` is the only defence.
- Path traversal / oversized payloads on the catalog import route
  (`/api/projects/[id]/basic-rate/import`) and any file upload: wrong MIME type, 50 MB
  file, malformed XLSX/CSV, formula-injection cells (`=cmd|...`), zip bomb.
- Mass assignment: add unexpected fields (`role`, `id`, `isAdmin`, `ownerId`,
  `createdAt`) to a PATCH body and see whether they are written.

#### E. Security headers, transport & information disclosure
- Verify the headers set by `src/lib/securityHeaders.ts` actually arrive on this page's
  responses: `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Strict-Transport-Security`, and **`Content-Security-Policy`**
  (prior audit notes flag CSP as still outstanding — confirm the current state).
- Check `src/lib/edgeRateLimit.ts` is applied to this page's write endpoints; try to
  exceed it.
- Error responses must not leak stack traces, raw SQL, table/column names, file paths, or
  library versions. Force a 500 and inspect the body.
- No secrets, tokens, internal ids or `console.log` debug output in the client bundle or
  browser console. Confirm `SESSION_SECRET` and anything from `.dev.vars` never reaches the
  client.
- User enumeration: does a wrong-password response differ from an unknown-email response,
  in body **or** in timing?
- Check for exposed source maps in the production build.

#### F. Data integrity & business-rule correctness
Cross-check against the specs in `doc/` — `Vega_Construction_Enhancements.md`,
`GAP_ANALYSIS.md` (note the still-open Gap #11 on rate-change propagation), and the
relevant `*_PROMPT.md` for the feature — plus `README.md` in `vega-manager/`.
- Per-project catalog isolation: Basic Price / Basic Rate items must be scoped to one
  project. Confirm project A's catalog changes never affect project B, that promoting and
  cloning produce genuinely independent records, and that a `code` collision across
  projects is handled (codes are unique *within* a project only).
- Recipe/BSR maths: `ActivityItem` rates derived from `RecipeComponent`s, the
  `analysisQty` "basis isn't always 1 unit" quirk, `floorMultiplier`, and percentage
  allowance lines. Verify against a hand-computed figure.
- `PriceHistoryEntry` is written on **every** rate change, with the right actor and timestamp.
- Payments/expenses: partial and full allocation, over-allocation (paying more than the
  expense), negative payments, and the **paid-vs-committed** distinction — confirm ROI and
  the Expenses/Payments views use `expensePaid`, not `expenseCommitted`.
- Concurrency: two admins editing the same record simultaneously — last-write-wins silently,
  or is there a guard? Double-click a submit button and check for duplicate rows.

### Report format

Write reports to **`doc/claude-analyze-report/`** (create it). One `.md` per page, named per
the table above. Use exactly this structure:

```markdown
# QA Audit — <Page Name> (`<route>`)

- **Audited:** <YYYY-MM-DD>
- **Build/commit:** <git rev-parse --short HEAD, or "uncommitted working tree">
- **Verdict:** BLOCKER / NEEDS-FIX / PASS-WITH-NOTES / PASS
- **Playwright spec:** `vega-manager/tests/<slug>.spec.ts` — <N> tests, <N> passed, <N> failed

## Summary
<3–5 sentences: what this page does, what you tested, and the headline risk.>

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Functional / Playwright | ✅ / ⚠️ / ❌ | |
| B. Authentication & session | | |
| C. Authorisation / RBAC / IDOR | | |
| D. SQL injection & input handling | | |
| E. Headers / disclosure | | |
| F. Data integrity & business rules | | |

## Findings

### F-<page#>-01 — <short title>
- **Severity:** Critical / High / Medium / Low / Info
- **Confidence:** Confirmed / Unconfirmed
- **Class:** Functional | Auth | Authorisation | Injection | XSS | CSRF | Disclosure | Data integrity | UX
- **Location:** `path/to/file.ts:123`
- **Reproduction:**
  1. …
  2. …
- **Expected:** …
- **Actual:** …
- **Evidence:**
  ```
  <request / response / console output / screenshot path>
  ```
- **Impact:** <what a real user or attacker gets out of this>
- **Suggested fix:** <one or two lines — DESCRIBE ONLY, do not implement>

<repeat per finding, numbered sequentially>

## Tested and clean
<Bullet list of things you actively verified and found correct — this is as valuable to the
client as the findings. Be specific: "Staff user's direct PATCH to /api/roles/2 returned 403".>

## Not tested / blocked
<Anything you could not cover, and why. Be honest — an unexamined area silently reported as
clean is worse than an admitted gap.>
```

Severity guide: **Critical** = auth bypass, SQLi, cross-tenant data access, data loss.
**High** = privilege escalation, stored XSS, broken core business calculation.
**Medium** = missing validation, integrity gap with a workaround, missing security header.
**Low** = cosmetic, minor UX, inconsistent formatting. **Info** = observation only.

### Also maintain an index

`doc/claude-analyze-report/00-INDEX.md` — update it after **each** page so progress survives
a session restart:

- A table: page | report file | verdict | Critical / High / Medium / Low counts | date audited.
- A **Cross-cutting findings** section for issues that recur across pages (e.g. one missing
  authorisation helper affecting eight routes) — describe the pattern once here and reference
  it from the per-page files rather than repeating it.
- A **Handover readiness** section: the shortlist of things that must be fixed before the
  client sees this, ranked.

### Working method

Do **one page at a time**, start to finish: write its Playwright spec, run it, do the
security probing, write its report file, update the index — then move to the next page.
Do not batch all 19 pages' testing and leave the writing to the end; a session that ends
early must still leave completed reports behind.

Before starting a page, check `00-INDEX.md` — if that page already has a verdict, skip to
the next unaudited one. When all 19 are done, review the whole set for cross-cutting patterns
and finalise the Handover readiness list.

Tell me at the start of each page which page you are on, and at the end give me a one-line
verdict with the finding counts.
```

---

## Notes on using this

- **It is deliberately resumable.** 19 pages will not fit in one context window. Run the
  prompt, let it work, and re-paste it when the session ends — `00-INDEX.md` is what makes
  the next run pick up where the last one stopped.
- **Consider running it against a scratch copy** of the local D1 database. The audit
  deliberately creates junk rows (XSS payloads in supplier names, injected SQL strings,
  oversized imports) and does not clean up after itself. `npm run db:reset-seed` restores a
  clean local state afterwards.
- **The high-value classes are C and D.** The app runs raw SQL against D1 and has a
  two-layer permission model (role permissions + per-project membership), so authorisation
  gaps and identifier-level injection are where real findings will be. A prior audit
  (`2026-09-01`) already flagged a milestone IDOR and unguarded catalog writes — those are
  a good sanity check that the audit is finding what it should.
- If you would rather parallelise, the pages are independent: run the prompt in several
  sessions with the page table narrowed to a slice each (1–5, 6–11, 12–19), then merge the
  indexes by hand.
