# Pathfinder: AI-Based Multi-Domain Career Guidance and Recommendation System

Final-year project. Recommends careers from every field to a student, explains each recommendation
from the student's own answers, finds skill gaps, and builds a learning roadmap.

## Status

| Part | Status |
|---|---|
| Literature survey (11 papers), research gap, architecture, ER diagram, UI mockups | Done |
| O*NET 31.0 data explored (`notebooks/01_explore_onet.ipynb`) | Done |
| Baseline recommender with explanations and skill gaps (`ml/baseline_recommender.py`) | Done |
| Working browser prototype (`frontend/prototype/pathfinder.html`) | Done |
| Tests for the engine (`tests/`) | Done |
| Student survey script (`tools/create_career_survey.gs`, 9 questions, "No experience" / "Can't assess" options) | Ready, not sent yet |
| MySQL database: 13-table schema, O*NET loader, engine reads from MySQL, files-vs-MySQL tests (`database/`, `backend/db.py`) | Done (verify on your PC with the real O*NET data) |
| `answer_status` for answers without a number (`database/migrations/002_answer_status.sql`) | Done |
| Engine v2: readiness, score ranges for unknown answers, field diversity (`ml/recommender_v2.py`) | Done (verify on real O*NET) |
| No-survey experiments (`experiments/`, `docs/results/`) | Scripts done; run them on real O*NET (see `docs/results/README.md`) |
| FastAPI backend: auth, assessment, recommendations, search, target career (`backend/main.py`) | Done |
| Prototype connected to the API, `engine.js` v2, React | Not done (24-31 Oct) |
| ML comparison, Sentence-BERT, hybrid ranking | After survey data |
| ESCO, NCO-2015, jobs, resume analyser, RAG chatbot | Later |

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Download the O*NET 31.0 text database from
https://www.onetcenter.org/dl_files/database/db_31_0_text.zip and extract it into `data/raw/onet/`.

### MySQL (Phase 1)

1. Install MySQL Server and MySQL Workbench. In Workbench, run:
   `CREATE DATABASE career_guidance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
2. `Copy-Item .env.example .env`, then put your MySQL password in `.env` (never commit `.env`).
3. `python scripts\load_onet_to_mysql.py` creates the 13 tables from `database/schema.sql`, fills them
   from O*NET and prints the row counts. It is safe to run again (no duplicates).
4. Database created before October 2026? Run the migration once (safe to repeat):
   `python -c "from backend.db import get_engine, run_sql_file; run_sql_file(get_engine(), 'database/migrations/002_answer_status.sql')"`
5. `pytest -q -rs` checks that MySQL and the `.txt` files give identical recommendations.

### API (FastAPI)

1. `pip install -r requirements-dev.txt` (adds FastAPI, uvicorn, bcrypt, PyJWT, httpx).
2. In `.env` set `JWT_SECRET` to a long random string:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"` (see `.env.example`).
3. Start the server: `uvicorn backend.main:app --reload`
4. Open http://127.0.0.1:8000/docs. Try `POST /auth/register`, then `POST /auth/login`, copy `access_token`,
   click **Authorize** (top right) and paste it. Then `POST /assessment` → `GET /recommend`.
5. `GET /health` shows where the data comes from: `"data_source": "mysql"` (O*NET loaded into MySQL) or
   `"files"` (MySQL not running or empty; then accounts and answers are kept in memory and lost on restart).

| Endpoint | Login? | What it does |
|---|---|---|
| `POST /auth/register`, `POST /auth/login` | no | create an account (bcrypt-hashed password), get a token |
| `POST /assessment` | yes | save the survey answers (rating 1-5, `no_experience`, `not_studied`, `cant_assess`) |
| `GET /recommend?assessment_id=&top_n=` | yes | engine v2 top careers (score / range / withheld, follow-ups, reasons); saved with `model_version = v2` |
| `GET /careers/search?q=` | no | search by title and O*NET alternate titles |
| `GET /careers/{career_id}` | no | description, field, Job Zone |
| `GET /target/{career_id}/questions?assessment_id=` | yes | survey rows still needed for that career |
| `POST /target/{career_id}` | yes | readiness range, gaps, interest check, nearby alternatives |
| `GET /health` | no | data source, storage, number of careers |

## Run

| What | How |
|---|---|
| List O*NET files | `python scripts\inventory_onet.py` |
| Explore the data | open `notebooks/01_explore_onet.ipynb` |
| Get recommendations (v1) | open `notebooks/02_baseline_demo.ipynb` and Run All |
| Engine v2 demo (v1 vs v2, ranges) | open `notebooks/03_engine_v2_demo.ipynb` and Run All |
| No-survey experiments | see `docs/results/README.md` (`python experiments\self_match.py` etc.) |
| Prototype | open `frontend/prototype/pathfinder.html` in a browser; load `docs/careers.json` (made by notebook 02's last cell) in the Data tab for real data |
| Load O*NET into MySQL | `python scripts\load_onet_to_mysql.py` |
| API | `uvicorn backend.main:app --reload`, then open http://127.0.0.1:8000/docs |
| Tests | `pip install -r requirements-dev.txt` then `pytest -q -rs` (MySQL tests are skipped if MySQL is not running) |
| Create the survey | paste `tools/create_career_survey.gs` into script.google.com and run it |

## How the baseline works

Each career is compared with the student on interests (6 RIASEC types), skills and subjects.
Each part is the Pearson correlation between the two profiles, rescaled to 0–1.

```
Profile Match Score = (0.30 × skills + 0.25 × interests + 0.15 × subjects) / 0.70 × 100
Skill gap           = required level (O*NET LV, 0–7) − student level (self-rating mapped to 0–7)
Gap priority        = importance × gap
```

The score measures profile similarity, not a probability of success. Weights are starting values.

## Data

O*NET 31.0 Database, National Center for O*NET Development, CC BY 4.0
(https://www.onetcenter.org/db_releases.html). Raw files are not stored in this repository.

See `CLAUDE.md` for full project context, design decisions and the roadmap.
