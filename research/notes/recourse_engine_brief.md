# Recourse Engine Technical Brief — Fixed-Threshold Mode

**Scope.** The counterfactual generator that sits behind the pass/fail gate: given an extracted
profile `x`, an employer-configured interpretable scorer `f`, and a fixed per-job threshold `τ`,
return the `k` cheapest feasible profiles `x'` with `f(x') ≥ τ`. Ranking mode is out of scope.
Companion to `research/algorithmic_recourse_and_counterfactual_explanations_in_hiring.md`
(sections 2.1–2.2); this brief goes one level down into formulation, tooling and code.
All library facts below were verified against PyPI JSON and the GitHub API on **2026-09-19**,
and three of the libraries were actually installed and run.

---

## 1. Problem formulation for our feature space

### 1.1 Feature taxonomy

Partition the `d` profile features into four disjoint sets:

| Set | Examples | Domain | Action model |
|---|---|---|---|
| `J_int` | `yrs_python`, `n_backend_projects` | `{0,…,U_j} ⊂ ℤ` | one-directional, `a_j ≥ 0` |
| `J_bool` | `has_aws_cert`, `knows_docker` | `{0,1}` | acquire only, `a_j ∈ {0,1}` |
| `J_ord` | `sql_proficiency ∈ {0..3}`, `edu_level ∈ {0..3}` | ordered levels | one-directional, non-uniform step cost |
| `J_imm` | age, gender, nationality, name-derived signals, zip code | any | **excluded from the model entirely, not merely frozen** |

Two notes that matter more than they look. First, immutable and protected attributes should not be
inputs to the scorer at all, so they never appear in the recourse program — freezing them at
solve time still lets them shift the intercept and produce group-dependent recourse cost. Zip code
is specifically barred as a proxy by Illinois HB 3773. Second, "one-directional" is a property of
the *action*, not the feature: a candidate can gain a year of Python but cannot lose one, so
`a_j ≥ 0` is a hard constraint, not a preference.

Let `x ∈ ℤ^d` be the current profile, `a ∈ ℤ^d` the action, `x' = x + a` the counterfactual profile.

### 1.2 Case (a): additive/linear scorer with knockout rules

The employer configures weights `w_j ≥ 0`, an offset `b`, a threshold `τ`, and a set `K` of
knockout predicates (hard requirements such as "≥ 2 years of Python", "work authorization").
The decision is

```
pass(x)  ⇔  Σ_j w_j x_j + b ≥ τ    AND    x_j ≥ κ_j  ∀ j ∈ K
```

Keep the knockout conjunction **outside** the weighted score. Folding a knockout in as a huge weight
makes the recourse engine emit nonsense trade-offs ("compensate for missing work authorization with
four more side projects").

Minimum-cost recourse is then the integer program

```
min_a    C(a) = Σ_j c_j(a_j)                              (effort cost)
s.t.     Σ_j w_j (x_j + a_j) + b ≥ τ + ε                  (flip + robustness margin)
         x_j + a_j ≥ κ_j                    ∀ j ∈ K       (knockouts)
         0 ≤ a_j ≤ Δ_j                      ∀ j           (feasible change horizon)
         x_j + a_j ≤ U_j                    ∀ j           (domain upper bound)
         a_j ∈ ℤ                            ∀ j
         a_j = 0                            ∀ j ∈ J_imm
         G(x + a) ≤ 0                                      (causal / dependency constraints, §3)
```

`Δ_j` is the largest change deemed achievable in the stated horizon (we use 18 months). It is what
stops the solver from answering "get eight more years of experience".

**Ustun-style flipset encoding for non-linear step costs.** Ustun, Spangher & Liu (2019) encode each
feature's action grid with one-hot binaries, which lets `c_j` be an arbitrary (e.g. convex
increasing) function of the step rather than a constant per unit. Let `A_j = {0, 1, …, Δ_j}` be the
admissible steps for feature `j` and `u_{jk} ∈ {0,1}` indicate `a_j = k`:

