# Rate Change Flag — Proposed Design

Companion to `GAP_ANALYSIS.md` gap #11 (rate changes don't propagate downstream, no warning/fix).
This document explains the proposed "flag" behaviour in plain terms, with examples, for client sign-off.

---

## 1. Basic Rate change → flag every BSR recipe that used it

Say you built 3 different BSR items in 3 different projects, and all 3 of them used Cement as
one ingredient — each locked in Cement's price at 1,250 when they were built.

Now you go to Basic Rate and change Cement's price from 1,250 to 1,500.

**The rule:** all 3 of those BSR items should get flagged — not just one. Because all 3 used
that same Cement rate, and all 3 are now out of date.

So it's not "one ingredient → one flag." It's "one ingredient → flag everywhere it was used."
If Cement is used in 10 different recipes across 5 different projects, changing Cement's rate
flags all 10.

Each flagged item still follows the same on/off rule below:

- One flag per item (not stacking, even if Cement's price changes again before you fix it —
  just compares to the newest price).
- Click "update to current rate" on that item → it updates, flag clears for that one.
- The other 9 flagged items stay flagged until you go fix each one too — updating one doesn't
  fix the rest automatically (since each recipe is its own separate copy).

---

## 2. One flag, not a pile of flags

Only show 1 flag, not many flags.

Example: Basic Price changes 3 times — 100 → 110 → 120. Don't show 3 separate warnings. Just
show 1 warning that says "this is outdated," and compare against the newest number (120).

Once the user updates Basic Rate to 120, the flag goes away.

If the price changes again later, a new single flag appears again.

So it's just: flag ON or flag OFF — never a list, never stacking up. Simple on/off switch, not
a history.

---

## 3. Duplicate ingredients don't cross-flag each other

The other one was about duplicate ingredients — when there's more than one Basic Price entry
for what is really the same material.

Simple example: someone adds "Cement" as a draft and promotes it to Basic Rate as code M-050.
Later, someone else (not knowing M-050 already exists) adds "Cement" again as a brand new
separate draft, and promotes that one too — now you get a second code, say M-095, also called
"Cement."

These two are not connected to each other — they're two completely separate records that just
happen to share a name by accident.

So the rule is: if you edit the first "Cement" (the one that became M-050), only M-050 gets the
flag — M-095 does NOT get flagged, even though it's also called "Cement." They're treated as two
different items, not one.

**Side issue worth flagging to the client:** maybe the app should warn you when you're about to
create a duplicate (e.g. "a similar item called Cement already exists") — to stop this confusing
double-entry situation from happening in the first place.

---

## Status

Proposed — pending client sign-off. See `GAP_ANALYSIS.md` gap #11 for the overall context this
design responds to.
