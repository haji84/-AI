import argparse
import getpass
from sqlalchemy import select

from .db import Base, engine, SessionLocal
from .models import User, Employee, UserRole
# Register additive domain tables before the development-only create_all.
# Production still uses append-only migrations and the canonical bound session.
from . import operations_models, assets_models, emergency_models, personnel, learning_models
from .rbac_seed import seed_rbac
from .module_seed import seed_modules
from .submission_seed import seed_submission_types
from .equipment_seed import seed_equipment_types
from .security import hash_password
from .personnel import PasswordHistory,account_change_lock
from .audit import write_audit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--display-name", required=True)
    p.add_argument("--password")
    args = p.parse_args()
    password = args.password or getpass.getpass("Password: ")
    if not 12 <= len(password) <= 128:
        raise SystemExit("password must contain12..128 characters")
    if str(engine.url).startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        account_change_lock(db)
        if db.scalar(select(User).where(User.username == args.username)):
            raise SystemExit("username already exists")
        roles = seed_rbac(db)
        seed_modules(db)
        seed_submission_types(db)
        seed_equipment_types(db)
        emp = Employee(display_name=args.display_name)
        db.add(emp)
        db.flush()
        user = User(employee_id=emp.employee_id, username=args.username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=roles["system_admin"].role_id))
        db.add(PasswordHistory(user_id=user.user_id,password_hash=user.password_hash))
        write_audit(db,user_id=user.user_id,action='account.bootstrap',entity_type='user',entity_id=user.user_id,
            after={'username':user.username,'employee_id':emp.employee_id,'role_codes':['system_admin'],'reason':'Human server bootstrap'})
        db.commit()
        print(f"created admin user: {args.username}")


if __name__ == "__main__":
    main()

