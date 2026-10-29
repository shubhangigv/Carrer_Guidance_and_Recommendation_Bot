# Pathfinder: demo script and viva sheet

Print this page. The full details are in `docs/PROJECT_GUIDE.txt`; every number here comes from
`docs/report/results_tables.md`.

## Before the demo (10 minutes earlier)

1. Close other programs and browser tabs (the PC is low on memory).
2. Start MySQL (service MySQL80), then in the project folder:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   uvicorn backend.main:app --reload
   ```
3. Wait about 1 minute (Sentence-BERT loads in the background), then open http://127.0.0.1:8000/app/.
   Check http://127.0.0.1:8000/health.
4. Make two fresh accounts in advance (e.g. `demo1@test.com`, `demo2@test.com`) so you are not typing
   during the demo.
5. Check internet access for the chatbot (`GEMINI_API_KEY` in `.env`). If it fails, skip step 6 below.

## The 5-minute demo

| Time | What you do | What you say |
|---|---|---|
| 0:00 | Show the home page | "Most students get no career guidance: in our survey of 87 students, 89.7% had no counsellor or got no help. Pathfinder recommends careers from every field, not just IT, and explains each one." |
| 0:30 | **Quiz** (account 1): pick 1-2 areas (e.g. Healthcare), a course, rate interests, skills and subjects, pick 3 strongest and 2 weakest skills, a workday and a place, and type a sentence in the last box | "One question per screen. The ratings are the 6 RIASEC interest types and 16 skill and subject rows, mapped to O*NET, the US government's database of about 900 careers." |
| 1:30 | **My matches**: show "In your areas" and "Also worth a look" | "Every career is scored by our engine: interest fit, readiness (do your levels meet what the career needs) and strength fit (are your best skills the ones this career relies on). The reasons come only from your own answers." |
| 2:15 | Open one career: "What you'd do", **Skills to build** / **You have this**, **How to get there** | "For each career: the skills you have, the ones to build, and an Indian education route." |
| 2:45 | Click **Not for me** on one career and show it disappear; give a **Would you consider it?** rating | "Students can hide careers, and rate each one; that is our user-test data." |
| 3:15 | **Quiz** (account 2): pick NO areas, pick a course, and rate Programming and Arts/Design low (pick them as weakest) | "Here the student picks no areas, so our trained model suggests a field." |
| 3:45 | **My matches**: show **Suggested field** | "A Logistic Regression model, trained on our survey, predicts the field. It fills the first 3 places, and the engine ranks careers inside it. Careers that need the student's weak points are moved back, so a student weak in coding and design no longer gets Game Designer." |
| 4:15 | **Ask**: e.g. "What does a pharmacist do and what should I study?" | "The chatbot first finds the matching career records, then Gemini answers from them only (RAG)." |
| 4:40 | Close with the results | "Tested on 81 students: our hybrid puts the field a student aims for first for 66.4% of them, against 9.0% for random choice and 14.8% for the engine alone." |

If something fails: stay calm and say what it would show. You can also open `/docs` (the API page) and run
`GET /recommend` there.

## Numbers to remember

| What | Number |
|---|---|
| Survey | 87 analysed responses (closed 26 Oct); 52 more later (139 in total), reported separately |
| Problem | 89.7% no counsellor or no help; 23.0% unsure of their path; 54 of 87 would use an AI tool (29 maybe) |
| Careers | O*NET 31.0: 910 rankable, 903 after the India rules |
| Hit@1 / Hit@5 (81 students) | Hybrid (answers + branch) **66.4% / 71.4%**; answers only 57.0% / 66.2%; engine v3 14.8% / 35.8%; random 9.0% / 36.2% |
| Field model (77 students, 5 fields) | Logistic Regression 60.5% accuracy, macro-F1 0.527; with branch 69.6% / 0.636; majority guess 35.1% |
| Other models | SVM 58.4% / 0.412; Random Forest 57.7% / 0.383 |
| Survey study | Interests barely differ between fields (eta squared 0.01-0.04); Programming 0.52, Computer Science 0.41 |
| All 139 responses | 10 fields instead of 5, so lower: hybrid + branch 48.6% / 55.5%, random 8.4% / 34.4% |
| Tests | 135 automated tests pass |

## Hard questions, short answers

**"Your engine alone is no better than random in the top 5. Why?"**
Interests barely differ between fields in our survey, and the engine relies on them. Skills, subjects and
branch separate fields well, so the hybrid uses machine learning to pick the field and the engine to pick
and explain careers inside it. We report this openly rather than hiding it.

**"You got 139 responses. Why does the report use 87?"**
We closed the survey for analysis at 87 and fixed our rules on that data. 52 more came later; we ran exactly
the same evaluations on all 139 and report them in their own section. The task grows from 5 to 10 fields, so
the numbers drop, but the hybrid still clearly beats the engine and random. The website trains on all 139.

**"Isn't 66% low?"**
It is agreement with a student's own plan, not proof of the right career. Random choice gets 9%. With 87
students from one college, a careful honest number matters more than a high one.

**"Why not deep learning or XGBoost?"**
With 87 students, a large model would overfit. We compared Logistic Regression, Random Forest and SVM with
cross-validation, and the simplest one was best.

**"Did you tune on your test data?"**
No. The weights, the 3 places for the predicted field and the field map were fixed before we saw results.
Weight tuning was tested with cross-validation, did not improve both measures, and was not used.

**"How is it 'AI' if the engine is formulas?"**
Three AI parts: a trained classifier (field model), Sentence-BERT for understanding free text, and a RAG
chatbot. The knowledge-based engine is deliberate: it works for any new student and can explain every score.

**"Is the education route data correct?"**
Each route is tagged in the app as "Checked by the team" or "Not yet checked – confirm on the official
site", and the unchecked ones can be hidden with one setting. We
never show salaries or courses without a source.

**"What about privacy and bias?"**
Passwords are hashed with bcrypt, logins use JWT, and raw survey answers never leave the team PC or go into
Git. The model is never saved, and gender, religion and caste are never used.

**"What would you do next?"**
A user study with more students and colleges, job listings, a resume analyser, and Indian occupation codes
(NCO-2015).
