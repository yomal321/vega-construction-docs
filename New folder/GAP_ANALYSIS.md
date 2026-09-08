# Gap Analysis — Manual Process → System Conversion
**Vega Construction / Vega Homes — Price List, BSR & Payment/ROI System**
Prepared while converting the BRD + Project Summary + client's real Excel sheets into the system design.

This document lists every discrepancy, ambiguity, or gap found between (a) what the BRD/Summary
describe, (b) what the client's actual working Excel sheets show, and (c) what a working system
needs to resolve cleanly. Each item includes: what the gap is, how it was resolved for this
prototype, and whether it still needs client sign-off.

---

## 1. Construction stage count: BRD says 5, real usage shows 4

**Gap:** The BRD (Section 2.2, FR-3.1) and Project Summary both hardcode "5 fixed construction
stages." The client's actual `Payments_Schedule_Cash_Flow.xlsx` for a real project only has
**4 stages** (STAGE-01 to STAGE-04), each still split 50/25/25.

**Why this matters:** If stage count is hardcoded to 5 as the BRD instructs, the system would
not match how this project — or possibly others — is actually run. Hardcoding either number
risks being wrong for some project.

**Resolution:** Stage count is **configurable per project** rather than hardcoded to either 5
or 4. Confirmed with you directly.

**Status:** ✅ Resolved — confirmed by you.

---

## 2. Payment milestone scope: BRD marks this as unconfirmed

**Gap:** BRD Section 6 (Assumptions) explicitly flags: *"The 3 payment milestones (50%/25%/25%)
apply once per construction stage... pending client confirmation."* This was an open item in
the source document itself, not just something we noticed.

**Resolution:** Confirmed by you as **once per stage** (so a 4-stage project has 4×3=12
payments; a 5-stage project has 15). Schema and stage-creation logic generate exactly 3
`stage_payments` rows per stage automatically.

**Status:** ✅ Resolved — confirmed by you.

---

## 3. "Price list" is described as flat, but real usage is a full rate-analysis engine

**Gap:** The BRD (FR-1.1–FR-1.5) and Summary describe Module 1 as a simple flat list: item,
unit, price. But the client's real `BSR_for_Pricing.xlsx` shows something considerably more
complex — ~150 **composite trade items** (e.g. "Random Rubble Masonry in foundation"), each
built from a **recipe** of base materials/labour/plant, with rates that **escalate by floor**,
and some trade items referencing *other* trade items as ingredients (e.g. a concrete-mix rate
feeding into a column rate).

**Why this matters:** If we'd built only what the BRD literally describes, the client would
open the system, look for their real pricing method, and not find it — a functional gap
between "requirements as written" and "how the business actually works." This is the single
biggest gap found in this whole exercise.

**Resolution:** Built the full rate-analysis engine: `base_items` (flat list) feed into
`trade_items` via a self-referencing `trade_item_components` recipe table, with a recursive
rate-resolution service and per-floor multipliers. Confirmed by you as the direction to build.

**Status:** ✅ Resolved — confirmed by you. This is scoped larger than the original BRD; worth
noting to the client that the delivered system does more than FR-1.1–FR-1.5 describe.

---

## 4. Expense tracking: BRD is vague, real ledger is detailed

**Gap:** BRD FR-3.4/FR-3.5 just say the dashboard should show "payments made (expenses)" and
"total project expenses" — no structure specified. The real `Income_Balance_Statement` and
`Payments_Schedule_Cash_Flow` sheets track expenses in much more detail: vendor name,
invoice/memo number, category (Labour/Material/Sub Contractor/Machinery/Transport/Other),
which stage and BOQ item it relates to, payment method (Cash/Bank/Online), and running
cumulative totals.

**Resolution:** Built the detailed version — `expenses` table captures vendor, category,
invoice ref, linked stage, linked trade item (BOQ ref), payment method. Confirmed by you.

**Status:** ✅ Resolved — confirmed by you.

---

## 5. Single-user assumption invalidated, then role model simplified

**Gap:** BRD Section 6 assumes single primary user "unless additional staff/user roles are
confirmed." You confirmed multiple roles are needed.

**Why this matters:** This isn't just a UI change — it means every price/rate table needs
**who changed it**, not just when, and every write action needs a permissions model. A
single-user system retrofitted for multi-user later usually means rebuilding the schema.

**First pass:** Built with a 3-role split (Admin / Estimator / Accounts) based on how the
business appeared to operate (estimating vs. bookkeeping are naturally separate work).

