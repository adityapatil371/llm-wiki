import sqlite3
import hashlib
from datetime import datetime
from config import DB_PATH


def get_connection():
    """Get a SQLite connection. Creates the DB file if it doesn't exist."""
    return sqlite3.connect(DB_PATH)


def init_db():
    """Create the ingestion_index table if it doesn't exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_index (
                document_name   TEXT PRIMARY KEY,
                file_hash       TEXT NOT NULL,
                date_ingested   TIMESTAMP NOT NULL,
                wiki_pages      TEXT
            )
        """)
        conn.commit()


def hash_file(file_bytes: bytes) -> str:
    """Generate SHA256 hash of file contents."""
    return hashlib.sha256(file_bytes).hexdigest()


def is_already_ingested(document_name: str, file_hash: str) -> bool:
    """
    Returns True if this exact version of the document
    has already been ingested (same name AND same hash).
    """
    with get_connection() as conn:
        row = conn.execute("""
            SELECT file_hash FROM ingestion_index
            WHERE document_name = ?
        """, (document_name,)).fetchone()

    if row is None:
        return False  # never seen this document
    return row[0] == file_hash  # seen it, but has it changed?


def record_ingestion(document_name: str, file_hash: str, wiki_pages: list[str]):
    """
    Insert or update a document record after successful ingestion.
    wiki_pages is a list of markdown filenames the agent created/updated.
    """
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ingestion_index 
                (document_name, file_hash, date_ingested, wiki_pages)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(document_name) DO UPDATE SET
                file_hash       = excluded.file_hash,
                date_ingested   = excluded.date_ingested,
                wiki_pages      = excluded.wiki_pages
        """, (
            document_name,
            file_hash,
            datetime.now().isoformat(),
            ",".join(wiki_pages)
        ))
        conn.commit()


def get_all_ingested() -> list[dict]:
    """Return all ingested documents — used by the Streamlit UI."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT document_name, date_ingested, wiki_pages
            FROM ingestion_index
            ORDER BY date_ingested DESC
        """).fetchall()

    return [
        {
            "document_name": row[0],
            "date_ingested": row[1],
            "wiki_pages": row[2].split(",") if row[2] else []
        }
        for row in rows
    ]