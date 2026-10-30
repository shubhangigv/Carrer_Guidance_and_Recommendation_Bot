# Pathfinder: AI-Based Multi-Domain Career Guidance and Recommendation System

Final-year project. A student takes a short quiz; Pathfinder recommends careers from **every field**
(about 900 careers from O*NET, not IT only), explains each match from the student's own answers,
shows the skills to build and a step-by-step roadmap, and answers questions in a career chatbot.

## How it works (one paragraph per part)

1. **Quiz** (`frontend/app/quiz.js`): areas the student wants to work in (optional), course, 6 interests,
   8 skills (+ 3 strongest / 2 weakest), 8 subjects, kind of workday, further study, city, "about you".
2. **Engine v3** (`ml/recommender_v3.py`): for every career, *interest fit* (RIASEC, Pearson), *readiness*
   (do your skill/subject levels meet O*NET's required levels?) and *strength fit* (are your strongest rows the
   ones this career relies on most?). Unanswered questions give a score range, never a higher score.
3. **Field model** (`ml/field_model.py`): Logistic Regression trained on the student survey predicts the field a
   student with these answers and this course usually aims for. Used when the student picks no areas.
4. **Personalisation** (`ml/preferences.py`): areas the student picked come first (7 places), then 3 "also worth a
   look"; lifestyle filters (desk/active from O*NET Work Context, no further study from Job Zones); careers that
   need the student's weak points go last and say why; "Not for me" hides a career.
5. **Text matching** (`ml/semantic.py`): Sentence-BERT matches "about you" to career descriptions by meaning.
6. **Career pages, roadmap, chatbot** (`ml/career_needs.py`, `ml/pathways.py`, `backend/assistant.py`):
   every important skill (have / build), Indian education routes, a roadmap with progress, and a Gemini chatbot
   that answers only from our career records.

Results and limitations: `docs/report/results_tables.md` (generated from `docs/results/`).

## Setup on a new PC (Windows PowerShell, from the project folder)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu    # small CPU-only PyTorch
pip install -r requirements-ml.txt                                     # Sentence-BERT
Copy-Item .env.example .env                                            # then edit .env (below)
```

1. **O*NET data:** download https://www.onetcenter.org/dl_files/database/db_31_0_text.zip and extract it into
   `data\raw\onet\` (not in Git).
2. **`.env`:** set `JWT_SECRET` to a long random string
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) and your MySQL password. Optional:
   `GEMINI_API_KEY` (free at https://aistudio.google.com) for the chatbot. All settings are explained in `.env.example`.
3. **MySQL** (recommended; without it accounts are kept in memory and lost on restart): install MySQL Server +
   Workbench, run `CREATE DATABASE career_guidance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`, then
   `python scripts\load_onet_to_mysql.py`. New tables and columns (`database/migrations/`) are added
   automatically when the server starts.
4. **Survey file (team PC only):** save the Google Form responses as `data\raw\survey\responses.csv`
   (git-ignored, never commit it). Without it the app works, but the field model is off.

## Run

```powershell
.venv\Scripts\uvicorn backend.main:app --reload
```

* Student app: **http://127.0.0.1:8000/app/**
* API documentation (try every endpoint): http://127.0.0.1:8000/docs
* Health check: http://127.0.0.1:8000/health (`"data_source": "mysql"` or `"files"`)

The first minute after starting, "matches for your own words" may say the matcher is still starting
(Sentence-BERT is loading). Close large programs if the PC is low on memory.

| Page | What it does |
|---|---|
| Quiz `#/quiz` | one question at a time; review screen before submitting |
| My matches `#/matches` | 10 careers grouped "your areas" / "also worth a look", reasons, "What you'd do", "Not for me", 1–5 rating, matches for your own words |
| Career `#/career/<id>` | description, how to get there in India, skills to build / you have, salary (cited only), job links, similar careers |
| Roadmap `#/roadmap/<id>` | qualification → skills by priority → experience → applying; ticks are saved |
| Explore `#/explore` | 27 industries and search by job title |
| Ask `#/assistant` | career chatbot (Gemini; offline list of careers without a key) |

## Tests and experiments

```powershell
pytest -q -rs                                   # all tests (MySQL tests skip if MySQL is not running)
python experiments\survey_analysis.py           # survey charts and counts
python experiments\survey_insights.py           # answer quality, branch vs aim, which answers separate fields
python experiments\hit_rate.py                  # Hit Rate@1/3/5 of the aimed field vs random
python experiments\tune_weights.py              # cross-validated weight tuning
python experiments\ml_compare.py                # ML models vs the engine
python experiments\model_features.py            # which answers the field model should use
python experiments\hybrid.py                    # ML field + engine, cross-validated
python experiments\later_responses.py           # the same on ALL responses (the ones above use the first 87)
python experiments\user_test.py --since 2026-10-22 --exclude-emails team@x.com   # after the user test
python experiments\report_tables.py             # rebuild docs/report/results_tables.md
```

The O*NET-only checks (synthetic students) are in `docs/results/README.md`. The user test procedure is in
`docs/user_test_protocol.md`.

## Settings you can change without code (`config/`)

| File | What it holds |
|---|---|
| `areas.csv` | the 17 areas a student can pick, as O*NET-SOC code prefixes |
| `course_areas.csv` | each course → its areas and the matching survey branch option |
| `career_paths.csv` | Indian education routes with official links. **AI drafts, `verified = no`** until the team checks each row on the official site; set `SHOW_UNVERIFIED_ROUTES=no` in `.env` to show only checked routes |
| `india_exclusions.csv` | careers never recommended in India, each with a reason |
| `industries.csv` | the Explore categories |
| `salary_india.csv`, `courses.csv` | salaries and courses, **only with a source / checked date** (empty until the team adds them) |
| `survey_field_map.csv` | survey field → O*NET codes; fixed before any result, do not tune |

## Rules the project follows

* No invented numbers: every result comes from a script in `experiments/`, and the report tables are generated.
* Raw survey responses never leave the team PC; the field model is trained in memory and never saved.
* Gender, religion, caste and other sensitive attributes are never used.

## Data and licence

O*NET 31.0 Database, National Center for O*NET Development, CC BY 4.0
(https://www.onetcenter.org/db_releases.html). Raw files are not stored in this repository.


