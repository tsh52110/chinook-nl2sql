"""SQL guardrail: only a single SELECT statement may pass.

sqlglot parses the generated SQL; anything that is not exactly one SELECT
(or a CTE/UNION whose root resolves to a SELECT) is rejected: writes
(INSERT/UPDATE/DELETE), DDL (DROP/CREATE/ALTER/TRUNCATE), PRAGMA, ATTACH,
multi-statement payloads, and unparseable input. The executor's read-only
connection is the second layer of defense; this is the first.
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Roots that resolve to a plain read query.
_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)


@dataclass
class Verdict:
    allowed: bool
    reason: str | None = None


def check_sql(sql: str) -> Verdict:
    if not sql or not sql.strip():
        return Verdict(False, "empty SQL")

    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as e:
        return Verdict(False, f"unparseable SQL: {e.errors[0]['description'] if e.errors else e}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return Verdict(False, f"expected exactly 1 statement, got {len(statements)}")

    root = statements[0]

    # Unwrap a WITH (CTE) wrapper: sqlglot attaches the WITH to the outer
    # expression, so the root class is still Select/Union/etc.
    if not isinstance(root, _ALLOWED_ROOTS):
        return Verdict(False, f"only SELECT statements are allowed, got {root.key.upper()}")

    # Even inside a SELECT tree, reject any embedded write/DDL node
    # (e.g. sqlite doesn't support it, but belt and braces).
    forbidden = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
        exp.TruncateTable, exp.Pragma, exp.Attach, exp.Detach, exp.Command,
    )
    for node in root.walk():
        if isinstance(node, forbidden):
            return Verdict(False, f"forbidden operation inside query: {node.key.upper()}")

    return Verdict(True)
