# Vega Manager — UI/UX Audit

**Date:** 2026-08-22
**Method:** Full-text design read of every routed page + the shared component layer. No runtime/usability testing performed — this is a static read of the code, not a substitute for watching a real estimator or admin use the app.
**Scope:** 16 routes, the shared component layer (`src/components/`), and the project-detail view (`src/app/projects/[id]/client.tsx`, 4,233 lines).
**Stack observed:** Next.js 15 + Tailwind + Framer Motion + SWR, dark-mode-first.

## Summary

The design system is more deliberate than most codebases this size — a real four-color accent system, a working accessibility floor, reduced-motion handling, tabular numerals on money. See [What's Working](#whats-working) — it's worth defending, not just noting.

Where it frays is scale: 16 pages and one 4,233-line mega-view built up over several feature passes have drifted from that system and from each other. **14 items below (Priority Redlines) read as bugs or risks, not taste — fix those first**, independent of any broader consistency cleanup.

---

## Priority Redlines

The line between "inconsistent" and "actually wrong."

### 1. Login screen ships pre-filled with a real-looking staff email
`login/page.tsx:11`
The email field initializes to `'nimal@vegahomes.lk'` on every load — anyone who opens the login page sees a specific person's address suggested before they've typed anything.
**Fix:** initialize to an empty string; this looks like a debug convenience that reached production.

### 2. Users and Roles pages aren't wrapped in the app's own permission gate
`users/page.tsx` · `roles/page.tsx`
Every other admin route (Projects, Suppliers, both detail pages) renders behind `<RequirePermission>`. Users and Roles rely only on a cosmetic "Admin" badge next to the page title — worth confirming urgently whether a server-side guard actually backs these two routes.
**Fix:** wrap both in `RequirePermission` to match the pattern every other admin page already follows.

### 3. Editing a role's permissions has no confirmation step
`roles/page.tsx:66-87`
A role edit can silently change what every user holding that role can do. Deleting a supplier, a user, or a project all pass through `useConfirm()` first — this, the most far-reaching mutation in the app, does not.
**Fix:** add a confirm step naming the affected user count, same as the delete flow already does two lines below it.

### 4. An invalid rate edit reports success instead of failing
`basic-rate/page.tsx:156`
`rate: Number(eRate) || editing.rate` — clear the field or type something non-numeric and the code silently keeps the old rate, then still shows "Item updated — timestamped & logged." The user believes a change was recorded that never happened.
**Fix:** reject the save and show an inline error when the parsed rate isn't a positive number.

### 5. "Log expense" always defaults to the same fixed date
`client.tsx:2591`
`useState('2026-07-15')` — every new expense opens pre-filled with a hardcoded date rather than today's, on a form used daily by whoever logs project costs.
**Fix:** default to `new Date().toISOString().slice(0,10)`.

### 6. The header's notification bell shows fixed, fabricated data
`Header.tsx:180-189`
The three notifications ("Payment overdue," "Price updated," "Export ready") and the unread badge count are a hardcoded array, not live data — every user sees the same three items regardless of what's actually happened on their projects, and the count never changes.
**Fix:** wire to a real notifications endpoint, or remove the bell until one exists — a permanently-stale "3" erodes trust in every other number on the page.

### 7. Payments — the one portfolio list most likely to grow long — has no pagination
`payments/page.tsx:308, 455`
Basic Price, Basic Rate, and Activities all paginate via the shared component; Payments renders its full vendor list unbounded.
**Fix:** apply the same `Pagination`/`PAGE_SIZE` already used three other places in this exact page family.

### 8. Activities is the only catalog page with no search, skeleton, or empty state
`activities/page.tsx`
A "global lookup catalog" page that can exceed one page of results ships with none of the loading/empty/search affordances its three sibling pages (Basic Price, Basic Rate, Payments) all have.
**Fix:** bring in `SkeletonTableRows`, a search input, and a real empty-state row — the pattern already exists three files away.

### 9. Expandable payment rows aren't operable by keyboard
`payments/page.tsx:320-325, 459-464`
These rows carry `role="button" aria-expanded` — which promises keyboard support — but have no `onKeyDown` and no `tabIndex`. Every comparable expandable row elsewhere in the app (Stages, BSR, Expenses tabs) correctly handles Enter/Space.
**Fix:** add the same keyboard handler already used on the equivalent rows in `client.tsx`.

### 10. Promoting to Basic Rate has two implementations, and only one warns about duplicates
`client.tsx`: `PromoteModal` vs. `PromoteActions` (~3635, ~3991)
Promoting from the Basic Price tab checks for a duplicate name and warns; promoting the same kind of item from the Basic Rate tab's own picker does not. Same action, two code paths, two different safety guarantees.
**Fix:** collapse to one promote flow, or port the duplicate-name check into the second path.

### 11. Money columns are left-aligned almost everywhere, against the app's own numeric convention
Basic Price, Basic Rate, Payments, `client.tsx` (BSR & Expenses tabs)
Tabular figures (`.tnum`) are applied consistently, but the columns themselves are left-aligned in most tables — only the newer Stage Costs / Unlinked-items tables right-align. Numbers that don't share a decimal point are measurably harder to scan and compare down a column.
**Fix:** right-align every Qty/Rate/Amount/Paid/Outstanding column; the newer tables already show the target pattern.

### 12. A fifth color has entered a deliberately four-color accent system
`client.tsx:1681-1686` · `field-options/page.tsx:14`
The app's accent vocabulary is teal / indigo / amber / rose, applied consistently almost everywhere. A native `<select>` for cheque status introduces blue, and the field-options color picker separately lists `cheque`/`error`/`info` as standalone options never reconciled with that system.
**Fix:** fold "cheque" into indigo (already the neutral/informational accent) and prune the field-options color list to the four accents plus neutral.

### 13. Search exists on two admin lists and is silently missing from three others
`users/page.tsx` · `roles/page.tsx` · `suppliers/page.tsx`
Projects and Project Access both have search + result counts. Users, Roles, and Suppliers — lists just as likely to grow — have none. This is the clearest sign these screens were each shipped in a separate pass without a shared "list page" contract.
**Fix:** define one list-page header (search + count + primary action) and apply it to all five.

### 14. Login errors and "Remember me" aren't wired up
`login/page.tsx:88, 91`
A failed login renders in a plain `<p>` with no `role="alert"`, so screen-reader users aren't told it happened. Separately, "Remember me" is an uncontrolled, always-checked box never sent in the login request — a control that does nothing.
**Fix:** add `role="alert"` to the error message; either wire "Remember me" into the request or remove it.

---

## The Shared Layer

The component library, accent system, and motion/accessibility baseline are more deliberate than most codebases this size. This is where that discipline frays as new screens got added on their own timeline.

### Component reuse
- **[High]** The page-level "Add new" button is hand-copied nine times rather than pulled from a shared primitive — Basic Price, Basic Rate, Activities, Projects, Users, Roles, Suppliers, and both Field Options sections each carry their own long, identical Tailwind class string. `BtnPrimary` already exists and is used correctly inside every modal footer, just never at page scope.
- **[High]** The "preset value, or type your own" editable-select pattern (category/trade/unit/supplier pickers) is reimplemented roughly eight times inside `basic-price/page.tsx` alone — by far the largest driver of that file's length, and a direct risk that the add-form and edit-form copies quietly diverge.
- **[Med]** Two permission-matrix implementations exist side by side: `users/page.tsx` extracts a reusable component with "implied by role" support; `roles/page.tsx` rebuilds the same table inline instead of reusing it.
- **[Med]** The Export button (icon + label + hover-teal border) is copy-pasted verbatim three times across the BSR, Expenses, and Stages tabs in `client.tsx` instead of one shared component.
- **[Low]** Segmented pill-toggle controls appear at least four times (component-type, view-mode, item-mode, filter pills) with slightly different padding each time — a natural candidate for one `SegmentedControl`.

### One pattern, several dialects
- **[Med]** "Active filter" has three different visual languages across three adjacent pages: a segmented pill group (Basic Rate), a toggle chip (Basic Price), and underlined tabs (Payments) — no shared grammar for "this is the current view."
- **[Med]** Delete confirmation splits into two mechanisms: a dedicated Modal + `BtnDanger` on Activities, versus the generic `useConfirm()` dialog on Basic Price and Basic Rate — same action class, two different interaction patterns to learn.
- **[Med]** Delete affordance also splits by page tier: icon-only on every list page (Projects, Users, Roles) versus a labeled, rose-bordered button on both detail pages (Suppliers, Sub-contractors). Internally consistent per tier, mismatched across them.
- **[Low]** Only Payments gets a KPI summary strip; Basic Price, Basic Rate, and Activities are equally portfolio-wide views but show no rollup metrics at all.

### Forms & feedback
- **[Med]** No form in the app marks required fields upfront — validation is toast-only at submit time everywhere, so a 6-field modal gives no clue which field the toast is actually about.
- **[Med]** Double-submit guards are inconsistent: the "new category" mini-modal and `PaymentsModal` correctly disable + spin during save; the Basic Price, Basic Rate, and Activities primary submit buttons do not, though the pattern to copy sits in the same codebase.
- **[Low]** Inline stage/milestone number edits in `client.tsx` silently revert on an invalid commit with no visible message — the one form-error path in the file that breaks from its own error-banner convention.

---

## Estimating & Finance

Basic Price, Basic Rate, Payments, and Activities — the screens estimators and accountants likely open every day. Dense, data-heavy, and the four most divergent siblings in the app.

**Tables**
- **[Med]** No table in this group has a sticky header — an 11-column Basic Rate table scrolls its own labels out of view on a normal-length list.
- **[Low]** No column supports click-to-sort anywhere; Payments instead offers a separate sort dropdown that isn't mirrored on its three siblings.
- **[Low]** Row hover state is consistent on top-level tables but absent on Payments' nested drill-down sub-tables.

**Search & filter**
- **[Med]** No page offers a single "clear all filters" action even where category, stale, no-supplier, and text-query filters can combine to zero results on Basic Rate.
- **[Low]** A visible result count ("N of M") appears only on Basic Rate — Basic Price and Payments give no count outside the pagination footer.
- **[Good]** Filter state correctly persists across pagination and resets to page 1 on any filter change — small detail, done right everywhere it was checked.

**Empty & loading states**
- **[Med]** Payments has the richest empty state of the four (icon, message, inline "Clear search") — a pattern worth backporting to Basic Price and Basic Rate, whose search-empty states offer no way out.
- **[Good]** Basic Price and Basic Rate both correctly distinguish "nothing here yet" from "nothing matches your filters" — an easy distinction to skip and this app doesn't.

**Notable strength**
- **[Good]** Basic Rate's stale-price affordance — amber tint, before/after diff with a trend arrow, one-click "Update rate" with a confirm-and-preview step — is the strongest single interaction pattern found in this audit. It's worth generalizing rather than leaving it a one-off.

---

## Admin, RBAC & Settings

Projects, Users, Roles, Suppliers, Sub-contractors, Settings, Login — the screens office staff and admins use, where the cost of an unclear control is a wrong permission grant or an accidental deletion.

**Destructive-action safety**
- **[Med]** Projects sets the standard the rest of the app should match: its delete confirm explicitly lists every cascading effect (activity items, BSR lines, stages, expenses). Suppliers and Sub-contractors follow suit, explaining the server's "rejected if still linked" behavior in plain language.
- **[Med]** User delete and role delete both use generic "This can't be undone" copy, with no mention of owned projects, logged expenses, or (for roles) the user count already visible one column over — the two most consequential deletes in the app currently have the weakest confirmation copy.
- **[Good]** A dedicated "Remove all access" danger-confirm fires specifically when a save would leave a user with zero roles or permissions — a thoughtful guardrail that isn't obviously required by the data model, someone chose to add it.

**Visual hierarchy**
- **[Low]** Row actions on the Users list (View / Deactivate / Edit / Delete) carry near-identical visual weight; deactivating or deleting an account reads no more consequential than viewing it until the pointer is already on top of it.
- **[Low]** Status is legible at a glance almost everywhere checked — colored dot paired with a text label, never color alone.

**Information architecture**
- **[Low]** Suppliers uses tabs, Field Options uses stacked sections, and Users/Roles are separate top-level routes — three different answers to "how do I group a related set of entities," each apparently chosen per-feature rather than from one convention.
- **[Low]** The Settings landing page promotes Field Options and Project Access to their own nav cards, while Currency and the audit-log blurb sit inline on the same page with no equivalent visual treatment for what is, structurally, the same kind of link.

---

## Project Detail — the 4,233-Line View

One file (`projects/[id]/client.tsx`) carries six tabs — BSR, Stages & Payments, Expenses, Stage Costs, Basic Price, Basic Rate — and has absorbed most of this year's feature work. The audit found it in better shape internally than its size suggests, but size itself is now the risk.

**Navigation & overlap**
- **[Med]** The Expenses and Stage Costs tabs source the same underlying data and look similar at a glance; the distinction between "chronological ledger" and "ranked by cost" exists only in a code comment, not in any on-screen hint for a first-time user.
- **[Low]** The main tab bar is hand-rolled rather than a shared Tabs primitive — reasonable if none exists yet, but it's the single most-used navigation element in the file and currently has no shared implementation to inherit future fixes from.

**Tables at scale**
- **[Med]** BSR, Stages, Expenses, and Stage Costs tables have no pagination — only Basic Price and Basic Rate (inside this same file) use the shared component. A project with hundreds of BSR lines renders all of them at once.
- **[Low]** Most tables force horizontal scroll via `whitespace-nowrap` even on an 11-column Expenses table — a reasonable trade-off for this much data, but the scroll container gives no edge hint that more columns exist off-screen.

**Structural note**
- **[Low]** Three separate "grand total" pill treatments (BSR, recipe builder, expense line-items) are near-identical but independently coded — a small tell that at this file size, even good instincts (see `SelectedHeader` and `FloorQtyPanel`, both correctly extracted and reused) can't always keep up with where a pattern has already been solved once.

---

## What's Working

An audit that only lists problems is a bad audit. This system got a lot right on the first pass, and the fixes above should extend these patterns outward, not replace them.

- **A genuine four-color accent system** — teal, indigo, amber, rose — mapped consistently to positive/neutral/warning/negative meaning across KPI cards, badges, and glow accents, not just a palette of colors used interchangeably.
- **The accessibility floor is real, not decorative**: `focus-visible` outlines, `aria-label` on essentially every icon-only button, Enter/Space handling on clickable rows, and a `color-scheme` hook so native form controls don't break in dark mode — this is well above the baseline most apps this size ship with.
- **Motion respects the user** — every animation routes through `MotionConfig reducedMotion="user"` and a `prefers-reduced-motion` media query, down to a documented exception for the one toast progress bar whose animation is functional, not decorative.
- **Toast + confirm + inline-error conventions are applied consistently** almost everywhere a mutation happens, with domain-specific copy rather than generic "Success" / "Are you sure?"
- **Cascading-effect delete copy on Projects and Suppliers** explains exactly what else will be affected before the user commits — the right way to write a destructive confirmation, and worth propagating to Users and Roles per Redline 3 and 13.
- **Tabular numerals and right-aligned money are the evident intent throughout** — the newer Stage Costs and Unlinked-items tables show the target pattern cleanly; the older tables just haven't been brought up to it yet (Redline 11).

---

## Recommended Sequence

Ordered by what happens if it's skipped, not by effort.

1. **Close the redlines.** All fourteen items above first — several are correctness or security-adjacent, not styling, and every day they sit is a day someone can hit them.
2. **Extract the repeated primitives.** A page-level `BtnPrimary`, one `EditableSelect`, one `SegmentedControl`, one list-page header (search + count + CTA). This is the highest-leverage cleanup: it collapses the nine-times-copied "Add new" button and the eight-times-copied preset/custom picker into single sources of truth.
3. **Unify the table & delete conventions.** Right-align every numeric column, paginate BSR/Stages/Expenses/Stage Costs/Payments, and settle on one delete-confirmation pattern (Modal+BtnDanger or `useConfirm()`, not both) with cascading-effect copy as the standard, not the exception.
4. **Split the mega-view.** `projects/[id]/client.tsx` is well-organized internally for its size, but 4,233 lines in one file is now the biggest risk to keeping it that way. Break it along its existing tab boundaries before the next feature adds to it.
5. **Validate with real users.** This audit is a static read of the code, not a usability test. The stale-rate affordance, the promote flow, and the RBAC matrix in particular are worth watching an actual estimator and admin use before calling them finished.
