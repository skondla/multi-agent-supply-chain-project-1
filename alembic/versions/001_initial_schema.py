"""Initial database schema.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="operator"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("full_name", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # ── suppliers ─────────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("address", postgresql.JSONB()),
        sa.Column("country", sa.String(100)),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("payment_terms", sa.Integer(), server_default="30"),
        sa.Column("lead_time_days", sa.Integer(), server_default="7"),
        sa.Column("reliability_score", sa.Numeric(4, 3), server_default="0.800"),
        sa.Column("quality_score", sa.Numeric(4, 3), server_default="0.800"),
        sa.Column("delivery_score", sa.Numeric(4, 3), server_default="0.800"),
        sa.Column("price_competitiveness_score", sa.Numeric(4, 3), server_default="0.800"),
        sa.Column("overall_score", sa.Numeric(4, 3), server_default="0.800"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("is_preferred", sa.Boolean(), server_default="false"),
        sa.Column("contract_start_date", sa.Date()),
        sa.Column("contract_end_date", sa.Date()),
        sa.Column("certifications", postgresql.ARRAY(sa.String())),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_suppliers_code", "suppliers", ["code"])
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    # ── inventory ─────────────────────────────────────────────────────────────
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("sku", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(100)),
        sa.Column("unit_of_measure", sa.String(50), server_default="unit"),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_on_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reorder_point", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("reorder_quantity", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("max_stock_level", sa.Integer()),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(12, 4)),
        sa.Column("warehouse_location", sa.String(100)),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("suppliers.id")),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("last_counted_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_inventory_qty_on_hand"),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_inventory_qty_reserved"),
        sa.CheckConstraint("quantity_on_order >= 0", name="ck_inventory_qty_on_order"),
        sa.CheckConstraint("reorder_point >= 0", name="ck_inventory_reorder_point"),
    )
    op.create_index("ix_inventory_sku", "inventory", ["sku"])
    op.create_index("ix_inventory_category", "inventory", ["category"])
    op.create_index("ix_inventory_supplier", "inventory", ["supplier_id"])

    # ── orders ────────────────────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("order_number", sa.String(50), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_email", sa.String(255)),
        sa.Column("customer_name", sa.String(255)),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(50), nullable=False, server_default="standard"),
        sa.Column("items", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("shipping_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("shipping_address", postgresql.JSONB()),
        sa.Column("billing_address", postgresql.JSONB()),
        sa.Column("notes", sa.Text()),
        sa.Column("fraud_score", sa.Numeric(4, 3), server_default="0"),
        sa.Column("fraud_indicators", postgresql.JSONB(), server_default="[]"),
        sa.Column("agent_task_id", sa.String(255)),
        sa.Column("agent_result", postgresql.JSONB()),
        sa.Column("requested_delivery_date", sa.DateTime(timezone=True)),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])
    op.create_index(
        "ix_orders_customer_search",
        "orders",
        [sa.text("to_tsvector('english', customer_name || ' ' || customer_email)")],
        postgresql_using="gin",
    )

    # ── shipments ─────────────────────────────────────────────────────────────
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("tracking_number", sa.String(100), unique=True),
        sa.Column("carrier", sa.String(100)),
        sa.Column("service_level", sa.String(50)),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("origin_address", postgresql.JSONB()),
        sa.Column("destination_address", postgresql.JSONB()),
        sa.Column("current_location", postgresql.JSONB()),
        sa.Column("route_history", postgresql.JSONB(), server_default="[]"),
        sa.Column("estimated_weight_kg", sa.Numeric(10, 3)),
        sa.Column("shipping_cost", sa.Numeric(12, 2)),
        sa.Column("label_url", sa.String(500)),
        sa.Column("estimated_delivery_date", sa.DateTime(timezone=True)),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"])
    op.create_index("ix_shipments_status", "shipments", ["status"])


def downgrade() -> None:
    op.drop_table("shipments")
    op.drop_table("orders")
    op.drop_table("inventory")
    op.drop_table("suppliers")
    op.drop_table("users")
