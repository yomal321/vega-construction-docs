# Frontend Test Plan — Pre-Handover Verification

**Date:** 2026-08-30
**Purpose:** The areas to test and verify on the frontend before handing the system over.

---

## 1. Core functional flows

Every screen, walked end to end — not just "does the page load":

- **Full CRUD per entity** — create → view in list → search/filter → edit → delete. Confirm the list actually refreshes after each mutation rather than showing stale data.
- **Navigation** — every link, breadcrumb, tab, and sidebar item lands where it should. No dead links, no 404s.
- **Deep linking / direct URL access** — paste a detail-page URL straight into the address bar. Does it load, or does it assume you arrived from the list page?
- **Browser back/forward and refresh** — does app state survive, or does the user lose their work?
- **Multi-step flows** — wizards, modals with several stages: cancel midway, go back a step, resubmit.

## 2. Forms & validation

The highest-defect-density area in most apps:

- **Required fields** are marked upfront, not just enforced at submit time.
- **Client-side validation matches server-side rules** — a form that lets you submit what the API will reject is a bad experience; one that blocks what the API would accept is a bug.
- **Field-level errors point at the offending field**, not just a generic toast that leaves the user hunting.
- **Boundary input** — empty, whitespace-only, very long strings, special characters, emoji, negative numbers, zero, decimals where integers are expected.
- **Double-submit protection** — rapid-clicking Save must not create two records. Buttons should disable during submission.
- **Unsaved-changes warning** — navigating away mid-edit should warn, or the data loss should be a deliberate accepted decision.
- **Date/number formats** — entered, displayed, and stored consistently; check timezone handling if dates matter.

## 3. State & data handling

- **Loading states** — every async action shows a spinner/skeleton; no blank screens or frozen UI.
- **Empty states** — a list with no data shows a helpful message, not an empty box. Distinguish "nothing here yet" from "nothing matches your filters," and give a way out of the latter.
- **Error states** — a failed API call shows a real message with a retry path, not a silent failure or an infinite spinner.
- **Stale data after mutation** — after create/edit/delete, does every affected view update? Cached lists showing deleted records is a classic.
- **Filter/sort/pagination interaction** — do filters persist across pages? Does changing a filter reset to page 1? Does the count reflect the filter?

## 4. Authorization in the UI

- **Log in as each role** and walk the whole app — confirm hidden/disabled controls match what the API actually allows.
- **A hidden button is not security** — verify the corresponding API call is also blocked server-side (cross-reference the backend plan).
- **Direct URL access to a restricted page** as a low-privilege user → must redirect or show a proper access-denied screen, not a broken page.
- **Session expiry mid-session** — what happens when the token expires while the user is on a page? A clean redirect to login, or a wall of failed requests?
- **Logout** clears state fully — hitting back after logout must not show cached data.

## 5. Data display correctness

- **Numbers, currency, and dates format consistently** across every screen — same decimal places, same currency symbol, same date order.
- **Totals and derived figures match the backend** — spot-check a few against hand-calculated values.
- **Long content doesn't break layout** — long names, large numbers, many table columns. Test with realistic worst-case data, not "Test 1."
- **Tables with realistic row counts** (hundreds, not ten) — does the page still render responsively? Is pagination or virtualization actually needed?
- **Null/missing values** display as "—" or similar, never as `null`, `undefined`, or `NaN`.

## 6. Cross-browser & responsive

- **Browsers** — Chrome, Edge, Firefox, Safari at minimum; prioritize whichever the client's staff actually use.
- **Screen sizes** — desktop, laptop, tablet, and the narrowest width anyone will realistically use. Data-dense tables are the usual casualty.
- **Zoom levels** — 100%, 125%, 150%. Many office users run scaled displays.
- **Print / export views** if the app produces reports — check the actual generated PDF/Excel file opens and is correct, not just that the download fired.

## 7. Accessibility

- **Keyboard-only navigation** — tab through every screen; every interactive element must be reachable and operable via Enter/Space. Expandable rows and custom controls are the usual gaps.
- **Focus is visible** at all times and doesn't get trapped in modals (or lost when they close).
- **Screen reader basics** — icon-only buttons have `aria-label`; error messages announce via `role="alert"`; form inputs have associated labels.
- **Color is never the only signal** — status shown by color alone fails for colorblind users; pair with text or an icon.
- **Contrast ratios** meet WCAG AA, especially for muted/secondary text.
- **Reduced motion** preference respected if the app animates.

## 8. Performance & resilience

- **Initial load time** on a realistic connection, and bundle size sanity-check.
- **Slow network behavior** — throttle to 3G in devtools: do loading states hold up, or does the UI flash/jump?
- **Offline / API-down behavior** — a clear error, not a white screen.
- **Memory leaks on long sessions** — navigate around for a while and watch memory; unclosed subscriptions/intervals are the usual cause.
- **No console errors or warnings** in production build — a noisy console makes real errors invisible to whoever maintains this next.

## 9. Security-adjacent frontend checks

- **No secrets in the client bundle** — API keys, credentials, internal URLs. Search the built output, not just the source.
- **XSS** — enter `<script>alert(1)</script>` into text fields and confirm it renders as text, not code, everywhere it's later displayed.
- **No sensitive data in `localStorage`/`sessionStorage`** — tokens belong in httpOnly cookies.
- **No sensitive data logged to console** in production.
- **Source maps** — decide deliberately whether they ship to production.

## 10. Consistency & polish

- **One pattern per interaction** — delete confirmations, filters, empty states, and buttons should look and behave the same way across screens. Divergence here is the clearest sign of features built in separate passes.
- **Copy is correct and professional** — no placeholder text, no lorem ipsum, no debug labels, no developer-facing error messages reaching users.
- **No hardcoded/fabricated data** reaching production — pre-filled emails, fixed dates, dummy notification counts. These are the things a client spots in the first ten minutes.
- **Branding and terminology match the client's vocabulary**, not the developer's.

## 11. Regression & handover readiness

- Run every critical user journey one final time on the **production build**, against production-like data — not the dev server.
- Verify against the original requirements/BRD, feature by feature, so nothing agreed was quietly dropped.
- Document known limitations and unfixed issues and hand that list over with the system.
- Confirm someone else can build and run the frontend from the README alone.

---

## Highest-leverage subset

If time is short, these four catch the most-likely and most-visible problems:

1. **Role-by-role walkthrough** — confirms authorization and catches broken screens in one pass.
2. **Forms with boundary/invalid input** — highest defect density in any frontend.
3. **Realistic data volume** — exposes layout breakage and missing pagination that test data never will.
4. **Hardcoded/placeholder data sweep** — cheapest fix, most damaging to first impressions if missed.

---

## Related

- [BACKEND_TEST_PLAN.md](./BACKEND_TEST_PLAN.md) — backend pre-handover verification areas.
- [UNAUTHORIZED_ACCESS_DEFENSE.md](./UNAUTHORIZED_ACCESS_DEFENSE.md) — unauthorized-access defense checklist and current-state comparison.