**Final resolution:** You've since clarified the real structure is simpler — **2 admins**
plus everyone else on **one shared role**. Rebuilt around this: `user_role` is now just
`admin` (full control, incl. currency setting and user management) and `staff` (everything
operational — price list, trade items, BSR, payment status, expenses). Every route that
previously distinguished estimator-only vs. accounts-only actions now allows either `admin`
or `staff`. Audit logging (`changed_by`) is unaffected by this simplification.

**Status:** ✅ Resolved — confirmed and rebuilt.

---

## 6. "Supplier rate" category — inconsistent wording in the BRD itself

**Gap:** The BRD uses inconsistent terms for the same thing across its own sections: Executive
Summary says "materials, labor, and rates"; Section 2.1 says "materials, labor, and
suppliers"; FR-1.3 says "materials, labor, suppliers." Meanwhile the real Excel sheet's actual
categories are Material / Labour / **Plant** — "supplier" doesn't appear as a category there
at all.

**Resolution:** Per your answer, "supplier" is **not** a distinct category — it's folded into
materials as a source note, not a separate schema category. The system's three real categories
are `material`, `labour`, `plant`, matching the client's actual working sheet rather than the
BRD's inconsistent wording.

**Status:** ✅ Resolved — confirmed by you.

---

## 7. "Match existing format" (FR-2.1, FR-3.7) — literal vs. functional

**Gap:** Both the BSR module and the dashboard are required to "recreate the existing Excel
layout/format" per the BRD, but "layout/format" is never defined — literal pixel-for-pixel
recreation of the Excel grid, or just the same underlying data model with a normal modern UI.

**Resolution:** Per your answer, functional equivalence is sufficient — same data, sensible
modern UI, not a literal Excel-grid recreation.

**Status:** ✅ Resolved — confirmed by you.

---

## 8. Referenced "Open Questions" section is missing from the BRD

**Gap:** BRD Section 6 says "pending client confirmation (see Open Questions)" — implying a
dedicated Open Questions section or document exists. It is not present in either PDF provided
(the BRD ends at Section 6 - Assumptions, 4 pages total).

**Resolution:** You confirmed there's no separate document — this gap analysis file now serves
that purpose instead.

**Status:** ✅ Resolved — this document is the substitute.

---

## 9. Currency — confirmed default, made configurable rather than fixed

**Gap:** BRD Section 6 says "the system will initially support a single currency" but never
states which one. The client's real sheets use LKR (Sri Lankan Rupees) implicitly (no currency
symbol shown, but Vega Construction/Vega Homes operates in Sri Lanka per their sheets and the
BISTEC document footer).

**Resolution:** Rather than hardcoding LKR as the BRD's assumption suggested, currency is now a
**configurable system setting** (`system_settings` table, defaulting to `LKR`), switchable by
an admin from a dropdown in the sidebar — matching your preference for flexibility (e.g. if
Vega ever takes an overseas contract) over a fixed hardcoded value. All money displays across
the app now read from this setting instead of a literal "LKR" string.

**Status:** ✅ Resolved — confirmed and rebuilt as configurable.

---

## 10. Price history: timestamp-only vs. full version history

**Gap:** BRD Section 6 says historical price changes are "assumed to only require a
'last updated' timestamp... not a full version history — to be confirmed." This was flagged
as unconfirmed in the source document.

