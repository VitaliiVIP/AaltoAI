---
theme: seriph
background: https://images.unsplash.com/photo-1521737604893-d14cc237f11d?q=80&w=2400
title: Recourse — an automated HR advisor
info: |
  ## Recourse — an automated HR advisor
  AaltoAI Hackathon 2026 — Gleb Tretiakov, Vitalii Virronen, Ilia Zalesskii

  An open-source CV pre-screener that tells rejected candidates exactly what
  would have to change, and keeps the human in the loop.
class: text-center
drawings:
  persist: false
transition: slide-left
mdc: true
duration: 10min
---

# Recourse

<div class="text-2xl pt-1">An automated HR advisor</div>

<div class="pt-3 text-lg opacity-85">CV screening that <b>explains itself — to both sides</b></div>

<div class="pt-8 text-sm opacity-70">
Gleb Tretiakov · Vitalii Virronen · Ilia Zalesskii<br>
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

<div class="mt-8 p-4 rounded border border-gray-400 border-opacity-40 bg-gray-400 bg-opacity-5">

**The problem, in EU AI Act terms.** AI that screens or ranks job applicants is a
**high-risk system** (Reg. 2024/1689, Annex III). Whoever deploys one must keep a human
in charge of the decision, log every decision so it can be audited, and explain each
one to the person affected.

<div class="pt-1 text-sm opacity-70">
A black-box filter delivers none of the three — and every rejection it issues is a decision it cannot account for.
</div>

</div>

<!--
This slide sets up the differentiator. Don't rush it — the judges need to feel
that the second column is a real, unserved problem.

The box is the legal framing of the same two problems: Annex III 4(a) puts
recruitment/selection AI in the high-risk class. Human oversight (Art. 14),
record-keeping (Art. 12), explanation of individual decisions (Art. 86).
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

<div class="relative -mt-2" style="height: 440px">

<!-- Screenshot, built up piece by piece: top bar, then the three panels.
     Each piece is the same image clipped to one region, so nothing has to be cropped.
     The seriph content area is ~870px wide: 500px screenshot + 16px gap + 354px notes. -->
<div class="absolute" style="left: 0; top: 0; width: 500px; aspect-ratio: 1280 / 798">
  <img v-click="1" src="/console.jpg" class="console-piece" style="clip-path: inset(0 0 91.5% 0)" />
  <img v-click="2" src="/console.jpg" class="console-piece" style="clip-path: inset(8.5% 71% 1.5% 0.8%)" />
  <img v-click="3" src="/console.jpg" class="console-piece" style="clip-path: inset(8.5% 30.2% 1.5% 29%)" />
  <img v-click="4" src="/console.jpg" class="console-piece" style="clip-path: inset(8.5% 0.8% 1.5% 69.8%)" />
</div>

<!-- One note per piece, appearing with it -->
<div class="absolute text-xs leading-snug" style="left: 516px; top: 0; width: 354px">

<div v-click="1" class="console-note">
<b>Top bar</b> — the job being hired for, and the bar to clear: the <b>top N of the pool</b> advance
(N = 3 here). Settings open the job editor and the audit log.
</div>

<div v-click="2" class="console-note">
<b>Uploaded CVs</b> — drop in CVs, get a ranked shortlist. Each candidate carries a score out of
<b>100</b>; the job is authored as a 100-point budget, so the score reads as a percentage.
</div>

<div v-click="3" class="console-note">
<b>Why this match?</b> — hard requirements ticked off, matched requirements, and the gaps with their
point values. Shows which parts of the CV drove the score. Approve or override every decision.
</div>

<div v-click="4" class="console-note">
<b>Candidate email</b> — up to <b>3 independent routes</b> back to a pass, each with a cost and a
realistic timeline, pre-drafted from the solver's output. The manager edits and sends. Never sent automatically.
</div>

</div>

<!-- The pipeline, laid out horizontally under the screenshot -->
<div v-click="5" class="absolute left-0 right-0" style="top: 324px">

<div class="flex items-stretch gap-2 text-xs">

<div class="pipeline-step">
<div class="pipeline-num">1 · Parse</div>
LLM reads the CV, emits a structured profile. Cached by content hash.
</div>
<div class="pipeline-arrow">→</div>
<div class="pipeline-step">
<div class="pipeline-num">2 · Score</div>
Deterministic. Knockouts first, then the 100-point budget.
</div>
<div class="pipeline-arrow">→</div>
<div class="pipeline-step">
<div class="pipeline-num">3 · Recourse</div>
CP-SAT solver finds the cheapest changes that flip the outcome.
</div>
<div class="pipeline-arrow">→</div>
<div class="pipeline-step">
<div class="pipeline-num">4 · Explain</div>
Code-owned templates; the LLM may rephrase, never invent.
</div>
<div class="pipeline-arrow">→</div>
<div class="pipeline-step">
<div class="pipeline-num">5 · Log</div>
Hash-chained, append-only audit record per decision.
</div>

</div>

<div class="pt-1.5 text-xs opacity-60 text-center">
The LLM appears <b>twice</b> (steps 1 and 4); everything between is deterministic and replayable.
Open source · self-hostable · runs the whole demo with <b>no LLM key</b>.
</div>

