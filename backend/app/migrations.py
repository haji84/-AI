from __future__ import annotations

from pathlib import Path
import re

from sqlalchemy import create_engine, text


def split_sql(sql: str) -> list[str]:
    """Preserve PostgreSQL strings, dollar bodies and nested comments as raw SQL."""
    out=[];buf=[];i=0;quote=None;dollar=None;escaped=False
    line_comment=False;block_depth=0;has_code=False
    def identifier(char):return char.isalnum() or char in '_$'
    def continuation(start):
        cursor=start;newline=False
        while cursor<len(sql):
            if sql[cursor] in ' \t\n\r\f\v':
                newline=newline or sql[cursor] in '\r\n';cursor+=1
            elif sql.startswith('--',cursor):
                while cursor<len(sql) and sql[cursor] not in '\r\n':cursor+=1
            else:break
        return cursor if newline and cursor<len(sql) and sql[cursor]=="'" else None
    while i<len(sql):
        ch=sql[i];nxt=sql[i+1] if i+1<len(sql) else ''
        if dollar is not None:
            if sql.startswith(dollar,i):buf.append(dollar);i+=len(dollar);dollar=None
            else:buf.append(ch);i+=1
            continue
        if line_comment:
            buf.append(ch);i+=1
            if ch in '\r\n':line_comment=False
            continue
        if block_depth:
            if ch=='/' and nxt=='*':buf.extend((ch,nxt));block_depth+=1;i+=2
            elif ch=='*' and nxt=='/':buf.extend((ch,nxt));block_depth-=1;i+=2
            else:buf.append(ch);i+=1
            continue
        if quote:
            buf.append(ch);i+=1
            if escaped and ch=='\\':
                if i<len(sql):buf.append(sql[i]);i+=1
            elif ch==quote:
                if nxt==quote:buf.append(nxt);i+=1
                else:
                    continued=continuation(i) if escaped else None
                    if continued is not None:buf.append(sql[i:continued+1]);i=continued+1
                    else:quote=None;escaped=False
            continue
        if ch=='-' and nxt=='-':buf.extend((ch,nxt));line_comment=True;i+=2;continue
        if ch=='/' and nxt=='*':buf.extend((ch,nxt));block_depth=1;i+=2;continue
        if ch in ("'",'"'):
            quote=ch;escaped=ch=="'" and i>0 and sql[i-1] in 'Ee' and (i<2 or not identifier(sql[i-2]))
            buf.append(ch);has_code=True;i+=1;continue
        if ch=='$' and (i==0 or not identifier(sql[i-1])):
            match=re.match(r'\$(?:[^\W\d]\w*)?\$',sql[i:])
            if match:dollar=match.group();buf.append(dollar);has_code=True;i+=len(dollar);continue
        if ch==';':
            if has_code:out.append(''.join(buf).strip())
            buf=[];has_code=False;i+=1;continue
        buf.append(ch)
        if not ch.isspace():has_code=True
        i+=1
    if quote or dollar or block_depth:raise ValueError('unterminated SQL quote or block comment')
    if has_code:out.append(''.join(buf).strip())
    return out


def apply_migrations(database_url: str, migrations_dir: Path) -> list[str]:
    if not database_url.startswith("postgresql"):
        raise ValueError("production migrations require PostgreSQL")
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        raise ValueError("no migration files found")
    # Validate every file before taking a connection or altering any schema.
    parsed=[(path,split_sql(path.read_text(encoding='utf-8'))) for path in files]
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    applied: list[str] = []
    try:
        with engine.connect() as conn:
            acquired = conn.execute(text("SELECT pg_try_advisory_lock(hashtext('fire-ai-schema-migration'))")).scalar_one()
            conn.commit()
            if not acquired:
                raise ValueError("another migration is running in this database")
            try:
                with conn.begin():
                    conn.exec_driver_sql(
                        "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
                    )
                for path,statements in parsed:
                    version = path.name
                    with conn.begin():
                        done = conn.execute(text("SELECT 1 FROM schema_migrations WHERE version=:v"), {"v": version}).first()
                        if done:
                            continue
                        for statement in statements:
                            conn.exec_driver_sql(statement,execution_options={'no_parameters':True})
                        conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:v)"), {"v": version})
                    applied.append(version)
            finally:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(hashtext('fire-ai-schema-migration'))"))
                conn.commit()
    finally:
        engine.dispose()
    return applied
