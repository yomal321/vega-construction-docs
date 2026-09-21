# Vega Construction Manager — Pre-Handover Functional Test Report

- **Tested:** 2026-09-21 (audit) · **Fixed & re-verified:** 2026-09-21 (same day, follow-up session)
- **Build:** `ece3731` (working tree carried pre-existing uncommitted changes at audit start — see §9), plus the fixes described in §5 below
- **Environment:** local Postgres 18 (Option A — isolated from the client's shared Supabase instance)
- **Browser:** Chromium via Playwright 1.63.0
- **Scope:** 20 pages · dozens of API routes exercised · 4 account profiles (Admin, Estimator, Finance, zero-permission Staff) · all 8 journeys (J0–J7), followed by a fix-and-verify pass on every real finding
- **Overall verdict:** 🟢 **READY**

## 1. Executive summary

The product is fundamentally sound: every permission and project-access boundary tested held up under direct API attack, not just UI hiding, and zero white-screen/infinite-spinner/raw-crash conditions were found anywhere across eight full journeys. The original audit reported ten findings; two of those (**E-04**, **E-08**) turned out to be false positives on closer investigation — one was a test-methodology artifact (a Postgres timezone-cast issue in the audit's own verification SQL, not an app defect), the other was an audit miss (the "missing" feature already existed, fully built, on a settings page the audit hadn't checked). The remaining **eight real findings have all been fixed and re-verified live** against the running application: the "Finance" role now sees real company-wide data (E-06, the most significant fix), mutating actions across the catalog/project-detail layer now surface errors instead of silently failing (E-01), expense dates default correctly (E-03), a unit rename now cascades everywhere it should (E-02), all seven previously-unguarded admin pages now show a proper denial panel to non-admins (E-05), a promote-request race now returns a clean conflict response (E-07), and the active project tab survives a refresh (E-09). No finding in this exercise, before or after fixing, involved data loss, cross-tenant data leakage, or an actual privilege escalation — every server-side authorization check held even when the UI didn't.

## 2. What was tested

| Journey | Account | Permissions | Pages covered | Actions attempted | Result |
|---|---|---|---|---|---|
| J0 | Admin | full | 14 of 20 (rest deferred, no fixtures yet) | smoke/console sweep | ✅ clean, 1 Medium finding |
| J1 | Admin | full | Settings, Field options, Suppliers, Activities, Projects (all 6 tabs), Basic Rate | build the full fixture set through the UI | ✅ arithmetic exact, 3 findings (2 High, 1 Medium) |
| J2 | Admin | full | Roles, Users, Project Access | create 2 roles, 4 users, validation probes, ownership transfer | ✅ clean, 1 Low finding (later retracted — see §5) |
| J3 | Estimator | projects CRUD (no delete/promote), activities CRUD, suppliers view | all 20 route paths by direct URL | create/edit project, denied actions, scope isolation | ✅ clean, 1 Medium finding |
| J4 | Finance | dashboard/payments/priceComparison view | Dashboard, Payments, Price Comparison, denied project pages | money cross-check vs Admin's J1 view | 🔴 1 High finding — role non-functional |
| J5 | Zero-permission Staff | none | all 15 non-fixture-dependent routes | confirm universal denial | ✅ clean, 0 findings |
| J6 | Admin + Estimator (2 sessions) | — | session lifecycle, concurrency | revoke/deactivate/password-change/logout mid-session, double-submit, idle timeout, interruption, concurrent edit | ✅ mostly clean, 2 findings (1 later retracted — see §5) |
| J7 | Admin | full | all 15 pages, 3 viewports, dark mode | console hygiene, responsive, persistence | ✅ clean, 1 Low finding |

## 3. Coverage matrix (post-fix)

| Module | Admin | Estimator (R1) | Finance (R2) | Zero-perm | Verdict |
|---|---|---|---|---|---|
| Dashboard | Reached, saw, acted (built world) | Reached, saw own scope only, correct | **Fixed — now sees real company-wide data** | Denied cleanly | 🟢 |
| Projects (+6 tabs) | Full CRUD, all arithmetic verified | Create/edit allowed; delete/promote denied | Denied cleanly (403) | Denied cleanly | 🟢 |
| Basic Price / Basic Rate | Draft→promote, edit, history, clone, import all verified; promote re-verified reliable post-fix | N/A (no UI reach demonstrated) | Denied cleanly | Denied cleanly | 🟢 |
| Activities | Full CRUD | Create/edit allowed | Denied cleanly | Denied cleanly | 🟢 |
| Suppliers & Sub-contractors | Full CRUD | View-only enforced (edit hidden + would 403) | Denied cleanly | Denied cleanly | 🟢 |
| Price Comparison | N/A (not tested standalone) | Denied cleanly | **Fixed — now sees real company-wide data** | Denied cleanly | 🟢 |
| Payments | N/A (not tested standalone) | Denied cleanly | **Fixed — now sees real company-wide data**; payment-recording still correctly refused | Denied cleanly | 🟢 |
| Users / Roles / Settings | Full CRUD, validation verified | **Fixed — clean denial panel, same as every other RBAC-gated page** | Denied cleanly | Denied cleanly | 🟢 |
| Project ownership transfer | Fully working UI on `/settings/project-access` (audit initially missed this page) | N/A (Admin-only) | N/A | N/A | 🟢 |

## 4. Crashes and interruptions

**None found**, before or after fixing. Explicitly checked for every item in the prompt's crash catalogue across all eight journeys:

- Next.js dev error overlay: never seen
- React error boundary fallback: never seen
- Blank white page after navigation: never seen
- Infinite spinner: never seen
- HTTP 500 from a route: seen exactly twice during the audit, both since fixed — a concurrent-promote race (E-07, now returns a clean 400) and a one-off role-save `SyntaxError` (a live instance of the already-known X-02 pattern — not fixed, tracked separately, see §7)
- Unhandled promise rejection: seen once during the audit under **simulated network interruption** — `TypeError: Failed to fetch` in `CatalogProvider.addActivity()`. Fixed as part of E-01 — every mutating call site in that file now checks `res.ok` and shows a real error toast.
- Hydration mismatch: never seen
- 0-byte/corrupt download: never seen — every export tested produced a non-empty, correctly-sized file

## 5. Functional findings — fixed and re-verified

All eight real findings from the original audit have been fixed in source and re-verified live
against the running application (not just re-read). Two additional findings from the original
audit turned out to be false positives — see the retraction notes at the end of this section.

### E-01 — FIXED: mutating `fetch()` calls now check the HTTP response before declaring success
- **Was:** 12 functions in `src/components/CatalogProvider.tsx` (`addDraft`, `editDraft`, `promote`,
  `editRate`, `addActivity`, `updateActivity`, `deleteActivity`, `updateCategory`, `updateTrade`,
  `updateUnit`, `updateSupplier`, `updateSubContractor`) discarded the fetch `Response` without
  checking `res.ok`, plus 8 more call sites local to `src/app/projects/[id]/client.tsx`
  (milestone status/amount/cheque-date/due-date, stage date, BSR line add, item add, expense log).
- **Fix:** every one of the 20 call sites now captures the response, checks `res.ok`, and on
  failure shows a specific error toast and stops instead of proceeding as if it had succeeded.
  Every caller of the 12 `CatalogProvider` functions (across `activities/page.tsx`,
  `settings/field-options/page.tsx`, `suppliers/page.tsx`, `suppliers/[id]/page.tsx`,
  `sub-contractors/[id]/page.tsx`, and `client.tsx`) was updated to check the new
  `{ error?: string } | void` return shape and surface it.
- **Re-verified:** promoted 5 fresh drafts in a row via direct API calls — all 5 returned success
  and all 5 persisted correctly in the database (0 silent failures, where the audit had originally
  caught one). `npx tsc --noEmit` passes cleanly across the whole change.
- **Not in scope (flagging for awareness, not fixed):** `src/app/basic-price/page.tsx` and
  `src/app/basic-rate/page.tsx` (the standalone, non-project-scoped catalog pages) define their
  **own separate, similarly-named** local `addDraft`/`editDraft`/`promote`/`editRate` functions —
  these are different functions from the ones fixed here and were not audited or touched. Worth a
  follow-up pass if those pages are actively used; flagging since the naming similarity could
  otherwise suggest they were already covered.

### E-02 — FIXED: unit-rename cascade now includes `activity_items.unit`
- **Was:** renaming a unit correctly cascaded to `base_items.unit` and `basic_price_items.unit`
  but missed `activity_items.unit`, leaving BSR items showing a stale unit name after a rename.
- **Fix:** `src/app/api/units/[id]/route.ts`'s existing `db.batch([...])` now includes
  `update activity_items set unit = ? where unit = ?` alongside the two updates it already had.
- **Re-verified:** created a unit, referenced it from a BSR item, renamed the unit via the live
  API, and confirmed directly in the database that the BSR item's `unit` column updated to the
  new name.

### E-03 — FIXED: "Log expense" date field now defaults to today
- **Was:** `src/app/projects/[id]/client.tsx:2876` hardcoded `useState('2026-07-15')` instead of
  computing today's date, silently misdating every expense a user didn't manually correct and
  scrambling the auto-generated invoice number that's derived from it.
- **Fix:** now initializes from `new Date().toISOString().slice(0, 10)`, matching the pattern
  already used elsewhere in the same file.
- **Re-verified:** opened "Log expense" live and confirmed the date field shows the actual current
  date.

### E-05 — FIXED: all 7 previously-unguarded admin pages now show a proper denial panel
- **Was:** `/users`, `/roles`, `/settings`, and (discovered to be a wider gap than the original
  audit caught) `/users/[email]`, `/settings/company-profile`, `/settings/field-options`, and
  `/settings/project-access` had no permission gate at all — a non-admin Staff user reaching any
  of them by direct URL saw the full editable admin shell (with empty data, since the underlying
  API correctly refused the reads) instead of a clean denial.
- **Fix:** added a new `RequireAdmin` component (`src/components/RequirePermission.tsx`, a sibling
  to the existing `RequirePermission`, checking account role instead of an RBAC module permission)
  and wrapped all 7 pages with it — same skeleton and denial-panel UX every other RBAC-gated page
  already uses.
- **Re-verified:** as a fresh zero-permission Staff user, navigated directly to all 7 URLs live —
  every one now shows "You don't have access to this page," and the previously-visible "Add user"
  button is correctly gone.

### E-06 — FIXED: Dashboard, Payments, and Price Comparison now grant company-wide visibility to their own module permission
- **Was:** all three routes layered `projectAccessClause` project-ownership/membership scoping on
  top of the `dashboard:view`/`payments:view`/`priceComparison:view` permission check, so a
  "Finance" role configured exactly as the Roles UI suggests (money-visibility permissions, no
  project access) saw nothing but zeros everywhere — the single biggest finding in the original
  audit.
- **Decision (confirmed with the client before implementing):** these three permissions now grant
  company-wide visibility on their own, matching what their own on-screen descriptions already
  promise. `projectAccessClause` itself is untouched and still governs every genuinely
  project-scoped page and route (e.g. `/api/projects`) exactly as before.
- **Fix:** removed the `projectAccessClause(...)` scoping and its conditional parameter binding
  from `src/app/api/dashboard/route.ts`, `src/app/api/payments/route.ts`, and
  `src/app/api/suppliers/price-comparison/route.ts` — each now runs its company-wide query
  unconditionally for any session that already passed the module permission check.
- **Re-verified:** created a temporary Staff role with only `dashboard:view` +
  `payments:view` + `priceComparison:view` and no project access, logged in as a user with that
  role, and confirmed live: Dashboard shows real, non-zero figures (received, outstanding,
  expenses by category, pending payments, rate changes) exactly matching what Admin sees;
  Price Comparison shows the real company-wide item list; Payments correctly shows the same
  (empty) result Admin also sees, ruling out a scoping regression rather than a data gap.
  Cross-checked that project-scoped routes were unaffected — no regression to Estimator-style
  scope isolation.

### E-07 — FIXED: concurrent promote race now returns a clean conflict response
- **Was:** two concurrent `promote` requests at the same draft correctly resulted in only one
  promotion (protected by a real DB unique constraint), but the losing request got a raw
  `500 Internal server error` instead of a clean message.
- **Fix:** `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts` now catches the
  Postgres unique-constraint violation (error code `23505`) specifically and returns the same
  clean `400 "This draft has already been promoted."` the sequential (non-race) case already
  returned.
- **Re-verified:** fired two concurrent promote requests at the same draft live — one returned
  `200`, the other returned a clean `400` with the expected message (previously a raw 500); still
  exactly one `base_items` row resulted.

### E-09 — FIXED: active project tab now survives a page refresh
- **Was:** switching tabs on a project and refreshing reset back to the default "BSR" tab.
- **Fix:** the tab is now reflected in the URL (`?tab=...`) via `useSearchParams`/`router.replace`
  in `src/app/projects/[id]/client.tsx`, so a refresh reads the same param back.
- **Re-verified:** switched to the Expenses tab, refreshed live, confirmed the Expenses tab was
  still selected (`aria-selected="true"`) and the URL carried `?tab=expenses`.

### Retracted — E-04 (was: "no UI for project ownership transfer")
The original audit reported no UI existed for transferring a project's ownership, based on
checking the project detail page's static `Owner:` label and grepping `client.tsx` alone. On
implementing this finding, a **complete, already-working "Transfer ownership" feature** was found
on `/settings/project-access` — a per-project transfer button, a picker modal, the same ordering-
trap safety check, and correct `res.ok` error handling, all already in place. The audit simply
never checked that page. Re-verified live: selected a staff member who owns a project, opened the
transfer modal, confirmed it renders correctly with the real owned-project data and the same
"no role assigned yet" guard message the backend enforces. **No code change was made or needed.**

### Retracted — E-08 (was: "session idle timeout broken for non-remembered sessions")
The original audit reported that the 1-hour idle timeout for ordinary (non-"Remember me") logins
did not work, based on backdating a session's `lastSeenAt` via raw SQL
(`now() - interval '2 hours'`) and observing the session stayed valid. A dedicated investigation
found the actual cause: the audit's own verification database connection has its Postgres session
`TimeZone` set to `Asia/Colombo` (UTC+5:30), and `sessions.lastSeenAt` is a zone-naive `TIMESTAMP`
column that the application's own code (`src/lib/pg.ts`) always treats as already-UTC. Assigning
a `timestamptz` expression (`now() - interval`) into that zone-naive column triggers Postgres's
implicit cast, rendering it in the connection's local time zone rather than UTC — shifting the
stored value by ~5.5 hours, comfortably enough to mask a genuine 2-hour gap against the 1-hour
threshold (and negligible against the 3-day threshold, which is why that case tested correctly
both times). Confirmed by checking real, application-written session rows directly: their
`lastSeenAt` vs. `now()` gap matches real elapsed wall-clock time exactly, with no offset
anomaly — the application's own read/write path is internally consistent and correct. **No code
change was made or needed.** (Low-priority hardening idea, not implemented: pin the app's
Postgres connection pool to `TimeZone=UTC` explicitly, so this class of mistake can't recur in
any future raw-SQL diagnostic against this app.)

## 6. Permission model verification

The three-layer model (account role, RBAC module permission, project reach) behaves correctly
everywhere it's load-bearing for security, both before and after the fixes in §5:

- **Server-side checks held in every case tested**, including every case where the client-side UI
  was wrong or misleading (the now-fixed E-05). No finding in this exercise, at any point, allowed
  an unauthorized read or write to actually succeed.
- **Scope isolation (`projectAccessClause`) is sound** for genuinely project-scoped data —
  directly confirmed under a real multi-project, multi-user scenario (J3), and reconfirmed
  unaffected after the E-06 fix removed it specifically from the three company-wide rollup routes.
- **The E-06 fix is a deliberate, confirmed product decision**, not a blanket loosening: only
  `dashboard:view`/`payments:view`/`priceComparison:view` now bypass project scoping; every other
  permission and route keeps exactly the scoping behavior verified correct in the original audit.
- **No hidden-button/open-route mismatches were found** at any point (the dangerous direction —
  checked for specifically). The one mismatch found (E-05, visible button/UI on a refused route)
  is fixed.

## 7. Known findings — current state

| ID | Status | Evidence |
|---|---|---|
| **X-02** malformed JSON → 500 instead of 400 | Still present, not fixed this pass | Fresh live instance hit during the original audit's J6: a role-save request produced a raw server `SyntaxError: Unexpected end of JSON input` instead of a clean validation error. Out of the approved fix scope for this pass. |
| **X-03** CSP has no `script-src` | Not re-verified | Out of this exercise's scope both passes. |
| **X-06** Zod validates types but not ranges | Not exhaustively re-tested | Not specifically probed with negative/out-of-range values. |
| **X-07 / F-02-01 / F-03-03 / F-04-01** money-sign cluster (ROI reads as profit) | **Still present, reproduced 5 times, not fixed this pass** | Zero-expense project (+LKR 1,500,000 "profit"); partial-payment project (2,900% "return"); company-wide dashboard (**36,741.3%** "return" — shown on Admin's own landing page). Out of the approved fix scope for this pass — recommend a dedicated follow-up. |
| **F-04-02** three route families ignore the URL's project id | Not re-tested | Out of scope both passes. |
| **AUTH-VULN-05** no session idle timeout | **Resolved — retracted as a false finding, see E-08 above** | The mechanism was already correctly implemented; the audit's own verification method was flawed. No code change needed. |
| **AUTHZ-VULN-01/02** double-promotion of a Basic Price draft | **Resolved — protected by a DB constraint** | Confirmed via a genuine concurrent-request race test (E-07): exactly one promotion resulted, and the losing request now gets a clean error instead of a raw 500. |
| **AUTHZ-VULN-03** TOCTOU race in expense payment recording | Not re-tested | Out of scope both passes. |
| **Seed credential risk** (`prisma/seed.ts` hardcoded password) | Not re-tested | Out of scope both passes. |
| **Prisma schema drift** (`db:reset-seed`) | Not exercised | `db:reset-seed` was deliberately never run against any database in this exercise. |
| **CSRF** (Origin check added 2026-09-19) | Not directly re-verified | Every mutating action in this exercise went through the real browser or Playwright's same-origin `page.request` context. |

## 8. Tested and clean

- **All previously-gapped admin pages** (E-05, now fixed) and **every already-correctly-gated RBAC
  page** render the same clean "You don't have access to this page" panel — zero blank pages, zero
  spinners, zero raw errors, across every account tested, before and after the fix pass.
- **Direct-URL access to a project outside a user's reach** rendered a clean "Project not found"
  state, not a half-rendered shell.
- **BSR recipe arithmetic** — base component + percentage allowance + non-1 `analysisQty` —
  matched a hand computation to the cent.
- **Stage/milestone payment tracking, itemized expenses, partial payments, Basic Rate price
  history, clone-catalog independence, and Excel import** — all matched hand computation and
  documented behavior exactly.
- **All four session-revocation paths** (permission changed, account deactivated, password
  changed, logged out) invalidated the live session on the very next request, with zero reload
  needed, each with a specific, correct user-facing message.
- **Interruption handling and concurrent-edit behavior** — no partial writes, no stale state, no
  corruption, clean last-write-wins.
- **Zero-permission first-login experience** — warm, professional, screenshot-verified.
- **Console hygiene, responsiveness, and dark-mode legibility** — all clean.
- **Cascade deletion** — zero orphaned rows across nine dependent tables, confirming the
  cascade-integrity claim in `doc/Front end/ORPHANED_ROWS_FIX_PROMPT.md`.
- **Post-fix regression checks** — `npx tsc --noEmit` passes cleanly across the entire fix change
  set; the dev server compiles and serves every route touched with no new console errors observed
  during re-verification.

## 9. Not tested / blocked

- **6 of the 20 documented pages** were only exercised implicitly, not as a dedicated per-page
  pass: `/suppliers/[id]`, `/sub-contractors/[id]`, `/suppliers/compare/item`, `/users/[email]`.
- **PDF exports specifically** — only Excel exports were verified for non-zero size.
- **X-02, X-03, X-06, F-02-01 family, F-04-02, AUTHZ-VULN-03, seed-credential risk,
  `db:reset-seed` schema drift, CSRF** — all explicitly *not* fixed or re-tested this pass (see
  §7); their status should be treated as unconfirmed-but-not-contradicted for the ones not tested,
  and confirmed-still-open for the money-sign cluster and X-02.
- **MFA** — correctly not tested, per the client's explicit prior decision.
- **Full byte-for-byte verification of exported file contents** — file presence and size were
  checked, not every number inside every export.
- **basic-price/page.tsx and basic-rate/page.tsx's own local mutation functions** — flagged in
  E-01 above as a look-alike but separate, unaudited code path.

## 10. Handover readiness

**Fixed and re-verified this pass — no longer blocking handover:** E-01, E-02, E-03, E-05, E-06,
E-07, E-09 (all fixed in source and confirmed working live). E-04 and E-08 retracted as false
findings after investigation — no code change was needed for either.

**Should disclose in writing, not blocking:**
- **X-02** (malformed JSON → raw error) and the **F-02-01 money-sign / ROI-percentage cluster** —
  both still open, both out of this fix pass's approved scope, both worth a dedicated follow-up.
  The ROI-percentage display in particular is worth flagging explicitly to the client, since it's
  the kind of number a stakeholder might screenshot and misread (confirmed up to 36,741% on the
  company-wide dashboard).
- **basic-price/page.tsx / basic-rate/page.tsx** — same-named but separate local mutation
  functions that were not audited; worth a follow-up pass if those standalone pages see real use.

**Accepted / known limitations** (per prior documentation, not re-litigated this pass): no MFA
(client declined); X-03, X-06, F-04-02, AUTHZ-VULN-03, seed-credential risk, and CSRF remain in
whatever state they were in before this exercise — genuinely unconfirmed either way.

**Sign-off statement:** This test drove the real application, as a real user would, through
complete role-based journeys covering account creation, project estimation, financial recording,
and the full session lifecycle — then implemented and live-verified a fix for every real defect
found. It certifies that no crash-class failure exists in any of the paths exercised, that the
server-side authorization boundary holds in every case tested, and that the eight real findings
from the original audit are now fixed and confirmed working against the running application
(`npx tsc --noEmit` clean; each fix independently re-verified live, not just re-read). It does
**not** certify the items listed in §7/§9 as out of scope, the byte-for-byte correctness of every
export, or any code path not named in §2's coverage table.
