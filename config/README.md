# config/

`india_exclusions.csv` lists O*NET careers that Pathfinder never recommends to Indian students.
Each row is one rule:

| rule | value | meaning |
|---|---|---|
| `title_contains` | a word, e.g. `gambling` | hide every career whose title contains it. The check ignores ", Except ..." so "Entertainment and Recreation Managers, Except Gambling" is **not** hidden. |
| `code` | an O*NET code, e.g. `11-9071.00` | hide exactly this career |

Always write a `reason`: it is shown to students who search for the career, and examiners may ask why
a career was removed. To add a rule, add a line, restart the server, and check the list with
`python scripts\export_career_titles.py` (writes `data/processed/career_titles.csv`).

## industries.csv

The "Explore careers" categories. `soc_prefixes` is a `;`-separated list of O*NET-SOC code beginnings:
`27-4` matches every code starting with `27-4` (media equipment workers), a full code like
`29-1131` matches one career. A career can be in more than one category. Careers hidden by
`india_exclusions.csv` are never listed.

## salary_india.csv

Salaries shown on the career page. **Only add numbers from a source you can cite** (for example a
government survey or a published salary report), with the source name, link and year; the app shows
the source next to the number. Rows: `onet_code` (or empty) and `industry_id` (or empty) - a code row
wins over an industry row. Amounts in lakh per annum (LPA). Leave the file empty rather than guess.
