#!/usr/bin/env python3
from app.db import SessionLocal
from app.rbac_seed import seed_rbac
from app.module_seed import seed_modules

if __name__ == "__main__":
    with SessionLocal() as db:
        roles = seed_rbac(db)
        modules = seed_modules(db)
        db.commit()
    print("seeded roles: " + ", ".join(sorted(roles)))
    print("seeded modules: " + ", ".join(sorted(modules)))