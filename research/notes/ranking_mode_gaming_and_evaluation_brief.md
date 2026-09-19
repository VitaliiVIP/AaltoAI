# Ranking-Mode Recourse, Gaming, and Evaluation — Implementation Brief

Companion to `research/algorithmic_recourse_and_counterfactual_explanations_in_hiring.md`.
That document establishes the problem and the threshold-mode (mode A) literature. This one covers
what is missing for the demo: recourse when only the top N advance (mode B), a gaming simulation,
an evaluation protocol with concrete targets, and cheap fairness guardrails.

Date: 2026-09-19. All citations verified by retrieval; URLs inline.

---

## Part 1 — Recourse under relative / ranking decisions (mode B)

### 1.1 What the literature actually offers

The Part 3(d) objection in the main document — that threshold recourse is fictional when the bar is
relative — is not merely a critique. Since roughly 2023 it has become its own research line, and the
line is now mature enough to implement from. Three clusters matter.

**Cluster 1: recourse under capacity constraints and competition.** This is the direct match.

- **Fonseca, Bell, Abrate, Bonchi & Stoyanovich, "Setting the Right Expectations: Algorithmic Recourse
  Over Time" (EAAMO 2023)** — <https://arxiv.org/abs/2309.06969>, <https://dl.acm.org/doi/10.1145/3617694.3623251>.
  Simulation study of recourse reliability in a multi-agent, resource-constrained environment. Isolates
  two effects that erode recourse: *other agents acting on their own recommendations*, and *new agents
  entering the pool*. Conclusion relevant to us: recourse offered without a time and pool qualifier sets
  expectations it cannot meet. This is the paper to cite for "the advice has a shelf life".
- **Khotanlou, Larson & Karimi, "Your Recourse, My Loss? Algorithmic Recourse under Shared Constraints"
  (arXiv 2508.11070, Aug 2025, rev. May 2026)** — <https://arxiv.org/abs/2508.11070>. Formalises
  many-seekers/many-providers recourse as a **capacitated weighted bipartite matching** problem with three
  layers: matching under capacity, capacity allocation, and cost-aware optimisation. Key result for us:
  individually optimal recourse is not jointly realisable once capacity binds, and concave social-welfare
  objectives let you prioritise disadvantaged seekers while staying near the welfare optimum.
- **Ceccon, Fabris, Radanović, Biega & Susto, "Reinforcement Learning for Durable Algorithmic Recourse"
  (arXiv 2509.22102, Sept 2025, rev. Feb 2026)** — <https://arxiv.org/abs/2509.22102>. The single most
  useful paper for mode B. It shows that the standard move — *push the rejected candidate to the
  last-seen decision threshold* — is the wrong baseline in a competitive setting, because too many
  candidates can reach an easy target and the realised bar moves past them. Their fix is to
  **anticipate the population-level response and pick a target score that only a subset can reach**,
  so that those who reach it are actually accepted. Their mechanism is RL over a time horizon; we do not
  need RL, but we should steal the target-selection principle wholesale (see 1.2).
- **Yang & Zhu, "Actionable Recourse in Competitive Environments: A Dynamic Game of Endogenous Selection"
  (arXiv 2603.17907, Mar 2026)** — <https://arxiv.org/abs/2603.17907>. Game-theoretic treatment of
  recourse-for-everyone: rejected candidates improve while the selection threshold co-evolves. Cite for
  the equilibrium framing of the performative loop.

**Cluster 2: strategic behaviour specifically under ranking / fixed slots.**

- **Liu, Garg & Borgs, "Strategic Ranking" (AISTATS 2022, PMLR v151)** —
  <https://proceedings.mlr.press/v151/liu22b/liu22b.pdf>. Introduces strategic *ranking* for constrained
  allocation (college admissions is their running example), where an individual's payoff depends on their
  post-effort **rank**, not on crossing an absolute bar. Shows that competition induced by the mechanism
  changes optimal effort in ways strategic-classification models miss entirely. This is the theoretical
  backbone for mode B gaming, and the one citation the report must not omit.

