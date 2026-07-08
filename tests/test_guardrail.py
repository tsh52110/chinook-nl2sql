from src.guardrail import check_sql


def test_plain_select_allowed():
    assert check_sql("SELECT Name FROM Artist LIMIT 5").allowed


def test_cte_select_allowed():
    sql = "WITH t AS (SELECT ArtistId, COUNT(*) c FROM Album GROUP BY 1) SELECT * FROM t"
    assert check_sql(sql).allowed


def test_union_allowed():
    assert check_sql("SELECT Name FROM Artist UNION SELECT Name FROM Genre").allowed


def test_drop_blocked():
    v = check_sql("DROP TABLE Album")
    assert not v.allowed


def test_injection_style_multi_statement_blocked():
    v = check_sql("DROP TABLE albums; --")
    assert not v.allowed


def test_select_then_drop_blocked():
    v = check_sql("SELECT 1; DROP TABLE Album")
    assert not v.allowed
    assert "1 statement" in v.reason


def test_insert_blocked():
    assert not check_sql("INSERT INTO Artist (Name) VALUES ('x')").allowed


def test_update_blocked():
    assert not check_sql("UPDATE Artist SET Name='x'").allowed


def test_delete_blocked():
    assert not check_sql("DELETE FROM Artist").allowed


def test_create_blocked():
    assert not check_sql("CREATE TABLE t (a int)").allowed


def test_alter_blocked():
    assert not check_sql("ALTER TABLE Artist ADD COLUMN x int").allowed


def test_pragma_blocked():
    assert not check_sql("PRAGMA writable_schema=1").allowed


def test_attach_blocked():
    assert not check_sql("ATTACH DATABASE '/tmp/x.db' AS x").allowed


def test_empty_blocked():
    assert not check_sql("   ").allowed


def test_garbage_blocked():
    assert not check_sql("hello world this is not sql").allowed
