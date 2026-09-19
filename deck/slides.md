---
theme: seriph
background: https://images.unsplash.com/photo-1521737604893-d14cc237f11d?q=80&w=2400
title: HR AI Advisor — algorithmic recourse for CV screening
info: |
  ## HR AI Advisor
  AaltoAI Hackathon 2026 — Gleb Tretiakov, Vitalii Virronen, Ilya Zalesskii

  An open-source CV pre-screener that tells rejected candidates exactly what
  would have to change, and keeps the human in the loop.
class: text-center
drawings:
  persist: false
transition: slide-left
mdc: true
duration: 10min
---

# HR AI Advisor

Automated CV screening that **explains itself — to both sides**

<div class="pt-8 text-sm opacity-70">
Gleb Tretiakov · Vitalii Virronen · Ilya Zalesskii<br>
AaltoAI Hackathon 2026 — AI sovereignty, security & EU data law
</div>

<div class="abs-br m-6 text-sm opacity-60">
recourse.ilia.fi · open source
</div>

<!--
DRAFT DECK — built from deck/tmp.pdf. Numbers verified against the running backend
on 2026-09-19. Slides marked TODO need the team's input.

30 s: who we are, one sentence on what it does. Don't explain the architecture yet.
-->

---
layout: statement
---

# 250 applications. One afternoon.

<div class="text-xl opacity-80 mt-6">
Generative AI made applying free.<br>
It did not make <span class="text-teal-300">reading</span> free.
</div>

<!--
Motivation, section 2 of the doc. The asymmetry is the whole story:
cost of sending a CV went to ~zero, cost of reading one did not.
Consequence: employers buy filters, candidates get silence.
-->

---

# Two people are stuck

<div class="grid grid-cols-2 gap-8 pt-6">

<div>

### The HR manager

- Hundreds of CVs per opening
- No time to read them all properly
- Buys a black-box filter → now **legally exposed**
- Cannot answer "why was I rejected?"

</div>

<div>

### The applicant

- Sends 100 applications
- Gets silence, or "we moved forward with other candidates"
- Learns **nothing** — cannot improve, cannot contest
- Reapplies next year with the same CV

</div>

</div>

<div class="pt-10 text-center text-xl">
Every screening product on the market solves the first problem<br>
<span class="opacity-60">and treats the second as someone else's.</span>
</div>

<!--
This slide sets up the differentiator. Don't rush it — the judges need to feel
that the second column is a real, unserved problem.
-->

---
layout: statement
---

# Our bet

### Tell the rejected candidate<br>**exactly what would have changed the answer.**

<div class="pt-8 text-lg opacity-70">
"One more shipped microservice project would have been enough."
</div>

<div class="pt-6 text-sm opacity-50">
The technique is called <b>algorithmic recourse</b> — well studied in papers,<br>
almost absent from shipped hiring products.
</div>

<!--
Wachter, Mittelstadt & Russell (2017) — counterfactual explanations. The literature
is 8 years old; vendors ship "developmental tips" (HireVue) but nobody ships
actual threshold recourse. That gap is our project.
-->

---

# What we built

<div class="grid grid-cols-2 gap-8 pt-4">

<div>

**For HR** — a screening console
- Upload CVs, get a ranked shortlist
- Author the job as a **100-point budget**
- See which parts of the CV drove the score
- Approve or override every decision

</div>

<div>

**For the candidate** — an answer
- Up to **3 independent routes** back to a pass
- Each with a cost and a realistic timeline
- Drafted as an email the manager sends
- Never sent automatically

</div>

</div>

<div class="pt-8">

Open source · self-hostable · runs the whole demo with **no LLM key** if you want it to

</div>

<!--
Emphasise: the LLM is optional at demo time. Deterministic templates cover the whole
flow; the model only polishes prose. That matters for sovereignty and for judges
who ask "what if the API is down / the data can't leave the EU".
-->

---
layout: two-cols
layoutClass: gap-8
---

# The pipeline

<v-clicks>

**1 · Parse** — LLM reads the CV, emits a structured profile. Cached by content hash.

**2 · Score** — deterministic. Knockouts, then a 100-point budget.

**3 · Recourse** — CP-SAT solver finds the cheapest changes that flip the outcome.

**4 · Explain** — code-owned templates; LLM may rephrase, never invent.

**5 · Log** — hash-chained, append-only audit record per decision.

