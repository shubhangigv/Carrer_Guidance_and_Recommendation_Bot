"""Where the API saves and reads students, assessments and recommendations.

Two versions with the same methods:
  SqlRepository    - the real MySQL database (tables from database/schema.sql)
  MemoryRepository - plain Python dicts; used by the tests, and as a demo fallback when MySQL is not
                     running (everything is lost when the server stops; /health shows which one is used)

The API only calls these methods, so the tests can swap the database for memory
(FastAPI "dependency override") without changing any endpoint code.
"""
import json
import threading
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


class EmailTaken(Exception):
    """Raised when a student registers with an email that already exists."""


def career_ids_from_data(data):
    """career_id for every occupation, 1, 2, 3 ... in Occupation Data.txt order (same as the MySQL loader)."""
    return {code: i for i, code in enumerate(data["occupations"].index, start=1)}


class MemoryRepository:
    kind = "memory"

    def __init__(self):
        self.students, self.assessments, self.recommendations = {}, {}, []
        self.progress = {}                      # (student_id, career_id) -> set of finished step keys
        self.hidden = {}                        # student_id -> set of career_ids marked "not for me"
        self.ratings = {}                       # (student_id, assessment_id, career_id) -> rating row
        self._lock = threading.Lock()

    def create_student(self, name, email, password_hash, education_level=None, degree=None, year_of_study=None):
        with self._lock:
            if any(s["email"] == email for s in self.students.values()):
                raise EmailTaken(email)
            student_id = len(self.students) + 1
            self.students[student_id] = {"student_id": student_id, "name": name, "email": email,
                                         "password_hash": password_hash, "education_level": education_level,
                                         "degree": degree, "year_of_study": year_of_study}
            return student_id

    def get_student_by_email(self, email):
        return next((dict(s) for s in self.students.values() if s["email"] == email), None)

    def get_student(self, student_id):
        s = self.students.get(student_id)
        return None if s is None else dict(s)

    def create_assessment(self, student_id, answers, preferred_location=None, about_me=None, profile=None):
        with self._lock:
            assessment_id = len(self.assessments) + 1
            self.assessments[assessment_id] = {"assessment_id": assessment_id, "student_id": student_id,
                                               "completed_at": datetime.now(timezone.utc),
                                               "preferred_location": preferred_location, "about_me": about_me,
                                               "profile_json": json.dumps(profile) if profile else None,
                                               "answers": [dict(a) for a in answers]}
            return assessment_id

    def latest_assessment_id(self, student_id):
        mine = [a for a, v in self.assessments.items() if v["student_id"] == student_id]
        return max(mine) if mine else None

    def get_progress(self, student_id, career_id):
        return set(self.progress.get((student_id, career_id), set()))

    def set_progress(self, student_id, career_id, step_key, done):
        with self._lock:
            steps = self.progress.setdefault((student_id, career_id), set())
            steps.add(step_key) if done else steps.discard(step_key)

    def roadmap_careers(self, student_id):
        """[(career_id, finished steps)] for careers the student has started a roadmap for."""
        return [(cid, len(v)) for (sid, cid), v in self.progress.items() if sid == student_id and v]

    def get_assessment(self, assessment_id):
        a = self.assessments.get(assessment_id)
        return None if a is None else {**a, "answers": [dict(x) for x in a["answers"]]}

    def save_recommendations(self, student_id, assessment_id, rows, career_ids):
        with self._lock:
            for r in rows:
                self.recommendations.append({"student_id": student_id, "assessment_id": assessment_id,
                                             "career_id": career_ids[r["code"]], "match_score": r["match_score"],
                                             "reasons": json.dumps(r["reasons"]), "model_version": r["model_version"]})

    def set_hidden(self, student_id, career_id, hidden):
        with self._lock:
            ids = self.hidden.setdefault(student_id, set())
            ids.add(career_id) if hidden else ids.discard(career_id)

    def hidden_careers(self, student_id):
        return set(self.hidden.get(student_id, set()))

    def rate_career(self, student_id, assessment_id, career_id, rating, shown_rank, shown_group, model_version):
        with self._lock:
            self.ratings[(student_id, assessment_id, career_id)] = {
                "student_id": student_id, "assessment_id": assessment_id, "career_id": career_id, "rating": rating,
                "shown_rank": shown_rank, "shown_group": shown_group, "model_version": model_version}

    def ratings_for(self, student_id, assessment_id):
        return {k[2]: v["rating"] for k, v in self.ratings.items() if k[:2] == (student_id, assessment_id)}

    def career_ids(self, data):
        return career_ids_from_data(data)


