# AI-Powered Pre-Screening in Hiring: What Criteria Hiring Managers Actually Configure

## TL;DR
- **The dominant real-world filter is a small set of binary "knockout" questions** — work authorization/visa sponsorship, location, required licenses/certifications, minimum experience, and shift availability — not the sophisticated semantic skill-matching that vendors market. In a 2025 Enhancv study of 25 US recruiters, knockout questions were the primary automated filter while 92% said their systems do not auto-reject resumes on content, and only 8% had any content/threshold-based auto-rejection configured.
- **There is a large gap between what these systems can do and what recruiters use.** AI "fit"/match scores exist in ~44% of the ATSs recruiters use, but most treat them as advisory or ignore them; meanwhile the criteria with the strongest predictive validity (structured interviews, work samples, cognitive tests) are underused, and the two most common resume-screen criteria — years of experience and education — are among the *weakest* predictors of job performance.
- **Regulation is reshaping which criteria are legal and how they must be disclosed** — NYC Local Law 144 bias audits, Illinois HB 3773 (banning zip-code proxies), the EU AI Act's high-risk classification of hiring AI, and the *Mobley v. Workday* collective action — even as US federal enforcement retreated sharply in 2025 (EEOC AI guidance removed; a disparate-impact executive order).

## Key Findings

**1. The criteria fall into six tiers, and their real-world prevalence is inverted from their sophistication.** Hard knockout questions (used almost universally where volume is high) are simple and binary; the more advanced weighted skill-matching and learned-ranking features are widely available but inconsistently trusted.

**2. Knockout/disqualifier questions are the workhorse.** Across vendor documentation (Greenhouse, SAP, Workable, Lever, Ashby, SmartRecruiters) and practitioner accounts, the standard knockout set is: work authorization / visa sponsorship, geographic location / relocation / onsite-hybrid willingness, required licenses & certifications (CDL, CPA, RN, security clearance), minimum years of experience, shift/weekend availability, minimum age (18/21), willingness to undergo background check and drug screen, and sometimes salary-expectation and notice-period gates. A well-configured knockout set is described by practitioners as eliminating 30–60% of applications before human review.

**3. Hard requirements vs. weighted scoring.** Systems distinguish "must-have" (auto-disqualify or hard filter) from "nice-to-have" (weighted). Greenhouse's own scorecard template codifies four categories: Details (eligibility — work authorization, salary range, travel), Qualifications (degree, certifications, industry experience), Skills, and other attributes. Semantic/embedding-based matching (Eightfold, Phenom, Beamery, SeekOut) scores candidates on inferred and adjacent skills rather than keyword presence.

**4. Career-trajectory signals are increasingly modeled** — seniority progression, tenure/job-hopping, employment gaps, recency of relevant experience, and company prestige — but these are exactly the signals implicated in bias litigation (age, in *Mobley v. Workday*) and audit studies.

**5. The predictive-validity evidence contradicts common criteria.** Structured interviews and work-sample/job-knowledge tests have the highest validity; years of experience and education have low validity. Yet resume screens lean heavily on experience and education because they are cheap to parse.

**6. Documented failures are real and repeated** — Amazon's scrapped tool (2018), the iTutorGroup ADEA settlement (2023), and multiple LLM resume-audit studies (University of Washington 2024) showing race/gender bias.

## Details

### The vendor landscape (2025–2026)

**ATS-native screening/ranking.** Workday, Greenhouse, Lever, SmartRecruiters, iCIMS, Ashby, Bullhorn, Oracle Taleo, SAP SuccessFactors. These parse resumes into structured fields and apply knockout rules plus, increasingly, an AI match/fit score. Crucially, the degree of automation varies enormously: Greenhouse is explicitly a "structured hiring" platform that does *no* keyword-based auto-rejection — the only automatic rejection comes from knockout questions on the application form, and every other rejection is a human decision against an interviewer scorecard (rated "Definitely Not" to "Strong Yes"). By contrast, Workday and iCIMS are described by practitioners as built around heavier automated screening and ranking. Workday's acquisition of Paradox (closed Oct 1, 2025) and its HiredScore AI are both central to the *Mobley* litigation.

**Talent intelligence & matching.** Eightfold AI, Phenom, Beamery, SeekOut, hireEZ, Gloat. Eightfold's engineering blog describes the technical mechanism plainly: it embeds "skills, titles, companies, degrees, and schools using token-level embedding models" trained on hundreds of millions of profiles, mapping each skill phrase to an N-dimensional vector so related skills ("Pandas" near "Python") cluster — this is embedding-based semantic similarity, producing a "Match Score." Eightfold markets a dataset of over a billion career profiles and, in 2026, launched an autonomous "AI Interviewer." Beamery emphasizes a developed skills framework and was among the first to obtain independent bias-audit certification.

