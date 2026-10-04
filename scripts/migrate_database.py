#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.migrations import apply_migrations
from app.settings import settings


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--database-url", default=settings.database_url)
    p.add_argument("--migrations", type=Path, default=Path(__file__).resolve().parents[1] / "db" / "migrations")
    args = p.parse_args()
    try:
        applied = apply_migrations(args.database_url, args.migrations)
    except ValueError as exc:
        raise SystemExit(str(exc))
    for name in applied:
        print(f"applied {name}")
    if not applied:
        print("database already up to date")


if __name__ == "__main__":
    main()