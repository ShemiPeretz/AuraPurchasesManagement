"""
Unit Tests for Customer Facing Web Server

Tests cover:
1. API endpoints
2. Kafka producer integration
3. Data validation
4. Error handling
5. Proxy functionality

Run with: pytest -v test_main.py
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from fastapi.testclient import TestClient
import httpx

# Import application components
import sys

sys.path.insert(0, '..')
from main import app, BuyRequest, PurchaseEvent, select_random_item


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_buy_request():
    """Sample buy request for testing."""
    return BuyRequest(
        username="test_user",
        user_id="user_123"
    )


@pytest.fixture
def sample_purchase_event():
    """Sample purchase event for testing."""
    return PurchaseEvent(
        username="test_user",
        user_id="user_123",
        item_name="Laptop",
        price=999.99,
        timestamp="2025-12-15T10:30:00Z"
    )


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer for testing."""
    producer = AsyncMock()
    producer.is_connected.return_value = True

    # Mock send_message to return record metadata
    mock_metadata = MagicMock()
    mock_metadata.partition = 0
    mock_metadata.offset = 42
    mock_metadata.topic = "purchases"
    producer.send_message.return_value = mock_metadata

    producer.get_stats.return_value = {
        "messages_sent": 10,
        "messages_failed": 0,
        "connected": True
    }

    return producer


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for testing."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def client(mock_kafka_producer, mock_http_client):
    """Test client with mocked dependencies."""
    with patch('main.kafka_producer', mock_kafka_producer), \
            patch('main.http_client', mock_http_client):
        yield TestClient(app)


# ============================================================================
# DATA MODEL TESTS
# ============================================================================

class TestDataModels:
    """Test data model validation."""

    def test_valid_buy_request(self, sample_buy_request):
        """Test creating a valid buy request."""
        assert sample_buy_request.username == "test_user"
        assert sample_buy_request.user_id == "user_123"

    def test_buy_request_empty_username(self):
        """Test that empty username is rejected."""
        with pytest.raises(ValueError):
            BuyRequest(username="", user_id="user_123")

    def test_buy_request_whitespace_username(self):
        """Test that whitespace-only username is rejected."""
        with pytest.raises(ValueError):
            BuyRequest(username="   ", user_id="user_123")

    def test_buy_request_whitespace_trimming(self):
        """Test that whitespace is trimmed from username."""
        request = BuyRequest(username="  test_user  ", user_id="user_123")
        assert request.username == "test_user"

    def test_valid_purchase_event(self, sample_purchase_event):
        """Test creating a valid purchase event."""
        assert sample_purchase_event.username == "test_user"
        assert sample_purchase_event.price == 999.99
        assert sample_purchase_event.price > 0

    def test_purchase_event_invalid_price(self):
        """Test that zero/negative prices are rejected."""
        with pytest.raises(ValueError):
            PurchaseEvent(
                username="test_user",
                user_id="user_123",
                item_name="Laptop",
                price=0,  # Invalid
                timestamp="2025-12-15T10:30:00Z"
            )


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestHelperFunctions:
    """Test helper functions."""

    def test_select_random_item(self):
        """Test random item selection."""
        item = select_random_item()

        assert "name" in item
        assert "price" in item
        assert isinstance(item["name"], str)
        assert isinstance(item["price"], (int, float))
        assert item["price"] > 0

    def test_select_random_item_variety(self):
        """Test that different items can be selected."""
        items = [select_random_item() for _ in range(20)]
        unique_items = set(item["name"] for item in items)

        # With 20 selections from 15 items, we should get some variety
        assert len(unique_items) > 1


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestAPIEndpoints:
    """Test FastAPI endpoints."""

    def test_root_endpoint(self, client):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "service" in data
        assert data["service"] == "Customer Facing Web Server"
        assert "endpoints" in data

    def test_health_endpoint_healthy(self, client, mock_kafka_producer, mock_http_client):
        """Test health endpoint when services are healthy."""
        # Mock Customer Management API health check
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_client.get.return_value = mock_response

        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["kafka_connected"] is True
        assert data["customer_management_api_reachable"] is True

    def test_health_endpoint_kafka_down(self, client, mock_kafka_producer, mock_http_client):
        """Test health endpoint when Kafka is down."""
        # Simulate Kafka down
        mock_kafka_producer.is_connected.return_value = False

        # Mock CM API as healthy
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_client.get.return_value = mock_response

        response = client.get("/health")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["kafka_connected"] is False

    def test_health_endpoint_cm_api_down(self, client, mock_kafka_producer, mock_http_client):
        """Test health endpoint when Customer Management API is down."""
        # Kafka is healthy
        mock_kafka_producer.is_connected.return_value = True

        # Simulate CM API down
        mock_http_client.get.side_effect = Exception("Connection refused")

        response = client.get("/health")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["customer_management_api_reachable"] is False

    def test_get_available_items(self, client):
        """Test getting list of available items."""
        response = client.get("/items")
        assert response.status_code == 200

        items = response.json()
        assert isinstance(items, list)
        assert len(items) > 0

        # Verify item structure
        for item in items:
            assert "name" in item
            assert "price" in item

    def test_metrics_endpoint(self, client, mock_kafka_producer):
        """Test metrics endpoint."""
        response = client.get("/metrics")
        assert response.status_code == 200

        data = response.json()
        assert "service" in data
        assert "messages_sent" in data
        assert "kafka_connected" in data