**Video/structured interview AI.** HireVue, Sapia.ai, Willo. HireVue hosted 19M+ interviews for 700+ customers; critically, it discontinued facial-expression analysis in January 2021 (its own data scientist found visual data added ~0.25% predictive power) after an EPIC FTC complaint, and now scores only the *transcript* of responses against employer-configured competency models (communication, problem-solving, teamwork) — with candidates presented in tiers, not individually scored.

**AI interviewers / voice screeners.** Micro1 (Zara), Apriora, Mercor, Ribbon, Alex, Classet. Mercor runs a ~20-minute LLM-driven interview built on fine-tuned foundation models; questions are generated from the candidate's resume, and follow-ups are generated from the last answer; one score gates the whole platform for up to six months. Micro1's Zara publishes that resume/credential signal correlates only r≈0.19 with interview outcome — deliberately weighting demonstrated skill over paper credentials.

**Assessment platforms.** HackerRank, Codility, CodeSignal (coding), TestGorilla, Criteria Corp (cognitive/personality), Harver (formerly with Pymetrics; high-volume), Plum. These provide the pass/fail cutoff scores and percentile thresholds that feed shortlisting.

**High-volume conversational.** Paradox (Olivia) is the category leader for hourly hiring — McDonald's (McHire), Chipotle, CVS, Lowe's, GM, 7-Eleven, Marriott. Olivia asks knockout questions (availability, work authorization, age) over SMS/WhatsApp, then books interviews; a "no" to a knockout typically ends the conversation. (Note: in 2025 a researcher disclosed that Paradox's McHire admin portal used a default password "123456," exposing an estimated 64 million chat records — reported by *Wired*.)

### How the ranking actually works, technically

- **Keyword/boolean matching:** oldest method; matches job-description terms against parsed resume text. Still underpins recruiter search filters.
- **Knockout rules engines:** binary "Disqualify If" automations on application-form answers. Zero-false-positive when the requirement is truly binary (work authorization) but dangerous when misapplied to preferences.
- **Embedding-based semantic similarity:** Eightfold/Beamery map skills/titles to vectors; candidates ranked by cosine similarity to the role, capturing adjacent/inferred skills.
- **Learned ranking models trained on past hiring decisions:** the Amazon approach — and the reason it failed (it learned to prefer male-coded resumes because the training data was male-heavy).
- **LLM-based rubric scoring:** Mercor, Micro1, HireVue transcript scoring — an LLM scores free-text/interview answers against a competency rubric.

### The actual criteria — granular

**(a) Hard knockout / disqualifiers (most commonly configured):**
- Work authorization / "will you require sponsorship" (practitioners cite this as the single highest-knocking question — one VP of HR estimated it eliminates ~30% of applicants for her roles)
- Location / relocation / onsite-hybrid-remote willingness
- Required license/certification (CDL, CPA, RN, PMP, security clearance)
- Minimum years of experience (binary framing: "Do you have at least X years…")
- Shift/weekend/schedule availability (dominant in hourly hiring)
- Minimum age (18/21 where legally required)
- Background check / drug-screen willingness
- Education minimum ("Do you have a bachelor's degree?" — auto-knockout where set)
- Salary expectation and notice period (used as gates in some configs)

**(b) Hard requirements (filtered or heavily weighted):** years of experience, education level/degree field, specific certifications, specific tools/technologies, industry background, language proficiency.

**(c) Soft/weighted scoring:** skill-match scores, semantic similarity to JD, must-have vs. nice-to-have weighting, inferred/adjacent skills. Example threshold rules recruiters described in the Enhancv study: "Reject if resume match < 75%" and "Reject if fewer than 7 of the 10 required technical skills are present."

**(d) Career-trajectory signals:** seniority progression, average tenure, job-hopping, employment gaps, recency of relevant experience, company prestige/tier, career pivots.

**(e) Assessment scores:** coding-test pass rates, work-sample scores, cognitive/personality percentiles, structured-interview rubric scores.

**(f) Operational/behavioral signals:** application source, application completeness, responsiveness (huge in Paradox-style flows), prior applications, internal referral.

### Commonly used vs. merely available — the gap you suspected

The evidence strongly confirms a marketing-vs-reality gap:
- **Enhancv (Sept–Oct 2025, 25 US recruiters across 10+ ATSs):** 92% (23/25) said systems do NOT auto-reject on formatting/content/design; knockout questions were the real filters; only 8% (2/25, on Bullhorn and BambooHR) had content/threshold auto-rejection. 44% of ATSs had an AI/fit score, but 56% ignored it or lacked it, 36% used it only as a guide, and 8% used it definitively. The widely repeated "75% of resumes auto-rejected by ATS" claim is an unsourced myth traceable to 2012 marketing by Preptel (defunct 2013). Caveat: n=25, self-described as not nationally representative, and Enhancv is a resume vendor.
- **The "volume, not software, is the real filter" finding:** recruiters described getting 400–2,000 applicants per role; the co-founder framed candidate perception of "AI rejection" as actually "human overload."
- **Adoption context:** the World Economic Forum's *Future of Jobs Report 2025* — which surveyed "more than 1,000 leading global employers…representing more than 14 million workers across 22 industry clusters and 55 economies" — is cited (WEF, March 2025) for the statement that "more than 90% of employers already use some form of automated system to filter or rank job applications." The precise survey question behind that figure is not disclosed, so treat it as an adoption estimate rather than a measured configuration rate.

### Weightings, thresholds, and funnel attrition

- CareerPlug's 2025 Recruiting Metrics Report (10M+ applications): only ~3% of applicants reach interview, <1% (~0.5%) are hired — roughly 1 hire per 180 applicants; ~97% eliminated before speaking to a human; tech roles ~191 applicants/hire, healthcare ~47.
- Knockout stage removes an estimated 30–60% of applications where well-configured.
- Application volume roughly tripled since 2021 (Greenhouse data: recruiters manage 56% more open roles and 2.7× more applications than three years ago).

### Differences by role type

- **Technical/engineering:** coding assessments (HackerRank/Codility/CodeSignal) and LLM technical interviews (Mercor/Micro1) dominate; skills > credentials; ~191 applicants/hire.
- **Sales:** trajectory signals (quota attainment, tenure), personality assessments.
- **Healthcare:** license/certification knockouts are decisive; lower applicant-per-hire ratio (~47).
- **Hourly/high-volume retail & warehouse:** availability, work authorization, age, location knockouts via Paradox-style conversational screening; speed and responsiveness weighted heavily; minimal skill assessment.
- **Executive:** least automated; human/search-firm driven; AI used for sourcing not screening.

### Evidence and effectiveness (predictive validity)

The foundational meta-analysis is Schmidt & Hunter (1998), which reported operational validity of r≈.51 for both general mental ability (GMA) and structured interviews, atop a 19-method hierarchy across 85 years of research, and positioned cognitive ability as the focal predictor. The major revision is **Sackett, Zhang, Berry & Lievens (2022, *Journal of Applied Psychology* 107(11):2040–2068)**, which — correcting for systematic overcorrection of range restriction, and using interrater rather than internal-consistency reliability — **revised GMA operational validity down from .52 to .31 and set structured interviews at .42 (biodata .38), making structured interviews the strongest single predictor**. Critically for screening design: across both frameworks, **years of experience (r≈.18, per McDaniel, Schmidt & Hunter 1988) and education remain near the bottom of the validity hierarchy**, while structured interviews, work samples, and job-knowledge tests remain at the top. This is the core scientific indictment of resume screening: the two criteria easiest to parse from a CV (experience and education) are among the weakest predictors, while the strongest predictors require structured assessment.

A related working paper ("Decision Traces," arXiv) notes that Hoffman, Kahn & Li (2018) found removing manager discretion in favor of algorithmic screening improved hire quality — a counterpoint suggesting well-designed algorithms can beat unstructured human judgment.

### Bias research and documented failures

- **Amazon (2014–2017, revealed by Reuters Oct 2018):** a learned-ranking model trained on 10 years of mostly-male resumes learned to penalize the word "women's" and downgrade all-women's-college graduates; scrapped after fixes failed.
- **iTutorGroup (EEOC, 2023):** the EEOC's first AI-hiring settlement. Per the consent decree filed in the Eastern District of New York on Aug 9, 2023, the company "programmed their tutor application software to automatically reject female applicants aged 55 or older and male applicants aged 60 or older," rejecting "more than 200 qualified applicants," and agreed to pay **$365,000** (an ADEA violation). It was detected when a rejected applicant reapplied with a more recent birth date and got an interview. Note: this settlement predates and is unaffected by the 2025 federal policy changes.
- **University of Washington / Wilson & Caliskan, "Gender, Race, and Intersectional Bias in Resume Screening via Language Model Retrieval" (AIES 2024, arXiv:2407.20371):** audited three Massive Text Embedding models (Mistral, Salesforce, Contextual AI) over 550+ real resumes; the models favored White-associated names in **85.1%** of cases and female-associated names in only **11.1%** of cases (men's names favored 51.9%), and "Black males are disadvantaged in up to 100% of cases." A follow-up UW study (2025, n=528 human participants) found people mirror biased AI recommendations.
- **Newer research (2024–2026):** paired-resume LLM audits show newer model generations sometimes reverse the direction of bias (null or pro-Black gaps), suggesting the picture is model-dependent and shifting.
- **Hidden Workers (Harvard Business School / Accenture; Fuller & Raman, Sept 2021):** surveyed 8,000+ hidden workers and 2,250+ executives across the US, UK, and Germany; **88% of employers agreed that qualified, high-skills candidates are vetted out of the process because they do not match the exact job criteria (94% for middle-skill roles)**, with an estimated **27 million hidden workers in the US alone**. This is the definitive quantification of knockout-criteria false negatives.

### Regulatory constraints on criteria

- **NYC Local Law 144 (effective July 5, 2023):** requires annual independent bias audits of Automated Employment Decision Tools (AEDTs), public posting of results, and 10-business-day candidate notice with opt-out. A December 2025 NY State Comptroller audit found DCWP enforcement badly lacking (75% of 311 complaint calls misrouted; DCWP found 1 non-compliant company where the Comptroller's auditors found 17+), prompting a promised stricter 2026 enforcement phase.
- **Illinois HB 3773 (effective Jan 1, 2026):** amends the Illinois Human Rights Act; makes discriminatory AI use in employment a civil rights violation, **explicitly bans using zip codes as a proxy for protected classes**, and requires notice. Strict liability — intent is not a defense. Implementing notice rules were temporarily withdrawn June 2, 2026, but the statute is in force. Builds on the earlier Illinois AI Video Interview Act (2020).
- **Colorado AI Act (SB 24-205):** first comprehensive US state AI law; delayed from Feb 1, 2026 to June 30, 2026 (SB 25B-004); then largely repealed and replaced by SB 26-189 (signed May 14, 2026, effective Jan 1, 2027), shifting from a duty-of-care/impact-assessment model to a lighter disclosure-and-transparency model — after a federal court stayed the original law amid an xAI/DOJ constitutional challenge.
- **EU AI Act:** classifies recruitment/selection AI as high-risk (Annex III, point 4). High-risk obligations (risk management, human oversight, transparency, bias testing, logging, registration) were set for Aug 2, 2026, but the Digital Omnibus (adopted by the EU Council June 29, 2026) deferred standalone Annex III high-risk deadlines to **December 2, 2027** — a 16-month deferral. Article 5 bans (including workplace emotion recognition) have applied since Feb 2025; AI literacy obligations since Feb 2, 2026. Penalties up to €35M/7% (bans) or €15M/3% (other). GDPR Article 22 (automated-decision limits) applies in parallel.
- **US federal (retreat in 2025):** the EEOC removed its May 2023 Title VII AI technical-assistance document and its ADA/AI guidance from its website on January 27, 2025 (removed, not formally rescinded — they were non-binding). Trump's EO 14281, "Restoring Equality of Opportunity and Meritocracy" (signed April 23, 2025; 90 Fed. Reg. 17537), directs agencies to "deprioritize" disparate-impact enforcement. However, private disparate-impact claims under Title VII survive, and state laws are unaffected.
- ***Mobley v. Workday* (N.D. Cal., 3:23-cv-00770):** Derek Mobley (Black, 40+, disabled) alleges Workday's AI screening tools rejected him 100+ times. Judge Rita Lin ruled Workday can be liable as an "agent"/covered entity because it performs screening functions; on May 16, 2025 she granted preliminary certification of a nationwide ADEA collective (applicants 40+ screened since Sept 2020) — potentially millions, given Workday represented ~1.1 billion applications were rejected through its system in the period. In July 2025 the court ordered Workday to identify customers who used its HiredScore AI. As of 2026 the case continues, with FEHA and disparate-impact disability claims surviving. Implication: vendors, not just employers, can face liability for screening criteria.

### Practitioner criticism and the 2024–2026 volume explosion

- **The application flood:** LinkedIn recorded 11,000 applications/minute in June 2025 (up 45% YoY); applications per role roughly doubled since 2022; a common figure is 250+ applications per corporate opening (500+ for tech roles).
- **The "doom loop" (Greenhouse CEO Daniel Chait):** candidates use AI to mass-apply, employers use AI to filter harder, both escalate. Greenhouse's 2025 data: 22% of active job seekers (31% of Gen Z) use bots to auto-apply; 41% of job seekers admit inserting prompt injections/hidden text to trick AI screeners; 91% of recruiters have spotted candidate deception.
- **Fraud/deepfakes:** Gartner (press release, July 31, 2025) projected that "by 2028, one in four candidate profiles worldwide will be fake," based on a 2Q25 survey of 3,000 candidates in which 6% admitted to participating in interview fraud; North Korean IT-worker infiltration schemes were documented in 2025.
- **Skills-based hiring — mostly rhetoric:** HBS/Burning Glass Institute (Feb 2024) found that despite widespread degree-drop announcements, fewer than 1 in 700 hires (≈97,000 of 77M) actually benefited; 45% of companies dropped requirements "in name only." Indeed data shows the degree-required share of postings has trended back up since early 2024. The "degree filter moved, it didn't die."
- **The arms race:** keyword gaming, resume optimization, and AI-generated applications have pushed employers to add friction (skills assessments, essays) and to repurpose AI interviewers (originally candidate-experience tools) as volume filters.

## Recommendations

**For hiring managers/TA leaders configuring these systems:**

1. **Start with a minimal knockout set (≤5) mapped only to truly binary, job-related, legally defensible requirements** (work authorization, required license, firm schedule). Audit rejection rates by demographic group at least annually. More than five knockouts usually means preferences are being mis-coded as requirements — the Hidden Workers mechanism.
2. **Treat "years of experience" and "degree" as weak, weightable signals — not hard filters.** The validity evidence (Sackett 2022: experience ≈ r.18) is unambiguous that these predict poorly; hard-gating on them is where qualified "hidden workers" are lost. Replace exact-match experience cutoffs with structured assessment.
3. **Invest the screening budget in the high-validity methods:** structured interviews with consistent rubrics and work-sample/job-knowledge tests. These both predict best (structured interviews r≈.42) and are the most legally defensible (job-related, consistently applied).
4. **Use AI match/fit scores as ranking aids for review order, never as auto-reject** — which is how most surveyed recruiters already (correctly) use them, and how Greenhouse and HireVue position their scores.
5. **Build the compliance scaffold now, regardless of federal retreat:** independent bias audits (NYC), candidate notice + no zip-code proxies (Illinois), human-in-the-loop review, and documentation of what each tool tests and how it was validated. The *Mobley* agency theory means vendor assurances do not transfer your liability.

**Benchmarks/thresholds that would change the recommendation:**
- If a single knockout question's disqualify rate exceeds ~30–40%, re-examine whether it screens for a requirement or a preference.
- If a demographic four-fifths (80%) selection-rate disparity appears in a bias audit, the criterion/tool must be revalidated or dropped.
- If your applicant-per-hire ratio spikes (volume flood), add legitimate friction (assessments, essays) rather than tightening opaque AI thresholds.

## Caveats

- **The strongest real-world-configuration data (Enhancv) is a small qualitative study (n=25) by a resume vendor and is explicitly not nationally representative;** it has an internal inconsistency on knockout prevalence (100% vs. 84%). Treat its direction as reliable and its precise percentages as indicative.
- **Many circulating funnel statistics (including the "75% ATS auto-reject" figure) are unsourced or trace to defunct marketing.** The CareerPlug (10M+ applications), WEF *Future of Jobs 2025*, and Employ/Jobvite *Recruiter Nation* figures are the most credible; several aggregator-sourced stats could not be traced to primary datasets.
- **Vendor descriptions of "how the AI works" (Eightfold's billion-profile dataset, Mercor's validity claims, Paradox's ROI) are largely self-reported and not independently audited.**
- **The regulatory landscape is moving fast and in opposite directions** — US federal deregulation vs. state and EU tightening, with the EU high-risk deadline deferred to Dec 2027 and Colorado's law repealed/replaced. Dates and statuses cited are as of mid-2026 and should be reverified before action.
- **Bias-audit research is model-dependent and shifting:** older LLMs showed pro-white bias; some 2024+ models show reversal, so blanket claims about "AI resume bias" should be tied to specific models and dates.