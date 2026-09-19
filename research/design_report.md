# Design Report: A Pre-Screening Demo with Algorithmic Recourse

Date: 2026-09-19. Status: groundwork for development, no code yet except a 64-line solver toy.

This report proposes a design for a hackathon / student-showcase demo of an automated hiring
pre-screener whose differentiating feature is algorithmic recourse: a rejected candidate is told
what minimal, concrete change to their profile would have carried them to the interview stage.
It consolidates the two background documents in this folder and three technical briefs in
`research/notes/`, and ends with a register of design decisions, a recommended stack, and a build
plan.

Scope as agreed:

- Purpose: hackathon / student showcase. Convincing end-to-end story over production hardening.
- Input: free-text CV, parsed by an LLM into a structured profile. Scoring and recourse run on the
  profile, never on the text.
- Decision: two switchable modes. Mode A is a fixed per-job threshold. Mode B is relative ranking,
  where the top N of a pool advance. The demo shows how advice weakens under mode B.
- Focus: the technical backend. UI is a separate effort; section 8 gives suggestions only.

Supporting documents:

| File | What it contains |
|---|---|
| `algorithmic_recourse_and_counterfactual_explanations_in_hiring.md` | Vendor landscape, regulation, papers table, critical analysis of why recourse is hard in hiring |
| `criteria_used_in_ai_hiring.md` | What criteria employers actually configure (knockouts, must-haves, weighted skills), funnel numbers, validity evidence |
| `notes/recourse_engine_brief.md` | MILP formulation, library evaluation (with installs and runs), constraint design, robustness, worked example |
| `notes/recourse_toy_cpsat.py` | Runnable CP-SAT solver for the worked example; output re-verified while writing this report |
| `notes/cv_parsing_and_llm_brief.md` | Profile schema and feature manifest, extraction pipeline, model choice and cost, taxonomy, synthetic data, explanation guardrails |
| `notes/ranking_mode_gaming_and_evaluation_brief.md` | Ranking-mode literature and design, gaming simulation, 18-metric evaluation protocol, cheap fairness guardrails |

---

## 1. The idea, and what it can honestly promise

The pitch is simple. Most rejected applicants hear nothing, or a template. Our screener tells them:
"you did not pass the automated screen for this role; two more backend projects and one more level
of SQL depth would have been enough on this date under this scoring version; here are three
alternative routes; if you already have any of these and left them off your CV, say so and we will
re-run the screen."

The background research is blunt about the limits, and the design must respect them rather than
paper over them:

1. **Recourse is only true when the decision is a replayable function of candidate-actionable
   features.** That rules out an LLM deciding pass/fail. The LLM reads the CV and later phrases the
   advice; a deterministic, interpretable scorer makes the decision. This one rule drives most of the
   architecture.
2. **Most real hiring bars are relative.** Mode B exists so the demo can show, rather than hide,
   what happens to advice when the bar is the N-th best applicant. The honest output in mode B is a
   rank estimate with a frequency over comparable pools, not "you would have got the interview".
3. **Recourse invites gaming.** Advice on proxy features (a keyword, a title string) is
   indistinguishable from an instruction to keyword-stuff, and it invalidates itself once the model
   is refitted (König et al., NeurIPS 2025). The solver may only act on features that represent real,
   ideally verifiable, capability.
4. **Missing is not absent.** CVs under-report. Telling someone to "learn Docker" when they use it
   daily destroys trust instantly. The profile must distinguish stated, absent and denied, and the
   cheapest recourse is often "restate what you already have".
5. **Some rejections have no cheap recourse.** Work authorisation, a licence that takes 18 months,
   an education level. The system must say "the binding constraint is X and it is not something a CV
   edit fixes", and route to human review, rather than invent a weighted-score path around a knockout.
6. **Framing matters legally and psychologically.** The output is developmental guidance about
   *this scorer on this date*, not "the reason you were rejected" and not a promise about hiring.
   Every explanation carries the model version, the as-of date, a non-guarantee, and a human-review
   route. This is the shape GDPR Article 22, EU AI Act Article 86 and Colorado SB 26-189 point at.

A demo that visibly honours these limits is more credible to a technical jury than one that
produces slick advice for every candidate.

---

## 2. Architecture

