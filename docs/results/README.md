# No-survey experiments (Phase B)

These experiments check engine v2 **before any survey data exists**. Every "student" in them is
**synthetic**: it is built from a career's own O*NET profile. They show whether the scoring formulas
behave sensibly. They are **not accuracy results**, and none of these numbers may be described as
"the system is X% accurate".

## Status

**Run on the real O*NET 31.0 data on 21 Oct 2026** (910 rankable careers). The numbers are in `summary.md`,
generated directly from the CSVs, so nothing is copied by hand. B1 also includes **V3** (engine v3 with the app's
weights). Note: V3's strength fit compares rating *shapes* with importance, and the synthetic student is built
from the same career's levels, so V3 is partly favoured in B1. B2 and B3 test engine v2's weights and ranges.

## How to run (Windows PowerShell, project root, `.venv` active, O*NET in `data/raw/onet/`)

```powershell
python experiments\self_match.py           # about 1-2 minutes
python experiments\weight_sensitivity.py   # about 1 minute
python experiments\masking.py              # about 4-5 minutes
python experiments\summarise.py            # writes docs/results/summary.md from the CSVs
```

(These times were measured on a 900-career throw-away dataset in the development session. Your PC may differ.)
Add `--limit 20` to any experiment for a quick trial run on the first 20 careers.

## What each experiment tests

### B1. Self-match: `self_match.csv`, `self_match_summary.csv`

For each rankable career, a synthetic "perfect student" is made from that career's O*NET profile:
interest = (OI − 1) / 6 × 4 + 1; each skill/subject survey row = mean over its elements of LV / 7 × 4 + 1,
clipped to 1–5. All careers are then ranked (no Job Zone filter, no diversity re-ranking) by three methods:

| Method | Skills and subjects scored by |
|---|---|
| V0 | v1's Pearson correlation between the student's ratings and the career's importance (IM) profile |
| V1 | the same correlation, each element weighted by w = (IM − 1) / 4 |
| V2 | engine v2 readiness: sum(w × met) / sum(w) |

Interests use Pearson on the RIASEC scores in all three. Ties are broken by interest fit, then by code.

| Column | Meaning |
|---|---|
| pct_own_in_top5 / top10 | % of synthetic students whose own career is in the top 5 / top 10 |
| median_own_rank | median position of the own career (1 = first) |
| pct_top1_in_own_field | % where the first career is in the same SOC major group as the own career |
| mean_ties_at_top, pct_students_with_tie_at_top | how often several careers share exactly the best score |

**Why ties matter for V2:** readiness ignores a surplus, so a career that needs *less* than the student
has also gets full readiness. Several careers can reach the same top score, and only interest fit
separates them.

### B2. Weight sensitivity: `weight_sensitivity.csv`

Each component weight (interest 0.25, skill 0.30, subject 0.15) is changed by +10% and −10% in turn, the
weights are renormalised, and V2 is re-run on the B1 synthetic students. Top-5 overlap = careers shared
with the base top 5 ÷ 5. Reported: mean and minimum overlap, and % of students with an identical top 5.
A high overlap means the ranking does not depend on the exact (untuned) starting weights.

### B3. Masking: `masking.csv`

For each B1 synthetic student, the 1, 2 and 3 most important answered rows for the student's own career
(sum of w over the row's elements; ties broken randomly with seed 42) are set to "Can't assess".
Two methods are compared with the full-answer result:

- **naive**: unknown elements are dropped from the denominator (a category with no known element counts as 0.5)
- **range** (engine v2): unknowns stay in the denominator, low/high bounds, ranked by the low bound

| Column | Meaning |
|---|---|
| mean_inflation | mean of (score − full score) over all student × career pairs (range: low bound) |
| mean_abs_error | mean of the absolute difference |
| false_top5_entries | careers in the top 5 that are not in the full top 5 **and** scored higher than with full answers |
| top5_overlap | careers shared with the full top 5 ÷ 5 |
| pct_contains_full | range: % of pairs with low ≤ full ≤ high; naive: % of pairs where the score equals the full score |
| top5_overlap_after_follow_ups | range only: answer the follow-up questions shown for the top 5 with their true values, re-rank |

Some range-method values are **guaranteed by the formulas** (and checked by `tests/test_experiments.py`):
mean_inflation ≤ 0, false_top5_entries = 0, pct_contains_full = 100. They show the method works as designed.
The informative numbers are the naive method's inflation and false entries, and the top-5 overlap before
and after the follow-up questions.

## Limitations (write these in the report)

1. **Synthetic, circular data.** The students are copies of O*NET careers, scored against the same O*NET
   data. Real students are not copies of a career, so real performance will be lower and different.
2. **Not accuracy.** No real student's career outcome or choice is used. Accuracy needs the survey
   (Hit Rate@5 of the student's aimed field, Q8) and later follow-up data.
3. **Perfect, continuous answers.** Synthetic ratings are exact decimals. Real students answer whole numbers
   1–5 and are biased (over- or under-rating themselves); the self-rating → level mapping is approximate.
4. **Levels built from LV, compared with IM.** V0/V1 compare against importance (IM) profiles; the synthetic
   ratings come from levels (LV). These are correlated in O*NET but not identical.
5. **No Job Zone filter or diversity** in the experiments, so the numbers describe the raw ranking, not the
   final list a student sees.
6. **Masking order.** Only the most important rows are hidden; real students may skip any row.
