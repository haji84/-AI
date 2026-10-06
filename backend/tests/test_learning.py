import os
os.environ.setdefault('FIRE_AI_DATABASE_URL','sqlite+pysqlite:///:memory:')
import pytest


def test_literal_correction_compiles_approved_examples_without_changing_raw_text():
    from app.learning_engine import compile_corrections,apply_artifact
    artifact=compile_corrections('ocr',[{'input_text':'消火線','output_text':'消火栓','review_status':'approved'},
        {'input_text':'消防','output_text':'誤変更','review_status':'pending'}])
    result=apply_artifact(artifact,'屋内消火線と消防設備')
    assert result['original']=='屋内消火線と消防設備'
    assert result['suggestion']=='屋内消火栓と消防設備'
    assert result['human_review_required'] is True


def test_fixed_evaluation_calculates_comparison_and_rejects_malformed_artifacts():
    from app.learning_engine import compile_corrections,compare_artifacts,apply_artifact
    champion=compile_corrections('ocr',[])
    candidate=compile_corrections('ocr',[{'input_text':'消火線','output_text':'消火栓','review_status':'approved'}])
    result=compare_artifacts(champion,candidate,[{'input':'屋内消火線','expected':'屋内消火栓'}])
    assert result['champion']['exact_accuracy']==0
    assert result['candidate']['exact_accuracy']==1
    assert result['no_regression'] is True
    with pytest.raises(ValueError):apply_artifact({'task':'formal_legal_rule','entries':[]},'test')


@pytest.fixture(params=['sqlite','postgresql'])
def learning_environment(request):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.db import Base,get_db
    from app.models import Employee,User,UserRole,AuditLog
    from app.rbac_seed import seed_rbac
    from app.module_seed import seed_modules
    from app.security import hash_password
    from app.routers import auth,learning
    from app import learning_models
    cluster=None;database=None
    if request.param=='postgresql':
        from sqlalchemy.engine import make_url
        from app.migrations import apply_migrations
        from pathlib import Path
        from uuid import uuid4
        base=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
        if not base:pytest.skip('real PostgreSQL learning lifecycle executes in CI')
        database='fi_learning_'+uuid4().hex[:16]
        cluster=create_engine(make_url(base).set(database='postgres'),isolation_level='AUTOCOMMIT')
        with cluster.connect() as db:db.exec_driver_sql('CREATE DATABASE '+database)
        target=make_url(base).set(database=database).render_as_string(hide_password=False)
        try:apply_migrations(target,Path(__file__).resolve().parents[2]/'db/migrations')
        except BaseException:
            with cluster.connect() as db:db.exec_driver_sql('DROP DATABASE '+database+' WITH (FORCE)')
            cluster.dispose();raise
        engine=create_engine(target)
    else:
        engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
    with Session(engine) as db:
        roles=seed_rbac(db);seed_modules(db);staff=Employee(display_name='Synthetic learning administrator');db.add(staff);db.flush()
        user=User(employee_id=staff.employee_id,username='learning-admin',password_hash=hash_password('synthetic-learning-password'));db.add(user);db.flush()
        db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id));db.commit()
    app=FastAPI();app.include_router(auth.router);app.include_router(learning.router)
    def dependency():
        with Session(engine,expire_on_commit=False) as db:yield db
    app.dependency_overrides[get_db]=dependency
    with TestClient(app) as client:
        assert client.get('/learning/corrections').status_code==401
        assert client.post('/auth/login',json={'username':'learning-admin','password':'synthetic-learning-password'}).status_code==200
        yield client,engine
    engine.dispose()
    if cluster:
        with cluster.connect() as db:db.exec_driver_sql('DROP DATABASE '+database+' WITH (FORCE)')
        cluster.dispose()


