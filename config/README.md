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
