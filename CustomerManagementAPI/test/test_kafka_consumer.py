"""
Unit Tests for Kafka Consumer Service

Tests cover:
1. Consumer initialization
2. Message processing
3. Error handling
4. Metrics tracking

Run with: pytest -v test_kafka_consumer.py
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Import components to test
import sys

sys.path.insert(0, '../..')
from CustomerManagementAPI.kafka.kafka_consumer import KafkaConsumer
from ..main import Purchase, DatabaseManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db_manager():
    """Mock DatabaseManager for testing."""
    manager = AsyncMock(spec=DatabaseManager)
    manager.save_purchase.return_value = "mock_purchase_id_123"
    return manager


@pytest.fixture
def sample_kafka_message():
    """Sample Kafka message for testing."""
    message = MagicMock()
    message.partition = 0
    message.offset = 42
    message.key = b"user_123"
    message.value = {
        "username": "test_user",
        "user_id": "user_123",
        "item_name": "Test Product",
        "price": 99.99,
        "timestamp": "2025-12-15T10:30:00Z"
    }
    return message


@pytest.fixture
def kafka_consumer_service(mock_db_manager):
    """Create KafkaConsumerService instance for testing."""
    return KafkaConsumer(
        bootstrap_servers="localhost:9092",
        topic="test-purchases",
        group_id="test-group",
        db_manager=mock_db_manager
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestKafkaConsumerInitialization:
    """Test consumer initialization."""

    def test_consumer_creation(self, kafka_consumer_service):
        """Test creating a consumer instance."""
        assert kafka_consumer_service.bootstrap_servers == "localhost:9092"
        assert kafka_consumer_service.topic == "test-purchases"
        assert kafka_consumer_service.group_id == "test-group"
        assert kafka_consumer_service.running is False
        assert kafka_consumer_service.consumer is None

    def test_initial_metrics(self, kafka_consumer_service):
        """Test initial metric values."""
        assert kafka_consumer_service.messages_processed == 0
        assert kafka_consumer_service.messages_failed == 0
        assert kafka_consumer_service.last_message_time is None


# ============================================================================
# CONSUMER LIFECYCLE TESTS
# ============================================================================

class TestKafkaConsumerLifecycle:
    """Test consumer start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_consumer(self, kafka_consumer_service):
        """Test starting the consumer."""
        with patch('kafka_consumer.AIOKafkaConsumer') as mock_consumer_class:
            # Mock consumer instance
            mock_consumer = AsyncMock()
            mock_consumer_class.return_value = mock_consumer

            # Start consumer
            await kafka_consumer_service.start()

            # Verify consumer was created and started
            assert kafka_consumer_service.running is True
            assert kafka_consumer_service.consumer is not None
            mock_consumer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_consumer(self, kafka_consumer_service):
        """Test stopping the consumer."""
        # Mock a running consumer
        mock_consumer = AsyncMock()
        kafka_consumer_service.consumer = mock_consumer
        kafka_consumer_service.running = True
        kafka_consumer_service.consumer_task = AsyncMock()

        # Stop consumer
        await kafka_consumer_service.stop()

        # Verify consumer was stopped
        assert kafka_consumer_service.running is False
        mock_consumer.stop.assert_called_once()

    def test_is_running_true(self, kafka_consumer_service):
        """Test is_running when consumer is active."""
        kafka_consumer_service.running = True
        kafka_consumer_service.consumer = MagicMock()

        assert kafka_consumer_service.is_running() is True

    def test_is_running_false(self, kafka_consumer_service):
        """Test is_running when consumer is not active."""
        kafka_consumer_service.running = False
        kafka_consumer_service.consumer = None

        assert kafka_consumer_service.is_running() is False


# ============================================================================
# MESSAGE PROCESSING TESTS
# ============================================================================

