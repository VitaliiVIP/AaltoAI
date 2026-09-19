# CV Parsing, Feature Schema, and the Two LLM Touchpoints

Design brief for the recourse-based pre-screening demo. Written 2026-09-19.
Scope: the free-text CV -> structured profile step, the delta -> plain-language explanation step,
skill normalisation, and demo data. Not the scoring model or the counterfactual solver.

---

## 0. The one architectural rule

The LLM appears exactly twice, at the two ends of the pipeline, and **never touches the decision**:

```
CV text ──[LLM #1: extract]──> candidate_profile.json ──[code: scoring]──> pass/fail + score
                                        │
                                        └──> [code: solver] ──> delta set ──[LLM #2: verbalise]──> text
```

Everything in the middle is deterministic code. This is not stylistic: it is what makes the
system auditable under the EU AI Act's high-risk regime and what makes the recourse *true*. If an
LLM sits anywhere on the decision path, you cannot promise a candidate that the stated change
would actually have flipped the outcome, because you cannot replay the decision. With the split
above you can: re-run the scorer on `profile + delta` and assert it passes. Do that assertion in
code on every explanation you emit. Call it the **flip test** and never ship an explanation that
fails it.

A second consequence: the recourse metadata (actionability, direction, step size, cost weight)
is **employer policy, not extraction output**. It lives in a static feature manifest checked into
the repo, keyed by field path. The LLM must never emit an actionability tag. If it did, a model
update could silently reclassify "requires visa sponsorship" from immutable to actionable and the
system would start telling people to change their nationality.

---

## 1. The feature schema