```
min      Σ_j Σ_{k∈A_j} c_{jk} · u_{jk}
s.t.     Σ_{k∈A_j} u_{jk} = 1                      ∀ j        (SOS-1: exactly one step per feature)
         Σ_j Σ_{k∈A_j} w_j · k · u_{jk} ≥ τ + ε − (Σ_j w_j x_j + b)   (flip)
         u_{jk} = 0   whenever  x_j + k > U_j                 (domain)
         u_{jk} ∈ {0,1}
```

The right-hand side of the flip constraint is the **score gap** `g = τ + ε − f(x)`, precomputed once.
The problem size is `Σ_j (Δ_j + 1)` binaries — for a 20-feature profile with `Δ_j ≤ 6` that is under
150 binaries, which any MILP solver closes in milliseconds.

**Sparsity.** Candidates act on at most two or three things. Add a used-indicator `v_j ∈ {0,1}` with
`a_j ≤ Δ_j v_j` and `a_j ≥ v_j`, then either penalise (`+ λ Σ_j v_j` in the objective, λ small enough
to act only as a tie-break) or hard-cap (`Σ_j v_j ≤ 3`). The penalty is better: a hard cap can make
an otherwise-feasible instance infeasible, and "no recourse exists" is a much worse answer than a
four-item plan.

### 1.3 Case (b): monotone tree / GAM scorer

The useful structural fact: **any purely additive model is MILP-representable with exactly the same
machinery**, because a shape function evaluated on a discrete grid is just a lookup table. For an
EBM or monotone GAM with `f(x) = Σ_j g_j(x_j) + b`, reuse the one-hot variables with the level value
`v_{jk} = x_j + k` and substitute the shape function for the linear term:

```
Σ_j Σ_{k∈A_j} g_j(v_{jk}) · u_{jk} + b ≥ τ + ε
```

Nothing else changes. Monotone training (`monotone_constraints` in `interpret`'s
`ExplainableBoostingClassifier`, verified present in 0.7.8) guarantees `g_j` is non-decreasing,
which keeps the advice coherent: no "drop a project to pass".

Pairwise interactions `g_{jl}(x_j, x_l)` break additivity and need a 2-D one-hot `z_{jklm}` with
McCormick-style linking constraints — quadratically many binaries. For the demo, **train the EBM
with `interactions=0`** and keep the additive form. If a later version needs interactions, the
2-D encoding is still exact, just larger.

For a genuinely non-additive monotone tree ensemble, exact MILP encoding of the tree paths is
possible but heavy. The cheap alternative for our feature space: it is small and discrete, so
**enumerate**. With 20 features and a horizon cap of `Δ_j ≤ 6`, a best-first search over action
vectors ordered by cost, pruned by monotonicity (if an action fails and the model is monotone, no
sub-action of it succeeds), terminates fast enough for an interactive demo.

### 1.4 k diverse counterfactuals

Solve sequentially and cut. After returning action `a^t`, add one of:

- **No-good cut (exact distinctness).** `Σ_{(j,k) ∈ S_t} u_{jk} ≤ |S_t| − 1` where
  `S_t = {(j, a^t_j)}`. Forbids that exact vector. Cheap, but produces near-duplicates
  ("+2 projects" then "+3 projects").
- **Support-disjointness (what we recommend).** Require each new counterfactual to touch at least
  one feature no previous one touched: `Σ_{j ∉ supp(a^t)} v_j ≥ 1`, added once per previous
  solution. This is the MILP analogue of DiCE's diversity term and gives genuinely different
  *stories*, which is the point for a candidate.
- **DiCE-style objective term.** Maximise a determinantal or pairwise-distance term over the whole
  set at once. Requires solving for all `k` jointly; not worth it at our scale.

In the worked example below, support-disjointness changed the returned set materially versus plain
no-good cuts, at no measurable solve-time cost.

---

## 2. Library landscape, verified 2026-09-19

