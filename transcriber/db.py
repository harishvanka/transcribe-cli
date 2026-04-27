import sqlite3
from datetime import datetime, timezone

from transcriber.config import DB_PATH


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY,
                file_path   TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                progress    INTEGER NOT NULL DEFAULT 0,
                output_path TEXT,
                error       TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


def add_job(file_path: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (file_path, status, created_at) VALUES (?, 'pending', ?)",
            (file_path, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def update_status(job_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        conn.commit()


def update_progress(job_id: int, progress: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET progress = ? WHERE id = ?", (progress, job_id))
        conn.commit()


def get_pending_jobs(include_failed: bool = False) -> list[sqlite3.Row]:
    statuses = ("pending", "failed") if include_failed else ("pending",)
    placeholders = ",".join("?" * len(statuses))
    with _connect() as conn:
        return conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders})", statuses
        ).fetchall()


def mark_completed(job_id: int, output_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'completed', progress = 100, output_path = ? WHERE id = ?",
            (output_path, job_id),
        )
        conn.commit()


def mark_failed(job_id: int, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', error = ? WHERE id = ?",
            (error, job_id),
        )
        conn.commit()
