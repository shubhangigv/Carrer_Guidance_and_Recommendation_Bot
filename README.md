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
| Student survey script (`tools/create_career_survey.gs`) | Ready, not sent yet |
| MySQL database | Designed (ER), not built |
| FastAPI backend, React frontend | Next |
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

## Run

| What | How |
|---|---|
| List O*NET files | `python scripts\inventory_onet.py` |
| Explore the data | open `notebooks/01_explore_onet.ipynb` |
| Get recommendations | open `notebooks/02_baseline_demo.ipynb` and Run All |
| Prototype | open `frontend/prototype/pathfinder.html` in a browser; load `docs/careers.json` (made by notebook 02's last cell) in the Data tab for real data |
| Tests | `pip install -r requirements-dev.txt` then `pytest -q` |
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
