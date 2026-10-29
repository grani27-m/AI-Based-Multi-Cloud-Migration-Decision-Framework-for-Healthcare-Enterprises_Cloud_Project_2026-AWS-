"""Alembic environment. URL precedence: config option (set by backend.db.run_migrations) > DATABASE_URL > SQLite default."""

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.db import Base  # noqa: E402
import backend.models  # noqa: E402,F401  (registers tables)

config = context.config
url = (
    config.get_main_option("sqlalchemy.url")
    or os.environ.get("DATABASE_URL")
    or f"sqlite:///{ROOT / 'runtime' / 'app.db'}"
)
config.set_main_option("sqlalchemy.url", url)
if url.startswith("sqlite"):
    (ROOT / "runtime").mkdir(exist_ok=True)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=connection.dialect.name == "sqlite"
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