class SqlRepository:
    kind = "mysql"

    def __init__(self, engine):
        self.engine = engine

    def create_student(self, name, email, password_hash, education_level=None, degree=None, year_of_study=None):
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO student (name, email, password_hash, education_level, degree, year_of_study)
                    VALUES (:name, :email, :password_hash, :education_level, :degree, :year_of_study)"""),
                    {"name": name, "email": email, "password_hash": password_hash,
                     "education_level": education_level, "degree": degree, "year_of_study": year_of_study})
                return int(result.lastrowid)
        except IntegrityError as err:          # the UNIQUE key on email
            raise EmailTaken(email) from err

    def get_student_by_email(self, email):
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM student WHERE email = :email"), {"email": email}).mappings().first()
        return None if row is None else dict(row)

    def get_student(self, student_id):
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM student WHERE student_id = :id"), {"id": student_id}).mappings().first()
        return None if row is None else dict(row)

    def create_assessment(self, student_id, answers, preferred_location=None, about_me=None, profile=None):
        with self.engine.begin() as conn:      # one transaction: the assessment and all its answers, or nothing
            assessment_id = int(conn.execute(text("""
                INSERT INTO assessment (student_id, preferred_location, about_me, profile_json)
                VALUES (:sid, :loc, :about, :profile)"""),
                {"sid": student_id, "loc": preferred_location, "about": about_me,
                 "profile": json.dumps(profile) if profile else None}).lastrowid)
            conn.execute(text("""
                INSERT INTO assessment_rating (assessment_id, category, item, rating, answer_status)
                VALUES (:assessment_id, :category, :item, :rating, :answer_status)"""),
                [{"assessment_id": assessment_id, **a} for a in answers])
            return assessment_id

    def get_assessment(self, assessment_id):
        with self.engine.connect() as conn:
            head = conn.execute(text("SELECT * FROM assessment WHERE assessment_id = :id"),
                                {"id": assessment_id}).mappings().first()
            if head is None:
                return None
            answers = conn.execute(text("""
                SELECT category, item, rating, answer_status FROM assessment_rating
                WHERE assessment_id = :id ORDER BY category, item"""), {"id": assessment_id}).mappings().all()
        return {**dict(head), "answers": [dict(a) for a in answers]}

    def save_recommendations(self, student_id, assessment_id, rows, career_ids):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO recommendation (student_id, career_id, assessment_id, match_score, reasons, model_version)
                VALUES (:student_id, :career_id, :assessment_id, :match_score, :reasons, :model_version)"""),
                [{"student_id": student_id, "assessment_id": assessment_id, "career_id": career_ids[r["code"]],
                  "match_score": r["match_score"], "reasons": json.dumps(r["reasons"]),
                  "model_version": r["model_version"]} for r in rows])

    def latest_assessment_id(self, student_id):
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT MAX(assessment_id) FROM assessment WHERE student_id = :sid"),
                                {"sid": student_id}).scalar()

    def get_progress(self, student_id, career_id):
        with self.engine.connect() as conn:
            return set(conn.execute(text("""
                SELECT step_key FROM roadmap_progress WHERE student_id = :sid AND career_id = :cid"""),
                {"sid": student_id, "cid": career_id}).scalars())

    def set_progress(self, student_id, career_id, step_key, done):
        sql = ("INSERT IGNORE INTO roadmap_progress (student_id, career_id, step_key) VALUES (:sid, :cid, :key)"
               if done else
               "DELETE FROM roadmap_progress WHERE student_id = :sid AND career_id = :cid AND step_key = :key")
        with self.engine.begin() as conn:
            conn.execute(text(sql), {"sid": student_id, "cid": career_id, "key": step_key})

    def roadmap_careers(self, student_id):
        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text("""
                SELECT career_id, COUNT(*) FROM roadmap_progress WHERE student_id = :sid
                GROUP BY career_id ORDER BY MAX(done_at) DESC"""), {"sid": student_id}).all()]

    def career_ids(self, data):
        with self.engine.connect() as conn:
            return dict(conn.execute(text("SELECT onet_code, career_id FROM career")).all())

    def set_hidden(self, student_id, career_id, hidden):
        sql = ("INSERT IGNORE INTO career_feedback (student_id, career_id) VALUES (:sid, :cid)" if hidden else
               "DELETE FROM career_feedback WHERE student_id = :sid AND career_id = :cid")
        with self.engine.begin() as conn:
            conn.execute(text(sql), {"sid": student_id, "cid": career_id})

    def hidden_careers(self, student_id):
        with self.engine.connect() as conn:
            return set(conn.execute(text("SELECT career_id FROM career_feedback WHERE student_id = :sid"),
                                    {"sid": student_id}).scalars())

    def rate_career(self, student_id, assessment_id, career_id, rating, shown_rank, shown_group, model_version):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO career_rating (student_id, assessment_id, career_id, rating, shown_rank, shown_group, model_version)
                VALUES (:sid, :aid, :cid, :rating, :rank, :grp, :ver)
                ON DUPLICATE KEY UPDATE rating = VALUES(rating), shown_rank = VALUES(shown_rank),
                    shown_group = VALUES(shown_group), model_version = VALUES(model_version), rated_at = CURRENT_TIMESTAMP"""),
                {"sid": student_id, "aid": assessment_id, "cid": career_id, "rating": rating, "rank": shown_rank,
                 "grp": shown_group, "ver": model_version})

    def ratings_for(self, student_id, assessment_id):
        with self.engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT career_id, rating FROM career_rating WHERE student_id = :sid AND assessment_id = :aid"""),
                {"sid": student_id, "aid": assessment_id}).all())
