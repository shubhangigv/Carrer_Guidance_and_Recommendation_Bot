"""One shared MySQL connection for the whole project.

Settings come from the .env file in the project root (copy .env.example to .env
and fill in your password). Nothing secret is written in code.

Usage:
    from backend.db import get_engine
    engine = get_engine()
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "database" / "schema.sql"

load_dotenv(PROJECT_ROOT / ".env")


def get_url(database=None):
    """Build the connection address from .env. URL.create handles special
    characters in the password, so no manual escaping is needed.
    database=None uses MYSQL_DATABASE from .env; database="" connects to no database."""
    return URL.create(
        "mysql+pymysql",
        username=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=(database if database is not None else os.getenv("MYSQL_DATABASE", "career_guidance")) or None,
        query={"charset": "utf8mb4"},
    )


def get_engine(database=None):
    """Return a SQLAlchemy engine. pool_pre_ping reconnects if MySQL closed an idle connection."""
    return create_engine(get_url(database), pool_pre_ping=True)


def run_sql_file(engine, path=SCHEMA_FILE):
    """Run every statement in a .sql file (used to create the tables)."""
    sql = Path(path).read_text(encoding="utf-8")
    sql = re.sub(r"--[^\n]*", "", sql)              # drop comments
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
