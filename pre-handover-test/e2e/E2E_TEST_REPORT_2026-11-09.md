# Vega Construction Manager — Pre-Handover End-to-End Test Report

- **Date:** 2026-11-09 · **Tester:** Claude Code (senior QA role) · **Requested by:** yomal@bistecglobal.com
- **Build:** branch `dev`, commit `348da81` (latest `origin/dev`, includes PR 1338 security fixes S1–S4)
- **Overall verdict:** 🔴 **NOT READY** — short path to ready (see §1)

## 1. Executive summary and verdict

**🔴 NOT READY.** Access control is solid and the core money maths is right: across 7 accounts and about 370 permission checks, no request reached data it should not, and every hand-computed figure (stage splits, instalments, cheques, BSR wastage/profit, unit × qty expenses, cost-plus margin, dashboard and payments totals) matched the UI, the API and the database to the cent. It is not ready because one Critical defect can corrupt money records (two expense payments at the same moment overpay an expense — P-35), seven High defects include success messages for actions that did not happen (P-38, P-41) and a Finance role that sees an empty dashboard (P-29), and two UAT items are not delivered as agreed (ENH-04 expense clone, ENH-07 remove ROI / add Project Status).

**To reach 🟡/🟢:** fix P-35 (reuse the existing `insertPaymentGuarded()`), P-38, P-39, P-41, P-27, P-12/P-43 (map duplicate-key errors to 409); get the client's decision on P-29 (Finance scope) and on ENH-04/ENH-07; then re-run this suite (`tests/e2e-handover/`, about 10 minutes). Most of these are small, local changes.

| | Count |
|---|---|
| Test cases (clean final pass) | **182** — 147 passed, 35 failed, 0 blocked |
| Failures caused by the app | 34 (each maps to a finding) · 1 test-script error (J3-04, see §10) |
| Findings | **43** — Critical 1 · High 7 · Medium 16 · Low 18 · Info 1 |
| Money figures cross-checked UI/API/DB | 38 rows, all consistent once display rules are applied (§6) |
| Previous findings E-00…E-09 | 6 still fixed · 1 partly open (E-01) · 1 regressed (E-06) · 2 retracted ones confirmed working |
| UAT ENH-01…09 | 7 resolved · 2 still open (ENH-04, ENH-07) |

## 2. Environment

| Item | Value |
|---|---|
| Commit | `348da81` on `dev` (fast-forwarded from `0e15246` at start; `npm ci`, `npx prisma generate`) |
| Dirty tree | Yes, outside `src/`: `.gitignore`, `next-env.d.ts` modified; 5 staged deletions in `doc/test/security/`; untracked `.specclaw/`, `docs/`; created for this run: `.env.local`, `tests/e2e-handover/`, `prisma/.demo-seed.vega_e2e*.json`. No application code was changed. |
| Next.js | 16.4.5, production build (`npm run build && next start -p 3200`) |
| Database | Local Docker `vega-e2e-pg` (`postgres:17-alpine` 17.11, TZ UTC) on `127.0.0.1:5441`. First pass DB `vega_e2e`; clean final pass on a fresh `vega_e2e_rerun`. Host verified as localhost before the first write. No shared database (Supabase/Azure/k3s) was touched. |
| Seed | `db:migrate`, `db:seed`, `scripts/seed-demo-payments.ts`, `prisma/seed-cost-plus.ts` (+7 hand-inserted suppliers, finding P-02) |
| Browser | System Chrome 156.0.8078.80 via Playwright 1.63 (`channel: 'chrome'`; the Playwright browser download was blocked on this machine) |
| App URL | `http://localhost:3200` (3000 and 3100 were used by other local apps; see RUN-LOG) |
| Time zone | App and DB UTC; idle/expiry tests move timestamps with UTC-safe SQL |

## 3. Scope and accounts

All 22 pages in the brief (plus every project tab and the variations view) and all API route families under `src/app/api/**`, exercised through the UI and directly. Accounts were created **through the UI** by the admin (cases J9-01…J9-10):

| Account | Role / permissions | Project access |
|---|---|---|
| E2E-Admin | `nimal@vegahomes.lk`, seeded Admin | all |
| E2E-Estimator | projects view/create/edit, activities view/create/edit, suppliers view | member of E2E-Main |
| E2E-Estimator2 | same role as Estimator | **not** a member of E2E-Main |
| E2E-Finance | dashboard, payments, priceComparison view | none |
| E2E-CostPlus | costPlus view/create/edit/delete | owns its cost-plus project |
| E2E-ViewOnly | view on every module | member of E2E-Catalog only (from J7) |
| E2E-NoPerm | no role | none |

Main test data: **E2E-Main Residence** (contract 12,000,000; 4 stages; Stage 1 Advance paid in 5 instalments incl. a bounced cheque; Interim by cleared cheque; variations V1 250,000 in contract / V2 100,000 not; BSR item 01.91 with wastage and profit; expenses with unit × qty lines, other payee, payments), **E2E-Catalog** (Basic Price → Basic Rate catalog, clone source), **E2E-Cost plus villa** (12 %, later 15 %).

## 4. Coverage matrix

Page/module × account. 🟢 behaves correctly for that account (allowed and working, or cleanly denied) · 🟡 works with Medium/Low findings · 🔴 a Critical/High finding affects that account here. "denied" = clean "You don't have access to this page" panel and API 403, verified.

| Module / pages | Admin | Estimator | Estimator2 | Finance | CostPlus | ViewOnly | NoPerm |
|---|---|---|---|---|---|---|---|
| Dashboard `/` | 🟡 ROI still shown (P-23), whole-rupee cards (P-28), truncated tile (P-40) | 🟢 denied | 🟢 denied | 🔴 empty (P-29) | 🟢 denied | 🟡 scoped figures correct; same display issues | 🟢 denied |
| Projects list + project tabs | 🟡 P-15, P-16, P-17, P-22, P-24 | 🟡 same; no delete/promote (correct) | 🟢 list excludes Main; Main → "not found"; 9 API probes 403 | 🟢 denied | 🟢 denied | 🟢 read-only, no create/edit controls | 🟢 denied |
| Expenses (project tab) | 🔴 P-35 concurrent overpay; P-18, P-19, P-20, P-21 | 🔴 same | 🟢 blocked | 🟢 denied | 🟢 denied | 🟢 read-only | 🟢 denied |
| Stages, milestones, variations | 🟢 all instalment rules correct (P-17 wording) | 🟢 | 🟢 blocked | 🟢 denied | 🟢 denied | 🟢 read-only | 🟢 denied |
| Basic Price / Basic Rate (global + tabs) | 🔴 P-41, P-12; P-10, P-11, P-13, P-14, P-42 | 🟡 no promote (correct) | 🟢 | 🟢 denied | 🟢 denied | 🟢 read-only | 🟢 denied |
| Activities | 🔴 P-43 (race → 500); P-07 | 🔴 P-43 (has create) | 🔴 P-43 | 🟢 denied | 🟢 denied | 🟢 read-only | 🟢 denied |
| Suppliers & sub-contractors (+ detail) | 🔴 P-39; P-01, P-07, P-08 | 🟡 view-only enforced; P-01 | 🟡 view-only; other projects' vouchers hidden | 🟢 denied | 🟢 denied | 🟡 P-01 | 🟢 denied |
| Price comparison (+ item) | 🟢 | 🟢 denied | 🟢 denied | 🟡 item page "not found" (P-30) | 🟢 denied | 🟡 P-30 | 🟢 denied |
| Payments | 🟡 P-25, P-26 | 🟢 denied | 🟢 denied | 🔴 empty (P-29) | 🟢 denied | 🟡 scoped | 🟢 denied |
| Cost plus (+ detail) | 🔴 P-27 | 🟢 denied | 🟢 denied | 🟢 denied | 🔴 P-27; owner-only access correct | 🟢 other owner's project → clean "doesn't exist" | 🟢 denied |
| Users, Roles, Settings (all 7 admin pages) | 🟡 P-03, P-06, P-31, P-32, P-33, P-34 | 🟢 denied | 🟢 denied | 🟢 denied | 🟢 denied | 🟢 denied | 🟢 denied |
| Login / session | 🟡 P-31 | 🟡 P-31 | 🟡 P-31 | 🟡 P-31 | 🟡 P-31 | 🟡 P-31 | 🟡 P-31 |

## 5. Workflow results

One table per journey from the clean final pass (`evidence-2026-11-09/rerun/`). "Pass ⚠" = the case passed but recorded a finding or note. Evidence paths are relative to that folder. Expected/actual for every individual comparison are in `api/<ID>-checks.json`.

### J0

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J0-01 | /api/healthz and /api/ready respond | healthz 200 {status:"ok"}, ready 200 {status:"ready"}, no session needed | healthz 200 {"status":"ok"}; ready 200 {"status":"ready"} | Pass | `api/J0-01.json` |
| J0-02 | /login renders for an anonymous user, protected page redirects to it | /login shows the sign-in form; / without a session redirects to /login | redirected to /login in 180 ms; password field visible | Pass | `screens/J0-02.png` |
| J0-03 | every page loads for admin without console errors, failed requests or stuck spinners | each page: HTTP 200, renders content, 0 console errors, 0 page errors, 0 own 4xx/5xx, no spinner after 15 s | Supplier detail: status 200, console: Failed to load resource: the server responded with a status of 404 (Not Found) / Failed to load resource: the server responded with a status of 404 (Not Found), failed: GET /api/projects/seedfix_sup_2/basic-rate 404, GET … | Fail | `api/J0-03.json`<br>`screens/J0-03-*.png (one per page)` |

### J1

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J1-01 | company profile: defaults shown, edit and save through the UI | GET returns defaults (usingDefaults:true) on a fresh DB; saving the form persists every field to company_profile and GET returns them | as expected (3 checks) | Pass | `screens/J1-01-before.png`<br>`screens/J1-01.png` |
| J1-02 | company profile: required name, invalid email rejected; logo is not configurable | blank name -> 400 "Name is required"; bad email -> 400 "Enter a valid email address"; profile unchanged | as expected (2 checks) | Pass | `api/J1-02.json` |
| J1-03 | category: create through Field options UI | category saved with uppercased unique prefix; toast "Category added" | as expected (1 checks) | Pass | `screens/J1-03-form.png`<br>`screens/J1-03.png` |
| J1-04 | category: duplicate prefix (other case) rejected; duplicate label allowed | prefix "qum" again -> 409 "Prefix ... is already used" | as expected (1 checks) | Pass | `api/J1-04.json` |
| J1-05 | category: rename shows everywhere (key unchanged), blank rename rejected | PATCH label renames; items keep the key so every screen shows the new label; PATCH label "" -> 400 | blank label rejected: expected 400, got 200<br>⚠ PATCH /api/categories/[key] accepted label "" (stored "") | Fail | `screens/J1-05.png`<br>`api/J1-05.json` |
| J1-06 | category: delete in use blocked, unused delete works | DELETE in-use category -> 409 "Still used by 1 item ..."; a fresh unused one -> 200 and row gone | as expected (4 checks) | Pass | `api/J1-06.json` |
| J1-07 | trade: create through Field options UI | toast "Trade added", row in trades | as expected (1 checks) | Pass | `screens/J1-07.png` |
| J1-08 | trade: duplicate name in different case rejected | POST /api/trades "E2E-TRADE R6I8UM" -> 409 (brief: duplicate checks are case-insensitive) | different-case duplicate: expected 409, got 200<br>⚠ trade duplicate check is case-sensitive: "E2E-TRADE R6I8UM" accepted next to "E2E-Trade r6i8um" | Fail | `api/J1-08.json`<br>`traces/j01-master-data-J1-08-trad-c9a46--in-different-case-rejected/trace.zip` |
| J1-09 | trade: rename cascades to Basic Price drafts in every project | PATCH /api/trades/[id] renames trade and every basic_price_items.trade that used the old name | as expected (2 checks) | Pass | `api/J1-09.json` |
| J1-10 | trade: delete in use blocked, unused delete works | in use -> 409 "Still used by 1 item(s) in Basic price"; unused -> 200 | as expected (2 checks) | Pass | `api/J1-10.json` |
| J1-11 | unit: create through Field options UI | toast "Unit added", row in units | as expected (1 checks) | Pass | `screens/J1-11.png` |
| J1-12 | unit: duplicate name in different case rejected | POST /api/units "E2E-UNIT R6I8UM" -> 409 (brief: duplicate checks are case-insensitive) | different-case duplicate: expected 409, got 200<br>⚠ unit duplicate check is case-sensitive: "E2E-UNIT R6I8UM" accepted next to "E2E-Unit r6i8um" | Fail | `api/J1-12.json`<br>`traces/j01-master-data-J1-12-unit-c35c9--in-different-case-rejected/trace.zip` |
| J1-13 | unit: rename cascades to Basic Rate, Basic Price and BSR items (E-02 regression) | unit rename updates base_items.unit, basic_price_items.unit and activity_items.unit | as expected (3 checks) | Pass | `api/J1-13.json` |
| J1-14 | unit: delete blocked while any item uses it (incl. a BSR item only) | unit used by drafts/rates -> 409; a unit used ONLY by a BSR activity item must also be blocked (else items keep an orphan unit) | in use only by a BSR item: expected 409, got 200<br>⚠ DELETE /api/units/[id] does not check activity_items.unit: a unit still used by a BSR item was deleted | Fail | `api/J1-14.json`<br>`traces/j01-master-data-J1-14-unit-94ee2-es-it-incl-a-BSR-item-only-/trace.zip` |
| J1-15 | supplier: create through the UI | toast "Supplier added", row in DB, listed | as expected (1 checks) | Pass | `screens/J1-15.png` |
| J1-16 | supplier: case-insensitive duplicate rejected in UI and API | "e2e-supplier alpha r6i8um" and " E2E-SUPPLIER ALPHA R6I8UM " -> 409 "A supplier named ... already exists" | as expected (3 checks) | Pass | `screens/J1-16.png`<br>`api/J1-16.json` |
| J1-17 | supplier: rename on detail page, detail page sections render | detail page shows name, Payment summary with zeros, empty vouchers; Rename saves | rename of unknown id: expected 404, got 200<br>⚠ PATCH /api/suppliers/<unknown id> returns 200 and writes nothing (should be 404) | Fail | `screens/J1-17-detail.png`<br>`screens/J1-17.png` |
| J1-20 | sub-contractor: create through the UI | toast "Sub-Contractor added", row in DB, listed | as expected (1 checks) | Pass | `screens/J1-20.png` |
| J1-21 | sub-contractor: case-insensitive duplicate rejected in UI and API | "e2e-subcon alpha r6i8um" and " E2E-SUBCON ALPHA R6I8UM " -> 409 "A sub-contractor named ... already exists" | as expected (3 checks) | Pass | `screens/J1-21.png`<br>`api/J1-21.json` |
| J1-22 | sub-contractor: rename on detail page, detail page sections render | detail page shows name, Payment summary with zeros, empty vouchers; Rename saves | rename of unknown id: expected 404, got 200<br>⚠ PATCH /api/sub-contractors/<unknown id> returns 200 and writes nothing (should be 404) | Fail | `screens/J1-22-detail.png`<br>`screens/J1-22.png` |
| J1-23 | supplier: delete in use blocked with a clear message; unused delete works | seeded supplier with expenses -> 409 "Still used by N expense(s)..."; supplier only used by cost-plus -> 409 with a friendly message; unused -> 200 | in use only by cost plus: expected 409, got 200; friendly cost-plus message: expected true, got false | Fail | `api/J1-23.json`<br>`traces/j01-master-data-J1-23-supp-81219-message-unused-delete-works/trace.zip` |
| J1-24 | activity: create through the UI gets the next code | new activity gets code 17; toast "Activity added" | as expected (1 checks) | Pass | `screens/J1-24.png` |
| J1-25 | activity: duplicate (other case) rejected, rename, delete in-use blocked | dup -> 409; rename -> 200; delete while a draft uses it -> 409; delete when unused -> 200 | rename unknown code: expected 404, got 200<br>⚠ PATCH /api/activities/<unknown code> returns 200 (no 404) | Fail | `api/J1-25.json`<br>`traces/j01-master-data-J1-25-acti-2eed9-ename-delete-in-use-blocked/trace.zip` |
| J1-26 | activity: two concurrent creates both succeed or fail cleanly (no 500) | two simultaneous POST /api/activities get distinct codes, or the loser gets a 4xx — never a 500 | no 500: expected true, got [200,500]<br>⚠ concurrent POST /api/activities: the loser gets a raw 500 (unique violation 23505 not mapped) | Fail | `api/J1-26.json`<br>`traces/j01-master-data-J1-26-acti-a42e9-eed-or-fail-cleanly-no-500-/trace.zip` |

