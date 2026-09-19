# Synthetic evaluation report

`n=30` seed `0` as-of `2026-09-19` renderer/extractor `claude-opus-5`

## Corpus

| property | value |
|---|---|
| profiles sampled | 30 |
| CVs rendered | 30 |
| under-reporting variants | 12 |
| skills deliberately omitted | 42 |
| year-only date variants | 4 |
| overlapping-contract variants | 7 |

| archetype | count |
|---|---|
| senior_backend | 6 |
| junior_backend | 5 |
| devops | 4 |
| mid_backend | 4 |
| career_changer | 3 |
| qa | 3 |
| frontend | 3 |
| non_software | 2 |

## Parser accuracy

**Headline.** Recall splits hard by whether the skill was written in the CV at all. Skills the renderer deliberately omitted are unrecoverable by any parser; that gap is what the restatement channel exists for, not a tuning target.

| skill recall | n | recall |
|---|---|---|
| **stated in the CV text** | 357 | **0.994** |
| **deliberately omitted** | 42 | **0.095** |

| metric | value | demo target |
|---|---|---|
| skills micro-F1 | 0.926 | >= 0.85 |
| skills micro-precision | 0.955 | |
| skills micro-recall (all) | 0.900 | |
| skills macro-F1 | 0.925 | |
| per-skill months MAE | 1.52 | <= 6 months |
| experience months MAE | 0.32 | <= 6 months |
| &nbsp;&nbsp;total_months MAE | 0.00 | |
| &nbsp;&nbsp;software_months MAE | 0.00 | |
| &nbsp;&nbsp;backend_months MAE | 0.97 | |
| education level exact match | 1.000 | >= 0.95 |
| seniority exact match | 0.600 | |
| role count exact | 0.967 | |
| evidence verification rate | 1.000 (n=1301) | |
| hallucination rate | 0.045 | <= 0.02 |

| subset | n | note |
|---|---|---|
| under-reporting CVs | 12 | stated recall 0.983, omitted recall 0.095 |
| year-only dates | 4 | experience MAE 0.00 |
| month-precision dates | 26 | experience MAE 0.37 |

## Recourse

`extracted` runs on parsed profiles; `truth` runs on the ground-truth profiles and isolates solver behaviour from parser error.

| run | pass rate | rejected | validity | actionability | L0 mean | L0 max | cost median | diversity | immutable | no path |
|---|---|---|---|---|---|---|---|---|---|---|
| extracted_A | 0.200 | 24 | 1.000 | 0.542 | 4.08 | 8 | 27.5 | 2.77 | 0.000 | 0.458 |
| extracted_B | 0.033 | 29 | 1.000 | 0.414 | 3.38 | 7 | 23.5 | 2.67 | 0.000 | 0.586 |
| truth_A | 0.200 | 24 | 1.000 | 0.625 | 4.24 | 9 | 22.0 | 2.73 | 0.000 | 0.375 |
| truth_B | 0.033 | 29 | 1.000 | 0.414 | 3.10 | 5 | 27.0 | 2.58 | 0.000 | 0.586 |

## Per-CV

| cv | archetype | under-report | year-only | skills P | skills R | R stated | R omitted | months MAE | exp MAE | roles |
|---|---|---|---|---|---|---|---|---|---|---|
| synth_000.txt | career_changer | no | no | 0.92 | 1.00 | 1.00 | - | 12.4 | 3.7 | 4/4 |
| synth_001.txt | qa | yes | no | 1.00 | 0.71 | 1.00 | 0.00 | n/a | 0.0 | 4/4 |
| synth_002.txt | devops | yes | no | 0.91 | 0.83 | 1.00 | 0.00 | 2.0 | 0.0 | 2/2 |
| synth_003.txt | senior_backend | no | no | 1.00 | 1.00 | 1.00 | - | 4.5 | 0.0 | 3/3 |
| synth_004.txt | qa | no | yes | 1.00 | 1.00 | 1.00 | - | n/a | 0.0 | 1/1 |
| synth_005.txt | mid_backend | no | no | 0.94 | 1.00 | 1.00 | - | 0.0 | 0.0 | 3/3 |
| synth_006.txt | junior_backend | no | no | 1.00 | 1.00 | 1.00 | - | 0.0 | 1.7 | 3/3 |
| synth_007.txt | mid_backend | yes | no | 1.00 | 0.82 | 1.00 | 0.25 | 4.9 | 4.3 | 5/5 |
| synth_008.txt | devops | no | no | 1.00 | 1.00 | 1.00 | - | 1.4 | 0.0 | 3/3 |
| synth_009.txt | senior_backend | no | no | 1.00 | 1.00 | 1.00 | - | 0.0 | 0.0 | 4/4 |
| synth_010.txt | non_software | yes | no | 1.00 | 0.67 | 1.00 | 0.00 | n/a | 0.0 | 3/3 |
| synth_011.txt | junior_backend | yes | no | 1.00 | 0.82 | 1.00 | 0.33 | 0.0 | 0.0 | 2/2 |
| synth_012.txt | devops | yes | no | 1.00 | 0.69 | 0.90 | 0.00 | 0.0 | 0.0 | 2/2 |
| synth_013.txt | mid_backend | no | no | 0.95 | 1.00 | 1.00 | - | 1.8 | 0.0 | 4/4 |
| synth_014.txt | senior_backend | no | no | 0.94 | 1.00 | 1.00 | - | 0.0 | 0.0 | 5/5 |
| synth_015.txt | senior_backend | yes | no | 1.00 | 0.75 | 1.00 | 0.20 | 0.0 | 0.0 | 4/4 |
| synth_016.txt | career_changer | no | no | 0.91 | 1.00 | 1.00 | - | 3.7 | 0.0 | 4/4 |
| synth_017.txt | devops | yes | yes | 0.92 | 0.71 | 1.00 | 0.00 | 0.0 | 0.0 | 4/4 |
| synth_018.txt | junior_backend | no | no | 0.92 | 1.00 | 1.00 | - | 0.9 | 0.0 | 3/3 |
| synth_019.txt | junior_backend | no | no | 1.00 | 1.00 | 1.00 | - | 0.0 | 0.0 | 2/2 |
| synth_020.txt | mid_backend | no | no | 0.95 | 1.00 | 1.00 | - | 0.0 | 0.0 | 3/3 |
| synth_021.txt | senior_backend | yes | yes | 0.93 | 0.70 | 0.93 | 0.00 | 0.0 | 0.0 | 4/4 |
| synth_022.txt | frontend | no | no | 0.91 | 1.00 | 1.00 | - | 1.5 | 0.0 | 4/4 |
| synth_023.txt | frontend | yes | yes | 0.82 | 0.75 | 1.00 | 0.00 | 3.0 | 0.0 | 3/3 |
| synth_024.txt | frontend | no | no | 0.91 | 1.00 | 1.00 | - | 0.0 | 0.0 | 2/2 |
| synth_025.txt | career_changer | no | no | 1.00 | 1.00 | 1.00 | - | 6.5 | 0.0 | 3/3 |
| synth_026.txt | junior_backend | no | no | 0.93 | 1.00 | 1.00 | - | 0.0 | 0.0 | 2/2 |
| synth_027.txt | senior_backend | yes | no | 0.88 | 0.70 | 1.00 | 0.00 | 0.7 | 0.0 | 6/6 |
| synth_028.txt | non_software | yes | no | 1.00 | 1.00 | 1.00 | 1.00 | n/a | 0.0 | 4/4 |
| synth_029.txt | qa | no | no | 1.00 | 1.00 | 1.00 | - | 0.0 | 0.0 | 2/1 |

