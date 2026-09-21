# Pre-Handover End-to-End Functional Test — Role Journey Prompt

Third and final prompt in the pre-handover set:

| Prompt | Lens | Unit of work | Status |
|---|---|---|---|
| `doc/Front end/PRE_HANDOVER_QA_PROMPT.md` | UI correctness, **page by page** | one page | 4 / 19 done, stale env |
| `doc/PRE_HANDOVER_BACKEND_SECURITY_PROMPT.md` | Server authorisation, **route by route** | one route family | 1 / 12 done, stale env |
| **this file** | **Does the whole product work for a real user, end to end, without crashing** | one **user journey** | new |

The other two ask "is this page right?" and "is this route safe?". This one asks the question the
client will actually ask on day one: *I made an account, I logged in, I tried to do my job — did
anything break?* It is the **handover sign-off** document. It is deliberately journey-shaped, not
page-shaped: bugs that only appear when a real person creates a user, assigns them a role, logs in
as them, and works through a whole task in sequence are invisible to a page-by-page sweep.

Paste everything below `## THE PROMPT` into Claude Code, working directory
`d:\Bistec Intern Project\Vega`.

---

## THE PROMPT

You are running the **final pre-handover end-to-end functional test** of the Vega Construction
Manager app (`VegaConstruction-ManagementSystem/`) before it is delivered to the client. This is
the last functional check before sign-off — after this, the product is handed over. Test it like
the person receiving it will use it.

Your job is to **drive the real application through complete user journeys**, one role at a time,
and report what works, what breaks, and what crashes. You are an auditor producing a handover
document, not an implementer.

### Ground rules — read these first, they override any instinct you have

1. **DO NOT FIX ANYTHING.** No source edits, no refactors, no "while I was here" cleanups. Finding
   and *describing* a bug is the deliverable. The only files you may create or modify are the
   report files described below and test specs under `VegaConstruction-ManagementSystem/tests/`.
   If you catch yourself opening a source file with intent to edit, stop.
2. **Read §"Database safety" before you create a single row.** `DATABASE_URL` in this repo points
   at a **shared remote Supabase Postgres**, not a local database. This is the single biggest way
   this exercise can go wrong.
3. **Drive the real UI, not just the API.** This prompt's whole value is the journey. Use
   Playwright (or the browser) to click through the app as the user would. Where a UI path is
   blocked or slow, an API call is an acceptable *fixture shortcut* — say so in the report — but
   the behaviour under test must be exercised through the interface.
4. **Report, don't speculate.** Every finding needs: the exact steps to reproduce, what you
   expected, what actually happened (with the real status code / error text / screenshot path),
   and the `file:line` of the responsible code. If you suspect a bug but cannot reproduce it, file
   it as `Unconfirmed` and state exactly what you tried.
5. **A journey is not "done" until it is written up.** Finish one journey completely — run it,
   write its section, update the run log — before starting the next. A session that dies early
   must still leave finished work behind.
6. **Do not re-report known-open findings as new.** See §"Known open — confirm, don't
   re-litigate". Confirming one still holds is valuable; filing it as fresh is noise.
7. **Negative results are findings too.** "Staff with no `payments:view` still sees the Payments
   nav item but gets a denial panel" is worth a line. So is "export produced a 0-byte file".

### Database safety — decide this before doing anything else

`VegaConstruction-ManagementSystem/.env` has:

```
DATABASE_URL=postgresql://postgres.ovobnhguozluizzhramy...@aws-0-ap-northeast-1.pooler.supabase.com...
```

That is a **remote, shared Postgres**. The D1/wrangler local database the two older prompts
assumed **no longer exists** — it was removed in the 2026-09-18 Cloudflare cutover. So there is no
"just run it locally" default any more, and this test creates users, roles, projects, expenses and
payments by design.

**Pick one of these, state your choice at the top of the report, and do not deviate:**

- **Option A (preferred) — local Postgres.** Stand up Postgres locally (Docker:
  `docker run -d -e POSTGRES_PASSWORD=vega -p 5432:5432 postgres:16`), point a `.env.local`
  `DATABASE_URL` at it, run `npm run db:migrate` then `npm run db:seed`. Full freedom to create,
  break and delete. Verify with `npm run verify:pg` before starting.