</div>

</div>

<style>
.console-piece {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border-radius: 6px;
  transition: opacity 0.45s ease, transform 0.45s ease;
}
.console-piece.slidev-vclick-hidden {
  transform: translateY(10px);
}
.console-note {
  padding: 0.45rem 0.6rem;
  margin-bottom: 0.4rem;
  border-radius: 6px;
  border: 1px solid rgba(156, 163, 175, 0.4);
  background: rgba(156, 163, 175, 0.06);
  transition: opacity 0.45s ease, transform 0.45s ease;
}
.console-note.slidev-vclick-hidden {
  transform: translateX(10px);
}
.pipeline-step {
  flex: 1 1 0;
  padding: 0.4rem 0.55rem;
  border-radius: 6px;
  border: 1px solid rgba(156, 163, 175, 0.4);
  background: rgba(156, 163, 175, 0.06);
  line-height: 1.25;
}
.pipeline-num {
  font-weight: 700;
  margin-bottom: 0.15rem;
}
.pipeline-arrow {
  align-self: center;
  opacity: 0.5;
}
</style>

<!--
Build the console one piece at a time, left to right — the same order as the decision.
Top bar (mode), CVs (rank), Why this match (score), Candidate email (recourse).

Then the pipeline. The key architectural claim, and the one judges will probe: we did
NOT ask a model "should we hire this person". Scoring and recourse are arithmetic and
integer programming. The model only reads unstructured text and writes prose.

Emphasise: the LLM is optional at demo time. Deterministic templates cover the whole
flow; the model only polishes prose. That matters for sovereignty and for judges
who ask "what if the API is down / the data can't leave the EU".

The screenshot is the synthetic candidate Priya Sharma (61/100, not advanced) —
no real CV in the deck.
-->

---

# The job is a point budget

<div class="text-sm opacity-80 -mt-2">
HR authors it. The system enforces it. The column sums to <b>100</b>, so a score reads as a
percentage and every candidate in the pool is measured on the same scale.
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

# Law compliance

<div class="text-sm pt-2">

Hiring AI is **high-risk under Annex III** of the EU AI Act. We designed to the strict reading.

</div>

<div class="grid grid-cols-2 gap-6 pt-4 text-sm">

<div>

**EU AI Act (2024/1689)**
Art. 86 — right to an explanation of an individual decision.
→ every decision carries its contributions, its routes and its config version.

Art. 12 — record-keeping: the system must **log** its decisions.
→ an append-only, **hash-chained** audit log. Each record stores the profile hash, job version,
scorer and solver versions, model id and the routes shown; `make audit` verifies the chain.
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

Logging: record_n.hash = sha256(record_{n-1}.hash + decision_id + timestamp + payload).
Edit or delete one line and every hash after it breaks — `make audit` finds the first bad
index. "Show us how this candidate was screened, 14 months ago" has an answer. Re-screens
after a candidate updates their CV link back to the parent decision.
-->

---
layout: statement
---

# Demo

<div class="text-left max-w-xl mx-auto pt-6 text-base">

1. Open the pool — 10 candidates, ranked
2. Open **Aisha** — 75/100, rejected
3. Read the three routes
4. Open the email draft, polish it, *don't* send
5. Open the job editor — move Kubernetes from 11 pts to 0, re-screen

</div>

<div class="pt-8 text-sm opacity-60">
recourse.ilia.fi
</div>

<!--
Step 5 is the strongest moment: it makes visible that the employer's config,
not the model, is what rejected her. Rehearse the timing — the re-screen is instant
because explain=false.
-->

---
layout: center
class: text-center
---

# Recourse

<div class="text-2xl pt-1">An automated HR advisor</div>

<div class="pt-3 text-lg opacity-85">Screening that can explain itself — to the manager <b>and</b> to the candidate</div>

<div class="pt-8 text-sm opacity-70">
Gleb Tretiakov · Vitalii Virronen · Ilia Zalesskii
</div>

<div class="pt-4 text-sm opacity-60">
recourse.ilia.fi · open source · AaltoAI Hackathon 2026
</div>

---
layout: section
---

# Appendix

<div class="text-base opacity-70">
Score math · Honesty rules · Keeping the model on a leash
</div>

---

# Score math

<div class="pt-2">

Each criterion has a **cap** — how many solver steps count as full marks — so one step is worth
`points // cap`, always an integer.

</div>

```python
score = Σ  min(steps(feature), cap) × (points // cap)
```

<div class="pt-6">

**The bar — top N of the pool**
A candidate advances if they are in the **top 3**. The bar to beat is the 3rd-best score in the pool,
so recourse is computed against the actual competition, not a fixed number.

</div>

<div class="pt-6 text-sm opacity-70">
Every route the solver returns is enough to clear that bar on its own, given the rest of the pool
as it stands today.
</div>

<!--
The bar is computed as the N-th best score among the other candidates (+1,
ties resolved pessimistically). No bootstrap, no capacity modelling — deliberately
simple, and we say so.
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