**Cluster 3: counterfactual explanations for ranked outputs.** Mostly information retrieval and
recommendation, but the machinery transfers because "why am I not in the top K" is the same question.

- **Rorseth, Godfrey, Golab, Kargar, Srivastava & Szlichta, "CREDENCE: Counterfactual Explanations for
  Document Ranking" (ICDE 2023 demo)** — <https://arxiv.org/abs/2302.04983>. Four explanation types:
  document perturbations, query perturbations, other documents, and user-defined perturbations. The
  "other documents" type maps directly onto our honest answer: *the reason you are out is partly who else
  applied.*
- **Chandna & Sen, "A Counterfactual Explanation Framework for Retrieval Models"
  (arXiv 2409.00860, Sept 2024, rev. Apr 2026)** — <https://arxiv.org/abs/2409.00860>. Explicitly flips
  the question to *why is this document **not** in the top K*, and treats the answer as a set of missing
  terms to add. Evaluated across BM25, DRMM, DSSM, ColBERT, MonoT5. The CV analogue is almost literal:
  which missing skills, if added, lift the profile into the top N.
- **"From Top-1 to Top-K: A Reproducibility Study and Benchmarking of Counterfactual Explanations for
  Recommender Systems" (arXiv 2604.19663, 2026)** — <https://arxiv.org/abs/2604.19663>. Benchmarks
  top-K counterfactual explainers on effectiveness, sparsity and computational cost, and reports that
  lower-ranked items are systematically easier to perturb than higher-ranked ones. Read that as: recourse
  for a candidate near the cut is cheap and recourse for a candidate far below it is not, and the demo
  should say so.
- **"Beyond Top-1: Addressing Inconsistencies in Evaluating Counterfactual Explanations for Recommender
  Systems" (RecSys 2025)** — <https://dl.acm.org/doi/10.1145/3705328.3748028>. Argues top-1 evaluation of
  ranking counterfactuals is misleading and proposes a position-aware list-level metric, PN-R@K, that
  weights displacement at higher ranks more heavily. Directly informs our mode-B metric choice.
  *(Verify the PN-R@K definition against the primary text before quoting it in the report; it is
  reported here from secondary sources.)*

**Cluster 4: performativity, which is what makes mode B unstable.**

- **König, Fokkema, Freiesleben, Mendler-Dünner & von Luxburg, "Performative Validity of Recourse
  Explanations" (NeurIPS 2025)** — <https://arxiv.org/abs/2506.15366>. The sharpest result available:
  when many applicants act on recommendations and the model is refitted, the recourse algorithm can
  **invalidate its own recommendations**. They characterise when validity survives, and the condition is
  clean — recourse that intervenes on or is influenced by **non-causal** variables is the part that
  breaks. Recommend actions on causal variables only. This supersedes the vaguer "Fokkema et al. 2024,
  recourse vs. manipulation" entry in the main document; the related Fokkema, de Heide & van Erven
  impossibility result is **"Attribution-based Explanations that Provide Recourse Cannot be Robust"
  (JMLR 24(360), 2023)** — <https://jmlr.org/papers/v24/23-0042.html>.

### 1.2 Design: how to define the effective bar

Do **not** use "the score of the N-th candidate in this pool". That is the baseline Ceccon et al. show
fails, and it also leaks the pool. Use a three-step construction.

