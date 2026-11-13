# Findings draft (working notes, folded into the report at the end)

IDs: `P-xx` (pre-handover 2026-11-09). Severity per the brief.

## P-01 — Low — Supplier and sub-contractor detail pages fire two 404 API calls on every visit
- Page: `/suppliers/[id]`, `/sub-contractors/[id]` · Account: E2E-Admin · New
- Steps: log in as admin, open any supplier (e.g. `/suppliers/seedfix_sup_2`) or sub-contractor detail page.
- Expected: only that vendor's API calls; no 4xx in the console.
- Actual: `GET /api/projects/<supplierId>/basic-rate` and `GET /api/projects/<supplierId>/basic-price` both return 404; the browser console logs two "Failed to load resource: 404" errors.
- Cause: `src/components/CatalogProvider.tsx:71-75` reads `useParams().id` as a project id on every route except `/cost-plus`, so a vendor id is sent as a project id.
- Impact: console noise and two wasted requests per visit; error monitoring would log false 404s. No data shown wrongly (the page ignores the empty catalog).
- Evidence: `evidence-2026-11-09/api/J0-03.json`, `screens/J0-03-Supplier_detail.png`, `screens/J0-03-Sub_contractor_detail.png`

## P-02 — Low — `prisma/seed-cost-plus.ts` cannot run on a freshly seeded database
- Steps: fresh DB → `npm run db:migrate` → `npm run db:seed` → `npx tsx scripts/seed-demo-payments.ts` → `npx tsx prisma/seed-cost-plus.ts`.
- Expected: cost-plus demo data seeded.
- Actual: `Error: Seed needs suppliers "Lanka Cement Distributors" — run the main seed first`. No seed script creates 7 of the suppliers it needs (Lanka Cement Distributors, Ceylon Steel Suppliers, K. Silva & Crew, Kottawa Plant Hire, Lanka Lorry Transport, Highland Quarry & Metal Suppliers, Masonry Crew Services). `prisma/seed.ts` creates no suppliers at all.
- Cause: `prisma/seed-cost-plus.ts:73-77` (`lookup`) assumes vendors that exist only on some other database.
- Impact: the client's team cannot reproduce the cost-plus demo from the repo. Workaround used: inserted the 7 suppliers by hand.
- Evidence: RUN-LOG.md 09:5x entry.

## P-03 — Low — Add/Edit user: first role checkbox is announced with the whole "Roles" group text
- Page `/users` (Add user, Edit user) · E2E-Admin · New
- Steps: open Add user with roles present; inspect accessibility tree.
- Expected: each role checkbox is named by its role.
- Actual: the first role's checkbox is named "Roles E2E-Estimator … E2E-Finance … E2E-CostPlus … E2E-ViewOnly …"; same for "Direct permissions". Screen-reader users hear the wrong label; automation by role name fails.
- Cause: `Field` wraps the control group in a `<label>`, and each checkbox has its own `<label>` inside it (nested labels): `src/app/users/page.tsx:620`, `:634`, `:736`, `:750`.
- Evidence: `traces/j00-accounts-J9-05-*/error-context.md` (first attempt)

## P-04 — Medium — Trade and unit duplicate checks are case-sensitive
- API `POST /api/trades`, `POST /api/units` (also PATCH) · E2E-Admin · New (the brief lists case-insensitive duplicate checks as a delivered feature)
- Steps: create trade "E2E-Trade r3ruz8"; POST `{name:"E2E-TRADE R3RUZ8"}`. Same for units.
- Expected: 409, as for suppliers, sub-contractors and activities.
- Actual: 200; two options differing only in case now appear in every unit/trade dropdown.
- Cause: exact-match check `src/app/api/trades/route.ts:25`, `src/app/api/trades/[id]/route.ts:21`, `src/app/api/units/route.ts:25`, `src/app/api/units/[id]/route.ts:21`.
- Evidence: `api/J1-08.json`, `api/J1-12.json`

## P-05 — Medium — A unit used only by BSR (activity) items can be deleted
- API `DELETE /api/units/[id]` · E2E-Admin · New
- Steps: create unit U; create a BSR item with unit U (no drafts/rates use U); DELETE the unit.
- Expected: 409 "Still used by …" (rename already cascades to `activity_items.unit`, so the app treats it as a reference).
- Actual: 200; the unit is gone from the dropdowns while BSR items still carry it; editing such an item shows no matching unit.
- Cause: in-use count checks only `basic_price_items` and `base_items`: `src/app/api/units/[id]/route.ts:45-51`.
- Evidence: `api/J1-14.json`

