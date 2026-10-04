import argparse
import getpass
from sqlalchemy import select

from .db import Base, engine, SessionLocal
from .models import User, Employee, UserRole
from .rbac_seed import seed_rbac
from .module_seed import seed_modules
from .submission_seed import seed_submission_types
from .security import hash_password


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--username", required=True)
    p.add_argument("--display-name", required=True)
    p.add_argument("--password")
    args = p.parse_args()
    password = args.password or getpass.getpass("Password: ")
    if str(engine.url).startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == args.username)):
            raise SystemExit("username already exists")
        roles = seed_rbac(db)
        seed_modules(db)
        seed_submission_types(db)
        emp = Employee(display_name=args.display_name)
        db.add(emp)
        db.flush()
        user = User(employee_id=emp.employee_id, username=args.username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=roles["system_admin"].role_id))
        db.commit()
        print(f"created admin user: {args.username}")


if __name__ == "__main__":
    main()
