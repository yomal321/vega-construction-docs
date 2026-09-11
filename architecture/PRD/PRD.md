# Vega Construction Manager — Product Requirements Document

**Client:** Vega Construction / Vega Homes (Sri Lanka)
**Delivered by:** BISTEC Global — Project Delivery Team
**Document date:** 2026-09-08
**Audience:** Project Manager, Senior Stakeholders

---

## 1. Executive Summary

Vega Construction Manager is a web application that replaces Vega Construction's manual
Excel-based workflow for **pricing, rate analysis, and project payment tracking**. It gives
the client a single system to manage multiple construction projects — from cost estimation
(price lists and rate analysis) through to physical payment collection and expense tracking —
with proper user access control, in place of shared, uncontrolled spreadsheets.

The system is **live and in active use**. All 7 client-requested enhancements are built. The
team is currently completing a pre-handover security audit and migrating the hosting
infrastructure per the client's request.

---

## 2. Background & Problem Statement

Vega Construction previously tracked everything in Excel:

- A **Basic Price / Basic Rate** list (materials, labour, and plant costs)
- A **BSR** (Bill/Schedule of Rates) — the rate analysis that builds a construction activity's
  unit cost from its material/labour recipe
- A **Payments Schedule** — stage-wise contract payment collection
- **Expenses** — money paid out to suppliers and sub-contractors