## P-06 — Low — Category label can be saved blank
- API `PATCH /api/categories/[key]` · E2E-Admin · New
- Steps: PATCH `{label:""}`.
- Expected: 400 "Label is required" (create enforces it).
- Actual: 200; category shows with an empty name in filters and badges. The Field options page also does not block it (no trim, no confirm).
- Cause: `src/app/api/categories/[key]/route.ts:9-10,22` (label not trimmed/min-checked); `src/app/settings/field-options/page.tsx:138`.
- Evidence: `api/J1-05.json`

## P-07 — Low — PATCH on a non-existent supplier, sub-contractor or activity returns 200
- API `PATCH /api/suppliers/[id]`, `/api/sub-contractors/[id]`, `/api/activities/[code]` · E2E-Admin · New
- Expected: 404. Actual: 200 with the echoed body; nothing written. A stale screen (record deleted by another user) shows "renamed" though nothing changed.
- Cause: no row-count check: `src/app/api/suppliers/[id]/route.ts:99`, `src/app/api/sub-contractors/[id]/route.ts:60`, `src/app/api/activities/[code]/route.ts:21,35`.
- Evidence: `api/J1-17.json`, `api/J1-22.json`, `api/J1-25.json`

## P-08 — Medium — Deleting a supplier used only by cost-plus expenses is allowed and silently unlinks them
- API `DELETE /api/suppliers/[id]` (UI: Suppliers → Delete) · E2E-Admin · New
- Steps: pick a supplier referenced only by `cost_plus_expenses` (here "Lanka Cement Distributors", expense `cpe_seed_1_1`, LKR 1,480,000); delete it.
- Expected: 409 "Still used by …", the same protection normal expenses get.
- Actual: 200. `cost_plus_expenses.supplierId` set to NULL (FK `ON DELETE SET NULL`); the expense keeps only the text name, drops out of any supplier view, and cannot be edited without re-picking a supplier (Material requires one). Same gap for sub-contractors.
- Cause: in-use check ignores `cost_plus_expenses`: `src/app/api/suppliers/[id]/route.ts:112-116`, `src/app/api/sub-contractors/[id]/route.ts:69`.
- Evidence: `api/J1-23.json`; DB: `select vendor, "supplierId" from cost_plus_expenses where id='cpe_seed_1_1'` → supplierId NULL.

## P-09 — Info — Company logo is not configurable
- `/settings/company-profile` has name/tagline/address/phone/email/registration only; no logo upload. Logo on PDFs is a fixed asset (checked in J3 exports). Brief asked for logo coverage; recorded as not available rather than a defect.

## P-10 — Low — Promoting a draft with a code already in use says "This draft has already been promoted."
- API `POST /api/projects/[id]/basic-price/[draftId]/promote` (UI: Promote modal, code edited by hand) · E2E-Admin · New
- Steps: Basic Rate has M-001; promote a fresh draft with code M-001.
- Expected: message that code M-001 is already used. Actual: 400 "This draft has already been promoted." although the draft is still a draft; user cannot tell what to fix.
- Cause: every 23505 is mapped to the same message: `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts:44`.
- Evidence: `api/J2-07.json`

## P-11 — Medium — Deleting a Basic Rate item leaves its source draft stuck as "promoted"
- API `DELETE /api/projects/[id]/basic-rate/[code]` · E2E-Admin · New
- Steps: promote draft → M-007; delete M-007 from Basic Rate; try to re-promote or delete the draft.
- Expected: draft returns to draft (or is removed) so it can be re-promoted or deleted.
- Actual: draft keeps `status=promoted`, `promotedCode=M-007`; re-promote → 400 "This draft has already been promoted."; delete → 400 "Only un-promoted drafts can be deleted." The draft is stuck for ever; Basic price tab shows "Promoted" for an item that no longer exists.
- Cause: `src/app/api/projects/[id]/basic-rate/[code]/route.ts:67-70` (and the global `src/app/api/basic-rate/[itemId]/route.ts:77-80`) do not reset `basic_price_items`.
- Evidence: `api/J2-13.json`

