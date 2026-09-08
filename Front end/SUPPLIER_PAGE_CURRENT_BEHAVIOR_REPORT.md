# Current situation: expense logged with a "no supplier" catalog item, then checked on the Supplier's page

## What was done

1. A Basic Price item was created with no supplier assigned, then promoted to a Basic Rate item
   (still no supplier).
2. In a project's Expenses tab, "Log expense" was opened. Vendor type: Supplier. A real,
   existing supplier was picked from the Supplier dropdown (the actual payee).
3. In the Items section, "From Basic Rate" was used, and the no-supplier item from step 1 was
   selected and added as a line item (via whichever mechanism currently exists for reaching
   unlinked items in that picker).
4. The expense was saved.
5. Afterward, the same supplier picked in step 2 was opened at `/suppliers/[id]`.
6. Something the user expected to see there did not appear — described as "cannot happen,"
   "very wrong." It is not yet confirmed which of the two things below is actually missing.

## Relevant current architecture (for context, not a proposal)

- `Expense.supplierId` / `Expense.subContractorId` — set once, at save time, from whichever real
  vendor was picked in the form's Supplier/Sub-Contractor dropdown. This is intended to be fully
  independent of which catalog item(s) were used to build the expense's line items.
- `BasicPriceItem.supplierId` / `BaseItem.supplierId` — a separate, independent fact: which
  supplier (if any) that specific catalog item/rate entry is tagged as being supplied by. Using
  an item as a line item on an expense does not read or write this field.
- The Supplier detail page (`src/app/suppliers/[id]/page.tsx`, backed by
  `GET /api/suppliers/[id]`) has two separate sections:
  - **"Payment history"** — every expense where `Expense.supplierId` equals this supplier's id,
    regardless of what catalog items (if any) were used on those expenses' line items.
  - **"Supplies"** — every Basic Price/Basic Rate item where `supplierId` equals this supplier's
    id, i.e. items structurally tagged as being supplied by them — unrelated to which expenses
    have been logged.
- `src/app/api/projects/[id]/expenses/route.ts`'s `POST` handler was inspected and appears to
  set `supplierId`/`subContractorId` strictly from the request body's chosen vendor (`e.supplierId`
  / `e.subContractorId`), independent of `lineItems` content — no code path was found there that
  derives the expense's vendor from a line item's own supplier link.

## What needs to be determined

It has not yet been confirmed which of the following the user actually observed after step 6:

- **(A)** The expense itself is missing from the supplier's **"Payment history"** section — i.e.
  an expense that was saved with `supplierId` = that supplier's id does not show up there. If
  true, this is a genuine bug, since the backend code inspected so far appears correct and the
  cause hasn't been located yet — needs live reproduction and tracing (check the actual saved
  `expenses` row's `supplierId` value against what was picked in the form; check the
  `GET /api/suppliers/[id]` query and the page's rendering of `expenses`).

- **(B)** The no-supplier catalog item itself is missing from the supplier's **"Supplies"**
  section. This is expected, current, by-design behavior, not a bug — that section only lists
  items whose own `supplierId` matches, and using an item on an expense never sets or changes
  that item's `supplierId`. If this is what was observed, the current behavior is correct and
  does not need a code change — it would instead be a product decision (not yet made) about
  whether using an unlinked item in a paid expense should also prompt linking that item to the
  paying supplier, which is a different feature from anything implemented so far.

## Task

Reproduce the exact steps above against the running app and determine which of (A) or (B)
occurred (or something else not covered here). If (A): trace why the expense isn't appearing
under that supplier's Payment history despite the backend appearing to set `supplierId`
correctly, and report findings before making any fix. If (B): report that this is expected
current behavior per the architecture above, and ask before changing anything, since it would
be new scope, not a bug fix.
