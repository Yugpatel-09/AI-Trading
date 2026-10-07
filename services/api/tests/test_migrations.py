import os

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_alembic_migrations_up_and_down(tmp_path):
    """
    Migration Lifecycle Test (WP-C).
    Proves that Alembic can apply all migrations up to head,
    and rollback cleanly down to base without schema corruption.
    """
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    sync_db_url = f"sqlite:///{db_file}"

    # Configure alembic
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    alembic_ini_path = os.path.join(repo_root, "alembic.ini")

    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(repo_root, "alembic"))
    alembic_cfg.set_main_option("version_locations", os.path.join(repo_root, "alembic", "versions"))
    alembic_cfg.set_main_option("path_separator", "os")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    sync_engine = create_engine(sync_db_url)
    inspector = inspect(sync_engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "users",
        "user_risk_settings",
        "session_tokens",
        "email_tokens",
        "broker_connections",
        "orders",
        "fills",
        "positions",
        "trades",
        "audit_logs",
        "candles",
    }
    assert expected_tables.issubset(set(tables)), f"Missing expected tables in {tables}"

    # 2. Downgrade to base
    command.downgrade(alembic_cfg, "base")

    inspector = inspect(sync_engine)
    post_downgrade_tables = inspector.get_table_names()
    # All platform tables should be removed
    for tbl in expected_tables:
        assert tbl not in post_downgrade_tables

    # 3. Upgrade to head again
    command.upgrade(alembic_cfg, "head")
    inspector = inspect(sync_engine)
    assert expected_tables.issubset(set(inspector.get_table_names()))
