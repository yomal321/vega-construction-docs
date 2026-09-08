# Vega Construction — Price List, BSR & Payment/ROI System

Prototype build for Vega Construction (Vega Homes), based on the BRD, project summary,
and the client's real working spreadsheets (Basic Prices, Rate Analysis, Income/Balance
Statement, Payments Schedule).

## Locked-in scope decisions (confirmed in requirements discussion)

| Decision | Choice |
|---|---|
| Users | Multi-user with roles: `admin`, `estimator`, `accounts` |
| Audit trail | Every price/rate change stamps **who** + **when** |
| Construction stages | **Configurable per project** (not hardcoded to 4 or 5) |
| Payment milestones | 3 per stage — Advance 50% / Interim 25% / Final 25%, applied **once per stage** |
| Payment status | Paid / Not Received / Paid via Cheque |
| Pricing engine | **Full rate-analysis engine**: base items (material/labour/plant) roll up into composite trade items via recipes, with floor-based rate escalation, matching the client's real BSR workbook |
| Expense tracking | Detailed: vendor, category, invoice reference, linked BOQ/trade item, linked stage |
| Currency | Single currency (LKR, per client's sheets) |

## 1. System Architecture

```
                        ┌─────────────────────────┐
                        │   React SPA (Vite)      │
                        │  Price List / BSR /      │
                        │  Projects / Dashboard    │
                        └───────────┬─────────────┘
                                    │ HTTPS / JSON (JWT bearer)
                        ┌───────────▼─────────────┐
                        │   Express API server     │
                        │  ┌─────────────────────┐ │
                        │  │ Auth & role middleware│ │
                        │  ├─────────────────────┤ │
                        │  │ Rate Engine service   │ │  <- recursive recipe resolver
                        │  │ (base items -> trade  │ │     + floor multiplier
                        │  │  items -> BSR lines)  │ │
                        │  ├─────────────────────┤ │
                        │  │ REST routes           │ │
                        │  └─────────────────────┘ │
                        └───────────┬─────────────┘
                                    │ SQL (pg)
                        ┌───────────▼─────────────┐
                        │      PostgreSQL          │
                        │ users, base_items,       │
                        │ trade_items + recipes,   │
                        │ projects, stages,        │
                        │ payments, bsr, expenses,  │
                        │ audit_log                │
                        └─────────────────────────┘
```

**Why this stack:** Postgres because the rate engine is inherently relational
(recipes referencing recipes, foreign keys everywhere) and needs transactional
integrity for money; Express because the API surface is plain CRUD + one
non-trivial service (the rate engine) — no need for a heavier framework;
React/Vite for a fast-to-build, easy-to-extend SPA. This stack scales
horizontally (stateless API behind a load balancer, managed Postgres with
read replicas) without any rework — the same shape used by most production
SaaS at this size.

**Scaling path (not built now, but the schema supports it):**
- Add a `tenants` table + `tenant_id` FK everywhere → multi-client SaaS
- Move file/report generation to a background queue (BullMQ + Redis)
- Read replica for the dashboard/reporting queries once the ledger grows
- Cache resolved trade-item rates (they only change when a recipe or a base
  price changes) instead of recomputing the recursive resolution on every read

## 2. File Structure

```
vega/
├── backend/
│   ├── package.json
│   ├── .env.example
│   ├── migrations/
│   │   └── 001_init.sql          # full schema, source of truth
│   └── src/
│       ├── server.js             # app entry
│       ├── config/db.js          # pg pool
│       ├── middleware/
│       │   ├── auth.js           # JWT verify
│       │   └── roles.js          # role-based guard
│       ├── utils/
│       │   ├── audit.js          # generic audit-log writer
│       │   └── rateEngine.js     # recursive rate resolution
│       └── routes/
│           ├── auth.routes.js
│           ├── baseItems.routes.js
│           ├── tradeItems.routes.js
│           ├── projects.routes.js
│           ├── bsr.routes.js
│           ├── expenses.routes.js
│           └── dashboard.routes.js
└── frontend/
    ├── package.json
    ├── index.html
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css
        ├── api/client.js
        ├── context/AuthContext.jsx
        ├── components/
        │   ├── Layout.jsx
        │   └── ProtectedRoute.jsx
        └── pages/
            ├── Login.jsx
            ├── PriceList.jsx
            ├── TradeItems.jsx
            ├── Projects.jsx
            ├── ProjectDetail.jsx
            └── Dashboard.jsx
```

## 3. Database Schema

See `backend/migrations/001_init.sql` for the executable version. Summary:

- **users** — id, name, email, password_hash, role (`admin`/`estimator`/`accounts`)
- **base_items** — the flat price list (materials/labour/plant): code, category,
  description, unit, unit_price, updated_at, updated_by → audit built in
- **trade_items** — composite BOQ/rate items (e.g. "Excavation in trenches..."):
  code, description, unit, analysis_qty (the "Analysis for N unit" basis)
- **trade_item_components** — the recipe: each row says "this trade item needs
  X quantity of [a base_item OR another trade_item]" — this self-referencing
  design is what lets concrete-mix rates feed into column/beam/slab rates,
  exactly like the real workbook
- **trade_item_floor_rates** — optional per-floor rate override/multiplier
  (ground floor, 1st, 2nd, 3rd...) since labour cost rises by floor
- **projects** — client, site, name, stage_count (configurable, not hardcoded)
- **project_stages** — one row per stage per project: stage_number, name,
  start_date, target_date, actual_completion_date
- **stage_payments** — exactly 3 rows per stage (Advance/Interim/Final),
  percentage, computed amount, status, paid_date
- **bsr** — one BSR (estimate) per project
- **bsr_line_items** — items added to a BSR, referencing a trade_item, storing
  quantity, the floor level, and a **snapshot of the rate at time of adding**
  (so historical BSRs don't silently change if prices update later)
- **expenses** — vendor_name, category, invoice_ref, amount, date,
  payment_method, linked project_stage_id, linked trade_item_id (BOQ ref)
- **audit_log** — generic table_name/record_id/action/changed_by/changed_at/
  old_value/new_value, used for base_items and trade_items price changes

## 4. API Endpoints

```
POST   /api/auth/login
GET    /api/auth/me

GET    /api/base-items                 ?category=&search=
POST   /api/base-items                 (admin, estimator)
PUT    /api/base-items/:id             (admin, estimator) -> auto audit-logged
DELETE /api/base-items/:id             (admin)

GET    /api/trade-items                ?category=&search=
GET    /api/trade-items/:id            -> includes resolved recipe + computed rate
POST   /api/trade-items                (admin, estimator)
PUT    /api/trade-items/:id            (admin, estimator)
POST   /api/trade-items/:id/components (admin, estimator)  add/replace recipe line
GET    /api/trade-items/:id/rate       ?floor=ground        -> resolved rate

GET    /api/projects
POST   /api/projects                   { name, client, site, stage_count }
GET    /api/projects/:id               -> includes stages + payment milestones
PUT    /api/projects/:id/stages/:stageId

GET    /api/projects/:id/bsr
POST   /api/projects/:id/bsr/items     { trade_item_id, quantity, floor }
DELETE /api/bsr-items/:id

GET    /api/projects/:id/payments
PUT    /api/payments/:id               { status, paid_date }

GET    /api/projects/:id/expenses
POST   /api/projects/:id/expenses      { vendor, category, invoice_ref, amount, stage_id, trade_item_id }

GET    /api/projects/:id/dashboard     -> income, expenses by category, ROI, outstanding
GET    /api/dashboard/summary          -> portfolio-wide totals (all projects, role-scoped)
```

## 5. UI Architecture

```
/login                          Login
/                                Dashboard (portfolio ROI summary)
/price-list                     Flat base items: search/filter by category, inline edit
/trade-items                    List of composite rate items
/trade-items/:id                Recipe builder: add base or trade items as components,
                                 shows live-computed rate, per-floor rate table
/projects                       List of projects
/projects/:id                   Tabs: Overview | BSR | Stages & Payments | Expenses
/projects/:id/bsr                 Add trade items with qty + floor -> live line totals
/projects/:id/payments            Stage list, each with 3 milestone rows, status dropdown
/projects/:id/expenses            Expense log with vendor/category/invoice/BOQ ref
```

Role-based UI: `accounts` role doesn't see Price List/Trade Items edit controls
(read-only); `estimator` doesn't see Payments status editing; `admin` sees
everything, including user management (stubbed for this prototype).

## 6. Running it

```bash
# Backend
cd backend
cp .env.example .env      # set DATABASE_URL, JWT_SECRET
npm install
psql "$DATABASE_URL" -f migrations/001_init.sql
npm run dev                # http://localhost:4000

# Frontend
cd frontend
npm install
npm run dev                # http://localhost:5173
```

## 7. What's scaffolded vs. what's a stub

Fully implemented: schema, auth, rate engine (recursive + floor rates),
base items CRUD w/ audit, trade items CRUD w/ recipe, projects/stages/payments
computation, BSR line items, expenses, dashboard ROI aggregation, and working
React pages for Login, Price List, Trade Items (with recipe builder), Projects,
Project Detail (BSR + Payments + Expenses tabs), Dashboard.

Left as clearly-marked TODOs (next iteration, not needed to validate the
prototype): user management UI, password reset, CSV export, pagination
UI (API supports `?limit&offset` already), file attachments on expenses.
