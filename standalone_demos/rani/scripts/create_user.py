"""
Create a user directly in the database (first admin, device service accounts).

    python -m scripts.create_user --username admin --role admin            # prompts for the password
    python -m scripts.create_user --username sim-device --role device --password-env DEVICE_PASSWORD

Passwords are never accepted as plain command-line arguments (they would end up in shell history).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from backend.audit import write_audit
from backend.config import Settings
from backend.db import Database, run_migrations
from backend.models import User
from backend.security import ROLES, hash_password


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True)
    ap.add_argument("--role", required=True, choices=ROLES)
    ap.add_argument("--full-name", default="")
    ap.add_argument("--password-env", help="read the password from this environment variable")
    a = ap.parse_args(argv)
    pw = os.environ.get(a.password_env, "") if a.password_env else getpass.getpass("Password (>= 10 chars): ")
    if len(pw) < 10:
        print("password must be at least 10 characters", file=sys.stderr)
        return 2
    s = Settings.from_env()
    run_migrations(s.database_url)
    db = Database(s.database_url)
    with db.session() as session:
        u = session.execute(select(User).where(User.username == a.username)).scalar_one_or_none()
        if u:
            u.password_hash, u.role, u.is_active = hash_password(pw, s.password_iterations), a.role, True
            action = "user_password_reset"
        else:
            u = User(
                username=a.username,
                full_name=a.full_name or a.username,
                role=a.role,
                password_hash=hash_password(pw, s.password_iterations),
            )
            session.add(u)
            action = "user_created"
        session.flush()
        write_audit(session, "cli", action, f"user/{u.id}", {"username": a.username, "role": a.role})
    print(f"{action}: {a.username} ({a.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
