"""
Every university tenant in Schoolmate has its own MySQL database (see
`universities.db_name`). The chatbot never keeps long-lived pooled
connections across tenants (unsafe on free-tier hosts like Render/
PythonAnywhere where the process can sleep); instead it opens a short-lived
connection per request and closes it right away.

`db_name` always comes from the signed JWT minted by the PHP app — never
from a client-controlled field — so a student can never point the chatbot
at a different tenant's database.
"""
import re
import pymysql
import pymysql.cursors
from contextlib import contextmanager
from fastapi import HTTPException

from config import settings

# Defensive allow-list check: tenant db names in this project are simple
# identifiers (letters, digits, underscore). Reject anything else outright.
_SAFE_DBNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _validate_db_name(db_name: str) -> str:
    if not db_name or not _SAFE_DBNAME_RE.match(db_name):
        raise HTTPException(status_code=400, detail="Invalid tenant database.")
    return db_name


@contextmanager
def get_connection(db_name: str):
    db_name = _validate_db_name(db_name)
    conn = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=8,
        read_timeout=15,
    )
    try:
        yield conn
    finally:
        conn.close()