## P-12 — High — Adding a Basic Rate item with an existing code returns a raw 500
- API `POST /api/projects/[id]/basic-rate` · E2E-Admin · New
- Steps: project has M-001; POST `{code:"M-001", name, cat:"material", unit:"Bag", rate:1}`.
- Expected: 409 `Code "M-001" already exists in this project.` (items POST does this). Actual: 500 "Internal server error".
- Cause: unique violation 23505 not mapped (`src/lib/api.ts:20`); route has no pre-check: `src/app/api/projects/[id]/basic-rate/route.ts:78-81`. Same race exists in `basic-rate/clone/route.ts:49`.
- Reach: API (no project-tab form posts here directly); severity follows the brief's "server 500 = High".
- Evidence: `api/J2-14.json`

## P-13 — Medium — Editing a promoted draft's price makes Basic Price and Basic Rate disagree
- API `PATCH /api/projects/[id]/basic-price/[draftId]` (UI: Basic price tab → Edit on a promoted row) · E2E-Admin · New
- Steps: draft "Sand river" promoted as M-002 at 18,000; edit the draft price to 19,000.
- Expected: refused for promoted drafts, or Basic Rate M-002 updated (with history), so one item has one price.
- Actual: 200; draft shows 19,000, Basic Rate M-002 stays 18,000, no history entry. (The reverse direction — editing the rate — does sync the draft.)
- Cause: no status check / no sync in `src/app/api/projects/[id]/basic-price/[draftId]/route.ts` PATCH; same in global `src/app/api/basic-price/[draftId]/route.ts:47-49` (which can also move a promoted draft to another project).
- Evidence: `api/J2-15.json`

## P-14 — Low — Price history modal shows money without 2 decimals
- UI `/projects/[id]?tab=basic-rate` → View price history · E2E-Admin · New
- Expected: LKR to 2 decimals, as the rest of the catalog ("2,450.00", "2,600.50").
- Actual: "2,450", "2,600.5", change "+150.5".
- Evidence: `screens/J2-09.png`, `api/J2-09-checks.json`

## P-15 — Low — Project "current stage" accepts any integer
- API `PATCH /api/projects/[id]` · E2E-Admin · New
- Steps: PATCH `{curStage: 0}` and `{curStage: 9}` on a 4-stage project. Expected 400. Actual 200 both; the project report shows "Stage 9 of 4" and dashboard progress divides by it.
- Cause: `src/app/api/projects/[id]/route.ts:28` (int only, no 1..stages range).
- Evidence: `api/J3-03.json`

## P-16 — Medium — Stage update with "Expand contract & save" silently drops dates sent in the same request
- API `PATCH /api/projects/[id]/stages/[stageId]` with `expandContractTo` · E2E-Admin · New
- Steps: PATCH `{value:1100000, expandContractTo:1850000, startDate:"2026-11-05"}`.
- Expected: contract expanded, value and start date saved (or a 400). Actual: 200, contract and value saved, `startDate` stays NULL.
- Cause: the expand branch returns early: `src/app/api/projects/[id]/stages/[stageId]/route.ts:84-93`.
- Evidence: `api/J3-08.json`

## P-17 — Medium — "Outstanding" and "Contract value" mean different things on different screens for the same project
- Pages `/projects/[id]` header, project report PDF, dashboard · E2E-Admin · New
- Data: main project, contract 12,000,000, V1 250,000 included in contract, 50,000 cheque in hand.
- Project page header: Contract value 12,250,000 (incl. variation); Outstanding **9,900,000** (adds cheques in hand: `src/app/projects/[id]/client.tsx:226`).
- Project report PDF: Contract value **12,000,000** (variation not included); Outstanding **9,850,000**; Pending cheque clearance 50,000 shown separately.
- API / dashboard / variations strip: outstanding 9,850,000 with cheques separate.
- Expected: one definition per figure on every screen and export. Each figure is arithmetically consistent with its own definition (hand-checked), so this is misleading UI rather than wrong maths; a client comparing the PDF with the screen sees two different numbers.
- Evidence: `screens/J3-18.png`, `screens/J3-42-pdf-page1.png`, `api/J3-18-checks.json`, `exports/J3-42-pdf.txt`

