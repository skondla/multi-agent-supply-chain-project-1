"""
Pytest configuration and shared fixtures.
"""
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from unittest.mock import AsyncMock, MagicMock, patch

# Use SQLite for tests (no postgres required for unit tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        from app.core.database import Base
        # Import all models
        from app.models import order, inventory, supplier, shipment, user  # noqa
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        from app.core.database import Base
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.ping = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic Claude API client."""
    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(type="text", text="Mock AI response for testing")
        ]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_client.messages.create = MagicMock(return_value=mock_response)
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_slack():
    """Mock Slack notifier."""
    with patch("app.core.slack_notifier.SlackNotifier.send") as mock_send:
        mock_send.return_value = AsyncMock(return_value=True)
        yield mock_send


@pytest.fixture
def sample_order_data():
    return {
        "customer_id": "cust-test-001",
        "customer_name": "Test Customer",
        "customer_email": "test@example.com",
        "items": [
            {"sku": "SKU-001", "quantity": 5, "unit_price": 25.99},
            {"sku": "SKU-002", "quantity": 2, "unit_price": 49.99},
        ],
        "shipping_address": {
            "street": "123 Test St",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "country": "US",
        },
        "priority": "high",
    }


@pytest.fixture
def sample_inventory_data():
    return {
        "sku": "SKU-TEST-001",
        "product_name": "Test Widget Pro",
        "description": "A test widget for unit testing",
        "quantity_on_hand": 100,
        "reorder_point": 20,
        "reorder_quantity": 50,
        "unit_cost": 10.50,
        "unit_price": 25.99,
        "currency": "USD",
        "category": "Electronics",
        "subcategory": "Widgets",
        "lead_time_days": 7,
        "warehouse_id": "WH-001",
    }


@pytest.fixture
def sample_supplier_data():
    return {
        "name": "Test Supplier Corporation",
        "code": "TSC-TEST-001",
        "contact_name": "Jane Smith",
        "email": "jane@testsupplier.com",
        "phone": "+1-555-0100",
        "country": "US",
        "payment_terms": "NET30",
        "lead_time_days": 7,
        "categories": ["Electronics", "Widgets"],
        "certifications": ["ISO9001"],
    }