</v-clicks>

::right::

<div class="pt-16 text-sm font-mono leading-relaxed opacity-80">

```
CV (pdf/text)
     │  LLM #1
     ▼
  Profile  ─────► Score ──► pass ──► shortlist
  (JSON)            │
                    │ fail
                    ▼
              CP-SAT solver
                    │
                    ▼
              3 routes back
                    │  LLM #2 (optional)
                    ▼
              Candidate email
                    │
                    ▼
              Manager approves
```

</div>

<div class="absolute bottom-6 right-8 text-xs opacity-60">
The LLM appears <b>twice</b>. Everything between is deterministic and replayable.
</div>

<!--
The key architectural claim, and the one judges will probe: we did NOT ask a model
"should we hire this person". Scoring and recourse are arithmetic and integer
programming. The model only reads unstructured text and writes prose.
-->

---

# The job is a point budget

<div class="text-sm opacity-80 -mt-2">
HR authors it. The system enforces it. The column sums to <b>100</b>, so a score reads as a
percentage and the pass mark is a share of the job — not a magic number.
</div>

<div class="grid grid-cols-2 gap-8 pt-4 text-xs">

<div>

#### Hard requirements — knockouts
Fail one → rejected. No score traded off against it.

```yaml
skills.python.held == true
experience.software_months >= 12
education.highest_level >= bsc
```

</div>

<div>

#### Soft requirements — 100 points

| Criterion | Pts |
|---|---|
| Backend experience | 32 |
| Python | 16 |
| Kubernetes | 11 |
| Microservices projects | 10 |
| Cloud platform | 9 |
| Education level | 6 |
| CI/CD · Docker · IaC · SQL | 5·4·4·3 |

</div>

</div>

<!--
Real config from backend/recourse_screen/jobs/backend_engineer.yaml.
If asked why the numbers are 32/16/11/10/9/6/5/4/4/3: points must divide the
solver's step count exactly, so the editor snaps them server-side.
-->

---

# 4.1 · Score math

<div class="pt-2">

Each criterion has a **cap** — how many solver steps count as full marks — so one step is worth
`points // cap`, always an integer.

</div>

```python
score = Σ  min(steps(feature), cap) × (points // cap)
```

<div class="grid grid-cols-2 gap-8 pt-6">

<div>

**Mode A — fixed threshold**
Pass at **≥ 80 / 100**.
Absolute, stable, explainable.

</div>

<div>

**Mode B — top N of pool**
Pass if you are in the **top 3**.
The bar is the 3rd-best score — it *moves*.

</div>

</div>

<div class="pt-6 text-sm opacity-70">
Both modes ship. We show both on purpose — see slide "the uncomfortable finding".
</div>

<!--
Mode B bar is computed as the N-th best score among the other candidates (+1,
ties resolved pessimistically). No bootstrap, no capacity modelling — deliberately
simple, and we say so.
-->

---

# Recourse is an optimisation problem

Not a prompt.

<div class="pt-4 text-sm">

Given the candidate's profile, find the **cheapest set of changes** that crosses the bar:

</div>

<div class="grid grid-cols-3 gap-4 pt-6 text-sm">

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**Actionability**
Every feature is tagged `actionable`, `conditionally actionable` or `immutable`.
Immutable features are never in a route.

</div>

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**Cost & time**
Each step has a cost and a typical duration, from the job-family manifest — not invented per candidate.

</div>

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**Causal constraints**

<div class="font-mono text-xs py-2 leading-relaxed">
k8s ≤ docker<br>
Δmicro ≤ 2 + Δbackend_mo
</div>

You cannot be advised to fake a dependency.

</div>

</div>

<div class="pt-6 text-sm opacity-70">
CP-SAT returns up to <b>3 diverse routes</b>, each sufficient on its own, sparsity-penalised so
short routes win.
</div>

<!--
The two dependency rules are real, from the manifest. The first stops us saying
"learn Kubernetes" to someone with no Docker. The second stops "ship 5 microservices
next month" advice to someone with no backend time to ship them in.
-->

---

# Honesty rules, in code

<div class="text-base opacity-90 -mt-2">
The system must never claim the candidate lacks something it merely <b>didn't see</b>.
</div>

<div class="grid grid-cols-3 gap-5 pt-8 text-sm">

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

`stated` / `computed`