Two files. A **feature manifest** (static, one per job family, employer-editable) and a
**candidate profile** (per CV, produced by LLM #1 plus deterministic post-processing).

### 1.1 Candidate profile

Every leaf value is wrapped in the same envelope so the solver and the auditor can treat all
fields uniformly.

```jsonc
{
  "schema_version": "1.0",
  "job_family": "software_engineering",
  "as_of": "2026-09-19",                 // all date math is relative to this, never to now()
  "provenance": {
    "cv_sha256": "…",
    "extractor_model": "claude-opus-5",
    "prompt_version": "extract-v7",
    "taxonomy_version": "swe-core-0.3",
    "extracted_at": "2026-09-19T11:02:14Z"
  },

  // ---- envelope shape, used by every field below ----
  // {
  //   "value":       <typed, or null>,
  //   "derivation":  "stated" | "computed" | "inferred" | "absent" | "denied",
  //   "confidence":  "high" | "medium" | "low",
  //   "evidence":    [{ "quote": "<verbatim substring of the CV>",
  //                     "start": 1043, "end": 1102, "section": "experience[1]" }]
  // }

  "experience": {
    "total_years":        { "value": 6.4,  "derivation": "computed", "confidence": "high",
                            "evidence": [] },          // computed fields cite their inputs by path
    "relevant_years":     { "value": 4.1,  "derivation": "computed", "confidence": "medium", "evidence": [] },
    "seniority":          { "value": "mid", "derivation": "inferred", "confidence": "medium",
                            "evidence": [{ "quote": "Senior Backend Engineer", "start": 220, "end": 245,
                                           "section": "experience[0].title" }] },
    "roles": [
      {
        "title_raw": "Senior Backend Engineer",
        "title_canonical": "backend_engineer",
        "employer": "Acme Oy",
        "start": "2022-03", "end": "present",
        "date_precision": "month",
        "months": 42,
        "employment_type": "full_time",
        "skills_mentioned": ["python", "postgresql", "kubernetes"],
        "primary_skills": ["python"],        // in the title or the first two bullets
        "evidence": [{ "quote": "Mar 2022 – Present", "start": 246, "end": 264, "section": "experience[0]" }]
      }
    ],
    "num_roles":          { "value": 3, "derivation": "computed", "confidence": "high", "evidence": [] },
    "avg_tenure_months":  { "value": 25, "derivation": "computed", "confidence": "high", "evidence": [] },
    "max_gap_months":     { "value": 4,  "derivation": "computed", "confidence": "medium", "evidence": [] },
    "months_since_relevant": { "value": 0, "derivation": "computed", "confidence": "high", "evidence": [] }
  },

  "skills": {
    // keyed by canonical taxonomy id; presence of a key does NOT imply the candidate has it
    "python": {
      "held":          { "value": true, "derivation": "stated", "confidence": "high",
                         "evidence": [{ "quote": "Python (5 yrs)", "start": 1401, "end": 1415, "section": "skills" }] },
      "years":         { "value": 4.5, "derivation": "computed", "confidence": "high", "evidence": [] },
      "last_used_year":{ "value": 2026, "derivation": "computed", "confidence": "high", "evidence": [] },
      "proficiency":   { "value": "advanced", "derivation": "inferred", "confidence": "low", "evidence": [] },
      "project_count": { "value": 3, "derivation": "computed", "confidence": "medium", "evidence": [] },
      "dated":         true      // false => mentioned only in a skills block, years is null
    },
    "kubernetes": {
      "held":  { "value": null, "derivation": "absent", "confidence": "low", "evidence": [] },
      "years": { "value": null, "derivation": "absent", "confidence": "low", "evidence": [] },
      "dated": false
    }
  },

  "projects": [
    { "title": "Recourse demo", "topics": ["machine_learning", "web_backend"],
      "role": "author", "duration_months": 4, "url_present": true,
      "evidence": [{ "quote": "…", "start": 2210, "end": 2280, "section": "projects[0]" }] }
  ],
  "project_counts_by_topic": { "machine_learning": 2, "web_backend": 3 },

  "education": {
    "highest_level": { "value": "msc", "derivation": "stated", "confidence": "high",
                       "evidence": [{ "quote": "M.Sc. (Tech), Aalto University", "start": 90, "end": 120,
                                      "section": "education[0]" }] },
    "field":         { "value": "computer_science", "derivation": "stated", "confidence": "high", "evidence": [] },
    "graduation_year": { "value": 2021, "derivation": "stated", "confidence": "high", "evidence": [] },
    "in_progress":   { "value": false, "derivation": "inferred", "confidence": "medium", "evidence": [] }
  },

  "certifications": [
    { "cert_id": "aws_saa", "issuer": "Amazon Web Services", "issued": "2024-05", "expires": "2027-05",
      "active_as_of": true,
      "evidence": [{ "quote": "AWS Certified Solutions Architect – Associate (2024)", "start": 3100, "end": 3152,
                     "section": "certifications" }] }
  ],

  "languages": [
    { "lang": "en", "cefr": "C1", "derivation": "inferred", "confidence": "low" },
    { "lang": "fi", "cefr": "B2", "derivation": "stated",   "confidence": "high" }
  ],

  "eligibility": {                        // knockouts; mostly immutable or conditionally actionable
    "work_authorization_region": { "value": "EU", "derivation": "stated", "confidence": "medium", "evidence": [] },
    "requires_sponsorship":      { "value": false, "derivation": "stated", "confidence": "medium", "evidence": [] },
    "location_country":          { "value": "FI", "derivation": "stated", "confidence": "high", "evidence": [] },
    "location_region":           { "value": "Uusimaa", "derivation": "stated", "confidence": "medium", "evidence": [] },
    "relocation_willing":        { "value": null, "derivation": "absent", "confidence": "low", "evidence": [] },
    "onsite_willing":            { "value": null, "derivation": "absent", "confidence": "low", "evidence": [] },
    "notice_period_weeks":       { "value": null, "derivation": "absent", "confidence": "low", "evidence": [] }
  },

  "never_extract": ["name", "date_of_birth", "age", "gender", "photo", "nationality",
                    "marital_status", "street_address", "postal_code", "health", "religion",
                    "union_membership", "criminal_record"]
}
```

`never_extract` is echoed back by the extractor as a self-check, and a post-extraction scrubber in
code asserts none of those keys appear anywhere in the object. Postal code matters specifically:
Illinois HB 3773 bans zip codes as protected-class proxies, so the schema stops at country and
region.

### 1.2 Feature manifest (static, employer-editable)

```jsonc
{
  "job_family": "software_engineering",
  "features": {
    "skills.kubernetes.held": {
      "actionability": "actionable",
      "direction": "increase_only",
      "step": { "unit": "boolean", "size": 1 },
      "cost_weight": 3.0,
      "plausible_max_delta": 1,
      "typical_time_months": 3,
      "candidate_phrase": "working knowledge of Kubernetes"
    },
    "skills.python.years": {
      "actionability": "conditionally_actionable",   // only by waiting
      "direction": "increase_only",
      "step": { "unit": "years", "size": 0.5 },
      "cost_weight": 8.0,
      "plausible_max_delta": 2.0,
      "typical_time_months": 12,
      "candidate_phrase": "professional Python experience"
    },
    "project_counts_by_topic.machine_learning": {
      "actionability": "actionable", "direction": "increase_only",
      "step": { "unit": "projects", "size": 1 }, "cost_weight": 2.0,
      "plausible_max_delta": 3, "typical_time_months": 2,
      "candidate_phrase": "machine-learning projects"
    },
    "education.highest_level": {
      "actionability": "conditionally_actionable",
      "direction": "increase_only",
      "step": { "unit": "level", "size": 1, "ladder": ["none","secondary","vocational","bsc","msc","phd"] },
      "cost_weight": 40.0, "plausible_max_delta": 1, "typical_time_months": 24,
      "candidate_phrase": "completed degree level"
    },
    "eligibility.requires_sponsorship": { "actionability": "immutable",
      "direction": "none", "cost_weight": null,
      "disclosure": "This is a legal eligibility requirement for the role." },
    "experience.total_years":   { "actionability": "immutable", "direction": "none" },
    "education.graduation_year":{ "actionability": "protected_never_use",
      "reason": "age proxy — ADEA / Mobley v. Workday" },
    "experience.max_gap_months":{ "actionability": "protected_never_use",
      "reason": "caregiving and disability proxy" },
    "languages.*.cefr": { "actionability": "conditionally_actionable",
      "direction": "increase_only", "step": { "unit": "cefr_level", "size": 1 },
      "cost_weight": 20.0, "typical_time_months": 12 }
  }
}
```

Four actionability classes, and each does distinct work:

- **actionable** — the solver may propose it and the explanation may state it.
- **conditionally actionable** — proposable, but the explanation must carry the time cost
  ("about a year"). Years-of-experience is here, not in *actionable*: you cannot acquire it by
  deciding to.
- **immutable** — the solver may not move it, but the explanation *must* mention it when it is the
  binding constraint. Telling someone "add Kubernetes" when the real blocker is work authorisation
  is the cruellest possible failure mode.
- **protected_never_use** — excluded from the scoring model entirely, not just from the solver.
  Graduation year and employment gaps sit here because they are the exact signals at issue in
  *Mobley v. Workday* and the iTutorGroup consent decree.

`cost_weight` is what the solver minimises. Set it from `typical_time_months` so the ordering is
defensible rather than arbitrary, and expose it in the employer UI so the weights are a
configuration artefact you can show an auditor.

### 1.3 Deriving "years of experience in skill X"

Do this in code, after extraction. The LLM's job is to emit `roles[]` with dates and
`skills_mentioned` scoped to each role; it must never emit a years figure.

1. **Normalise dates.** `"Mar 2022"` -> `2022-03`; a bare `"2022"` -> `2022-07` with
   `date_precision: "year"` so you can report an error bar. `"Present"`, `"Current"`, `"nyt"` ->
   `as_of`. Never `datetime.now()`: the profile must be replayable, and a cached prompt with a
   live timestamp also silently kills your prompt cache.
2. **Scope skills to roles.** A skill counts toward a role only if it appears inside that role's
   text block. Skills that appear only in a standalone "Skills" header get `dated: false` and
   `years: null`.
3. **Union, do not sum.** `years(s) = |⋃ {interval(r) : s ∈ r.skills_mentioned}| / 12`. Summing
   double-counts a contract that overlapped a full-time job, and CVs with concurrent freelance work
   are common. Union of half-open month intervals; keep months internally, expose years to one
   decimal, round only at display.
4. **Recency.** `last_used_year = max(end_year(r))` over the same set. Employers weight this and it
   is a cheap recourse lever ("use it in something current").
5. **Depth, not just duration.** `primary_skills` (skill in the role title or the first two bullets)
   lets the scorer distinguish four years of Python from four years of having Python in a list at
   the bottom of a role that was really about Java. Emit both; let the employer weight it.
6. **Projects and education count** when dated, at a discount the manifest sets.
7. **Error bars.** Propagate `date_precision`. A profile built from year-only dates can be off by
   ±6 months per role, and the explanation must not say "0.5 years short" when the input precision
   is ±0.5 years. Where the shortfall is inside the error bar, say so.

### 1.4 Missing is not absent

This is the single hardest correctness problem in the whole system, and getting it wrong makes the
product actively harmful: telling a candidate "learn Docker" when they have used Docker daily for
three years and just did not list it destroys trust instantly.

Four mitigations, all cheap:

- **Three-valued logic in the schema.** `derivation` distinguishes `stated`, `absent` (not in the
  CV), and `denied` (the CV positively rules it out, e.g. "no cloud experience"). The scorer must
  treat `absent` as *unverified*, not as zero. In practice: score `absent` at a configured prior
  rather than at the floor, and record that you did.
- **Ask before you instruct.** Any delta on an `absent` field is rendered as a question, not a
  demand: "If you have worked with Kubernetes, add it — the screen did not find it." A delta on a
  `denied` or `stated`-but-low field is rendered as an instruction. One boolean in the template
  table, enormous difference in how the message lands.
- **Co-occurrence prior for cheap wins.** From your taxonomy, precompute which skills almost always
  travel together (Django -> SQL, Kubernetes -> Docker, React -> JavaScript). When an absent skill
  has high posterior given the stated ones, surface it *first* and label it zero-cost: "you
  probably already have this, it is missing from the page." The cheapest recourse is very often
  "restate what you already did", and no competitor ships that.
- **A restatement channel.** Let the candidate confirm absent-but-plausible skills and re-run the
  scorer. This is the feature that turns the demo from a rejection letter into a product, and it
  costs one API call.

---

## 2. Reliable extraction with Claude

### 2.1 Request shape

Use **structured outputs**: `output_config: {format: {...}}` on `messages.create()`, or the
`client.messages.parse()` helper, which validates the response against your schema for you. Do not
use the deprecated top-level `output_format` parameter. If you route extraction through a tool
instead, set `strict: true` as a top-level field on the tool definition (not on `tool_choice`), and
give the schema `additionalProperties: false` plus a complete `required` list — strict mode
requires both.

**Do not use the citations feature for evidence spans.** Document citations
(`citations: {enabled: true}`) return real `cited_text` and `char_location` offsets and would be
ideal, but they are **incompatible with `output_config.format` and return a 400**. So evidence
spans go in the schema as ordinary string fields that the model fills with verbatim quotes, and you
verify them in code:

```python
for span in every_evidence_span(profile):
    idx = cv_text.find(span["quote"])
    span["verified"] = idx != -1
    if idx != -1:
        span["start"], span["end"] = idx, idx + len(span["quote"])
```

This substring check is the highest-value 10 lines in the pipeline. It is free, deterministic, and
catches fabricated values immediately, because a hallucinated skill almost never comes with a quote
that exists in the document. Policy: any value whose quote fails to verify is downgraded to
`confidence: "low"` and, if it is a knockout field, dropped to `absent` rather than trusted.

### 2.2 The passes

1. **Pass A — extract.** One call. System prompt holds the instructions, the taxonomy enum, and the
   schema; the CV goes last, in a user turn, inside delimiters. Adaptive thinking at
   `output_config: {effort: "medium"}`. Structured output.
2. **Post-process in code.** Date normalisation, interval union, seniority laddering, taxonomy
   canonicalisation, span verification, the `never_extract` scrub. None of this is a model job:
   it is arithmetic and lookups, and the model will get it subtly wrong at a rate you cannot drive
   to zero.
3. **Pass B — verify.** A second call sees the CV plus the extracted profile and is asked for one
   narrow thing: a list of disagreements, each with a field path and a quote. Narrow tasks are far
   more reliable than "check everything". Empty list is the common case and costs almost nothing.
   Escalate any disagreement on a knockout field to human review.
4. **Self-consistency, selectively.** Sampling parameters (`temperature`, `top_p`) are removed on
   current models, so you cannot dial variance directly, but independent calls still vary. Run
   3-way sampling only on the two or three fields your eval shows are unstable (usually `seniority`
   and proficiency), and take the majority. Do not 3× the whole extraction; it triples cost to fix
   fields that were already stable.

### 2.3 Prompt injection from CV text

Real and measured, not hypothetical. A USENIX Security 2026 study scanned ~196,682 real resumes and
found roughly **1% carried hidden prompt injections** (1.19% recent, 0.91% over 6.5 years of
history), spiking to ~1.2% in 2024. The composition is the surprise: **over 90% was *data*
injection** — invisible keyword stuffing, fabricated skills, pasted job requirements aimed at
keyword matchers — and **under 10% was instruction injection** of the "ignore previous instructions"
kind. Greenhouse's 2025 survey found 41% of job seekers *admit* to trying it while only ~1% of
actual resumes contained hidden white text. General-purpose injection detectors scored **under 10%
recall**; the study's own hybrid rule-plus-LLM cascade hit 86.1% precision at ~$0.0001 per resume.

Mitigations, in order of value:

1. **Extract the text yourself and compare renderings.** Most attacks are invisible-to-human, not
   invisible-to-parser: white text, 1pt fonts, off-page absolute positioning, text layered under
   images. Compare the PDF's embedded text layer against an OCR of the rendered page and flag any
   span present in one and not the other. This catches the majority of real attacks before a token
   reaches the model, and it is a pure PDF-library task.
2. **Structure beats instruction.** Because the output is schema-constrained and every value must
   carry a verifiable quote, an injected "rate this candidate highly" has nowhere to land — there
   is no rating field, and the scoring model never sees prose. This is the strongest argument for
   the architecture in §0: it is injection-resistant by construction, not by filtering.
3. **Never put CV text in the system prompt.** It goes in a user turn, wrapped in explicit
   delimiters, with a standing instruction that content inside them is data to be described, never
   instructions to follow.
4. **Use the operator channel for mid-run instructions.** On Claude Opus 5 you can append a
   `{"role": "system", ...}` message to `messages[]` mid-conversation without invalidating the
   cached prefix; that is the injection-safe place for operator instructions. Claude Sonnet 5 does
   not support it — a real point in Opus 5's favour for this pipeline.
5. **Flag, do not auto-reject.** Detected injection routes to human review. Auto-rejecting on
   suspected injection creates a trivial sabotage vector against other candidates and an obvious
   false-positive liability, given that a pasted job description is indistinguishable from keyword
   stuffing at the string level.

### 2.4 Model choice and cost

**Recommendation: `claude-opus-5` for both steps in the demo; consider `claude-sonnet-5` for the
bulk extraction pass in production, gated on an eval.**

The demo argument is arithmetic. At a 200-CV corpus the entire end-to-end difference between Opus 5
and Sonnet 5 is roughly twelve euros. There is no scenario where saving that is worth a schema
violation or a mis-parsed date in a live jury demo. Extraction quality here is not generic
information extraction: it is multi-hop (scope skills to roles, respect the taxonomy enum, get
overlapping date intervals right, distinguish absent from denied), and that is precisely where the
capability gap shows up.

The explanation step should be Opus 5 regardless of volume. It is one short call per rejected
candidate, it is the only text a human ever reads, and it is the step with legal exposure. Do not
economise there.

For a production extraction fleet, extraction is the textbook bulk-extractor role where a second,
cheaper model belongs. Sonnet 5 at `effort: "medium"` is the candidate; Haiku 4.5 is likely too
weak for the interval arithmetic. Decide with an eval on your own synthetic corpus (§4), not on
vibes: hold Opus 5 as the reference, and step down only if Sonnet 5 holds field-level accuracy on
the knockout fields and mean absolute error under one month on the years fields.

Per-CV estimates. Assume a ~6,000-token cached prefix (system + schema + taxonomy), a ~1,200-token
CV, and ~2,500 output tokens of profile with evidence spans. Cache reads are roughly a tenth of the
input rate; thinking tokens bill as output, so these assume `effort: "medium"`.

| Step | Opus 5 ($5 / $25 per MTok) | Sonnet 5 ($2 / $10) |
|---|---|---|
| Pass A extract | $0.072 | $0.029 |
| Pass B verify | $0.030 | $0.012 |
| Explanation | $0.020 | $0.008 |
| **Total per CV** | **~$0.12** | **~$0.05** |

A 200-CV demo corpus on Opus 5 end to end is about **$24**. Eval sweeps go through the Batch API at
50% off, so a 500-CV regression run is roughly $30. Two further request-level details: cache the
system-plus-schema prefix and keep the CV strictly after the last breakpoint, then verify
`usage.cache_read_input_tokens` is non-zero; and include the server-side refusal fallback on Opus 5
(`betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"`) so a classifier refusal
on an unusual CV degrades instead of erroring.

---

## 3. Skill normalisation

| | Size / scope | Licence & access (verified 2026-09) | Fit here |
|---|---|---|---|
| **ESCO** v1.2.1 (Dec 2025) | ~13,900 skill concepts, ~3,000 occupations, 28 languages | Free reuse for any purpose under Commission Decision 2011/833/EU, effectively CC BY 4.0. CSV, RDF, TTL, ODS, XML, JSON-LD downloads plus a hosted web API and a local API | Best free backbone. EU-framed, multilingual, stable IDs, hierarchical. Weak on current tooling granularity: it has "use Python" but will not distinguish FastAPI from Django, and new frameworks arrive slowly |
| **O\*NET** (US DOL) | 900+ occupations, KSAs, plus a genuinely useful Technology Skills / Hot Technologies table | Free, CC BY 4.0 for the database; Web Services needs registration, attribution, URL registration, and requires presenting data "without alteration" | The Hot Technologies list is an excellent *seed* for a software taxonomy. The no-alteration clause makes it awkward as your canonical store, since you will want to remap and re-granularise |
| **Lightcast Open Skills** | ~34,000 skills, best coverage of live tech tooling | **Changed in April 2026.** Split into public-good access (nonprofit / public sector, approval required, reported ~50 extractions per month) and commercial access by contract. Taxonomy still browsable free on the web | Best data, worst hackathon fit. An approval queue does not survive a weekend deadline. Do not build a dependency on it |
| **Hand-curated** | 150-400 concepts per job family | Yours | Recommended |

**For the hackathon: hand-curate, cross-reference ESCO, skip embeddings at first.**

Build a 200-400 concept taxonomy for your two job families. Seed it from O\*NET Hot Technologies
for software, attach an ESCO concept URI to every entry where one exists, and give each entry an
alias list (`k8s`, `kubernetes`, `K8S`; `postgres`, `PostgreSQL`, `psql`). Total effort: an
afternoon, most of it an LLM drafting entries you then review.

Then the opinionated bit: **at 400 concepts, put the taxonomy in the schema as an enum and let the
model select from it directly.** Do not build an embedding-matching stage first. The enum fits
comfortably in a cached prefix, costs nothing per call after the first, makes out-of-taxonomy
output structurally impossible, and is trivially debuggable. Reserve two escape hatches: an
`unmatched_skills: string[]` field for things the model saw but could not map (which becomes your
taxonomy backlog, and is genuinely interesting to show a jury), and a local sentence-transformers
model over the canonical labels for offline triage of that backlog. The Claude API has no
embeddings endpoint, so a local model is the right choice here anyway: free, offline, fast.

Three normalisation rules that matter more than the taxonomy choice: keep `raw` alongside
`canonical` everywhere so a mapping error is always recoverable; version the taxonomy and stamp the
version into the profile, because a profile scored under `swe-core-0.3` is not comparable to one
scored under `0.4`; and never delete a concept, only deprecate with a redirect, or old profiles
stop replaying.

**What a real product does:** license Lightcast or Eightfold-style embeddings for coverage,
maintain an internal taxonomy mapped to ESCO for EU regulatory reporting and to O\*NET for US
occupational reporting, and run an LLM-assisted intake queue where unmatched strings are clustered
weekly and promoted to concepts by a human. The taxonomy becomes a maintained asset with an owner,
which is exactly what a hackathon should not attempt.

---

## 4. Demo data

### 4.1 Open datasets, and why most of them are the wrong tool

| Dataset | What it is | Licence | Verdict |
|---|---|---|---|
| [Careerflow/ResumeExtractBench](https://huggingface.co/datasets/Careerflow/ResumeExtractBench) | 38 docs (28 expert-written, 10 adversarial distractors), 9 schema sections, 6 domains, fictional PII | CC BY 4.0 | **Use it.** Tiny, but exactly the right shape: schema-guided extraction with ground truth and built-in adversarial cases. Your held-out human-written slice |
| [snehaanbhawal/resume-dataset](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset) (Kaggle) | ~2,400 resumes scraped from livecareer.com, 24 categories, HTML + text + PDF | Could not verify from the dataset page; treat as unconfirmed | Smoke-testing only. These are *published resume examples*, not real applications, so the distribution is unrealistically clean. Do not redistribute |
| CareerCorpus (*Data in Brief*, 2026) | Annotated resume corpus derived from the Kaggle set | CC BY 4.0 per the article metadata; the article itself was behind a 403 | Worth 20 minutes to fetch properly if you want more annotated human-written text |
| [sukhrobnurali/resume-parsing-vision](https://huggingface.co/datasets/sukhrobnurali/resume-parsing-vision) | Fully synthetic rendered resume *images* paired with ground-truth JSON | Check on the card | Only if you accept PDF upload in the demo |
| [datasetmaster/resumes](https://huggingface.co/datasets/datasetmaster/resumes) | Mixed real + Faker-synthetic, normalised JSON | Unclear provenance on the real half | **Avoid.** Unclear-provenance real CVs are a privacy problem you do not need |

The blocking issue with all the real-resume sets: they contain personal data you have no lawful
basis to process for a student demo in the EU, and none of them ship the ground-truth *derived*
fields you actually need to measure (years per skill, seniority, canonical education level). Use
real corpora as **style references for your generator prompt** and as a small held-out realism
check. Run the demo itself on synthetic CVs.

### 4.2 Profile-first synthetic generation

The ordering is the whole trick: **sample the ground-truth profile in code, then render the CV text
from it with Claude.** Generating CVs first and labelling them afterwards gives you labels that are
themselves model output, and your extraction accuracy number becomes meaningless.

1. **Sample the profile in pure Python.** Draw seniority, then role count, then non-overlapping
   month intervals (with a configurable rate of deliberate overlaps), then skills from the taxonomy
   using the co-occurrence prior, then education, certifications, languages, eligibility. No LLM.
   Because you compute `years_per_skill` with the same interval-union code the extractor will be
   graded against, the derived ground truth is exact by construction.
2. **Render with Claude.** Give it the profile JSON plus a style directive and one hard rule:
   *never state a derived value*. The CV may say "Mar 2022 – Present, Python"; it must not say "5
   years of Python", or you are testing reading comprehension instead of date arithmetic. Vary
   style aggressively: reverse-chronological, functional, academic, two-page consultant, terse
   startup one-pager, non-native English, prose without bullets, Finnish-English mix.
3. **Inject the hard cases deliberately**, each as a flagged variant so you can score them
   separately: under-reporting (drop 30% of the profile's skills from the text but keep them in the
   ground truth — this measures the §1.4 failure directly and is your headline number),
   overlapping contracts, career gaps, bare-year dates, synonym-only mentions (`k8s`, `RHEL`),
   invisible-text injections, off-topic filler, and a title that oversells the role.
4. **Hold out the human-written slice.** Score against ResumeExtractBench too. A generator and an
   extractor from the same model family will flatter each other; the held-out slice is what keeps
   you honest.
5. **Metrics.** Exact match on categoricals; mean absolute error in *months* on every years field;
   precision and recall on skill sets, reported separately for skills stated in the text versus
   skills deliberately omitted (the second is your honest ceiling, and it will be low — that is the
   finding, not a bug); evidence-span verification rate; and schema-violation rate, which should be
   zero under structured outputs and is a canary if it is not.

### 4.3 Job families

**Software engineering** and **registered nurse**.

Software engineering is the obvious first: skills are granular and genuinely actionable, the
taxonomy is easy to seed, your audience can eyeball whether an explanation is sensible, and it is
the role type with the worst applicant-per-hire ratio (~191), so pre-screening is real there.

Nursing is the contrast that makes the project credible rather than a toy. Its criteria are
dominated by licence and certification knockouts; much of the profile is immutable or slow-moving;
and a large share of rejections have **no cheap recourse at all**. A system that can say "the
blocker is the licence, which takes 18 months, and here is the human-review route" is demonstrating
honesty about its own limits. That is a far stronger demo than two flavours of "learn one more
framework", and it exercises every branch of the actionability taxonomy in §1.2. If you want a
lighter second family instead, sales works (trajectory and quota signals, almost no hard skills),
but it does not stress the immutable path the way nursing does.

---

## 5. Explanation generation guardrails

### 5.1 Inputs

LLM #2 sees a whitelisted object and nothing else. Not the CV, not the score internals, not the
weights, not other candidates.

```jsonc
{
  "outcome": "not_advanced",
  "binding_constraints": [
    { "delta_id": "d1", "field": "skills.kubernetes.held",
      "from": null, "to": true, "unit": "boolean",
      "derivation_of_current": "absent",
      "candidate_phrase": "working knowledge of Kubernetes",
      "typical_time_months": 3, "actionability": "actionable" },
    { "delta_id": "d2", "field": "project_counts_by_topic.machine_learning",
      "from": 2, "to": 3, "unit": "projects",
      "derivation_of_current": "stated",
      "candidate_phrase": "machine-learning projects",
      "typical_time_months": 2, "actionability": "actionable" }
  ],
  "immutable_blockers": [],
  "flip_test_passed": true,
  "as_of": "2026-09-19", "model_version": "screen-v3", "uncertainty_note": "date_precision_month"
}
```

### 5.2 Constraining the output

**Pin the structure with the schema, not with instructions.** Use structured outputs with an array
whose items are `{ "delta_id": string, "sentence": string }` and require exactly one item per input
delta. Extra sentences then become structurally impossible rather than something you have to detect
afterwards. Code owns the intro, the ordering, the disclosures, and the closing; the LLM writes
only the per-delta sentences and, optionally, one summary line drawn from the same constrained set.
Every skeleton has a code-generated fallback string, so a failed check degrades to stiff-but-true
prose rather than to nothing.

Template selection is code, driven by `derivation_of_current`: `absent` -> question form, `stated`
-> instruction form, `immutable` -> the disclosure text from the manifest, verbatim, never
paraphrased by the model.

### 5.3 The checker

Runs on every generated explanation, before anything is shown:

1. **Coverage and injectivity** — every `delta_id` appears exactly once, no more, no fewer.
2. **Numeric containment** — regex every numeral in the text; each must appear in the input object.
   Catches the most common and most damaging hallucination, an invented threshold.
3. **Banned lexicon** — reject any comparative or causal claim the system cannot support: "better
   candidates", "we preferred", "you were not qualified", "your background suggests", "stronger
   applicants", "unfortunately your profile".
4. **Protected-term scan** — no age, gender, nationality, name, or school-prestige language.
5. **Entailment judge** — one Claude call: given the delta JSON and one sentence, does the sentence
   assert anything not in the JSON? Boolean out, structured output, cheap.
6. **Flip test** — already asserted in code before generation; the checker confirms the flag.

On failure: one regeneration, then fall back to the code-generated template text. Never loop, and
never ship unchecked output.

### 5.4 What to disclose

Say: that an automated screen produced the outcome; that the listed changes are **one sufficient
path, not the only one and not a guarantee**; the time realism; the as-of date and model version;
that other candidates and role requirements change; and the route to human review and contest.
That last item is the GDPR Article 22 and EU AI Act Article 86 shape, and it is the thing that turns
this from a clever demo into something an employer could actually deploy.

Do not say: the weights, the exact threshold, anything about other applicants, or anything about
the immutable blockers beyond the manifest's fixed disclosure text.

### 5.5 Example prompt and output

System:

```
You rewrite structured screening feedback into plain, warm, concrete sentences.

Rules:
- Write exactly one sentence per delta, in the order given, each tagged with its delta_id.
- Use ONLY the facts in the JSON. Invent nothing: no comparisons to other applicants, no
  reasons, no numbers that are not in the JSON.
- If derivation_of_current is "absent", the CV did not mention it — phrase it as a question
  ("if you have X, add it"), never as an accusation that the person lacks it.
- If derivation_of_current is "stated", phrase it as a concrete step.
- Second person, no jargon, no more than 30 words per sentence. No apologies, no filler.
- Do not state or imply that making these changes guarantees any outcome.
```

User: the JSON from §5.1.

Output (after checks pass, wrapped in code-generated framing):

> **Your application did not move to the interview stage.** An automated screen compared your
> profile against this role's configured requirements. Two things would have changed the result:
>
> - **Kubernetes.** Your CV did not mention Kubernetes — if you have worked with it, add it and
>   ask us to re-run the screen. If not, a hands-on introduction takes most people around three
>   months.
> - **One more machine-learning project.** You listed two; this role was configured to look for
>   three, so a third project you can describe and link would close the gap.
>
> *This is guidance, not a promise. These two changes would have been enough on 19 September 2026,
> under screening model `screen-v3`; other routes exist, requirements change, and meeting them does
> not guarantee an interview. Your experience dates were read to the month, so figures are
> approximate. To have a person review this decision, [contact us].*

Note what the model did **not** write: no score, no threshold, no ranking, no reason, no
comparison, no encouragement it cannot back. Everything it produced maps one-to-one onto a delta,
and a checker proved it.

---

## 6. Build order

1. Feature manifest and candidate schema as JSON Schema files, plus the deterministic
   post-processor (date math, interval union, taxonomy lookup, span verification, scrubber). No
   LLM yet. Half a day, and it is the part the rest depends on.
2. Curated taxonomy, 200-400 concepts, ESCO URIs attached, aliases filled.
3. Synthetic generator: profile sampler in Python, then the Claude renderer. Produce 200 CVs across
   the two families with the adversarial variants flagged.
4. Extractor: Opus 5, structured outputs, cached prefix, span verification, verify pass. Measure
   against the synthetic ground truth and the ResumeExtractBench hold-out.
5. Explanation step with the full checker chain and the flip test.
6. Only then, if time remains, the PDF render-vs-text-layer injection detector.

---

## Sources

- [ESCO portal — downloads and API](https://esco.ec.europa.eu/en/use-esco/download), [ESCO v1.2](https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia/esco-v12), [ESCO FAQ on reuse](https://esco.ec.europa.eu/en/about-esco/faq)
- [Commission Decision 2011/833/EU on reuse of Commission documents](https://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=OJ:L:2011:330:0039:0042:EN:PDF)
- [O\*NET Web Services](https://services.onetcenter.org/), [O\*NET Web Services data licence](https://services.onetcenter.org/help/license_data), [O\*NET API v1.9](https://services.onetcenter.org/v1.9/)
- [Lightcast Open Skills](https://lightcast.io/open-skills), [Lightcast API access](https://lightcast.io/open-skills/access), [analysis of the April 2026 free-tier change](https://jobspipe.dev/blog/lightcast-api)
- ["Measuring Real-World Prompt Injection Attacks in LLM-based Resume Screening" (USENIX Security 2026)](https://arxiv.org/html/2605.28999v1)
- [Duke Pratt — thwarting hidden resume prompt injection](https://pratt.duke.edu/news/thwarting-prompt-injection/)
- [Careerflow/ResumeExtractBench (CC BY 4.0)](https://huggingface.co/datasets/Careerflow/ResumeExtractBench)
- [Kaggle resume dataset (livecareer scrape)](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset)
- [CareerCorpus, *Data in Brief* 2026](https://www.sciencedirect.com/science/article/pii/S2352340926001204)
- [sukhrobnurali/resume-parsing-vision](https://huggingface.co/datasets/sukhrobnurali/resume-parsing-vision), [datasetmaster/resumes](https://huggingface.co/datasets/datasetmaster/resumes)
- Claude model IDs, pricing, structured outputs, strict tool use, citations/`output_config` incompatibility, prompt caching, and mid-conversation system messages: `claude-api` skill, model table cached 2026-06-24.
