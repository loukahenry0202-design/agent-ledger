from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def sqlite_connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Ouvre une connexion SQLite et la ferme proprement à la sortie."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