class TestMessageProcessing:
    """Test message processing logic."""

    @pytest.mark.asyncio
    async def test_process_valid_message(self, kafka_consumer_service, mock_db_manager, sample_kafka_message):
        """Test processing a valid message."""
        # Process message
        await kafka_consumer_service._process_message(sample_kafka_message)

        # Verify message was saved to database
        mock_db_manager.save_purchase.assert_called_once()

        # Verify metrics were updated
        assert kafka_consumer_service.messages_processed == 1
        assert kafka_consumer_service.messages_failed == 0
        assert kafka_consumer_service.last_message_time is not None

    @pytest.mark.asyncio
    async def test_process_invalid_message_format(self, kafka_consumer_service, mock_db_manager):
        """Test processing a message with invalid format."""
        # Create invalid message (missing required fields)
        invalid_message = MagicMock()
        invalid_message.partition = 0
        invalid_message.offset = 43
        invalid_message.key = b"user_456"
        invalid_message.value = {
            "username": "test_user",
            # Missing: user_id, item_name, price, timestamp
        }

        # Process message
        await kafka_consumer_service._process_message(invalid_message)

        # Verify message was NOT saved to database
        mock_db_manager.save_purchase.assert_not_called()

        # Verify failure was recorded
        assert kafka_consumer_service.messages_failed == 1
        assert kafka_consumer_service.messages_processed == 0

    @pytest.mark.asyncio
    async def test_process_invalid_price(self, kafka_consumer_service, mock_db_manager):
        """Test processing a message with invalid price."""
        # Create message with negative price
        invalid_message = MagicMock()
        invalid_message.partition = 0
        invalid_message.offset = 44
        invalid_message.key = b"user_789"
        invalid_message.value = {
            "username": "test_user",
            "user_id": "user_789",
            "item_name": "Test Product",
            "price": -10.00,  # Invalid negative price
            "timestamp": "2025-12-15T10:30:00Z"
        }

        # Process message
        await kafka_consumer_service._process_message(invalid_message)

        # Verify message was NOT saved
        mock_db_manager.save_purchase.assert_not_called()
        assert kafka_consumer_service.messages_failed == 1

    @pytest.mark.asyncio
    async def test_process_database_error(self, kafka_consumer_service, mock_db_manager, sample_kafka_message):
        """Test handling database errors during message processing."""
        # Simulate database error
        mock_db_manager.save_purchase.side_effect = Exception("Database connection failed")

        # Process message
        await kafka_consumer_service._process_message(sample_kafka_message)

        # Verify failure was recorded
        assert kafka_consumer_service.messages_failed == 1
        assert kafka_consumer_service.messages_processed == 0

    @pytest.mark.asyncio
    async def test_process_multiple_messages(self, kafka_consumer_service, mock_db_manager, sample_kafka_message):
        """Test processing multiple messages in sequence."""
        # Process same message 5 times
        for i in range(5):
            sample_kafka_message.offset = i
            await kafka_consumer_service._process_message(sample_kafka_message)

        # Verify all messages were processed
        assert kafka_consumer_service.messages_processed == 5
        assert kafka_consumer_service.messages_failed == 0
        assert mock_db_manager.save_purchase.call_count == 5


# ============================================================================
# METRICS TESTS
# ============================================================================

class TestMetrics:
    """Test metrics tracking."""

    def test_get_stats_initial(self, kafka_consumer_service):
        """Test getting stats before processing any messages."""
        stats = kafka_consumer_service.get_stats()

        assert stats["running"] is False
        assert stats["messages_processed"] == 0
        assert stats["messages_failed"] == 0
        assert stats["last_message_time"] is None
        assert stats["topic"] == "test-purchases"
        assert stats["group_id"] == "test-group"

    @pytest.mark.asyncio
    async def test_get_stats_after_processing(self, kafka_consumer_service, mock_db_manager, sample_kafka_message):
        """Test getting stats after processing messages."""
        # Process a message
        await kafka_consumer_service._process_message(sample_kafka_message)

        stats = kafka_consumer_service.get_stats()

        assert stats["messages_processed"] == 1
        assert stats["messages_failed"] == 0
        assert stats["last_message_time"] is not None

    def test_get_lag(self, kafka_consumer_service):
        """Test getting consumer lag."""
        # Currently returns 0 as placeholder
        lag = kafka_consumer_service.get_lag()
        assert lag == 0


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_malformed_json(self, kafka_consumer_service, mock_db_manager):
        """Test handling malformed JSON data."""
        # Create message with non-dict value
        malformed_message = MagicMock()
        malformed_message.partition = 0
        malformed_message.offset = 50
        malformed_message.key = b"user_bad"
        malformed_message.value = "not a dict"  # Invalid format

        # Process message - should handle gracefully
        await kafka_consumer_service._process_message(malformed_message)

        # Verify failure was recorded
        assert kafka_consumer_service.messages_failed == 1

    @pytest.mark.asyncio
    async def test_connection_failure(self, kafka_consumer_service):
        """Test handling connection failures during start."""
        with patch('kafka_consumer.AIOKafkaConsumer') as mock_consumer_class:
            # Simulate connection error
            mock_consumer_class.side_effect = Exception("Connection refused")

            # Start should raise exception
            with pytest.raises(Exception):
                await kafka_consumer_service.start()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for consumer."""

    @pytest.mark.asyncio
    async def test_full_message_flow(self, mock_db_manager):
        """Test complete message consumption flow."""
        consumer = KafkaConsumerService(
            bootstrap_servers="localhost:9092",
            topic="integration-test",
            group_id="integration-group",
            db_manager=mock_db_manager
        )

        with patch('kafka_consumer.AIOKafkaConsumer') as mock_consumer_class:
            # Setup mock consumer
            mock_consumer = AsyncMock()
            mock_consumer_class.return_value = mock_consumer

            # Mock message stream
            async def mock_message_stream():
                message = MagicMock()
                message.partition = 0
                message.offset = 100
                message.key = b"user_integration"
                message.value = {
                    "username": "integration_user",
                    "user_id": "user_integration",
                    "item_name": "Integration Product",
                    "price": 199.99,
                    "timestamp": "2025-12-15T12:00:00Z"
                }
                yield message

                # Stop after one message
                consumer.running = False

            mock_consumer.__aiter__.return_value = mock_message_stream()

            # Start consumer
            await consumer.start()

            # Let it process messages
            await asyncio.sleep(0.1)

            # Stop consumer
            await consumer.stop()

            # Verify message was processed
            assert mock_db_manager.save_purchase.called


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run tests with: python test_kafka_consumer.py
    pytest.main([__file__, "-v", "--cov=kafka_consumer", "--cov-report=term-missing"])