| Library | Latest release | Last commit | Models | Constraints | Python | Licence |
|---|---|---|---|---|---|---|
| **actionable-recourse** (`ustunb/actionable-recourse`) | 1.0.1, **2020-10-09** | **2020-10-15** | linear only | direction, mutability, integer grids, custom bounds — the best constraint model of any of these | declares `>=3.6`; **broken on NumPy ≥ 2** | BSD-3 |
| **dice-ml** (`interpretml/DiCE`) | 0.12, **2025-07-13** | 2025-07-13 | sklearn, PyTorch, TF, XGBoost, model-agnostic | `features_to_vary` (immutability) and `permitted_range` (box bounds) **only** | 3.9–3.12 declared; ran fine on 3.14 | MIT |
| **CARLA** (`carla-recourse/CARLA`) | 0.0.5, **2022-05-30** | **2023-02-22** | benchmark harness over 11 methods | varies by wrapped method | classifier says **3.7 only** | MIT |
| **alibi** (`SeldonIO/alibi`) | 0.9.6, **2024-04-18** | 2025-10-10 | TF/PyTorch-centric CF methods (CFProto, CEM, CF-RL) | feature-range and categorical handling; no first-class actionability model | 3.8–3.11 | **Business Source Licence 1.1** |
| **OmniXAI** (`salesforce/OmniXAI`) | 1.3.1, **2023-07-16** | 2026-06-02 (compliance file only) | `MACEExplainer` (black-box, mixed types), `CounterfactualExplainer` (continuous only) | no documented actionability/monotonicity API | `>=3.7,<4` | BSD-3 |
| **jax-relax** (`BirkhoffG/jax-relax`) | — | 2025-02-11, 6 stars | JAX models | research-grade | — | Apache-2.0 |
| **OR-Tools CP-SAT** | 9.15.6755, **2026-01-14** | 2026-09-17 | n/a (solver) | arbitrary linear/integer/logical constraints | `>=3.9` | Apache-2.0 |
| **PuLP** / **highspy** | 3.3.2 (2026-05) / 1.15.1 (2026-07) | active | n/a (solver) | arbitrary MILP | `>=3.10` / `>=3.9` | MIT |
| **interpret** (EBM) | 0.7.8, **2026-03-17** | 2026-08-17 | GA2M/EBM | `monotone_constraints`, `exclude`, `interactions` | active | MIT |

**What I actually ran.**

`actionable-recourse` installs on Python 3.14 but **does not work on a current stack**. Two hard
failures in a minimal four-feature logistic-regression example:

```
recourse/helper_functions.py:72  TypeError: only 0-dimensional arrays can be converted to Python scalars
recourse/flipset.py:41          AttributeError: `np.float_` was removed in the NumPy 2.0 release
```

Both are NumPy 2 incompatibilities in a package last touched in October 2020, and pinning
`numpy<2` conflicts with current pandas, scipy and matplotlib. Treat it as **reference source code,
not a dependency** — its `ActionSet` design (per-feature `step_direction`, `mutable`, `step_type`,
`bounds`) is the right API and worth copying.

`dice-ml` installs and runs cleanly on Python 3.14 / NumPy 2.5 / pandas 3.0, and it is the only
genuinely maintained option in the list. But on our feature space it misbehaves. Asked for three
counterfactuals for a candidate at `(years_python=0, n_projects=1, has_cert=0)` with the `genetic`
method, it returned:

```
years_python  n_projects  has_cert
         0.0         7.8       0.0
         0.0         8.9       0.0
         8.0         0.9       0.0
```

Three problems in three rows: **fractional counts** (7.8 projects), a **decrease** in a
one-directional feature (1 → 0.9 projects), and **no cost minimality** (8 years of Python when 2
would do). Declaring the lower bound of `permitted_range` equal to the candidate's current value
per query does fix the direction problem — a useful hack, verified working — but fractional values
survive, and rounding them afterwards can push the profile back below the threshold, silently
destroying validity.

**Recommendation: write the solver ourselves on OR-Tools CP-SAT.** Roughly 120 lines. Justification:

1. Our decision function is *known and interpretable by construction*. We are not explaining a black
   box, so the whole model-agnostic search apparatus buys nothing.
2. Every constraint we care about — integrality, one-directional actionability, per-feature change
   horizons, knockouts, cross-feature causal links, sparsity, diversity cuts, robustness margin — is
   a native CP-SAT constraint and *none* of them is expressible in dice-ml's public API.
3. Exact optimality with a proof, versus a genetic algorithm's "something that flips". For a demo
   whose pitch is "the *minimal* change", returning a provably minimal change matters.
4. Zero licence friction. Alibi's BSL 1.1 restricts production use to non-profit educational
   institutions that do not commercialise; fine for a student showcase, a trap if the project
   continues.
