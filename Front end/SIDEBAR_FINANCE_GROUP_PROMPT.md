# Fix: split "Estimating" sidebar group — add a "Finance" group

## Problem

`src/components/Sidebar.tsx`'s `navItems` array (lines 18-47) currently groups "Payments" and
"Suppliers & sub-contractors" under the **Estimating** section, alongside Basic price, Basic
rate, and Activities. Estimating should mean "building up a rate/price" — Payments and
Suppliers/Sub-Contractors are about tracking money owed and who it's owed to, a different
concern entirely, and lumping them together blurs what each section means.

## Solution

Add a new `{ section: 'Finance' }` group between Estimating and Projects, and move `Payments`
and `Suppliers & sub-contractors` into it. Estimating keeps only Basic price, Basic rate, and
Activities.

In `src/components/Sidebar.tsx`, change the `navItems` array (currently lines 18-47) from:

```ts
const navItems: NavEntry[] = [
  { section: 'Overview' },
  { href: '/', icon: LayoutGrid, label: 'Dashboard', module: 'dashboard' },
  { section: 'Estimating' },
  { href: '/basic-price', icon: FilePlus2, label: 'Basic price', module: 'projects' },
  { href: '/basic-rate', icon: Receipt, label: 'Basic rate', module: 'projects' },
  { href: '/payments', icon: HandCoins, label: 'Payments', module: 'projects' },
  { href: '/activities', icon: ListTree, label: 'Activities', module: 'activities' },
  { href: '/suppliers', icon: Truck, label: 'Suppliers & sub-contractors', module: 'suppliers' },
  { section: 'Projects' },
  { href: '/projects', icon: FolderKanban, label: 'Projects', module: 'projects' },
  { section: 'Administration' },
  ...
]
```

to:

```ts
const navItems: NavEntry[] = [
  { section: 'Overview' },
  { href: '/', icon: LayoutGrid, label: 'Dashboard', module: 'dashboard' },
  { section: 'Estimating' },
  { href: '/basic-price', icon: FilePlus2, label: 'Basic price', module: 'projects' },
  { href: '/basic-rate', icon: Receipt, label: 'Basic rate', module: 'projects' },
  { href: '/activities', icon: ListTree, label: 'Activities', module: 'activities' },
  { section: 'Finance' },
  { href: '/payments', icon: HandCoins, label: 'Payments', module: 'projects' },
  { href: '/suppliers', icon: Truck, label: 'Suppliers & sub-contractors', module: 'suppliers' },
  { section: 'Projects' },
  { href: '/projects', icon: FolderKanban, label: 'Projects', module: 'projects' },
  { section: 'Administration' },
  ...
]
```

Only the order/grouping changes — same `href`, `icon`, `label`, and `module` values on every
entry, so permissions-based visibility (`usePermissions`) and active-route highlighting are
unaffected. Leave the two explanatory comments currently above `Payments` and `Suppliers &
sub-contractors` in place, just moved down along with their entries — they're still accurate.

## Verification

Load the sidebar and confirm: Estimating shows exactly Basic price, Basic rate, Activities; a
new Finance section appears right after it showing Payments and Suppliers & sub-contractors;
Projects and Administration are unchanged. Confirm active-route highlighting still works
correctly when visiting `/payments` or `/suppliers` (should highlight under the new Finance
section, not error or highlight nothing).
