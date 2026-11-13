"""Targeted checks for the S5 fix (origin/dev e6b4d49): Supplier Price Comparison scoped per user.

GET /api/suppliers/price-comparison now applies projectAccessClause. This script checks it against
an independent DB oracle (its own owner-or-member SQL, not the code under test), for EVERY active
Staff account that holds priceComparison:view, plus Admin, plus widening attempts, plus a live
membership change on an existing session.
Run AFTER the other scripts (it creates one user and one membership, and removes both).
Target: local throwaway instance only (see authz_test.py). Never prod.
Usage: python -I s5_verify.py <dir holding authz_test.py>
"""
import json, sys, os, subprocess, hashlib, base64, urllib.parse
S = sys.argv[1]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)

PG = ["docker", "exec", "vega-perf-pg", "psql", "-U", "vega", "-d", "vega_sec5", "-tAc"]
def sql(q):
    r = subprocess.run(PG + [q], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

LIST = "/api/suppliers/price-comparison"
ITEM = "/api/suppliers/price-comparison/item"
out = []
def chk(cid, name, m, p, status, ok, note=""):
    out.append((cid, name, m, p, status, "PASS" if ok else "FAIL", str(note)[:200]))

def uid(email):
    return sql(f"select id from users where email='{email}'")

def oracle_projects(user_id):
    rows = sql(f'''select p.id from projects p where p."ownerId"='{user_id}'
                   or exists (select 1 from project_members pm where pm."projectId"=p.id and pm."userId"='{user_id}')''')
    return set(rows.split()) if rows else set()

def oracle_counts(pids):
    if not pids:
        return 0, 0
    inl = ",".join(f"'{p}'" for p in pids)
    n = int(sql(f'select count(*) from base_items b join projects p on p.id=b."projectId" where p.id in ({inl})'))
    nn = int(sql(f'select count(*) from base_items b join projects p on p.id=b."projectId" where p.id in ({inl}) and b."supplierId" is null'))
    return n, nn

def rows_of(body):
    return [r for g in body for r in g["rows"]]

def get_list(cookie, qs=""):
    s, t, *_ = req("GET", LIST + qs, cookie)
    return s, t, (json.loads(t) if s == 200 else None)

ALL_ROWS = int(sql('select count(*) from base_items b join projects p on p.id=b."projectId"'))
ALL_PROJ_WITH_ITEMS = set(sql('select distinct "projectId" from base_items').split())

# ── P1 Gate ─────────────────────────────────────────────────────────────────
s, t, *_ = req("GET", LIST)
chk("P1", "no cookie -> 401", "GET", LIST, s, s == 401, t[:80])
none_tok = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode() + "." + \
    base64.urlsafe_b64encode(b'{"sid":"x"}').rstrip(b"=").decode() + "."
s, t, *_ = req("GET", LIST, none_tok)
chk("P1", "forged alg:none cookie -> 401", "GET", LIST, s, s == 401, t[:80])
s, t, *_ = req("GET", LIST, None, headers={"x-middleware-subrequest": "middleware:middleware:middleware:middleware:middleware"})
chk("P1", "x-middleware-subrequest bypass header, no cookie -> 401", "GET", LIST, s, s == 401, t[:80])
s, t, *_ = req("GET", LIST, None, headers={"x-middleware-subrequest": "src/proxy:src/proxy:src/proxy:src/proxy:src/proxy"})
chk("P1", "x-middleware-subrequest (proxy path), no cookie -> 401", "GET", LIST, s, s == 401, t[:80])
NOPC, _ = login("perf.staff12@vegahomes.lk")   # suppliers:view only
assert NOPC
s, t, *_ = req("GET", LIST, NOPC)
chk("P1", "staff without priceComparison:view -> 403 (list)", "GET", LIST, s, s == 403, t[:80])
s, t, *_ = req("GET", ITEM + "?name=Cement&unit=Bag", NOPC)
chk("P1", "staff without priceComparison:view -> 403 (item)", "GET", ITEM, s, s == 403, t[:80])
ADMIN, _ = login("sanduni@vegahomes.lk")
assert ADMIN
s, t, *_ = req("POST", LIST, ADMIN, {})
chk("P1", "POST on list -> 405", "POST", LIST, s, s == 405, t[:80])

# ── P2 Admin baseline ──────────────────────────────────────────────────────
s, t, body = get_list(ADMIN)
rows = rows_of(body) if body is not None else []
chk("P2", f"admin sees every base_item ({ALL_ROWS})", "GET", LIST, s, s == 200 and len(rows) == ALL_ROWS, f"{len(rows)} rows")
chk("P2", f"admin sees every project with items ({len(ALL_PROJ_WITH_ITEMS)})", "GET", LIST, s,
    {r["projectId"] for r in rows} == ALL_PROJ_WITH_ITEMS, f"{len({r['projectId'] for r in rows})} projects")

# ── P3 Every eligible Staff account against the oracle ─────────────────────
eligible = sql('''select u.email from users u where u.role='Staff' and u.status='Active' and (
    exists (select 1 from user_roles ur join role_permissions rp on rp."roleId"=ur."roleId"
            where ur."userId"=u.id and rp.module='priceComparison' and rp.action='view')
 or exists (select 1 from user_permissions up where up."userId"=u.id and up.module='priceComparison' and up.action='view'))
 order by 1''').split()
COOKIES = {}
staff_summary = []
for email in eligible:
    c, _ = login(email)
    if not c:
        chk("P3", f"{email}: login", "POST", "/api/auth/login", 0, False, "login failed"); continue
    COOKIES[email] = c
    pids = oracle_projects(uid(email))
    n, nn = oracle_counts(pids)
    s, t, body = get_list(c)
    rows = rows_of(body) if body is not None else []
    got = {r["projectId"] for r in rows}
    foreign = got - pids
    chk("P3", f"{email}: no foreign project", "GET", LIST, s, s == 200 and not foreign, f"foreign={sorted(foreign)[:5]}")
    chk("P3", f"{email}: row count = DB ({n})", "GET", LIST, s, len(rows) == n, f"{len(rows)} rows")
    chk("P3", f"{email}: null-supplier rows = DB ({nn})", "GET", LIST, s,
        sum(1 for r in rows if r["supplierId"] is None) == nn, "")
    staff_summary.append((email, len(pids), len(got), len(rows), n, len(ALL_PROJ_WITH_ITEMS - pids & ALL_PROJ_WITH_ITEMS)))

# Owner-only and member-only branches must each be exercised by at least one account
u1, u13 = uid("perf.staff1@vegahomes.lk"), uid("perf.staff13@vegahomes.lk")
mem_only = set(sql(f'''select pm."projectId" from project_members pm join projects p on p.id=pm."projectId"
                       where pm."userId"='{u1}' and p."ownerId"<>'{u1}' ''').split()) & ALL_PROJ_WITH_ITEMS
s, t, body = get_list(COOKIES["perf.staff1@vegahomes.lk"])
got1 = {r["projectId"] for r in rows_of(body)}
chk("P3", f"member branch: perf.staff1 (member-only) sees its {len(mem_only)} member projects with items", "GET", LIST, s,
    len(mem_only) > 0 and mem_only <= got1, f"missing={sorted(mem_only - got1)}")
own_only = set(sql(f'''select id from projects where "ownerId"='{u13}' ''').split()) & ALL_PROJ_WITH_ITEMS
s, t, body = get_list(COOKIES["perf.staff13@vegahomes.lk"])
got13 = {r["projectId"] for r in rows_of(body)}
chk("P3", f"owner branch: perf.staff13 (owner-only) sees its {len(own_only)} owned projects with items", "GET", LIST, s,
    len(own_only) > 0 and own_only <= got13, f"missing={sorted(own_only - got13)}")

# ── P4 Widening attempts (perf.staff1) ─────────────────────────────────────
ST = COOKIES["perf.staff1@vegahomes.lk"]
_, base_t, _ = get_list(ST)
base_h = hashlib.sha256(base_t.encode()).hexdigest()
admin_id = uid("sanduni@vegahomes.lk")
for qs in ["?projectId=perf_p001", "?project=perf_p001&project=perf_p002", "?all=1", "?scope=all", "?role=Admin",
           f"?userId={admin_id}", "?projectId=' or 1=1--", "?projectId[]=perf_p001", "?" + "x=" + "A" * 4000]:
    s, t, _ = get_list(ST, qs.replace(" ", "%20"))
    chk("P4", f"query {qs[:40]} ignored (body identical)", "GET", LIST + qs[:40], s,
        s == 200 and hashlib.sha256(t.encode()).hexdigest() == base_h, f"{len(t)} bytes vs {len(base_t)}")
for hk, hv in [("X-User-Id", admin_id), ("X-Role", "Admin"), ("X-Forwarded-For", "127.0.0.1"), ("x-middleware-subrequest", "src/proxy:src/proxy:src/proxy:src/proxy:src/proxy")]:
    s, t, *_ = req("GET", LIST, ST, headers={hk: hv})
    chk("P4", f"header {hk} ignored (body identical)", "GET", LIST, s,
        s == 200 and hashlib.sha256(t.encode()).hexdigest() == base_h, f"{len(t)} bytes")

# ── P5 List and detail agree (perf.staff1) ─────────────────────────────────
pids1 = oracle_projects(u1)
_, _, body1 = get_list(ST)
mixed = []
for g in body1:
    nm, un = g["name"].replace("'", "''"), g["unit"].replace("'", "''")
    on_db = set(sql(f'''select distinct "projectId" from base_items where lower(name)=lower('{nm}') and lower(unit)=lower('{un}')''').split())
    if on_db - pids1:
        mixed.append(g)
    if len(mixed) >= 10:
        break
chk("P5", "fixture: groups that also exist on foreign projects", "-", "-", 0, len(mixed) > 0, f"{len(mixed)} groups")
for g in mixed:
    q = "?" + urllib.parse.urlencode({"name": g["name"], "unit": g["unit"]})
    s, t, *_ = req("GET", ITEM + q, ST)
    d = json.loads(t) if s == 200 else {}
    det = {p["projectId"] for p in d.get("projects", [])}
    aud = {a["projectId"] for a in d.get("audit", [])}
    use = {u["projectId"] for u in d.get("usage", [])}
    lst = {r["projectId"] for r in g["rows"]}
    chk("P5", f"detail = list for '{g['name'][:30]}' / {g['unit']}", "GET", ITEM, s,
        s == 200 and det == lst and aud <= pids1 and use <= pids1, f"list={sorted(lst)} detail={sorted(det)}")
# A group that exists ONLY on foreign projects must be absent from the list and 404 on the detail
fo = sql(f'''select b.name||'|'||b.unit from base_items b where not exists (
               select 1 from base_items b2 where lower(b2.name)=lower(b.name) and lower(b2.unit)=lower(b.unit)
               and b2."projectId" in ({",".join(f"'{p}'" for p in pids1)})) limit 1''')
if fo:
    nm, un = fo.split("|", 1)
    in_list = any(g["name"].lower() == nm.strip().lower() and g["unit"].lower() == un.strip().lower() for g in body1)
    chk("P5", f"foreign-only group '{nm[:30]}' absent from staff list", "GET", LIST, 200, not in_list, "")
    s, t, *_ = req("GET", ITEM + "?" + urllib.parse.urlencode({"name": nm, "unit": un}), ST)
    chk("P5", f"foreign-only group detail -> 404", "GET", ITEM, s, s == 404, t[:80])
else:
    chk("P5", "fixture: a foreign-only group exists", "-", "-", 0, False, "none found")

# ── P6 Staff with priceComparison:view and zero projects ───────────────────
EMPTY = f"s5.empty.{int(time.time())}@vegahomes.lk"
PW = "S5-Check-Pass-2026!"
s, t, *_ = req("POST", "/api/users", ADMIN, {"name": "S5 empty", "email": EMPTY, "role": "Staff", "password": PW,
                                              "permissions": ["priceComparison:view"]})
chk("P6", "fixture: admin creates Staff with only priceComparison:view", "POST", "/api/users", s, s in (200, 201), t[:100])
EC, _ = login(EMPTY, PW)
s, t, body = get_list(EC) if EC else (0, "", None)
chk("P6", "zero-project staff -> 200 []", "GET", LIST, s, s == 200 and body == [], t[:80])
s, t, *_ = req("GET", ITEM + "?name=Cement&unit=Bag", EC)
chk("P6", "zero-project staff, item detail -> 404", "GET", ITEM, s, s == 404, t[:80])

# ── P7 Membership change applies to an EXISTING session, both ways ─────────
S13 = COOKIES["perf.staff13@vegahomes.lk"]
pids13 = oracle_projects(u13)
target = sorted(ALL_PROJ_WITH_ITEMS - pids13)[0]
s, t, *_ = req("POST", f"/api/projects/{target}/members", ADMIN, {"userId": u13})
chk("P7", f"fixture: admin adds perf.staff13 to {target}", "POST", f"/api/projects/{target}/members", s, s in (200, 201), t[:100])
s, t, body = get_list(S13)
chk("P7", f"same session now sees {target}", "GET", LIST, s, target in {r["projectId"] for r in rows_of(body)}, "")
s, t, *_ = req("DELETE", f"/api/projects/{target}/members/{u13}", ADMIN)
chk("P7", "fixture: admin removes the membership", "DELETE", f"/api/projects/{target}/members/{u13}", s, s in (200, 204), t[:100])
s, t, body = get_list(S13)
chk("P7", f"same session no longer sees {target}", "GET", LIST, s, target not in {r["projectId"] for r in rows_of(body)}, "")

# ── Cleanup ────────────────────────────────────────────────────────────────
s, t, *_ = req("DELETE", f"/api/users/{urllib.parse.quote(EMPTY)}", ADMIN)
chk("CL", "cleanup: delete the zero-project user", "DELETE", "/api/users/<s5.empty>", s, s in (200, 204), t[:100])

# ── Output ─────────────────────────────────────────────────────────────────
print("eligible staff accounts:", len(eligible))
print(f"{'account':32} {'oracle proj':>11} {'seen proj':>9} {'rows':>6} {'db rows':>7} {'hidden proj':>11}")
for e, op, sp, r, n, hid in staff_summary:
    print(f"{e:32} {op:>11} {sp:>9} {r:>6} {n:>7} {hid:>11}")
for r in out:
    print(" | ".join(str(x) for x in r))
p = sum(1 for r in out if r[5] == "PASS")
print(f"\nTOTAL {len(out)}  PASS {p}  FAIL {len(out) - p}")
json.dump([dict(zip(["id", "name", "method", "path", "status", "verdict", "note"], r)) for r in out],
          open(os.path.join(S, "s5_verify_results.json"), "w", encoding="utf-8"), indent=1)
