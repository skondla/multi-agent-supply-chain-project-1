"""Seed database with sample data for development/testing."""
import asyncio
import random
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.supplier import Supplier
from app.models.inventory import Inventory
from app.models.order import Order, OrderStatus, OrderPriority
from app.models.user import User, UserRole
from app.core.security import hash_password

SUPPLIERS = [
    {"name": "TechParts Global", "code": "TPG-001", "country": "USA", "reliability_score": 0.95, "quality_score": 0.92},
    {"name": "Asian Manufacturing Co", "code": "AMC-002", "country": "China", "reliability_score": 0.88, "quality_score": 0.90},
    {"name": "Euro Components Ltd", "code": "ECL-003", "country": "Germany", "reliability_score": 0.97, "quality_score": 0.98},
    {"name": "Pacific Supply Chain", "code": "PSC-004", "country": "Japan", "reliability_score": 0.93, "quality_score": 0.95},
]

PRODUCTS = [
    {"sku": "ELEC-001", "name": "Laptop Computer 15\"", "category": "Electronics", "unit_cost": 650.00, "reorder_point": 10},
    {"sku": "ELEC-002", "name": "Wireless Mouse", "category": "Electronics", "unit_cost": 25.00, "reorder_point": 50},
    {"sku": "COMP-001", "name": "SSD 1TB NVMe", "category": "Components", "unit_cost": 120.00, "reorder_point": 20},
    {"sku": "COMP-002", "name": "DDR5 RAM 32GB", "category": "Components", "unit_cost": 150.00, "reorder_point": 15},
    {"sku": "PERI-001", "name": "Mechanical Keyboard", "category": "Peripherals", "unit_cost": 89.00, "reorder_point": 25},
    {"sku": "PERI-002", "name": "27\" 4K Monitor", "category": "Peripherals", "unit_cost": 399.00, "reorder_point": 8},
    {"sku": "NET-001", "name": "Network Switch 48-Port", "category": "Networking", "unit_cost": 320.00, "reorder_point": 5},
]


async def seed_database():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("Seeding database...")

        # Users
        for email, username, role, full_name, password in [
            ("admin@supply-chain.local", "admin", UserRole.ADMIN, "System Administrator", "Admin@12345"),
            ("analyst@supply-chain.local", "analyst", UserRole.ANALYST, "Supply Chain Analyst", "Analyst@12345"),
            ("operator@supply-chain.local", "operator", UserRole.OPERATOR, "Supply Chain Operator", "Operator@12345"),
        ]:
            user = User(email=email, username=username, hashed_password=hash_password(password),
                       role=role, full_name=full_name, is_active=True, is_verified=True)
            session.add(user)
        await session.flush()
        print("✓ Users created")

        # Suppliers
        supplier_objs = []
        for s in SUPPLIERS:
            supplier = Supplier(
                name=s["name"], code=s["code"], country=s["country"],
                reliability_score=s["reliability_score"], quality_score=s["quality_score"],
                delivery_score=random.uniform(0.85, 0.98),
                price_competitiveness_score=random.uniform(0.75, 0.95),
                overall_score=(s["reliability_score"] + s["quality_score"]) / 2,
                lead_time_days=random.randint(3, 14), payment_terms=30, is_active=True,
            )
            session.add(supplier)
            supplier_objs.append(supplier)
        await session.flush()
        print("✓ Suppliers created")

        # Inventory
        for i, p in enumerate(PRODUCTS):
            qty = random.randint(20, 200)
            inventory = Inventory(
                sku=p["sku"], name=p["name"], category=p["category"],
                unit_cost=p["unit_cost"], unit_price=p["unit_cost"] * 1.35,
                quantity_on_hand=qty, quantity_reserved=random.randint(0, min(10, qty)),
                reorder_point=p["reorder_point"], reorder_quantity=p["reorder_point"] * 5,
                warehouse_location=f"RACK-{chr(65 + i % 26)}-{random.randint(1, 99):02d}",
                supplier_id=supplier_objs[i % len(supplier_objs)].id, is_active=True,
            )
            session.add(inventory)
        await session.flush()
        print("✓ Inventory created")

        # Orders
        for j in range(25):
            days_ago = random.randint(0, 30)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
            product = random.choice(PRODUCTS)
            qty = random.randint(1, 5)
            subtotal = product["unit_cost"] * qty
            order = Order(
                order_number=f"ORD-{created_at.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}",
                customer_id=uuid.uuid4(),
                customer_email=f"customer{j}@example.com",
                customer_name=f"Customer {j}",
                status=random.choice(list(OrderStatus)),
                priority=random.choice(list(OrderPriority)),
                items=[{"sku": product["sku"], "name": product["name"], "quantity": qty, "unit_price": product["unit_cost"]}],
                subtotal=subtotal, tax_amount=round(subtotal * 0.08, 2),
                shipping_cost=random.uniform(5, 50), total_amount=round(subtotal * 1.08 + random.uniform(5, 50), 2),
                currency="USD", created_at=created_at, updated_at=created_at,
            )
            session.add(order)

        await session.commit()
        print("✓ Sample orders created")
        print("\n✅ Database seeding complete!")
        print("   admin@supply-chain.local / Admin@12345")
        print("   analyst@supply-chain.local / Analyst@12345")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