# ============================================================================
# BUY ENDPOINT TESTS
# ============================================================================

class TestBuyEndpoint:
    """Test /buy endpoint."""

    def test_buy_success(self, client, mock_kafka_producer):
        """Test successful purchase."""
        buy_data = {
            "username": "john_doe",
            "user_id": "user_123"
        }

        response = client.post("/buy", json=buy_data)
        assert response.status_code == 201

        data = response.json()
        assert data["success"] is True
        assert "purchase" in data
        assert data["purchase"]["username"] == "john_doe"
        assert data["purchase"]["user_id"] == "user_123"
        assert data["purchase"]["price"] > 0
        assert "kafka_partition" in data
        assert "kafka_offset" in data

        # Verify Kafka producer was called
        mock_kafka_producer.send_message.assert_called_once()

    def test_buy_invalid_request(self, client):
        """Test buy with invalid data."""
        # Missing username
        buy_data = {
            "user_id": "user_123"
        }

        response = client.post("/buy", json=buy_data)
        assert response.status_code == 422  # Validation error

    def test_buy_empty_username(self, client):
        """Test buy with empty username."""
        buy_data = {
            "username": "",
            "user_id": "user_123"
        }

        response = client.post("/buy", json=buy_data)
        assert response.status_code == 422

    def test_buy_kafka_unavailable(self, client, mock_kafka_producer):
        """Test buy when Kafka is unavailable."""
        # Simulate Kafka down
        mock_kafka_producer.is_connected.return_value = False

        buy_data = {
            "username": "john_doe",
            "user_id": "user_123"
        }

        response = client.post("/buy", json=buy_data)
        assert response.status_code == 503

        data = response.json()
        assert "unavailable" in data["detail"].lower()

    def test_buy_kafka_send_fails(self, client, mock_kafka_producer):
        """Test buy when Kafka send operation fails."""
        # Simulate Kafka send failure
        mock_kafka_producer.send_message.side_effect = Exception("Kafka error")

        buy_data = {
            "username": "john_doe",
            "user_id": "user_123"
        }

        response = client.post("/buy", json=buy_data)
        assert response.status_code == 500

    def test_buy_multiple_purchases(self, client, mock_kafka_producer):
        """Test multiple purchases from same user."""
        buy_data = {
            "username": "john_doe",
            "user_id": "user_123"
        }

        # Make 5 purchases
        for i in range(5):
            response = client.post("/buy", json=buy_data)
            assert response.status_code == 201

        # Verify producer was called 5 times
        assert mock_kafka_producer.send_message.call_count == 5