**Resolution:** Built with an `audit_log` table that actually stores full old/new value
history on every base_item/trade_item change (not just a bare timestamp) — this gives you
full version history essentially for free, since the audit trail was already needed for the
multi-user requirement (Gap #5). You confirmed this approach is good as-is. A "view price
history" browsing screen isn't built yet, but the data is fully captured and ready for one
whenever it's wanted.

**Status:** ✅ Resolved — approach confirmed by you. UI for browsing history remains a
straightforward future addition if needed.

---

## 11. Rate changes don't propagate downstream — no warning, no easy fix

**Gap:** Rates get copied ("snapshotted") at three separate points in the pipeline — Basic Price → Basic Rate
(on promotion) and Basic Rate → a trade item's recipe (when an ingredient is added to a recipe). None of these
snapshots are live links. If a rate changes upstream after the fact, nothing downstream updates, and — more
importantly — **nothing tells the user it happened.** A trade item built against Cement at LKR 1,250 will keep
showing that number forever, even after Cement is corrected to LKR 1,500 in Basic Rate, with no flag, badge,
or warning anywhere on the BSR screen. The only way to fix it today is to manually delete the recipe component
and re-add it.

**Why this matters:** Snapshotting itself is defensible — once a customer has agreed to a quoted price, you
don't want it silently changing underneath them. But right now the system has the "locking" half of that
idea without the "visibility" half. For a project still being estimated (pre-contract), a rate correction
upstream can drift out of every recipe that used it, with no way to notice short of manually re-checking
every ingredient in every recipe by hand — which is the exact manual, error-prone problem this system was
built to eliminate (see the BRD's own Problem Statement).

**Recommendation:** Keep snapshot-at-add-time as the default — don't change locking behaviour, since it
protects already-quoted/signed work. Add the piece that's missing instead:
- A lightweight flag/badge on any BSR item whose ingredient's current Basic Rate no longer matches the rate
  stored in that item's recipe ("price changed since this was added").
- A one-click "Update to current rate" action on that flagged item, instead of the current delete-and-re-add
  workaround.

This gives two things at once: stability for work that's already under contract, and visibility for estimates
still being assembled — instead of the current state, which has neither warning nor an easy correction, just
quiet drift.

**Detailed behaviour rules (worked out with the client, for the flag/fix mechanism above):**

*Rule 1 — a rate change flags every recipe that used it, everywhere.* Say you built 3 different BSR items in
3 different projects, and all 3 of them used Cement as one ingredient — each locked in Cement's price at
1,250 when they were built. Now you go to Basic Rate and change Cement's price from 1,250 to 1,500. The rule:
all 3 of those BSR items should get flagged — not just one. Because all 3 used that same Cement rate, and all
3 are now out of date. So it's not "one ingredient → one flag." It's "one ingredient → flag everywhere it was
used." If Cement is used in 10 different recipes across 5 different projects, changing Cement's rate flags
all 10. Each flagged item still follows Rule 2 below (one flag, not stacking), and:
- Click "update to current rate" on that item → it updates, flag clears for that one.
- The other 9 flagged items stay flagged until you go fix each one too — updating one doesn't fix the rest
  automatically, since each recipe is its own separate copy.

*Rule 2 — one flag, not a pile of flags.* Only show 1 flag, not many flags, no matter how many times the
source rate changes before someone acts on it. Example: Basic Price changes 3 times — 100 → 110 → 120. Don't
show 3 separate warnings. Just show 1 warning that says "this is outdated," and compare against the newest
number (120). Once the user updates Basic Rate to 120, the flag goes away. If the price changes again later,
a new single flag appears again. So it's just: flag ON or flag OFF — never a list, never stacking up. Simple
on/off switch, not a history.

*Rule 3 — duplicate ingredients don't cross-flag each other.* This covers what happens when there's more than
one Basic Price entry for what is really the same material. Example: someone adds "Cement" as a draft and
promotes it to Basic Rate as code M-050. Later, someone else (not knowing M-050 already exists) adds "Cement"
again as a brand new separate draft, and promotes that one too — now you get a second code, say M-095, also
called "Cement." These two are not connected to each other — they're two completely separate records that
just happen to share a name by accident. So the rule is: if you edit the first "Cement" (the one that became
M-050), only M-050 gets the flag — M-095 does NOT get flagged, even though it's also called "Cement." They're
treated as two different items, not one. **Side issue worth flagging to the client:** maybe the app should
warn you when you're about to create a duplicate (e.g. "a similar item called Cement already exists") — to
stop this confusing double-entry situation from happening in the first place.

**Status:** 🟡 Open — recommendation proposed, pending client decision on whether this matches how Vega
expects rate corrections to behave.

---

## Summary table

| # | Gap | Status |
|---|---|---|
| 1 | Stage count 5 vs. 4 | ✅ Resolved — configurable |
| 2 | Milestone split once per stage | ✅ Resolved — confirmed |
| 3 | Flat price list vs. rate-analysis engine | ✅ Resolved — full engine built |
| 4 | Expense tracking detail level | ✅ Resolved — detailed |
| 5 | Single vs. multi-user, role structure | ✅ Resolved — simplified to admin/staff |
| 6 | "Supplier" category inconsistency | ✅ Resolved — folded into materials |
| 7 | "Match existing format" literalness | ✅ Resolved — functional equivalence |
| 8 | Missing "Open Questions" doc | ✅ Resolved — this file is the substitute |
| 9 | Currency not named | ✅ Resolved — configurable, defaults to LKR |
| 10 | Price history depth | ✅ Resolved — full audit history captured |
| 11 | Rate changes don't propagate downstream, no warning/fix | 🟡 Open — recommendation proposed, pending client decision |

Items 1–10 are resolved and reflected in the codebase. Item 11 is a newly identified design gap awaiting
client input.
