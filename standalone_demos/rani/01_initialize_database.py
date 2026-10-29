"""
01 - Create / upgrade the persistent database with Alembic migrations and create the demo accounts.

    python 01_initialize_database.py

Safe to run again: migrations are idempotent and existing users are kept (passwords are reset to the .env values).
"""

from __future__ import annotations

from demo_common import load_env, require_env


def main() -> int:
    env = load_env()
    require_env("SECRET_KEY", "BOOTSTRAP_ADMIN_PASSWORD", "DOCTOR_PASSWORD", "DEVICE_PASSWORD")
    from sqlalchemy import func, inspect, select

    from backend.audit import write_audit
    from backend.config import Settings
    from backend.db import Database, run_migrations
    from backend.models import Base, User
    from backend.security import hash_password

    s = Settings.from_env()
    print(f"database: {s.database_url}")
    run_migrations(s.database_url)
    db = Database(s.database_url)
    accounts = [(env["BOOTSTRAP_ADMIN_USERNAME"] or "admin", "admin", env["BOOTSTRAP_ADMIN_PASSWORD"]),
                ("doctor", "doctor", env["DOCTOR_PASSWORD"]), (env.get("STREAM_USER") or "sim-device", "device", env["DEVICE_PASSWORD"])]
    with db.session() as session:
        for username, role, pw in accounts:
            u = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if u is None:
                session.add(User(username=username, full_name=username, role=role,
                                 password_hash=hash_password(pw, s.password_iterations)))
                print(f"  created user {username} ({role})")
            else:
                u.password_hash, u.role, u.is_active = hash_password(pw, s.password_iterations), role, True
                print(f"  user {username} ({role}) exists - password reset to .env value")
            session.flush()
        write_audit(session, "01_initialize_database", "database_initialised", "database", {"users": [a[0] for a in accounts]})
    tables = inspect(db.engine).get_table_names()
    print("\ntables (migration head applied):")
    with db.session() as session:
        for t in sorted(tables):
            if t in Base.metadata.tables:
                n = session.execute(select(func.count()).select_from(Base.metadata.tables[t])).scalar_one()
                print(f"  {t:<20} {n:>6} rows")
            else:
                print(f"  {t}")
    print("\nnext: python 02_start_backend.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
