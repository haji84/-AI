#!/usr/bin/env python3
"""Explicit server-admin operation before bootstrap or adoption of legacy data."""
import argparse
from app.db import Base, engine
from app.settings import settings
from app import models
from app.tenant import initialize_tenant


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--adopt-existing-data', action='store_true')
    args = parser.parse_args()
    if engine.dialect.name == 'sqlite' and not settings.production_mode:
        Base.metadata.create_all(engine)
    result = initialize_tenant(engine, settings, args.name, adopt_existing=args.adopt_existing_data)
    print('Department initialized: ' + result['tenant_id'])


if __name__ == '__main__':
    main()