## P-18 — Medium — Exact final expense instalment can be refused as an over-payment (float comparison)
- API `POST /api/projects/[id]/expenses/[expenseId]/payments` (UI: Payments — vendor ledger) · E2E-Admin · New
- Steps: expense of 0.30; pay 0.10 (200), then 0.20.
- Expected: 200, expense Completed. Actual: 400 "This payment would overpay the expense — it exceeds the outstanding balance." (0.1 + 0.2 > 0.3 in float8). 700.10 + 300.20 on 1,000.30 happened to pass.
- Cause: raw float compare, no cents rounding, no row lock: `src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:50-57` (milestone/variation/cost-plus ledgers use `insertPaymentGuarded` with cents rounding and `FOR UPDATE`). Same compare in expense PATCH `src/app/api/projects/[id]/expenses/[expenseId]/route.ts:30`.
- Impact: some cent combinations cannot be settled exactly; the expense stays "Partial" with a residual. Concurrent payments can also both pass (AUTHZ-VULN-03 still open).
- Evidence: `api/J3-35.json`

## P-19 — Low — Expense stage is not checked against the project's stages
- API `POST/PATCH /api/projects/[id]/expenses` · New
- Steps: stage 99 on a 4-stage project → 200. Stage costs tab then has an expense in no stage. Cause: `src/lib/expenseInput.ts:23`.
- Evidence: `api/J3-36.json`

## P-20 — Low — Nested expense/BSR routes ignore the project id in the URL (F-04-02 still open)
- API `PATCH /api/projects/<other project>/expenses/<expenseId>` → 200 and edits the expense in its real project. Access is checked against the real project, so no cross-project leak was possible in testing (see J8), but URLs/logs/audit can name the wrong project.
- Cause: `src/app/api/projects/[id]/expenses/[expenseId]/route.ts:16,51`, `.../payments/route.ts:16,34`, `.../payments/[paymentId]/route.ts:6`, `src/app/api/projects/[id]/bsr/[lineId]/route.ts:13,30`.
- Evidence: `api/J3-36.json`

## P-21 — Medium — UAT ENH-04 not delivered as written: no selective clone of expenses
- `/projects/[id]?tab=expenses` · E2E-Admin · UAT still open
- ENH-04 asks to pick a source project, tick expenses (with Select all), clone only those, with new voucher numbers and a count confirmation. No such control exists. Commit `56cd2ef` delivered a selective **Basic Rate** clone instead (tested J3-20/21, works).
- Evidence: `screens/J3-39.png`

## P-22 — Medium — Sinhala and Tamil text is garbled in PDF exports
- Project report PDF (and other jsPDF exports) · E2E-Admin · New
- Steps: client name "E2E Client — සිංහල தமிழ்" (saved and shown correctly in the app); export project report.
- Actual: PDF shows "E 2 E  C l i e n t — Ã Ò , Ä ½  ¤ ® ¿ ´ Î" (letter-spaced, mojibake). Sri Lankan client/site/payee names in Sinhala or Tamil cannot be printed.
- Cause: jsPDF standard fonts have no Sinhala/Tamil glyphs; no Unicode font embedded (`src/lib/pdfTemplate.ts`, `src/lib/exportPdf.ts`, `src/lib/exportProjectReport.ts`).
- Evidence: `screens/J3-42-pdf-page1.png`, `exports/J3-42-*.pdf`

## P-23 — Medium — UAT ENH-07 not delivered: ROI still shown, no "Project Status" tile
- Dashboard ("Overall ROI" card), project page ("Project ROI" card), project report PDF ("ROI (PAID BASIS)") · UAT still open (confirmed again in J7/J13)
- ENH-07: remove ROI %, add a Project Status tile = Outstanding (vendors + expenses) − 70% × Received.
- Evidence: `screens/J3-42-pdf-page1.png`; dashboard in J7.