```
                 employer side                              candidate side
        ┌──────────────────────────┐                ┌──────────────────────────┐
        │ job template (YAML/JSON) │                │ CV (text / PDF)          │
        │  knockouts, weights, τ   │                └────────────┬─────────────┘
        │  or (N, M, conf) for B   │                             │
        │  feature manifest        │                   [LLM #1] extract  ──► evidence spans
        └────────────┬─────────────┘                             │        verified in code
                     │                              ┌────────────▼─────────────┐
                     │                              │ candidate_profile.json   │
                     │                              │ (value/derivation/       │
                     │                              │  confidence/evidence)    │
                     │                              └────────────┬─────────────┘
                     │            deterministic code             │
                     ▼                                           ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │  scorer: knockouts ∧ additive score        mode A: τ               │
        │                                            mode B: bar distribution │
        └────────────┬───────────────────────────────────────────────────────┘
                     │ pass ──► interview list
                     │ fail
                     ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │  recourse engine (CP-SAT MILP): k diverse min-cost actions         │
        │  constraints: actionable ∧ causal ∧ horizon ∧ dependencies ∧ margin │
        │  flip test: assert scorer(profile + action) passes                 │
        └────────────┬───────────────────────────────────────────────────────┘
                     │ structured deltas + immutable blockers + p(top-N)
                     ▼
          [LLM #2] verbalise one sentence per delta ──► checker chain ──► candidate text
                     │
                     ▼
        append-only audit log (hash-chained): versions, hashes, τ or bars, actions shown
```

Four architectural rules:

- **The LLM never touches the decision.** It appears exactly twice, at the ends. Everything between
  is deterministic and replayable, which is what makes the flip test possible and the recourse true.
- **Actionability is policy, not extraction output.** The feature manifest, not the LLM, says what
  is actionable, in which direction, at what step and cost. A model update must never be able to
  reclassify "requires visa sponsorship" as something to change.
- **One solver, two modes.** Mode B is a thin wrapper that replaces the scalar threshold with a
  bootstrapped distribution of the cutoff score and a capacity-aware target. Same solver, same
  tests, one code path.
- **Protected attributes are excluded three times**: from the extraction schema, from the scorer's
  accepted inputs, and from the solver's action set. Assert at each boundary.

---

## 3. Component design

### 3.1 Feature schema and feature manifest

Two artefacts (full JSON in the CV-parsing brief, section 1):

**Candidate profile**, one per CV. Every leaf value carries the same envelope:
`{value, derivation, confidence, evidence[]}` where `derivation ∈ {stated, computed, inferred,
absent, denied}` and each evidence item is a verbatim quote plus character offsets. Sections:
experience (roles with dates, per-role skills mentioned, computed totals), skills keyed by
taxonomy id (held, years, last used, proficiency, project count, dated flag), projects with topics,
education, certifications, languages, eligibility (work authorisation, location at region level,
relocation and onsite willingness, notice period). A `never_extract` list (name, birth date, age,
gender, photo, nationality, marital status, street address, postal code, health, religion) is
echoed back by the extractor and asserted absent by a scrubber. Postal code stops at region because
Illinois HB 3773 bars zip codes as proxies.

**Feature manifest**, one per job family, employer-editable, checked into the repo. For every field
path: actionability class, allowed direction, step unit and size, cost weight, plausible maximum
delta within the horizon, typical acquisition time in months, and the phrase the explanation may use.
Four actionability classes, each with distinct behaviour:

| Class | Solver may move it | Explanation | Examples |
|---|---|---|---|
| actionable | yes | instruction or question | framework knowledge, project count, certification |
| conditionally actionable | yes, with time cost shown | must state the time | years per skill, education level, CEFR level |
| immutable | no | must be named when it is the binding constraint, using fixed manifest text | work authorisation, total experience |
| protected_never_use | excluded from scorer entirely | never mentioned | graduation year, employment gaps, anything age- or disability-correlated |

Two further columns per feature: `is_causal` (the feature represents demonstrated capability, not
a proxy) and `provenance` level support (self-asserted, artefact-linked, third-party verified). The
solver may only act on causal features. Provenance discounts the weight at scoring time.

Cost weights are a value judgement, not a measurement (Barocas, Selbst and Raghavan 2020). Derive
them from typical acquisition time so the ordering is defensible, and show them in the employer
configuration so they are an auditable artefact.

### 3.2 CV extraction

Detailed in the CV-parsing brief, section 2. The design:

1. **Pass A, extract.** One structured-output call. System prompt holds instructions, the taxonomy
   as an enum, and the JSON schema; the CV goes last in a user turn inside delimiters with a standing
   instruction that delimited content is data. The model emits roles with dates and per-role skill
   mentions, never a years figure.
2. **Deterministic post-processing.** Date normalisation against a frozen `as_of` (never the wall
   clock), interval union per skill (not sum, because overlapping contracts are common), recency,
   primary-versus-listed skill depth, seniority laddering, taxonomy canonicalisation, the protected
   scrub, and evidence-span verification by exact substring match against the CV text. That last
   check is about ten lines and catches fabricated values immediately, because hallucinated skills
   rarely come with a quote that exists. Failed spans downgrade confidence; on knockout fields they
   drop the value to absent.
3. **Pass B, verify.** A narrow second call that sees the CV and the profile and returns only a list
   of disagreements with quotes. Disagreements on knockout fields route to human review.
4. **Selective self-consistency** on the two or three fields the eval shows to be unstable (usually
   seniority and proficiency), not on the whole extraction.

Gotcha found while researching: Claude's document citations feature would be the natural way to get
evidence spans, but it is incompatible with structured outputs and returns an error when combined.
Evidence spans therefore live in the schema as string fields and are verified in code.

