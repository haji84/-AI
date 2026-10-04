from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text


def split_sql(sql: str) -> list[str]:
    """Split the project's plain DDL migration files safely enough for current Phase 1 SQL.

    Supports quoted strings/identifiers and line/block comments. Procedural dollar-quoted
    bodies are intentionally out of scope; move to Alembic before such migrations appear.
    """
    out: list[str] = []
    buf: list[str] = []
    i = 0
    quote: str | None = None
    line_comment = False
    block_comment = False
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if line_comment:
            buf.append(ch)
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                block_comment = False
            else:
                i += 1
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                if nxt == quote:
                    buf.append(nxt)
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch == "-" and nxt == "-":
            buf.extend([ch, nxt])
            i += 2
            line_comment = True
            continue
        if ch == "/" and nxt == "*":
            buf.extend([ch, nxt])
            i += 2
            block_comment = True
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                out.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def apply_migrations(database_url: str, migrations_dir: Path) -> list[str]:
    if not database_url.startswith("postgresql"):
        raise ValueError("production migrations require PostgreSQL")
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        raise ValueError("no migration files found")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
    applied: list[str] = []
    for path in files:
        version = path.name
        with engine.begin() as conn:
            done = conn.execute(text("SELECT 1 FROM schema_migrations WHERE version=:v"), {"v": version}).first()
            if done:
                continue
            for statement in split_sql(path.read_text(encoding="utf-8")):
                conn.exec_driver_sql(statement)
            conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:v)"), {"v": version})
        applied.append(version)
    engine.dispose()
    return applied