def test_learning_api_requires_review_fixed_eval_and_cas_before_promotion(learning_environment):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models import AuditLog
    client,engine=learning_environment
    correction=client.post('/learning/corrections',json={'task':'ocr','input_text':'消火線','output_text':'消火栓','synthetic':True,'reason':'Human synthetic correction'}).json()
    assert correction['review_status']=='pending'
    review=client.post('/learning/corrections/'+correction['correction_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Human reference verified'})
    assert review.status_code==200,review.text
    test_set=client.post('/learning/evaluation-sets',json={'task':'ocr','name':'Synthetic fixed holdout','synthetic':True,'cases':[{'input':'屋内消火線','expected':'屋内消火栓'}],'reason':'Human fixed test'}).json()
    artifact=client.post('/learning/artifacts',json={'task':'ocr','correction_ids':[correction['correction_id']],'reason':'Human training request'}).json()
    evaluate={'evaluation_set_id':test_set['evaluation_set_id']}
    assert client.post('/learning/artifacts/'+artifact['artifact_id']+'/evaluate',json=evaluate).status_code==409
    assert client.post('/learning/evaluation-sets/'+test_set['evaluation_set_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Human expected outputs verified'}).status_code==200
    scored=client.post('/learning/artifacts/'+artifact['artifact_id']+'/evaluate',json=evaluate)
    assert scored.status_code==201,scored.text
    scored=scored.json()
    assert scored['result']['candidate']['exact_accuracy']==1
    promote={'evaluation_id':scored['evaluation_id'],'expected_version':1,'reason':'Human benchmark acceptance'}
    promoted=client.post('/learning/champions/ocr/promote',json=promote)
    assert promoted.status_code==200,promoted.text
    assert client.post('/learning/champions/ocr/promote',json=promote).status_code==409
    suggestion=client.post('/learning/suggest',json={'task':'ocr','input_text':'屋内消火線'}).json()
    assert suggestion['suggestion']=='屋内消火栓' and suggestion['human_review_required']
    rolled=client.post('/learning/champions/ocr/rollback',json={'expected_version':2,'transition_id':promoted.json()['transition_id'],'reason':'Human revert to baseline'})
    assert rolled.status_code==200,rolled.text
    assert client.post('/learning/suggest',json={'task':'ocr','input_text':'屋内消火線'}).json()['suggestion']=='屋内消火線'
    with Session(engine) as db:assert db.scalar(select(AuditLog).where(AuditLog.action=='learning.rollback'))


def test_real_fixed_set_requires_original_evidence(learning_environment):
    client,_=learning_environment
    result=client.post('/learning/evaluation-sets',json={'task':'ocr','name':'claimed real benchmark','synthetic':False,'cases':[{'input':'x','expected':'y'}],'reason':'Human validation'})
    assert result.status_code==422,result.text


def test_compiled_training_source_and_holdout_must_be_disjoint(learning_environment):
    from sqlalchemy.orm import Session
    from app.models import Document
    client,engine=learning_environment
    with Session(engine) as db:
        source=Document(storage_path='synthetic/text.txt',original_filename='synthetic.txt',sha256='a'*64);db.add(source);db.commit();identity=source.document_id
    correction=client.post('/learning/corrections',json={'task':'ocr','source_document_id':identity,'input_text':'消火線','output_text':'消火栓','reason':'Human correction'}).json()
    assert client.post('/learning/corrections/'+correction['correction_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Human verified'}).status_code==200
    artifact=client.post('/learning/artifacts',json={'task':'ocr','correction_ids':[correction['correction_id']],'reason':'Human build'}).json()
    fixed=client.post('/learning/evaluation-sets',json={'task':'ocr','name':'same source holdout','source_document_ids':[identity],'cases':[{'input':'屋内消火線','expected':'屋内消火栓'}],'reason':'Human test'}).json()
    assert 'evaluation_set_id' in fixed,fixed
    client.post('/learning/evaluation-sets/'+fixed['evaluation_set_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Human expected values'})
    response=client.post('/learning/artifacts/'+artifact['artifact_id']+'/evaluate',json={'evaluation_set_id':fixed['evaluation_set_id']})
    assert response.status_code==409,response.text


def test_disabled_learning_module_does_not_produce_suggestions(learning_environment):
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.models import FeatureFlag
    client,engine=learning_environment
    with Session(engine) as db:
        flag=db.scalar(select(FeatureFlag).where(FeatureFlag.key=='module.learning.enabled'));flag.enabled=False;db.commit()
    assert client.post('/learning/suggest',json={'task':'ocr','input_text':'test'}).status_code==503


