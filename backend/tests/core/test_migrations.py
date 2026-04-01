import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import settings


def test_alembic_upgrade_head_applies_payment_schema(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "migration-upgrade.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            INSERT INTO alembic_version (version_num) VALUES ('20260401_0002');

            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                password_hash VARCHAR(512) NOT NULL,
                display_name VARCHAR(255),
                created_at DATETIME NOT NULL
            );

            CREATE TABLE runtime_access_sessions (
                id INTEGER PRIMARY KEY
            );

            CREATE TABLE usage_charges (
                id INTEGER PRIMARY KEY
            );

            CREATE TABLE buyer_wallets (
                id INTEGER PRIMARY KEY,
                buyer_user_id INTEGER NOT NULL,
                balance_cny_credits FLOAT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );

            CREATE TABLE wallet_ledgers (
                id INTEGER PRIMARY KEY,
                buyer_user_id INTEGER NOT NULL,
                session_id INTEGER,
                usage_charge_id INTEGER,
                entry_type VARCHAR(50) NOT NULL,
                amount_delta_cny FLOAT NOT NULL,
                balance_after FLOAT NOT NULL,
                detail JSON NOT NULL,
                created_at DATETIME NOT NULL
            );

            CREATE TABLE buyer_orders (
                id INTEGER PRIMARY KEY,
                buyer_user_id INTEGER NOT NULL,
                offer_id INTEGER NOT NULL,
                requested_duration_minutes INTEGER NOT NULL,
                issued_hourly_price_cny FLOAT NOT NULL,
                order_status VARCHAR(50) NOT NULL,
                license_token VARCHAR(255) NOT NULL,
                license_redeemed_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    database_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    try:
        inspector = inspect(engine)
        assert "payment_orders" in inspector.get_table_names()
        assert "payment_transactions" in inspector.get_table_names()

        buyer_wallet_columns = {column["name"] for column in inspector.get_columns("buyer_wallets")}
        assert "status" in buyer_wallet_columns
        assert "frozen_amount_cny" in buyer_wallet_columns

        buyer_order_columns = {column["name"] for column in inspector.get_columns("buyer_orders")}
        assert "order_no" in buyer_order_columns
        assert "payment_status" in buyer_order_columns
        assert "paid_at" in buyer_order_columns

        wallet_ledger_columns = {column["name"] for column in inspector.get_columns("wallet_ledgers")}
        assert "payment_order_id" in wallet_ledger_columns
    finally:
        engine.dispose()
