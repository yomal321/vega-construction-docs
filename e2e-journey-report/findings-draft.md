# Findings draft (working notes, folded into HANDOVER_FUNCTIONAL_TEST_REPORT.md at the end)

## J0 — Environment & smoke baseline

- Build: `ece3731` (working tree has pre-existing uncommitted changes, see RUN-LOG "Environment notes")
- Node: v22.11.0 · Browser: Chromium via Playwright 1.63.0 · DB: Option A, local Postgres 18, database `vega_qa`
- Date: 2026-09-21
- Server under test: `http://localhost:3001` (an already-running `next dev` process that picked up
  the local DB via env hot-reload; a second `next dev` I started detected the collision and exited
  cleanly on its own — no orphaned process created by this exercise). A separate, older, unrelated
  process was also found listening on port 3000 (different security-header fingerprint, started
  the day before) — left untouched, not used for testing.

### E-00 — `/api/healthz` and `/api/ready` require authentication, defeating their purpose
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Permission / Operability
- **Journey:** J0 · **Account:** none (unauthenticated) · **Page:** `/api/healthz`, `/api/ready`
- **Steps:** `curl http://localhost:3001/api/healthz` / `.../api/ready` with no session cookie.
- **Expected:** `{"status":"ok"}` (or a readiness payload) with HTTP 200 — these are infra liveness/
  readiness probes, meant to be hit by an orchestrator with no session.
- **Actual:** HTTP 401 `{"error":"Not authenticated"}` for both. The handler itself
  (`src/app/api/healthz/route.ts:10-12`) unconditionally returns `{status:'ok'}` and has a comment
  explicitly describing it as a liveness probe for "the kubelet" — but the request never reaches
  the handler because the global auth gate rejects it first.
- **Location:** `src/proxy.ts:15` — `PUBLIC_PATHS = ['/login', '/api/auth/login']` does not include
  `/api/healthz` or `/api/ready`, so both fall through to the `if (!token)` branch at
  `src/proxy.ts:86-89` and get a 401 before ever reaching the route handler.
- **Impact:** Any k8s/k3s-style liveness or readiness probe configured to hit these paths (which is
  exactly what `healthz/route.ts`'s own comment says they're for) will always report unhealthy/not
  ready and the orchestrator will restart-loop the pod, since it has no session cookie to present.
  This would be caught immediately in any real deployment with liveness probes configured — worth
  confirming whether the k3s deployment config actually points at these paths before treating this
  as launch-blocking.
- **Suggested fix:** add `/api/healthz` and `/api/ready` to `PUBLIC_PATHS` in `src/proxy.ts`
  (describe only, not implementing).

### Page-by-page smoke (Admin, `nimal@vegahomes.lk`)
14 of the 20 documented pages are reachable without journey-specific fixtures and were all
visited as Admin via a dedicated Playwright spec (`tests/e2e-journey/j0-smoke.spec.ts`):
`/`, `/projects`, `/activities`, `/basic-price`, `/basic-rate`, `/payments`, `/suppliers`,
`/suppliers/compare`, `/users`, `/roles`, `/settings`, `/settings/company-profile`,
`/settings/field-options`, `/settings/project-access`.

- **Result: clean.** Zero browser console errors, zero uncaught page errors, across all 14 pages.
  Dashboard renders real seeded figures (3 projects, payments, expenses by category, rate-change
  feed, pending payments) — screenshot-verified.
- Note on method: an initial overlay-detection check (`nextjs-portal` element presence) produced a
  false positive on every page — that custom element is always present in the DOM in Next dev mode
  as a portal root, whether or not an error is showing. Verified by screenshot that the dashboard
  render is clean; not treating this as a finding, just a note on the detection method used.
- **Deferred to J1/J2:** `/projects/[id]`, `/suppliers/[id]`, `/suppliers/compare/item`,
  `/sub-contractors/[id]`, `/users/[email]` need real entities that don't exist yet on a fresh DB —
  will be exercised naturally as J1 creates the project/supplier/sub-contractor and J2 creates users.
- `/login` itself exercised as part of the login flow (loads, accepts credentials, redirects to `/`).

### Test-suite state (handover-critical fact per prompt's explicit ask)
- `playwright.config.ts`'s "KNOWN BROKEN" banner (dated 2026-09-18) claims `tests/helpers.ts`
  shells out to `wrangler d1 execute --local`. **This is now false.** Ran the existing
  `tests/01-login.spec.ts` against the local Postgres DB: `clearLoginThrottle()` /
  `execLocalSql()` (which now runs through `scripts/test-db-exec.mts` over `DATABASE_URL`) worked
  correctly — the brute-force-throttle tests that depend on it passed. 2 of 19 tests in that spec
  failed, but only because the spec's hardcoded `ADMIN`/`INACTIVE` accounts
  (`tests/helpers.ts:13-18`) belong to the shared Supabase DB's specific seed, not this exercise's
  fresh local seed — not a product bug, an account-fixture mismatch from running under Option A.
- Separately (not previously flagged in the prompt): `tests/02-dashboard.spec.ts` and likely
  `03`–`05` still write fixture SQL using SQLite/D1 syntax (`datetime('now')`), which is not valid
  Postgres (`now()` is the Postgres equivalent) — these specific specs would fail if run, on top of
  the account mismatch. Noting for whoever owns the test-suite migration; out of scope to fix here
  per the "don't fix anything" ground rule, and not itself a product defect.
