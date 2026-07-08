"""Read-only SQLite executor.

Adapted from premAI-io/premsql (premsql/executors/from_sqlite.py, SQLiteExecutor),
MIT License — https://github.com/premAI-io/premsql. Changes from upstream:
- connection opened read-only (file:...?mode=ro) so no write can ever reach the DB
- per-query timeout via SQLite progress handler
- returns column names alongside rows
"""

import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    rows: list | None
    columns: list = field(default_factory=list)
    error: str | None = None
    execution_time: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


class SQLiteExecutor:
    """Executes SQL against a SQLite file opened in read-only mode."""

    def __init__(self, db_path: str, timeout_s: float = 15.0):
        self.db_path = db_path
        self.timeout_s = timeout_s

    def execute(self, sql: str) -> ExecutionResult:
        start = time.time()
        deadline = start + self.timeout_s
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        except sqlite3.Error as e:
            return ExecutionResult(rows=None, error=str(e))
        # abort long-running queries (checked every N VM instructions)
        conn.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10_000)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description] if cursor.description else []
            return ExecutionResult(rows=rows, columns=columns, execution_time=time.time() - start)
        except sqlite3.Error as e:
            return ExecutionResult(rows=None, error=str(e), execution_time=time.time() - start)
        finally:
            conn.close()
