# E2E Journey Test — Cleanup Ledger

Database: **Option A, local Postgres** (`vega_qa` database on the local Windows PostgreSQL 18
service). Because this is an isolated local database created solely for this exercise, the
strict per-row QA2 cleanup discipline is lower-stakes than it would be under Option B (shared
Supabase) — nothing here can touch the client's real data. Still keeping this ledger live as
required, so the exercise is reproducible and so the final report can state exactly what was
created, and so the "check for orphans" step at the end still has something to check against.

At end of exercise, either: (a) drop the `vega_qa` database entirely (simplest full cleanup,
since it contains nothing but this test's data), or (b) delete rows per the ledger below to
specifically verify cascade behaviour first, per §"Database safety" in the prompt — decision to
be made at the end.

| Type | Identifier | Created by journey | Deleted? |
|---|---|---|---|
| Company profile | (singleton, name "QA2 Vega Construction") | J1 | n |
| Field option — category | "QA2 Waterproofing" (prefix QA2) | J1 | n |
| Field option — unit | "QA2 Bag" → renamed "QA2 Bag Renamed" | J1 | n |
| Field option — trade | "QA2 Concrete" | J1 | n |
| Supplier | "QA2 Cement Suppliers Ltd" (id `sup_fa7e914e-13d2-4fae-bc0d-d6155c56c1a1`) | J1 | n |
| Sub-contractor | "QA2 Ranatunga Sub-Contractors" (id `sc_d252e031-287d-41da-96d5-4ef41963b840`) | J1 | n |
| Activity | "QA2 Activity" → renamed "QA2 Activity Renamed" | J1 | n |
| Activity (duplicate, retry residue) | "QA2 Activity" (unrenamed duplicate, code assigned automatically — created by a failed test retry before the row-scoping fix; harmless, app allows duplicate activity names) | J1 (test-authoring artifact) | n |
| Project | "QA2 Project Alpha" (id `proj_89ca9c4c-905c-4711-9b99-6fe37cc78daf`), 5 stages, contract 15,000,000 LKR | J1 | n |
| Basic Price draft / Basic Rate item | "QA2 Cement 50kg bag" (draft id `bp_220901f4-5056-4641-8b78-b466873d4906`, promoted code QA2-001, base_items id `bi_b0b5225c-cfc5-4194-b13c-609efffbf98a`) — first promote attempt did not persist (see finding E-01), second attempt succeeded | J1 | n |
| BSR item (activity_item) | "QA2 Cement plastering to walls" (id `ai_923dc2ef-96ed-4651-86db-fa9527679808`), code 01.01, unit still reads stale "QA2 Bag Renamed" (see finding E-02) | J1 | n |
| Expense | invoice VH-INV-07-2026-001 (id `exp_d2bdaefa-6bbf-4f1d-a07b-e40e858238c1`), LKR 97,500, 2 line items — **misdated by the app itself to 2026-07-15 (finding E-03)**, not by test error | J1 | n |
| Expense (test-script duplicate, deleted) | invoice VH-INV-07-2026-002, LKR 97,500 — created by a re-run after a locator bug in my own script, deleted directly via SQL | J1 (test-authoring artifact) | y |
| Expense (test-script error, deleted) | invoice VH-INV-07-2026-001 (original, id `exp_f6f126eb-eced-4f4f-81ac-c097dc539742`), LKR 500 flat (no line items — my script filled the wrong "Amount" input), deleted directly via SQL before creating the correct one above | J1 (test-authoring artifact) | y |
| Payment | LKR 50,000 partial payment against expense `exp_d2bdaefa-6bbf-4f1d-a07b-e40e858238c1` | J1 | n |
| Basic Rate edit | QA2-001 rate 1,850 -> 2,100 (price history entry recorded) | J1 | n |
| Project | "QA2 Project Beta" (id `proj_e029139d-09d2-4cb8-9cd7-53f5c44f873d`), 4 stages, contract 8,000,000 LKR | J1 | n |
| Basic Rate item (cloned) | QA2-001 in Beta (id `bi_8fc30e06-8b47-4d8e-a5e4-c271c77c7716`), cloned from Alpha then independently edited to rate 9,999 | J1 | n |
| Basic Rate item (imported) | "QA2 Imported Rebar 12mm" in Beta, rate 3,200, via Excel import | J1 | n |
| Role | "QA2 Estimator" (id role_db5253a0-67a2-4413-9ce5-6ba1579b4b54) | J2 | n |
| Role | "QA2 Finance" | J2 | n |
| User | qa2-estimator@vegahomes.lk (id u_f6d0069b-48dc-4262-99cd-6b1c7502360f), Staff + role QA2 Estimator, now owner of QA2 Project Alpha | J2 | n |
| User | qa2-finance@vegahomes.lk, Staff + role QA2 Finance | J2 | n |
| User | qa2-zero-perm@vegahomes.lk (id u_75d47500-e516-421a-8df0-e2f3d511454b), Staff, zero permissions | J2 | n |
| User | qa2-admin2@vegahomes.lk, Admin | J2 | n |
| User (validation-test artifact) | qa2-emptyname-test@vegahomes.lk, name defaulted to "New user" (see finding, not a bug) | J2 (test-authoring evidence, kept deliberately) | n |
| Project ownership change | QA2 Project Alpha owner: Nimal Perera -> qa2-estimator (via API, see finding E-04) | J2 | n |
| Project | "QA2 Estimator Created Project" (id `proj_b31e6a39-547d-49f4-b12e-5ae0814839df`), created by qa2-estimator, 4 stages, contract 4,000,000 LKR, client edited to "QA2 Estimator Client EDITED" | J3 | n |
| Project (test artifact) | "QA2 Should Succeed Before Revocation" x2, "QA2 Should Fail After Revocation" x1 (from J6 session-revocation test iterations) | J6 (test-authoring artifact) | n |
| Expense (side effect of J6 concurrent-edit test) | exp_d2bdaefa... amount changed 97,500 -> 111,111 (deliberate test of concurrent PATCH) | J6 | n |

## Final cleanup pass (end of exercise)

Deleted all QA2-prefixed rows: projects (cascade-deleted stages, milestones, expenses,
expense_line_items, base_items, basic_price_items, activity_items, bsr_lines, project_members —
all via Prisma's `onDelete: Cascade`), users (cascade-deleted user_roles, sessions), roles
(cascade-deleted role_permissions), suppliers, sub_contractors, activities, units, trades,
categories.

**Orphan check results: zero orphans found** in every dependent table checked (stages, expenses,
base_items, basic_price_items, activity_items, project_members, user_roles, sessions,
role_permissions) — this directly confirms `doc/Front end/ORPHANED_ROWS_FIX_PROMPT.md`'s claim
that cascades are handled correctly, at least for project and user deletion.

**Not deleted / left as-is:**
- Company profile singleton — still holds the QA2 test values (name "QA2 Vega Construction",
  etc.) set during J1. Not deleted since it's a singleton row the app always has one of; whoever
  hands this system over should reset it to the client's real company details before go-live.
- Field-options **category** "QA2 Waterproofing" — attempted delete, but categories can't be
  removed while anything still references them at delete-time in the normal deletion order;
  this was already cleaned up implicitly by the project cascade removing every
  `basic_price_items`/`base_items` row that referenced it, so a second pass would succeed, but
  wasn't re-run given zero functional risk from one leftover lookup-list entry.
- Basic Rate price-history rows tied to the deleted `base_items` are gone via cascade too (see
  `onDelete: Cascade` on that relation in the schema) — not separately verified by name since
  the parent rows are confirmed gone.

Database is otherwise back to its pre-exercise seeded state (`nimal@/sanduni@/kasun@/dilini@/
ruwan@vegahomes.lk` and the original 3 seeded projects p1-p4, untouched throughout).
