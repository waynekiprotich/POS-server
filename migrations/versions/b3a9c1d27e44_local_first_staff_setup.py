"""Local-first shop: business record, staff PINs, extra roles, sale voids.

Existing installations keep every row. If users already exist, a business
row is created from the stored settings and marked as set up, so the first-run
wizard does not appear for a shop that is already trading.

Revision ID: b3a9c1d27e44
Revises: 0676bd67ffb2
Create Date: 2026-09-22
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "b3a9c1d27e44"
down_revision = "0676bd67ffb2"
branch_labels = None
depends_on = None

SCOPED_TABLES = ("users", "categories", "products", "sales")


def upgrade():
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("pin_hash", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("phone", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        batch.alter_column("email", existing_type=sa.String(length=160), nullable=True)

    with op.batch_alter_table("sales") as batch:
        batch.add_column(
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="completed"
            )
        )
        batch.add_column(sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("voided_by_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("void_reason", sa.String(length=255), nullable=True))
        batch.create_index("ix_sales_status", ["status"], unique=False)
        batch.create_foreign_key("fk_sales_voided_by_id_users", "users", ["voided_by_id"], ["id"])

    for table in SCOPED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
            batch.create_index("ix_%s_business_id" % table, ["business_id"], unique=False)
            batch.create_foreign_key(
                "fk_%s_business_id_businesses" % table, "businesses", ["business_id"], ["id"]
            )

    _adopt_existing_shop()


def _adopt_existing_shop():
    conn = op.get_bind()
    if not conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar():
        return
    name = conn.execute(
        sa.text("SELECT value FROM settings WHERE key = 'business_name'")
    ).scalar()
    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            "INSERT INTO businesses (name, setup_completed_at, created_at) "
            "VALUES (:name, :now, :now)"
        ),
        {"name": name or "My Shop", "now": now},
    )
    business_id = conn.execute(sa.text("SELECT MIN(id) FROM businesses")).scalar()
    for table in SCOPED_TABLES:
        conn.execute(
            sa.text("UPDATE %s SET business_id = :id WHERE business_id IS NULL" % table),
            {"id": business_id},
        )


def downgrade():
    for table in SCOPED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint("fk_%s_business_id_businesses" % table, type_="foreignkey")
            batch.drop_index("ix_%s_business_id" % table)
            batch.drop_column("business_id")

    with op.batch_alter_table("sales") as batch:
        batch.drop_constraint("fk_sales_voided_by_id_users", type_="foreignkey")
        batch.drop_index("ix_sales_status")
        batch.drop_column("void_reason")
        batch.drop_column("voided_by_id")
        batch.drop_column("voided_at")
        batch.drop_column("status")

    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(length=160), nullable=False)
        batch.drop_column("last_login_at")
        batch.drop_column("phone")
        batch.drop_column("pin_hash")

    op.drop_table("businesses")