- **Trap reconfirmed the hard way:** `prisma migrate deploy` (via `npm run db:migrate`) does **not**
  read `.env.local` — only `next dev`'s own loader does. Running it without an explicit
  `DATABASE_URL` shell export connected it to the **shared Supabase instance** (read-only "no
  pending migrations" check, no writes occurred). Same applies to `tests/helpers.ts`'s
  `execFileSync(... '--env-file=.env' ...)": an already-exported `DATABASE_URL` in the parent shell
  takes precedence over `--env-file=.env`'s value, which is what made the local-DB test run above
  actually hit the local DB rather than Supabase — confirmed by inspecting `vega_qa.login_throttle`
  after the run. **Every subsequent `npm run db:*`, `tsx`, or `npx playwright test` invocation in
  this exercise explicitly exports `DATABASE_URL` first; do the same if resuming this in a new
  session.**

**J0 verdict:** ✅ done. 0 crashes. 1 Medium finding (E-00, healthz/ready auth gate). Test-suite
state confirmed: DB helper layer works, two pre-existing specs have account/DB-dialect mismatches
unrelated to this exercise.

## J1 — Admin journey: build the world (in progress)

### J1 part 1 — Company profile, Field options, Suppliers & Sub-contractors, Activities
Driven via `tests/e2e-journey/j1a-settings-catalog.spec.ts` as Admin (`nimal@vegahomes.lk`).

- **Company profile:** all 7 fields save correctly and persist across a hard reload. Clean.
- **Field options:** category (with code prefix + badge color), unit, and trade all add cleanly.
  Renamed a unit (`QA2 Bag` → `QA2 Bag Renamed`) — UI reflects the rename immediately. The
  prompt's specific ask ("confirm the rename cascades — this uses `db.batch`, check for
  half-applied state") needs a unit that's actually *referenced* by a `base_items`/
  `basic_price_items` row to be meaningful — deferring the actual cascade proof to J1 part 3
  (Basic Price/BSR), where a Basic Price item will be created using this renamed unit, then
  renamed again and checked against the DB directly.
  - **Confirmed correct duplicate-prevention UX**: re-adding a category with an already-used code
    prefix is cleanly rejected with a specific, correct toast (`Prefix "QA2" is already used by
    another category`) — not a crash, not a silent failure. (Discovered incidentally via a test
    re-run colliding with itself; not a product bug.)
  - **Observation (Info, not a finding):** Activities allow duplicate names with no uniqueness
    check (unlike Field-option categories, which do check prefix uniqueness). Consistent within
    itself, just noting the asymmetry in case it's not deliberate.
- **Suppliers & Sub-contractors:** both add cleanly, both detail pages (`/suppliers/[id]`,
  `/sub-contractors/[id]`) load without error — covers 2 of the 5 dynamic-route pages deferred
  from J0.
- **Activities:** create and rename both work. **UX note (Low):** the Activities list paginates
  (14/page) with only Previous/Next controls and no "jump to last page" — a newly created activity
  (appended at the end) is invisible on page 1 with no indication of which page to check. Minor,
  but worth a mention for a catalog admins will grow over time.

**Running verdict so far:** 0 crashes in J1 part 1. 0 new Medium/High findings; 1 Low UX note
(pagination) and 1 Info observation (duplicate activity names). Continuing to J1 part 2 (Project
Alpha: BSR/stages/expenses/basic-price/basic-rate tabs) and part 3 (second project, exports,
dashboard cross-check).

### E-02 — Unit rename cascade misses `activity_items.unit` (BSR items keep the stale unit name)
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Data integrity
- **Journey:** J1 · **Account:** Admin · **Page:** `/settings/field-options` (rename a unit),
  effect visible on `/projects/[id]` BSR tab
- **Steps:** Created unit "QA2 Bag Renamed", used it as the unit on both a Basic Price draft (→
  promoted to a Basic Rate item) and a BSR item's own unit field. Renamed the unit again via
  Settings → Field options (`QA2 Bag Renamed` → `QA2 Bag Cascade Check`).
- **Expected:** Every row that stored the unit by name (the same "denormalized copy" pattern the
  code's own comment at `src/app/api/units/[id]/route.ts:24-26` describes) updates atomically.
- **Actual:** `basic_price_items.unit` and `base_items.unit` correctly updated to
  `QA2 Bag Cascade Check` (verified directly in the DB). `activity_items.unit` — the unit field
  on a BSR item created via the Basic rate/BSR builder — **did not update** and still reads the
  old name `QA2 Bag Renamed`.
- **Location:** `src/app/api/units/[id]/route.ts:27-31` — the `db.batch([...])` cascade lists only
  `base_items` and `basic_price_items`; `activity_items` (populated by
  `src/app/api/projects/[id]/items/route.ts:70-72`, which also stores `unit` as a plain string
  column, not a foreign key) is not included.
- **Impact:** A BSR item's displayed/exported unit can silently diverge from the Basic Price/Basic
  Rate unit it was built from, after any admin renames that unit — confusing on its own, and a
  correctness risk anywhere the app matches or displays units by exact string across these tables
  (e.g. any future unit-based filtering or export). Checked whether the same gap exists for the
  trade-rename cascade (`src/app/api/trades/[id]/route.ts`) — it does not: that route's own
  comment confirms trade is stored only on `basic_price_items.trade` (no `base_items` or
  `activity_items` trade column exists), so there's nothing to miss there. This appears to be
  specific to units.
- **Suggested fix (describe only):** add `db.prepare('update activity_items set unit = ? where
  unit = ?').bind(name, existing.name)` to the same batch in `units/[id]/route.ts`.

### J1 part 2 — Project Alpha: Basic Price → Basic Rate promotion

Created "QA2 Project Alpha" (5 stages, contract LKR 15,000,000) cleanly through the UI — dashboard
cards showed correct initial state (Outstanding 100% of contract, ROI +0, etc.).

Created a Basic Price draft ("QA2 Cement 50kg bag", category QA2 Waterproofing, trade QA2
Concrete, unit QA2 Bag Renamed, price 1,850, supplier QA2 Cement Suppliers Ltd), then used the
row's "Promote" action to promote it to Basic Rate.

### E-01 — Mutating `fetch()` calls across the app never check the HTTP response before declaring success
- **Severity:** High
- **Confidence:** Confirmed (by source inspection; the specific promote incident below that led to
  this discovery is Confirmed-but-unexplained as its own data point, see below)
- **Class:** Data integrity / Error handling
- **Journey:** J1 · **Account:** Admin · **Page:** `/projects/[id]` (Basic price tab), and
  systemically across `src/components/CatalogProvider.tsx` and `src/app/projects/[id]/client.tsx`
- **What happened:** While promoting the "QA2 Cement 50kg bag" draft to Basic Rate, the UI showed
  the success toast "Promoted to Basic Rate as QA2-001" and the item appeared on the Basic Rate
  tab. A direct database check immediately afterward showed the draft's `status` column was still
  `'draft'` (not `'promoted'`), `promotedCode` was still `null`, and no corresponding row existed
  in `base_items` at all. A second, identical promote action on the same draft then succeeded and
  correctly persisted (`status='promoted'`, `base_items` row created). Ruled out the DB safety
  concern this raised: confirmed via read-only query that no QA2-named rows exist on the shared
  Supabase instance — the first attempt's write did not silently land on production, it appears to
  have simply not persisted anywhere, for a reason not fully pinned down (see Impact).
- **Root cause (confirmed by reading the source, independent of the above incident's exact
  trigger):** `promote()` in `src/components/CatalogProvider.tsx:100-105` does
  `await fetch(...)` and discards the `Response` entirely — it never checks `res.ok` — before
  revalidating SWR and returning. Its caller,
  `src/app/projects/[id]/client.tsx:3942-3948` (`PromoteModal`'s `onConfirm`), then
  unconditionally calls `show('Promoted to Basic Rate as ${code}')` with **no way to know whether
  the request actually succeeded**. This is not an isolated case: the same "fire the fetch,
  discard the Response" shape appears in **11 of 25** mutation calls in `CatalogProvider.tsx`
  (every plain `addX`/`updateX` — draft add/edit, rate edit, activity add/edit, category add/edit,
  trade add/edit, unit add/edit, supplier add/edit, sub-contractor add/edit — only the `deleteX`
  calls capture `res` and check `.ok`) and in **8 of 16** `fetch()` calls in the much larger
  `src/app/projects/[id]/client.tsx`. Any server-side failure on any of these calls — a validation
  rejection, a transient DB error, a 500 — is silently swallowed: the SWR cache still revalidates
  (so the UI *may* self-correct on next read if the write partially applied, or *may* just show
  stale data), and the user is told the action succeeded regardless.
- **Impact:** A user cannot trust any success toast for these actions. In the specific incident
  observed, an Admin doing exactly what J1 asks them to do (create a draft, price it, promote it)
  would have walked away believing the item was live on Basic Rate — confirmed visually on the
  Basic Rate tab in the same session — while the server-side record was not actually promoted.
  Whether this exact non-persistence was a one-off dev-environment hiccup (this session's dev
  server had its env hot-reloaded mid-session, see RUN-LOG "Environment notes") or a genuine
  server-side reliability gap under load/contention cannot be fully determined from this session
  alone — but the **code has no mechanism to detect or report either case** to the user, which is
  the actual defect regardless of root cause.
- **Location:** `src/components/CatalogProvider.tsx:85,90,101,108,129,134,152,169,186,205,224`
  (11 unchecked mutations); `src/app/projects/[id]/client.tsx` (8 more, not yet individually
  enumerated — grep `await fetch(` in that file for the full list); the specific incident is at
  the promote flow, `client.tsx:3942-3948` → `CatalogProvider.tsx:100-105` →
  `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts`.
- **Suggested fix (describe only):** every mutating `fetch()` should check `res.ok` (or parse a
  typed error body) before the caller shows a success toast or optimistically assumes the mutation
  applied — the existing `deleteX` functions in the same file already demonstrate the pattern to
  follow. Given the scope (19 call sites across two files), this reads like a systemic gap rather
  than 19 separate oversights — worth a dedicated pass rather than one-off patches.

### J1 part 3 — BSR arithmetic verification (hand-computed) and Stages

Built a BSR item ("QA2 Cement plastering to walls", unit QA2 Bag Renamed, analysisQty=10) with:
- 1 base component: 5 × "QA2 Cement 50kg bag" @ LKR 1,850/unit = **9,250**
- 1 % allowance: 10% of the subtotal-so-far (9,250) = **925**
- Recipe total = 10,175 → rate/unit = 10,175 ÷ 10 = **LKR 1,017.50**

The app displayed **LKR 1,017.50** exactly, before the item was even saved. Added to BSR at
Ground floor, qty 1 → line total LKR 1,017.50 (correct: rate × 1.0 floor multiplier × qty).
Edited the line to qty 3 → line total recalculated to **LKR 3,052.50** (1,017.50 × 3, correct).

**Note on floor multipliers:** could not exercise a non-default (≠1.0) floor multiplier as the
prompt asks. Every item created via the "Add item" builder is hard-coded to `floors: [1,1,1,1]`
(`client.tsx` `NewItemBuilder.confirm()`) — there is no field in either the create or edit form
to set `floorGround`/`floor1st`/`floor2nd`/`floor3rd`, even though the schema and
`floorMultiplier()` fully support per-floor values (the seed data has non-1 values on some seeded
items). The per-line "factor calculator" is explicitly commented in source as
"a view-only estimation helper, nothing here persists." This looks like a real UI gap relative to
the data model, but filing as **Low** / "Not fully tested — no UI path found" rather than a
functional defect, since it may be an intentionally-deferred feature.

**Stages & payments:** marked Stage 1's Advance payment (50% × 3,000,000 = 1,500,000) "Paid".
Dashboard cards updated correctly and consistently: Received LKR 1,500,000 (10% of contract),
Outstanding LKR 13,500,000 (90%), ROI +LKR 1,500,000. Zero-expense division handled gracefully
(shows "0.0% on paid expense", not `NaN`/`Infinity` — no crash).

### E-03 — "Log expense" date field defaults to a hardcoded literal date, not today
- **Severity:** High
- **Confidence:** Confirmed
- **Class:** Data integrity / Validation
- **Journey:** J1 · **Account:** Admin · **Page:** `/projects/[id]` (Expenses tab → Log expense)
- **Steps:** Open "Log expense" on any project on any date. Do not touch the Date field.
- **Expected:** Date defaults to today (2026-09-21 in this session).
- **Actual:** Date field defaults to **15 Jul 2026** — a hardcoded literal, not computed from
  `new Date()`. Confirmed at `src/app/projects/[id]/client.tsx:2876`:
  `const [date, setDate] = useState('2026-07-15')`. Every other date-like default in this same
  file computes from `new Date()` (e.g. line 230's `today`) — this one specific field is a
  leftover placeholder value.
- **Cascading effect:** the auto-generated invoice number format is `VH-INV-MM-YYYY-NNN`, derived
  directly from the expense date's month/year (`client.tsx:2925-2927`). Because the date defaults
  to July, every expense logged without manually correcting the date gets invoice numbers stamped
  `VH-INV-07-2026-NNN` instead of the actual current month — confirmed: two expenses logged today
  (2026-09-21) auto-numbered `VH-INV-07-2026-001` and `-002`. Also observed the persisted
  timestamp is `2026-07-14T13:00:00.000Z` for a field displaying `07/15/2026` — a secondary
  one-day timezone-shift artifact on top of the wrong literal, consistent with the "unguarded
  date parsing" pattern already flagged as X-06 in the known-open list, though this specific
  hardcoded-default instance is new.
- **Impact:** Every expense an operator logs without manually changing the date is silently
  misdated by roughly two months and gets a wrong invoice number — a financial record-keeping
  integrity problem for a construction-management app, and it would go unnoticed unless someone
  specifically checks the date column (the rest of the UI — amount, vendor, stage — all looked
  correct, so this is easy to miss). Affects reporting/exports grouped or filtered by month/date.
- **Location:** `src/app/projects/[id]/client.tsx:2876` (and the invoice-numbering cascade at
  `2920-2931`).
- **Suggested fix (describe only):** initialize `date` from `new Date().toISOString().slice(0,
  10)`, matching the pattern already used elsewhere in this file (line 230).

**Known-open reconfirmed, not a new finding:** this is a live, direct reproduction of the
already-documented **F-02-01 "ROI reads as profit when nothing is paid"** pattern — with expenses
still at LKR 0, the dashboard shows "+LKR 1,500,000" ROI, which reads as profit despite no cost
data having been entered yet (not that costs are zero — none have been recorded). Still present,
confirmed with fresh evidence on this build.

### J1 part 4 — Expenses and payments

Logged an itemized expense (2 line items, LKR 92,500 + LKR 5,000 = **LKR 97,500** flat sum,
correct per `lineItemSchema` — `amount` is each line's own total, `qty` is descriptive only, not
multiplied). "Amount" field correctly locked/computed to 97,500 once items were added. Then
recorded a partial payment of LKR 50,000 against it.

**Result: arithmetic correct throughout.** Paid LKR 50,000 (51% of committed, correct rounding),
Outstanding LKR 47,500 (97,500 − 50,000, correct), status badge changed to "Partial" (correct —
neither "Pending" nor fully "Paid"). Expenses dashboard card: LKR 97,500 / Paid LKR 50,000.

**Known-open reconfirmed, with vivid fresh evidence:** Project ROI card now reads
**"+LKR 1,450,000 · 2900.0% on paid expense"** (1,500,000 received − 50,000 paid = 1,450,000;
1,450,000 ÷ 50,000 × 100 = 2900%). This is the same F-02-01/money-sign-cluster pattern — dividing
by a small `expensePaid` early in a project's life produces a wildly misleading percentage that
reads as a stellar return when in fact almost nothing has actually been spent or accounted for
yet. Not filing as new (already tracked), but this is about as clear a live reproduction as the
pattern gets — worth quoting directly in the final report's "Known findings" section as evidence
the issue is still exactly as documented.

### J1 part 5 — Basic Rate: edit/history, second project, clone, import

- **Edit + history:** edited QA2-001's rate 1,850 → 2,100. UI updated correctly.
  `GET /api/projects/.../basic-rate/QA2-001/history` returned
  `[{"oldRate":1850,"newRate":2100,"by":"Nimal Perera","at":"21 Sept 2026, 05:41"}]` — actor and
  timestamp both correct, matching the prompt's specific ask.
- **Created QA2 Project Beta** (4 stages, contract LKR 8,000,000) — needed for cross-project
  scope-isolation testing in J3, and to exercise Clone.
- **Clone from another project:** cloned Alpha's Basic Rate catalog into Beta. Carried over the
  *current* rate (2,100, post-edit) and the *current* (post-rename-cascade) unit name correctly.
  **Independence verified directly in the DB**: edited Beta's copy to 9,999, re-queried both rows
  — Alpha stayed at 2,100, Beta at 9,999. Genuinely independent copies as documented, no shared
  state or accidental cross-project mutation. Also positively note: `cloneFrom()` in
  `client.tsx:4062-4080` **does** check `res.ok` before showing success — a correct counter-example
  to the E-01 pattern, showing the codebase isn't uniformly bad here, just inconsistent.
  - **Note (not filed as a finding):** clicking "Clone catalog" does *not* raise the shared
    confirm() dialog that nearly every other mutating action in this app does (add/rename/delete
    all do). Inconsistent, but arguably fine since Import right next to it also has an explicit
    preview-then-confirm step of its own — not filing since it's a UX-consistency nit, not a
    functional defect.
- **Import (Excel):** uploaded a 1-row `.xlsx` (Description/Category/Unit/Rate/Supplier header).
  Preview screen correctly parsed and displayed the row as "1 new" before any write; confirming
  actually inserted it. Clean, correct, matches the documented "every row is shown to you before
  anything is saved" behavior.

### J1 part 6 — Exports and company-wide dashboard cross-check

- **Exports:** Dashboard "Portfolio Income Statement" Excel (7,765 bytes) and Project BSR Excel
  export (7,438 bytes) both downloaded successfully, both non-empty. Not opened byte-for-byte
  against every on-screen figure given time budget, but file presence/size rules out the "0-byte
  or corrupt download" crash class for these two.
- **Company-wide dashboard**, checked after both QA2 projects existed: Projects table correctly
  shows QA2 Project Beta (Income 0, Expense 0 — accurate, nothing recorded there) and QA2 Project
  Alpha (Income 1,500,000, Expense 97,500 — matches exactly what J1 recorded). "Rate changes"
  activity feed correctly attributes both Basic Rate edits to the right actor and project
  (`Nimal Perera · QA2 Project Beta: 2,100 -> 9,999`, `Nimal Perera · QA2 Project Alpha:
  1,850 -> 2,100`).
- **Known-open reconfirmed, flagship evidence:** the company-wide **Overall ROI** card — the very
  first thing an Admin sees on login — reads **"+LKR 18,370,625 . 36,741.3% on paid expense."**
  This is the same F-02-01 division-by-small-`expensePaid` pattern as the two project-level
  instances above, now visible at the top-level portfolio dashboard with an even more extreme,
  clearly-nonsensical percentage. This is the single most visible reproduction of this pattern
  found in the whole exercise — recommend leading with this exact figure in the final report's
  "Known findings" section as the concrete evidence.

**J1 verdict:** done. 0 crashes. 3 new findings (E-01 High, E-02 Medium, E-03 High). Known-open
F-02-01 reconfirmed three times with escalating, concrete evidence. All arithmetic hand-verified
(BSR recipe/rate, stage milestones, expense totals, payment outstanding) matched exactly wherever
checked. Clone/import/history all correct.

## J2 — Create test users and roles

- **Roles created and verified via DB**: QA2 Estimator (dashboard:view, projects:view/create/edit,
  activities:view/create/edit, suppliers:view) and QA2 Finance (dashboard:view, payments:view,
  priceComparison:view) — permission sets match the prompt's spec exactly, confirmed via direct
  query of `role_permissions`.
- **User-creation form validation, tested live:**
  - Duplicate email: correctly rejected — "A user with email ... already exists"
  - Invalid email format: correctly rejected — "Enter a valid email address"
  - Weak/common password (`password123`, 11 chars): correctly rejected — "Password must be at
    least 12 characters" (length check fired; did not separately confirm the dictionary/
    common-password check fires independently of length given time budget)
  - Password containing the user's own identity (`qa2identitytest1234` for
    `qa2identitytest@vegahomes.lk`): correctly rejected — "Password must not be based on your
    name or email"
  - **Empty name: NOT rejected.** Silently falls back to the literal string `"New user"` — same
    `name || 'New user'` pattern already used for empty project names
    (`src/app/users/page.tsx:303,309`). Not filing as a functional bug (deliberate, consistent
    pattern across the app), but noting as a **Low** UX/data-quality observation: nothing stops
    an Admin from ending up with several accounts all literally named "New user" in the Users
    list, which would be hard to tell apart. Left one such test account in the DB
    (`qa2-emptyname-test@vegahomes.lk`) as evidence — see CLEANUP.md.
- **Created all 4 required accounts**, verified via DB: `qa2-estimator@vegahomes.lk` (Staff, role
  QA2 Estimator), `qa2-finance@vegahomes.lk` (Staff, role QA2 Finance),
  `qa2-zero-perm@vegahomes.lk` (Staff, zero roles/permissions — this session's equivalent of the
  prompt's `csp-test-staff`), `qa2-admin2@vegahomes.lk` (Admin).

### E-04 — Project ownership transfer has a working API but no UI entry point
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** UX / Missing feature surface
- **Journey:** J2 · **Account:** Admin · **Page:** `/settings/project-access`,
  `/projects/[id]`
- **Steps:** Tried to follow the prompt's instruction to make a Staff user a project owner
  through the UI. `/settings/project-access` explicitly states ownership is fixed to the
  creator and this page only manages *membership* ("this only grants visibility, not
  permissions"). The project detail page shows `Owner: <name>` as a static label
  (`client.tsx:402`, a plain `MetaChip`) with no click handler. Grepped the whole project client
  for any "Transfer ownership" affordance — none found.
- **Expected:** Either a UI path to reassign ownership, or (if intentionally API-only) no
  fully-built backend suggesting otherwise.
- **Actual:** `PATCH /api/projects/[id]/owner` is a complete, correct, Admin-only endpoint —
  transfers ownership, demotes the outgoing owner to a member for handover continuity, removes
  any redundant member row for the incoming owner, and **already implements the exact
  "ordering trap" safety check** the prompt warns about
  (`assertAssignableUser` — refuses to make a permissionless user an owner). Confirmed working
  correctly via direct API calls (see below). It just has no UI button anywhere.
- **Impact:** Low severity since nothing is broken — but if a client ever needs to actually
  reassign a project (an employee leaves, a PM changes), there is currently no way to do it
  from the app itself, despite the backend being fully built and tested. Worth flagging since
  this looks like an accidentally-unshipped feature rather than a deliberate omission (the
  code comment literally frames it as "the one legitimate way `Project.ownerId` ever changes
  after creation").
- **Location:** No UI location exists; backend at
  `src/app/api/projects/[id]/owner/route.ts`.
- **Suggested fix (describe only):** add a "Transfer ownership" action somewhere reachable
  (e.g. the project detail header, next to the Owner chip, Admin-only).
- **Used as fixture shortcut, per the prompt's explicit allowance for this case:** called the
  API directly to transfer QA2 Project Alpha's ownership to `qa2-estimator` for J3. Also used
  it to independently test the ordering trap.

### Ordering trap — confirmed correct, not a crash
Attempted `PATCH /api/projects/{alphaId}/owner` with `newOwnerId` = `qa2-zero-perm` (a Staff
user with no role/permissions at all yet). Got a clean **400**: `"This user has no role assigned
yet — give them one on the Roles page first."` — exactly the documented behavior, no crash, no
500, a specific and actionable message. Then transferred Alpha's ownership to `qa2-estimator`
(who does have a role) — succeeded (200), and the UI's `Owner:` chip correctly updated to show
"QA2 Estimator User" on reload.

**J2 verdict:** done. 0 crashes. 1 new Low finding (E-04, ownership-transfer has no UI). All
validation rules behaved correctly except the deliberate empty-name fallback (Info, not a bug).
Fixtures ready for J3/J4/J5: qa2-estimator owns Alpha (and nothing else), qa2-finance has no
project reach at all, qa2-zero-perm has zero permissions, Beta remains entirely outside
qa2-estimator's reach (never made a member of it).

## J3 — Estimator journey (qa2-estimator@vegahomes.lk)

### Navigation shape
Sidebar correctly shows only: Dashboard, Basic price, Basic rate, Activities,
Suppliers & sub-contractors, Projects. Correctly **hides**: Payments, Price comparison, Users,
Roles, Settings — matching the role's actual permission set exactly.

### E-05 — Admin-only pages (`/users`, `/roles`, `/settings`) render their full editable UI for non-Admin users who reach them by direct URL
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** UX (not a security hole — see below)
- **Journey:** J3 · **Account:** qa2-estimator (Staff, no admin) · **Pages:** `/users`, `/roles`,
  `/settings`
- **Steps:** As Estimator, typed `/users` directly into the URL bar (nav correctly hides the
  link). Compared against typing `/payments` directly (also hidden from nav).
- **Expected (and what `/payments` actually does):** a clean "You don't have access to this
  page — Ask an admin to assign you a role with access to this section" panel, matching the
  `RequirePermission` pattern used on the permission-gated pages.
- **Actual:** `/users` renders the **entire real admin page** — stat cards, the user table
  (empty, since the underlying `GET /api/users` correctly 403'd), and a fully clickable
  **"Add user" button**. Clicking it opens the real add-user form; filling it out and
  submitting reaches a live `POST /api/users`, which the server correctly refuses
  (`403 {"error":"Admin access required"}` — confirmed via network capture) and the client
  correctly surfaces as a toast ("Admin access required") without closing the dialog as if it
  had succeeded. **No user was actually created** (verified directly in the DB — 0 rows). Same
  shape confirmed by source inspection for `/roles` and `/settings`: all three pages show a
  static "Admin only" text badge (cosmetic) but have **no `RequirePermission`/`requireAdmin`
  gate** wrapping the page content, unlike `/payments` and the other RBAC-gated pages.
- **Why this is UX, not a security gap:** the server-side check is correct and was verified to
  actually refuse the write. This is exactly the distinction the test prompt asks to draw — "a
  visible button whose route refuses is a UX defect" (as opposed to a hidden button whose route
  is open, which would be the security gap). No data or access was ever actually exposed or
  created.
- **Impact:** confusing and unprofessional in front of a real user or a client demo — a Staff
  user can spend a minute filling in a whole "Add user" form (name, email, password, role
  selection) before being told they can't do this at all, instead of being told immediately on
  arrival like every other restricted page in the app does. Inconsistent with the app's own
  established pattern.
- **Location:** `src/app/users/page.tsx`, `src/app/roles/page.tsx`, `src/app/settings/page.tsx`
  — none import or use `RequirePermission` (grepped; zero matches in all three, versus every
  RBAC-gated page which does).
- **Suggested fix (describe only):** wrap these three pages the same way `/payments` etc. are
  wrapped — gate on `session.role === 'Admin'` and show the same denial panel pattern.

### J3 — Allowed happy path
Created a new project ("QA2 Estimator Created Project", 4 stages, contract 4,000,000) through
the UI as Estimator — succeeded (has `projects:create`). Edited its client name — succeeded (has
`projects:edit`). **Persisted correctly across a hard reload** (not just optimistic UI).

### J3 — Correctly denied (all clean, no crashes)
- Delete button correctly **hidden** on Estimator's own project (no `projects:delete`); direct
  `DELETE /api/projects/{id}` also correctly 403'd server-side — both layers agree.
- Promote (direct API call, no UI path even attempted): `403 {"error":"Missing permission:
  projects:promote"}` — specific, clean, not a crash.
- Supplier rename/edit button correctly **hidden** (has `suppliers:view` only).
- Opening `QA2 Project Beta` by direct URL: page renders a clean **"Project not found"** state
  (not a blank page, not a raw stack trace, not a shell that half-loads then explodes) — exactly
  the behavior the prompt asks to verify. `GET /api/projects/{betaId}` also correctly 403's.

### J3 — Scope isolation: confirmed sound
Dashboard and Projects-list figures for the Estimator **exactly** match the sum of only their
reachable projects (Alpha as owner + their own new project) — Received LKR 1,500,000, Outstanding
LKR 17,500,000 (13,500,000 from Alpha + 4,000,000 from the new project, both hand-verified) — and
**never** mention Beta or any of the seeded legacy projects the company-wide Admin dashboard
shows. This directly and positively answers the prompt's specific concern about the
`projectAccessClause` "bare-ID footgun" (`src/lib/rbac.ts`) — scoping held correctly under a real
multi-project, multi-user scenario. Dashboard export as Estimator also produced a smaller,
non-empty file (7,332 bytes vs. the Admin company-wide export's 7,765 bytes), consistent with a
properly-scoped dataset.

**Known-open reconfirmed, 4th instance:** Estimator's dashboard ROI card still reads
"+LKR 1,450,000 · 2900.0% on paid expense" (same figure as Admin's project-level view of Alpha,
correctly scoped to what they can see) — same F-02-01 pattern, now confirmed to reproduce
consistently across different user roles and scopes, not just Admin.

**J3 verdict:** done. 0 crashes. 1 new Medium finding (E-05, admin pages render their full
editable shell for non-Admin users — UX only, server-side checks all held). Happy path,
denials, and scope isolation all behaved exactly as designed.

## J4 — Finance journey (qa2-finance@vegahomes.lk)

### Navigation and reach
Sidebar correctly shows only Dashboard, Payments, Price comparison. Correctly refuses (clean
"You don't have access" panel, no crash) on every project-shaped page tried by direct URL:
`/projects`, `/projects/{alphaId}`, `/basic-price`, `/basic-rate`, `/activities`, `/suppliers`.
`GET /api/projects/{alphaId}` directly also correctly 403's.

### E-06 — Dashboard, Payments, and Price Comparison are scoped by project ownership/membership on top of their own module permission, so a "financial visibility only" role sees nothing
- **Severity:** High
- **Confidence:** Confirmed
- **Class:** Permission model / Broken core workflow
- **Journey:** J4 · **Account:** qa2-finance (Staff — `dashboard:view`, `payments:view`,
  `priceComparison:view`, deliberately **no** project ownership or membership, exactly as
  designed by the test prompt's own R2 role spec)
- **Steps:** Log in as Finance. Visit `/`, `/payments`, `/suppliers/compare`.
- **Expected:** per the prompt's own stated permission model ("Project reach — orthogonal to
  both... membership grants visibility only and never implies any module permission" — implying
  the reverse should also hold: module permissions shouldn't *require* project reach either,
  especially for company-wide rollup pages), and per the Payments page's own on-screen copy
  ("Every supplier and sub-contractor's outstanding balance, grouped across every project they're
  linked to") — Finance should see real, company-wide money data: Alpha's LKR 1,500,000 received,
  LKR 97,500 expense with LKR 50,000 paid, etc. — everything the Admin saw in J1.
- **Actual:** **Every figure is zero.** Dashboard: "OVERALL PAYMENTS RECEIVED LKR 0 · OVERALL
  OUTSTANDING LKR 0 · OVERALL ROI +LKR 0." Payments page: "TOTAL OUTSTANDING LKR 0.00 · No
  supplier expenses logged yet." This is not a display bug — confirmed by reading the source:
  `src/app/api/dashboard/route.ts`, `src/app/api/payments/route.ts`, and
  `src/app/api/suppliers/price-comparison/route.ts` **all** layer
  `projectAccessClause(session, 'p.id', 'p.ownerId')` on top of their
  `requirePermission('dashboard'|'payments'|'priceComparison', 'view')` check. `dashboard/route.ts`
  even has an explicit code comment confirming this is deliberate: *"a Staff dashboard only ever
  reflects projects they own OR are an assigned ProjectMember on."*
- **Impact:** there is **no way**, in the current design, for an Admin to grant a Staff user
  company-wide financial visibility (dashboard totals, vendor payment status, price comparison)
  without *also* making them an owner or member of literally every project in the company. The
  three modules whose entire purpose is cross-project financial rollup are the ones most tightly
  bound to per-project reach — the opposite of what their own descriptions promise. A real
  "Finance" hire at Vega, set up exactly the way the RBAC UI suggests (check the three view boxes,
  done), would open the app to a wall of zeros and reasonably conclude the product is broken or
  their account is misconfigured, when actually every permission was granted correctly.
- **Location:** `src/app/api/dashboard/route.ts:24-52`,
  `src/app/api/payments/route.ts:36-67`, `src/app/api/suppliers/price-comparison/route.ts:26-39`.
- **Relationship to known-open items:** distinct from **F-04-02** ("three route families ignore
  the URL's project id") — this is the inverse failure mode (over-scoping rather than
  under-scoping) and a different set of routes. Not previously documented under this framing;
  filing as new.
- **Suggested fix (describe only):** decide the intended model and make it explicit — either (a)
  `dashboard:view`/`payments:view`/`priceComparison:view` should grant company-wide visibility on
  their own, with `projectAccessClause` only applied for Staff who lack the module permission
  entirely (fallback to project-reach-only visibility), or (b) if project-scoped financial
  visibility is intentional, the Roles UI and these pages' own copy should say so explicitly,
  and give Admins a "company-wide" toggle/grant so a real Finance hire is actually usable.

### Confirmed correct: payment recording is cleanly refused, exactly as documented
Attempted `POST /api/projects/{alphaId}/expenses/{expenseId}/payments` as Finance (who has
`payments:view` but not `projects:edit`, and recording a payment is gated by `projects`, per the
prompt's own design note). Got `403 {"error":"Missing permission: projects:edit"}` — clean,
specific, matches the documented design exactly. No UI path to attempt this even existed (project
pages are fully denied), so this was tested directly against the API as the prompt allows.

**J4 verdict:** done. 0 crashes. 1 new **High** finding (E-06 — Finance role's core purpose is
unusable as designed). Payment-recording refusal behaved exactly as documented.

## J5 — Zero-permission baseline (qa2-zero-perm@vegahomes.lk)

Authenticated successfully (Staff account, zero roles, zero direct permissions). Sidebar nav
shows literally nothing but the brand header — no section links at all, correctly reflecting zero
permissions. Walked all 15 reachable-without-fixtures pages by direct URL:
`/`, `/projects`, `/projects/{alphaId}`, `/activities`, `/basic-price`, `/basic-rate`,
`/payments`, `/suppliers`, `/suppliers/compare`, `/users`, `/roles`, `/settings`,
`/settings/company-profile`, `/settings/field-options`, `/settings/project-access`.

**Result: clean across the board.** Every page rendered a designed state — either the same clean
"You don't have access to this page / Ask an admin to assign you a role with access to this
section" panel (RBAC-gated pages), or the E-05 pattern already documented in J3 (admin pages
render their static shell with empty data, same root cause, not re-filed here). Zero blank white
pages, zero infinite spinners, zero raw stack traces, zero uncaught page errors. Only console
noise was the expected 403s from the underlying API calls each denied page's data-fetch made —
correct, not a bug.

**First-login experience, worth noting positively:** login itself is warm and unconfused — a
"Welcome back, QA2!" toast, then a calm, well-designed empty dashboard state with a clear call to
action. This is exactly what a brand-new employee's first day should look like before an admin
configures their access — screenshot-verified. Recommend calling this out explicitly in the
"Tested and clean" section of the final report; a bad first-run experience for a new hire is
exactly the kind of thing that erodes client confidence even though it's "just" an edge case.

**J5 verdict:** done. 0 crashes. 0 new findings (E-05's pattern recurs here but isn't re-filed).
The single most productive probe in the codebase, per the prompt's own framing, came back clean.

## J6 — Lifecycle, concurrency, and interruption

### Permission revoked mid-session — confirmed correct
Revoked `projects:create` from the live QA2 Estimator role while the Estimator had an open,
unreloaded session (via a clean direct API PATCH — see note below about the UI path).
The Estimator's very next request (`POST /api/projects`, same session, zero reload) was
immediately refused: `403 {"error":"Missing permission: projects:create"}`. Confirms the
documented design (`src/proxy.ts` comment: "roles are re-read per request, not trusted from the
JWT") is actually true, not just claimed. Restored the permission afterward.

*(Process note, not a product finding: my first two attempts at this test wrongly concluded the
revocation "didn't take effect" — both were my own test-script bugs, not app bugs. First: the
role-edit UI's PATCH request hit a genuine one-off server exception
(`SyntaxError: Unexpected end of JSON input`, logged server-side) that the client correctly
surfaced as a save failure — I just didn't check for it and wrongly assumed success. That
exception is a fresh, live instance of the already-known **X-02** pattern (raw exception instead
of a clean error) — noting under Known Findings below. Second: my direct-API repro script assumed
`GET /api/roles` returns `permissions` as `{module, action}` objects; it actually returns plain
strings like `"projects:create"`, so my "revoke" filter was a no-op both times. Once fixed, the
revocation and enforcement both worked exactly as designed.)*

### Deactivated mid-session — confirmed correct
Deactivated the Estimator's account (`status: 'Inactive'`) via Admin while their session was
still open. Next request (same session, no reload): **401**. Next page navigation: redirected to
`/login`. Re-login attempt: cleanly refused with **"This account has been deactivated. Contact an
admin for access."** — specific, correct, not a generic error. Reactivated afterward.

### E-07 — Concurrent Basic Price promote surfaces a raw 500 instead of a clean conflict response (but does NOT double-promote)
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Error handling (data integrity is fine — see below)
- **Journey:** J6 · **Account:** Admin
- **Steps:** Created a Basic Price draft, then fired two `POST .../promote` requests at the
  **same draft id concurrently** (`Promise.all`, no artificial delay) to simulate a genuine
  double-submit race, bypassing the UI's own dialog-close protection.
- **Result:** Request 1 → `200`, correctly promoted. Request 2 → **`500
  {"error":"Internal server error"}`**. Server log shows the real cause:
  `error: duplicate key value violates unique constraint "base_items_promotedFromId_key"`.
  **Only one `base_items` row was created** (verified directly in the DB) — no double-promotion
  occurred.
- **What this means:** the AUTHZ-VULN-01/02 double-promotion vulnerability class described in
  `doc/test/security/` is **not reproducible on this build** — a real DB-level unique constraint
  on `base_items.promotedFromId` is what actually stops it, which is a robust, race-proof
  guarantee (unlike the earlier application-level `status !== 'draft'` check alone, which has a
  TOCTOU gap the constraint closes). This is good news, but the *way* it's stopped — an unhandled
  exception hitting the shared `apiRoute` catch-all — means the losing request in a real race gets
  an opaque "Internal server error" instead of the same clean
  `400 {"error":"This draft has already been promoted"}` the route already returns for the
  non-race case (re-promoting an already-promoted draft sequentially).
- **Impact:** low — no data integrity risk, just a confusing error message for the rare case of a
  genuine double-click race actually reaching the server twice.
- **Location:** `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts` — the
  `db.batch([...])` call isn't wrapped to catch a unique-constraint violation specifically.
- **Suggested fix (describe only):** catch the constraint violation (or re-check `status` inside
  the same transaction before the insert) and return the same clean 400 the sequential case uses.

### Double-submit — UI layer
Rapidly double-clicking the "Confirm" button on the promote confirmation dialog through the
actual UI did **not** produce two network requests — the dialog closes after the first click,
so the UI itself prevents this class of double-submit before it reaches the server. Only the
direct-concurrent-API case above (bypassing the UI) could trigger the race, and even then, no
double-promotion resulted.

### E-08 — Session idle timeout does not actually expire non-"remembered" sessions (updates AUTH-VULN-05)
- **Severity:** High
- **Confidence:** Confirmed (extensively verified — see method below)
- **Class:** Data integrity / Session lifecycle / Security
- **Journey:** J6 · **Account:** qa2-estimator
- **Context:** `src/lib/auth.ts` implements a real, deliberately-engineered idle timeout (backed
  by its own design doc, `doc/test/security/SESSION_IDLE_TIMEOUT_PLAN_2026-09-07.md`):
  `SESSION_ONLY_IDLE_SECONDS = 3600` (1 hour) for a normal login, `REMEMBERED_IDLE_SECONDS =
  259200` (3 days) for a "Remember me" login. `resolveSession()` picks the window via
  `row.remember === 1 ? REMEMBERED_IDLE_SECONDS : SESSION_ONLY_IDLE_SECONDS` and calls
  `isIdleExpired(lastSeenAt, idleWindow, now)`.
- **Steps:** Logged in twice: once with default `remember` (which defaults to `true` in both the
  login form's initial state and the API schema — see the note below), once with an explicit
  `remember: false`. For each, decoded the session cookie's JWT to get the exact session id, then
  directly backdated that row's `lastSeenAt` in Postgres past the *documented* window for that
  session type, and made one authenticated request on the still-open session.
- **Result:**
  - **Remembered session** (`remember=1`), backdated **4 days** (past its 3-day window): next
    request → **401**. Correct.
  - **Non-remembered session** (`remember=0`), backdated **2 hours** (past its 1-hour window):
    next request → **200, still fully authenticated**. **Wrong** — should have been 401.
- **Verification rigor (to rule out a test artifact):** re-ran the non-remembered case three
  times against three different server states — the long-running dev server, a freshly restarted
  process, and a freshly restarted process with `.next/cache` deleted entirely (full Turbopack
  cache wipe) — identical result every time. Confirmed via `extract(epoch from (now() -
  "lastSeenAt"))` queried directly in Postgres that the row really was ~7,200 seconds
  (2 hours) stale by the database's own clock at the moment of the request, and confirmed via
  decoding the actual session cookie's JWT payload that the session id checked in the database
  is the exact same one the live request's cookie carried (no row-mismatch). Traced the full
  code path (`requirePermission` → `requireSession` → `getSession` → `resolveSession` →
  `isIdleExpired`) and found no alternate/bypassing logic — the comparison function itself reads
  as textually correct. Could not pin the exact defect to a single line through static reading
  and without adding instrumentation (out of scope — no source edits per the ground rules); the
  finding is reported on the strength of the reproducible empirical result, not a code diagnosis.
- **Compounding factor:** `remember` defaults to **`true`** in both `src/app/login/page.tsx:35`
  (`useState(true)`) and `src/app/api/auth/login/route.ts:35`
  (`z.boolean().optional().default(true)`) — a user must actively *uncheck* "Remember me" to get
  a non-remembered session. So in practice: (a) most real users get the 3-day window, which
  *does* work correctly, but is a long idle allowance for a construction-management app handling
  contract values and payment records; (b) the one path that's supposed to give a
  security-conscious user (or anyone who deliberately unchecks the box expecting a tighter
  session) the shorter, safer 1-hour window is the specific path that's broken — so choosing the
  more cautious option silently produces *no* effective idle enforcement at all.
- **Relationship to known-open AUTH-VULN-05:** updates rather than simply reconfirms it. The
  original finding ("no session idle timeout") predates this feature's implementation — a real
  mechanism now exists and partially works (the 3-day window is genuinely enforced), so
  "still present, unchanged" would understate what's true; "resolved" would overstate it, since
  the shorter/more meaningful window silently does nothing. Recommend the handover report state
  it exactly this way rather than picking one of the two stock labels.
- **Location:** `src/lib/auth.ts:106-109` (`isIdleExpired`), `:134-160` (`resolveSession`),
  `:32-33` (the two window constants); defaults at `src/app/login/page.tsx:35` and
  `src/app/api/auth/login/route.ts:35`.
- **Suggested fix (describe only):** needs actual runtime debugging (add temporary logging around
  the `remember`/`idleWindow`/`isIdleExpired` values on a real request) to find why the
  non-remembered branch doesn't trigger despite the logic reading correctly — this report
  deliberately stops short of that since it requires source changes. Separately, worth reviewing
  whether "Remember me" should default to unchecked, as most login forms do, given it currently
  steers every user toward the (correctly-enforced but long) 3-day idle window by default.

### E-01 addendum (found during J6): network interruption turns the same defect into an actual uncaught exception
Simulated a dropped connection (`route.abort('internetdisconnected')`) on `POST /api/activities`
mid-save. Result: the dialog silently stayed open with no error toast and no indication anything
went wrong — but the console shows a genuine **unhandled exception**:
`TypeError: Failed to fetch` at `CatalogProvider.useCallback[addActivity]` →
`submitAdd`, with no `try`/`catch` anywhere in that call chain. This is the exact same root cause
as E-01 (`await fetch(...)` with no error handling) — a genuine network failure makes `fetch()`
itself *reject* rather than just return a non-ok `Response`, so these call sites don't even reach
a `res.ok` check, they throw, uncaught. The prompt's own crash catalogue lists "Unhandled promise
rejection" as a console-visible crash class, rated at minimum High severity regardless of trigger
obscurity — this is a concrete, reproducible instance of exactly that, and it confirms E-01's
severity rather than being a separate root cause. (The app did recover cleanly once the network
route was restored — retrying the same action worked normally on the next attempt.)

### Two users, one record — confirmed clean
Fired two concurrent `PATCH` requests at the same expense (amounts 111,111 vs 222,222) from two
separate authenticated sessions. Both returned 200; the final stored value was cleanly one of the
two (last-write-wins), `outstanding` recalculated correctly against it (111,111 − 50,000 =
61,111). No corruption, no `NaN`, no partial merge, no crash — an explicable outcome, which is
the bar the prompt sets for this scenario.

**J6 verdict:** done. 0 crashes in the product itself (one confirmed uncaught exception under
simulated network failure, which is the E-01 defect surfacing in its worst form — documented as
an addendum to E-01, not a separate crash count). 2 new findings this journey: **E-07** (Low —
concurrent promote race surfaces a raw 500 but does not corrupt data; AUTHZ-VULN-01/02
double-promotion could not be reproduced, protected by a real DB constraint) and **E-08** (High —
non-remembered sessions' 1-hour idle timeout does not actually expire, updating AUTH-VULN-05).
Every session-lifecycle path tested (permission revoked, deactivated, password changed, logged
out) correctly invalidated the live session on its very next request, with no reload needed.
Interruption (Escape/backdrop/Back/refresh) and concurrent-edit scenarios all behaved cleanly.

## J7 — Cross-cutting sweep

- **Console hygiene:** zero uncaught exceptions, zero unhandled rejections, zero hydration
  mismatches, zero key warnings across all 15 pages walked as Admin (the same 403-noise and
  cosmetic `scroll-behavior` warning already noted in J0 excluded as known/benign). Clean.
- **Responsive (1920 / 1366 / 390px):** no horizontal overflow on the project detail page (the
  densest page in the app) at any breakpoint. Mobile view shows a clean skeleton-loading state
  with no layout breakage.
- **Dark mode:** legible throughout the dashboard — good contrast, no invisible text,
  screenshot-verified. (Also re-surfaces the company-wide ROI figure at an even more extreme
  **36,741.3%** now that more test projects exist — 5th reproduction of the known F-02-01
  pattern in this exercise, not filed again.)

### E-09 — Active project tab does not survive a page refresh
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** UX / Persistence
- **Steps:** On `/projects/{id}`, switch to the "Expenses" tab, then press F5 / reload.
- **Expected:** per the prompt's own persistence check ("the page restores its own state — active
  tab, filters, scroll"), the Expenses tab should still be selected.
- **Actual:** reload resets to the default "BSR" tab. `aria-selected` on the Expenses tab reads
  `false` after refresh.
- **Impact:** minor — no data loss, just has to re-click the tab. Common pattern (URL query param
  or hash for tab state) not currently used here.
- **Suggested fix (describe only):** reflect the active tab in the URL (e.g. `?tab=expenses`).

**J7 verdict:** done. 0 crashes. 1 new Low finding (E-09). Everything else in this sweep came
back clean.