**→ instruction**

<div class="pt-2 italic opacity-80">"Add about 6 more months of professional software engineering experience."</div>

</div>

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

`denied`

**→ instruction that concedes**

<div class="pt-2 italic opacity-80">"Your CV said you do not have hands-on Kubernetes experience, so gaining it is one way to close this gap."</div>

</div>

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

`absent`

**→ question**

<div class="pt-2 italic opacity-80">"Your CV did not mention infrastructure-as-code — if you have it, add it and ask us to re-run the screen."</div>

</div>

</div>

<div class="pt-6 text-sm opacity-60">
Verbatim output from the running system.
</div>

<!--
This is the slide that separates us from "we asked GPT to write rejection feedback".
The distinction absent vs denied is enforced by template selection, not by a prompt.
-->

---

# Keeping the model on a leash

<div class="grid grid-cols-2 gap-8 pt-4">

<div>

### What the LLM writes
- One sentence per change
- That is all

### What code writes
- The framing and intro
- Ordering of routes
- Immutable-blocker disclosures
- The closing text

</div>

<div>

### What checks it
A **code-only checker** runs on every generated sentence:
- whitelist of facts it may mention
- no new numbers, no new features
- fails → fall back to the template

<div class="pt-4 text-sm opacity-70">
No LLM judges another LLM. No "as an AI language model" apology path.
</div>

</div>

</div>

<div class="pt-8 text-center text-sm opacity-70">
Every screening in this demo ran with <code>explain=false</code> — the deterministic path.
</div>

<!--
Practical consequence: the demo cannot be broken by a rate limit, a bad key, or a
model refusing. Judges love a demo that survives the venue wifi.
-->

---
layout: statement
---

# The uncomfortable finding

<div class="text-left max-w-3xl mx-auto pt-4">

Same candidate. Same CV. Same job.

</div>

<div class="grid grid-cols-2 gap-8 pt-6 text-left max-w-3xl mx-auto">

<div class="p-4 rounded bg-green-500 bg-opacity-10">

**Threshold mode** — bar 80, scored 75

One step:
- *one more microservices project*

<div class="pt-2 text-sm opacity-70">cost 6</div>

</div>

<div class="p-4 rounded bg-red-500 bg-opacity-10">

**Ranking mode** — bar 91, scored 75, ranked 5/10

Two steps, and the bar moves if others improve:
- *one more microservices project*
- *plus hands-on Kubernetes — ~4 months*

<div class="pt-2 text-sm opacity-70">cost 15</div>

</div>

</div>

<div class="pt-6 text-sm opacity-80 max-w-3xl mx-auto text-left">
Recourse is honest under a threshold. Under ranking it is a <b>moving target</b> — and we show that
rather than hide it.
</div>

<!--
This is the research contribution and the intellectually honest moment of the pitch.
Real numbers, candidate cv4. Mode B is the default in the UI precisely so the weakness
is visible, not buried.
-->

---

# 3 · Law compliance

<div class="text-sm pt-2">

Hiring AI is **high-risk under Annex III** of the EU AI Act. We designed to the strict reading.

</div>

<div class="grid grid-cols-2 gap-6 pt-4 text-sm">

<div>

**EU AI Act (2024/1689)**
Art. 86 — right to an explanation of an individual decision.
→ every decision carries its contributions, its routes and its config version.
<span class="opacity-60">High-risk duties deferred to 2 Dec 2027 (Digital Omnibus 2026/1744).</span>

**GDPR Art. 22**
No solely-automated decision with significant effect.
→ **the manager decides.** The system shortlists and drafts; a human sends.

</div>

<div>

**GDPR Art. 13–15** — "meaningful information about the logic involved."
→ the logic *is* the published point budget.

**Data minimisation**
→ protected attributes are never extracted into the profile; the model scores a
feature vector, not a person.

**NIS2 / sovereignty**
→ self-hostable, two containers, no third-party ATS.

</div>

</div>

<div class="pt-4 text-xs opacity-60">
TODO (team): decide how hard we claim compliance vs "designed toward". Framing it as
<b>developmental feedback</b>, not "the legal reason for rejection", is the safer posture.
</div>

<!--
Dates checked against research/algorithmic_recourse_and_counterfactual_explanations_in_hiring.md,
accurate as of Sept 2026. Do NOT say "we are compliant" on stage — say "we built to
the obligations that land in Dec 2027".
-->

