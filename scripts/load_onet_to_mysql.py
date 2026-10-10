"""Copy the O*NET data the engine uses into MySQL.

What it does:
  1. Creates the 13 tables from database/schema.sql (safe if they already exist).
  2. Reads O*NET with the engine's own load_onet(), so MySQL gets exactly the values the engine uses.
  3. Fills career, skill, interest, knowledge, career_skill, career_interest and career_knowledge.

Running it again does not create duplicates: every insert is an "upsert"
(INSERT ... ON DUPLICATE KEY UPDATE), which updates the row when its key already exists.
It only reads data/raw/onet/ and never changes those files.

Run (PowerShell, from the project root, with the database already created):
    python scripts\\load_onet_to_mysql.py
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.db import get_engine, run_sql_file  # noqa: E402
from ml.baseline_recommender import RIASEC, SOC_MAJOR_GROUPS, _read, load_onet  # noqa: E402

ONET_DIR = PROJECT_ROOT / "data" / "raw" / "onet"


def _value(x):
    """pandas NaN -> SQL NULL, numbers -> plain Python float."""
    return None if pd.isna(x) else float(x)


def _upsert(conn, sql, rows):
    """Run one INSERT ... ON DUPLICATE KEY UPDATE for many rows at once."""
    if rows:
        conn.execute(text(sql), rows)


def _ids(conn, table, id_col, key_col):
    """Map each name/code to its id, e.g. {'Biology': 4, ...}."""
    return dict(conn.execute(text(f"SELECT {key_col}, {id_col} FROM {table}")).all())


def _link_rows(table_a, table_b, a_name, b_name, a_ids, b_ids):
    """Combine two (career x element) tables into rows for a link table.
    A row is kept when at least one of the two values exists."""
    a = table_a.stack().rename(a_name)
    b = table_b.stack().rename(b_name) if table_b is not None else None
    both = pd.concat([a, b], axis=1) if b is not None else a.to_frame()
    both = both.dropna(how="all")
    rows = []
    for (code, element), values in both.iterrows():
        if code in a_ids and element in b_ids:
            row = {"career_id": a_ids[code], "element_id": b_ids[element]}
            row.update({name: _value(values[name]) for name in both.columns})
            rows.append(row)
    return rows


def _check_two_decimals(data):
    """MySQL stores ratings as DECIMAL(5,2), the same precision O*NET publishes.
    Warn if any value has more decimals, because it would be rounded."""
    tables = ["interests", "skill_importance", "skill_level", "knowledge_importance", "knowledge_level"]
    for name in tables:
        values = data[name].stack()
        bad = (values - values.round(2)).abs() > 1e-9
        if bad.any():
            print(f"WARNING: {bad.sum()} values in {name} have more than 2 decimals and will be rounded.")


def load(engine, onet_dir=ONET_DIR):
    data = load_onet(onet_dir)   # already drops Recommend Suppress = "Y" rows, so MySQL stores clean values
    _check_two_decimals(data)

    run_sql_file(engine)

    occ = data["occupations"]
    job_zone = data.get("job_zone", pd.Series(dtype=float))
    essential = set(_read(onet_dir, "Essential Skills.txt")["Element Name"])
    skill_names = sorted(set(data["skill_importance"].columns) | set(data["skill_level"].columns))
    knowledge_names = sorted(set(data["knowledge_importance"].columns) | set(data["knowledge_level"].columns))

    with engine.begin() as conn:   # one transaction: all of it is saved, or nothing is
        _upsert(conn, """
            INSERT INTO career (onet_code, title, description, domain, job_zone, source)
            VALUES (:code, :title, :description, :domain, :job_zone, 'O*NET 31.0')
            ON DUPLICATE KEY UPDATE title = VALUES(title), description = VALUES(description),
                domain = VALUES(domain), job_zone = VALUES(job_zone)""",
            [{"code": code, "title": row["Title"], "description": row.get("Description"),
              "domain": SOC_MAJOR_GROUPS.get(code[:2], "Other"),
              "job_zone": None if pd.isna(job_zone.get(code)) else int(job_zone.get(code))}
             for code, row in occ.iterrows()])

        _upsert(conn, """
            INSERT INTO skill (name, category) VALUES (:name, :category)
            ON DUPLICATE KEY UPDATE category = VALUES(category)""",
            [{"name": n, "category": "essential" if n in essential else "transferable"} for n in skill_names])
        _upsert(conn, "INSERT INTO interest (name) VALUES (:name) ON DUPLICATE KEY UPDATE name = name",
                [{"name": n} for n in RIASEC])
        _upsert(conn, "INSERT INTO knowledge (name) VALUES (:name) ON DUPLICATE KEY UPDATE name = name",
                [{"name": n} for n in knowledge_names])

        careers = _ids(conn, "career", "career_id", "onet_code")
        skills = _ids(conn, "skill", "skill_id", "name")
        interests = _ids(conn, "interest", "interest_id", "name")
        knowledge = _ids(conn, "knowledge", "knowledge_id", "name")

        _upsert(conn, """
            INSERT INTO career_skill (career_id, skill_id, importance, required_level)
            VALUES (:career_id, :element_id, :importance, :required_level)
            ON DUPLICATE KEY UPDATE importance = VALUES(importance), required_level = VALUES(required_level)""",
            _link_rows(data["skill_importance"], data["skill_level"], "importance", "required_level",
                       careers, skills))
        _upsert(conn, """
            INSERT INTO career_interest (career_id, interest_id, score)
            VALUES (:career_id, :element_id, :score)
            ON DUPLICATE KEY UPDATE score = VALUES(score)""",
            _link_rows(data["interests"], None, "score", None, careers, interests))
        _upsert(conn, """
            INSERT INTO career_knowledge (career_id, knowledge_id, importance, level)
            VALUES (:career_id, :element_id, :importance, :level)
            ON DUPLICATE KEY UPDATE importance = VALUES(importance), level = VALUES(level)""",
            _link_rows(data["knowledge_importance"], data["knowledge_level"], "importance", "level",
                       careers, knowledge))


def print_counts(engine):
    """The numbers to compare with Workbench (step 1.6)."""
    queries = {
        "careers (all occupations)": "SELECT COUNT(*) FROM career",
        "careers with interest + skill + knowledge data (ranked)": """
            SELECT COUNT(*) FROM career c
            WHERE EXISTS (SELECT 1 FROM career_interest  x WHERE x.career_id = c.career_id AND x.score IS NOT NULL)
              AND EXISTS (SELECT 1 FROM career_skill     x WHERE x.career_id = c.career_id AND x.importance IS NOT NULL)
              AND EXISTS (SELECT 1 FROM career_knowledge x WHERE x.career_id = c.career_id AND x.importance IS NOT NULL)""",
        "skills (essential)": "SELECT COUNT(*) FROM skill WHERE category = 'essential'",
        "skills (transferable)": "SELECT COUNT(*) FROM skill WHERE category = 'transferable'",
        "knowledge areas": "SELECT COUNT(*) FROM knowledge",
        "interest types": "SELECT COUNT(*) FROM interest",
        "career_skill rows": "SELECT COUNT(*) FROM career_skill",
        "career_interest rows": "SELECT COUNT(*) FROM career_interest",
        "career_knowledge rows": "SELECT COUNT(*) FROM career_knowledge",
    }
    with engine.connect() as conn:
        for label, sql in queries.items():
            print(f"{label:>58}: {conn.execute(text(sql)).scalar()}")


if __name__ == "__main__":
    engine = get_engine()
    print(f"Loading O*NET from {ONET_DIR} into MySQL database '{engine.url.database}' ...")
    load(engine)
    print("Done. Row counts:")
    print_counts(engine)
