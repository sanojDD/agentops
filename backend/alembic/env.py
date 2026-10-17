from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db.base import Base
from app.db.session import get_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_database_url()
    if not url:
        # Lets the first Render deploy succeed before a database is configured.
        print("DATABASE_URL is not set: skipping migrations.")
        return

    connect_args = {} if url.startswith("sqlite") else {"connect_timeout": 30}
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline mode is not supported. Run: alembic upgrade head")
run_migrations_online()