# ============================================================================
# GET PURCHASES ENDPOINT TESTS
# ============================================================================

class TestGetPurchasesEndpoint:
    """Test /purchases/{user_id} endpoint."""

    def test_get_purchases_success(self, client, mock_http_client):
        """Test successful retrieval of purchases."""
        # Mock Customer Management API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "user_123",
            "username": "john_doe",
            "total_purchases": 5,
            "total_spent": 2599.95,
            "purchases": [
                {
                    "_id": "507f1f77bcf86cd799439011",
                    "username": "john_doe",
                    "user_id": "user_123",
                    "item_name": "Laptop",
                    "price": 999.99,
                    "timestamp": "2025-12-15T10:30:00Z"
                }
            ]
        }
        mock_http_client.get.return_value = mock_response

        response = client.get("/purchases/user_123")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "user_123"
        assert data["total_purchases"] == 5
        assert len(data["purchases"]) == 1

    def test_get_purchases_not_found(self, client, mock_http_client):
        """Test getting purchases for user with no purchases."""
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http_client.get.return_value = mock_response

        response = client.get("/purchases/user_999")
        assert response.status_code == 404

        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_purchases_cm_api_unavailable(self, client, mock_http_client):
        """Test getting purchases when CM API is unavailable."""
        # Simulate connection error
        mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")

        response = client.get("/purchases/user_123")
        assert response.status_code == 503

        data = response.json()
        assert "unavailable" in data["detail"].lower()

    def test_get_purchases_timeout(self, client, mock_http_client):
        """Test getting purchases with timeout."""
        # Simulate timeout
        mock_http_client.get.side_effect = httpx.TimeoutException("Request timeout")

        response = client.get("/purchases/user_123")
        assert response.status_code == 503

        data = response.json()
        assert "timeout" in data["detail"].lower()

    def test_get_purchases_cm_api_error(self, client, mock_http_client):
        """Test getting purchases when CM API returns error."""
        # Mock 500 response from CM API
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_http_client.get.return_value = mock_response

        response = client.get("/purchases/user_123")
        assert response.status_code == 503


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for the complete flow."""

    def test_buy_and_retrieve_flow(self, client, mock_kafka_producer, mock_http_client):
        """Test complete flow: buy -> kafka -> retrieve."""
        # Step 1: Make a purchase
        buy_data = {
            "username": "integration_user",
            "user_id": "user_integration"
        }

        buy_response = client.post("/buy", json=buy_data)
        assert buy_response.status_code == 201

        purchase_data = buy_response.json()["purchase"]

        # Step 2: Mock retrieval response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "user_integration",
            "username": "integration_user",
            "total_purchases": 1,
            "total_spent": purchase_data["price"],
            "purchases": [
                {
                    "_id": "507f1f77bcf86cd799439011",
                    **purchase_data
                }
            ]
        }
        mock_http_client.get.return_value = mock_response

        # Step 3: Retrieve purchases
        get_response = client.get("/purchases/user_integration")
        assert get_response.status_code == 200

        retrieved_data = get_response.json()
        assert retrieved_data["user_id"] == "user_integration"
        assert retrieved_data["total_purchases"] == 1


# ============================================================================
# CORS TESTS
# ============================================================================

class TestCORS:
    """Test CORS middleware."""

    def test_cors_headers(self, client):
        """Test that CORS headers are present."""
        response = client.options("/")

        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers

    def test_cors_preflight(self, client):
        """Test CORS preflight request."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"
        }

        response = client.options("/buy", headers=headers)
        assert response.status_code == 200


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run tests with: python test_main.py
    pytest.main([__file__, "-v", "--cov=main", "--cov-report=term-missing"])