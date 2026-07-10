import sys
from pathlib import Path

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import get_settings
from db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url from settings
_db_url = get_settings().database_url
# SQLite does not create parent directories — ensure data/ exists on a fresh clone.
if _db_url.startswith("sqlite:///") and not _db_url.endswith(":memory:"):
    Path(_db_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
