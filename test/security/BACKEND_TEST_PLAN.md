# Backend Test Plan — Pre-Handover Verification

**Date:** 2026-08-30
**Purpose:** The areas to test and verify on the backend before handing the system over.

---

## 1. API contract testing

Every endpoint, tested directly (Postman/curl/automated suite) — not through the UI:

- **Happy path** — correct input returns correct status code, correct response shape.
- **Status codes are honest** — 200 vs 201 vs 204, 400 vs 401 vs 403 vs 404 vs 409 vs 422. A route returning 200 with an error body inside is a common and painful bug to inherit.
- **Response shape stability** — field names, types, nullability, date formats. The frontend is coupled to these.

## 2. Authentication & authorization

This is the area most worth over-testing, because failures here are silent:

- Call every endpoint **with no token** → must reject.
- Call every endpoint **with an expired/tampered token** → must reject.
- Call every endpoint **as a low-privilege user** → must reject where appropriate. Do this at the API level, not by checking whether the button is hidden.
- **Object-level access (IDOR)** — log in as User A, then request User B's record by ID. This is the single most commonly missed test and the most commonly exploited flaw.
- **Privilege escalation** — can a normal user edit their own role, or assign themselves permissions via a PATCH?

## 3. Input validation & boundary testing

For each endpoint that accepts a payload:

- Missing required fields, `null`, empty string, wrong type (string where number expected).
- Oversized input (very long strings, huge arrays) — does it error gracefully or blow up?
- Negative numbers and zero where only positives make sense (quantities, amounts, prices).
- Unicode, emoji, special characters, leading/trailing whitespace.
- Injection payloads — SQL (`' OR 1=1--`), and script tags to confirm they're stored/escaped safely, not executed.
- **Extra/unexpected fields** — does the API silently accept and persist fields it shouldn't (mass assignment)?

## 4. Business logic & calculations

The category clients notice first:

- Recompute every financial/derived figure by hand (or in a spreadsheet) for one real dataset and diff against what the API returns — totals, subtotals, rollups, percentages, ROI, outstanding balances.
- **Rounding behavior** — verify it's consistent and defined. Cent/rupee drift on summed columns is a classic.
- **Currency and decimal precision** — especially if amounts are stored as floats rather than integers/decimals.
- Edge cases the formula wasn't written for: zero values, division by zero, empty collections, negative adjustments.

## 5. Data integrity

- **Cascade/orphan behavior** — delete a parent record, then query every child table for rows left behind. Do this for every entity with children.
- **Referential integrity** — can you create a child pointing at a non-existent parent?
- **Unique constraints** — try creating duplicates (same email, same code, same name where uniqueness is expected).
- **Transaction atomicity** — if a multi-step write fails halfway, does everything roll back, or are you left with half-written state?
- **Soft vs hard delete** — confirm deleted records actually stop appearing in every query that should exclude them.

## 6. Concurrency & race conditions

- Two simultaneous updates to the same record — last-write-wins, or lost update?
- Double-submit — fire the same create request twice rapidly; do you get two records?
- Concurrent operations on shared counters/sequences (invoice numbers, codes) — do they collide?

## 7. Database & migrations

- **Migrations replay from zero** on a clean database, in order, without error. This catches "works on my machine because my DB already has that column."
- **Rollback path** — can you go back a version if a deploy goes wrong?
- **Seed script** runs cleanly against a fresh DB.
- **Indexes exist** on columns you filter/join on — check query plans for the heaviest endpoints.

## 8. Performance under realistic data

- Load the DB with production-scale row counts (not 10 test rows) and re-run the heaviest endpoints — list views, dashboards, reports.
- **N+1 query detection** — one request firing hundreds of queries is the most common backend performance bug.
- Response times on the slowest endpoints; set an acceptable threshold and confirm you're under it.
- Pagination actually limits what's fetched from the DB, not just what's displayed.

## 9. Error handling & resilience

- **Error responses don't leak internals** — no stack traces, SQL fragments, file paths, or library versions in responses.
- Unhandled exceptions return a clean 500, not a crash.
- External dependency failures (DB unreachable, third-party API down) degrade gracefully.
- Malformed JSON body → 400, not 500.

## 10. Configuration & deployment

- App starts cleanly in a **fresh environment** with only documented env vars set — and fails loudly with a clear message if one is missing.
- No secrets, credentials, or connection strings committed to the repo (scan git history, not just the working tree).
- Verify the production build actually runs, not just the dev server.
- Logging works in the deployed environment and doesn't log sensitive data (passwords, tokens, full payloads with PII).

## 11. Regression & handover readiness

- Run the full suite of critical user journeys end to end one final time on the **production build against production-like data**.
- Document every known limitation and unfixed bug and hand that list over with the system — clients discovering these themselves post-handover costs far more trust than disclosing them upfront.
- Confirm someone other than you can set the project up from the README alone. If they can't, the handover isn't done.

---

## Highest-leverage subset

If time is short, these four catch the bugs that are both most likely present and most expensive to find later:

1. **Authorization / IDOR testing** — silent failures, highest security impact.
2. **Financial calculation verification** — what the client notices first.
3. **Cascade-delete integrity** — invisible in the UI, corrupts data over time.
4. **Clean migration replay from zero** — catches environment-drift bugs before the client hits them.

---

## Related

- [UNAUTHORIZED_ACCESS_DEFENSE.md](./UNAUTHORIZED_ACCESS_DEFENSE.md) — unauthorized-access defense checklist and current-state comparison for this codebase.