**Prompt injection is measured, not hypothetical.** A USENIX Security 2026 study of about 196,000
real resumes found roughly 1% carried hidden injections, over 90% of them hidden keyword stuffing
rather than instruction attacks, and general-purpose detectors had under 10% recall. Mitigations in
order of value: compare the PDF text layer against an OCR of the rendered page and flag spans present
in only one; rely on the structure (schema-constrained output with verifiable quotes leaves an
injected instruction nowhere to land); never place CV text in the system prompt; flag for human
review rather than auto-reject, since a pasted job description and keyword stuffing are
indistinguishable at the string level.

**Model choice.** Claude Opus 5 for both LLM steps in the demo; the whole Opus-versus-Sonnet
difference across a 200-CV corpus is roughly twelve euros, and extraction here is multi-hop (scope
skills to roles, respect the enum, union overlapping intervals, distinguish absent from denied).
Rough cost per CV end to end: about $0.12 on Opus 5, about $0.05 on Sonnet 5. Sonnet 5 is the
legitimate production bulk-extractor choice, gated on an eval against the synthetic ground truth.
The explanation step stays on Opus 5 regardless: it is one short call per rejected candidate and the
only text a human reads.

### 3.3 Employer criteria and the scoring model

The criteria research shows what real configurations look like: a small set of binary knockouts
(work authorisation, location, required licence, minimum experience, availability), a must-have
list, and weighted nice-to-haves, with AI "fit scores" mostly advisory. The job template mirrors
that and nothing more exotic:

```yaml
job: backend_engineer_helsinki
family: software_engineering
manifest: manifests/software_engineering.json
knockouts:                      # hard, binary, job-related; keep to <= 5
  - eligibility.requires_sponsorship == false
  - skills.python.years >= 2
score:                          # additive, non-negative weights, over causal features
  skills.python.years:            {weight: 6, cap: 8}
  skills.django.years:            {weight: 4, cap: 5}
  project_counts_by_topic.backend:{weight: 5, cap: 6}
  certifications.aws_saa:         {weight: 7}
  skills.docker.held:             {weight: 6}
  skills.sql.proficiency:         {weight: 5}
  education.highest_level:        {weight: 4}
absent_prior: 0.0               # how an 'absent' (unstated) field scores; see 3.1
mode:
  A: {threshold: 60, margin: 6}
  B: {slots_N: 10, pool_size_M: 200, confidence: 0.8, uptake: 0.3, jitter: 0.03}
dependencies:
  - skills.django.years <= skills.python.years
  - project_counts_by_topic.backend_delta <= 2 + 2 * skills.python.years_delta
```

Design points:

- **Decision = knockouts AND additive score.** Keep the knockout conjunction outside the weighted
  sum. Folding a knockout in as a huge weight makes the solver propose "compensate for missing work
  authorisation with four side projects".
- **Additive, monotone, non-negative weights by default.** Kleinberg and Raghavan (EC 2019) show a
  linear mechanism suffices whenever any reasonable mechanism induces improvement rather than
  gaming; it is also the form the MILP handles natively. A monotone additive GAM (interpret's EBM
  with `interactions=0`, `monotone_constraints`) drops into the same MILP via per-bin lookup and is
  the "learned scorer" stretch goal if the demo wants to show one trained on synthetic outcomes.
- **Caps per feature** stop advice past the point where more of a feature buys nothing.
- **Absent scored as unverified, not zero.** The template sets a prior; the audit log records that
  it was applied.
- **Provenance-weighted scoring.** `w_effective = w · κ(provenance)` with κ roughly (0.5, 0.8, 1.0)
  for self-asserted, artefact-linked, verified. Gaming then costs real effort. Cheap and legible.
- **Do not train a ranker on past hiring decisions.** That is the Amazon failure mode and it
  produces an opaque bar. If a learned model is shown at all, it is the additive EBM above.

### 3.4 Recourse engine, threshold mode

Detailed in the recourse-engine brief. Given profile `x`, scorer `f`, threshold `τ`, return the `k`
cheapest feasible `x' = x + a` with `f(x') ≥ τ + ε` and all knockouts met.

**Formulation.** Integer program over one-hot step indicators `u_jk` (Ustun-style flipset
encoding), which allows arbitrary non-linear per-step costs: exactly one step per feature; flip
constraint against the precomputed score gap; domain bounds; horizon caps `Δ_j` (largest change
achievable in 18 months); one-directional actions (`a_j ≥ 0`); dependency constraints
(`x'_django ≤ x'_python`, a shared time budget `Σ t_j a_j ≤ T`, implications for side effects such as
"certification implies proficiency ≥ 2"); a sparsity tie-break penalty rather than a hard cap; and
support-disjoint diversity cuts (each new counterfactual must touch a feature no previous one
touched), which give three genuinely different stories where plain no-good cuts give near-duplicates.
For a 20-feature profile with `Δ_j ≤ 6` this is under 150 binaries and solves in milliseconds.

