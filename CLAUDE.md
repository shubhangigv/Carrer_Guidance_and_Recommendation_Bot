# CLAUDE.md: project context for AI assistants

Read this file before writing or changing code in this repository.

## Project

**AI-Based Multi-Domain Career Guidance and Recommendation System** (working name "Pathfinder").
Final-year college project. It recommends careers from every field (not IT-only, including niche jobs)
to a student, explains each match from the student's own answers, finds skill gaps and builds a
learning roadmap. Later: jobs, resume analysis and a RAG chatbot.

The developers are students learning as they build. When you write code:
explain what it does and why, keep files small and readable, give exact file paths,
give Windows PowerShell commands, and say how to run and verify it.

## Hard rules

- Never invent results, accuracy numbers, datasets, citations or salaries. Only report experiments that were actually run.
- No student data exists yet. Do not create fake "student datasets" and present them as real.
- Never modify files in `data/raw/`. Write derived files to `data/cleaned/` or `data/processed/`.
- Never put passwords or keys in code. Use a `.env` file (git-ignored) and `python-dotenv`.
- Inspect real file columns before using them; do not assume names (O*NET 31.0 renamed several files).
- Do not use gender, religion, caste or other sensitive attributes as recommendation inputs.
- Keep the architecture below unless the team agrees to change it.

## Status (updated 10 Oct 2026)

| Part | Status |
|---|---|
| O*NET exploration, baseline engine v1, prototype, survey script | DONE |
| MySQL schema (`database/schema.sql`), `backend/db.py`, loader, files-vs-MySQL tests | DONE |
| `assessment_rating.answer_status` (migration `database/migrations/002_answer_status.sql`) | DONE |
| Engine v2 (`ml/recommender_v2.py`, spec in "Design decisions v2") | NOT done |
| No-survey experiments (`experiments/`, results in `docs/results/`) | NOT done |
| FastAPI backend (`backend/main.py`) | NOT done |
| Prototype calls the API, `engine.js` v2 | NOT done |
| Survey sent, survey analysis, ML comparison | NOT done (no survey data yet) |

## Plan to the deadline (whole project finished by 31 Oct 2026)

- 10-16 Oct: Phase A (engine v2) + Phase B (no-survey experiments).
- 17-23 Oct: Phase E (FastAPI) + survey analysis.
- 24-31 Oct: Phase F (connect the prototype to the API, `engine.js` v2), ML comparison, report, demo.

## Stack and decisions

| Area | Choice |
|---|---|
| Language | Python 3.13 (Windows, VS Code, `.venv`) |
| Data / ML | pandas, NumPy, scikit-learn; later XGBoost, sentence-transformers |
| Database | **MySQL + MySQL Workbench**, SQLAlchemy + PyMySQL (`backend/db.py`, settings from `.env`) |
| Backend | FastAPI (planned) |
| Frontend | React (planned); a working single-file prototype exists |
| Data source | O*NET 31.0 (Aug 2026, CC BY 4.0); later ESCO v1.2.1 and India's NCO-2015 via ISCO-08 codes |

Recommendations work in two levels: career family first, then specific careers.
The core engine is knowledge-based (no training needed, works for a brand-new student).
Supervised ML is an experiment compared against it once survey data exists.

## Repository layout

```
ml/baseline_recommender.py      the recommendation engine (load O*NET, match, explain, skill gaps)
notebooks/01_explore_onet.ipynb  data exploration
notebooks/02_baseline_demo.ipynb demo on two test profiles + careers.json export
scripts/inventory_onet.py        lists every O*NET file with rows and columns
frontend/prototype/pathfinder.html  working browser prototype (engine ported to JavaScript)
frontend/prototype/engine.js     the JavaScript engine on its own (same results as Python)
tools/create_career_survey.gs    Google Apps Script that builds the 9-question student survey
tests/test_baseline_recommender.py  pytest tests with a tiny fake O*NET folder (tests/fake_onet.py)
tests/test_mysql_matches_files.py   files vs MySQL give identical results (skipped if MySQL is not running)
database/schema.sql              the 13 MySQL tables (CREATE TABLE IF NOT EXISTS)
database/migrations/            ALTER scripts for an existing database (002_answer_status.sql)
backend/db.py                    get_engine() from .env, run_sql_file()
scripts/load_onet_to_mysql.py    creates the tables and upserts O*NET into them (re-runnable)
data/raw/onet/                   O*NET text files (not in Git; download separately)
```

## O*NET 31.0 facts (verified on the real files)

- 46 `.txt` files, tab-separated. 1,016 occupations; **910** have interest + skill + knowledge data and are ranked.
- Files used: `Occupation Data.txt` (O*NET-SOC Code, Title, Description), `Career Interest Types.txt`,
  `Essential Skills.txt` (10 skills), `Transferable Skills.txt` (25 skills), `Knowledge.txt` (33 areas), `Job Zones.txt`.
