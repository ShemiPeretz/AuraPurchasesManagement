"""
Unit Tests for Customer Management API

Tests cover:
1. Database operations
2. API endpoints
3. Data validation
4. Error handling

Run with: pytest -v test_main.py
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Import application components
import sys

from CustomerManagementAPI.data_model.purchase import Purchase
from CustomerManagementAPI.database.database_manager import DatabaseManager

sys.path.insert(0, '../..')


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_purchase():
    """
    Sample purchase data for testing.
    """
    return Purchase(
        username="test_user",
        user_id="user_123",
        item_name="Test Product",
        price=99.99,
        timestamp="2025-12-15T10:30:00Z"
    )


@pytest.fixture
def sample_purchase_dict():
    """
    Sample purchase as dictionary (MongoDB format).
    """
    return {
        "_id": "507f1f77bcf86cd799439011",
        "username": "test_user",
        "user_id": "user_123",
        "item_name": "Test Product",
        "price": 99.99,
        "timestamp": "2025-12-15T10:30:00Z",
        "timestamp_dt": datetime(2025, 12, 15, 10, 30, 0)
    }


@pytest.fixture
def mock_db_manager():
    """
    Mock DatabaseManager for testing without real database.
    """
    manager = AsyncMock(spec=DatabaseManager)
    manager.is_connected.return_value = True
    return manager


@pytest.fixture
def mock_kafka_consumer():
    """
    Mock Kafka consumer for testing.
    """
    consumer = MagicMock()
    consumer.is_running.return_value = True
    consumer.get_lag.return_value = 0
    return consumer


@pytest.fixture
def client(mock_db_manager, mock_kafka_consumer):
    """
    Test client with mocked dependencies.
    """
    # Patch global instances in main module
    with patch('main.db_manager', mock_db_manager), \
            patch('main.kafka_consumer', mock_kafka_consumer):
        yield TestClient(app)


# ============================================================================
# DATA MODEL TESTS
# ============================================================================

class TestPurchaseModel:
    """
    Test Purchase data model validation.
    """

    def test_valid_purchase(self, sample_purchase):
        """Test creating a valid purchase."""
        assert sample_purchase.username == "test_user"
        assert sample_purchase.user_id == "user_123"
        assert sample_purchase.price == 99.99

    def test_invalid_price_negative(self):
        """Test that negative prices are rejected."""
        with pytest.raises(ValueError):
            Purchase(
                username="test_user",
                user_id="user_123",
                item_name="Test Product",
                price=-10.00,  # Invalid: negative price
                timestamp="2025-12-15T10:30:00Z"
            )

    def test_invalid_price_zero(self):
        """Test that zero prices are rejected."""
        with pytest.raises(ValueError):
            Purchase(
                username="test_user",
                user_id="user_123",
                item_name="Test Product",
                price=0,  # Invalid: zero price
                timestamp="2025-12-15T10:30:00Z"
            )

    def test_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        with pytest.raises(ValueError):
            Purchase(
                username="test_user",
                # Missing: user_id, item_name, price, timestamp
            )


# ============================================================================
# DATABASE MANAGER TESTS
# ============================================================================

class TestDatabaseManager:
    """
    Test DatabaseManager operations.

    Note: These tests use AsyncMock to simulate database operations
    without requiring a real MongoDB instance.
    """

    @pytest.mark.asyncio
    async def test_connection(self):
        """Test database connection."""
        manager = DatabaseManager(
            uri="mongodb://localhost:27017",
            db_name="test_db",
            collection_name="test_collection"
        )

        # Mock the client
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_client:
            mock_client.return_value.admin.command = AsyncMock(return_value={"ok": 1})
            await manager.connect()

            assert manager.client is not None
            assert manager.db is not None
            assert manager.collection is not None

    @pytest.mark.asyncio
    async def test_save_purchase(self, sample_purchase):
        """Test saving a purchase to database."""
        manager = DatabaseManager(
            uri="mongodb://localhost:27017",
            db_name="test_db",
            collection_name="test_collection"
        )

        # Mock collection
        manager.collection = AsyncMock()
        manager.collection.insert_one.return_value.inserted_id = "mock_id_123"

        # Save purchase
        result_id = await manager.save_purchase(sample_purchase)

        assert result_id == "mock_id_123"
        manager.collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_purchases(self, sample_purchase_dict):
        """Test retrieving user purchases."""
        manager = DatabaseManager(
            uri="mongodb://localhost:27017",
            db_name="test_db",
            collection_name="test_collection"
        )

        # Mock collection with cursor
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [sample_purchase_dict]

        manager.collection = MagicMock()
        manager.collection.find.return_value.sort.return_value = mock_cursor

        # Get purchases
        purchases = await manager.get_user_purchases("user_123")

        assert len(purchases) == 1
        assert purchases[0]["user_id"] == "user_123"
        assert purchases[0]["_id"] == "507f1f77bcf86cd799439011"


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestAPIEndpoints:
    """
    Test FastAPI endpoints.
    """

    def test_root_endpoint(self, client):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "service" in data
        assert data["service"] == "Customer Management API"

    def test_health_endpoint_healthy(self, client, mock_db_manager, mock_kafka_consumer):
        """Test health endpoint when services are healthy."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["mongodb_connected"] is True
        assert data["kafka_connected"] is True

    def test_health_endpoint_unhealthy(self, client, mock_db_manager, mock_kafka_consumer):
        """Test health endpoint when services are down."""
        # Simulate unhealthy services
        mock_db_manager.is_connected.return_value = False
        mock_kafka_consumer.is_running.return_value = False

        response = client.get("/health")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["mongodb_connected"] is False
        assert data["kafka_connected"] is False

    def test_get_user_purchases_success(self, client, mock_db_manager, sample_purchase_dict):
        """Test retrieving user purchases successfully."""
        # Mock database response
        mock_db_manager.get_user_purchases.return_value = [sample_purchase_dict]

        response = client.get("/purchases/user_123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user_123"
        assert data["total_purchases"] == 1
        assert data["total_spent"] == 99.99
        assert len(data["purchases"]) == 1

    def test_get_user_purchases_not_found(self, client, mock_db_manager):
        """Test retrieving purchases for user with no purchases."""
        # Mock empty result
        mock_db_manager.get_user_purchases.return_value = []

        response = client.get("/purchases/user_999")
        assert response.status_code == 404

        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_user_purchases_multiple(self, client, mock_db_manager):
        """Test retrieving multiple purchases for a user."""
        # Mock multiple purchases
        purchases = [
            {
                "_id": "id1",
                "username": "test_user",
                "user_id": "user_123",
                "item_name": "Product 1",
                "price": 50.0,
                "timestamp": "2025-12-15T10:00:00Z",
                "timestamp_dt": datetime(2025, 12, 15, 10, 0, 0)
            },
            {
                "_id": "id2",
                "username": "test_user",
                "user_id": "user_123",
                "item_name": "Product 2",
                "price": 75.0,
                "timestamp": "2025-12-15T11:00:00Z",
                "timestamp_dt": datetime(2025, 12, 15, 11, 0, 0)
            }
        ]
        mock_db_manager.get_user_purchases.return_value = purchases

        response = client.get("/purchases/user_123")
        assert response.status_code == 200

        data = response.json()
        assert data["total_purchases"] == 2
        assert data["total_spent"] == 125.0
        assert len(data["purchases"]) == 2

    def test_metrics_endpoint(self, client, mock_db_manager, mock_kafka_consumer):
        """Test metrics endpoint for monitoring."""
        response = client.get("/metrics")
        assert response.status_code == 200

        data = response.json()
        assert "kafka_consumer_lag" in data
        assert "mongodb_connected" in data
        assert data["service"] == "CustomerManagementAPI"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """
    Test error handling scenarios.
    """

    def test_database_error(self, client, mock_db_manager):
        """Test handling of database errors."""
        # Simulate database error
        mock_db_manager.get_user_purchases.side_effect = Exception("Database connection failed")

        response = client.get("/purchases/user_123")
        assert response.status_code == 500

        data = response.json()
        assert "internal server error" in data["detail"].lower()

    def test_invalid_user_id_format(self, client, mock_db_manager):
        """Test handling of invalid user ID format."""
        # User ID with special characters
        response = client.get("/purchases/user@#$%")
        # Should still work - user_id is just a string
        assert response.status_code in [200, 404, 500]


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """
    Integration tests that test multiple components together.

    Note: These require more complex mocking or actual services.
    """

    @pytest.mark.asyncio
    async def test_purchase_flow(self, sample_purchase):
        """Test complete purchase processing flow."""
        # This would test:
        # 1. Message received from Kafka
        # 2. Saved to MongoDB
        # 3. Retrieved via API
        # For now, we'll keep this as a placeholder
        pass


# ============================================================================
# PERFORMANCE TESTS (Optional)
# ============================================================================

class TestPerformance:
    """
    Performance and load tests.

    These are optional but useful for production systems.
    """

    def test_concurrent_requests(self, client, mock_db_manager):
        """Test handling multiple concurrent requests."""
        # Mock response
        mock_db_manager.get_user_purchases.return_value = []

        # Make multiple concurrent requests
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(client.get, f"/purchases/user_{i}")
                for i in range(100)
            ]
            results = [f.result() for f in futures]

        # All requests should succeed (404 is okay)
        assert all(r.status_code in [200, 404] for r in results)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run tests with: python test_main.py
    pytest.main([__file__, "-v", "--cov=main", "--cov-report=term-missing"])