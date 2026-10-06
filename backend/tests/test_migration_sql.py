"""Migration DDL must preserve PostgreSQL quoted bodies and preflight malformed input."""
from pathlib import Path
import os
import pytest
from app.migrations import split_sql,apply_migrations


@pytest.mark.parametrize('tag',['$$','$guard$','$G_01$'])
def test_trigger_function_body_is_one_statement_and_immutable_guard_preserved(tag):
    body=f"CREATE FUNCTION synthetic_guard() RETURNS trigger LANGUAGE plpgsql AS {tag}\nBEGIN\n RAISE EXCEPTION 'synthetic immutable; source';\n RETURN OLD;\nEND;\n{tag}"
    parts=split_sql('CREATE TABLE synthetic_journal(data text);\n'+body+';\nCREATE TRIGGER synthetic_guard BEFORE UPDATE ON synthetic_journal FOR EACH ROW EXECUTE FUNCTION synthetic_guard();')
    assert len(parts)==3
    assert parts[1]==body


def test_nested_block_comments_and_escaped_quotes_do_not_split_sql():
    statement=r"""INSERT INTO synthetic_journal VALUES (E'it\'s; synthetic', 'ordinary''quote;value', "quoted;column")"""
    sql='/* outer; /* nested; */ still comment; */\n'+statement+';SELECT 1; -- trailing;'
    parts=split_sql(sql)
    assert len(parts)==2
    assert statement in parts[0] and parts[1]=='SELECT 1'


def test_comment_dollars_and_identifier_dollars_are_not_quote_delimiters():
    parts=split_sql('-- $unused$;\nSELECT synthetic$guard$identifier;SELECT \'$inside$;\';')
    assert len(parts)==2
    assert 'synthetic$guard$identifier' in parts[0]
    assert "'$inside$;'" in parts[1]


@pytest.mark.parametrize('sql',["SELECT 'open",'SELECT "open','DO $$ BEGIN;','DO $guard$ BEGIN;','/* open /* nested */'])
def test_unclosed_sql_is_rejected_before_execution(sql):
    with pytest.raises(ValueError,match='unterminated'):split_sql(sql)


def test_complete_set_is_preflighted_before_any_database_connection(tmp_path,monkeypatch):
    from app import migrations
    (tmp_path/'001_synthetic.sql').write_text('CREATE TABLE synthetic_journal(data text);')
    (tmp_path/'002_invalid.sql').write_text('DO $$ BEGIN;')
    def never_connect(*args,**kwargs):raise AssertionError('database connection opened before complete preflight')
    monkeypatch.setattr(migrations,'create_engine',never_connect)
    with pytest.raises(ValueError,match='unterminated'):apply_migrations('postgresql+psycopg://synthetic-unused',tmp_path)


def test_actual_postgresql_immutable_trigger_percent_literal_and_retry(tmp_path):
    base=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not base:pytest.skip('real PostgreSQL quote/trigger execution runs in CI')
    from sqlalchemy import create_engine,text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import IntegrityError
    from uuid import uuid4
    database='fi_sql_'+uuid4().hex[:16];cluster=create_engine(make_url(base).set(database='postgres'),isolation_level='AUTOCOMMIT');engine=None
    with cluster.connect() as db:db.exec_driver_sql('CREATE DATABASE '+database)
    target=make_url(base).set(database=database).render_as_string(hide_password=False)
    try:
        (tmp_path/'001_synthetic.sql').write_text("""CREATE TABLE synthetic_journal(data text);
CREATE FUNCTION synthetic_guard() RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
 RAISE EXCEPTION 'synthetic journal is immutable' USING ERRCODE='23514';
 RETURN OLD;
END;
$guard$;
CREATE TRIGGER synthetic_guard BEFORE UPDATE OR DELETE ON synthetic_journal FOR EACH ROW EXECUTE FUNCTION synthetic_guard();
INSERT INTO synthetic_journal(data) SELECT 'synthetic foo' WHERE 'synthetic foo' LIKE '%foo%';
""")
        with (tmp_path/'001_synthetic.sql').open('a') as stream:
            stream.write("CREATE TABLE synthetic_strings(data text); INSERT INTO synthetic_strings VALUES (E'first'\n'it\\'s; second');")
        assert apply_migrations(target,tmp_path)==['001_synthetic.sql']
        assert apply_migrations(target,tmp_path)==[]
        engine=create_engine(target)
        with engine.connect() as db:
            assert db.execute(text('SELECT data FROM synthetic_journal')).scalar_one()=='synthetic foo'
            assert db.execute(text('SELECT data FROM synthetic_strings')).scalar_one()=="firstit's; second"
        for statement in ["UPDATE synthetic_journal SET data='tampered'",'DELETE FROM synthetic_journal']:
            with pytest.raises(IntegrityError):
                with engine.begin() as db:db.execute(text(statement))
        with engine.connect() as db:
            assert db.execute(text('SELECT data FROM synthetic_journal')).scalar_one()=='synthetic foo'
            assert db.execute(text('SELECT data FROM synthetic_strings')).scalar_one()=="firstit's; second"
    finally:
        if engine:engine.dispose()
        with cluster.connect() as db:db.exec_driver_sql('DROP DATABASE '+database+' WITH (FORCE)')
        cluster.dispose()


@pytest.mark.parametrize('separator',['\n','\r\n',' -- synthetic; comment\n',' -- synthetic; comment\r'])
def test_continued_e_strings_preserve_escape_mode_after_newline_or_line_comment(separator):
    first="SELECT E'first'"+separator+r"'it\'s; second'"
    assert split_sql(first+'; SELECT 2;')==[first,'SELECT 2']


def test_unterminated_continued_e_string_is_rejected_before_any_connection(tmp_path,monkeypatch):
    from app import migrations
    (tmp_path/'001_synthetic.sql').write_text('CREATE TABLE synthetic_journal(data text);')
    (tmp_path/'002_invalid.sql').write_text("SELECT E'first'\n'\\';")
    def never_connect(*args,**kwargs):raise AssertionError('invalid continued string bypassed preflight')
    monkeypatch.setattr(migrations,'create_engine',never_connect)
    with pytest.raises(ValueError,match='unterminated'):apply_migrations('postgresql+psycopg://synthetic-unused',tmp_path)


def test_cr_line_comment_does_not_hide_following_migration_statement():
    parts=split_sql('CREATE TABLE synthetic_journal(data text); -- synthetic; comment\rINSERT INTO synthetic_journal VALUES (\'intact\');')
    assert len(parts)==2 and 'INSERT INTO' in parts[1]