### J2

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J2-01 | setup: catalog project with drafts | project E2E-Catalog created (4 stages) to hold the catalog under test | as expected (1 checks) | Pass |  |
| J2-02 | add a Basic Price draft through the project tab UI | draft saved with category Material, unit Bag, price 2450.00, supplier; toast "Draft added to Basic Price" | as expected (1 checks) | Pass | `screens/J2-02-form.png`<br>`screens/J2-02.png` |
| J2-03 | next-code: first material code in the project is M-001, then follows max+1 | GET next-code?cat=material -> M-001 on an empty catalog; after M-001 and M-007 exist -> M-008 (max+1, not count+1) | as expected (1 checks) | Pass | `api/J2-03.json` |
| J2-04 | promote the draft through the UI; code auto-filled | Promote modal pre-fills M-001; base_items row M-001 rate 2450, draft status promoted, promotedCode M-001; toast "Promoted to Basic Rate as M-001" | as expected (2 checks) | Pass | `screens/J2-04-form.png`<br>`screens/J2-04.png` |
| J2-05 | promote the same draft again -> clean 400, still one base item | 400 "This draft has already been promoted."; base_items count for the draft stays 1 | as expected (2 checks) | Pass | `api/J2-05.json` |
| J2-06 | concurrent promote of one draft -> one 200, one clean 4xx, one base item (E-07 regression) | two parallel promotes: exactly one 200, the other 400, never 500; one base item | as expected (2 checks) | Pass | `api/J2-06.json` |
| J2-07 | promote with a code already used in the project -> message names the code clash | 400/409 telling the user the code M-001 is already used (not "already promoted") | message mentions the code is in use: expected true, got This draft has already been promoted.<br>⚠ duplicate code on promote reports "This draft has already been promoted." — misleading; the draft was never promoted | Fail | `api/J2-07.json`<br>`traces/j02-pricing-J2-07-promote--54229-essage-names-the-code-clash/trace.zip` |
| J2-08 | next-code after M-001, M-002 and a manual M-007 is M-008 | next-code = max numeric suffix + 1 = M-008 | as expected (3 checks) | Pass | `api/J2-08.json` |
| J2-09 | edit Basic Rate rate through the UI -> history, previous rate, draft price synced | rate 2450 -> 2600.50: price_history_entries row (old 2450, new 2600.5); list shows previous rate 2,450.00; source draft price follows; history modal lists it | history modal shows money to 2 decimals (LKR standard): expected true, got Price history — E2E-Cement OPC r6i8um Sourced from the audit log — old value, new value, who, and when. WHEN OLD RATE NEW RATE CHANGE BY 09 Nov 2026, 11:31 2,450 2,600.5 +150.5 Nimal P… | Fail | `screens/J2-09.png`<br>`api/J2-09.json` |
| J2-10 | Basic Rate search and category filter | search "steel" shows only the steel item; search by code "M-002" shows sand; counter matches | as expected (2 checks) | Pass | `screens/J2-10-steel.png`<br>`screens/J2-10.png` |
| J2-11 | Basic Rate export to Excel matches the catalog | XLSX downloads; contains M-001 2600.50, M-002 18000, M-007 310 | as expected (3 checks) | Pass | `exports/J2-11-Basic_Rate_E2E-Catalog_r6i8um.xlsx`<br>`exports/J2-11-rows.txt` |
| J2-12 | delete: un-promoted draft deletes; promoted draft refused | draft delete 200; promoted draft delete 400 "Only un-promoted drafts can be deleted." | as expected (2 checks) | Pass | `api/J2-12.json` |
| J2-13 | deleting a Basic Rate item leaves its draft usable | after deleting M-007, its source draft can be re-promoted or deleted (it should not stay stuck as "promoted") | draft can be re-promoted or deleted: expected true, got {"re":[400,"This draft has already been promoted."],"rm":[400,"Only un-promoted drafts can be deleted."],"draft":{"status":"promoted","promotedCode":"M-007"}}<br>⚠ after its Basic Rate item is deleted, the draft stays status=promoted (promotedCode M-007) and can be neither re-promoted ("This draft has already been promote… | Fail | `api/J2-13.json`<br>`traces/j02-pricing-J2-13-deleting-14782-tem-leaves-its-draft-usable/trace.zip` |
| J2-14 | add Basic Rate item with a duplicate code -> 409, not 500 | POST /api/projects/[id]/basic-rate code M-001 again -> 4xx naming the duplicate code | status: expected one of [400,409], got 500<br>⚠ POST /api/projects/[id]/basic-rate with an existing code returns 500 (unique violation not mapped) | Fail | `api/J2-14.json`<br>`traces/j02-pricing-J2-14-add-Basi-1342d-uplicate-code---409-not-500/trace.zip` |
| J2-15 | editing a promoted draft keeps draft and Basic Rate in step | PATCH price on a promoted draft is either refused, or updates the linked Basic Rate item (never two different prices for one item) | no drift: expected true, got {"patch":200,"draft":19000,"rate":18000}<br>⚠ promoted draft price edited to 19000 while its Basic Rate item stays 18000; the Basic price tab and the Basic rate tab now disagree | Fail | `api/J2-15.json`<br>`traces/j02-pricing-J2-15-editing--4e971-raft-and-Basic-Rate-in-step/trace.zip` |
| J2-16 | global /basic-price page: promote with a blank price is not reported as success | blank/0 price is refused with a message; no "Promoted" toast; draft stays draft | no success toast: expected true, got Promoted to Basic Rate as L-001<br>⚠ global /basic-price promote with blank price: toast "Promoted to Basic Rate as L-001" but nothing was promoted (silent failure) | Fail | `screens/J2-16-form.png`<br>`screens/J2-16.png` |
| J2-17 | global /basic-rate page: rate edit to 0 is refused visibly | entering 0 shows a validation message; rate unchanged; no success toast | no success toast for a 0 rate: expected true, got Item updated — timestamped & logged<br>⚠ global /basic-rate: rate 0 → toast "Item updated — timestamped & logged" while the rate silently stays 18000 | Fail | `screens/J2-17.png`<br>`api/J2-17.json` |

### J3

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J3-01 | create the main project through the UI | confirm "Create project ... with 4 stages?"; toast "Project created — stages & milestones generated"; DB: contract 12,000,000, 4 stages, 12 milestones 50/25/25, owner = admin, status Active, curStage 1 | as expected (5 checks) | Pass | `screens/J3-01-form.png`<br>`screens/J3-01.png` |
| J3-02 | new project form: field validation in the UI | empty submit -> "Project name is required" (client, location too); stages 3 -> "Construction stages must be 4 or 5"; contract -1 -> "Contract value cannot be negative"; 1e12 -> "... 100,000,000,000 or less"; nothing cre… | as expected (7 checks) | Pass | `screens/J3-02-empty.png`<br>`screens/J3-02.png` |
| J3-03 | project API validation and edit (status, curStage range) | POST: 121-char name, stages 6, start 2026-02-30, whitespace name -> 400; PATCH status "On Hold" ok; curStage 0 / 9 (> stages) -> 400 | curStage 0: expected 400, got 200; curStage 9 > 4 stages: expected 400, got 200<br>⚠ PATCH /api/projects/[id] accepts curStage outside 1..stages (0 -> 200, 9 -> 200); dashboard progress would show stage 9 of 4 | Fail | `api/J3-03.json`<br>`traces/j03a-project-income-J3-03--e9e2b-edit-status-curStage-range-/trace.zip` |
| J3-04 | add Estimator as a member through /settings/project-access | toast "Project added — they can now see and work on it"; project_members row; Estimator2 NOT added | SyntaxError: Invalid regular expression: /^E2E-Main Residence r6i8um (/: Unterminated group | Fail | `traces/j03a-project-income-J3-04--eea69-ugh-settings-project-access/trace.zip` |
| J3-05 | member rules: no-role user refused, owner cannot be added or removed | NoPerm -> 400 "...no role assigned yet..."; owner as member -> 409; remove owner -> 400; add ViewOnly then remove via UI -> gone | as expected (5 checks) | Pass | `screens/J3-05.png`<br>`api/J3-05.json` |
| J3-06 | transfer ownership to Estimator and back (UI) — old owner kept as member | API transfer -> owner Estimator, admin becomes member; UI transfer back -> owner admin, Estimator becomes member again; toast "Ownership transferred to ..." | as expected (5 checks) | Pass | `screens/J3-06.png`<br>`api/J3-06.json` |
| J3-07 | stage values: even split, override rebalances, reset, over-budget refused | default 3,000,000 each; Stage 4 = 2,000,000 -> others 3,333,333.33 and Stage 2 Advance 1,666,666.67; reset -> even; 13,000,000 -> 400 with shortfall 1,000,000 / suggestedContract 13,000,000 | as expected (15 checks) | Pass | `api/J3-07.json` |
| J3-08 | stage value with "expand contract" also saves the dates sent with it | PATCH {value, expandContractTo, startDate} on the catalog project: contract expanded AND startDate saved (or a 400) | start date saved: expected true, got {"startDate":null,"value":1100000}<br>⚠ stage PATCH with expandContractTo returns 200 but silently drops startDate/completionDate sent in the same request | Fail | `api/J3-08.json`<br>`traces/j03a-project-income-J3-08--80922-aves-the-dates-sent-with-it/trace.zip` |
| J3-09 | Stage 1 Advance instalment 1: 500,000 cash through the UI (partial) | confirm "Record a client payment of 500,000.00?"; toast "Payment recorded"; received 500,000, outstanding 1,000,000, state partial; UI row shows Partial | as expected (5 checks) | Pass | `screens/J3-09-form.png`<br>`screens/J3-09.png` |
| J3-10 | Advance instalments 2-3: cheque 400,000 (pending), bank 600,000 (exact) -> paid; 0.01 mor… | after cheque: pending 400,000, outstanding 600,000; after 600,000: outstanding 0, state paid; +0.01 -> 400 "would overpay the milestone" | as expected (7 checks) | Pass | `api/J3-10.json` |
| J3-11 | bounced cheque reopens the balance; replacement payment; un-bouncing would overpay | bounce -> outstanding 400,000 partial; pay 400,000 online -> paid and Stage 1 start date stamped; mark bounced cheque "received" again -> 400 "Restoring this cheque would overpay" | as expected (5 checks) | Pass | `api/J3-11.json` |
| J3-12 | milestone guards: amount below paid, status write, contract cut below paid | Advance amount 1,000,000 -> 400 "below what has already been paid"; PATCH status -> 400 "derived from its payments"; contract 1,000,000 -> 400 | as expected (3 checks) | Pass | `api/J3-12.json` |
| J3-13 | paying a later milestone first asks "Payment out of order" in the UI | Stage 2 Interim "Record" while Stage 2 Advance is unpaid shows dialog "Payment out of order" | as expected (1 checks) | Pass | `screens/J3-13.png` |
| J3-14 | Stage 1 Interim paid by one cheque, then cleared | cheque 750,000 -> pending 750,000, outstanding 0, state paid; cleared -> received 750,000, pending 0 | as expected (2 checks) | Pass | `api/J3-14.json` |
| J3-15 | cents: 0.10 + 0.20 exactly settles a 0.30 milestone (no float residue) | catalog project Stage 4 Final amount override 0.30; pay 0.10 then 0.20 -> both 200, state paid; delete a payment -> 200 and balance reopens | as expected (5 checks) | Pass | `api/J3-15.json` |
| J3-16 | add variation V1 through the UI and include it in the contract | toast "Variation added" then "Added to contract"; DB amount 250,000, includedInContract true | as expected (1 checks) | Pass | `screens/J3-16-form.png`<br>`screens/J3-16.png` |
| J3-17 | variation instalments, guards and summary strip | V2 100,000 (not in contract); V1 paid 100,000 cash + 50,000 cheque; strip: Total 350,000 · Received 100,000 · Cheques pending 50,000 · Outstanding 200,000; overpay/amount-below-paid/delete-with-payments refused | as expected (9 checks) | Pass | `screens/J3-17.png`<br>`api/J3-17.json` |
| J3-18 | project income KPIs: milestones + included variation, header cards match | Contract value 12250000 (12,000,000 + V1 250,000), Received 2350000, Outstanding 9850000, cheque pending 50000; V2 (not in contract) excluded | as expected (7 checks)<br>⚠ project header Outstanding = 9900000 includes 50,000 cheques pending; API/dashboard/variations strip report outstanding 9850000 with cheques separate — same wo… | Pass ⚠ | `screens/J3-18.png` |
| J3-20 | selective clone through the UI copies only the ticked item | Clone modal: pick E2E-Catalog, tick only M-001 -> toast "Cloned 1 item..."; main project has M-001 (rate 2,600.50) and NOT M-002 | as expected (2 checks) | Pass | `screens/J3-20-form.png`<br>`screens/J3-20.png` |
| J3-21 | full clone: already-present code skipped, rest cloned; same project refused | clone [M-001, M-002, NOPE-1] -> {cloned:1, skipped:1}; unknown code ignored; source == target -> 400 | as expected (3 checks) | Pass | `api/J3-21.json` |
| J3-22 | import Basic Rate from Excel through the UI (new rows, bad row excluded) | preview: 2 new, 1 error ("Unknown category"); import -> "2 created, 0 updated"; L-001 Mason labour 4,500; M-010 tile adhesive 1,850 | as expected (2 checks) | Pass | `screens/J3-22-preview.png`<br>`screens/J3-22.png` |
| J3-23 | per-code history is per project (clone independence) | main M-001 2,600.50 -> 2,700: one history row on main; catalog M-001 history unchanged and rate still 2,600.50 | as expected (3 checks) | Pass | `api/J3-23.json` |
| J3-24 | BSR item with per-component wastage and profit: rate hand-computed | grand 21919.5, profit 2739.94, final 24659.44, rate 246.5944; wastage on the "pct" line not stored | as expected (4 checks) | Pass | `api/J3-24.json` |
| J3-25 | recipe modal shows the same grand total, profit and final total | UI: Grand total 21919.5, Profit amount 2739.94, Final total 24659.44; BSR row line total 49318.88 | as expected (5 checks) | Pass | `screens/J3-25.png` |
| J3-26 | wastage/profit extremes: 0, 100 accepted; negative and >100 refused | item B wastage 100% + profit 100% on 1,000 -> rate 4,000; wastage -5 -> 400 "Wastage cannot be negative"; 150 -> 400; profit -1 / 101 -> 400 | as expected (6 checks) | Pass | `api/J3-26.json` |
| J3-27 | add a BSR line through the UI ("Use existing", 1st floor x 10) | confirm "Add 10 × ... (1st) to the BSR?"; new bsr_lines row floor First qty 10; API lineTotal 2589.24 (rate x 1.05 x 10) | as expected (3 checks) | Pass | `screens/J3-27-form.png`<br>`screens/J3-27.png` |
| J3-28 | recipe component refresh to current Basic Rate keeps wastage % | M-001 rate 2,700 -> 2,800; refresh Cement component -> rate 2,800, amount 5,600 (qty 2); wastagePct still 2.5 | as expected (2 checks) | Pass | `api/J3-28.json` |
| J3-30 | log expense through the UI: unit amount x qty lines, voucher matches preview | lines 1,250 x 4 = 5,000.00 and 333.33 x 3 = 999.99; amount 5999.99; voucher = modal preview = VH-VOU-11-2026-NNN; category derived (custom lines -> Other) | as expected (7 checks) | Pass | `screens/J3-30-form.png`<br>`screens/J3-30.png` |
| J3-31 | derived category from line items: all material -> Material, mixed -> Other, sub-contractor | material lines -> Material; material + labour -> Other; category "Sub Contractor" + sub-contractor -> SubContractor; category sent by client never trusted | as expected (3 checks) | Pass | `api/J3-31.json` |
| J3-32 | voucher numbers: sequential, global, never reused after delete, per month, not editable | next Nov voucher = counter+1; delete the newest then create -> number skips the deleted one; October date -> VH-VOU-10-2026-xxx; PATCH with invoice -> 400 "Voucher number cannot be changed"; POST invoice field ignored | as expected (8 checks) | Pass | `api/J3-32.json` |
| J3-33 | other payee through the UI, with suggestion list | Vendor type Other + payee "E2E-Pradeshiya Sabha" -> isOtherPayee true, no supplier link, vendor text kept; "Other" badge in list | as expected (2 checks) | Pass | `screens/J3-33.png`<br>`api/J3-33.json` |
| J3-34 | expense payments: partial (UI), exact final, over-payment refused; status Completed | E1 5,999.99: pay 2,000 (UI) -> Partial, outstanding 3,999.99; pay 3,999.99 -> Completed; +0.01 -> 400 "would overpay the expense" | as expected (6 checks) | Pass | `screens/J3-34-partial.png`<br>`screens/J3-34.png` |
| J3-35 | expense payments in cents: 700.10 + 300.20 settle a 1,000.30 expense exactly | both instalments accepted (sum equals the amount to the cent); same for 0.10 + 0.20 on 0.30 | 0.10 + 0.20 on 0.30: expected [200,200], got [200,400]<br>⚠ exact final expense instalment refused as over-payment (float compare): 1,000.30 -> 200, 0.30 -> 400; milestone/variation payments compare in cents, expense pa… | Fail | `api/J3-35.json`<br>`traces/j03b-project-cost-J3-35-ex-7e0d5--a-1-000-30-expense-exactly/trace.zip` |
| J3-36 | edit expense: total below paid refused; edit keeps voucher; stage outside project refused | E1 (paid 5,999.99) lines -> 1,000 -> 400; stage 2 + same lines -> 200, invoice unchanged; stage 99 -> 400; URL with another project id -> 404 | stage 99 on a 4-stage project: expected 400, got 200; project id in URL is not this expense's project: expected one of [400,403,404], got 200<br>⚠ expense accepted with stage 99 on a 4-stage project (no range check) | Fail | `api/J3-36.json`<br>`traces/j03b-project-cost-J3-36-ed-1865b-age-outside-project-refused/trace.zip` |
| J3-37 | edit expense UI: voucher number field is read-only (ENH-09) | Edit expense modal shows the voucher, disabled, hint "System-issued — cannot be changed." | as expected (2 checks) | Pass | `screens/J3-37.png` |
| J3-38 | delete expense with payments through the UI: confirm, payments removed, totals drop | confirm "Delete this ... expense from X? This can't be undone."; toast "Expense deleted"; expense, its line items and payments gone; voucher not reused | as expected (3 checks) | Pass | `screens/J3-38.png`<br>`api/J3-38.json` |
| J3-39 | UAT ENH-04: selective clone of EXPENSES from another project | Expenses tab offers "clone expenses from another project" with checkboxes + Select all; cloned expenses get new vouchers | expense clone control present: expected true, got {"buttons":0,"sample":""}<br>⚠ UAT ENH-04 not delivered as written: no way to clone expenses between projects (commit 56cd2ef added a selective Basic Rate clone instead) | Fail | `screens/J3-39.png`<br>`traces/j03b-project-cost-J3-39-UA-4fbc0-PENSES-from-another-project/trace.zip` |
| J3-40 | BSR export (XLSX + PDF) carries the hand-computed line totals | both files contain item A and its Ground x200 line total 49318.88; PDF carries the company name from the profile | as expected (4 checks) | Pass | `exports/J3-40-BSR_E2E-Main_Residence_r6i8um.xlsx`<br>`exports/J3-40-xlsx.txt` |
| J3-41 | payments schedule and income statement exports match the UI figures | payments schedule contains S1 Advance 1,500,000 received; income statement total expenses = sum of project expenses in DB | as expected (2 checks) | Pass | `exports/J3-41-schedule-Payments_Schedule_E2E-Main_Residence_r6i8um.xlsx`<br>`exports/J3-41-schedule.txt` |
| J3-42 | project report PDF from the Projects list | PDF downloads, names the project and client, contract 12,000,000, company name from profile; toast "Project report exported" | Sinhala/Tamil client text survives (or is at least not garbage): expected true, got E2E-Vega Construction r6i8um Vega Homes — E2E No. 1, Test Road Colombo 05 +94 11 000 0000 e2e@vegahomes.lk PV E2E PROJECT REPORT PRJ/PROJ_5A777D69-9BD9-4C2F-97EE-C03CCC6A68B3/… | Fail | `exports/J3-42-Project_Report_E2E-Main_Residence_r6i8um.pdf`<br>`exports/J3-42-pdf.txt` |
| J3-43 | delete a populated project through the UI: everything under it goes, counters stay | project with stage payment, variation + payment, expense + payment, BSR item/line, draft, rate, member -> UI delete -> 0 rows left in every child table; invoice_counters unchanged | as expected (2 checks) | Pass | `screens/J3-43-confirm.png`<br>`screens/J3-43.png` |

### J4

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J4-01 | unfiltered totals: UI = API = DB (and what the totals leave out) | Total outstanding / Total paid on the page equal the API summary and an independent DB sum over every vendor group; expenses with no vendor at all are listed separately | as expected (5 checks)<br>⚠ 11 expenses (owed 5658200, outstanding 5658200) have no supplier/sub-contractor/payee and are left out of "Total outstanding" and every vendor tab; nothing on … | Pass ⚠ | `screens/J4-01.png`<br>`api/J4-01.json` |
| J4-02 | filter: project = main — API and UI match DB | with project = main: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-02.png`<br>`api/J4-02.json` |
| J4-03 | filter: status outstanding — API and UI match DB | with status outstanding: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-03.png`<br>`api/J4-03.json` |
| J4-04 | filter: status partial — API and UI match DB | with status partial: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-04.png`<br>`api/J4-04.json` |
| J4-05 | filter: status paid — API and UI match DB | with status paid: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-05.png`<br>`api/J4-05.json` |
| J4-06 | filter: date 2026-11-01..2026-11-30 — API and UI match DB | with date 2026-11-01..2026-11-30: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-06.png`<br>`api/J4-06.json` |
| J4-07 | filter: category Material — API and UI match DB | with category Material: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-07.png`<br>`api/J4-07.json` |
| J4-08 | filter: category SubContractor + Other — API and UI match DB | with category SubContractor + Other: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-08.png`<br>`api/J4-08.json` |
| J4-09 | filter: method Bank — API and UI match DB | with method Bank: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-09.png`<br>`api/J4-09.json` |
| J4-10 | filter: minOutstanding 50,000 — API and UI match DB | with minOutstanding 50,000: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-10.png`<br>`api/J4-10.json` |
| J4-11 | filter: search "alpha" — API and UI match DB | with search "alpha": API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-11.png`<br>`api/J4-11.json` |
| J4-12 | filter: combined: main + Nov + outstanding + Material/Other — API and UI match DB | with combined: main + Nov + outstanding + Material/Other: API summary and page KPIs equal an independent DB sum | as expected (6 checks) | Pass | `screens/J4-12.png`<br>`api/J4-12.json` |
| J4-13 | date presets set the right range (today 2026-11-09) | This month 2026-11-01..30; Last month 10-01..31; Last 3 months 09-01..11-30; This year 01-01..12-31; Last year 2025 | as expected (5 checks) | Pass | `screens/J4-13.png`<br>`api/J4-13.json` |
| J4-14 | date edge cases: leap day, impossible date, reversed range, month end inclusive | 2028-02-29 ok; 2026-02-29 -> 400 "That is not a real date"; from > to -> 400; to=2026-10-31 includes expenses dated 31 Oct; bad page/pageSize -> 400 | as expected (7 checks) | Pass | `api/J4-14.json` |
| J4-15 | DatePicker range: pick by clicking days, typed URL dates load the same range | clicking 1 Nov then 9 Nov sets from=2026-11-01&to=2026-11-09; opening that URL directly shows the same pill and totals | as expected (2 checks) | Pass | `screens/J4-15.png` |
| J4-16 | saved view: create through the UI, apply, rename, default, delete | toast "View saved"; menu lists it; applying restores the query; rename -> "View renamed"; default -> opening /payments with no params applies it; delete -> "View deleted" | as expected (8 checks) | Pass | `screens/J4-16-default-applied.png`<br>`screens/J4-16.png` |
| J4-17 | saved views are private to each user | Finance cannot list, rename or delete the admin's view (404 "View not found"); Finance's own view invisible to admin | as expected (6 checks) | Pass | `api/J4-17.json` |
| J4-18 | vendor drawer: totals equal the row and the DB; payment from the drawer | drawer for E2E supplier shows Owed/Paid/Outstanding equal to its row and to DB sums; per-project sections; completed expenses should not offer "Record a payment" | record-payment buttons only on unpaid expenses: expected true, got {"recordButtons":8,"unpaid":6,"completed":2}<br>⚠ vendor drawer shows "Record a payment" on 2 completed expense(s) (VendorDrawer.tsx:171); the supplier page hides it | Fail | `screens/J4-18.png`<br>`api/J4-18.json` |
| J4-19 | other-payee history: owed/paid and the payment list match the DB | GET other-payees/history?name=<payee> (any case, padded) returns owed = sum of that payee's expenses, payments listed; drawer shows "Payment history" | as expected (4 checks) | Pass | `screens/J4-19.png`<br>`api/J4-19.json` |
| J4-20 | tabs, sort and paging keep their state across refresh | tab=subContractors&sort=outstanding survives reload; rows sorted by outstanding desc; invalid sort falls back | as expected (3 checks) | Pass | `screens/J4-20.png` |

### J5

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J5-01 | setup: one item priced in three projects (2,500 / 2,400 / 2,400 tie), one single-supplier… | base items created; grouped by trimmed lower-case name + unit | as expected (1 checks) | Pass | `api/J5-01.json` |
| J5-02 | lowest price first, ties kept, case/space-insensitive grouping | one group for "Compare cement / Bag" with 3 rows ordered 2,400, 2,400, 2,500; both 2,400 rows marked Cheapest in the UI; price range 2,400 – 2,500 | as expected (4 checks) | Pass | `screens/J5-02.png`<br>`api/J5-02.json` |
| J5-03 | single supplier and missing supplier/price handling | "Compare single" has 1 row and is hidden by "Comparable only"; the no-supplier row counts in "No supplier"; an unpriced draft never appears | as expected (3 checks) | Pass | `screens/J5-03.png` |
| J5-04 | item page: projects, suppliers, history; untrimmed name still found | item page lists 3 projects and 2 suppliers; after a rate change it shows "Who changed it"; name with stray spaces resolves the same item (not 404) | as expected (5 checks) | Pass | `screens/J5-04.png`<br>`api/J5-04.json` |
| J5-05 | price comparison is company-wide for priceComparison:view; others refused | Finance (priceComparison:view, no projects) sees the comparison including E2E items; Estimator (no priceComparison) gets 403; NoPerm 403 | as expected (2 checks) | Pass | `api/J5-05.json` |

### J6

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J6-01 | create a cost-plus project through the UI as E2E-CostPlus | toast "Cost plus project created"; row with marginPct 12, owner = E2E-CostPlus, status Active | as expected (1 checks) | Pass | `screens/J6-01-form.png`<br>`screens/J6-01.png` |
| J6-02 | expenses (supplier, sub-contractor, other payee) recompute the margin | expense 160000.49, margin 19200.06, billed 179200.55; stored marginAmount matches; missing supplier -> 400 | as expected (6 checks) | Pass | `api/J6-02.json` |
| J6-03 | client payments: cash + cheque, cap at billed total, cheque cleared | received 100000, pending 50000, outstanding 29200.55; paying more than the balance -> 400; cleared cheque -> received 150,000 | as expected (5 checks) | Pass | `api/J6-03.json` |
| J6-04 | expense payments: full, cheque partial; "paid to suppliers" counts cleared money only | E1 100,000 paid in full (Bank); E2 20,000 cheque -> paidOut 100,000 until cleared, then 120,000; overpay E1 -> 400 | as expected (5 checks) | Pass | `api/J6-04.json` |
| J6-05 | margin change through the UI recalculates the margin amount | margin 15 % -> 24000.07, billed 184000.56; toast "Margin saved"; dashboard tab KPI "Total" shows it | as expected (3 checks)<br>⚠ KPI cards round money to whole rupees: expense 160000.49 shows as 160000 (brief: LKR to 2 decimals) | Pass ⚠ | `screens/J6-05.png` |
| J6-06 | cost-plus list KPIs = API summary = DB (own projects only for this user) | E2E-CostPlus sees only its own project; Total expense/margin/billed/Received/Paid to suppliers equal the API summary and DB | as expected (8 checks) | Pass | `screens/J6-06.png` |
| J6-07 | cutting expenses below what the client already paid is refused | received 150,000; margin 0 and delete the 100,000 expense would make the billed total 60,000.49 < received -> refused (like findUnderpaidMilestone on normal projects) | either change refused while received > billed: expected true, got {"margin0":200,"del":200,"total":60000.49,"received":150000,"outstanding":0}<br>⚠ cost-plus: margin set to 0 and a paid 100,000 expense deleted; billed total now 60000.49 while client received 150000; outstanding shows 0 (over-receipt hidden) | Fail | `api/J6-07.json`<br>`traces/j06-cost-plus-J6-07-cuttin-aba0e-ent-already-paid-is-refused/trace.zip` |
| J6-08 | cost-plus access: owner-only for staff; other modules refused | E2E-CostPlus cannot open a seeded admin cost-plus project (403); Estimator/Finance get 403 on /api/cost-plus; CostPlus gets 403 on /api/projects | as expected (4 checks) | Pass | `api/J6-08.json` |

### J7

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J7-01 | dashboard figures as admin: API and UI equal an independent DB computation | admin: all projects — received 19270625.21, outstanding 155033750.11, cheques 50000, committed 116361403.59, paid 69563260.39, projects 10 | as expected (17 checks) | Pass | `screens/J7-01.png`<br>`api/J7-01.json` |
| J7-02 | Estimator (no dashboard:view) gets a clean denial | GET /api/dashboard 403; / shows "You don't have access to this page"; no money figures leak | as expected (3 checks) | Pass | `screens/J7-02.png` |
| J7-03 | dashboard figures as finance: API and UI equal an independent DB computation | finance: projects owned or assigned — received 0, outstanding 0, cheques 0, committed 0, paid 0, projects 0 | as expected (11 checks)<br>⚠ Finance (dashboard:view, no project membership) sees an empty dashboard: every figure 0. E-06 (2026-09-21) made these company-wide by client decision; commit f… | Pass ⚠ | `screens/J7-03.png`<br>`api/J7-03.json` |
| J7-04 | cost-plus section on the dashboard equals the cost-plus portfolio summary | admin dashboard costPlus block = GET /api/cost-plus summary (same function) | as expected (7 checks) | Pass | `api/J7-04.json` |
| J7-05 | ENH-08: pending payment tile uses the current (first unpaid) stage, not a fixed stage | main project pending row = Stage 1 Final 750,000 (first stage with a balance); after a new payment it moves on | as expected (1 checks) | Pass | `api/J7-05.json` |
| J7-06 | dashboard tiles render and link correctly | tiles Expenses by category, Projects, Payment status, Rate changes, Pending payments, Project progress present; a pending row opens /projects/{id}?tab=stages | as expected (2 checks) | Pass | `screens/J7-06.png` |
| J7-07 | dashboard figures as viewonly: API and UI equal an independent DB computation | viewonly: projects owned or assigned — received 0.2, outstanding 1734375.1, cheques 0, committed 1001.6, paid 1000.4, projects 1 | as expected (12 checks) | Pass | `screens/J7-07.png`<br>`api/J7-07.json` |

### J8

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J8-01 | admin: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | as expected (47 checks) | Pass | `screens/J8-01-home.png`<br>`api/J8-01-matrix.json` |
| J8-02 | estimator: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | as expected (47 checks) | Pass | `screens/J8-02-home.png`<br>`api/J8-02-matrix.json` |
| J8-03 | estimator2: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | as expected (47 checks) | Pass | `screens/J8-03-home.png`<br>`api/J8-03-matrix.json` |
| J8-04 | finance: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | UI /suppliers/compare/item?name=E2E-Compare%20cement%20r6i8um&unit=Bag expected content: expected true, got {"got":"notfound","http":200,"pageErrors":[]} | Fail | `screens/J8-04-home.png`<br>`api/J8-04-matrix.json` |
| J8-05 | costplus: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | as expected (47 checks) | Pass | `screens/J8-05-home.png`<br>`api/J8-05-matrix.json` |
| J8-06 | viewonly: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | as expected (47 checks) | Pass | `screens/J8-06-home.png`<br>`api/J8-06-matrix.json` |
| J8-07 | noperm: every page and every module × action | allowed -> page content / API not 401-403-500; denied -> clean denial panel / API 403; out-of-reach record -> clean "not found"; never blank, crash or 500 | as expected (47 checks) | Pass | `screens/J8-07-home.png`<br>`api/J8-07-matrix.json` |
| J8-08 | Estimator2 (same role, not a member) cannot read or write the main project, even with gue… | list excludes it; GET project, stages, expenses, BSR, variations -> 403; PATCH expense / milestone payment / variation by real id -> 403; nothing changed | as expected (14 checks) | Pass | `api/J8-08.json` |
| J8-09 | unauthenticated: every API 401, every page redirects to /login | no cookie -> API 401 {"error":"Not authenticated"}; pages -> /login; healthz/ready public | as expected (35 checks) | Pass | `screens/J8-09.png`<br>`api/J8-09.json` |
| J8-10 | CSRF: mutations without or with a foreign Origin are rejected | POST/PATCH/DELETE with no Origin or Origin https://evil.example -> 403 "Cross-origin request rejected", even when logged in; same-origin works | as expected (7 checks) | Pass | `api/J8-10.json` |
| J8-11 | hidden controls match the API for restricted roles | Estimator: no Delete on projects, no Add/Rename/Delete on suppliers, no Promote; ViewOnly: no Log expense / Add variation / New project; Finance on /payments: no Record-payment buttons (it lacks projects:edit) | as expected (8 checks) | Pass | `screens/J8-11-estimator.png`<br>`screens/J8-11-viewonly.png` |

### J9

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J9-00 | create role "E2E-ViewOnly r6i8um" through /roles | role saved with exactly dashboard:view, projects:view, activities:view, suppliers:view, payments:view, priceComparison:view, costPlus:view; toast "Role created" | as expected (1 checks) | Pass | `screens/J9-00-form.png`<br>`screens/J9-00.png` |
| J9-05 | create user E2E-Estimator (estimator) through /users | user created Active, role Staff, assigned E2E-Estimator r6i8um; can log in | as expected (3 checks) | Pass | `screens/J9-05-form.png`<br>`screens/J9-05.png` |
| J9-06 | create user E2E-Finance (finance) through /users | user created Active, role Staff, assigned E2E-Finance r6i8um; can log in | as expected (3 checks) | Pass | `screens/J9-06-form.png`<br>`screens/J9-06.png` |
| J9-07 | create user E2E-CostPlus (costplus) through /users | user created Active, role Staff, assigned E2E-CostPlus r6i8um; can log in | as expected (3 checks) | Pass | `screens/J9-07-form.png`<br>`screens/J9-07.png` |
| J9-08 | create user E2E-ViewOnly (viewonly) through /users | user created Active, role Staff, assigned E2E-ViewOnly r6i8um; can log in | as expected (3 checks) | Pass | `screens/J9-08-form.png`<br>`screens/J9-08.png` |
| J9-09 | create user E2E-NoPerm (no role) through /users | user created Active, role Staff, assigned no roles; can log in | as expected (3 checks) | Pass | `screens/J9-09-form.png`<br>`screens/J9-09.png` |
| J9-10 | create user E2E-Estimator2 (estimator) through /users | user created Active, role Staff, assigned E2E-Estimator r6i8um; can log in | as expected (3 checks) | Pass | `screens/J9-10-form.png`<br>`screens/J9-10.png` |
| J9-11 | password policy: length, common password, based on name/email, byte cap | 11 chars -> "at least 12"; "unbelievable" -> "too common"; password containing the email local part -> "not be based on your name or email"; 73-byte password -> "72 characters or fewer"; valid -> 200 | as expected (5 checks) | Pass | `api/J9-11.json` |
| J9-12 | email uniqueness is case-insensitive; login with different case | POST "NIMAL@VEGAHOMES.LK" -> 409; PATCH another user to "Nimal@VegaHomes.lk" -> 409; logging in with the email in upper case works (emails are case-insensitive) | login with upper-case email: expected 200, got 401<br>⚠ login is case-sensitive on email ("ESTIMATOR.R6I8UM@E2E.TEST" -> 401 "Invalid email or password") while uniqueness is case-insensitive | Fail | `api/J9-12.json`<br>`traces/j09-users-roles-J9-12-emai-40a2c-e-login-with-different-case/trace.zip` |
| J9-13 | per-user permission override takes effect at once and can be removed | Finance + direct projects:view -> GET /api/projects 200 on its existing session; remove -> 403 again | as expected (2 checks) | Pass | `api/J9-13.json` |
| J9-14 | edit and deactivate a user through the UI; deactivated login refused with its own message | rename via Edit modal -> "User updated"; Deactivate -> status Inactive; login -> 403 "This account has been deactivated..."; Activate -> login 200 | as expected (3 checks) | Pass | `screens/J9-14.png`<br>`api/J9-14.json` |
| J9-15 | last active admin cannot be demoted or deactivated; self-delete refused; audit records pr… | with Sanduni and Yomal inactive, demoting or deactivating Nimal -> 409 "Cannot remove the last remaining Admin"; admin deleting self -> 400; deleting a user with audit records -> 409; fresh user delete -> 200 | as expected (6 checks) | Pass | `api/J9-15.json` |
| J9-16 | admin password change needs the admin's own current password | PATCH password without currentPassword -> 400; wrong currentPassword -> 401 "Incorrect current password"; correct -> 200 and the target's sessions are revoked | as expected (4 checks) | Pass | `api/J9-16.json` |
| J9-17 | user PATCH is all-or-nothing when part of it is invalid | PATCH {name, roleIds:["no-such-role"]} -> 4xx and the name is NOT changed | name unchanged: expected E2E-Tmp atomic, got E2E-Tmp half-saved<br>⚠ PATCH /api/users/[email] is not atomic: request refused (409) but the name was saved as "E2E-Tmp half-saved" | Fail | `api/J9-17.json`<br>`traces/j09-users-roles-J9-17-user-e0b83--when-part-of-it-is-invalid/trace.zip` |
| J9-18 | roles: edit through the UI, name-only PATCH keeps description, duplicates, delete in use | UI edit adds payments:view to E2E-Finance? no — to a temp role; PATCH {name} keeps description; duplicate name (other case) -> 409; delete role assigned to users -> 409 "assigned to N user(s)"; delete unused -> 200 | description kept after name-only PATCH: expected keep me, got null; duplicate name other case: expected 409, got 200<br>⚠ PATCH /api/roles/[id] with only a name clears the description | Fail | `screens/J9-18.png`<br>`api/J9-18.json` |

### J10

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J10-01 | login messages in the UI: wrong password, unknown email, deactivated, success | wrong password and unknown email both "Invalid email or password" (no enumeration); deactivated (right password) "This account has been deactivated..."; button disabled until both fields filled; success -> dashboard | as expected (4 checks) | Pass | `screens/J10-01-deactivated.png`<br>`screens/J10-01.png` |
| J10-02 | throttle: 5 failures lock the email for 15 min even with the right password; success rese… | failures 1-5 -> 401; 6th attempt with the CORRECT password -> 429 "Too many attempts..."; login_throttle lockedUntil ~ now+15 min | as expected (3 checks) | Pass | `api/J10-02.json` |
| J10-03 | per-IP rate limit: 21st login attempt in a minute from one IP -> 429 | with X-Real-Ip set (as Traefik does), attempts 1-20 pass the limiter, the 21st -> 429; different IP unaffected | as expected (3 checks) | Pass | `api/J10-03.json` |
| J10-04 | Remember me (7 days) vs session-only (8 h) vs admin (4 h, never remembered) | staff remember=true -> cookie Max-Age 604800, expiresAt +7d; remember=false -> no Max-Age, +8h; admin remember=true -> no Max-Age, +4h | as expected (3 checks) | Pass | `api/J10-04.json` |
| J10-05 | idle timeouts: staff 1 h (session-only), 24 h (remembered), admin 30 min | lastSeenAt moved back (UTC): staff session-only 59 min ok / 61 min 401; remembered 23 h ok / 25 h 401; admin 29 min ok / 31 min 401 | as expected (1 checks) | Pass | `api/J10-05.json` |
| J10-06 | background polling (/api/notifications) does not keep a session alive; real activity does | lastSeenAt 10 min old: GET /api/notifications leaves it unchanged; GET /api/auth/me refreshes it (writes are throttled to every 5 min) | as expected (3 checks) | Pass | `api/J10-06.json` |
| J10-07 | logout revokes the server session; the old cookie stops working | UI Log out -> /login; sessions.revokedAt set; replaying the old cookie -> 401 | as expected (1 checks) | Pass | `screens/J10-07.png` |
| J10-08 | while logged in elsewhere: deactivation, role change and password change end the session | each admin action -> the user's next request 401; the open page lands on /login?expired=1 with "Your session has expired"; role (permission set) change without account-role change applies at once without logout | as expected (6 checks) | Pass | `screens/J10-08-deactivated-idle-page.png`<br>`screens/J10-08-deactivated-new-navigation.png` |

### J11

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J11-01 | required and whitespace-only fields are refused on every create endpoint | every endpoint -> 400 with a sentence naming the field; nothing written; never 500 | as expected (19 checks) | Pass | `api/J11-01.json` |
| J11-02 | negative, zero, huge and over-precise money values | negative and zero amounts -> 400 everywhere; huge values refused or capped consistently; a payment with sub-cent precision is refused or stored to cents | variation 1e15 refused (contract is capped at 1e11): expected true, got 200; expense line 1e15 refused (cost-plus caps at 1e11): expected true, got 200; sub-cent payment refused or stored to cents: expected true, got {"status":200,"stored":100.123456}<br>⚠ no upper cap on variation amount (200) / expense line amount (200) — 1e15 accepted, while contract and cost-plus amounts cap at 1e11 | Fail | `api/J11-02.json`<br>`traces/j11-negative-input-J11-02--cfbd4-d-over-precise-money-values/trace.zip` |
| J11-03 | long strings, NUL bytes, malformed JSON, wrong types (X-02 regression) | 121-char names / 1001-char notes -> 400 "... must be N characters or fewer"; NUL -> 400; malformed JSON -> 400 "Invalid request body" (X-02 was 500); array for object -> 400; never 500 | as expected (7 checks) | Pass | `api/J11-03.json` |
| J11-04 | HTML and script in text fields render as plain text (UI) | supplier named <img src=x onerror=...> and a variation description with <script> show literally; no dialog/alert fires; no injected element in the DOM | as expected (4 checks) | Pass | `screens/J11-04-supplier.png`<br>`screens/J11-04.png` |
| J11-05 | Sinhala / Tamil text: stored, shown and searchable | supplier "ලංකා සිමෙන්ති — இலங்கை சீமெந்து" saved byte-exact; shown on its detail page and in the API list; duplicate check still applies | as expected (3 checks) | Pass | `screens/J11-05.png`<br>`api/J11-05.json` |
| J11-06 | double-click submit creates one record (UI) | double-clicking Add supplier and Record payment results in exactly one supplier and one payment | as expected (2 checks) | Pass | `screens/J11-06.png` |
| J11-07 | browser back after submit and refresh mid-form do not create anything | create variation, press Back, page reloads from cache without resubmitting (count +1 only); fill Add variation then refresh -> nothing saved | as expected (2 checks) | Pass | `screens/J11-07.png` |
| J11-08 | two sessions on one record: last write wins cleanly; concurrent payments never overpay | two admins rename one supplier at once -> both 200, final name is one of them; 5 parallel milestone payments of 400,000 against a 750,000 balance -> at most 750,000 accepted; 3 parallel expense payments of 60 against a … | expense never overpaid: expected true, got {"ePaid":180,"statuses":[200,200,200]}<br>⚠ concurrent expense payments overpaid an expense: 100.00 owed, 180 paid (200,200,200) — no row lock (AUTHZ-VULN-03 still open) | Fail | `api/J11-08.json`<br>`traces/j11-negative-input-J11-08--c2a5b-rent-payments-never-overpay/trace.zip` |

### J12

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J12-01 | viewport 1440px: no horizontal page scroll, content visible, no console errors | at 1440px every key page fits the width (document scrollWidth <= viewport), main content visible, no console/page errors | as expected (20 checks) | Pass | `api/J12-01.json`<br>`screens/J12-01-*.png` |
| J12-02 | viewport 1024px: no horizontal page scroll, content visible, no console errors | at 1024px every key page fits the width (document scrollWidth <= viewport), main content visible, no console/page errors | as expected (20 checks) | Pass | `api/J12-02.json`<br>`screens/J12-02-*.png` |
| J12-03 | viewport 390px: no horizontal page scroll, content visible, no console errors | at 390px every key page fits the width (document scrollWidth <= viewport), main content visible, no console/page errors | as expected (20 checks) | Pass | `api/J12-03.json`<br>`screens/J12-03-*.png` |
| J12-04 | dark mode: toggle persists, text stays readable | toggle sets <html class="dark"> and localStorage vega-theme=dark; survives reload; body text colour contrasts with background (luminance ratio >= 4.5) | as expected (3 checks) | Pass | `screens/J12-04.png` |
| J12-05 | empty states on a new project and on filters with no results | new project: Expenses "No expenses logged yet.", Variations "No variations yet...", BSR "Nothing added for this activity yet."; payments search with no match: "No supplier matches these filters." | as expected (1 checks) | Pass | `screens/J12-05.png` |
| J12-06 | loading state on a slow network shows skeletons, then content (no blank page) | with /api/* delayed 2 s the page shows .animate-pulse skeletons, then the data; never a blank screen | as expected (2 checks) | Pass | `screens/J12-06-loading.png`<br>`screens/J12-06.png` |
| J12-07 | failures are never silent: network error and server refusal both show an error toast | Add supplier with the request aborted -> error toast, dialog stays; duplicate name -> server message shown; project delete that fails -> no "Project deleted" toast | network failure toast: expected true, got ; refused delete is not reported as success: expected true, got Project deleted<br>⚠ a project delete refused by the server still shows "Project deleted" (src/app/projects/page.tsx:233-238 ignores the response) | Fail | `screens/J12-07-network.png`<br>`screens/J12-07.png` |
| J12-08 | tab and filter state survive a refresh (E-09 regression) | project ?tab=expenses stays selected after reload; payments filters (status, category, sort) stay; cost-plus ?tab=expenses stays | as expected (3 checks) | Pass | `screens/J12-08.png` |
| J12-09 | notifications: a milestone due within 7 days appears in the bell | Stage 2 Advance due 2026-11-12 (unpaid) -> "Payment due soon" notification for the main project; overdue one -> "Payment overdue" | as expected (3 checks) | Pass | `screens/J12-09.png`<br>`api/J12-09.json` |
| J12-10 | no CSP violations and LKR formatting consistent across pages | no CSP violation messages on any page; currency always "LKR" (no $, USD, Rs.); money with thousands separators | as expected (2 checks) | Pass | `screens/J12-10.png`<br>`api/J12-10.json` |

### J13

| ID | Scenario | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|
| J13-01 | E-00: health endpoints are public | /api/healthz 200 and /api/ready 200 without a session | as expected (1 checks) | Pass |  |
| J13-02 | E-01: a server refusal on a catalog mutation shows an error, not success | Rename activity with the server answering 500 -> error toast, name unchanged in DB; Add activity with the network dropped -> error message, no uncaught exception | no uncaught exception: expected [], got ["TypeError: Failed to fetch"] | Fail | `screens/J13-02-server-500.png`<br>`screens/J13-02.png` |
| J13-03 | E-03: Log expense date defaults to today | Expense date picker shows today (9 Nov 2026) | as expected (1 checks) | Pass | `screens/J13-03.png` |
| J13-04 | X-07 / ENH-07: ROI on dashboard, project page and report | ENH-07: no ROI % anywhere; a "Project Status" tile = Outstanding (vendors + expenses) − 70 % × Received | dashboard ROI removed: expected null, got OVERALL ROI ; project ROI removed: expected null, got PROJECT ROI +; Project Status tile present: expected true, got Dashboard Income, expense & return across all projects Export OVERALL PAYMENTS RECEIVED LKR 29,510,6… | Fail | `screens/J13-04-dashboard.png`<br>`screens/J13-04.png` |
| J13-05 | run-state check: the main project still has Estimator as a member at the end | project_members row for E2E-Estimator on E2E-Main still present after J9-J12 (guards the J8 test-state note) | as expected (1 checks) | Pass |  |


## 6. Money verification

| Case | Figure | Expected (hand-computed) | UI | API | DB | Match |
|---|---|---|---|---|---|---|
| J3-09 | S1 Advance outstanding after 500k | 1,000,000.00 | — | 1,000,000.00 | — | ✅ |
| J3-10 | S1 Advance received (1.1M + 400k cheque pending) | 1,100,000.00 | — | 1,100,000.00 | 1,100,000.00 | ✅ |
| J3-17 | Variations total | 350,000.00 | 350,000.00 | 350,000.00 | 350,000.00 | ✅ |
| J3-17 | Variations received | 100,000.00 | 100,000.00 | 100,000.00 | 100,000.00 | ✅ |
| J3-17 | Variations cheques pending | 50,000.00 | 50,000.00 | 50,000.00 | — | ✅ |
| J3-17 | Variations outstanding | 200,000.00 | 200,000.00 | 200,000.00 | — | ✅ |
| J3-18 | Main project received | 2,350,000.00 | 2,350,000.00 | 2,350,000.00 | 2,350,000.00 | ✅ |
| J3-18 | Main project outstanding (API; header shows +cheques pending) | 9,850,000.00 | — | 9,850,000.00 | — | ✅ |
| J3-18 | Main project header Outstanding (outstanding + cheques pending) | 9,900,000.00 | 9,900,000.00 | 9,900,000.00 | — | ✅ |
| J3-18 | Main project contract incl. variations | 12,250,000.00 | 12,250,000.00 | 12,250,000.00 | — | ✅ |
| J3-24 | Item A final total (per 100 Sq.ft) | 24,659.44 | — | — | — | ✅ |
| J3-24 | BSR line Item A Ground x200 | 49,318.88 | — | 49,318.88 | — | ✅ |
| J3-25 | Item A grand total | 21,919.50 | 21,919.50 | — | — | ✅ |
| J3-25 | Item A profit 12.5% | 2,739.94 | 2,739.94 | — | — | ✅ |
| J3-25 | Item A final total | 24,659.44 | 24,659.44 | — | — | ✅ |
| J3-27 | BSR line Item A 1st x10 | 2,589.24 | — | 2,589.24 | — | ✅ |
| J3-30 | Expense E1 amount (1250x4 + 333.33x3) | 5,999.99 | 5,999.99 | — | 5,999.99 | ✅ |
| J3-34 | Expense E1 paid | 5,999.99 | — | 5,999.99 | 5,999.99 | ✅ |
| J3-41 | Main project expenses total (income statement) | 124,900.99 | — | 124,900.99 | 124,900.99 | ✅ |
| J4-01 | Payments page total paid (all) | 69,558,260.39 | 69,558,260.39 | 69,558,260.39 | 69,558,260.39 | ✅ |
| J4-01 | Payments page total outstanding (all) | 41,144,912.20 | 41,144,912.20 | 41,144,912.20 | 41,144,912.20 | ✅ |
| J4-18 | Vendor drawer E2E supplier outstanding | 18,933.20 | 18,933.20 | — | 18,933.20 | ✅ |
| J6-02 | Cost plus expense total | 160,000.49 | — | 160,000.49 | 160,000.49 | ✅ |
| J6-02 | Cost plus margin 12% | 19,200.06 | — | 19,200.06 | 19,200.06 | ✅ |
| J6-02 | Cost plus billed total | 179,200.55 | — | 179,200.55 | — | ✅ |
| J6-03 | Cost plus outstanding after 100k + 50k cheque | 29,200.55 | — | 29,200.55 | — | ✅ |
| J6-05 | Cost plus margin 15% | 24,000.07 | — | 24,000.07 | — | ✅ |
| J6-05 | Cost plus billed at 15% | 184,000.56 | — | 184,000.56 | — | ✅ |
| J6-06 | Cost plus list Total billed (CostPlus user) | 184,000.56 | 184,001.00 | 184,000.56 | 184,000.56 | ❌ |
| J7-01 | Dashboard received (admin) | 19,270,625.21 | 29,510,625.00 | 19,270,625.21 | 19,270,625.21 | ❌ |
| J7-01 | Dashboard outstanding (admin) | 155,033,750.11 | 157,052,000.00 | 155,033,750.11 | 155,033,750.11 | ❌ |
| J7-01 | Dashboard expense committed (admin) | 116,361,403.59 | — | 116,361,403.59 | 116,361,403.59 | ✅ |
| J7-03 | Dashboard received (finance) | 0.00 | 0.00 | 0.00 | 0.00 | ✅ |
| J7-03 | Dashboard outstanding (finance) | 0.00 | 0.00 | 0.00 | 0.00 | ✅ |
| J7-03 | Dashboard expense committed (finance) | 0.00 | — | 0.00 | 0.00 | ✅ |
| J7-07 | Dashboard received (viewonly) | 0.20 | 0.00 | 0.20 | 0.20 | ❌ |
| J7-07 | Dashboard outstanding (viewonly) | 1,734,375.10 | 1,734,375.00 | 1,734,375.10 | 1,734,375.10 | ❌ |
| J7-07 | Dashboard expense committed (viewonly) | 1,001.60 | — | 1,001.60 | 1,001.60 | ✅ |


**How to read the ❌ rows in the money table:** every ❌ is a display rule, not a calculation error, and each was checked separately:
- J6-06, J7-07: KPI cards round to whole rupees (184,000.56 → "184,001"; 0.20 → "0"; 1,734,375.10 → "1,734,375") — finding P-28.
- J7-01: the dashboard "Overall" cards add the cost-plus portfolio to the project figures (received 19,270,625.21 + 10,240,000 = **29,510,625**; outstanding 155,033,750.11 + 2,018,250 = **157,052,000**). Case J7-01 checks exactly that and passes.
- Hand computations are in `tests/e2e-handover/lib/calc.ts` (written separately from the app's `src/lib/*`) and in the test comments, e.g. BSR item A: (5,400 + 135 wastage) + 9,000 + 6,750 + 634.50 allowance = 21,919.50; profit 12.5 % = 2,739.94; final 24,659.44 per 100 Sq.ft; rate 246.5944 → Ground × 200 = 49,318.88, 1st (×1.05) × 10 = 2,589.24.
- Rounding drift noted: stage values shown to cents can sum 0.01 below the contract (2,000,000 + 3 × 3,333,333.33 = 11,999,999.99); raw values sum exactly.

## 7. Findings, sorted by severity

Each finding gives page/route, account, steps, expected, actual, evidence, suspected code location, and whether it is new or a regression. Evidence paths are under `evidence-2026-11-09/` (`rerun/…` = clean final pass; others = first pass).

| ID | Severity | Finding |
|---|---|---|
| [P-35](#p-35) | Critical | Concurrent expense payments can overpay an expense (money record corrupted) |
| [P-12](#p-12) | High | Adding a Basic Rate item with an existing code returns a raw 500 |
| [P-27](#p-27) | High | Cost-plus: billed total can drop below what the client has paid; the over-payment is hidden |
| [P-29](#p-29) | High | The Finance role sees an empty dashboard and Payments page again (E-06 reversed) |
| [P-38](#p-38) | High | A project delete that fails is reported as "Project deleted" |
| [P-39](#p-39) | High | Network failure when adding a supplier gives no feedback (uncaught "Failed to fetch") |
| [P-41](#p-41) | High | Basic Price page: promote with a blank price says "Promoted" but nothing is promoted |
| [P-43](#p-43) | High | Two activities created at the same moment: one gets a raw 500 |
| [P-04](#p-04) | Medium | Trade and unit duplicate checks are case-sensitive |
| [P-05](#p-05) | Medium | A unit used only by BSR (activity) items can be deleted |
| [P-08](#p-08) | Medium | Deleting a supplier used only by cost-plus expenses is allowed and silently unlinks them |
| [P-11](#p-11) | Medium | Deleting a Basic Rate item leaves its source draft stuck as "promoted" |
| [P-13](#p-13) | Medium | Editing a promoted draft's price makes Basic Price and Basic Rate disagree |
| [P-16](#p-16) | Medium | Stage update with "Expand contract & save" silently drops dates sent in the same request |
| [P-17](#p-17) | Medium | "Outstanding" and "Contract value" mean different things on different screens for the same project |
| [P-18](#p-18) | Medium | Exact final expense instalment can be refused as an over-payment (float comparison) |
| [P-21](#p-21) | Medium | UAT ENH-04 not delivered as written: no selective clone of expenses |
| [P-22](#p-22) | Medium | Sinhala and Tamil text is garbled in PDF exports |
| [P-23](#p-23) | Medium | UAT ENH-07 not delivered: ROI still shown, no "Project Status" tile |
| [P-25](#p-25) | Medium | Expenses with no vendor are missing from the Payments page totals |
| [P-30](#p-30) | Medium | Price comparison: an item visible in the list opens "Item not found" for users without project access |
| [P-31](#p-31) | Medium | Login is case-sensitive on email, although emails are unique case-insensitively |
| [P-32](#p-32) | Medium | Editing a user is not atomic: a refused request still saves part of the change |
| [P-42](#p-42) | Medium | Basic Rate page: rate 0 says "Item updated" but keeps the old rate |
| [P-01](#p-01) | Low | Supplier and sub-contractor detail pages fire two 404 API calls on every visit |
| [P-02](#p-02) | Low | `prisma/seed-cost-plus.ts` cannot run on a freshly seeded database |
| [P-03](#p-03) | Low | Add/Edit user: first role checkbox is announced with the whole "Roles" group text |
| [P-06](#p-06) | Low | Category label can be saved blank |
| [P-07](#p-07) | Low | PATCH on a non-existent supplier, sub-contractor or activity returns 200 |
| [P-10](#p-10) | Low | Promoting a draft with a code already in use says "This draft has already been promoted." |
| [P-14](#p-14) | Low | Price history modal shows money without 2 decimals |
| [P-15](#p-15) | Low | Project "current stage" accepts any integer |
| [P-19](#p-19) | Low | Expense stage is not checked against the project's stages |
| [P-20](#p-20) | Low | Nested expense/BSR routes ignore the project id in the URL (F-04-02 still open) |
| [P-24](#p-24) | Low | API accepts BSR item codes that belong to no activity; such items are invisible |
| [P-26](#p-26) | Low | Vendor drawer offers "Record a payment" on fully paid expenses |
| [P-28](#p-28) | Low | KPI cards round money to whole rupees |
| [P-33](#p-33) | Low | Roles: renaming clears the description; duplicate names in another case accepted |
| [P-34](#p-34) | Low | Deleting a user with cost-plus payment history gives a generic message |
| [P-36](#p-36) | Low | No upper limit on variation and expense amounts |
| [P-37](#p-37) | Low | Payments keep sub-cent precision |
| [P-40](#p-40) | Low | Dashboard "Expenses by category" cuts money values off |
| [P-09](#p-09) | Info | Company logo is not configurable |

#### Details (same order)

<a id="p-35"></a>
##### P-35 — Critical — Concurrent expense payments can overpay an expense (money record corrupted)
- `POST /api/projects/[id]/expenses/[expenseId]/payments` (UI: expense payment ledger, vendor drawer, supplier page) · E2E-Admin (two sessions) · Known since AUTHZ-VULN-03, never fixed; now reproduced
- Steps: expense of 100.00; send three payments of 60.00 at the same moment from two sessions.
- Expected: at most 100.00 accepted (later ones 400 "would overpay"), as milestone, variation and cost-plus payments do.
- Actual: all three 200; **180.00 recorded as paid on a 100.00 expense**; outstanding −80. Supplier totals, Payments page and dashboard "expense paid" all include the extra 80.
- Cause: read-sum-then-insert with no row lock and no transaction guard: `src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:50-57`. The fix already exists in the codebase: `insertPaymentGuarded()` in `src/lib/incomePayments.ts` (`SELECT … FOR UPDATE` + cents compare), used by every other ledger.
- Likelihood: needs two submissions within milliseconds (two clerks paying one invoice, a retried request, a double-tap on a slow phone). The UI double-click case was safe in testing (J11-06).
- Evidence: `api/J11-08.json`; DB `select sum(amount) from expense_payments where "expenseId" = <race expense>` = 180.

<a id="p-12"></a>
##### P-12 — High — Adding a Basic Rate item with an existing code returns a raw 500
- API `POST /api/projects/[id]/basic-rate` · E2E-Admin · New
- Steps: project has M-001; POST `{code:"M-001", name, cat:"material", unit:"Bag", rate:1}`.
- Expected: 409 `Code "M-001" already exists in this project.` (items POST does this). Actual: 500 "Internal server error".
- Cause: unique violation 23505 not mapped (`src/lib/api.ts:20`); route has no pre-check: `src/app/api/projects/[id]/basic-rate/route.ts:78-81`. Same race exists in `basic-rate/clone/route.ts:49`.
- Reach: API (no project-tab form posts here directly); severity follows the brief's "server 500 = High".
- Evidence: `api/J2-14.json`

<a id="p-27"></a>
##### P-27 — High — Cost-plus: billed total can drop below what the client has paid; the over-payment is hidden
- API `PATCH /api/cost-plus?id=` (margin) and `DELETE /api/cost-plus/expenses?expenseId=` (UI: margin field, expense delete) · E2E-CostPlus · New
- Steps: project billed 179,200.55, client received 150,000; set margin 0 %, delete the paid 100,000 expense.
- Expected: refused (normal projects refuse any edit that leaves a milestone below what was paid — `findUnderpaidMilestone`), or the over-receipt shown as money due back.
- Actual: both 200. Billed total 60,000.49, received 150,000, **outstanding shows 0**; the 89,999.51 the company owes the client appears nowhere. The deleted expense's supplier payments are deleted too.
- Cause: no guard in `src/app/api/cost-plus/expenses/route.ts:128-149` or `src/app/api/cost-plus/route.ts:77-82`; `paymentSettlement` clamps outstanding at 0.
- Evidence: `api/J6-07.json`

<a id="p-29"></a>
##### P-29 — High (needs a client decision) — The Finance role sees an empty dashboard and Payments page again (E-06 reversed)
- `/`, `/payments` · E2E-Finance (dashboard:view, payments:view, priceComparison:view; no project membership) · Regression of E-06
- 2026-09-21: E-06 made these three permissions company-wide, "confirmed with the client". Commit `fcfd636` ("Scope dashboard/reporting routes by project access") re-applied `projectAccessClause` to dashboard and payments.
- Actual now: Finance dashboard — every figure 0, 0 projects; Payments — no vendors; Price comparison list — every project (still company-wide).
- Expected: whichever rule the client confirms, applied the same way on all three. Today a Finance user configured exactly as the Roles screen suggests cannot do their job, and the three screens disagree on scope.
- Evidence: `api/J7-03.json`, `screens/J7-03.png`, `api/J8-04-matrix.json`

<a id="p-38"></a>
##### P-38 — High — A project delete that fails is reported as "Project deleted"
- `/projects` → Delete · E2E-Admin (server response simulated as 403) · New (flagged by code review, confirmed live)
- Steps: open Delete for E2E-Catalog; make `DELETE /api/projects/[id]` return 403 (as it would for a user without delete rights who still has the button through a stale page, or any server error); confirm.
- Expected: error toast with the server message; project stays. Actual: green toast "Project deleted"; the project is still in the database (and reappears on refresh).
- Cause: `deleteProject` ignores the response: `src/app/projects/page.tsx:233-238`. Same pattern: user activate/deactivate toast `src/app/users/page.tsx:277-282`; global Basic Price promote `src/app/basic-price/page.tsx:859`.
- Evidence: `screens/J12-07.png`, `api/J12-07.json`

<a id="p-39"></a>
##### P-39 — High — Network failure when adding a supplier gives no feedback (uncaught "Failed to fetch")
- `/suppliers` → Add supplier · E2E-Admin · E-01 addendum partly still open
- Steps: request aborted (network drop) after confirming Add supplier.
- Expected: error toast ("Could not add … try again"). Actual: nothing — no toast, dialog stays open; browser logs uncaught `TypeError: Failed to fetch`. E-01 (2026-09-21) added `res.ok` checks but thrown network errors are still unhandled on this path.
- Evidence: `screens/J12-07-network.png`, probe log in RUN-LOG
- Offline **Add activity** now shows an error toast (E-01 addendum fixed for that path) but still throws an uncaught `TypeError: Failed to fetch` in the console. Offline **Add supplier** shows nothing at all.

<a id="p-41"></a>
##### P-41 — High — Basic Price page: promote with a blank price says "Promoted" but nothing is promoted
- `/basic-price` (global page) → Promote → clear Price → Promote · E2E-Admin · New (clean pass; the first pass missed it because my toast helper could not see toasts — see RUN-LOG)
- Actual: toast "Promoted to Basic Rate as L-001"; the draft stays `status=draft`, no Basic Rate item exists.
- Cause: the page sends `Number(price)||0` and ignores the API's 400: `src/app/basic-price/page.tsx:859, 902`. (The project-tab promote validates and is correct.)
- Evidence: `rerun/api/J2-16.json`, `rerun/screens/J2-16.png`

<a id="p-43"></a>
##### P-43 — High — Two activities created at the same moment: one gets a raw 500
- `POST /api/activities` (UI: Activities → Add activity, two users) · E2E-Admin · New (clean pass: `[200, 500]`; first pass happened to get distinct codes)
- Cause: next code = max+1 without a lock; the second insert hits the primary key (23505), which is not mapped: `src/app/api/activities/route.ts:27-30`, `src/lib/api.ts:20`.
- Evidence: `rerun/api/J1-26.json`

<a id="p-04"></a>
##### P-04 — Medium — Trade and unit duplicate checks are case-sensitive
- API `POST /api/trades`, `POST /api/units` (also PATCH) · E2E-Admin · New (the brief lists case-insensitive duplicate checks as a delivered feature)
- Steps: create trade "E2E-Trade r3ruz8"; POST `{name:"E2E-TRADE R3RUZ8"}`. Same for units.
- Expected: 409, as for suppliers, sub-contractors and activities.
- Actual: 200; two options differing only in case now appear in every unit/trade dropdown.
- Cause: exact-match check `src/app/api/trades/route.ts:25`, `src/app/api/trades/[id]/route.ts:21`, `src/app/api/units/route.ts:25`, `src/app/api/units/[id]/route.ts:21`.
- Evidence: `api/J1-08.json`, `api/J1-12.json`

<a id="p-05"></a>
##### P-05 — Medium — A unit used only by BSR (activity) items can be deleted
- API `DELETE /api/units/[id]` · E2E-Admin · New
- Steps: create unit U; create a BSR item with unit U (no drafts/rates use U); DELETE the unit.
- Expected: 409 "Still used by …" (rename already cascades to `activity_items.unit`, so the app treats it as a reference).
- Actual: 200; the unit is gone from the dropdowns while BSR items still carry it; editing such an item shows no matching unit.
- Cause: in-use count checks only `basic_price_items` and `base_items`: `src/app/api/units/[id]/route.ts:45-51`.
- Evidence: `api/J1-14.json`

<a id="p-08"></a>
##### P-08 — Medium — Deleting a supplier used only by cost-plus expenses is allowed and silently unlinks them
- API `DELETE /api/suppliers/[id]` (UI: Suppliers → Delete) · E2E-Admin · New
- Steps: pick a supplier referenced only by `cost_plus_expenses` (here "Lanka Cement Distributors", expense `cpe_seed_1_1`, LKR 1,480,000); delete it.
- Expected: 409 "Still used by …", the same protection normal expenses get.
- Actual: 200. `cost_plus_expenses.supplierId` set to NULL (FK `ON DELETE SET NULL`); the expense keeps only the text name, drops out of any supplier view, and cannot be edited without re-picking a supplier (Material requires one). Same gap for sub-contractors.
- Cause: in-use check ignores `cost_plus_expenses`: `src/app/api/suppliers/[id]/route.ts:112-116`, `src/app/api/sub-contractors/[id]/route.ts:69`.
- Evidence: `api/J1-23.json`; DB: `select vendor, "supplierId" from cost_plus_expenses where id='cpe_seed_1_1'` → supplierId NULL.

<a id="p-11"></a>
##### P-11 — Medium — Deleting a Basic Rate item leaves its source draft stuck as "promoted"
- API `DELETE /api/projects/[id]/basic-rate/[code]` · E2E-Admin · New
- Steps: promote draft → M-007; delete M-007 from Basic Rate; try to re-promote or delete the draft.
- Expected: draft returns to draft (or is removed) so it can be re-promoted or deleted.
- Actual: draft keeps `status=promoted`, `promotedCode=M-007`; re-promote → 400 "This draft has already been promoted."; delete → 400 "Only un-promoted drafts can be deleted." The draft is stuck for ever; Basic price tab shows "Promoted" for an item that no longer exists.
- Cause: `src/app/api/projects/[id]/basic-rate/[code]/route.ts:67-70` (and the global `src/app/api/basic-rate/[itemId]/route.ts:77-80`) do not reset `basic_price_items`.
- Evidence: `api/J2-13.json`

<a id="p-13"></a>
##### P-13 — Medium — Editing a promoted draft's price makes Basic Price and Basic Rate disagree
- API `PATCH /api/projects/[id]/basic-price/[draftId]` (UI: Basic price tab → Edit on a promoted row) · E2E-Admin · New
- Steps: draft "Sand river" promoted as M-002 at 18,000; edit the draft price to 19,000.
- Expected: refused for promoted drafts, or Basic Rate M-002 updated (with history), so one item has one price.
- Actual: 200; draft shows 19,000, Basic Rate M-002 stays 18,000, no history entry. (The reverse direction — editing the rate — does sync the draft.)
- Cause: no status check / no sync in `src/app/api/projects/[id]/basic-price/[draftId]/route.ts` PATCH; same in global `src/app/api/basic-price/[draftId]/route.ts:47-49` (which can also move a promoted draft to another project).
- Evidence: `api/J2-15.json`

<a id="p-16"></a>
##### P-16 — Medium — Stage update with "Expand contract & save" silently drops dates sent in the same request
- API `PATCH /api/projects/[id]/stages/[stageId]` with `expandContractTo` · E2E-Admin · New
- Steps: PATCH `{value:1100000, expandContractTo:1850000, startDate:"2026-11-05"}`.
- Expected: contract expanded, value and start date saved (or a 400). Actual: 200, contract and value saved, `startDate` stays NULL.
- Cause: the expand branch returns early: `src/app/api/projects/[id]/stages/[stageId]/route.ts:84-93`.
- Evidence: `api/J3-08.json`

<a id="p-17"></a>
##### P-17 — Medium — "Outstanding" and "Contract value" mean different things on different screens for the same project
- Pages `/projects/[id]` header, project report PDF, dashboard · E2E-Admin · New
- Data: main project, contract 12,000,000, V1 250,000 included in contract, 50,000 cheque in hand.
- Project page header: Contract value 12,250,000 (incl. variation); Outstanding **9,900,000** (adds cheques in hand: `src/app/projects/[id]/client.tsx:226`).
- Project report PDF: Contract value **12,000,000** (variation not included); Outstanding **9,850,000**; Pending cheque clearance 50,000 shown separately.
- API / dashboard / variations strip: outstanding 9,850,000 with cheques separate.
- Expected: one definition per figure on every screen and export. Each figure is arithmetically consistent with its own definition (hand-checked), so this is misleading UI rather than wrong maths; a client comparing the PDF with the screen sees two different numbers.
- Evidence: `screens/J3-18.png`, `screens/J3-42-pdf-page1.png`, `api/J3-18-checks.json`, `exports/J3-42-pdf.txt`

<a id="p-18"></a>
##### P-18 — Medium — Exact final expense instalment can be refused as an over-payment (float comparison)
- API `POST /api/projects/[id]/expenses/[expenseId]/payments` (UI: Payments — vendor ledger) · E2E-Admin · New
- Steps: expense of 0.30; pay 0.10 (200), then 0.20.
- Expected: 200, expense Completed. Actual: 400 "This payment would overpay the expense — it exceeds the outstanding balance." (0.1 + 0.2 > 0.3 in float8). 700.10 + 300.20 on 1,000.30 happened to pass.
- Cause: raw float compare, no cents rounding, no row lock: `src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:50-57` (milestone/variation/cost-plus ledgers use `insertPaymentGuarded` with cents rounding and `FOR UPDATE`). Same compare in expense PATCH `src/app/api/projects/[id]/expenses/[expenseId]/route.ts:30`.
- Impact: some cent combinations cannot be settled exactly; the expense stays "Partial" with a residual. Concurrent payments can also both pass (AUTHZ-VULN-03 still open).
- Evidence: `api/J3-35.json`

<a id="p-21"></a>
##### P-21 — Medium — UAT ENH-04 not delivered as written: no selective clone of expenses
- `/projects/[id]?tab=expenses` · E2E-Admin · UAT still open
- ENH-04 asks to pick a source project, tick expenses (with Select all), clone only those, with new voucher numbers and a count confirmation. No such control exists. Commit `56cd2ef` delivered a selective **Basic Rate** clone instead (tested J3-20/21, works).
- Evidence: `screens/J3-39.png`

<a id="p-22"></a>
##### P-22 — Medium — Sinhala and Tamil text is garbled in PDF exports
- Project report PDF (and other jsPDF exports) · E2E-Admin · New
- Steps: client name "E2E Client — සිංහල தமிழ்" (saved and shown correctly in the app); export project report.
- Actual: PDF shows "E 2 E  C l i e n t — Ã Ò , Ä ½  ¤ ® ¿ ´ Î" (letter-spaced, mojibake). Sri Lankan client/site/payee names in Sinhala or Tamil cannot be printed.
- Cause: jsPDF standard fonts have no Sinhala/Tamil glyphs; no Unicode font embedded (`src/lib/pdfTemplate.ts`, `src/lib/exportPdf.ts`, `src/lib/exportProjectReport.ts`).
- Evidence: `screens/J3-42-pdf-page1.png`, `exports/J3-42-*.pdf`

<a id="p-23"></a>
##### P-23 — Medium — UAT ENH-07 not delivered: ROI still shown, no "Project Status" tile
- Dashboard ("Overall ROI" card), project page ("Project ROI" card), project report PDF ("ROI (PAID BASIS)") · UAT still open (confirmed again in J7/J13)
- ENH-07: remove ROI %, add a Project Status tile = Outstanding (vendors + expenses) − 70% × Received.
- Evidence: `screens/J3-42-pdf-page1.png`; dashboard in J7.

<a id="p-25"></a>
##### P-25 — Medium — Expenses with no vendor are missing from the Payments page totals
- Page `/payments` · E2E-Admin · New
- Data: 11 expenses (LKR 5,658,200 owed, all outstanding) saved with "No supplier / not specified" (and 2 sub-contractor-category expenses without a sub-contractor) — a choice the Log expense form allows.
- Expected: "Total outstanding" covers every unpaid expense, or the page shows the remainder somewhere.
- Actual: they are in no vendor tab and not in Total outstanding / Total paid (the groups drop rows whose vendor key is empty). The "No supplier items" tab only lists line items sourced from un-linked Basic Rate items. Company payables on this page are understated by LKR 5,658,200 with nothing telling the user.
- Cause: `src/app/api/payments/route.ts` groups CTE `where vendorKey is not null and vendorKey <> ''` (see `src/lib/paymentFilters.ts`).
- Evidence: `api/J4-01.json`, `screens/J4-01.png`

<a id="p-30"></a>
##### P-30 — Medium — Price comparison: an item visible in the list opens "Item not found" for users without project access
- `/suppliers/compare` → "View price history" (`/suppliers/compare/item`) · E2E-Finance · New
- Cause: list `src/app/api/suppliers/price-comparison/route.ts:29-40` is company-wide; item route `.../price-comparison/item/route.ts` filters by project access. Finance sees "E2E-Compare cement" in the list (3 projects), clicks through, gets "Item not found". Admin works.
- Evidence: `api/J8-04-matrix.json`, `screens/J8-finance-_suppliers_compare_item_*.png`

<a id="p-31"></a>
##### P-31 — Medium — Login is case-sensitive on email, although emails are unique case-insensitively
- `/login`, `POST /api/auth/login` · E2E-Estimator · New
- Steps: account `estimator.r3ruz8@e2e.test`; log in as `ESTIMATOR.R3RUZ8@E2E.TEST` with the right password.
- Expected: 200 (the app already refuses a second account differing only in case). Actual: 401 "Invalid email or password", and the failure counts towards the 5-attempt lock-out. Users on phones with auto-capitalised first letters get locked out.
- Cause: exact match `select … from users where email = ?` in `src/lib/auth.ts:264` via `src/app/api/auth/login/route.ts:89`.
- Evidence: `api/J9-12.json`

<a id="p-32"></a>
##### P-32 — Medium — Editing a user is not atomic: a refused request still saves part of the change
- `PATCH /api/users/[email]` (UI: Users → Edit) · E2E-Admin · New
- Steps: PATCH `{name:"E2E-Tmp half-saved", roleIds:["no-such-role"]}`.
- Expected: 4xx and nothing saved. Actual: 409 (generic FK message) but the name is saved. With a password change in the same request the password is saved but the user's other sessions are not revoked (revocation runs after the failing batch).
- Cause: separate non-transactional updates, roles/permissions batch last: `src/app/api/users/[email]/route.ts:113-144`.
- Evidence: `api/J9-17.json`

<a id="p-42"></a>
##### P-42 — Medium — Basic Rate page: rate 0 says "Item updated" but keeps the old rate
- `/basic-rate` (global page) → Edit → Rate 0 → Save · E2E-Admin · New
- Actual: toast "Item updated — timestamped & logged"; rate stays 18,000. A blank rate does the same. The user is told their change was saved.
- Cause: `src/app/basic-rate/page.tsx:158` (and `src/app/projects/[id]/client.tsx:4589`) silently keep the old rate for 0/blank.
- Evidence: `rerun/api/J2-17.json`

<a id="p-01"></a>
##### P-01 — Low — Supplier and sub-contractor detail pages fire two 404 API calls on every visit
- Page: `/suppliers/[id]`, `/sub-contractors/[id]` · Account: E2E-Admin · New
- Steps: log in as admin, open any supplier (e.g. `/suppliers/seedfix_sup_2`) or sub-contractor detail page.
- Expected: only that vendor's API calls; no 4xx in the console.
- Actual: `GET /api/projects/<supplierId>/basic-rate` and `GET /api/projects/<supplierId>/basic-price` both return 404; the browser console logs two "Failed to load resource: 404" errors.
- Cause: `src/components/CatalogProvider.tsx:71-75` reads `useParams().id` as a project id on every route except `/cost-plus`, so a vendor id is sent as a project id.
- Impact: console noise and two wasted requests per visit; error monitoring would log false 404s. No data shown wrongly (the page ignores the empty catalog).
- Evidence: `evidence-2026-11-09/api/J0-03.json`, `screens/J0-03-Supplier_detail.png`, `screens/J0-03-Sub_contractor_detail.png`

<a id="p-02"></a>
##### P-02 — Low — `prisma/seed-cost-plus.ts` cannot run on a freshly seeded database
- Steps: fresh DB → `npm run db:migrate` → `npm run db:seed` → `npx tsx scripts/seed-demo-payments.ts` → `npx tsx prisma/seed-cost-plus.ts`.
- Expected: cost-plus demo data seeded.
- Actual: `Error: Seed needs suppliers "Lanka Cement Distributors" — run the main seed first`. No seed script creates 7 of the suppliers it needs (Lanka Cement Distributors, Ceylon Steel Suppliers, K. Silva & Crew, Kottawa Plant Hire, Lanka Lorry Transport, Highland Quarry & Metal Suppliers, Masonry Crew Services). `prisma/seed.ts` creates no suppliers at all.
- Cause: `prisma/seed-cost-plus.ts:73-77` (`lookup`) assumes vendors that exist only on some other database.
- Impact: the client's team cannot reproduce the cost-plus demo from the repo. Workaround used: inserted the 7 suppliers by hand.
- Evidence: RUN-LOG.md 09:5x entry.

<a id="p-03"></a>
##### P-03 — Low — Add/Edit user: first role checkbox is announced with the whole "Roles" group text
- Page `/users` (Add user, Edit user) · E2E-Admin · New
- Steps: open Add user with roles present; inspect accessibility tree.
- Expected: each role checkbox is named by its role.
- Actual: the first role's checkbox is named "Roles E2E-Estimator … E2E-Finance … E2E-CostPlus … E2E-ViewOnly …"; same for "Direct permissions". Screen-reader users hear the wrong label; automation by role name fails.
- Cause: `Field` wraps the control group in a `<label>`, and each checkbox has its own `<label>` inside it (nested labels): `src/app/users/page.tsx:620`, `:634`, `:736`, `:750`.
- Evidence: `traces/j00-accounts-J9-05-*/error-context.md` (first attempt)

<a id="p-06"></a>
##### P-06 — Low — Category label can be saved blank
- API `PATCH /api/categories/[key]` · E2E-Admin · New
- Steps: PATCH `{label:""}`.
- Expected: 400 "Label is required" (create enforces it).
- Actual: 200; category shows with an empty name in filters and badges. The Field options page also does not block it (no trim, no confirm).
- Cause: `src/app/api/categories/[key]/route.ts:9-10,22` (label not trimmed/min-checked); `src/app/settings/field-options/page.tsx:138`.
- Evidence: `api/J1-05.json`

<a id="p-07"></a>
##### P-07 — Low — PATCH on a non-existent supplier, sub-contractor or activity returns 200
- API `PATCH /api/suppliers/[id]`, `/api/sub-contractors/[id]`, `/api/activities/[code]` · E2E-Admin · New
- Expected: 404. Actual: 200 with the echoed body; nothing written. A stale screen (record deleted by another user) shows "renamed" though nothing changed.
- Cause: no row-count check: `src/app/api/suppliers/[id]/route.ts:99`, `src/app/api/sub-contractors/[id]/route.ts:60`, `src/app/api/activities/[code]/route.ts:21,35`.
- Evidence: `api/J1-17.json`, `api/J1-22.json`, `api/J1-25.json`

<a id="p-10"></a>
##### P-10 — Low — Promoting a draft with a code already in use says "This draft has already been promoted."
- API `POST /api/projects/[id]/basic-price/[draftId]/promote` (UI: Promote modal, code edited by hand) · E2E-Admin · New
- Steps: Basic Rate has M-001; promote a fresh draft with code M-001.
- Expected: message that code M-001 is already used. Actual: 400 "This draft has already been promoted." although the draft is still a draft; user cannot tell what to fix.
- Cause: every 23505 is mapped to the same message: `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts:44`.
- Evidence: `api/J2-07.json`

<a id="p-14"></a>
##### P-14 — Low — Price history modal shows money without 2 decimals
- UI `/projects/[id]?tab=basic-rate` → View price history · E2E-Admin · New
- Expected: LKR to 2 decimals, as the rest of the catalog ("2,450.00", "2,600.50").
- Actual: "2,450", "2,600.5", change "+150.5".
- Evidence: `screens/J2-09.png`, `api/J2-09-checks.json`

<a id="p-15"></a>
##### P-15 — Low — Project "current stage" accepts any integer
- API `PATCH /api/projects/[id]` · E2E-Admin · New
- Steps: PATCH `{curStage: 0}` and `{curStage: 9}` on a 4-stage project. Expected 400. Actual 200 both; the project report shows "Stage 9 of 4" and dashboard progress divides by it.
- Cause: `src/app/api/projects/[id]/route.ts:28` (int only, no 1..stages range).
- Evidence: `api/J3-03.json`

<a id="p-19"></a>
##### P-19 — Low — Expense stage is not checked against the project's stages
- API `POST/PATCH /api/projects/[id]/expenses` · New
- Steps: stage 99 on a 4-stage project → 200. Stage costs tab then has an expense in no stage. Cause: `src/lib/expenseInput.ts:23`.
- Evidence: `api/J3-36.json`

<a id="p-20"></a>
##### P-20 — Low — Nested expense/BSR routes ignore the project id in the URL (F-04-02 still open)
- API `PATCH /api/projects/<other project>/expenses/<expenseId>` → 200 and edits the expense in its real project. Access is checked against the real project, so no cross-project leak was possible in testing (see J8), but URLs/logs/audit can name the wrong project.
- Cause: `src/app/api/projects/[id]/expenses/[expenseId]/route.ts:16,51`, `.../payments/route.ts:16,34`, `.../payments/[paymentId]/route.ts:6`, `src/app/api/projects/[id]/bsr/[lineId]/route.ts:13,30`.
- Evidence: `api/J3-36.json`

<a id="p-24"></a>
##### P-24 — Low — API accepts BSR item codes that belong to no activity; such items are invisible
- API `POST /api/projects/[id]/items` with code "E2E.A123" → 200; the item and its BSR line exist but appear under no activity on the BSR tab and are missing from the BSR export (the UI groups by the code's activity prefix). Found by a test-data mistake; recorded because the API should reject codes the UI cannot place.
- Cause: `code` is free text in `src/app/api/projects/[id]/items/route.ts`.

<a id="p-26"></a>
##### P-26 — Low — Vendor drawer offers "Record a payment" on fully paid expenses
- `/payments` → vendor drawer · E2E-Admin · New
- Actual: 15 "Record a payment" buttons for 11 unpaid + 4 completed expenses of the E2E supplier. The supplier detail page hides it for completed vouchers; the API then refuses any amount (over-payment), so the user gets an error after opening the form. Also shown without checking `projects:edit`.
- Cause: `src/components/payments/VendorDrawer.tsx:171`; same on the unlinked tab `src/app/payments/page.tsx:432`.
- Evidence: `api/J4-18.json`, `screens/J4-18.png`

<a id="p-28"></a>
##### P-28 — Low — KPI cards round money to whole rupees
- Cost-plus list and dashboard tab, project header, dashboard · New
- Actual: expense 160,000.49 shows "LKR 160,000"; billed 184,000.56 shows "LKR 184,001" (`fmt0`). Tables on the same pages show cents. Brief standard: LKR to 2 decimals; a reader adding cards will be off by rupees.
- Evidence: `screens/J6-06.png`, `api/J6-05-checks.json`

<a id="p-33"></a>
##### P-33 — Low — Roles: renaming clears the description; duplicate names in another case accepted
- `PATCH /api/roles/[id]` with only `name` → description NULL (`src/app/api/roles/[id]/route.ts:65-66`). `POST /api/roles` with the same name in upper case → 200 (case-sensitive; users/suppliers/activities are case-insensitive). The Roles page always sends both fields, so the UI path is not affected by the first part.
- Evidence: `api/J9-18.json`

<a id="p-34"></a>
##### P-34 — Low — Deleting a user with cost-plus payment history gives a generic message
- `DELETE /api/users/[email]` for E2E-CostPlus → 409 "This record refers to something that no longer exists, or is still in use elsewhere." Deletion is correctly blocked, but the user is not told to deactivate instead (the audit pre-check misses cost-plus, project ownership, expense payments). Cause `src/app/api/users/[email]/route.ts:175-185`. Evidence `api/J9-15.json`.

<a id="p-36"></a>
##### P-36 — Low — No upper limit on variation and expense amounts
- `POST /api/projects/[id]/variations` and expense line items accept 1,000,000,000,000,000; contract and cost-plus amounts are capped at 100,000,000,000. A typo (extra zeros) passes straight into the dashboard totals. Evidence `api/J11-02.json`.

<a id="p-37"></a>
##### P-37 — Low — Payments keep sub-cent precision
- A milestone payment of 100.123456 is stored as 100.123456 (not 100.12 and not refused). Money elsewhere is shown to cents, so sums of stored values drift from what is displayed. Cause: no cents rounding/validation on payment amounts (`src/lib/incomePayments.ts`, payment schemas). Evidence `api/J11-02.json`.

<a id="p-40"></a>
##### P-40 — Low — Dashboard "Expenses by category" cuts money values off
- `/` at 1440 px · E2E-Admin · New
- Actual: "LKR 67,351,2…", "LKR 33,550,0…", "LKR 13,903,9…" — the figure itself is truncated with an ellipsis, so the reader cannot see the amount. Evidence `screens/J13-04-dashboard.png`.

<a id="p-09"></a>
##### P-09 — Info — Company logo is not configurable
- `/settings/company-profile` has name/tagline/address/phone/email/registration only; no logo upload. Logo on PDFs is a fixed asset (checked in J3 exports). Brief asked for logo coverage; recorded as not available rather than a defect.

#### Info (no defect)
- Custom-text expense lines carry no category, so an expense typed by hand for a supplier is stored as category **Other** (derived), even for cement. The dashboard "Expenses by category" puts these under Other.
- `POST /expenses` response echoes the client-sent `category`, not the derived one stored.
- A project with recorded client and expense payments is deleted after one confirm dialog; all money rows go with it (cascade verified clean, invoice counters untouched).
- Stage values shown to cents can sum to 0.01 less than the contract (2,000,000 + 3 × 3,333,333.33 = 11,999,999.99); raw values sum exactly.
- Logo on PDFs is a fixed image (VEGA HOMES); company name/address come from the company profile (verified).


## 8. Regression status

### 2026-09-21 findings (the previous report numbers them E-00…E-09; there is no E-10)

| ID | Was | Status now | Proof |
|---|---|---|---|
| E-00 | `/api/healthz`, `/api/ready` needed a session | ✅ Still fixed | J0-01, J13-01 |
| E-01 | Mutations did not check the response | ⚠ **Partly open.** Server refusals now show an error on the catalog (J13-02 server-500 check passes); but a dropped network on Add supplier is silent (P-39), Add activity still throws an uncaught error, and the same "success regardless" pattern remains on project delete (P-38), global Basic Price promote (P-41), global Basic Rate edit (P-42) and user activate/deactivate. The 2026-09-21 report had flagged the global Basic Price/Rate pages as "not audited". | J12-07, J13-02, J2-16, J2-17 |
| E-02 | Unit rename missed BSR items | ✅ Still fixed | J1-13 |
| E-03 | Expense date hard-coded | ✅ Still fixed (defaults to today) | J13-03, J3-30 |
| E-04 | Retracted (ownership transfer UI exists) | ✅ Confirmed: transfer both ways through `/settings/project-access` | J3-06 |
| E-05 | Admin pages showed editable UI to non-admins | ✅ Still fixed for all 7 pages and 6 non-admin accounts | J8-02…J8-07 |
| E-06 | Finance saw zeros (dashboard/payments/price comparison) | ❌ **Regressed** — commit `fcfd636` re-scoped dashboard and payments by project access; price comparison stays company-wide | P-29, J7-03 |
| E-07 | Concurrent promote → 500 | ✅ Still fixed (one 200, one clean 400, one base item) | J2-06 |
| E-08 | Retracted (idle timeout works) | ✅ Confirmed at the boundaries: staff 59/61 min, remembered 23/25 h, admin 29/31 min | J10-05 |
| E-09 | Project tab lost on refresh | ✅ Still fixed (also payments filters and cost-plus tab) | J12-08 |

Other items carried in the 2026-09-21 report: **X-02** malformed JSON → 500: ✅ fixed (400 "Invalid request body", J11-03). **X-07** ROI % blow-up: the % is still shown ("−62.4 % on paid expense"), tracked as ENH-07/P-23. **F-04-02** URL project id ignored: still open (P-20). **AUTHZ-VULN-03** expense payment race: still open and now proven to corrupt data (P-35). **CSRF**: ✅ verified (foreign/missing Origin → 403, J8-10).

### UAT feedback (UAT_Feedback_Enhancements_Vega_Construction.docx)

| ID | Requirement | Status | Proof |
|---|---|---|---|
| ENH-01 | Edit and delete expenses, confirm on delete, totals recalc, per role | ✅ Resolved | J3-36, J3-38, J8 |
| ENH-02 | "Other" vendor type | ✅ Resolved (lists, payments "Other payees" tab, history) | J3-33, J4-19 |
| ENH-03 | Stage payments in instalments, status from the sum, cap, view/correct | ✅ Resolved | J3-09…J3-15 |
| ENH-04 | Selective clone of **expenses** from another project | ❌ **Still open** — only a Basic Rate clone exists | P-21, J3-39 |
| ENH-05 | Unique invoice numbers system-wide | ✅ Resolved (system-issued, sequential, never reused, per month) | J3-32 |
| ENH-06 | Amount = quantity × unit rate | ✅ Resolved | J3-30 |
| ENH-07 | Remove ROI %, add Project Status tile | ❌ **Still open** — ROI on dashboard, project page and project report; no Project Status tile | P-23, J13-04 |
| ENH-08 | Pending payment for the latest/current stage | ✅ Resolved | J7-05 |
| ENH-09 | Edit expense with invoice number locked (UI and API) | ✅ Resolved | J3-37, J3-32 |

## 9. Not tested, and why

- **Browsers other than Chrome** (Edge/Firefox/Safari, real phones): only Chromium was available; 390 px was emulated.
- **PDF import** of Basic Rate (Excel import tested); **dashboard portfolio export**, **cost-plus exports** (BSR, payments schedule, income statement and project report were tested).
- **Absolute session expiry by waiting** 4 h / 8 h / 7 d: verified through `expiresAt` values and cookie Max-Age, not wall-clock.
- **Real Traefik in front of the app**: the per-IP rate limit was tested by sending `X-Real-Ip` directly, as Traefik would.
- **Company logo upload**: the feature does not exist (P-09); the fixed logo on PDFs was checked.
- **Stage costs tab** and **Basic Price/Rate global page add/edit forms**: smoke-tested and partly exercised, not every field.
- **Screen readers**: only the accessibility tree was inspected (P-03 found that way).
- **Load/performance and security scanning**: covered by the separate reports in `pre-handover-test/performance` and `pre-handover-test/security`.
- **MFA**: not part of the product.

## 10. Test totals

Clean final pass (fresh database, single uninterrupted run, 9.8 minutes):


| Journey | Total | Passed | Failed | Blocked |
|---|---|---|---|---|
| J0 | 3 | 2 | 1 | 0 |
| J1 | 24 | 15 | 9 | 0 |
| J2 | 17 | 10 | 7 | 0 |
| J3 | 41 | 34 | 7 | 0 |
| J4 | 20 | 19 | 1 | 0 |
| J5 | 5 | 5 | 0 | 0 |
| J6 | 8 | 7 | 1 | 0 |
| J7 | 7 | 7 | 0 | 0 |
| J8 | 11 | 10 | 1 | 0 |
| J9 | 15 | 12 | 3 | 0 |
| J10 | 8 | 8 | 0 | 0 |
| J11 | 8 | 6 | 2 | 0 |
| J12 | 10 | 9 | 1 | 0 |
| J13 | 5 | 3 | 2 | 0 |
| **Total** | **182** | **147** | **35** | **0** |


Notes on the totals:
- **J3-04** failed in the clean pass because of a test-script error (a regex escape lost during an edit; fixed in the file). The same case passed in the first pass, and its end state (Estimator a member of E2E-Main) was also reached through J3-06 in the clean pass.
- **First pass** (`evidence-2026-11-09/`, run journey by journey while the suite was written): about 170 cases. Two cases (J2-16, J2-17) passed there only because an early version of the toast helper could not see toasts; the clean pass caught them (P-41, P-42). Every other first-pass test-authoring mistake is listed in `RUN-LOG.md` and was not reported as a finding.
- Case IDs J9-01…J9-10 (account creation through the UI) are in `j00-accounts.spec.ts` and counted under J9.

## 11. How to re-run the suite

The suite lives in the app repo at `tests/e2e-handover/` (uncommitted). Full instructions are in `tests/e2e-handover/README.md`; in short:

```bash
# 1. throwaway local database
docker run -d --name vega-e2e-pg -e POSTGRES_PASSWORD=e2e_local_only -e POSTGRES_DB=vega_e2e \
  -e TZ=UTC -p 127.0.0.1:5441:5432 postgres:17-alpine
export DATABASE_URL="postgresql://postgres:e2e_local_only@127.0.0.1:5441/vega_e2e"   # always export: Prisma ignores .env.local
npm run db:migrate && npm run db:seed
# .env.local needs the same DATABASE_URL and a 32+ byte SESSION_SECRET
npx tsx scripts/seed-demo-payments.ts
# until P-02 is fixed: insert the 7 suppliers listed in the README, then
npx tsx prisma/seed-cost-plus.ts
# 2. app
npm run build && npx next start -p 3200
# 3. suite (needs Chrome, and Python with pypdf for the PDF checks)
export E2E_DATABASE_URL="$DATABASE_URL" PW_BASE_URL=http://localhost:3200 E2E_EVIDENCE_DIR=/path/to/evidence
npx playwright test -c tests/e2e-handover
node tests/e2e-handover/tools/report-tables.mjs "$E2E_EVIDENCE_DIR" > tables.md
```

Use a fresh database each time. The suite refuses any database host but localhost. Every created record is prefixed `E2E-` and listed in `<evidence>/db/ledger.jsonl`.

---
Related files: `RUN-LOG.md` (timestamped log, environment details, test-authoring mistakes), `CLEANUP.md` (ledger and cleanup), `TEST_PLAN.md`, `FINDINGS-DRAFT.md` (working notes), `evidence-2026-11-09/` (first pass) and `evidence-2026-11-09/rerun/` (clean final pass).