**Library decision: write it on OR-Tools CP-SAT, about 120 lines.** The alternatives were installed
and run, not judged from memory:

| Library | Verdict |
|---|---|
| actionable-recourse (Ustun) | Last commit October 2020; crashes on NumPy 2 in two places; pinning NumPy below 2 breaks pandas and scipy. Copy its `ActionSet` API design, do not depend on it |
| dice-ml 0.12 | Only maintained option, but on an integer profile it returned 7.8 projects, decreased a one-directional feature and ignored cost minimality. Its API offers immutability and box bounds only. Keep as a citable baseline showing why constraints are needed |
| alibi 0.9.6 | Business Source Licence 1.1; production use limited to non-commercial educational settings. A trap if the project continues |
| CARLA | Python 3.7 only, last commit 2023 |
| OR-Tools CP-SAT 9.15 | Apache-2.0, every constraint we need is native, exact optimality with proof |

**Robustness.** Solve against `τ + ε` with ε calibrated from extraction noise (resample the
extraction, set ε = 2σ of the score). Worst-case robustness over an L∞ ball of radius ρ around the
weights collapses, for non-negative features, to replacing each `w_j` by `w_j − ρ`; it is free in the
same MILP and worth stating on a slide.

**Worked example** (seven features, τ = 60, candidate scores 47; numbers re-run from
`notes/recourse_toy_cpsat.py` while writing this report):

| Configuration | Cheapest paths returned |
|---|---|
| ε = 0, support-disjoint diversity | +2 backend projects and +1 SQL level (cost 16); +2 backend projects and AWS certification (19); AWS certification and +2 SQL levels (21) |
| ε = 6 robust margin | +2 backend projects and +2 SQL levels (22); +2 projects, AWS cert, +1 SQL (25); +1 year Python and +3 projects (27) |

The solver never proposed an education level (cost 40 for 4 points, dominated) and never proposed
Docker (already held, domain bound). An early version of the toy that omitted the upper bound
happily told a Docker user to learn Docker. That is the single most likely bug to ship.

**Infeasibility is a real outcome** and must be reported as such: "no path within 18 months; here is
the nearest partial progress; here is the human-review route". Never fall back to an unconstrained
solve.

### 3.5 Ranking mode

Detailed in the ranking brief, part 1. The literature since 2023 treats this directly: recourse
under capacity (Fonseca et al. EAAMO 2023; Khotanlou, Larson and Karimi 2025), durable recourse in
competitive settings (Ceccon et al. 2025), strategic ranking (Liu, Garg and Borgs AISTATS 2022),
counterfactuals for "why am I not in the top K" (CREDENCE ICDE 2023; Chandna and Sen 2024), and
performative validity (König et al. NeurIPS 2025).

The design replaces the scalar threshold with a distribution and reuses the mode A solver:

1. **Bar distribution.** Bootstrap-resample pools of size M from historical (in the demo: synthetic
   archetype) scores, take the N-th order statistic of each, giving an empirical law of the cutoff
   even with few past requisitions.
2. **Robust quantile target.** `τ_rob = Quantile(bars, conf)` with conf = 0.8, employer-configurable
   and logged. Reading: reaching this score would have placed you inside the top N in about 80% of
   comparable pools.
3. **Capacity-aware ceiling.** Following Ceccon et al., do not push everyone to the last-seen cutoff,
   because too many can reach it and the realised bar moves. Bisect for the smallest score that stays
   scarce once an assumed uptake fraction of advised candidates acts. Publish `τ = max(τ_rob, τ_cap)`
   plus a small per-candidate jitter so advised candidates do not pile up at one point.
4. **Solve** with the threshold-mode solver against τ, then report for each action the empirical
   `P(top-N) = mean(score(x+a) ≥ bars)` and a rank interval (p10, median, p90).

Communication rules, enforced in the template layer: never a bare outcome claim; always rank plus
frequency ("top 10 in 8 of the last 10 comparable pools"); name the competition once, in aggregate
("10 of 180 advanced; 6 of them exceeded you on backend experience"); attach a validity window.
Expect the actionability rate (share of rejected candidates with a feasible path) to fall from
around 70% in mode A to roughly a third to a half in mode B. Report that honestly; it is the point
of having the mode.

Mode A is the same routine with the bar distribution collapsed to a point mass at τ, so `P(top-N)`
is trivially 0 or 1. Build it as one code path.

### 3.6 Explanation generation

Detailed in the CV-parsing brief, section 5. LLM #2 sees a whitelisted object only: outcome, the
deltas (field, from, to, unit, derivation of the current value, candidate phrase, typical time,
actionability), immutable blockers, the flip-test flag, as-of date, model version, and in mode B the
rank and frequency figures. Not the CV, not the weights, not other candidates.

