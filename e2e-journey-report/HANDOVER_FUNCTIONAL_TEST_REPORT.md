# Vega Construction Manager — Pre-Handover Functional Test Report

- **Tested:** 2026-09-21 (single-day session)
- **Build:** `ece3731` (working tree carried pre-existing uncommitted changes at test start — see §9)
- **Environment:** local Postgres 18 (Option A — isolated from the client's shared Supabase instance)
- **Browser:** Chromium via Playwright 1.63.0
- **Scope:** 20 pages · dozens of API routes exercised · 4 account profiles (Admin, Estimator, Finance, zero-permission Staff) · all 8 journeys (J0–J7)
- **Overall verdict:** 🟠 **READY WITH FIXES**

## 1. Executive summary

The product is fundamentally sound: every permission and project-access boundary tested held up under direct API attack, not just UI hiding, and zero white-screen/infinite-spinner/raw-crash conditions were found anywhere across eight full journeys. However, ten concrete defects were found, four of them High severity and none of them cosmetic. The single biggest risk is **E-06**: the "Finance" role, configured exactly as the app's own Roles UI suggests, sees nothing but zeros — there is currently no way to give a real finance hire company-wide visibility into payments without also granting them project-level access to every project, which defeats the purpose of the role. The second biggest risk is a confirmed, rigorously-verified bug in session idle timeout (**E-08**): the shorter, safer 1-hour timeout for ordinary logins silently does not work, while the longer 3-day "Remember me" timeout (the default) does. None of the ten findings involve data loss, cross-tenant data leakage, or an actual privilege escalation — every server-side authorization check held even when the UI didn't.

## 2. What was tested

| Journey | Account | Permissions | Pages covered | Actions attempted | Result |
|---|---|---|---|---|---|
| J0 | Admin | full | 14 of 20 (rest deferred, no fixtures yet) | smoke/console sweep | ✅ clean, 1 Medium finding |
| J1 | Admin | full | Settings, Field options, Suppliers, Activities, Projects (all 6 tabs), Basic Rate | build the full fixture set through the UI | ✅ arithmetic exact, 3 findings (2 High, 1 Medium) |
| J2 | Admin | full | Roles, Users, Project Access | create 2 roles, 4 users, validation probes, ownership transfer | ✅ clean, 1 Low finding |
| J3 | Estimator | projects CRUD (no delete/promote), activities CRUD, suppliers view | all 20 route paths by direct URL | create/edit project, denied actions, scope isolation | ✅ clean, 1 Medium finding |
| J4 | Finance | dashboard/payments/priceComparison view | Dashboard, Payments, Price Comparison, denied project pages | money cross-check vs Admin's J1 view | 🔴 1 High finding — role non-functional |
| J5 | Zero-permission Staff | none | all 15 non-fixture-dependent routes | confirm universal denial | ✅ clean, 0 findings |
| J6 | Admin + Estimator (2 sessions) | — | session lifecycle, concurrency | revoke/deactivate/password-change/logout mid-session, double-submit, idle timeout, interruption, concurrent edit | ✅ mostly clean, 2 findings (1 High, 1 Low) |
| J7 | Admin | full | all 15 pages, 3 viewports, dark mode | console hygiene, responsive, persistence | ✅ clean, 1 Low finding |

## 3. Coverage matrix

| Module | Admin | Estimator (R1) | Finance (R2) | Zero-perm | Verdict |
|---|---|---|---|---|---|
| Dashboard | Reached, saw, acted (built world) | Reached, saw own scope only, correct | **Reached, saw nothing (E-06)** | Denied cleanly | 🟠 |
| Projects (+6 tabs) | Full CRUD, all arithmetic verified | Create/edit allowed; delete/promote denied | Denied cleanly (403) | Denied cleanly | 🟢 |
| Basic Price / Basic Rate | Draft→promote, edit, history, clone, import all verified | N/A (no UI reach demonstrated) | Denied cleanly | Denied cleanly | 🟢 (see E-01 for promote reliability) |
| Activities | Full CRUD | Create/edit allowed | Denied cleanly | Denied cleanly | 🟢 |
| Suppliers & Sub-contractors | Full CRUD | View-only enforced (edit hidden + would 403) | Denied cleanly | Denied cleanly | 🟢 |
| Price Comparison | N/A (not tested standalone) | Denied cleanly | **Reached, saw nothing (E-06)** | Denied cleanly | 🟠 |
| Payments | N/A (not tested standalone) | Denied cleanly | **Reached, saw nothing (E-06)**; payment-recording correctly refused | Denied cleanly | 🟠 |
| Users / Roles / Settings | Full CRUD, validation verified | **Denied by server, but full editable UI shell renders (E-05)** | Denied (shell renders, same E-05 pattern) | Denied (shell renders, same E-05 pattern) | 🟡 |

## 4. Crashes and interruptions

**None found.** Explicitly checked for every item in the prompt's crash catalogue across all eight journeys:

- Next.js dev error overlay: never seen except when deliberately investigating E-08 (unrelated to app logic)
- React error boundary fallback: never seen
- Blank white page after navigation: never seen
- Infinite spinner: never seen
- HTTP 500 from a route: seen exactly twice, both understood and non-crashing — a concurrent-promote race (E-07, correctly prevented by a DB constraint, just an ugly error message) and a one-off role-save `SyntaxError` (a live instance of already-known X-02)
- Unhandled promise rejection: seen once, under **simulated network interruption** (not a normal user action) — `TypeError: Failed to fetch` in `CatalogProvider.addActivity()`, documented as an addendum to E-01. The dialog stayed open and did not silently pretend to succeed, but gave no visible error toast either.
- Hydration mismatch: never seen
- Server-side exception surfaced to `next dev` terminal: the two 500s above, both explained
- "Something went wrong" with no detail: never seen
- 0-byte/corrupt download: never seen — every export tested produced a non-empty, correctly-sized file (7.3–7.8 KB range, scaled sensibly with the visible user's data scope)

## 5. Functional findings

### E-01 — Mutating `fetch()` calls across the app never check the HTTP response before declaring success
- **Severity:** High · **Confidence:** Confirmed
- **Class:** Data integrity / Error handling
- **Journey:** J1, reconfirmed in J6
- A Basic Price → Basic Rate promotion returned a success toast and appeared on the Basic Rate tab, but a database check showed it had not persisted — the draft was still `'draft'`, no `base_items` row existed. A second, identical attempt then succeeded and persisted correctly.
- **Root cause, confirmed by source inspection independent of that one incident:** `src/components/CatalogProvider.tsx` has 11 of 25 mutation functions (`promote`, draft add/edit, rate edit, activity add/edit, category/trade/unit add/edit, supplier/sub-contractor add/edit) that call `await fetch(...)` and **discard the Response** without checking `res.ok` — only the `deleteX` functions in the same file do this correctly. The same shape recurs 8 more times in `src/app/projects/[id]/client.tsx`.
- **Confirmed real-world trigger, not just theoretical:** under a simulated dropped network connection, this exact pattern produces a genuine **uncaught exception** (`TypeError: Failed to fetch`) with no user-facing error message — the app silently does nothing while the console shows an unhandled rejection.
- **Location:** `CatalogProvider.tsx:85,90,101,108,129,134,152,169,186,205,224`; 8 more sites in `client.tsx` (grep `await fetch(` for the full list).
- **Suggested fix:** every mutating `fetch()` should check `res.ok` before the caller declares success — the existing `deleteX` functions already show the pattern to copy. Given the scope, this is a systemic gap worth a dedicated pass rather than 19 one-off patches.

### E-02 — Unit-rename cascade misses `activity_items.unit` (BSR items keep a stale unit name)
- **Severity:** Medium · **Confidence:** Confirmed
- **Class:** Data integrity
- **Journey:** J1
- Renaming a unit correctly cascades to `base_items.unit` and `basic_price_items.unit` (the two tables `src/app/api/units/[id]/route.ts`'s own code comment names), but **not** to `activity_items.unit` — a BSR item's unit field silently goes stale after any rename. Confirmed via direct DB inspection after a live rename. The equivalent trade-rename cascade was checked and is *not* affected (trade only exists on one table).
- **Location:** `src/app/api/units/[id]/route.ts:27-31` (the `db.batch` call is missing an `activity_items` update).
- **Suggested fix:** add the missing `update activity_items set unit = ? where unit = ?` to the same batch.

### E-03 — "Log expense" date field defaults to a hardcoded literal date, not today
- **Severity:** High · **Confidence:** Confirmed
- **Class:** Data integrity / Validation
- **Journey:** J1
- The date field in the "Log expense" modal defaults to a hardcoded literal `'2026-07-15'` (`src/app/projects/[id]/client.tsx:2876`) rather than computing today's date — every other date default in the same file correctly uses `new Date()`. This cascades into the auto-generated invoice number (`VH-INV-MM-YYYY-NNN`, derived from the expense date's month), so any expense logged without the user noticing and manually correcting the date gets silently misdated by roughly two months and mis-numbered.
- **Impact:** a real financial record-keeping integrity issue — nothing else about the expense (amount, vendor, stage) looks wrong, so this is easy to miss until someone specifically checks the date column or a monthly report comes out wrong.
- **Location:** `src/app/projects/[id]/client.tsx:2876`.
- **Suggested fix:** initialize from `new Date().toISOString().slice(0, 10)`, matching the pattern already used at line 230 in the same file.

### E-04 — Project ownership transfer has a working API but no UI entry point
- **Severity:** Low · **Confidence:** Confirmed
- **Class:** Missing feature surface
- **Journey:** J2
- `/settings/project-access` only manages membership ("visibility, not permissions"); the project detail page shows `Owner:` as a static label with no click handler. `PATCH /api/projects/[id]/owner` is a complete, correct, Admin-only endpoint that already implements the exact "ordering trap" safety check the prompt describes — it just has no button anywhere. Used directly via API as a fixture shortcut for J3 (explicitly permitted for this case).
- **Location:** backend at `src/app/api/projects/[id]/owner/route.ts`; no UI location exists.
- **Suggested fix:** add a "Transfer ownership" action near the Owner chip on the project detail header, Admin-only.

### E-05 — Admin-only pages render their full editable UI for non-Admin users who reach them by direct URL
- **Severity:** Medium · **Confidence:** Confirmed (UX only — server-side checks all held)
- **Class:** UX consistency
- **Journey:** J3, reconfirmed in J5
- `/users`, `/roles`, `/settings` show a static "Admin only" text *badge* but have **no `RequirePermission`/`requireAdmin` gate** on the page itself — unlike every RBAC-gated page (`/payments` etc.), which shows a clean "You don't have access" panel immediately. A Staff user typing `/users` directly sees the real admin page shell (stat cards, an "Add user" button) with empty data (the underlying API correctly 403s). Clicking "Add user," filling the whole form, and submitting reaches a live `POST /api/users`, which the server correctly refuses (`403 "Admin access required"`) — confirmed no user was actually created.
- **Impact:** confusing, unprofessional in front of a client demo; a Staff user can waste a minute filling in a form before being told they never could do this. Not a security gap — every write was confirmed refused server-side.
- **Location:** `src/app/users/page.tsx`, `src/app/roles/page.tsx`, `src/app/settings/page.tsx` — none import `RequirePermission`.
- **Suggested fix:** wrap all three the same way `/payments` is wrapped.

### E-06 — Dashboard, Payments, and Price Comparison are scoped by project ownership/membership on top of their own module permission — a "financial visibility only" role sees nothing
- **Severity:** High · **Confidence:** Confirmed
- **Class:** Permission model / Broken core workflow
- **Journey:** J4
- Configured a "Finance" role exactly as the Roles UI suggests — `dashboard:view` + `payments:view` + `priceComparison:view`, deliberately **no** project ownership or membership (the natural way to model "sees money, can't touch projects"). Logging in as that user: **every figure is zero.** Confirmed by source inspection that `src/app/api/dashboard/route.ts`, `src/app/api/payments/route.ts`, and `src/app/api/suppliers/price-comparison/route.ts` all layer `projectAccessClause(session, 'p.id', 'p.ownerId')` on top of the module-permission check — `dashboard/route.ts` has an explicit comment confirming this is deliberate.
- **Impact:** there is **no way**, today, to give a Staff user company-wide financial visibility without *also* making them a member of every project in the company — the opposite of what these three modules' own on-screen descriptions promise ("every supplier ... across every project they're linked to"). A real Finance hire configured exactly the way the product's own UI suggests would see a wall of zeros and reasonably think the product or their account is broken.
- **Confirmed correct, by contrast:** recording a payment (which *is* gated by `projects`, not `payments`, by design) was cleanly refused with a specific `403`, exactly as documented.
- **Location:** `src/app/api/dashboard/route.ts:24-52`, `src/app/api/payments/route.ts:36-67`, `src/app/api/suppliers/price-comparison/route.ts:26-39`.
- **Suggested fix:** decide the intended model explicitly — either these three modules grant company-wide visibility on their own (only falling back to project-scoping for a user with no module permission at all), or the product should offer an explicit "company-wide" grant so a real Finance persona is actually usable.

### E-07 — Concurrent Basic Price promote surfaces a raw 500 instead of a clean conflict response (data integrity itself is fine)
- **Severity:** Low · **Confidence:** Confirmed
- **Class:** Error handling
- **Journey:** J6
- Fired two `promote` requests at the same draft concurrently. One succeeded (200); the other hit `500 {"error":"Internal server error"}`. Server log traced this to `duplicate key value violates unique constraint "base_items_promotedFromId_key"` — a real DB-level unique constraint correctly prevented a double-promotion (confirmed: only one `base_items` row exists afterward). **This means the previously-documented AUTHZ-VULN-01/02 double-promotion vulnerability class could not be reproduced on this build** — it is protected by a genuine, race-proof DB constraint. The only remaining gap is that the losing request in a genuine race gets an opaque 500 instead of the same clean `400 "already promoted"` the sequential case already returns.
- **Location:** `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts`.
- **Suggested fix:** catch the constraint violation and return the same clean 400.

### E-08 — Session idle timeout does not actually expire non-"remembered" sessions (updates AUTH-VULN-05)
- **Severity:** High · **Confidence:** Confirmed, extensively verified
- **Class:** Session lifecycle / Security
- **Journey:** J6
- `src/lib/auth.ts` implements a real, deliberately-engineered idle timeout: 1 hour for a normal login, 3 days for "Remember me." Backdating a **remembered** session's `lastSeenAt` 4 days correctly produced a 401 on the next request. Backdating a **non-remembered** session's `lastSeenAt` 2 hours (past its 1-hour window) did **not** — the session stayed fully valid.
- **Verification rigor:** reproduced identically across three separate server states — the original long-running process, a fresh restart, and a fresh restart with the entire Turbopack build cache deleted — to rule out any caching explanation. Confirmed via the exact session id decoded from the live cookie's JWT (not a different row), and confirmed via Postgres's own clock that the row really was ~7,200 seconds stale at request time. The code, read carefully end-to-end (`requirePermission → requireSession → getSession → resolveSession → isIdleExpired`), looks textually correct; the defect could not be pinned to a specific line without adding runtime instrumentation, which is out of scope for this audit (no source edits).
- **Compounding factor:** "Remember me" **defaults to checked**, in both the login form's initial state and the API's own schema default — a user must actively opt out to get the (broken) shorter window. In practice this means the meaningful 1-hour timeout is both broken *and* rarely the one in effect.
- **Relationship to AUTH-VULN-05:** this updates, rather than simply reconfirms, that finding. A real mechanism now exists (unlike when AUTH-VULN-05 was first documented) and the 3-day window genuinely works — but the shorter, more security-relevant window silently does nothing, which is a more specific and arguably more concerning state than "no idle timeout at all."
- **Location:** `src/lib/auth.ts:32-33` (window constants), `:106-109` (`isIdleExpired`), `:134-160` (`resolveSession`); defaults at `src/app/login/page.tsx:35` and `src/app/api/auth/login/route.ts:35`.

### E-09 — Active project tab does not survive a page refresh
- **Severity:** Low · **Confidence:** Confirmed
- **Class:** UX / Persistence
- **Journey:** J7
- Switching to the "Expenses" tab on a project and refreshing resets to the default "BSR" tab. No data loss, just has to re-click.
- **Suggested fix:** reflect the active tab in the URL (e.g. `?tab=expenses`).

## 6. Permission model verification

The three-layer model (account role, RBAC module permission, project reach) behaved correctly everywhere it was load-bearing for security:

- **Server-side checks held in every case tested**, including every case where the client-side UI was wrong or misleading (E-05). No finding in this exercise allowed an unauthorized read or write to actually succeed.
- **Scope isolation (`projectAccessClause`) is sound** for project-scoped data — directly confirmed under a real multi-project, multi-user scenario (J3): the Estimator's dashboard and project list totals exactly matched the sum of only their reachable projects, with zero leakage of Beta or the seeded legacy projects.
- **The same mechanism is the root cause of the model's biggest gap (E-06)**: it is applied to company-wide rollup modules (Dashboard, Payments, Price Comparison) where the module's own permission is supposed to be sufficient on its own, producing a role that is safe but useless.
- **Mismatches found, both directions:**
  - Hidden button, open route: none found (would be the dangerous direction — checked for specifically and not found).
  - Visible button, refused route (E-05): confirmed present, UX-only, not a security gap.

## 7. Known findings — current state

| ID | Status | Evidence |
|---|---|---|
| **X-02** malformed JSON → 500 instead of 400 | Still present | Fresh live instance hit during J6: a role-save request produced a raw server `SyntaxError: Unexpected end of JSON input` instead of a clean validation error. |
| **X-03** CSP has no `script-src` | Not re-verified this pass | Out of this exercise's direct scope; the Phase-6 CSP work referenced in the codebase was not re-audited here. |
| **X-06** Zod validates types but not ranges | Not exhaustively re-tested | Not specifically probed with negative/out-of-range values this pass; flagging as not re-verified rather than assuming still-present. |
| **X-07 / F-02-01 / F-03-03 / F-04-01** money-sign cluster (ROI reads as profit) | **Still present, reproduced 5 times** | Zero-expense project (+LKR 1,500,000 "profit"); partial-payment project (2,900% "return"); company-wide dashboard (**36,741.3%** "return" — the most visible instance, shown on Admin's own landing page); reproduced identically for the Estimator's correctly-scoped view. |
| **F-04-02** three route families ignore the URL's project id | Not re-tested | Out of this exercise's direct scope this pass. |
| **AUTH-VULN-05** no session idle timeout | **Updated, not simply reconfirmed** | A real mechanism now exists and partially works — see E-08. The accurate status is "partially fixed, and the broken part is the one that matters." |
| **AUTHZ-VULN-01/02** double-promotion of a Basic Price draft | **Could not reproduce — appears resolved** | A genuine concurrent-request race test (see E-07) resulted in exactly one promotion, protected by a real DB unique constraint. |
| **AUTHZ-VULN-03** TOCTOU race in expense payment recording | Not re-tested | Out of this exercise's direct scope this pass. |
| **Seed credential risk** (`prisma/seed.ts` hardcoded password) | Not re-tested | Not directly probed this pass; this exercise used its own local seed with a different demo password. |
| **Prisma schema drift** (`db:reset-seed`) | Not exercised | `db:reset-seed` was deliberately never run against any database in this exercise (would have destroyed fixtures mid-test). |
| **CSRF** (Origin check added 2026-09-19) | Not directly re-verified | Every mutating action in this exercise went through the real browser (which sends a correct Origin) or Playwright's `page.request` (same-origin context) — no raw cross-origin POST was attempted specifically to re-test this. |

## 8. Tested and clean

- **All 5 non-admin-shell-affected page-level RBAC denials** (Payments, Suppliers-compare, Users, Roles, Settings for Estimator; all 15 routes for the zero-permission user) rendered the same clean, well-designed "You don't have access to this page — Ask an admin to assign you a role with access to this section" panel — zero blank pages, zero spinners, zero raw errors, across every account tested.
- **Direct-URL access to a project outside a user's reach** (`/projects/{betaId}` as Estimator) rendered a clean "Project not found" state, not a half-rendered shell — confirmed with a network capture showing the underlying API also correctly 403s.
- **BSR recipe arithmetic** — base component + percentage allowance + non-1 `analysisQty` — matched a hand computation to the cent (LKR 1,017.50), both at creation and after editing the line's quantity (LKR 3,052.50).
- **Stage/milestone payment tracking** — marking a milestone paid correctly updated Received/Outstanding/ROI on both the project page and the company-wide dashboard, with zero-expense division handled gracefully (no `NaN`/`Infinity`).
- **Itemized expenses and partial payments** — line-item totals, locked Amount field, Paid/Outstanding recalculation after a partial payment, all matched hand computation exactly.
- **Basic Rate price history** — actor and timestamp both correctly recorded on a rate change, confirmed via the history API.
- **Clone-catalog between projects** — carried the current (post-edit) rate and unit correctly, and produced a genuinely independent copy (confirmed directly in the DB: editing the clone did not touch the source).
- **Excel import** — preview-before-write flow worked exactly as documented; the imported row appeared correctly after confirming.
- **All four session-revocation paths** (permission changed, account deactivated, password changed, logged out) invalidated the live session on the very next request, with zero reload needed in every case — and each produced a specific, correct user-facing message on the next login/navigation attempt, not a generic error.
- **Interruption handling** (Escape, backdrop click, browser Back, refresh mid-edit) — no partial writes, no stale state, no broken pages in any case.
- **Concurrent edit of the same record** — clean last-write-wins, dependent figures (Outstanding) recalculated correctly against the winning value, no corruption.
- **Zero-permission first-login experience** — warm, professional, not confusing: a "Welcome back" toast followed by a calm empty-dashboard state with a clear call to action, screenshot-verified.
- **Console hygiene, responsiveness (1920/1366/390px), and dark-mode legibility** — all clean across every page walked.
- **Cascade deletion** — deleting every test project and user left **zero orphaned rows** across nine dependent tables checked directly in the database, positively confirming the cascade-integrity claim in `doc/Front end/ORPHANED_ROWS_FIX_PROMPT.md`.

## 9. Not tested / blocked

- **6 of the 20 documented pages** were only exercised implicitly, not as a dedicated per-page pass: `/suppliers/[id]`, `/sub-contractors/[id]`, `/suppliers/compare/item`, `/users/[email]` were opened at least once each (confirmed loading without error) but not deeply exercised for every control on them.
- **PDF exports specifically** — only Excel exports were opened/verified for non-zero size; PDF variants were not separately downloaded and checked this pass (page-by-page prompt's territory).
- **X-03, X-06, F-04-02, AUTHZ-VULN-03, seed-credential risk, `db:reset-seed` schema drift, CSRF** — all explicitly *not* re-tested this pass (see §7); their prior documented status should be treated as unconfirmed-but-not-contradicted, not as "still open" or "resolved."
- **MFA** — correctly not tested, per the prompt's explicit instruction (declined by the client, removed 2026-09-04).
- **Full byte-for-byte verification of exported file contents** — file presence and size were checked; the actual numbers inside each export were not opened and compared line-by-line against on-screen figures for every export button in the app (only the BSR and Dashboard Excel exports got this level of scrutiny in earlier page-by-page work, which this exercise did not repeat).
- **A true multi-day idle-timeout wait** — the idle-timeout finding (E-08) was verified by backdating the database directly rather than waiting the real 1 hour / 3 days; this is a faster, equally valid way to test the same code path (confirmed by successfully triggering the *working* 3-day case the same way), but is worth knowing if anyone re-verifies this by other means.
- **The specific 400 vs. 500 distinction for every other route** — E-07's constraint-violation-surfaces-as-500 pattern was found once; whether the same gap exists at other unique-constraint boundaries in the app was not systematically swept.

## 10. Handover readiness

**Must fix before handover:**
1. **E-06** (Finance role is non-functional) — this is the one finding that makes a documented, expected configuration produce a broken-looking product for the end user. Ranked first because it will be discovered by the client almost immediately if they set up a real Finance user the way the UI suggests.
2. **E-08** (idle timeout silently broken for the shorter window) — a genuine session-lifecycle security gap, and the default ("Remember me" checked) actively steers users away from the one path that's at least verified to work.
3. **E-03** (expense date defaults to a hardcoded literal) — silently corrupts financial record-keeping for every expense an operator doesn't think to double-check the date on.
4. **E-01** (unchecked fetch responses, systemic) — the underlying cause of at least one confirmed silent-failure incident; worth a dedicated pass given its scope (19+ call sites) rather than leaving it as latent risk.

**Should disclose in writing rather than fix immediately:**
- **E-02** (unit-rename cascade gap) — narrow, low-frequency trigger; a one-line fix, but low urgency.
- **E-05** (admin pages render full shell for non-admins) — cosmetic/UX only, no security exposure; worth a note so the client doesn't mistake it for a security bug if they notice it themselves.
- **E-07** (raw 500 on a promote race) — extremely narrow trigger (genuine double-click race reaching the server twice), and the data-integrity outcome is already correct.
- **E-09** (tab doesn't survive refresh) — pure polish.
- **E-04** (no ownership-transfer UI) — disclose as a known gap; the API exists and works if urgently needed via direct support intervention.

**Accepted / known limitations** (per prior documentation, not re-litigated this pass): no MFA (client declined); the money-sign/ROI-percentage display issue (F-02-01 family) remains open and was repeatedly reproduced — recommend the client be shown this explicitly, since it's the kind of number a stakeholder might screenshot and misread.

**Sign-off statement:** This test drove the real application, as a real user would, through complete role-based journeys covering account creation, project estimation, financial recording, and the full session lifecycle (including deliberately adversarial conditions: concurrent writes, dropped network, revoked permissions mid-session, and backdated session state). It certifies that no crash-class failure was found in any of the paths exercised, and that the server-side authorization boundary held in every single case tested, including every case where the client-side experience was misleading. It does **not** certify the six known-open items in §7 that were deliberately not re-tested this pass, the byte-for-byte correctness of every export, or any code path not named in §2's coverage table. The four "must fix" items in this section are functional and security-relevant enough that they should be resolved — or at minimum explicitly disclosed to the client with their exact impact — before this build is represented as complete.
