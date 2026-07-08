from src.agent import extract_sql
from src.executor import SQLiteExecutor
from src.schema import get_schema

DB = "data/Chinook.db"


def test_extract_sql_fenced():
    text = "I need Artist and Album.\n```sql\nSELECT 1;\n```"
    assert extract_sql(text) == "SELECT 1"


def test_extract_sql_takes_last_block():
    text = "```sql\nSELECT 1\n```\nactually:\n```sql\nSELECT 2\n```"
    assert extract_sql(text) == "SELECT 2"


def test_extract_sql_bare_fence_with_select():
    text = "```\nSELECT Name FROM Artist\n```"
    assert extract_sql(text) == "SELECT Name FROM Artist"


def test_extract_sql_none():
    assert extract_sql("no sql here") is None


def test_schema_contains_all_tables():
    schema = get_schema(DB)
    for table in ["Album", "Artist", "Customer", "Employee", "Genre", "Invoice",
                  "InvoiceLine", "MediaType", "Playlist", "PlaylistTrack", "Track"]:
        assert f"CREATE TABLE [{table}]" in schema or f"CREATE TABLE {table}" in schema


def test_executor_select_ok():
    r = SQLiteExecutor(DB).execute("SELECT COUNT(*) FROM Track")
    assert r.ok and r.rows == [(3503,)]


def test_executor_is_read_only():
    # even if the guardrail were bypassed, writes must fail at the connection
    r = SQLiteExecutor(DB).execute("UPDATE Artist SET Name='x' WHERE ArtistId=1")
    assert not r.ok
    assert "readonly" in r.error.lower() or "read-only" in r.error.lower()


def test_executor_bad_sql_returns_error():
    r = SQLiteExecutor(DB).execute("SELECT nope FROM NotATable")
    assert not r.ok and r.error