- Rating columns: O*NET-SOC Code, Element ID, Element Name, Scale ID, Data Value, N, Standard Error,
  Lower CI Bound, Upper CI Bound, Recommend Suppress, Not Relevant, Date, Domain Source.
  (`Career Interest Types.txt` has only O*NET-SOC Code, Element ID, Element Name, Scale ID, Data Value, Date, Domain Source.)
- Scales: IM importance 1–5, LV level 0–7, OI RIASEC interest 1–7, IH interest high-point codes.
- Other files available but unused so far: Abilities (52), Work Styles, Task Statements, Work Activities,
  Work Context, Software Skills, Job Titles, Sample of Reported Titles, Related Occupations, Education, Emerging Tasks.
- Not verified yet: the exact columns of `Job Zones.txt`, `Job Titles.txt`, `Related Occupations.txt`, `Work Styles.txt`. Inspect before use.

## How the baseline works (ml/baseline_recommender.py)

- Student input (all 1–5): `interests` (6 RIASEC types), `skills` (16 questionnaire skills, see `SKILL_MAP`),
  `subjects` (10 subjects, see `SUBJECT_MAP`). Questionnaire items map to O*NET element names.
- For each career: part score = (r + 1) / 2, where r = Pearson correlation between the student's profile and
  the career's profile, computed for interests (OI), skills (IM) and knowledge (IM).
- Profile Match Score = (0.30 skills + 0.25 interests + 0.15 subjects) / 0.70 × 100. Starting weights, to be tuned.
- Skill gap: student level = (rating − 1) / 4 × 7; gap = O*NET LV − student level; priority = IM × gap;
  shown when IM ≥ 3 and gap > 0.5.
- Missing values: filled with the career's row mean. Flat answers give a neutral 50. Job Zone filter (≥ 3) for students.
- Reasons come only from the student's own answers.
- Known weaknesses: the top 5 can all be in one field (needs diversity re-ranking); preferences/values not in the score;
  `Recommend Suppress = Y` ratings not filtered; self-rating to level mapping is approximate.

Sanity results on real O*NET 31.0 (hand-made profiles, NOT accuracy):
biology/research profile → Biochemists and Biophysicists 81, Bioinformatics Scientists 80, Medical Scientists 79;
arts/communication profile → Talent Directors 90, Music Directors and Composers 89, Producers and Directors 88.

## Design decisions v2 (engine v2 spec, follow this in future sessions)

Engine v2 lives in `ml/recommender_v2.py` and reuses the loaders in `ml/baseline_recommender.py`.
v1 stays: `recommend_v1` / `explain_v1`, with the old names `recommend` / `explain` kept as aliases.

**A1. Inputs (match the survey).** `interests`: 6 RIASEC values, 1-5, always answered.
`skills`: 8 survey rows; `subjects`: 8 survey rows. Each skill/subject answer is `{"rating": 1-5}`,
`"no_experience"` / `"not_studied"`, or `"cant_assess"`. `SKILL_MAP_V2` and `SUBJECT_MAP_V2` map rows to O*NET
element names (check every name exists in the real files; `check_maps()` prints missing ones):
- Skills: Mathematics -> Mathematics; Programming -> Programming; Problem Solving -> Complex Problem Solving,
  Critical Thinking; Research -> Science, Active Learning; Communication -> Speaking, Active Listening;
  Writing -> Writing, Reading Comprehension; Leadership -> Coordination, Persuasion, Negotiation,
  Management of Personnel Resources; Technical/Practical Skills -> Troubleshooting, Repairing,
  Equipment Maintenance, Operation and Control.
- Subjects: Mathematics -> Mathematics; Physics/Chemistry -> Physics, Chemistry; Biology -> Biology;
  Computer Science -> Computers and Electronics; Commerce/Economics -> Economics and Accounting;
  Languages -> English Language, Foreign Language; Social Sciences -> Sociology and Anthropology, Psychology,
  History and Archeology, Geography; Arts/Design -> Fine Arts, Design.
- A merged row gives the same answer to every element it maps to. An element in two rows uses the mean of the
  known answers. Only mapped elements are scored; unmapped O*NET elements are outside the questionnaire (not "unknown").

**A2. Data cleaning on load.** Rating rows with `Recommend Suppress = "Y"` are ignored (in `load_onet()`, so the
MySQL loader stores the cleaned values and the files-vs-MySQL test stays equal). Job Zone >= 3 filter for students.

**A3. Interest fit.** Pearson on RIASEC OI scores, part = (r + 1) / 2. Flat answers give 0.5.

**A4. Readiness** (skills and subjects separately). For each mapped element with importance IM and required level LV:
w = (IM - 1) / 4; student level L = (rating - 1) / 4 x 7; no_experience / not_studied -> L = 0;
met = 1 - max(0, LV - L) / 7; readiness = sum(w x met) / sum(w). A surplus never lowers the score.

**A5. Unknowns (`cant_assess`) give a range.** Lower bound: unknown -> L = 0. Upper bound: unknown -> met = 1.
Unknowns are never dropped from the denominator. Match low/high = (0.25 interest + 0.30 skill readiness +
0.15 subject readiness) / 0.70 x 100 (weights in one constant). **Rank by the lower bound**, so a missing answer
can never push a career up.

