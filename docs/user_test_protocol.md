# User test: how to run it (22–25 Oct)

Goal: find out whether students would actually consider the careers Pathfinder gives them.
This is the evaluation of the full app (areas, course, lifestyle answers). The survey Hit@k test cannot do this.

## Before you start
1. Pick a start date and time, e.g. `2026-10-22 09:00`. Ratings before it are ignored (your own testing).
2. Write down the emails of the team's own accounts. They are left out of the results.
3. Start the server on the demo PC with MySQL running: `.venv\Scripts\uvicorn backend.main:app`.
   Check http://127.0.0.1:8000/assistant/status shows `sbert:all-MiniLM-L6-v2`.

## Who
- 5–10 students, ideally from different branches and years (not only 4th-year engineering, the survey is already skewed that way).
- Not team members, and not people who helped build the app.
- Write down in your notes how you found them (e.g. "classmates from 3 branches who agreed to help"). The report needs this.

## What to say (consent)
> "We are testing our final-year project, a career guidance website. You will take a 5-minute quiz and rate the careers it suggests.
> Your answers are stored under an account you create, but we only report totals, never names. You can stop at any time."

Only continue if they agree.

## Steps for each student
1. They register their own account and take the quiz on their own. **Do not help them choose answers.**
2. On "My matches" they rate **every** career shown: *Would you consider it? 1–5* (1 = not at all, 5 = definitely).
   They may also press "Not for me" or open a career; that is fine.
3. Optional, at the end, ask one open question and write the answer down: *"Was anything surprising or wrong?"*

## After the test
```powershell
python experiments\user_test.py --since "2026-10-22 09:00" --exclude-emails team1@x.com,team2@y.com
```
This writes `docs/results/user_test/summary.md` (totals only). Put its main numbers in the report:
"share of top-5 careers students would consider (rated 4–5)", by position, and "your areas" vs "also worth a look".

## Do not
- Do not enter answers for a student or "fix" their ratings.
- Do not commit anything with names or emails. The script writes totals only.
- Do not describe the result as accuracy. It is students' own opinion of their matches, from a small group.
