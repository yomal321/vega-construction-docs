# Architecture Documentation

Diagrams and schema reference for **Vega Construction Manager**.

All `.drawio.xml` files open directly in [draw.io / diagrams.net](https://app.diagrams.net) —
**File → Open From → Device**, or drag the file onto the canvas. They're plain mxGraph XML, so they're
diff-able in git and editable by hand.

## C4 model diagrams

Read them in order — each one zooms in a level.

| File | Level | Answers |
|---|---|---|
| [c4-1-context.drawio.xml](c4-1-context.drawio.xml) | **L1 — Context** | Who uses the system, and what does it depend on? |
| [c4-2-container.drawio.xml](c4-2-container.drawio.xml) | **L2 — Container** | What are the deployable pieces, and how do they communicate? |
| [c4-3-component.drawio.xml](c4-3-component.drawio.xml) | **L3 — Component** | Inside the Worker: what does a request pass through? |

Standard C4 colours apply: **dark blue** = person, **mid blue** = in-scope system or container,
**light blue** = component, **grey** = external. Dashed boundaries mark scope, not deployment.

There is no L4 (code) diagram — at that level the source is clearer than a picture, and it goes stale
immediately.

## Database

| File | What it is |
|---|---|
| [database-er-overview.drawio.xml](database-er-overview.drawio.xml) | ER diagram, **entity names only**, grouped by domain. Start here |
| [database-er-full.drawio.xml](database-er-full.drawio.xml) | ER diagram with **every column**, PK/FK/unique markers, and all 30 relationships |
| [database-schema.md](database-schema.md) | Written reference — every table, column meaning, and the conventions behind them |

Edge colours in the full ER: **grey** = one-to-many, **green** = one-to-one (draft promoted to rate
item), **red dashed** = user reference (owner / audit columns), **orange dashed** = optional supplier
link. Table header colour marks the domain.

## Whole-system overview

| File | What it is |
|---|---|
| [vega-manager-architecture-overview.drawio.xml](vega-manager-architecture-overview.drawio.xml) | Seven-box layered view — the simplest picture of the stack |
| [vega-manager-architecture.drawio.xml](vega-manager-architecture.drawio.xml) | Same layers, expanded to file and route level. Useful for onboarding, dense for presenting |

## Two things to know before reading any of these

1. **Prisma is not in the request path.** `prisma/schema.prisma` owns the schema and migrations, but API
   routes query D1 directly through its native binding (`src/lib/db.ts`). This was deliberate — Prisma's
   WASM query engine doesn't bundle correctly through the OpenNext Cloudflare adapter.
2. **Access control has two independent axes.** *Reach* (which projects you can see) comes from
   `projects.ownerId` plus `project_members`. *Capability* (what you can do) comes from
   `PERMISSION_CATALOG` via roles and direct user grants. Membership grants reach only — it never implies
   a permission. `role = 'Admin'` bypasses the capability axis entirely.
3. **Login is single-factor by design.** The client declined MFA, so `0026_remove_mfa.sql` removed
   everything `0025_mfa.sql` had added (it was never wired up — no route served it). Brute-force
   resistance comes from `login_throttle` and the Cloudflare edge rate limiter. Don't read the absence
   of a second factor here as an oversight.

## Keeping these current

These are hand-maintained, not generated. The schema files are the ones most likely to drift — when you
add a migration, update [database-schema.md](database-schema.md) and the full ER in the same change.

No known drift: as of `0026_remove_mfa.sql`, `prisma/schema.prisma` matches what D1 actually holds.