Structure is pinned by the output schema, not by instructions: an array with exactly one
`{delta_id, sentence}` per input delta, so extra claims are impossible by construction. Code owns
the intro, ordering, disclosures and closing, and selects the template by derivation: absent yields a
question ("if you have worked with Kubernetes, add it and ask us to re-run"), stated yields an
instruction, immutable yields the manifest's fixed disclosure text verbatim.

Checker chain before anything is shown: coverage and injectivity of delta ids; numeric containment
(every numeral in the text must appear in the input); banned comparative and causal lexicon ("better
candidates", "you were not qualified"); protected-term scan; a one-call entailment judge; and the
flip-test flag. On failure: one regeneration, then the code-generated fallback text. Never loop,
never ship unchecked output.

Disclose: automated screen; one sufficient path among others, not a guarantee; time realism; as-of
date and model version; that requirements and pools change; and the human-review route. Do not
disclose weights, the exact threshold, or anything about other applicants beyond the aggregate line.

**The restatement channel** is the feature that turns a rejection letter into a product: the
candidate confirms absent-but-plausible skills (surfaced first via a co-occurrence prior, labelled
zero-cost: "you probably already have this, it is missing from the page") and the scorer re-runs.
One API call, and it doubles as the right-to-correct-data route.

### 3.7 Gaming simulation

The demo should not merely assert that recourse invites gaming; it should run it. Ranking brief,
part 2:

- 200 agents per round with latent quality `q`, causal features driven by `q`, and proxy features
  correlated with them. Additive scorer, top 10 advance, 20 rounds, retrain every 5 rounds on
  admitted-cohort outcomes only (selective labels, which is realistic).
- Agent types: improver (acts on causal features, quality rises, slow, costly), gamer (cheapest
  proxy edit, quality unchanged, instant), inert. Sweep the gamer share over 0, 0.3, 0.6.
- Three levers: disclosure = all features versus causal only; provenance verification on or off;
  cooldown on or off.
- Plot per round: Spearman(score, quality) as validity drift; mean quality of the admitted cohort;
  recourse validity retained (advised agents who implemented and were admitted within 3 rounds); bar
  drift versus advised τ; proxy weight share after retraining.

Expected contrast: under all-features disclosure with 30% gamers, validity and retained recourse
collapse within about ten rounds while the model's in-sample accuracy still looks fine; under
causal-only disclosure, validity holds and cohort quality rises above the no-recourse baseline
because improvers actually improved. That is the strongest single slide available to this project.

### 3.8 Evaluation harness

Everything is computable on synthetic data with ground-truth profiles. The ranking brief, part 3,
defines 18 metrics with demo targets; the ones that matter most:

| Metric | Definition | Demo target |
|---|---|---|
| Recourse validity (A) | share of returned actions with `f(x+a) ≥ τ` | 100% (solver soundness) |
| Rank validity (B) | `P(top-N)` against the bootstrap ensemble, per advice | at least 0.75 empirically |
| Validity under refit | re-issue nothing; replay stored advice against a refitted or perturbed scorer | at least 0.80 retained; invalidation at most 0.20 under 10% weight noise |
| Sparsity and plausibility | features changed; distance of `x'` to its 5 nearest real profiles | L0 at most 3; normalised yNN at most 1.5 |
| Actionability rate | rejected candidates with at least one feasible causal path within horizon | A at least 0.70; B reported honestly |
| Recourse-cost disparity | ratio of median cost between best- and worst-off synthetic groups (Gupta et al.) | at most 1.25; flag above 1.5 |
| Parser accuracy | micro-F1 on skills, MAE in months on years fields, exact match on categoricals, hallucination rate | F1 at least 0.85; MAE under 6 months; hallucination at most 2% |
| Explanation faithfulness | re-parse the text into a delta struct with a separate model and compare to solver output | at least 0.98 agreement |
| Adverse impact ratio | lowest group pass rate over highest, per run, both modes | at least 0.80, logged every run |

Protocol notes: refit and perturbation validity must be computed on advice already issued and
stored, not on freshly re-solved advice. Report parser recall separately for skills present in the
text and skills deliberately omitted from the rendered CV; the second number will be low, and that
is the finding that motivates the restatement channel.

**Synthetic data, profile-first.** Sample the ground-truth profile in pure Python (seniority, role
count, month intervals with deliberate overlaps, skills via the co-occurrence prior, education,
certifications, eligibility), then render CV text with Claude under one hard rule: never state a
derived value. Vary style aggressively and inject flagged hard cases: 30% skill under-reporting,
overlapping contracts, year-only dates, synonym-only mentions, five hidden-text injections. Hold out
ResumeExtractBench (38 documents, CC BY 4.0) as the human-written check, because a generator and an
extractor from the same model family flatter each other. Avoid real-resume corpora for anything but
style reference: GDPR, and they lack derived ground truth.

**Job families: software engineering and registered nurse.** Software engineering because skills
are granular and actionable and the jury can judge the advice. Nursing because its rejections are
dominated by licence knockouts and slow-moving or immutable features, so it exercises the "no cheap
recourse, here is the human-review route" branch. A system that says so is more credible than two
flavours of "learn one more framework".

### 3.9 Guardrails and audit log

All cheap, all demonstrable (ranking brief, part 4):

- Protected-feature exclusion asserted at three boundaries.
- Proxy checks on the recommendations, not only the model: correlation of recommended deltas with
  synthetic group; a throwaway classifier predicting group from the action vector must stay at or
  below AUC 0.60.
- Four-fifths rule on pass rates per synthetic group per run, surfaced on the dashboard, with the
  note that it is a rule of thumb and not a safe harbour.
- Per-decision append-only, hash-chained audit record: mode, model, criteria, cost-model, solver and
  prompt versions; profile and CV hashes; τ or (N, M, conf, uptake, jitter seed); score; decision;
  actions shown with `P(top-N)`; explanation hash; assertion results; impact ratio at decision time.
  Ten lines of code, and it is the concrete answer to "what would an auditor ask for".

---

## 4. Design decision register

| # | Decision | Options considered | Recommendation | Why | Revisit if |
|---|---|---|---|---|---|
| D1 | Where the LLM sits | LLM decides; LLM scores a rubric; LLM only at the ends | **Only at the ends** (extract, verbalise) | Replayable decision, flip test possible, injection-resistant by structure, auditable | Never for the decision path |
| D2 | Scorer form | additive linear; monotone additive GAM/EBM; tree ensemble; learned ranker on past hires | **Additive linear with knockouts outside the sum**; EBM with `interactions=0` as stretch | MILP-native, induces improvement over gaming (Kleinberg and Raghavan), matches real configs | Employer wants interactions: 2-D one-hot encoding is exact but larger |
| D3 | Recourse solver | dice-ml; actionable-recourse; alibi; custom MILP on CP-SAT; custom on PuLP/HiGHS | **Custom, OR-Tools CP-SAT** | Only option that expresses integrality, direction, horizon, dependencies, diversity; provable minimality; Apache-2.0; verified alternatives fail | Feature space becomes continuous and high-dimensional |
| D4 | Diversity | no-good cuts; support-disjoint cuts; DiCE joint objective | **Support-disjoint cuts, k = 3** | Distinct stories, no measurable cost | Employer wants many paths: joint objective |
| D5 | Robustness | none; margin ε; ROAR L∞ ball; retrain ensembles | **Margin from extraction noise plus L∞ weight shrink** | Both free in the same MILP; demonstrable trade-off | Scorer becomes non-linear |
| D6 | Causal handling | none; hand-authored dependency graph; estimated SCM | **Hand-authored per job template, stated as such** | Honest, small, linear constraints; an estimated SCM would be fabricated at demo scale | Real data with interventions exists |
| D7 | Cost model | per-step constants; percentile shift; group-normalised | **Employer-authored constants derived from acquisition time; percentile shift once pool data exists; group cost as audit metric** | Transparent, arguable, visible as configuration | Applicant distribution becomes available |
| D8 | Ranking-mode bar | N-th score of this pool; historical mean; **bootstrap distribution + robust quantile + capacity cap** | The latter | Last-seen cutoff is the baseline Ceccon et al. show fails; leaks pool | Pool history too small even for resampling |
| D9 | Mode B communication | outcome claim; probability; **rank + frequency + aggregate competition + validity window** | The latter | Honest and readable | Never a bare outcome claim |
| D10 | Action set | all scored features; **causal, verifiable features only** | The latter | Performative validity (König et al.); manipulation indistinguishable from improvement otherwise | Never |
| D11 | Profile schema | flat vector; **enveloped values with derivation and evidence, plus separate manifest** | The latter | Missing-is-not-absent, auditability, policy separated from extraction | None |
| D12 | Handling absent fields | score as zero; **score at a prior, phrase as question, restatement channel** | The latter | Under-reporting is the dominant extraction error; trust | None |
| D13 | Extraction model | Opus 5; Sonnet 5; Haiku 4.5 | **Opus 5 for the demo; Sonnet 5 for production bulk after eval** | Cost difference trivial at demo scale; multi-hop extraction; explanation step stays on Opus | Eval shows Sonnet 5 holds knockout accuracy and years MAE |
| D14 | Evidence spans | citations feature; **schema string fields verified by substring match** | The latter | Citations are incompatible with structured outputs | API changes |
| D15 | Skill taxonomy | ESCO; O*NET; Lightcast; **hand-curated 200 to 400 concepts with ESCO URIs, enum in schema** | The latter | Lightcast gated since April 2026; enum makes out-of-taxonomy output impossible; embeddings only for triaging the unmatched backlog | Coverage complaints: add local sentence-transformer matching |
| D16 | Demo data | real resume corpora; CV-first synthetic; **profile-first synthetic plus ResumeExtractBench hold-out** | The latter | Exact derived ground truth; no personal data; adversarial variants by design | None |
| D17 | Job families | one; **software engineering plus registered nurse** | Two, with contrast | Nursing exercises immutable and slow paths honestly | Time: drop nursing to a scripted example |
| D18 | Explanation control | free generation; **schema-pinned one sentence per delta plus checker chain plus code-owned framing** | The latter | Extra claims impossible by construction; legal exposure sits here | None |
| D19 | Protected attributes | frozen at solve time; **absent from schema, scorer and action set, asserted thrice** | The latter | Freezing still shifts the intercept and yields group-dependent recourse cost | None |
| D20 | Infeasible recourse | relax silently; **report "no path within horizon", show partial progress and human-review route** | The latter | Ustun et al.: classifiers can deny recourse; honesty is the differentiator | None |
| D21 | Gaming defences | none; **causal-only disclosure, magnitude buckets not coefficients, provenance discount, cooldown** | All four, shown in the simulation | Cheap, legible, theoretically grounded | None |
| D22 | Audit log | none; database rows; **append-only hash-chained JSONL** | The latter | Ten lines; replay for evaluation; auditor-ready | None |

---

## 5. Stack and repository layout

Python 3.12, one package, no framework beyond what the UI effort needs.

| Concern | Choice |
|---|---|
| Solver | `ortools` (CP-SAT), Apache-2.0 |
| Optional learned scorer | `interpret` (EBM, monotone, `interactions=0`) |
| LLM | Anthropic SDK, structured outputs via `output_config.format`, prompt caching on the schema-plus-taxonomy prefix, Batch API for eval sweeps |
| Schemas | JSON Schema files for profile, manifest, job template, explanation; `pydantic` for validation |
| Data and eval | `numpy`, `pandas`, `scikit-learn` for the simulation and metrics |
| Taxonomy triage | local `sentence-transformers` over canonical labels (offline) |
| Serving | `fastapi` with a handful of endpoints (score, recourse, restate, simulate, audit) for the separate UI effort |
| Storage | JSONL audit log, JSON profiles on disk; no database needed for a demo |

Suggested layout:

```
recourse_screen/
  schemas/        profile.schema.json, manifest.schema.json, job.schema.json, explanation.schema.json
  taxonomy/       swe-core-0.x.json, nursing-core-0.x.json (with ESCO URIs and aliases)
  manifests/      software_engineering.json, nursing.json
  jobs/           backend_engineer_helsinki.yaml, rn_ward_nurse.yaml
  extract/        prompts, extractor client, postprocess (dates, union, canonicalise, spans, scrub), verify pass
  score/          job template loader, knockouts, additive scorer, provenance discount, absent prior
  recourse/       cpsat_solver, constraints, diversity, robustness, threshold_mode, ranking_mode
  explain/        input whitelist, templates, verbaliser client, checker chain, fallback text
  synth/          profile sampler, CV renderer, adversarial variants
  sim/            strategic agents, retraining loop, plots
  eval/           metrics, replay from audit log, fairness audits
  audit/          hash-chained JSONL writer
  api/            fastapi app
```

---

## 6. Build plan

Ordered so that each stage is demoable on its own and the risky parts come first.

1. **Schemas, manifest, deterministic post-processor** (half a day). Date math, interval union,
   taxonomy lookup, span verification, protected scrub. No LLM. Unit tests on hand-written role
   lists.
2. **Job template loader and scorer** (half a day). Knockouts, additive score, caps, absent prior,
   provenance discount. Tests on hand-written profiles.
3. **CP-SAT recourse solver, threshold mode** (one day). Port the toy, add the manifest-driven
   domains, dependencies, sparsity penalty, support-disjoint cuts, margin, infeasibility handling,
   flip test. Reproduce the worked example as a test.
4. **Audit log** (an hour). Written from here on so the evaluation harness has data to replay.
5. **Taxonomy and synthetic generator** (one day). 200 to 400 concepts per family; profile sampler;
   Claude renderer with the never-state-derived-values rule and flagged adversarial variants; 200 CVs.
6. **Extractor** (one day). Opus 5, structured outputs, cached prefix, verify pass. Measure against
   synthetic ground truth and ResumeExtractBench. Report present-versus-omitted recall separately.
7. **Explanation step** (one day). Whitelisted input, schema-pinned output, checker chain, fallback
   text, restatement channel endpoint.
8. **Ranking mode** (half a day). Bar distribution, robust quantile, capacity-aware bisection,
   jitter, `P(top-N)` and rank intervals, template rules.
9. **Gaming simulation and evaluation harness** (one to two days). Three levers, five curves,
   the metric table, fairness audits.
10. **Stretch**: EBM scorer through the same MILP; PDF text-layer-versus-OCR injection detector;
    fixed-point bar iteration plotted live; FACE-style plausibility paths.

**Suggested demo storyline.** One software-engineering job, 200 synthetic applicants. Show a
rejected candidate: extracted profile with evidence highlighted, the three routes with costs and
times, one route phrased as a question because the skill was absent from the CV, the candidate
confirming it, the screen re-running and passing. Toggle to mode B for the same candidate: the same
routes now read "top 10 in 8 of 10 comparable pools", one route drops out, and the aggregate
competition line appears. Switch to the nursing job: the binding constraint is the licence, the
system says so and offers human review instead of a fake path. Close with the twenty-round
simulation: two curves, causal-only disclosure holding and all-features disclosure collapsing.

---

## 7. What the UI effort needs from the backend, and suggestions

Backend contract, so the UI can be built in parallel:

- `POST /screen` with CV text or PDF and a job id returns the profile (with evidence offsets), the
  decision, and, on rejection, the ordered advice list with per-route cost, typical time, derivation
  of the current value, `P(top-N)` and rank interval in mode B, immutable blockers, and the checked
  explanation text with its disclosures.
- `POST /restate` with confirmed fields re-runs scoring and recourse.
- `POST /simulate` with lever settings streams per-round metrics.
- `GET /audit/{decision_id}` returns the full record.

Suggestions only, since the UI is a separate effort:

- Show the extracted profile next to the advice with the CV quotes highlighted. Candidates forgive
  a wrong parse they can see and fix; they do not forgive invisible ones.
- Present routes as cards ("build", "certify", "deepen") with cost and time, not as a single
  counterfactual; the IUI 2025 hiring study found single counterfactuals can underperform ranked
  reason codes when the system does not know the candidate's constraints.
- Render absent-field advice visibly differently from stated-field advice (question versus step).
- In mode B, put the frequency and the aggregate competition line above the routes, and show the
  validity window.
- Employer view: knockouts, weights, caps, cost weights and the mode dial are all editable and all
  visible, because they are the audit artefact. Include the four-fifths and recourse-cost-disparity
  readouts next to them.
- The simulation is a chart with a lever panel; it should be runnable live.

---

## 8. Risks and open questions

- **Extraction recall on omitted skills will be low.** This is expected and is the argument for
  the restatement channel, but it needs to be framed as a finding, not hidden.
- **Cost weights are contestable.** Every recourse ordering depends on them. Keep them
  employer-authored, visible and versioned; say plainly that they are a value judgement.
- **Mode B actionability will disappoint.** Roughly a third to a half of rejected candidates will
  have a feasible path. Show it; it is the honest number and the reason mode A is preferred where
  a real threshold exists.
- **Selective labels in the simulation.** Retraining on admitted cohorts only is realistic but makes
  the retrained scorer drift even without gaming; separate the two effects in the plots.
- **Legal framing.** Even as a demo, every output string should say it is guidance about this
  scorer on this date, not the reason for rejection and not a hiring promise. The background
  research explains why explanations become discoverable evidence.
- **Two unverified items** from the briefs: the licence of the Kaggle livecareer resume set, and
  the PN-R@K metric definition attributed to the RecSys 2025 "Beyond Top-1" paper (reported from
  secondary sources). Neither is on the critical path.
- **Open**: whether the demo should include a learned EBM scorer at all, or stay with the
  employer-authored additive scorer. Recommendation: employer-authored first; the EBM only if there
  is time, and only through the same MILP.

---

## 9. Key sources

Full citation lists with URLs are in the three briefs and the two background documents. The ones
this design leans on most:

- Ustun, Spangher and Liu, "Actionable Recourse in Linear Classification", FAT* 2019.
- Mothilal, Sharma and Tan, DiCE, FAT* 2020 (used as baseline, not as product path).
- Karimi, Schölkopf and Valera, "Algorithmic Recourse: From Counterfactual Explanations to Interventions", FAccT 2021.
- Upadhyay, Joshi and Lakkaraju, ROAR, NeurIPS 2021.
- Gupta, Nokhiz, Roy and Venkatasubramanian, "Equalizing Recourse Across Groups", 2019.
- Barocas, Selbst and Raghavan, "The Hidden Assumptions Behind Counterfactual Explanations and Principal Reasons", FAT* 2020.
- Kleinberg and Raghavan, "How Do Classifiers Induce Agents to Invest Effort Strategically?", EC 2019.
- Liu, Garg and Borgs, "Strategic Ranking", AISTATS 2022.
- Fonseca et al., "Setting the Right Expectations: Algorithmic Recourse Over Time", EAAMO 2023.
- Ceccon et al., "Reinforcement Learning for Durable Algorithmic Recourse", arXiv 2509.22102.
- König, Fokkema, Freiesleben, Mendler-Dünner and von Luxburg, "Performative Validity of Recourse Explanations", NeurIPS 2025.
- Zhang et al., "Measuring Real-World Prompt Injection Attacks in LLM-based Resume Screening", USENIX Security 2026.
- "Counterfactual Explanations May Not Be the Best Algorithmic Recourse Approach", IUI 2025.
- OR-Tools CP-SAT; InterpretML EBM; ESCO v1.2.1; Careerflow/ResumeExtractBench.
