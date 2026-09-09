# Database Schema — Vega Construction Manager

Cloudflare D1 (SQLite). **26 tables.** Written reference for the ER diagrams in this folder.

Sources of truth: `vega-manager/prisma/schema.prisma` for models, `vega-manager/migrations/0001…0026` for
what the database actually contains. As of `0026_remove_mfa.sql` the two agree — see
[Schema history](#schema-history).

## Conventions used throughout

| Convention | Detail |
|---|---|
| Primary keys | `cuid()` text ids, except `activities.code` (natural key) and `login_throttle.key` |
| Foreign keys | **Not enforced by D1.** Declared in Prisma and in migration DDL, but SQLite-on-D1 does not check them at runtime — every referential rule is application-enforced |
| Money snapshots | `recipe_components.amount` and `expense_line_items.amount` are stored values, never recomputed from a live join |
| Derived values | Paid / outstanding / ROI are computed on read (`sum(expense_payments.amount)` vs `expenses.amount`), never stored |
| Per-project scoping | Catalog and estimation tables carry their own `projectId`; codes are unique **within** a project, not globally |
| Lookup references | `cat`, `trade`, `unit` are stored as **text values**, not FKs, into `categories` / `trades` / `units` |
| Cross-field rules | Enforced in API routes, not by DB constraints (e.g. supplier-vs-sub-contractor by category, overpay checks, line-item sum lock) |

---

## Identity & Access (7 tables)

Authentication is **single-factor by design** — the client declined MFA, so there is no second factor
and no authenticator enrollment. Brute-force resistance comes from `login_throttle` plus the Cloudflare
edge rate limiter, not from a second factor.

### `users`
| Column | Notes |
|---|---|
| `id` | PK |
| `name` | |
| `email` | **unique** |
| `passwordHash` | bcrypt |
| `role` | `Admin` \| `Staff` — legacy super-admin bootstrap flag; **Admin bypasses RBAC entirely** |
| `status` | `Active` \| `Inactive` |
| `createdAt` | |

### `sessions`
`id` PK · `userId` → users · `expiresAt` · `revokedAt` (NULL = valid) · `createdAt`

Backs **session revocation**. The JWT cookie carries only this row's id — never role or status — so a
deactivation, role change or password change invalidates an issued token immediately instead of waiting
out its 7-day expiry.

### `login_throttle`
`key` PK · `failures` · `firstFailAt` · `lockedUntil`

`key` is `email:<lowercased>` or `ip:<cf-connecting-ip>` — deliberately *not* keyed by `userId`, since a
throttle has to work for emails that don't resolve to a user.

### `roles`
`id` PK · `name` **unique** · `description` · `createdAt` · `updatedAt`

### `role_permissions`
`id` PK · `roleId` → roles · `module` · `action` · **unique** (`roleId`, `module`, `action`)

`module`/`action` are validated against `PERMISSION_CATALOG` in `lib/rbac.ts` — application-level, not a
DB enum, so adding a permission is a code change in one place.

### `user_roles`
Composite PK (`userId` → users, `roleId` → roles). No group layer — roles attach straight to users.

### `user_permissions`
Composite PK (`userId` → users, `module`, `action`). A third grant path: a direct per-user permission
with no role involved. Effective access = **union** of role permissions and these.

---

## Projects (4 tables)

### `projects`
`id` PK · `name` · `client` · `location` · `start` · `stages` (total stage **count**) · `curStage` ·
`status` (`Active`\|`Completed`\|`OnHold`) · `contract` · `ownerId` → users · `createdAt`

`ownerId` is the permanent creator and drives per-user data isolation: Admin sees everything, Staff see
only projects they own or are a member of. Nested resources inherit this via `projectId`.

### `project_members`
`id` PK · `projectId` → projects · `userId` → users · `addedById` → users · `addedAt` ·
**unique** (`projectId`, `userId`)

Additive **visibility** grant on top of ownership. Grants *reach* only — it confers no `module:action`
permission of its own. Admin-managed via Settings → Project access.

### `stages`
`id` PK · `projectId` → projects · `order` · `name` · `value` (NULL = `contract / projects.stages`, even
split) · `startDate` · `completionDate` (both optional, feed the Payments Schedule export)

### `milestones`
`id` PK · `stageId` → stages · `label` (`Advance`\|`Interim`\|`Final`) · `pct` (the hardcoded 50/25/25) ·
`status` · `amount` (NULL = `perStage × pct/100`, computed on read) · `chequeDate` · `dueDate`

`status` lifecycle: `pending` → `paid`, or through the cheque states —
`cheque_received` (deposited, **not** counted as received) → `cheque_cleared` (counted, same as paid) /
`cheque_bounced` (back to outstanding, flagged). `dueDate` NULL means "not tracked" and deliberately
generates no overdue notification.

---

## Catalog & Estimation (7 tables — all per-project)

### `activities`
`code` PK (e.g. `'05'`) · `name`

Fixed trade categories, mutable at runtime from the Activities page. Holds **no** items or recipes.

### `basic_price_items` — Basic Price drafts
`id` PK · `projectId` → projects · `activityCode` → activities · `cat` → categories.key · `trade` →
trades.name (nullable) · `name` · `unit` · `price` (nullable while draft) ·
`status` (`draft`\|`promoted`) · `promotedCode` · `addedById` → users · `supplierId` → suppliers
(nullable) · `addedAt`

### `base_items` — Basic Rate (the coded catalog)
`id` PK · `projectId` → projects · `code` (e.g. `M-026`) · **unique** (`projectId`, `code`) · `name` ·
`cat` · `unit` · `rate` · `promotedFromId` → basic_price_items (**unique**, 1:1) · `supplierId` →
suppliers · `updatedById` → users · `ownerId` → users (audit only) · `createdAt` · `updatedAt`

The PK moved from a global `code` to a synthetic id precisely because `code` is now only unique per
project — two projects can each hold their own `M-026` independently. `createdAt` = when first promoted
(sorts newest-first); `updatedAt` changes on every rate edit.

### `price_history_entries`
`id` PK · `baseItemId` → base_items · `oldRate` · `newRate` · `byId` → users · `at`

### `activity_items` — rate-analysis items
`id` PK · `projectId` → projects · `code` (e.g. `05.D.01`) · **unique** (`projectId`, `code`) · `name` ·
`unit` · `analysisQty` (default 1) · `floorGround` / `floor1st` / `floor2nd` / `floor3rd`

`rate = sum(recipe.amount) / analysisQty`, always derived. `analysisQty` exists because the client's real
BSR has items whose analysis basis isn't 1 unit (`05.D.01` = 0.51).

### `recipe_components`
`id` PK · `activityItemId` → activity_items · `order` · `name` · `type` (`base`\|`trade`\|`pct`) ·
`qty` (display string, e.g. `"23 Bag"`) · `rate` (snapshot; NULL for `pct`) · `amount` (stored) ·
`sourceBaseItemCode` / `sourceActivityItemId` (traceability only, **not** enforced FKs — sourced items may
later be renamed or deleted)

### `bsr_lines`
`id` PK · `projectId` → projects · `activityItemId` → activity_items · `floor` · `qty`

No unique constraint on (project, item) — the same item appears on multiple floors as separate rows.

---

## Finance (5 tables)

### `suppliers` / `sub_contractors`
Both: `id` PK · `name`

Two tables rather than one `vendor` with a type flag — they're different kinds of business relationship
(matching the Payments Summary page's own two buckets), and the same real company can legitimately be a
Supplier on one expense and a SubContractor on another. Two tables let that be one row in each.

### `expenses`
| Column | Notes |
|---|---|
| `id` | PK |
| `projectId` | → projects |
| `date`, `invoice` | |
| `category` | `Material`\|`Labour`\|`SubContractor`\|`Machinery`\|`Transport`\|`Other` |
| `stage` | 1-based stage **number**, not an FK — matches the source spreadsheet |
| `amount` | Total owed. **Never mutated by payment activity** |
| `supplierId` | → suppliers, nullable |
| `subContractorId` | → sub_contractors, nullable |
| `vendor` | *legacy* free text — display fallback for pre-migration rows |
| `method` | *legacy* single payment method — superseded by `expense_payments` |
| `boq` | *legacy* single BSR-code reference, display-only, no longer settable |

Exactly one of `supplierId` / `subContractorId` is set, decided by `category`
(`SubContractor` → sub-contractor; everything else → supplier). Enforced in the API route, not the DB.

### `expense_payments`
`id` PK · `expenseId` → expenses · `amount` · `date` · `method` (`Cash`\|`Bank`\|`Online`) ·
`recordedById` → users

One row per payment, so an expense can be settled across several payments on different dates and methods.
`paid = sum(amount)`, `outstanding = expenses.amount − paid` — both computed on read. Also the foundation
for the vendor-grouped Payment Summary (same rows, grouped by vendor instead of by expense).

### `expense_line_items`
`id` PK · `expenseId` → expenses · `description` · `category` (snapshot, NULL for free-text lines) ·
`qty` (snapshot, NULL for free-text) · `amount` · `sourceItemId` / `sourceType`
(`basicPrice`\|`base`, no FK)

Optional itemized breakdown. Zero rows = a plain manual expense; **one or more rows locks
`expenses.amount` to their sum** (enforced in the create route). Lines come from either picking a Basic
Rate catalog item (category + qty snapshotted, `amount = qty × rate` at add-time) or typing a description
and amount directly. Not tied to BOQ/BSR codes — an earlier BOQ-linked version was replaced outright.

---

## Lookup lists (3 tables)

User-manageable via Settings → Field options. Replaced what used to be hardcoded arrays in page
components, so adding a category / trade / unit is no longer a code change.

| Table | Columns |
|---|---|
| `categories` | `id` PK · `key` **unique** (stored on `*.cat`) · `label` · `prefix` **unique** (`M` → `M-001`) · `color` · `sortOrder` |
| `trades` | `id` PK · `name` **unique** · `sortOrder` |
| `units` | `id` PK · `name` **unique** · `sortOrder` |

Referenced **by value**, not by foreign key — `basic_price_items.cat` stores `categories.key` as text.

---

## Schema history

**MFA was added and then removed.** Migration `0025_mfa.sql` added `users.mfaSecret`,
`users.mfaEnabledAt`, `users.mfaLastUsedStep` and an `mfa_recovery_codes` table. It was never wired up —
no route ever served it, nothing imported `lib/totp.ts` or `lib/mfaCrypto.ts`, and login issued a full
session straight after the bcrypt check. The client then declined the feature, so `0026_remove_mfa.sql`
drops all four objects.

Two consequences worth knowing:

- Those columns were NULL for every row and `mfa_recovery_codes` was empty, so the drop cost no data.
- `prisma/schema.prisma` never declared any of it (0025 was applied as raw SQL without a matching schema
  update). Removing it **closes that drift** rather than deepening it — the Prisma schema is once again
  an accurate description of the database.

## Cascade behaviour

`onDelete: Cascade` is declared on the child side of most parent-child relations (sessions,
role_permissions, user_roles, user_permissions, project_members, stages, milestones, activity_items,
recipe_components, bsr_lines, basic_price_items, base_items, price_history_entries, expenses,
expense_payments, expense_line_items). Because **D1 does not enforce foreign keys**, these are
declarations only — deletes are cascaded manually in the API routes. `doc/` records this as the
"manual cascade-delete child tables" pattern.