def test_synthetic_reference_cannot_be_approved_for_production(learning_environment,monkeypatch):
    from app.settings import settings
    client,_=learning_environment
    correction=client.post('/learning/corrections',json={'task':'ocr','input_text':'x','output_text':'y','synthetic':True,'reason':'Synthetic test only'}).json()
    monkeypatch.setattr(settings,'production_mode',True)
    response=client.post('/learning/corrections/'+correction['correction_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'must be refused'})
    assert response.status_code==422


def test_learning_only_permission_cannot_read_source_text(learning_environment):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.models import Employee,User,UserRole,Role,Permission,RolePermission
    from app.security import hash_password
    client,engine=learning_environment
    with Session(engine) as db:
        employee=Employee(display_name='Synthetic limited reviewer');role=Role(code='synthetic_learning_only',name='Synthetic limited',system_role=False);db.add_all([employee,role]);db.flush()
        user=User(employee_id=employee.employee_id,username='limited',password_hash=hash_password('synthetic-limited-password'));db.add(user);db.flush()
        permission=db.scalar(select(Permission).where(Permission.code=='learning.read'))
        db.add_all([UserRole(user_id=user.user_id,role_id=role.role_id),RolePermission(role_id=role.role_id,permission_id=permission.permission_id)]);db.commit()
    with TestClient(client.app) as limited:
        assert limited.post('/auth/login',json={'username':'limited','password':'synthetic-limited-password'}).status_code==200
        assert limited.get('/learning/corrections').status_code==403
        assert limited.get('/learning/evaluation-sets').status_code==403
        assert limited.get('/learning/artifacts').status_code==403
        assert limited.post('/learning/suggest',json={'task':'ocr','input_text':'test'}).status_code==403


def test_concurrent_promotion_preserves_single_champion_history(learning_environment):
    import threading
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.learning_models import LearningTransition
    client,engine=learning_environment
    if engine.dialect.name!='postgresql':pytest.skip('actual PostgreSQL concurrency required')
    correction=client.post('/learning/corrections',json={'task':'ocr','input_text':'消火線','output_text':'消火栓','synthetic':True,'reason':'Synthetic reference'}).json()
    client.post('/learning/corrections/'+correction['correction_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Synthetic Human review'})
    artifact=client.post('/learning/artifacts',json={'task':'ocr','correction_ids':[correction['correction_id']],'reason':'Synthetic training'}).json()
    fixed=client.post('/learning/evaluation-sets',json={'task':'ocr','name':'Synthetic race holdout','synthetic':True,'cases':[{'input':'屋内消火線','expected':'屋内消火栓'}],'reason':'Synthetic fixed set'}).json()
    client.post('/learning/evaluation-sets/'+fixed['evaluation_set_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Synthetic expected values'})
    result=client.post('/learning/artifacts/'+artifact['artifact_id']+'/evaluate',json={'evaluation_set_id':fixed['evaluation_set_id']}).json()
    barrier=threading.Barrier(2);responses=[];failures=[]
    def promote():
        from fastapi.testclient import TestClient
        try:
            with TestClient(client.app) as second:
                second.cookies.update(client.cookies)
                barrier.wait(timeout=10)
                responses.append(second.post('/learning/champions/ocr/promote',json={'expected_version':1,'evaluation_id':result['evaluation_id'],'reason':'Synthetic concurrent Human approval'}).status_code)
        except BaseException as exc:failures.append(exc)
    threads=[threading.Thread(target=promote) for _ in range(2)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(timeout=20)
    assert not failures and all(not thread.is_alive() for thread in threads),failures
    assert sorted(responses)==[200,409],responses
    with Session(engine) as db:assert len(db.scalars(select(LearningTransition)).all())==1


def test_duplicate_original_bytes_cannot_be_holdout(learning_environment):
    from sqlalchemy.orm import Session
    from app.models import Document
    client,engine=learning_environment
    with Session(engine) as db:
        first=Document(storage_path='synthetic/first.txt',original_filename='first.txt',sha256='b'*64)
        second=Document(storage_path='synthetic/copy.txt',original_filename='copy.txt',sha256='b'*64)
        db.add_all([first,second]);db.commit();training_id,holdout_id=first.document_id,second.document_id
    correction=client.post('/learning/corrections',json={'task':'ocr','source_document_id':training_id,'input_text':'消火線','output_text':'消火栓','reason':'Synthetic Human correction'}).json()
    client.post('/learning/corrections/'+correction['correction_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Synthetic Human approval'})
    artifact=client.post('/learning/artifacts',json={'task':'ocr','correction_ids':[correction['correction_id']],'reason':'Synthetic build'}).json()
    fixed=client.post('/learning/evaluation-sets',json={'task':'ocr','name':'Duplicated-byte holdout','source_document_ids':[holdout_id],'cases':[{'input':'屋内消火線','expected':'屋内消火栓'}],'reason':'Synthetic fixed set'}).json()
    client.post('/learning/evaluation-sets/'+fixed['evaluation_set_id']+'/review',json={'expected_version':1,'decision':'approved','reason':'Synthetic expected values'})
    response=client.post('/learning/artifacts/'+artifact['artifact_id']+'/evaluate',json={'evaluation_set_id':fixed['evaluation_set_id']})
    assert response.status_code==409,response.text
