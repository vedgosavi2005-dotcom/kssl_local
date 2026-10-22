"""Static checks on agent-written SQL, before it reaches the database.

This is the second of three locks. The database is the real one: parallax_agent can SELECT
on analytics.* and nothing else, every transaction is read-only, and statements time out
after 5 s. These checks exist to fail fast with a message the data agent can act on
("only the analytics schema is available") instead of a raw permission error, and to keep
a malformed or multi-statement string from ever being sent.
"""

import re

MAX_SQL_CHARS = 8000

# Statement keywords that have no place in a read-only analytics query.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|alter|create|grant|revoke|truncate|copy|"
    r"vacuum|analyze|cluster|reindex|comment|security|reset|do|call|execute|prepare|"
    r"deallocate|discard|listen|notify|unlisten|lock|refresh|import|load|begin|commit|"
    r"rollback|savepoint|into|set)\b",
    re.IGNORECASE,
)
# Other schemas, system catalogs and server-side functions.
_FOREIGN_SCHEMA = re.compile(
    r"\b(pg_catalog|information_schema|serving|serving_live|extracted|public|metrics|provenance)\s*\.",
    re.IGNORECASE,
)
_SYSTEM_IDENT = re.compile(r"\b(pg_\w+|lo_\w+|dblink\w*|set_config|current_setting|txid_\w+)\b", re.IGNORECASE)


class SqlRejected(ValueError):
    """The SQL failed a static check. The message is written for the model to read."""


def _strip_literals_and_comments(sql: str) -> str:
    """Blank out string literals, quoted identifiers and comments so keyword checks only
    see SQL structure (a WHERE title ILIKE '%drop%' is fine)."""
    out, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
        elif c == "/" and sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif c in ("'", '"'):
            q = c
            j = i + 1
            while j < n:
                if sql[j] == q:
                    if j + 1 < n and sql[j + 1] == q:  # doubled quote escape
                        j += 2
                        continue
                    break
                j += 1
            out.append(" '' " if q == "'" else ' "x" ')
            i = j + 1
        elif c == "$" and re.match(r"\$\w*\$", sql[i:]):
            tag = re.match(r"\$\w*\$", sql[i:]).group(0)
            j = sql.find(tag, i + len(tag))
            i = n if j < 0 else j + len(tag)
            out.append(" '' ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_sql(sql: str) -> str:
    """Return the statement to run (trailing semicolon removed) or raise SqlRejected."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlRejected("Empty SQL.")
    if len(sql) > MAX_SQL_CHARS:
        raise SqlRejected(f"SQL is longer than {MAX_SQL_CHARS} characters; simplify the query.")

    statement = sql.strip().rstrip(";").strip()
    bare = _strip_literals_and_comments(statement)

    if ";" in bare:
        raise SqlRejected("Only one statement per call. Remove the extra statements.")
    if not re.match(r"^\s*\(*\s*(select|with)\b", bare, re.IGNORECASE):
        raise SqlRejected("Only SELECT queries (optionally starting with WITH) are allowed.")
    m = _FORBIDDEN.search(bare)
    if m:
        raise SqlRejected(f"'{m.group(1).upper()}' is not allowed: queries are read-only SELECTs.")
    m = _FOREIGN_SCHEMA.search(bare)
    if m:
        raise SqlRejected(
            f"Schema '{m.group(1)}' is not available. Query the analytics views only "
            "(unqualified names resolve to analytics)."
        )
    m = _SYSTEM_IDENT.search(bare)
    if m:
        raise SqlRejected(f"'{m.group(1)}' is not available to analytics queries.")
    return statement