---

# Every decision is replayable

<div class="pt-4">

An append-only, **hash-chained** log. Each record links to the previous one:

</div>

```
record_n.hash = sha256( record_{n-1}.hash + decision_id + timestamp + payload )
```

<div class="grid grid-cols-3 gap-6 pt-8 text-sm">

<div>

**What's stored**
profile hash, job version, scorer version, solver version, model id, the routes shown

</div>

<div>

**What it proves**
edit or delete one line and every hash after it breaks — `make audit` finds the first bad index

</div>

<div>

**Why it matters**
"show us how this candidate was screened, 14 months ago" has an answer

</div>

</div>

<!--
Also: re-screens after a candidate updates their CV link back to the parent decision,
so the chain shows the whole conversation, not just the last verdict.
-->

---

# 5 · The console

<div class="pt-2 text-sm opacity-80">
Three panels, left to right — the same order as the decision.
</div>

<div class="grid grid-cols-3 gap-4 pt-6 text-sm">

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**Uploaded CVs**
Ranked, best first. Score chip per candidate. Click to open the original PDF or the parsed profile.

</div>

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**Why this match?**
Hard requirements ticked off, matched requirements, gaps identified with point values. Switch to candidate view.

</div>

<div class="p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**Candidate email**
Pre-drafted from the routes. Edit, *Polish with Claude*, then **Send** or **Keep further** — the manager's call.

</div>

</div>

<div class="pt-8 p-4 rounded border border-dashed border-gray-500 text-center text-sm opacity-60">
TODO: drop a fresh screenshot in <code>deck/public/console.png</code> and uncomment the image below.<br>
The screenshot in tmp.pdf is stale (old 103-point scale) and shows a real CV — don't ship it.
</div>

<!--
<img src="/console.png" class="rounded shadow mt-4" />
-->

<!--
If the live demo works on stage, skip this slide entirely and just drive the UI.
Keep it as the fallback.
-->

---
layout: statement
---

# Demo

<div class="text-left max-w-xl mx-auto pt-6 text-base">

1. Open the pool — 10 candidates, ranked
2. Open **Aisha** — 75/100, rejected
3. Read the three routes
4. Flip **A → B** — watch the advice get more expensive
5. Open the email draft, polish it, *don't* send
6. Open the job editor — move Kubernetes from 11 pts to 0, re-screen

</div>

<div class="pt-8 text-sm opacity-60">
recourse.ilia.fi
</div>

<!--
Step 6 is the strongest moment: it makes visible that the employer's config,
not the model, is what rejected her. Rehearse the timing — the re-screen is instant
because explain=false.
-->

---

# What's real, what's demo

<div class="grid grid-cols-2 gap-8 pt-4 text-sm">

<div>

### Real
- LLM CV parsing with a content-hash cache
- Deterministic scorer, 100-point budget
- CP-SAT recourse with causal constraints
- Template + checker explanation layer
- Hash-chained audit log
- HR job editor with server-side budget snapping
- 17 test modules, synthetic eval harness

</div>

<div>

### Demo-scale, and we'll say so
- 10 candidates in the pool, one job family
- Ranking mode is deliberately simplified — the bar is just the N-th best score
- Costs and durations are hand-authored in the manifest, not learned
- No bias audit across groups yet
- No ATS integration

</div>

</div>

<!--
Judges reward the right-hand column. Say it before they ask.
-->

---

# Next

<div class="grid grid-cols-2 gap-8 pt-6">

<div>

**Near term**
- Recourse-cost fairness audit across groups
- More job families than backend engineering
- Candidate-side re-screen loop ("I added this — recheck me")

</div>

<div>

**The open question**
- Does telling people how to pass teach them to **improve** — or to **game**?
- Causal features and dependency constraints are our first answer.
- It needs real data to settle.

</div>

</div>

<!--
Ending on an honest open question beats ending on a roadmap. Invite the challenge.
-->

---
layout: center
class: text-center
---

# HR AI Advisor

Screening that can explain itself — to the manager **and** to the candidate

<div class="pt-8 text-sm opacity-70">
Gleb Tretiakov · Vitalii Virronen · Ilya Zalesskii
</div>

<div class="pt-4 text-sm opacity-60">
recourse.ilia.fi · open source · AaltoAI Hackathon 2026
</div>