**Step 1 — build a bar distribution, not a bar.** Pool the scores of all historically screened applicants
for the job family (or, in the demo, for the synthetic generator's job archetype). Bootstrap-resample
pools of the requisition's expected size M and take the N-th order statistic of each. That yields an
empirical distribution of the cutoff score `B = {b_1 ... b_K}` even when you only have three or four real
past requisitions, because the resampling is over candidates, not over requisitions. Smooth with a small
additive jitter if M is large relative to the history.

**Step 2 — pick a robust quantile, not the mean.** The advice target is
`tau_rob = Quantile(B, conf)` with `conf = 0.8`. Reading: *reaching this score would have put you inside
the top N in about 80% of comparable pools.* The confidence level is an employer-configurable dial and
should be surfaced in the audit log, because it is the single parameter that decides how honest the
advice is.

**Step 3 — impose a capacity-aware ceiling.** This is the Ceccon et al. principle. Let `uptake` be the
assumed fraction of advised candidates who implement the advice, and `budget_i` each candidate's
plausible effort budget. Define

```
reachable(b) = #{ i in rejected pool : min_cost_to_reach(i, b) <= budget_i }
expected_above(b) = M * (1 - F_pool(b)) + uptake * reachable(b)
```

`expected_above` is decreasing in `b`, so bisect for the smallest `b` with `expected_above(b) <= N`. Call
it `tau_cap`. The published target is `tau = max(tau_rob, tau_cap)`. The `tau_cap` term is what stops the
demo from handing out advice that is individually cheap and collectively worthless.

### 1.3 Design: how to communicate that the advice is pool-conditional

Three rules, all enforced in the template layer rather than left to the language model.

1. **Never state a bare counterfactual in mode B.** The sentence form is *"in a typical pool for this
   role, this change would have placed you around rank R"*, not *"this change would have got you an
   interview"*. Rank, not outcome.
2. **Always attach the frequency.** Report `P(top-N)` computed directly against the bootstrap ensemble:
   *"this change would have put you in the top 10 in 8 of the last 10 comparable pools."* This is the
   empirical win rate `mean(s_new >= B)`, which costs one vectorised comparison. It is an interval in
   spirit and a frequency in presentation, which reads better than a confidence interval to a non-expert.
3. **Name the competition explicitly, once.** Borrowing CREDENCE's "other documents" explanation type:
   *"Ten of the 180 applicants advanced. Six of them exceeded you on [dimension]."* Aggregate only, never
   identifiable, and only over the pool that actually existed.

Also attach a **validity window** (Fonseca et al.): *"this estimate is based on pools from the last 12
months and should be treated as stale after 6 months."*

### 1.4 Design: handling the performative effect

Four concrete measures, in increasing order of ambition. Implement the first three for the demo.

- **Capacity-aware target** (`tau_cap`, above). Handles first-order uptake.
- **Causal-only action set.** Following König et al., partition features into `causal` (a skill actually
  demonstrated, a shipped project, a passed certification) and `proxy` (a keyword's presence, a title
  string, a buzzword count). The recourse solver may only propose actions on `causal` features. Proxies
  may still feed the score, but they are never recommended. This is the single highest-value line of code
  in the whole design: it is what keeps advice valid after refit, and it is what makes the advice honest
  advice rather than an instruction to keyword-stuff.
- **Target jitter.** Publish `tau + eps` with `eps ~ Uniform(0, delta)` per candidate, `delta` about 3% of
  the score range. Keeps a population of advised candidates from piling up at exactly one point, which is
  what makes the bar jump discontinuously, and incidentally degrades the value of pooling advice across
  candidates to reverse-engineer the weights.
- **Fixed-point bar (stretch).** Iterate: compute `tau`, simulate uptake, recompute the realised bar,
  recompute `tau`. Two or three iterations suffice in practice and it is a nice thing to show live in the
  demo, because you can plot the bar converging.

### 1.5 Pseudocode

The whole point of the construction is that mode B is a thin wrapper over mode A's solver.

```python
# ---------- mode A: unchanged, already implemented ----------------------------
def solve_threshold_recourse(x, score, tau, actionable, cost, k=3):
    """Up to k diverse minimum-cost actions a with score(x + a) >= tau.
    MILP flipsets (Ustun et al. 2019) for the linear/monotone employer scorer;
    DiCE for any black-box fallback. `actionable` is the causal-feature allowlist."""
    ...
    return actions            # list of sparse dicts {feature: delta}


# ---------- mode B: bar distribution -------------------------------------------
def bar_distribution(history_scores, M, N, K=2000, rng=None):
    """Empirical law of the cutoff score for a pool of size M admitting N."""
    bars = np.empty(K)
    for k in range(K):
        pool = rng.choice(history_scores, size=M, replace=True)
        bars[k] = np.partition(pool, -N)[-N]        # N-th largest = the bar
    return np.sort(bars)


def capacity_aware_target(rejected, score, cost, budgets, F_pool, M, N, uptake):
    """Smallest target that stays scarce once `uptake` of the advised act on it."""
    def expected_above(b):
        reachable = sum(
            1 for i, x in enumerate(rejected)
            if min_cost_to_reach(x, score, b, cost) <= budgets[i]
        )
        return M * (1 - F_pool(b)) + uptake * reachable
    return bisect_smallest(expected_above, target=N, lo=score_min, hi=score_max)


# ---------- mode B: the recourse routine ---------------------------------------
def rank_mode_recourse(x, pool, history_scores, score, cost, actionable,
                       M, N, conf=0.80, uptake=0.30, jitter=0.03, k=3, rng=None):
    bars    = bar_distribution(history_scores, M, N, rng=rng)
    tau_rob = np.quantile(bars, conf)
    tau_cap = capacity_aware_target(pool.rejected, score, cost, pool.budgets,
                                    pool.ecdf, M, N, uptake)
    tau     = max(tau_rob, tau_cap) + rng.uniform(0, jitter * score_range)

    actions = solve_threshold_recourse(x, score, tau, actionable, cost, k=k)
    if not actions:
        return NoFeasibleRecourse(tau=tau, bars=bars)   # say so; do not fake it

    out = []
    for a in actions:
        s_new  = score(apply(x, a))
        p_topN = float(np.mean(s_new >= bars))          # "in 8 of 10 pools"
        ranks  = [1 + int(np.sum(rng.choice(history_scores, M, replace=True) > s_new))
                  for _ in range(500)]
        out.append(Advice(
            action        = a,
            target_score  = tau,
            p_topN        = p_topN,
            rank_p10      = np.percentile(ranks, 10),
            rank_median   = np.median(ranks),
            rank_p90      = np.percentile(ranks, 90),
            cost          = cost(a),
            pool_note     = f"{N} of {len(pool)} advanced in the pool you were in",
            valid_until   = today() + timedelta(days=180),
        ))
    return sorted(out, key=lambda z: (-z.p_topN, z.cost))
```

Mode A is the same call with `bars` replaced by a degenerate point mass at the employer's threshold,
which means one code path, one set of tests, and a `p_topN` that is trivially 0 or 1 in mode A. Build it
that way.

---

## Part 2 — Gaming and strategic behaviour: a simulation to ship with the demo

The demo should not merely assert that recourse invites gaming. It should run a twenty-round simulation
on stage and plot the screener falling apart.

### 2.1 Foundations to cite

Beyond Hardt, Megiddo, Papadimitriou & Wootters (ITCS 2016), Perdomo et al. (ICML 2020) and Tsirtsis &
Gomez-Rodriguez (NeurIPS 2020, <https://proceedings.neurips.cc/paper/2020/hash/c2ba1bc54b239208cb37b901c0d3b363-Abstract.html>;
extended as "Optimal Decision Making Under Strategic Behavior", *Management Science* 2024,
<https://pubsonline.informs.org/doi/10.1287/mnsc.2021.02567>), add:

- **Kleinberg & Raghavan, "How Do Classifiers Induce Agents to Invest Effort Strategically?" (EC 2019,
  pp. 825–844)** — <https://arxiv.org/abs/1807.05307>. Characterises exactly when a mechanism induces
  *improvement* rather than *gaming*, and shows a simple linear mechanism suffices whenever any
  reasonable one does. This is the design justification for keeping the employer scorer linear and
  interpretable rather than reaching for an ensemble.
- **Liu, Garg & Borgs, "Strategic Ranking" (AISTATS 2022)** — the ranking version, as above.
- **König et al., "Performative Validity of Recourse Explanations" (NeurIPS 2025)** — the causal-variable
  condition, as above. This is the paper whose prediction the simulation is designed to reproduce.
- **Zhang, Jia, Tan, Jiang, Gong, Chen & Song, "Measuring Real-World Prompt Injection Attacks in
  LLM-based Resume Screening" (USENIX Security 2026)** — <https://arxiv.org/abs/2605.28999>. Roughly
  200,000 real resumes from hireEZ; **about 1% contain hidden prompt injections**, prevalence rising over
  the last one to two years, and **over 90% of injected prompts avoid explicit instructions**. This is
  gold for the demo: an empirical base rate for the most extreme gaming strategy against exactly our
  architecture (free-text CV into an LLM extractor). Pair with the defence work,
  "ResumeShield: Channel Separation and an Open Benchmark for Indirect Prompt Injection in AI Resume
  Screening" (<https://arxiv.org/abs/2609.20188>).

### 2.2 The simulation

**Agents.** `M = 200` per round. Each agent `i` has latent quality `q_i ~ N(0,1)`, a causal feature vector
`c_i` with `c_i = g(q_i) + noise`, and a proxy vector `p_i` (keyword counts, title strings) correlated
with `c_i` but not caused by `q_i`. Score `s = w_c . c + w_p . p`. Top `N = 10` advance.

**Types.** Each agent draws a type: **improver** (applies the action to causal features, `q_i` rises,
cost high, takes 1–3 rounds), **gamer** (applies the cheapest edit that moves the score, always a proxy,
`q_i` unchanged, cost near zero, takes 0 rounds), **inert**. Sweep `P(gamer)` over `{0, 0.3, 0.6}`.

**Loop.** Each round: score the pool, admit the top `N`, generate recourse for the rejected, agents act
by type, a fraction re-enter next round alongside fresh arrivals, and every `R = 5` rounds retrain the
screener on hired-cohort outcomes only. The selective-labels bias is realistic and worth showing: the
model only ever learns from people it admitted.

**Arms.** Three binary levers, so eight cells, or three one-at-a-time comparisons for a short demo:
disclosure = `all-features` vs `causal-only`; verification = `off` vs `on`; cooldown = `off` vs `on`.

**Measured each round.**

- **Screener validity drift**: `Spearman(s, q)` on the full pool. The headline curve.
- **Realised cohort quality**: `mean(q | admitted)`. The thing the employer actually loses.
- **Recourse validity retained**: of agents advised in round `t` who implemented the advice, the fraction
  admitted by round `t + 3`. This is the number that operationalises König et al.
- **Bar drift**: the realised cutoff score over rounds, plotted against the advised `tau`.
- **Proxy weight share**: `||w_p|| / (||w_c|| + ||w_p||)` after each retrain. Shows the model migrating
  onto the gameable features.

Expected and demonstrable result: under `all-features` disclosure with 30% gamers, validity correlation
decays and recourse validity retained collapses within about ten rounds, while realised cohort quality
falls even though the screener's own accuracy on its training distribution looks fine. Under
`causal-only`, validity holds and cohort quality **rises** above the no-recourse baseline, because
improvers actually improved. That contrast is the demo's strongest single slide.

### 2.3 Design levers to implement and show

1. **Causal-feature targeting.** Two-column feature registry: `is_causal` and `is_verifiable`. The solver
   may only act on `is_causal`. Non-negotiable.
2. **Disclosure granularity.** Publish direction and a magnitude *bucket* ("roughly one more year of
   production Python", "one shipped project using Kubernetes"), never the coefficient, never the exact
   `tau`. Tsirtsis & Gomez-Rodriguez frame this as choosing which counterfactual set to publish; their
   objective is submodular, so a greedy `(1 - 1/e)` selection is available if you want to be principled
   about which subset to reveal.
3. **Verification of claimed changes.** Each feature carries a provenance level: self-asserted, artefact-
   linked (repo, portfolio URL, credential ID), or third-party verified. Score with a discount,
   `w_effective = w * kappa(provenance)` with `kappa` about `(0.5, 0.8, 1.0)`. Gaming then costs real
   effort, which is exactly Kleinberg & Raghavan's condition for inducing improvement over gaming. Cheap
   to implement and highly legible in a demo.
4. **Cooldown periods.** Advice carries `valid_until` and a `reapply_after` date matched to the plausible
   acquisition time of the recommended change. Prevents the same-week resubmission loop and gives the
   Fonseca et al. temporal caveat teeth.
5. **Injection hygiene at extraction.** Strip zero-width characters, white/zero-size text, comments and
   document metadata before the text reaches the model; keep CV text in a data channel separate from the
   instruction channel; run a canary check for instruction-like spans. Given a 1% real-world base rate,
   include five injected CVs in the demo corpus and show them being caught.

---

## Part 3 — Evaluation protocol

Everything below is computable on synthetic data with ground-truth profiles, which is what the demo has.
Generate a corpus of `n = 1000` synthetic profiles with known feature vectors, render each to free-text CV
prose with a generator model, and keep the ground-truth vector. That gives supervision for the parser and
a clean `q` for the simulation.

| # | Metric | Definition / how to compute | Demo target |
|---|---|---|---|
| 1 | **Recourse validity (mode A)** | Fraction of returned actions `a` with `score(x + a) >= tau`. Pure solver soundness check. | 100% |
| 2 | **Rank validity (mode B)** | `P(top-N) = mean(score(x+a) >= bars)` over the 2000-sample bootstrap ensemble; report per advice. | >= `conf` (0.80) by construction; verify empirically >= 0.75 |
| 3 | **Validity under retraining (ROAR-style)** | Refit the scorer on a resampled/shifted training set (drop 10%, add one simulated gamed cohort); recompute validity of previously issued advice. Upadhyay, Joshi & Lakkaraju (NeurIPS 2021). | >= 0.80 retained |
| 4 | **Validity under model perturbation (PROBE-style)** | Perturb weights `w + N(0, (0.1|w|)^2)`, 200 draws; report the invalidation rate. Pawelczyk et al., ICLR 2023, <https://arxiv.org/abs/2203.06768>. | invalidation <= 0.20 |
| 5 | **Proximity / cost** | Mean and median normalised `L1` cost of the chosen action in employer-defined effort units. | median <= 1.0 effort-year equivalent |
| 6 | **Sparsity** | `L0` — number of features changed. Also CARLA's *redundancy* (changes removable without flipping). | `L0 <= 3`; redundancy 0 |
| 7 | **Plausibility** | CARLA's `yNN`: mean `L2` from the counterfactual profile to its 5 nearest real profiles, normalised by the median nearest-neighbour distance within the corpus. <https://arxiv.org/abs/2108.00783> | <= 1.5 |
| 8 | **Diversity** | Mean pairwise distance among the `k = 3` returned actions, plus Jaccard distance over changed-feature sets. | >= 2 distinct feature sets of 3 |
| 9 | **Actionability rate** | Fraction of rejected candidates with >= 1 feasible action within budget and within the causal allowlist. Report separately per mode. | mode A >= 0.70; mode B reported honestly, expect 0.35–0.55 |
| 10 | **Recourse-cost disparity** | Ratio of median recourse cost between best- and worst-off synthetic groups (Gupta, Nokhiz, Roy & Venkatasubramanian, arXiv 1909.03166, <https://arxiv.org/abs/1909.03166>). Also the causal version: re-run cost under counterfactual group membership (von Kügelgen et al., AAAI 2022). | ratio <= 1.25; flag above 1.5 |
| 11 | **Parser extraction accuracy** | Against ground truth: micro-F1 on set-valued fields (skills, tools), MAE on numeric fields (years per skill), exact match on categorical. | skills F1 >= 0.85; years MAE <= 0.5; categorical >= 0.95 |
| 12 | **Parser hallucination rate** | Fraction of extracted skills absent from the ground-truth vector *and* unsupported by any CV span. | <= 0.02 |
| 13 | **Injection robustness** | Fraction of injected CVs (inject 5% of the corpus, styles per Zhang et al.) that change the admit/reject decision. | 0 after sanitisation; report pre/post |
| 14 | **Explanation faithfulness** | Re-parse the verbalised explanation back into an action struct with a separate model; require exact agreement on feature, direction and magnitude bucket with the solver output. Mismatch blocks send. | >= 0.98 agreement |
| 15 | **Screener validity drift** (simulation) | Drop in `Spearman(s, q)` over 20 rounds, per arm. | `causal-only` arm: drop <= 0.05 |
| 16 | **Recourse validity retained** (simulation) | Of advised agents who implemented, fraction admitted within 3 rounds. | `causal-only` >= 0.60; report `all-features` for contrast |
| 17 | **Adverse impact ratio** | Lowest group pass rate / highest group pass rate, per round, both modes. | >= 0.80 (four-fifths), logged every run |
| 18 | **Latency** | p95 end-to-end per candidate: extraction + score + solve + verbalise. | < 3 s |

Two protocol notes. First, for mode B use **position-aware** evaluation rather than a binary flip, per the
RecSys 2025 "Beyond Top-1" critique and the Top-1-to-Top-K reproducibility study: report the rank
distribution (`p10`, median, `p90`), not only `P(top-N)`. Second, metrics 3 and 4 must be computed on
advice *already issued*, not on freshly re-solved advice, or they measure nothing. Persist every issued
action and replay it. For a standardised harness, `RecourseBench` (Ahmed, Khotanlou, Tan, Abdelaal &
Karimi, arXiv 2606.16113, <https://arxiv.org/abs/2606.16113>) decomposes the pipeline into Data,
Preprocessing, Model, Recourse Method and Evaluation layers and ships 27 algorithms; it is a reasonable
skeleton to copy even if we do not adopt it.

---

## Part 4 — Cheap fairness and legal guardrails worth showing

Four items, all a day's work or less, all demonstrable.

**Protected-feature exclusion, enforced three times.** Once in the extractor's output schema (the LLM is
never asked for age, gender, nationality, name-derived ethnicity, postcode), once in the scorer's accepted
input keys, and once in the solver's action set. Assert at each boundary and fail loudly. Three checks
rather than one, because the demo's whole risk is a protected attribute sneaking in through free text.

**Proxy checks on the recommendations, not only on the model.** For each feature, compute `|corr(feature,
group)|` on the synthetic corpus, and separately `corr(recommended delta, group)`. The second is the one
people forget: a model can be clean while the *advice* is systematically different by group. Then train a
throwaway logistic regression to predict group membership from the recommended action vector; require
AUC <= 0.60. Flag any feature above 0.2 correlation in the audit view.

**Four-fifths rule on pass rates.** Compute the impact ratio per synthetic group per run, in both modes,
and surface it on the dashboard. Note in the report, per EEOC's (since withdrawn) 2023 guidance, that
four-fifths is a rule of thumb and not a safe harbour.

**Per-decision audit log, append-only and hash-chained.** One record per decision:

```
decision_id, timestamp, mode (A|B), model_version, criteria_version, cost_model_version,
solver_version, prompt_version, profile_hash (sha256 of canonical extracted JSON),
raw_cv_hash, tau (or N, M, conf, uptake, jitter_seed), bar_bootstrap_seed,
score, decision, actions_shown (JSON), p_topN per action, explanation_text_hash,
protected_exclusion_assert_passed, impact_ratio_at_decision_time, reviewer_id (if any)
```

Hash-chain consecutive records so the log is tamper-evident. This is ten lines of code, it is the concrete
answer to "what would an auditor ask for", and it maps onto the EU AI Act Article 86 explanation right and
Colorado SB 26-189's 30-day adverse-decision explanation without any additional work.

---

## What to build first

1. Feature registry with `is_causal` / `is_verifiable` / `is_protected` columns. Everything else depends on it.
2. `solve_threshold_recourse` with the MILP flipset, and `bar_distribution` + `rank_mode_recourse` as the
   thin wrapper. One code path for both modes.
3. The audit log record, written from day one so the evaluation harness has data to replay.
4. The twenty-round simulation with the three levers. It is the differentiator: most demos show recourse
   working, almost none show it eating itself.