5. Millisecond solve times at our problem size, and the model is readable by a judge.

Use `dice-ml` as a **baseline for the report**, not as the product path: it is a fair, citable
comparison showing why the constrained MILP is needed. CP-SAT over PuLP/HiGHS because the logical
constraints (reified indicators, `OnlyEnforceIf`, boolean-or diversity cuts) are first-class rather
than manual big-M encodings.

---

## 3. Constraint design

**Actionability and immutability.** Encode as variable domains, not post-filters:
`a_j ∈ [0, min(Δ_j, U_j − x_j)]`. Protected attributes are absent from the feature schema. A single
declarative `ActionSet`-style config (one YAML block per feature: `direction`, `max_delta`,
`step_cost`, `upper_bound`, `knockout_min`) keeps this employer-configurable and auditable, and
makes the constraint set itself a documentation artefact for EU AI Act technical-documentation
duties.

**Causal / dependency constraints.** Two forms, both linear and both cheap:

- *Dominance*: a specialisation cannot exceed its prerequisite.
  `x'_django ≤ x'_python`, `x'_react ≤ x'_javascript`.
- *Resource coupling*: actions compete for the same calendar time.
  `a_projects ≤ 2 + 2·a_yrs_python` encodes "no more than two extra projects without another year
  of coding time". A cleaner general version is a single time budget:
  `Σ_j t_j · a_j ≤ T` with `t_j` in months.
- *Side effects*: gaining a certification also lifts proficiency. Model as an implication,
  `a_cert = 1 ⇒ x'_sql_prof ≥ 2`, rather than silently adding score, so the effect is visible in the
  explanation.

This is the practical, demo-scale version of Karimi et al.'s causal recourse. We are not estimating
a structural causal model; we are hand-authoring a small dependency graph per job template. Say so
in the report — an honest hand-authored graph beats a fabricated SCM.

**Plausibility.** Full FACE (density-weighted graph paths) is a stretch goal. For the demo, two
cheap surrogates that get most of the value:
1. Cap `x'_j` at the 95th percentile of the applicant population per feature. Stops "12 projects".
2. Post-hoc k-NN check: require the returned `x'` to have at least `m` training profiles within L1
   radius `r`. If not, discard and take the next solution. This is a filter on an already-small
   candidate set, so it costs nothing.

**Cost models.** Three options, in increasing order of defensibility:
- *Per-step constants* `c_j` in "effort points", authored by the employer. Transparent, arguable,
  and the right default for the demo.
- *Percentile shift* (Ustun et al.): `c_j(a_j) = |Q_j(x_j + a_j) − Q_j(x_j)|` with `Q_j` the
  empirical CDF over the applicant pool. Removes hand-tuned units and makes costs commensurable
  across features. Requires an applicant distribution, which a hackathon demo may not have; it is
  the first thing to add once there is data.
- *Group-normalised* (Gupta et al. 2019, "Equalizing Recourse Across Groups"): normalise or
  constrain so that expected recourse cost is comparable across protected groups. This is an
  **audit metric** for us, not a live constraint — compute mean recourse cost per group over a
  synthetic cohort and report the ratio. Cheap to compute, and it is the single most compelling
  fairness slide available for this project.

Be explicit that the cost vector is a value judgement, not a measurement (Barocas, Selbst &
Raghavan 2020). Making it employer-authored and visible is the honest design.

---

## 4. Robustness

**Margin (do this).** Solve for `f(x') ≥ τ + ε` rather than `≥ τ`. Two sources of noise justify ε:
LLM extraction error on the profile, and future model retuning. Calibrate empirically: perturb each
extracted profile by resampling the LLM extraction `n` times, measure the score standard deviation
σ, set `ε = 2σ`. In the worked example, ε = 6 on a threshold of 60 changed the top recommendation
and raised its cost from 16 to 22 — a real, demonstrable trade-off, and a good slide.

**ROAR-style robustness, and a clean special case.** Upadhyay et al. (2021) ask for recourse valid
for any weight vector in a ball around `w`. For an L∞ ball of radius ρ:

```
min_{‖δ‖_∞ ≤ ρ} (w + δ)ᵀ x'  =  wᵀ x' − ρ · ‖x'‖₁
```