**A6. Coverage and display.** Coverage = sum(w of known elements) / sum(w of all mapped elements).
Critical unknown = unknown element with IM >= 4. Display (constants at the top of the file):
unknown share <= 20% and no critical unknown -> "score"; 20-50% or any critical unknown -> "range" + up to 3
follow-up questions (survey rows ordered by sum of w x (upper - lower) of their elements); > 50% -> "withheld"
(show interest fit only).

**A7. Field diversity.** Field = SOC major group (first 2 digits, `SOC_MAJOR_GROUPS`). At most 2 careers per field
in the top 5 (greedy re-rank, then fill the rest normally).

**A8. Functions.** `recommend_v2(student, data, top_n=10, min_job_zone=3, diversity=True)` -> DataFrame with code,
career, field, interest_fit, skill_low, skill_high, subject_low, subject_high, match_low, match_high, coverage,
critical_unknowns, display, follow_ups. `explain_v2(student, data, code)` -> reasons (only from the student's own
answers, ranked per career, max 2 interest, 2 skill, 2 subject) and gaps (gap = LV - L, shown if IM >= 3 and
gap > 0.5, priority = IM x gap; no_experience gaps labelled "start from scratch"; unknown elements listed as
"not assessed - answer to check"). `target_career(student, data, code)` -> questions needed (mapped rows whose
elements have IM >= 3 and are unanswered/unknown), readiness range, gaps, interest fit check, up to 5 nearby
alternatives (`Related Occupations.txt` if its columns are usable, else nearest careers by profile).

**A9. Tests** in `tests/test_recommender_v2.py` (fake O*NET helper): surplus never lowers readiness;
cant_assess never raises match_low and match_low <= match_high; all rated -> low == high and coverage 1;
no_experience lowers readiness vs rating 3 and gives a "start from scratch" gap; unknowns stay in the
denominator (manual calculation); diversity max 2 per field in the top 5; suppressed rows ignored; display
thresholds; matching profile ranks first; flat interests -> 0.5; all v1 tests still pass.
Demo: `notebooks/03_engine_v2_demo.ipynb` (hand-made test profiles, not real students).

## Database (MySQL, 13 tables, from the ER diagram; built in `database/schema.sql`)

- `load_from_mysql(engine)` in the engine returns the same dict as `load_onet()`; both go through `_pivot()`.
- `career` holds every occupation in `Occupation Data.txt`; only careers with interest + skill + knowledge data are ranked.
- Ratings are DECIMAL(5,2), the precision O*NET publishes; the loader warns if a value would be rounded.
- Tested against MariaDB 10.11 with fake O*NET data; the real-data comparison test runs on the team's PC.

| Table | Columns |
|---|---|
| student | student_id PK, name, email, password_hash, education_level, degree, year_of_study |
| assessment | assessment_id PK, student_id FK, completed_at |
| assessment_rating | assessment_id FK, category, item, rating (1–5, NULL if not rated), answer_status (rated / no_experience / not_studied / cant_assess) |
| recommendation | rec_id PK, student_id FK, career_id FK, assessment_id FK, match_score, reasons, model_version, created_at |
| career | career_id PK, onet_code, title, description, domain, job_zone, source |
| skill | skill_id PK, name, category |
| career_skill | career_id FK, skill_id FK, importance (1–5), required_level (0–7) |
| interest | interest_id PK, name (RIASEC) |
| career_interest | career_id FK, interest_id FK, score (1–7) |
| knowledge | knowledge_id PK, name |
| career_knowledge | career_id FK, knowledge_id FK, importance (1–5), level (0–7) |
| course | course_id PK, skill_id FK, title, provider, url (later phase) |
| job | job_id PK, career_id FK, title, company, location, posted_on, source_url (later phase) |

## Roadmap (next tasks, in order)

1. ~~MySQL~~ done; confirm on the real data: run the loader, then `pytest -q -rs` (expect 910 ranked careers).
1b. Engine v2 + no-survey experiments (Phase A + B, spec above).
2. **FastAPI** in `backend/`: `POST /assessment`, `POST /recommend`, `GET /careers/{id}`; save recommendations; Swagger at `/docs`.
3. **Frontend**: prototype calls the API; then React with the same screens.
4. **Survey** (Google Form from `tools/create_career_survey.gs`, 1st–3rd year students): analysis notebook;
   map form answers to engine input (form has 6 interest rows, 8 skills, 8 subjects incl. merged
   "Physics/Chemistry" and "Commerce/Economics"); Hit Rate@5 of the student's aimed field (Q8).
5. **ML**: Logistic Regression, Random Forest, SVM, XGBoost predicting career family; stratified split, 5-fold CV,
   Pipelines (no leakage), macro-F1. Then Sentence-BERT (`all-MiniLM-L6-v2`) and a hybrid score tuned for NDCG@5.
6. Later: ESCO, NCO-2015, jobs, resume analyser, RAG chatbot, evaluation, report.
