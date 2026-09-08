-- Vega Construction System — initial schema
-- Run with: psql "$DATABASE_URL" -f 001_init.sql

CREATE TYPE user_role AS ENUM ('admin', 'estimator', 'accounts');
CREATE TYPE item_category AS ENUM ('material', 'labour', 'plant');
CREATE TYPE component_kind AS ENUM ('base_item', 'trade_item');
CREATE TYPE payment_milestone AS ENUM ('advance', 'interim', 'final');
CREATE TYPE payment_status AS ENUM ('paid', 'not_received', 'paid_via_cheque');
CREATE TYPE floor_level AS ENUM ('ground', 'first', 'second', 'third', 'fourth');

-- ---------- Users ----------
CREATE TABLE users (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          user_role NOT NULL DEFAULT 'estimator',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Module 1: Base Price List ----------
CREATE TABLE base_items (
  id          SERIAL PRIMARY KEY,
  code        TEXT UNIQUE,                 -- e.g. M-026, L-009, P-001
  category    item_category NOT NULL,      -- material / labour / plant
  trade_group TEXT,                        -- e.g. CONCRETE, EXCAVATION (for search/filter)
  description TEXT NOT NULL,
  unit        TEXT NOT NULL,               -- Bag, Day, Cube, L.ft ...
  unit_price  NUMERIC(14,2) NOT NULL DEFAULT 0,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by  INTEGER REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_base_items_category ON base_items(category);
CREATE INDEX idx_base_items_search ON base_items USING gin (to_tsvector('english', description));

-- ---------- Composite BOQ / rate-analysis items ----------
CREATE TABLE trade_items (
  id            SERIAL PRIMARY KEY,
  code          TEXT UNIQUE,               -- e.g. 04.01, 05.A.02
  description   TEXT NOT NULL,
  unit          TEXT NOT NULL,             -- Cube, Sqr, L.ft ...
  analysis_qty  NUMERIC(14,4) NOT NULL DEFAULT 1,  -- "Analysis for N unit" basis
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by    INTEGER REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_trade_items_search ON trade_items USING gin (to_tsvector('english', description));

-- Recipe lines: a trade item is built from N quantity of a base_item OR another trade_item.
-- This self-referencing design lets e.g. "Mixing Concrete 1:2:4" feed into "Column Concrete".
CREATE TABLE trade_item_components (
  id              SERIAL PRIMARY KEY,
  trade_item_id   INTEGER NOT NULL REFERENCES trade_items(id) ON DELETE CASCADE,
  component_kind  component_kind NOT NULL,
  base_item_id    INTEGER REFERENCES base_items(id),
  child_trade_item_id INTEGER REFERENCES trade_items(id),
  quantity        NUMERIC(14,6) NOT NULL,
  note            TEXT,                    -- e.g. "Allow 2.5% for Tools"
  CONSTRAINT one_component_target CHECK (
    (component_kind = 'base_item' AND base_item_id IS NOT NULL AND child_trade_item_id IS NULL) OR
    (component_kind = 'trade_item' AND child_trade_item_id IS NOT NULL AND base_item_id IS NULL)
  ),
  -- a trade item cannot include itself directly (deeper cycles are guarded in app code)
  CONSTRAINT no_self_reference CHECK (child_trade_item_id IS DISTINCT FROM trade_item_id)
);
CREATE INDEX idx_tic_trade_item ON trade_item_components(trade_item_id);

-- Optional per-floor rate multiplier/override (labour costs more the higher you build)
CREATE TABLE trade_item_floor_rates (
  id             SERIAL PRIMARY KEY,
  trade_item_id  INTEGER NOT NULL REFERENCES trade_items(id) ON DELETE CASCADE,
  floor          floor_level NOT NULL,
  multiplier     NUMERIC(6,4) NOT NULL DEFAULT 1.0,  -- e.g. 1.10 = +10% vs ground floor
  UNIQUE (trade_item_id, floor)
);

-- ---------- Projects ----------
CREATE TABLE projects (
  id           SERIAL PRIMARY KEY,
  name         TEXT NOT NULL,
  client_name  TEXT NOT NULL,
  site_address TEXT,
  stage_count  INTEGER NOT NULL DEFAULT 4 CHECK (stage_count > 0),  -- configurable, not hardcoded
  created_by   INTEGER REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_stages (
  id                     SERIAL PRIMARY KEY,
  project_id             INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  stage_number           INTEGER NOT NULL,
  name                   TEXT NOT NULL,        -- e.g. "Stage 1", or a custom label
  start_date             DATE,
  target_date            DATE,
  actual_completion_date DATE,
  contract_amount        NUMERIC(14,2) NOT NULL DEFAULT 0,  -- basis for the 3 milestone amounts
  UNIQUE (project_id, stage_number)
);

-- Exactly 3 rows created per stage: advance 50%, interim 25%, final 25%
CREATE TABLE stage_payments (
  id               SERIAL PRIMARY KEY,
  project_stage_id INTEGER NOT NULL REFERENCES project_stages(id) ON DELETE CASCADE,
  milestone        payment_milestone NOT NULL,
  percentage       NUMERIC(5,4) NOT NULL,       -- 0.50 / 0.25 / 0.25
  amount           NUMERIC(14,2) NOT NULL,      -- contract_amount * percentage, snapshotted
  status           payment_status NOT NULL DEFAULT 'not_received',
  paid_date        DATE,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by       INTEGER REFERENCES users(id),
  UNIQUE (project_stage_id, milestone)
);

-- ---------- Module 2: BSR ----------
CREATE TABLE bsr (
  id         SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title      TEXT NOT NULL DEFAULT 'Building Schedule of Rates',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bsr_line_items (
  id            SERIAL PRIMARY KEY,
  bsr_id        INTEGER NOT NULL REFERENCES bsr(id) ON DELETE CASCADE,
  trade_item_id INTEGER NOT NULL REFERENCES trade_items(id),
  floor         floor_level NOT NULL DEFAULT 'ground',
  quantity      NUMERIC(14,4) NOT NULL,
  rate_snapshot NUMERIC(14,2) NOT NULL,   -- resolved rate at time of adding (doesn't drift later)
  line_total    NUMERIC(16,2) GENERATED ALWAYS AS (quantity * rate_snapshot) STORED,
  added_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  added_by      INTEGER REFERENCES users(id)
);
CREATE INDEX idx_bsr_line_items_bsr ON bsr_line_items(bsr_id);

-- ---------- Module 3: Expenses (detailed, per confirmed scope) ----------
CREATE TYPE expense_category AS ENUM
  ('labour', 'material', 'sub_contractor', 'machinery', 'transport', 'other');

CREATE TABLE expenses (
  id               SERIAL PRIMARY KEY,
  project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  project_stage_id INTEGER REFERENCES project_stages(id),
  trade_item_id    INTEGER REFERENCES trade_items(id),   -- BOQ item reference
  vendor_name      TEXT NOT NULL,
  category         expense_category NOT NULL,
  invoice_ref      TEXT,
  amount           NUMERIC(14,2) NOT NULL,
  expense_date     DATE NOT NULL DEFAULT CURRENT_DATE,
  payment_method   TEXT,                                  -- Cash / Bank / Online / Cheque
  notes            TEXT,
  created_by       INTEGER REFERENCES users(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_expenses_project ON expenses(project_id);
CREATE INDEX idx_expenses_category ON expenses(category);

-- ---------- Generic audit log (price/rate changes) ----------
CREATE TABLE audit_log (
  id          SERIAL PRIMARY KEY,
  table_name  TEXT NOT NULL,
  record_id   INTEGER NOT NULL,
  action      TEXT NOT NULL,              -- 'create' | 'update' | 'delete'
  changed_by  INTEGER REFERENCES users(id),
  changed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  old_value   JSONB,
  new_value   JSONB
);
CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);

-- ---------- Seed: one admin so the app is usable on first boot ----------
-- password is "changeme123" bcrypt-hashed — CHANGE THIS after first login
INSERT INTO users (name, email, password_hash, role) VALUES
  ('Admin', 'admin@vegaconstruction.lk',
   '$2b$10$8KzQxT1Y5xnE0m4x0Yf2ce2h7fz1mCUEPqR/6VqmzO3F0i5mE0h5.', 'admin');