- **Option B — the shared Supabase DB, under strict discipline.** Only if Option A cannot be made
  to work. Then **every** row you create must be prefixed `QA2 ` (name fields) or
  `qa2-` (emails, codes, slugs) so it is trivially identifiable and deletable, you must keep a
  **cleanup ledger** (below), and you must **never** delete, deactivate or edit a row you did not
  create. Do not run `npm run db:reset-seed` under Option B — it will destroy the client's data.

Under **either** option, these are hard stops — confirm with the user before running any of them:
`npm run deploy`, anything writing to a production target, `db:reset-seed` against a non-local DB,
any `delete from` without a `QA2`/`qa2-` predicate.

**Cleanup ledger.** Maintain `doc/e2e-journey-report/CLEANUP.md` from the first row you create.
One line per created entity: `<type> | <identifier> | <created by journey> | <deleted? y/n>`.
Delete in reverse dependency order at the end (payments → expenses → milestones → stages → BSR
lines → basic-rate items → basic-price drafts → project members → projects → user-role
assignments → users → roles → suppliers/sub-contractors → activities → categories/units/trades).
Then re-check every table for orphans — `doc/Front end/ORPHANED_ROWS_FIX_PROMPT.md` claims cascades
are handled; this is your chance to prove it.

### Environment setup

```bash
cd VegaConstruction-ManagementSystem
npm install
npx playwright install chromium     # @playwright/test 1.61.1 is already a devDependency
# set up DATABASE_URL per your Option A / B choice above
npm run dev                          # Next 16 dev server, usually http://localhost:3000
```

Traps that will cost you an hour each if you don't read them now:

- **`next dev` works fine.** The old prompts say it doesn't — that was the D1-binding era and is no
  longer true. Postgres is reached directly via `DATABASE_URL`. Ignore every `npm run preview`,
  `wrangler`, and "Workers runtime" instruction in the older prompts.
- **Playwright's `baseURL` defaults to `http://localhost:8787`**, which is the dead wrangler port.
  Run as `PW_BASE_URL=http://localhost:3000 npx playwright test ...` or nothing will connect.
- **The existing spec suite is in a half-ported state.** `playwright.config.ts` carries a
  KNOWN BROKEN banner from 2026-09-18 saying `tests/helpers.ts` shells out to wrangler — but
  `helpers.ts` has since been ported to `scripts/test-db-exec.mts` over `DATABASE_URL`. **Verify
  which is true before trusting either**: run one existing spec and see. Whatever you find,
  record it — "the handover test suite does/doesn't run" is itself a handover-critical fact.
- **`src/middleware.ts` does not exist.** Next 16 renamed it: the global auth/CSP gate is
  **`src/proxy.ts`**. Older docs referencing `middleware.ts` are stale.
- **Mutating requests are Origin-checked** (CSRF defence added 2026-09-19, `src/proxy.ts`). Browser
  traffic is fine; a bare Playwright `request.post(...)` needs the `Origin` header the config
  already sets. A sudden 403 on a raw fixture call is this, not a bug.
- **Login throttle: 5 failed attempts per email, 15-minute lock** (`src/lib/loginThrottle.ts`).
  Any deliberate bad-login test must clear it afterwards (`clearLoginThrottle()` in
  `tests/helpers.ts`) or you will lock yourself out of an account mid-journey and misread it.
- **Passwords are content-validated**, not just length-checked (`src/lib/password.ts` →
  `validatePassword`): common-password list plus an identity check against the user's own name and
  email. `qa2estimator@…` with password `qa2estimator1` will be **rejected** — that is correct
  behaviour, not a bug. Pick unrelated strong passwords and record them in the report.
- **Ordering trap that will block Journey A if you get it wrong:** `assertAssignableUser`
  (`src/lib/rbac.ts`) refuses to make a Staff user a project **owner or member** while they have
  zero effective permissions. You must **create the role and assign it first**, then assign the
  project. Otherwise you get a 400 that looks like a bug and isn't.

### The permission model you are testing — understand this before writing journeys

Two **independent** layers. Almost every interesting bug in this app lives in the gap between them.

1. **Legacy account role** — `User.role` is `'Admin' | 'Staff'`. **Admin bypasses RBAC entirely**
   (`hasPermission` short-circuits, no DB read). So an Admin journey tests *features*; only a Staff
   journey tests *permissions*.
