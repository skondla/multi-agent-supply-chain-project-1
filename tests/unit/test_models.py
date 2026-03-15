"""
Unit tests for database models and business logic.
"""
import pytest
from decimal import Decimal


@pytest.mark.unit
class TestOrderModel:
    def test_order_is_cancellable_when_pending(self):
        from app.models.order import Order, OrderStatus
        order = Order()
        order.status = OrderStatus.PENDING
        assert order.is_cancellable is True

    def test_order_is_cancellable_when_confirmed(self):
        from app.models.order import Order, OrderStatus
        order = Order()
        order.status = OrderStatus.CONFIRMED
        assert order.is_cancellable is True

    def test_order_not_cancellable_when_shipped(self):
        from app.models.order import Order, OrderStatus
        order = Order()
        order.status = OrderStatus.SHIPPED
        assert order.is_cancellable is False

    def test_order_is_shippable_when_processing(self):
        from app.models.order import Order, OrderStatus
        order = Order()
        order.status = OrderStatus.PROCESSING
        assert order.is_shippable is True

    def test_order_not_shippable_when_pending(self):
        from app.models.order import Order, OrderStatus
        order = Order()
        order.status = OrderStatus.PENDING
        assert order.is_shippable is False


@pytest.mark.unit
class TestInventoryModel:
    def test_quantity_available_calculation(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 100
        item.quantity_reserved = 25
        assert item.quantity_available == 75

    def test_quantity_available_never_negative(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 10
        item.quantity_reserved = 50  # More reserved than on hand
        assert item.quantity_available == 0

    def test_is_low_stock_true(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 5
        item.reorder_point = 20
        assert item.is_low_stock is True

    def test_is_low_stock_false(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 100
        item.reorder_point = 20
        assert item.is_low_stock is False

    def test_is_out_of_stock(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 0
        item.quantity_reserved = 0
        assert item.is_out_of_stock is True

    def test_needs_reorder_active_and_low(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 5
        item.reorder_point = 20
        item.is_active = True
        assert item.needs_reorder is True

    def test_needs_reorder_inactive(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 5
        item.reorder_point = 20
        item.is_active = False
        assert item.needs_reorder is False

    def test_total_value(self):
        from app.models.inventory import Inventory
        item = Inventory()
        item.quantity_on_hand = 100
        item.unit_cost = Decimal("12.50")
        assert item.total_value == 1250.0


@pytest.mark.unit
class TestSupplierModel:
    def test_is_preferred_high_score(self):
        from app.models.supplier import Supplier
        supplier = Supplier()
        supplier.overall_score = Decimal("0.92")
        assert supplier.is_preferred is True

    def test_is_preferred_low_score(self):
        from app.models.supplier import Supplier
        supplier = Supplier()
        supplier.overall_score = Decimal("0.80")
        assert supplier.is_preferred is False

    def test_is_at_risk(self):
        from app.models.supplier import Supplier
        supplier = Supplier()
        supplier.overall_score = Decimal("0.55")
        assert supplier.is_at_risk is True

    def test_not_at_risk(self):
        from app.models.supplier import Supplier
        supplier = Supplier()
        supplier.overall_score = Decimal("0.90")
        assert supplier.is_at_risk is False


@pytest.mark.unit
class TestSecurityUtils:
    def test_password_hashing(self):
        from app.core.security import hash_password, verify_password
        password = "SecurePassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password_rejected(self):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correct-password")
        assert verify_password("wrong-password", hashed) is False

    def test_create_access_token(self):
        from app.core.security import create_access_token, decode_token
        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 20
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        from app.core.security import create_refresh_token, decode_token
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    def test_decode_invalid_token_raises(self):
        from app.core.security import decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            decode_token("invalid.token.here")