This worked, but had no access control (anyone could see or edit any project's numbers), no
audit trail on price changes, and no way to track partial payments or see at a glance which
supplier or sub-contractor had been paid the most. The original requirements document (BRD)
also undersold the real complexity — the client's actual Excel was a full recipe-based rate
engine, not a flat price list. This surfaced during discovery and shaped the actual build (see
`GAP_ANALYSIS.md` in this repo).

---

## 3. Goals

1. Give each user their own scoped view of the projects they own or are assigned to
2. Let Basic Price/Rate differ per project (pricing genuinely varies by when a project was
   estimated)
3. Track partial and full payments — both **money coming in** (client payments per project
   stage) and **money going out** (expenses to suppliers/sub-contractors)
4. Preserve a full audit history of rate changes
5. Provide financial reporting: dashboards, ROI, cash flow, exportable Excel/PDF reports
6. Enforce real authentication and role-based permissions, not a shared login

---

## 4. Users & Access Model

Two account roles:

| Role | Access |
|---|---|
| **Admin** | Full access to every module and every project, company-wide. Manages Users, Roles, Settings. |
| **Staff** | Sees only projects they **own** or have been explicitly **assigned to**. What they can *do* within those projects (view/create/edit/delete/promote, per module) is controlled by a separate, admin-configurable **Roles & Permissions** system — a Staff user's reach (which projects) and their permissions (what actions) are governed independently. |

This two-part model (project access vs. action permission) was a deliberate design choice —
it lets an Admin grant someone visibility into a project without automatically granting every
permission, and vice versa.

---

## 5. Core Modules

| Module | What it does |
|---|---|
| **Dashboard** | Portfolio-wide KPIs, expense-by-category chart, project list, cash-flow snapshot. Admin sees company-wide; Staff sees only their own reachable projects. |
| **Projects** | Central hub per project — contract value, stage count, client/location, and four tabs: **BSR**, **Stages & Payments**, **Expenses**, **Stage Costs**. |
| **BSR (Bill of Rates)** | Per-project, per-activity list of construction items, each built from a **recipe** of Basic Rate components (material/labour/plant) or a percentage allowance. Grouped by trade Activity (Site Prep, Concrete, Formwork, Reinforcement, Block Work, etc. — 16 fixed categories). Supports floor-based quantity multipliers (Ground/1st/2nd/3rd). |
| **Basic Price / Basic Rate** | The underlying cost catalog. **Basic Price** holds priced or unpriced draft entries; promoting a draft (assigning it a code) creates a **Basic Rate** item, which is what BSR recipes are built from. Both are **project-scoped** — no cross-project sharing of pricing. Global list-and-reassign views also exist for a portfolio-wide look. |
| **Activities** | Admin-managed list of the 16 fixed trade categories (add/rename/delete only — holds no pricing data itself). |
| **Stages & Payments** | Splits a project's contract value into stages, each with milestones (Advance/Interim/Final). Tracks payment status including a full **cheque lifecycle** (received → cleared or bounced) and computes received/outstanding/pending-cheque totals. Exports a Payments Schedule to Excel. |
| **Expenses & Payments** | Logs money paid out per project, by category (Material/Labour/Sub-Contractor/Machinery/Transport/Other), linked to a real Supplier or Sub-Contractor record. Supports **partial payment allocation** — one expense can be settled across several payments over time, method-tagged (Cash/Bank/Online), with outstanding balance always computed live. Optional itemized breakdown of what an expense's amount was built from. |
| **Suppliers & Sub-Contractors** | Company-wide vendor directory. Supplier detail page shows their full relationship across every accessible project — what they supply (catalog items) and what they've been paid. **Price Comparison** view lets you compare a material's price across suppliers. |
| **Stage Costs** | Cost-analysis view over a project's existing expense data, broken down by stage — no new data entry, purely analytical. |
| **ROI / ROI Reporting** | Cash-basis return calculation — compares actual cash **received** against actual cash **paid**, not committed/logged totals, so an unpaid invoice doesn't distort ROI. |
| **Users, Roles & Settings** | Admin-only. User management, the Roles & Permissions matrix, system currency setting, company profile (used on PDF/Excel export letterheads), and per-project staff access assignment. |
| **Exports** | Real client-side generated Excel (BSR, Payments Schedule, Income Statement, portfolio statement) and PDF (quotes, reports) — not mockups, built from live data. |

---

## 6. Client-Requested Enhancements — Status

All 7 enhancements originally requested by the client (see `Front end/Vega_Construction_Enhancements.md`
in this repo) are **built and verified**:

| # | Enhancement | Status |
|---|---|---|
| 1 | User-scoped project visibility | ✅ Done |
| 2 | Unique Basic Price/Rate per project | ✅ Done |
| 3 | Free-text material description on BSR items | ✅ Done |
| 4 | Partial/full payment allocation for expenses | ✅ Done |
| 5 | Payment summary for suppliers & sub-contractors | ✅ Done |
| 6 | Row-wise, stage-based expense entry with cost highlighting | ✅ Done (built as the Stage Costs tab — a cost-analysis view rather than a new entry flow; scope narrowed with client input) |
| 7 | Multiply/divide factor calculator on BSR items | ✅ Done (per-line estimation helper — view-only, doesn't alter stored data) |

---

## 7. Key Business Rules Worth Knowing

A few rules in the system aren't obvious from the feature list alone, and matter for how the
numbers actually behave:

- **Cash-basis accounting**: ROI and "received" totals are driven by actual recorded payments,
  never by the full logged/committed amount. Logging a large unpaid expense does not tank ROI.
- **Cheque handling**: a deposited cheque sits in its own "pending" bucket — it counts as
  neither received nor outstanding until it clears the bank (counts as received) or bounces
  (falls back to outstanding).
- **Stage value rebalancing**: a project's contract value splits evenly across its payment
  stages by default, but any stage's value can be manually overridden — the remaining
  (non-overridden) stages automatically rebalance around it so the total always still equals
  the contract value.
- **Snapshot pricing**: once a BSR recipe component or expense line item is created, its
  price/amount is locked in at that point — it does not silently change if the underlying
  catalog price is edited later. Full price-change history is tracked separately per item.
- **Per-project isolation**: two projects can have items with the identical code (e.g.
  `M-026`) that are completely independent records with independent prices — codes are only
  guaranteed unique *within* a project, not company-wide.

---

## 8. Non-Functional Requirements

### Security

- Real authentication: hashed passwords, signed session tokens, server-side session
  revocation (a demoted/deactivated user is locked out on their very next request, not after
  their token happens to expire)
- Login throttling and lockout against brute-force attempts
- Full role-based access control on every module and action
- Security headers (HSTS, CSP, clickjacking protection, etc.) on every response
- A dedicated **session idle timeout** (separate from the absolute session expiry) — an
  unattended, logged-in session is automatically ended after a period of inactivity, distinct
  for "remember me" vs. regular sessions
- A structured pre-handover security audit is in progress (see §10)

### Data Integrity

- Every price change is logged to a permanent history table
- Payments are additive and immutable once recorded (corrections happen via new entries, not
  silent edits) — outstanding balances are always computed live from that history, never
  stored and drifted

### Usability

- Dark/light mode, persisted per browser
- Single system-wide currency setting — change it once, every screen updates
- Configurable dropdown lists (categories, trades, units) instead of hardcoded values, so an
  Admin can extend them without a code change

---

## 9. Technical Overview

*(Detail for engineering reference — see `architecture/` in this repo for full diagrams.)*

- **Stack**: Next.js 16 (React 19), TypeScript, Tailwind CSS
- **Database**: PostgreSQL (migrated from Cloudflare D1/SQLite in September 2026), schema
  managed via Prisma
- **Hosting**: currently Cloudflare Workers; **migrating to Azure App Service** per client/company
  direction (see §10)
- **CI/CD**: currently GitHub Actions; **migrating to Azure DevOps** alongside the hosting move

---

## 10. Current Status & In-Progress Work

| Item | Status |
|---|---|
| Core application (all modules in §5) | ✅ Built, live, in use |
| All 7 client enhancements | ✅ Built (see §6) |
| Database migration to PostgreSQL | ✅ Complete and verified |
| Session idle-timeout hardening | ✅ Complete |
| Hosting migration to Azure App Service | 🔧 In progress |
| CI/CD migration to Azure DevOps | 🔧 Blocked — pending an Azure DevOps access-level upgrade (current account is on a restricted "Stakeholder" tier that cannot access Git repos) |
| Pre-handover backend security audit (12 route families) | 🔧 In progress — 1 of 12 families complete and passed with minor notes; remaining 11 not yet started |

---

## 11. Known Open Items / Risks

1. **Security audit is only 8% complete** (1/12 route families) — should be finished before
   final client handover, since it covers access-control correctness across the whole API.
2. **Azure DevOps migration is stalled on an access permission**, not a technical blocker —
   needs an org admin to resolve.
3. **Gap #11** (rate-change propagation) is the one remaining item from the original discovery
   gap analysis without a client-approved resolution.
4. The hosting migration (Cloudflare → Azure) is a real infrastructure cutover, not yet
   scheduled for production — needs a maintenance window when it happens, since it involves a
   one-time forced re-login for all users and a database cutover.

---

## 12. References

Supporting documents in this repository:

- `architecture/` — C4 diagrams, database ER diagrams, architecture overview
- `GAP_ANALYSIS.md` (`New folder/`) — full discovery gap analysis, all 11 items
- `Front end/Vega_Construction_Enhancements.md` — original client enhancement requests, verbatim
- `backend-security-report/` — security audit progress and findings
- `test/security/` — security hardening plans (auth, session, remediation)
- `VegaConstruction_System_BRD.pdf` — original business requirements document
