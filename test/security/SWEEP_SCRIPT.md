# Per-handler auth guard sweep

Companion to `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md` task 0.3.

## Why per-handler, not per-file

The 2026-08-30 review checked guards at **file** granularity and concluded all 61 API route
files were guarded. That is true, but a `route.ts` exporting both `GET` and `POST` passes a
file-level grep if only `POST` calls `requireAdmin()`. `src/app/api/users/route.ts` is exactly
that case — `GET` returns the full user directory with no in-handler guard.

This script splits each file at its exported HTTP handlers and checks each handler body
independently.

## The script

Save as `scripts/audit-guards.js` in `vega-manager/`, run with `node scripts/audit-guards.js`
from that directory.

```js
const fs = require('fs')
const path = require('path')

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(p, out)
    else if (entry.name === 'route.ts') out.push(p)
  }
  return out
}

// Handlers that are legitimately public — anything else reported is a finding.
const ALLOWED_PUBLIC = [
  ['POST', 'api/auth/login'],
  ['POST', 'api/auth/logout'],
]

const HANDLER_RE = /export async function (GET|POST|PATCH|PUT|DELETE)\b/g
const GUARD_RE = /require(Session|Admin|Permission)|getSession/

const files = walk('src/app/api').sort()
const findings = []

for (const file of files) {
  const src = fs.readFileSync(file, 'utf8')
  const matches = [...src.matchAll(HANDLER_RE)]
  matches.forEach((m, i) => {
    const end = i + 1 < matches.length ? matches[i + 1].index : src.length
    const body = src.slice(m.index, end)
    if (GUARD_RE.test(body)) return
    const method = m[1]
    const norm = file.replace(/\\/g, '/')
    const allowed = ALLOWED_PUBLIC.some(([mm, pp]) => mm === method && norm.includes(pp))
    if (!allowed) findings.push(`${method.padEnd(6)} ${norm}`)
  })
}

console.log(`Scanned ${files.length} route files.`)
if (findings.length === 0) {
  console.log('OK — no unguarded handlers.')
} else {
  console.log(`\n${findings.length} unguarded handler(s):`)
  findings.forEach(f => console.log('  ' + f))
  process.exit(1)
}
```

## Baseline as of 2026-08-31

Six handlers had no in-handler guard:

| Method | Route | Assessment |
|---|---|---|
| POST | `api/auth/login` | Correctly public |
| POST | `api/auth/logout` | Correctly public |
| GET | `api/users` | **Finding** — full user directory, middleware-only protection |
| GET | `api/categories` | Low — lookup list, still behind middleware session check |
| GET | `api/trades` | Low — as above |
| GET | `api/units` | Low — as above |

After tasks 0.1 and 0.2 the script should exit 0.

## Wire into CI

The script exits non-zero on any finding, so it drops straight into the same workflow as the
`npm audit` gate from task 0.7. That is what stops this class of gap from reappearing — the
`GET /api/users` case was introduced by adding a second handler to a file that already looked
guarded, which no reviewer reliably catches by eye.