and because **every feature in our space is non-negative**, `‖x'‖₁ = Σ_j x'_j`. So the robust flip
constraint collapses to

```
Σ_j (w_j − ρ) · x'_j + b ≥ τ
```

which is still linear and drops straight into the same MILP with no solver change. This is worth
stating in the report: worst-case-robust recourse over an L∞ weight ball is *free* for a
non-negative-feature linear scorer. Set ρ from the largest weight change the employer is allowed to
make without re-issuing recourse, or measure it across model versions.

**Presenting validity.** Every returned counterfactual should carry: the achieved score, the margin
above threshold, the model version and date, the cost, and an explicit validity statement —
"under scoring model `swe-backend-v3` as evaluated on 2026-09-19". Store the `(profile, model
version, counterfactual, timestamp)` tuple. Do not promise future validity; promise that the change
would have flipped *this* decision. That phrasing is both technically true and the one the legal
analysis in the main report recommends.

---

## 5. Worked example

**Job:** backend software engineer. Seven features, linear scorer, threshold `τ = 60`, one knockout
(`yrs_python ≥ 2`). Numbers below are from an actual CP-SAT run
(`ortools 9.15.6755`), not hand-computed.

| Feature | Weight `w` | Cand. `x` | Max Δ (18 mo) | Cost/step | Domain |
|---|---|---|---|---|---|
| `yrs_python` | 6 | 3 | 3 | 12 | 0–15 |
| `yrs_django` | 4 | 1 | 3 | 12 | 0–15 |
| `n_be_projects` | 5 | 2 | 6 | 5 | 0–12 |
| `has_aws_cert` | 7 | 0 | 1 | 9 | 0–1 |
| `knows_docker` | 6 | 1 | 1 | 4 | 0–1 |
| `sql_proficiency` | 5 | 1 | 2 | 6 | 0–3 |
| `edu_level` | 4 | 1 | 1 | 40 | 0–3 |

Causal constraints: `x'_django ≤ x'_python`; `a_projects ≤ 2 + 2·a_yrs_python`.

**Baseline.** `f(x) = 6·3 + 4·1 + 5·2 + 7·0 + 6·1 + 5·1 + 4·1 = 47`. Knockout satisfied.
Score gap to threshold: **13 points**. Decision: reject.

**Result 1 — minimum cost, no-good cuts, ε = 0:**

| # | Action | Cost | New score |
|---|---|---|---|
| 1 | +2 backend projects, +1 SQL level | 16 | 62 |
| 2 | +1 backend project, +2 SQL levels | 17 | 62 |
| 3 | +2 backend projects, AWS certification | 19 | 64 |

Note how similar 1 and 2 are — this is the near-duplicate failure mode of plain no-good cuts.

**Result 2 — support-disjoint diversity, ε = 0** (recommended configuration):

| # | Action | Cost | New score |
|---|---|---|---|
| 1 | +2 backend projects, +1 SQL level | 16 | 62 |
| 2 | +2 backend projects, AWS certification | 19 | 64 |
| 3 | AWS certification, +2 SQL levels | 21 | 64 |

Three distinct stories: build, certify, or deepen. Exactly what a candidate-facing UI wants.

**Result 3 — robustness margin ε = 6:**

| # | Action | Cost | New score |
|---|---|---|---|
| 1 | +2 backend projects, +2 SQL levels | 22 | 67 |
| 2 | +2 backend projects, AWS cert, +1 SQL level | 25 | 69 |
| 3 | +1 year Python, +3 backend projects | 27 | 68 |

The margin costs 6 extra effort points on the cheapest path and pushes out the marginal advice.

**What the solver never suggested, and why that is the point.** Education level: weight 4, cost 40,
so one level costs 40 points to buy 4 score points — dominated by every alternative, and correctly
never returned. Extra Django years: capped by `x'_django ≤ x'_python` and priced at 12. Docker: the
candidate already has it, so `a = 0` by the domain bound — an early buggy version of the model that
omitted the `x'_j ≤ U_j` bound happily recommended "learn Docker" to someone who already knew it.
That bug is the single most likely one to ship.

---

## 6. Pitfalls specific to hiring recourse