2. **RBAC module permissions** — `requirePermission(module, action)` against `PERMISSION_CATALOG`
   (`src/lib/rbac.ts`). Effective permissions = union of (every assigned Role's permissions) and
   (direct per-user grants in `user_permissions`).

   | Module | Actions |
   |---|---|
   | `dashboard` | `view` |
   | `projects` | `view`, `create`, `edit`, `delete`, `promote` |
   | `activities` | `view`, `create`, `edit`, `delete` |
   | `suppliers` | `view`, `create`, `edit`, `delete` |
   | `payments` | `view` |
   | `priceComparison` | `view` |

   Note: Basic Price and Basic Rate are **not** their own modules — they fold into `projects`, and
   `promote` is the Basic Price draft → Basic Rate action.

3. **Project reach** — orthogonal to both. `requireProjectAccess` passes for Admin, the project
   **owner**, or an assigned **member**. Membership grants *visibility only* and **never** implies
   any module permission. A user can be a member of a project and still be unable to do anything
   in it — verify that this is what actually happens.

So a complete journey must separate three distinct questions, and your report must too:
**(a)** can they *reach* the page, **(b)** can they *see* the data, **(c)** can they *act* on it.

### Existing accounts

| Email | Password | Role | Notes |
|---|---|---|---|
| `yomaltheekshana66@gmail.com` | `yomal8899` | Admin | real account, **use for setup only, do not damage** |
| `csp-test-staff@vegahomes.lk` | `yomal8899` | Staff, zero roles/permissions | disposable, built for denial testing |

The demo accounts named in the two older prompts (`nimal@`, `sanduni@`, `kasun@`, `dilini@`,
`ruwan@vegahomes.lk`) **were deleted on 2026-09-11**. Ignore every reference to them.

---

## The journeys

Run these **in order** — each depends on fixtures the previous one created.

### J0 — Environment & smoke baseline

Before any journey: confirm the app is actually alive and record the baseline.

- `GET /api/healthz` and `/api/ready` respond.
- Log in as the existing Admin. Every one of the 20 pages loads without an error overlay:
  `/login`, `/`, `/projects`, `/projects/[id]`, `/activities`, `/basic-price`, `/basic-rate`,
  `/payments`, `/suppliers`, `/suppliers/[id]`, `/suppliers/compare`, `/suppliers/compare/item`,
  `/sub-contractors/[id]`, `/users`, `/users/[email]`, `/roles`, `/settings`,
  `/settings/company-profile`, `/settings/field-options`, `/settings/project-access`.
- Record: git commit (`git rev-parse --short HEAD`), Node version, browser, DB option A/B, date.
- Capture the browser console from this point on for **every** journey (see §Crash catalogue).

### J1 — Admin journey: build the world

As the existing Admin, create the fixture set the later journeys need, **through the UI**, and test
each creation as you go. This is both setup *and* the Admin functional pass.

1. **Company profile** (`/settings/company-profile`) — set it; confirm it flows into PDF/Excel export headers later.
2. **Field options** (`/settings/field-options`) — add a category, a unit, a trade. Rename one and
   confirm the rename cascades (this uses `db.batch` — check for half-applied state).
3. **Activities** (`/activities`) — create `QA2 Activity`, edit it, add activity items.
4. **Suppliers & sub-contractors** (`/suppliers`) — create one of each, open both detail pages.
5. **Project** (`/projects`) — create `QA2 Project Alpha`. Then in `/projects/[id]` work **every
   tab**: `bsr`, `stages`, `expenses`, `stage-costs`, `basic-price`, `basic-rate`.
   - BSR: add a line, add a recipe with components, set `analysisQty` ≠ 1 and a `floorMultiplier`,
     add a percentage allowance line. **Hand-compute the derived rate and diff it against the UI** —
     the page-by-page audit recorded this arithmetic as never exercised.
   - Stages: create stages and milestones, set values, dates and statuses.
   - Expenses: create an expense with line items, then record a payment against it.
   - Basic Price: create a draft → **promote** it → confirm it appears as a Basic Rate item, and
     that price history was written with the right actor and timestamp.
   - Basic Rate: edit a rate, check `/api/.../history`, use clone and import.
6. **Second project** `QA2 Project Beta` — you need two projects to test scope isolation.
7. **Exports** — every PDF and Excel button on dashboard, project, payments and supplier pages.
   File downloads, is non-empty, and the numbers inside match the screen.
8. **Dashboard** (`/`) — cross-check every figure against the underlying data by hand: income
   received/outstanding, ROI, committed vs paid expense. ROI must use `expensePaid`.

### J2 — Create the test users and roles

Still as Admin, **through the UI** (`/roles` then `/users`):

| # | Role name | Permissions | User | Account role |
|---|---|---|---|---|
| R1 | `QA2 Estimator` | `dashboard:view`, `projects:view/create/edit`, `activities:view/create/edit`, `suppliers:view` | `qa2-estimator@vegahomes.lk` | Staff |
| R2 | `QA2 Finance` | `dashboard:view`, `payments:view`, `priceComparison:view` | `qa2-finance@vegahomes.lk` | Staff |
| — | *(none)* | none at all | `csp-test-staff@vegahomes.lk` *(exists)* | Staff |
| — | n/a | n/a (bypasses RBAC) | `qa2-admin2@vegahomes.lk` | Admin |

The two roles are chosen to be **deliberately non-overlapping on the interesting axes**: R1 can
create and edit projects but can never `delete` or `promote`, and cannot see payments or price
comparison at all; R2 can see money but cannot touch a project. Every "is this button correctly
hidden / correctly refused?" question falls out of that asymmetry.

While creating users, test the creation form itself: duplicate email, invalid email, empty name,
weak/common password, a password containing the user's own name or email, assigning a role vs
assigning direct permissions vs neither.

Then, as Admin, at `/settings/project-access`: make `qa2-estimator` the **owner** of
`QA2 Project Alpha`, and a **member** (not owner) of nothing. Leave `QA2 Project Beta` entirely
outside their reach — Beta is your isolation probe. Confirm the ordering trap: try assigning
`csp-test-staff` (zero permissions) and verify you get the documented 400, not a crash.

### J3 — Estimator journey (`qa2-estimator`)

Log out fully. Log in as the Estimator. Now work an entire realistic day, and at every step record
all three of: *reached?* / *saw?* / *could act?*

- **Navigation shape** — which sidebar items render? Items for modules they lack (`payments`,
  `priceComparison`) should not be reachable. If the item renders but the page shows a denial
  panel, that is a UX finding, not a security one — file it as such and say which.
- **Allowed happy path** — create a new project, edit it, add BSR lines, stages, expenses,
  activities. All should succeed and **persist across a hard reload** (do not trust optimistic UI).
- **Correctly denied** — every one of these must be refused cleanly (a clear message, never a
  crash, never a silent no-op, never a stack trace):
  - Delete a project (lacks `projects:delete`)
  - Promote a Basic Price draft (lacks `projects:promote`)
  - Open `/payments`, `/suppliers/compare`, `/users`, `/roles`, `/settings` by **typing the URL
    directly** — the nav being hidden is not a defence
  - Open `QA2 Project Beta` by direct URL (no reach) → must 403/404, not render a shell then fail
  - Edit a supplier (has `suppliers:view` only)
- **Scope isolation** — does any list page (projects, payments, dashboard, price comparison)
  leak a row from `QA2 Project Beta`? Check the dashboard totals especially: do they include
  projects the Estimator cannot see? This is the `projectAccessClause` footgun
  (`src/lib/rbac.ts` — `idColumn` must be table-qualified, or the membership branch silently
  evaluates false). Grep every call site and confirm at runtime.
- **Exports as a limited user** — do the PDF/Excel exports respect the same scope, or do they
  quietly include everything?

### J4 — Finance journey (`qa2-finance`)

Log out fully. Log in as Finance. Same three-part recording.

- Dashboard, Payments and Price Comparison should work end to end. Cross-check every money figure
  against what the Admin saw in J1 — **do the two views of the same data agree?** A disagreement
  here is a serious finding.
- Everything project-shaped must be refused: `/projects`, `/projects/[id]` by direct URL,
  `/basic-price`, `/basic-rate`, `/activities`, `/suppliers`.
- Confirm `payments:view` really is view-only: attempt to record a payment from the Payments page
  and from a project expense. (Note the documented design: recording a payment is gated by
  `projects`, not `payments` — so this must be refused. Verify the refusal is clean.)

### J5 — Zero-permission baseline (`csp-test-staff`)

The most productive single probe in this codebase. Log in as a Staff user with no roles and no
direct grants.

- They authenticate successfully — confirm that.
- Then **every** page and **every** action must be denied. Walk all 20 routes by direct URL.
- Nothing should render a blank white page, an infinite spinner, a raw error, or a shell that
  loads then explodes. A denial must be a *designed* state.
- This is also the "what does a brand-new employee see on their first login before an admin
  configures them?" question — note whether that first-run experience is acceptable to hand over.

### J6 — Lifecycle, concurrency and interruption

This is where "works without interrupt or crash" is actually tested. Nothing here is covered by a
page-by-page sweep.

- **Permission revoked mid-session.** Log in as Estimator in browser 1. As Admin in browser 2,
  strip a permission from `QA2 Estimator`. Back in browser 1, without reloading, click the
  now-forbidden control. Expected: a clean refusal on the very next request (roles are re-read
  per request, not trusted from the JWT). Actual: record it. Does the UI recover, or wedge?
- **Deactivated mid-session.** Same setup; set the Estimator to Inactive. Next request must 401
  and land them on `/login`. Confirm they cannot log back in.
- **Role changed / password changed / user deleted / logged out** — all five are documented
  session-revocation paths. Verify each one actually invalidates the live session.
- **Two users, one record.** Estimator and Admin both open the same project expense; both save
  different values. Lost update, last-write-wins, or an error? Whatever happens, is it *explicable*
  to the client?
- **Double submit.** Click Save / Create / Promote twice rapidly (and specifically the Basic Price
  **promote** button — the security docs record a double-promotion vulnerability class). Duplicate
  rows? Two promotions of one draft?
- **Interruption.** Mid-way through a multi-step modal: press Escape, click the backdrop, hit
  browser Back, refresh the page. Is there a partial write? Stale state on reopen?
- **Network interruption.** Throttle to offline mid-save (Playwright route interception or
  DevTools). Does the app surface a real error, or spin forever / silently drop the change?
- **Session expiry / idle.** There is a documented finding that there is **no idle timeout**.
  Confirm current behaviour rather than assuming.

### J7 — Cross-cutting sweep (run once, not per journey)

- **Console hygiene** — zero uncaught exceptions, zero unhandled promise rejections, zero React
  hydration mismatches, zero key warnings, across every page visited in J0–J6. List every one you
  did see, with the page.
- **Formatting** — no `NaN`, no `Invalid Date`, no `undefined` rendered, no float artefacts
  (`1234.5600000001`), no `[object Object]`. Currency matches the Settings value everywhere.
- **Totals** — on every table with a total row, the rows sum to the total.
- **Empty / single / large states** — a project with no BSR lines, one line, and several hundred.
- **Responsive** — 1920, 1366, and 390px. Horizontal overflow? Unreachable controls? Modals usable?
- **Light and dark mode** — both legible on every page; no invisible text.
- **Deep links and browser navigation** — every page reachable by direct URL when authorised;
  Back/Forward never leaves a stale or half-rendered view.
- **Refresh persistence** — F5 on every page after an edit; the edit is still there and the page
  restores its own state (active tab, filters, scroll).

### Crash catalogue — what counts as a crash, and how to capture it

"Without interrupt or crash" is the client's bar. Treat **all** of these as crashes, and capture
each with a screenshot plus the console text:

| Symptom | Where to look |
|---|---|
| Next.js dev error overlay / red screen | browser |
| React error boundary fallback | browser |
| Blank white page after a successful navigation | browser |
| Infinite loading skeleton / spinner that never resolves | browser |
| HTTP 500 from any route | network tab + `next dev` terminal |
| Unhandled promise rejection | console |
| Hydration mismatch | console |
| Server-side exception | `next dev` terminal output |
| A toast saying "Something went wrong" with no detail | browser |
| Download that produces a 0-byte or corrupt file | filesystem |

Every crash is at minimum **High** severity for a handover, regardless of how obscure the trigger.

### Known open — confirm, don't re-litigate

From `doc/claude-analyze-report/00-INDEX.md`, `doc/backend-security-report/`, and
`doc/test/security/`. For each, state **still present / now worse / resolved**, with evidence —
do not file as new:

- **X-02** malformed JSON → 500 instead of 400 (shared `apiRoute` wrapper)
- **X-03** CSP has no `script-src` (`frame-ancestors` only) — note the Phase-6 CSP work and the
  three CSP test-failure screenshots in `test-results/`
- **X-06** Zod validates types but not **ranges** — negative contract values, negative payments,
  unbounded `stages`, unguarded date parsing
- **X-07 / F-02-01 / F-03-03 / F-04-01** the money-sign cluster: ROI reads as profit when nothing
  is paid; negative contract corrupts the company-wide outstanding total; negative payment
  understates paid expense
- **F-04-02** three route families ignore the URL's project id (not exploitable as recorded)
- **AUTH-VULN-05** no session idle timeout
- **AUTHZ-VULN-01/02** double-promotion of a Basic Price draft (project-scoped and global)
- **AUTHZ-VULN-03** TOCTOU race in expense payment recording
- **Seed credential risk** — `prisma/seed.ts` hardcoded password
- **Prisma schema drift** — may still break `npm run db:reset-seed`
- **CSRF** — an Origin check was added 2026-09-19; verify it holds rather than assuming either way

**Do not test or report MFA.** The client declined it and it was removed on 2026-09-04.
Single-factor is the intended design.

A *new instance* of one of these patterns, in a place not previously audited, **is** a new
finding — report it and cross-reference the pattern.

---

## Deliverables

Write to **`doc/e2e-journey-report/`** (create it).

### 1. `RUN-LOG.md` — update after every journey, not at the end

This is what makes the exercise survive a session ending mid-way.

```markdown
# E2E Journey Test — Run Log
- Build: <git short sha> · Node <v> · DB: Option A local / Option B shared Supabase
- Started: <date> · Tester: Claude Code

| Journey | Scope | Status | Crashes | C | H | M | L | Date |
|---|---|---|---|---|---|---|---|---|
| J0 | Smoke baseline | ✅ done | 0 | 0 | 0 | 0 | 0 | |
| J1 | Admin — build the world | ⏳ | | | | | | |
| J2 | Create users & roles | ⏳ | | | | | | |
| J3 | Estimator journey | ⏳ | | | | | | |
| J4 | Finance journey | ⏳ | | | | | | |
| J5 | Zero-permission baseline | ⏳ | | | | | | |
| J6 | Lifecycle & concurrency | ⏳ | | | | | | |
| J7 | Cross-cutting sweep | ⏳ | | | | | | |

## Environment notes for whoever resumes
<traps hit, ports, credentials created, anything that cost you time>
```

### 2. `CLEANUP.md` — the ledger from §Database safety, kept live from the first row created

### 3. `HANDOVER_FUNCTIONAL_TEST_REPORT.md` — the final deliverable

This is the document that goes to the client. Write it **last**, once every journey is done.

```markdown
# Vega Construction Manager — Pre-Handover Functional Test Report

- **Tested:** <date range>
- **Build:** <git short sha> · **Environment:** <local Postgres / shared Supabase> · **Browser:** <version>
- **Scope:** 20 pages · 64 API routes · 4 account profiles · 8 journeys
- **Overall verdict:** 🔴 NOT READY / 🟠 READY WITH FIXES / 🟡 READY WITH DISCLOSURES / 🟢 READY

## 1. Executive summary
<Five sentences a non-technical stakeholder can read. Can this be handed over? What is the single
biggest risk? How many crashes were found?>

## 2. What was tested
Journey table: journey · account · permissions · pages covered · actions attempted · result.

## 3. Coverage matrix
| Module | Admin | Estimator (R1) | Finance (R2) | Zero-perm | Verdict |
|---|---|---|---|---|---|
| Dashboard | | | | | |
| Projects (+6 tabs) | | | | | |
| Basic Price / Basic Rate | | | | | |
| Activities | | | | | |
| Suppliers & Sub-contractors | | | | | |
| Price Comparison | | | | | |
| Payments | | | | | |
| Users / Roles / Settings | | | | | |
Each cell records reached / saw / could act, and whether that matched the permission model.

## 4. Crashes and interruptions
The section the client reads first. One subsection per crash:
**Reproduction steps → expected → actual → screenshot → console/terminal output → `file:line` → severity.**
If there are none, say so explicitly and state how hard you looked.

## 5. Functional findings
### E-01 — <short title>
- **Severity:** Critical / High / Medium / Low / Info
- **Confidence:** Confirmed / Unconfirmed
- **Class:** Crash | Permission | Data integrity | Money/calculation | UX | Persistence | Export | Validation | Performance
- **Journey:** J3 · **Account:** qa2-estimator · **Page:** `/projects/[id]` (Expenses tab)
- **Steps:** 1… 2… 3…
- **Expected:** … **Actual:** … **Evidence:** <screenshot path / response / console>
- **Location:** `src/app/…:123`
- **Impact:** <what the client's user actually loses>
- **Suggested fix:** <one line, DESCRIBE ONLY — do not implement>

## 6. Permission model verification
Did the two-layer model behave as designed? Every mismatch between "what the UI showed" and
"what the server permitted", in both directions — a hidden button whose route is open is a
security gap; a visible button whose route refuses is a UX defect. Both matter.

## 7. Known findings — current state
The §"Known open" table with a still-present / worse / resolved verdict and evidence for each.

## 8. Tested and clean
Specific and evidenced. "Estimator's direct GET of /projects/<Beta id> returned 403 and rendered
the denial panel without a console error" beats "permissions OK". This section is as valuable to
the client as the findings.

## 9. Not tested / blocked
Everything you could not cover and exactly why. **An unexamined area silently reported as clean is
worse than an admitted gap** — and this is the last check before handover, so gaps here are what
the client inherits unknowingly.

## 10. Handover readiness
- **Must fix before handover** — ranked, with the reason each is a blocker
- **Should disclose in writing rather than fix** — with suggested wording
- **Accepted / known limitations** — what the client is knowingly receiving
- **Sign-off statement** — one paragraph: what this test does and does not certify
```

Severity guide: **Critical** = data loss, auth bypass, cross-user data exposure, money computed
wrong in the client's favour or against it. **High** = any crash, privilege gap, broken core
workflow, export producing wrong figures. **Medium** = missing validation, confusing denial, a
workflow with a workaround. **Low** = cosmetic, minor UX. **Info** = observation.

### Working method

Do **one journey at a time**, start to finish: run it → write its findings → update `RUN-LOG.md` →
update `CLEANUP.md` → next journey. Do not batch all eight and leave the writing to the end.

Before starting, read `RUN-LOG.md` — if a journey already has a status, skip to the next one.
At the start of each journey tell me which one you are on; at the end give me a one-line verdict
with the crash and finding counts.

When all eight are done: do the cleanup, verify no orphans, then write
`HANDOVER_FUNCTIONAL_TEST_REPORT.md` from the accumulated notes.

---

## Notes on using this prompt

- **It is resumable by design.** Eight journeys across 20 pages and 64 routes will not fit in one
  context window. Re-paste the prompt when a session ends; `RUN-LOG.md` is what makes the next run
  pick up cleanly.
- **The database decision is not optional.** `DATABASE_URL` is a shared remote Supabase instance.
  Running a destructive functional test against it without the Option B discipline is the one
  mistake here that cannot be undone. Make the call, write it at the top of the report, stick to it.
- **J6 is the highest-value journey and the one most likely to be skipped.** Lifecycle and
  concurrency bugs are invisible to page-by-page testing and are exactly what a client hits in
  week one with two people logged in at once. Do not let it be the section that gets cut for time.
- **J1's BSR recipe arithmetic and J4's money cross-check are the two places a real bug is most
  likely to be sitting undiscovered** — the BSR derived-rate maths is recorded as never exercised,
  and the money-sign findings cluster is still open.
- **This complements, does not replace, the other two prompts.** Where they overlap: the
  page-by-page prompt is authoritative on a single page's UI detail, the backend prompt is
  authoritative on what the server permits, and this one is authoritative on **whether the product
  works as a product**. If this report and one of theirs disagree, re-test and say so.
- **Parallelising:** J3, J4 and J5 are independent once J2 has created the fixtures. They can be
  split across sessions if each one updates `RUN-LOG.md`. J0→J1→J2 must run in order, and J6 needs
  everything before it.
