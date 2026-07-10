from pathlib import Path
import sqlite3

from app.core.constants import BACKEND_DIR
from app.core.settings import DB_PATH


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with get_conn() as conn:
            conn.executescript(schema_sql)
    except Exception as exc:
        print(f"[sqlite] init_db failed: {exc}")


def backend_relative_db_path() -> str:
    try:
        return str(DB_PATH.relative_to(BACKEND_DIR))
    except ValueError:
        return str(DB_PATH)