## P-24 — Low — API accepts BSR item codes that belong to no activity; such items are invisible
- API `POST /api/projects/[id]/items` with code "E2E.A123" → 200; the item and its BSR line exist but appear under no activity on the BSR tab and are missing from the BSR export (the UI groups by the code's activity prefix). Found by a test-data mistake; recorded because the API should reject codes the UI cannot place.
- Cause: `code` is free text in `src/app/api/projects/[id]/items/route.ts`.

## Info (no defect)
- Custom-text expense lines carry no category, so an expense typed by hand for a supplier is stored as category **Other** (derived), even for cement. The dashboard "Expenses by category" puts these under Other.
- `POST /expenses` response echoes the client-sent `category`, not the derived one stored.
- A project with recorded client and expense payments is deleted after one confirm dialog; all money rows go with it (cascade verified clean, invoice counters untouched).
- Stage values shown to cents can sum to 0.01 less than the contract (2,000,000 + 3 × 3,333,333.33 = 11,999,999.99); raw values sum exactly.
- Logo on PDFs is a fixed image (VEGA HOMES); company name/address come from the company profile (verified).

## P-25 — Medium — Expenses with no vendor are missing from the Payments page totals
- Page `/payments` · E2E-Admin · New
- Data: 11 expenses (LKR 5,658,200 owed, all outstanding) saved with "No supplier / not specified" (and 2 sub-contractor-category expenses without a sub-contractor) — a choice the Log expense form allows.
- Expected: "Total outstanding" covers every unpaid expense, or the page shows the remainder somewhere.
- Actual: they are in no vendor tab and not in Total outstanding / Total paid (the groups drop rows whose vendor key is empty). The "No supplier items" tab only lists line items sourced from un-linked Basic Rate items. Company payables on this page are understated by LKR 5,658,200 with nothing telling the user.
- Cause: `src/app/api/payments/route.ts` groups CTE `where vendorKey is not null and vendorKey <> ''` (see `src/lib/paymentFilters.ts`).
- Evidence: `api/J4-01.json`, `screens/J4-01.png`

## P-26 — Low — Vendor drawer offers "Record a payment" on fully paid expenses
- `/payments` → vendor drawer · E2E-Admin · New
- Actual: 15 "Record a payment" buttons for 11 unpaid + 4 completed expenses of the E2E supplier. The supplier detail page hides it for completed vouchers; the API then refuses any amount (over-payment), so the user gets an error after opening the form. Also shown without checking `projects:edit`.
- Cause: `src/components/payments/VendorDrawer.tsx:171`; same on the unlinked tab `src/app/payments/page.tsx:432`.
- Evidence: `api/J4-18.json`, `screens/J4-18.png`

## P-27 — High — Cost-plus: billed total can drop below what the client has paid; the over-payment is hidden
- API `PATCH /api/cost-plus?id=` (margin) and `DELETE /api/cost-plus/expenses?expenseId=` (UI: margin field, expense delete) · E2E-CostPlus · New
- Steps: project billed 179,200.55, client received 150,000; set margin 0 %, delete the paid 100,000 expense.
- Expected: refused (normal projects refuse any edit that leaves a milestone below what was paid — `findUnderpaidMilestone`), or the over-receipt shown as money due back.
- Actual: both 200. Billed total 60,000.49, received 150,000, **outstanding shows 0**; the 89,999.51 the company owes the client appears nowhere. The deleted expense's supplier payments are deleted too.
- Cause: no guard in `src/app/api/cost-plus/expenses/route.ts:128-149` or `src/app/api/cost-plus/route.ts:77-82`; `paymentSettlement` clamps outstanding at 0.
- Evidence: `api/J6-07.json`

## P-28 — Low — KPI cards round money to whole rupees
- Cost-plus list and dashboard tab, project header, dashboard · New
- Actual: expense 160,000.49 shows "LKR 160,000"; billed 184,000.56 shows "LKR 184,001" (`fmt0`). Tables on the same pages show cents. Brief standard: LKR to 2 decimals; a reader adding cards will be off by rupees.
- Evidence: `screens/J6-06.png`, `api/J6-05-checks.json`

## P-29 — High (needs a client decision) — The Finance role sees an empty dashboard and Payments page again (E-06 reversed)
- `/`, `/payments` · E2E-Finance (dashboard:view, payments:view, priceComparison:view; no project membership) · Regression of E-06
- 2026-09-21: E-06 made these three permissions company-wide, "confirmed with the client". Commit `fcfd636` ("Scope dashboard/reporting routes by project access") re-applied `projectAccessClause` to dashboard and payments.
- Actual now: Finance dashboard — every figure 0, 0 projects; Payments — no vendors; Price comparison list — every project (still company-wide).
- Expected: whichever rule the client confirms, applied the same way on all three. Today a Finance user configured exactly as the Roles screen suggests cannot do their job, and the three screens disagree on scope.
- Evidence: `api/J7-03.json`, `screens/J7-03.png`, `api/J8-04-matrix.json`

## P-30 — Medium — Price comparison: an item visible in the list opens "Item not found" for users without project access
- `/suppliers/compare` → "View price history" (`/suppliers/compare/item`) · E2E-Finance · New
- Cause: list `src/app/api/suppliers/price-comparison/route.ts:29-40` is company-wide; item route `.../price-comparison/item/route.ts` filters by project access. Finance sees "E2E-Compare cement" in the list (3 projects), clicks through, gets "Item not found". Admin works.
- Evidence: `api/J8-04-matrix.json`, `screens/J8-finance-_suppliers_compare_item_*.png`

## P-31 — Medium — Login is case-sensitive on email, although emails are unique case-insensitively
- `/login`, `POST /api/auth/login` · E2E-Estimator · New
- Steps: account `estimator.r3ruz8@e2e.test`; log in as `ESTIMATOR.R3RUZ8@E2E.TEST` with the right password.
- Expected: 200 (the app already refuses a second account differing only in case). Actual: 401 "Invalid email or password", and the failure counts towards the 5-attempt lock-out. Users on phones with auto-capitalised first letters get locked out.
- Cause: exact match `select … from users where email = ?` in `src/lib/auth.ts:264` via `src/app/api/auth/login/route.ts:89`.
- Evidence: `api/J9-12.json`

## P-32 — Medium — Editing a user is not atomic: a refused request still saves part of the change
- `PATCH /api/users/[email]` (UI: Users → Edit) · E2E-Admin · New
- Steps: PATCH `{name:"E2E-Tmp half-saved", roleIds:["no-such-role"]}`.
- Expected: 4xx and nothing saved. Actual: 409 (generic FK message) but the name is saved. With a password change in the same request the password is saved but the user's other sessions are not revoked (revocation runs after the failing batch).
- Cause: separate non-transactional updates, roles/permissions batch last: `src/app/api/users/[email]/route.ts:113-144`.
- Evidence: `api/J9-17.json`

## P-33 — Low — Roles: renaming clears the description; duplicate names in another case accepted
- `PATCH /api/roles/[id]` with only `name` → description NULL (`src/app/api/roles/[id]/route.ts:65-66`). `POST /api/roles` with the same name in upper case → 200 (case-sensitive; users/suppliers/activities are case-insensitive). The Roles page always sends both fields, so the UI path is not affected by the first part.
- Evidence: `api/J9-18.json`

## P-34 — Low — Deleting a user with cost-plus payment history gives a generic message
- `DELETE /api/users/[email]` for E2E-CostPlus → 409 "This record refers to something that no longer exists, or is still in use elsewhere." Deletion is correctly blocked, but the user is not told to deactivate instead (the audit pre-check misses cost-plus, project ownership, expense payments). Cause `src/app/api/users/[email]/route.ts:175-185`. Evidence `api/J9-15.json`.

## P-35 — Critical — Concurrent expense payments can overpay an expense (money record corrupted)
- `POST /api/projects/[id]/expenses/[expenseId]/payments` (UI: expense payment ledger, vendor drawer, supplier page) · E2E-Admin (two sessions) · Known since AUTHZ-VULN-03, never fixed; now reproduced
- Steps: expense of 100.00; send three payments of 60.00 at the same moment from two sessions.
- Expected: at most 100.00 accepted (later ones 400 "would overpay"), as milestone, variation and cost-plus payments do.
- Actual: all three 200; **180.00 recorded as paid on a 100.00 expense**; outstanding −80. Supplier totals, Payments page and dashboard "expense paid" all include the extra 80.
- Cause: read-sum-then-insert with no row lock and no transaction guard: `src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:50-57`. The fix already exists in the codebase: `insertPaymentGuarded()` in `src/lib/incomePayments.ts` (`SELECT … FOR UPDATE` + cents compare), used by every other ledger.
- Likelihood: needs two submissions within milliseconds (two clerks paying one invoice, a retried request, a double-tap on a slow phone). The UI double-click case was safe in testing (J11-06).
- Evidence: `api/J11-08.json`; DB `select sum(amount) from expense_payments where "expenseId" = <race expense>` = 180.

## P-36 — Low — No upper limit on variation and expense amounts
- `POST /api/projects/[id]/variations` and expense line items accept 1,000,000,000,000,000; contract and cost-plus amounts are capped at 100,000,000,000. A typo (extra zeros) passes straight into the dashboard totals. Evidence `api/J11-02.json`.

## P-37 — Low — Payments keep sub-cent precision
- A milestone payment of 100.123456 is stored as 100.123456 (not 100.12 and not refused). Money elsewhere is shown to cents, so sums of stored values drift from what is displayed. Cause: no cents rounding/validation on payment amounts (`src/lib/incomePayments.ts`, payment schemas). Evidence `api/J11-02.json`.

## P-38 — High — A project delete that fails is reported as "Project deleted"
- `/projects` → Delete · E2E-Admin (server response simulated as 403) · New (flagged by code review, confirmed live)
- Steps: open Delete for E2E-Catalog; make `DELETE /api/projects/[id]` return 403 (as it would for a user without delete rights who still has the button through a stale page, or any server error); confirm.
- Expected: error toast with the server message; project stays. Actual: green toast "Project deleted"; the project is still in the database (and reappears on refresh).
- Cause: `deleteProject` ignores the response: `src/app/projects/page.tsx:233-238`. Same pattern: user activate/deactivate toast `src/app/users/page.tsx:277-282`; global Basic Price promote `src/app/basic-price/page.tsx:859`.
- Evidence: `screens/J12-07.png`, `api/J12-07.json`

## P-39 — High — Network failure when adding a supplier gives no feedback (uncaught "Failed to fetch")
- `/suppliers` → Add supplier · E2E-Admin · E-01 addendum partly still open
- Steps: request aborted (network drop) after confirming Add supplier.
- Expected: error toast ("Could not add … try again"). Actual: nothing — no toast, dialog stays open; browser logs uncaught `TypeError: Failed to fetch`. E-01 (2026-09-21) added `res.ok` checks but thrown network errors are still unhandled on this path.
- Evidence: `screens/J12-07-network.png`, probe log in RUN-LOG

## P-40 — Low — Dashboard "Expenses by category" cuts money values off
- `/` at 1440 px · E2E-Admin · New
- Actual: "LKR 67,351,2…", "LKR 33,550,0…", "LKR 13,903,9…" — the figure itself is truncated with an ellipsis, so the reader cannot see the amount. Evidence `screens/J13-04-dashboard.png`.

## Addendum to P-39 (J13-02)
- Offline **Add activity** now shows an error toast (E-01 addendum fixed for that path) but still throws an uncaught `TypeError: Failed to fetch` in the console. Offline **Add supplier** shows nothing at all.

## P-41 — High — Basic Price page: promote with a blank price says "Promoted" but nothing is promoted
- `/basic-price` (global page) → Promote → clear Price → Promote · E2E-Admin · New (clean pass; the first pass missed it because my toast helper could not see toasts — see RUN-LOG)
- Actual: toast "Promoted to Basic Rate as L-001"; the draft stays `status=draft`, no Basic Rate item exists.
- Cause: the page sends `Number(price)||0` and ignores the API's 400: `src/app/basic-price/page.tsx:859, 902`. (The project-tab promote validates and is correct.)
- Evidence: `rerun/api/J2-16.json`, `rerun/screens/J2-16.png`

## P-42 — Medium — Basic Rate page: rate 0 says "Item updated" but keeps the old rate
- `/basic-rate` (global page) → Edit → Rate 0 → Save · E2E-Admin · New
- Actual: toast "Item updated — timestamped & logged"; rate stays 18,000. A blank rate does the same. The user is told their change was saved.
- Cause: `src/app/basic-rate/page.tsx:158` (and `src/app/projects/[id]/client.tsx:4589`) silently keep the old rate for 0/blank.
- Evidence: `rerun/api/J2-17.json`

## P-43 — High — Two activities created at the same moment: one gets a raw 500
- `POST /api/activities` (UI: Activities → Add activity, two users) · E2E-Admin · New (clean pass: `[200, 500]`; first pass happened to get distinct codes)
- Cause: next code = max+1 without a lock; the second insert hits the primary key (23505), which is not mapped: `src/app/api/activities/route.ts:27-30`, `src/lib/api.ts:20`.
- Evidence: `rerun/api/J1-26.json`
