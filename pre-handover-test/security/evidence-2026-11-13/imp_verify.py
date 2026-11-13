"""Basic Rate import (POST /api/projects/[id]/basic-rate/import): server-side checks.

The .xlsx / .pdf file is parsed in the browser (src/lib/importCatalog.ts); the server receives
JSON rows only. So the server surface is: who may call it, whose items a row may touch, and how
it handles hostile row values. A Staff user with projects:view+create but NOT projects:edit is
created to test whether import can change existing rates without the edit permission.
Run AFTER the other scripts. Local throwaway instance only (see authz_test.py). Never prod.
Usage: python -I imp_verify.py <dir holding authz_test.py>
"""
import json, sys, os, subprocess, urllib.parse
S = sys.argv[1]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)

PG = ["docker", "exec", "vega-perf-pg", "psql", "-U", "vega", "-d", "vega_sec5", "-tAc"]
def sql(q):
    r = subprocess.run(PG + [q], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

out = []
def rec2(cid, name, m, p, s, ok, note=""):
    out.append((cid, name, m, p, s, "PASS" if ok else "FAIL", str(note)[:200]))

OWN, F = "perf_p004", "perf_p001"
IMP = lambda p: f"/api/projects/{p}/basic-rate/import"
TAG = str(int(time.time()))
ADMIN, _ = login("sanduni@vegahomes.lk")
STAFF, _ = login("perf.staff1@vegahomes.lk")      # projects:create/edit, reaches perf_p004 only
NOCREATE, _ = login("perf.staff12@vegahomes.lk")  # projects:view only, member of 4 projects
assert ADMIN and STAFF and NOCREATE
OWN_ITEM, OWN_CODE, OWN_RATE = sql(f"""select id||'|'||code||'|'||rate from base_items where "projectId"='{OWN}' order by code limit 1""").split("|")
F_ITEM, F_CODE, F_RATE = sql(f"""select id||'|'||code||'|'||rate from base_items where "projectId"='{F}' order by code limit 1""").split("|")
good = lambda **kw: {"name": f"Import check {TAG}", "cat": "material", "unit": "Bag", "rate": 100, **kw}

# ── A Access ───────────────────────────────────────────────────────────────
s, t, *_ = req("POST", IMP(OWN), None, {"rows": [good()]})
rec2("A", "no session -> 401", "POST", IMP(OWN), s, s == 401, t[:80])
s, t, *_ = req("POST", IMP(OWN), NOCREATE, {"rows": [good()]})
rec2("A", "projects:view only -> 403", "POST", IMP(OWN), s, s == 403, t[:80])
s, t, *_ = req("POST", IMP(F), STAFF, {"rows": [good()]})
rec2("A", "staff -> foreign project -> 403", "POST", IMP(F), s, s == 403, t[:80])
s, t, *_ = req("POST", IMP(OWN), STAFF, {"rows": [good(id=F_ITEM, rate=1)]})
after = sql(f"select rate from base_items where id='{F_ITEM}'")
rec2("A", "own project URL + foreign item id: row refused, foreign rate unchanged", "POST", IMP(OWN), s,
     s == 200 and '"updated":0' in t and float(after) == float(F_RATE), f"{t[:120]} rate={after}")

# ── E Edit-permission parity ───────────────────────────────────────────────
EM, PW = f"imp.create.{TAG}@vegahomes.lk", "Imp-Check-Pass-2026!"
s, t, *_ = req("POST", "/api/users", ADMIN, {"name": "Import create-only", "email": EM, "role": "Staff", "password": PW,
                                              "permissions": ["projects:view", "projects:create"]})
rec2("E", "fixture: Staff with projects:view+create, no edit", "POST", "/api/users", s, s in (200, 201), t[:80])
UID = sql(f"select id from users where email='{EM}'")
s, t, *_ = req("POST", f"/api/projects/{OWN}/members", ADMIN, {"userId": UID})
rec2("E", f"fixture: member of {OWN}", "POST", f"/api/projects/{OWN}/members", s, s in (200, 201), t[:80])
CO, _ = login(EM, PW)
s, t, *_ = req("PATCH", f"/api/projects/{OWN}/basic-rate/{OWN_CODE}", CO, {"rate": 1.23})
rec2("E", "single-item rate edit without projects:edit -> 403 (baseline)", "PATCH", f"/api/projects/{OWN}/basic-rate/{OWN_CODE}", s, s == 403, t[:80])
before = sql(f"select rate from base_items where id='{OWN_ITEM}'")
name = sql(f"select name from base_items where id='{OWN_ITEM}'")
unit = sql(f"select unit from base_items where id='{OWN_ITEM}'")
cat = sql(f"select cat from base_items where id='{OWN_ITEM}'")
s, t, *_ = req("POST", IMP(OWN), CO, {"rows": [{"id": OWN_ITEM, "name": name, "cat": cat, "unit": unit, "rate": 1.23}]})
after = sql(f"select rate from base_items where id='{OWN_ITEM}'")
changed = float(after) != float(before)
rec2("E", "import with existing item id, without projects:edit: rate must not change", "POST", IMP(OWN), s,
     not changed, f"status={s} {t[:80]} rate {before} -> {after}")
if changed:  # put it back so later runs see the original data
    req("POST", IMP(OWN), STAFF, {"rows": [{"id": OWN_ITEM, "name": name, "cat": cat, "unit": unit, "rate": float(before)}]})

# ── I Hostile row values (as perf.staff1 on its own project) ───────────────
bad = [
    ("name number", good(name=123)), ("name object", good(name={"$gt": ""})), ("name empty", good(name="   ")),
    ("name 500 chars", good(name="A" * 500)), ("name NUL", good(name="ab\u0000c")),
    ("code number", good(code=5)), ("code NUL", good(code="M-\u0000")), ("code 100 chars", good(code="M-" + "9" * 98)),
    ("code clash", good(code=OWN_CODE)), ("cat unknown", good(cat="'; drop table base_items;--")), ("cat array", good(cat=["material"])),
    ("unit unknown", good(unit="Barrel")), ("rate string", good(rate="100")), ("rate negative", good(rate=-1)), ("rate zero", good(rate=0)),
    ("rate null", good(rate=None)), ("supplier unknown", good(supplierId="nope")), ("id unknown", good(id="bi_nope")),
    ("id object", good(id={"$ne": None})),
]
n0 = int(sql(f"""select count(*) from base_items where "projectId"='{OWN}'"""))
s, t, *_ = req("POST", IMP(OWN), STAFF, {"rows": [b for _, b in bad]})
d = json.loads(t) if s == 200 else {}
errs = {e["index"] for e in d.get("errors", [])}
n1 = int(sql(f"""select count(*) from base_items where "projectId"='{OWN}'"""))
rec2("I", f"{len(bad)} hostile rows in one import: every row refused, nothing written", "POST", IMP(OWN), s,
     s == 200 and errs == set(range(len(bad))) and d.get("created") == 0 and d.get("updated") == 0 and n1 == n0,
     f"refused {len(errs)}/{len(bad)}, created={d.get('created')} updated={d.get('updated')}, rows {n0}->{n1}; not refused: {[bad[i][0] for i in range(len(bad)) if i not in errs]}")
for label, body in [("rows missing", {}), ("rows empty", {"rows": []}), ("rows not array", {"rows": "x"}),
                    ("5001 rows", {"rows": [good()] * 5001}), ("row not object", {"rows": ["x"]}),
                    ("one 200k-char description", {"rows": [good(name="A" * 200000)]})]:
    s, t, *_ = req("POST", IMP(OWN), STAFF, body)
    refused_row = s == 200 and '"created":0' in t and '"updated":0' in t
    rec2("I", f"{label} -> refused, nothing written", "POST", IMP(OWN), s, s in (400, 413) or refused_row, t[:80])
s, t, *_ = req("POST", IMP(OWN), STAFF, {"rows": [good(name=f'=HYPERLINK("http://evil.example","x") {TAG}', code=f"M-X{TAG[-4:]}")]})
stored = sql(f"""select name from base_items where "projectId"='{OWN}' and code='M-X{TAG[-4:]}'""")
rec2("I", "formula-looking description stored as plain text", "POST", IMP(OWN), s, s == 200 and stored.startswith("=HYPERLINK"), stored[:60])

# ── Cleanup ────────────────────────────────────────────────────────────────
req("DELETE", f"/api/projects/{OWN}/members/{UID}", ADMIN)
s, t, *_ = req("DELETE", f"/api/users/{urllib.parse.quote(EM)}", ADMIN)
rec2("CL", "cleanup: delete create-only user", "DELETE", "/api/users/<imp.create>", s, s in (200, 204, 409), t[:80])

for r in out:
    print(" | ".join(str(x) for x in r))
p = sum(1 for r in out if r[5] == "PASS")
print(f"\nTOTAL {len(out)}  PASS {p}  FAIL {len(out) - p}")
json.dump([dict(zip(["id", "name", "method", "path", "status", "verdict", "note"], r)) for r in out],
          open(os.path.join(S, "imp_verify_results.json"), "w", encoding="utf-8"), indent=1)
