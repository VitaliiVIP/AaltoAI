from ortools.sat.python import cp_model

FEATS = ["yrs_python","yrs_django","n_be_projects","has_aws_cert","knows_docker","sql_prof","edu_level"]
W     = {"yrs_python":6,"yrs_django":4,"n_be_projects":5,"has_aws_cert":7,"knows_docker":6,"sql_prof":5,"edu_level":4}
UB    = {"yrs_python":15,"yrs_django":15,"n_be_projects":12,"has_aws_cert":1,"knows_docker":1,"sql_prof":3,"edu_level":3}
COST  = {"yrs_python":12,"yrs_django":12,"n_be_projects":5,"has_aws_cert":9,"knows_docker":4,"sql_prof":6,"edu_level":40}
MAXD  = {"yrs_python":3,"yrs_django":3,"n_be_projects":6,"has_aws_cert":1,"knows_docker":1,"sql_prof":2,"edu_level":1}  # 18-month horizon
X     = {"yrs_python":3,"yrs_django":1,"n_be_projects":2,"has_aws_cert":0,"knows_docker":1,"sql_prof":1,"edu_level":1}
TAU, EPS = 60, 0

def score(v): return sum(W[f]*v[f] for f in FEATS)

def solve(eps=0, cuts=(), sparsity_pen=0, forbid_edu=False):
    m = cp_model.CpModel()
    a = {f: m.NewIntVar(0, MAXD[f], "a_"+f) for f in FEATS}      # one-directional: a >= 0
    xp = {f: m.NewIntVar(0, UB[f], "x_"+f) for f in FEATS}
    u = {f: m.NewBoolVar("u_"+f) for f in FEATS}                  # used indicator
    for f in FEATS:
        m.Add(xp[f] == X[f] + a[f])
        m.Add(a[f] <= MAXD[f]*u[f]); m.Add(a[f] >= u[f])
    if forbid_edu: m.Add(a["edu_level"] == 0)
    # knockout: must have >= 2 years Python
    m.Add(xp["yrs_python"] >= 2)
    # causal: Django years cannot exceed Python years
    m.Add(xp["yrs_django"] <= xp["yrs_python"])
    # causal: no more than 2 extra projects without an extra year of coding time
    m.Add(a["n_be_projects"] <= 2 + 2*a["yrs_python"])
    # decision constraint with robustness margin
    m.Add(sum(W[f]*xp[f] for f in FEATS) >= TAU + eps)
    # no-good cuts: exclude previously returned action vectors
    for c in cuts:
        lits = []
        for f in FEATS:
            b = m.NewBoolVar(""); m.Add(a[f] != c[f]).OnlyEnforceIf(b); m.Add(a[f] == c[f]).OnlyEnforceIf(b.Not()); lits.append(b)
        m.AddBoolOr(lits)
    m.Minimize(sum(COST[f]*a[f] for f in FEATS) + sparsity_pen*sum(u.values()))
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = 10
    st = s.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return None
    act = {f: s.Value(a[f]) for f in FEATS}
    return act, sum(COST[f]*act[f] for f in FEATS), score({f: X[f]+act[f] for f in FEATS})

print("baseline score:", score(X), "threshold:", TAU, "gap:", TAU-score(X))
for eps,label in [(0,"eps=0"),(6,"eps=6 (robust margin)")]:
    print("\n### "+label)
    cuts=[]
    for k in range(3):
        r = solve(eps=eps, cuts=cuts, sparsity_pen=1)
        if r is None: print("  no more"); break
        act,cost,sc = r
        cuts.append(act)
        chg = {f:v for f,v in act.items() if v}
        print(f"  CF{k+1}: cost={cost:3d} score={sc} changes={chg}")
print("\n### eps=0, education change forbidden")
cuts=[]
for k in range(3):
    r = solve(eps=0, cuts=cuts, sparsity_pen=1, forbid_edu=True)
    if r is None: break
    act,cost,sc = r; cuts.append(act)
    print(f"  CF{k+1}: cost={cost:3d} score={sc} changes={ {f:v for f,v in act.items() if v} }")

# Reference implementation for the worked example in recourse_engine_brief.md
# Run: pip install ortools && python recourse_toy_cpsat.py
# Verified 2026-09-19 with ortools 9.15.6755 on Python 3.14.
