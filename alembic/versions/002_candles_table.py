"""Add candles table for Timescale hypertable multi-timeframe market data

Revision ID: 002_candles_table
Revises: 001_initial_schema
Create Date: 2026-10-07 22:15:00

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "002_candles_table"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(32), index=True, nullable=False),
        sa.Column("timeframe", sa.String(16), index=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("vwap", sa.Float(), nullable=True),
        sa.UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_candles_sym_tf_ts"),
    )

    # In PostgreSQL with TimescaleDB extension, convert table to hypertable:
    # op.execute("SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE);")


def downgrade() -> None:
    op.drop_table("candles")