1. **Near-immutable recommendations.** Education level, relocation and total years of experience are
   technically mutable and practically not, on any horizon a candidate cares about. Guard with
   `Δ_j` and a high `c_j`, and add a hard allow-list of features the UI is permitted to mention.
   Never let the engine emit advice about anything that correlates with a protected class.
2. **Degenerate "add one keyword".** If the LLM extractor sets `knows_kubernetes = 1` on the mere
   appearance of the word, the cheapest recourse is a resume edit, not a skill. This is
   Fokkema et al.'s recourse-versus-manipulation problem arriving through the extractor rather than
   the model. Mitigations: require evidence-grounded extraction (skill asserted only with a
   supporting project or role span), set step costs to reflect *acquisition* effort rather than
   *assertion* effort, and phrase the output as the underlying capability.
3. **Knockout versus weighted score.** If a knockout fails, there is no score-based recourse and the
   engine must say so separately: "this role requires X; no combination of other changes qualifies".
   Reporting a weighted-score counterfactual while a knockout is unmet is simply a false statement.
4. **Infeasibility is a real outcome.** Ustun et al. showed classifiers can deny recourse entirely.
   With `Δ_j` horizons in place this will happen. Detect it (CP-SAT returns INFEASIBLE), and either
   relax to a longer horizon and label it, or return "no feasible path within 18 months" plus the
   nearest partial progress. Never fall back to an unconstrained solve and present the result as if
   it were feasible.
5. **Rounding breaks validity.** Verified above with dice-ml. Any continuous-relaxation method needs
   a re-validation step: recompute `f(round(x'))` and reject if below τ. Solving in integers avoids
   the class of bug entirely.
6. **Multiplicity is hidden by default.** Many actions tie at the optimum; returning one implies it
   is *the* answer. Always return `k ≥ 3` and label them as alternatives.
7. **Extraction error propagates into the advice.** If the extractor missed a project, the advice is
   wrong in a way the candidate can see and resent. Show the extracted profile alongside the advice
   and offer a correction path. This doubles as compliance with Colorado SB 26-189's right to
   correct data.
8. **Cap-saturated features.** If `x_j` is already at `U_j` the feature cannot help, and if the
   scorer caps a feature's contribution, advice past the cap is worthless. Check saturation before
   emitting any message about a feature.
9. **Group-differential recourse cost.** Run the Gupta-style audit before demoing. If one group's
   mean cheapest-recourse cost is much higher, that is a finding worth presenting honestly rather
   than a bug to hide.
10. **Over-claiming.** The engine computes what would have flipped *this scorer*, not what would
    have got the person hired. Every output string should carry that distinction.

---

## Sources

- Ustun, Spangher & Liu, "Actionable Recourse in Linear Classification," FAT* 2019 —
  https://github.com/ustunb/actionable-recourse
- Mothilal, Sharma & Tan, DiCE — https://github.com/interpretml/DiCE ·
  https://pypi.org/pypi/dice-ml/json
- Pawelczyk et al., CARLA — https://github.com/carla-recourse/CARLA ·
  https://openreview.net/forum?id=vDilkBNNbx6
- Alibi — https://github.com/SeldonIO/alibi · licence:
  https://github.com/SeldonIO/alibi/blob/master/LICENSE
- OmniXAI counterfactual API —
  https://opensource.salesforce.com/OmniXAI/latest/omnixai.explainers.tabular.counterfactual.html
- InterpretML EBM — https://github.com/interpretml/interpret
- OR-Tools CP-SAT — https://github.com/google/or-tools · https://pypi.org/pypi/ortools/json
- Upadhyay, Joshi & Lakkaraju, ROAR, NeurIPS 2021
- Gupta et al., "Equalizing Recourse Across Groups," 2019
- Poyiadzi et al., FACE, AIES 2020
- Karimi, Schölkopf & Valera, "Algorithmic Recourse: From Counterfactual Explanations to
  Interventions," FAccT 2021
- Ahmed, Khotanlou, Tan, Abdelaal & Karimi, "RecourseBench: A Modular Framework for Reproducible
  Algorithmic Recourse Evaluation," arXiv:2606.16113 (June 2026; 27 recourse algorithms, five
  decoupled pipeline layers — worth checking for a public repo before the report is finalised)
