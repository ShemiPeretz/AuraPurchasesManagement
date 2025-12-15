"""
Unit Tests for Kafka Producer Service

Tests cover:
1. Producer initialization
2. Message sending
3. Batch operations
4. Error handling
5. Metrics tracking

Run with: pytest -v test_kafka_producer.py
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Import components to test
import sys

sys.path.insert(0, '..')
from kafka_producer import KafkaProducerService


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def kafka_producer_service():
    """Create KafkaProducerService instance for testing."""
    return KafkaProducerService(
        bootstrap_servers="localhost:9092",
        topic="test-purchases"
    )


@pytest.fixture
def sample_message():
    """Sample message for testing."""
    return {
        "username": "test_user",
        "user_id": "user_123",
        "item_name": "Test Product",
        "price": 99.99,
        "timestamp": "2025-12-15T10:30:00Z"
    }


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestKafkaProducerInitialization:
    """Test producer initialization."""

    def test_producer_creation(self, kafka_producer_service):
        """Test creating a producer instance."""
        assert kafka_producer_service.bootstrap_servers == "localhost:9092"
        assert kafka_producer_service.topic == "test-purchases"
        assert kafka_producer_service.connected is False
        assert kafka_producer_service.producer is None

    def test_initial_metrics(self, kafka_producer_service):
        """Test initial metric values."""
        assert kafka_producer_service.messages_sent == 0
        assert kafka_producer_service.messages_failed == 0
        assert kafka_producer_service.last_message_time is None


# ============================================================================
# PRODUCER LIFECYCLE TESTS
# ============================================================================

class TestKafkaProducerLifecycle:
    """Test producer start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_producer(self, kafka_producer_service):
        """Test starting the producer."""
        with patch('kafka_producer.AIOKafkaProducer') as mock_producer_class:
            # Mock producer instance
            mock_producer = AsyncMock()
            mock_producer_class.return_value = mock_producer

            # Start producer
            await kafka_producer_service.start()

            # Verify producer was created and started
            assert kafka_producer_service.connected is True
            assert kafka_producer_service.producer is not None
            mock_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_producer(self, kafka_producer_service):
        """Test stopping the producer."""
        # Mock a running producer
        mock_producer = AsyncMock()
        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Stop producer
        await kafka_producer_service.stop()

        # Verify producer was stopped
        assert kafka_producer_service.connected is False
        mock_producer.flush.assert_called_once()
        mock_producer.stop.assert_called_once()

    def test_is_connected_true(self, kafka_producer_service):
        """Test is_connected when producer is active."""
        kafka_producer_service.connected = True
        kafka_producer_service.producer = MagicMock()

        assert kafka_producer_service.is_connected() is True

    def test_is_connected_false(self, kafka_producer_service):
        """Test is_connected when producer is not active."""
        kafka_producer_service.connected = False
        kafka_producer_service.producer = None

        assert kafka_producer_service.is_connected() is False


# ============================================================================
# MESSAGE SENDING TESTS
# ============================================================================

class TestMessageSending:
    """Test message sending operations."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, kafka_producer_service, sample_message):
        """Test sending a message successfully."""
        # Mock producer
        mock_producer = AsyncMock()

        # Mock record metadata
        mock_future = asyncio.Future()
        mock_metadata = MagicMock()
        mock_metadata.topic = "test-purchases"
        mock_metadata.partition = 0
        mock_metadata.offset = 42
        mock_future.set_result(mock_metadata)

        mock_producer.send.return_value = mock_future

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Send message
        result = await kafka_producer_service.send_message(
            key="user_123",
            value=sample_message
        )

        # Verify
        assert result.partition == 0
        assert result.offset == 42
        assert kafka_producer_service.messages_sent == 1
        assert kafka_producer_service.messages_failed == 0
        assert kafka_producer_service.last_message_time is not None

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self, kafka_producer_service, sample_message):
        """Test sending message when not connected."""
        kafka_producer_service.connected = False

        with pytest.raises(ValueError, match="not connected"):
            await kafka_producer_service.send_message(
                key="user_123",
                value=sample_message
            )

    @pytest.mark.asyncio
    async def test_send_message_kafka_error(self, kafka_producer_service, sample_message):
        """Test handling Kafka errors during send."""
        from aiokafka.errors import KafkaError

        # Mock producer that raises error
        mock_producer = AsyncMock()
        mock_future = asyncio.Future()
        mock_future.set_exception(KafkaError("Connection failed"))
        mock_producer.send.return_value = mock_future

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Send should raise error
        with pytest.raises(KafkaError):
            await kafka_producer_service.send_message(
                key="user_123",
                value=sample_message
            )

        # Verify failure was recorded
        assert kafka_producer_service.messages_failed == 1
        assert kafka_producer_service.messages_sent == 0

    @pytest.mark.asyncio
    async def test_send_message_with_partition(self, kafka_producer_service, sample_message):
        """Test sending message to specific partition."""
        mock_producer = AsyncMock()

        mock_future = asyncio.Future()
        mock_metadata = MagicMock()
        mock_metadata.partition = 3  # Specific partition
        mock_metadata.offset = 100
        mock_future.set_result(mock_metadata)

        mock_producer.send.return_value = mock_future

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Send to specific partition
        result = await kafka_producer_service.send_message(
            key="user_123",
            value=sample_message,
            partition=3
        )

        assert result.partition == 3
        mock_producer.send.assert_called_once()
        call_kwargs = mock_producer.send.call_args[1]
        assert call_kwargs["partition"] == 3


# ============================================================================
# BATCH OPERATIONS TESTS
# ============================================================================

class TestBatchOperations:
    """Test batch message operations."""

    @pytest.mark.asyncio
    async def test_send_batch_success(self, kafka_producer_service):
        """Test sending multiple messages in batch."""
        # Mock producer
        mock_producer = AsyncMock()

        # Create mock futures for batch
        messages = [
            ("user_1", {"item": "item1", "price": 10}),
            ("user_2", {"item": "item2", "price": 20}),
            ("user_3", {"item": "item3", "price": 30}),
        ]

        futures = []
        for i in range(len(messages)):
            future = asyncio.Future()
            metadata = MagicMock()
            metadata.partition = 0
            metadata.offset = i
            future.set_result(metadata)
            futures.append(future)

        # Mock send to return futures
        mock_producer.send.side_effect = futures

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Send batch
        results = await kafka_producer_service.send_batch(messages)

        # Verify
        assert len(results) == 3
        assert all(r is not None for r in results)
        assert kafka_producer_service.messages_sent == 3
        assert kafka_producer_service.messages_failed == 0

    @pytest.mark.asyncio
    async def test_send_batch_partial_failure(self, kafka_producer_service):
        """Test batch send with some failures."""
        from aiokafka.errors import KafkaError

        mock_producer = AsyncMock()

        # Create futures: success, failure, success
        future1 = asyncio.Future()
        future1.set_result(MagicMock(partition=0, offset=1))

        future2 = asyncio.Future()
        future2.set_exception(KafkaError("Send failed"))

        future3 = asyncio.Future()
        future3.set_result(MagicMock(partition=0, offset=3))

        mock_producer.send.side_effect = [future1, future2, future3]

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        messages = [
            ("user_1", {"item": "item1"}),
            ("user_2", {"item": "item2"}),
            ("user_3", {"item": "item3"}),
        ]

        # Send batch
        results = await kafka_producer_service.send_batch(messages)

        # Verify
        assert len(results) == 3
        assert results[0] is not None  # Success
        assert results[1] is None  # Failed
        assert results[2] is not None  # Success
        assert kafka_producer_service.messages_sent == 2
        assert kafka_producer_service.messages_failed == 1


# ============================================================================
# FLUSH TESTS
# ============================================================================

class TestFlush:
    """Test flush operations."""

    @pytest.mark.asyncio
    async def test_flush(self, kafka_producer_service):
        """Test flushing pending messages."""
        mock_producer = AsyncMock()
        kafka_producer_service.producer = mock_producer

        await kafka_producer_service.flush()

        mock_producer.flush.assert_called_once()


# ============================================================================
# METRICS TESTS
# ============================================================================

class TestMetrics:
    """Test metrics tracking."""

    def test_get_stats_initial(self, kafka_producer_service):
        """Test getting stats before sending any messages."""
        stats = kafka_producer_service.get_stats()

        assert stats["connected"] is False
        assert stats["messages_sent"] == 0
        assert stats["messages_failed"] == 0
        assert stats["last_message_time"] is None
        assert stats["topic"] == "test-purchases"
        assert stats["bootstrap_servers"] == "localhost:9092"

    @pytest.mark.asyncio
    async def test_get_stats_after_sending(self, kafka_producer_service, sample_message):
        """Test getting stats after sending messages."""
        # Mock producer
        mock_producer = AsyncMock()
        mock_future = asyncio.Future()
        mock_metadata = MagicMock()
        mock_metadata.partition = 0
        mock_metadata.offset = 42
        mock_future.set_result(mock_metadata)
        mock_producer.send.return_value = mock_future

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Send a message
        await kafka_producer_service.send_message("user_123", sample_message)

        # Get stats
        stats = kafka_producer_service.get_stats()

        assert stats["connected"] is True
        assert stats["messages_sent"] == 1
        assert stats["messages_failed"] == 0
        assert stats["last_message_time"] is not None


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_connection_failure(self, kafka_producer_service):
        """Test handling connection failures during start."""
        from aiokafka.errors import KafkaError

        with patch('kafka_producer.AIOKafkaProducer') as mock_producer_class:
            # Simulate connection error
            mock_producer = AsyncMock()
            mock_producer.start.side_effect = KafkaError("Connection refused")
            mock_producer_class.return_value = mock_producer

            # Start should raise exception
            with pytest.raises(KafkaError):
                await kafka_producer_service.start()

            assert kafka_producer_service.connected is False

    @pytest.mark.asyncio
    async def test_timeout_error(self, kafka_producer_service, sample_message):
        """Test handling timeout errors."""
        from aiokafka.errors import KafkaTimeoutError

        mock_producer = AsyncMock()
        mock_future = asyncio.Future()
        mock_future.set_exception(KafkaTimeoutError("Request timeout"))
        mock_producer.send.return_value = mock_future

        kafka_producer_service.producer = mock_producer
        kafka_producer_service.connected = True

        # Send should raise timeout error
        with pytest.raises(Exception):
            await kafka_producer_service.send_message("user_123", sample_message)

        assert kafka_producer_service.messages_failed == 1


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for producer."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete producer lifecycle."""
        producer = KafkaProducerService(
            bootstrap_servers="localhost:9092",
            topic="integration-test"
        )

        with patch('kafka_producer.AIOKafkaProducer') as mock_producer_class:
            # Setup mock
            mock_producer = AsyncMock()
            mock_future = asyncio.Future()
            mock_metadata = MagicMock()
            mock_metadata.partition = 0
            mock_metadata.offset = 1
            mock_future.set_result(mock_metadata)
            mock_producer.send.return_value = mock_future
            mock_producer_class.return_value = mock_producer

            # Start
            await producer.start()
            assert producer.is_connected()

            # Send message
            message = {
                "username": "integration_user",
                "user_id": "user_int",
                "item_name": "Integration Item",
                "price": 99.99,
                "timestamp": "2025-12-15T10:00:00Z"
            }

            result = await producer.send_message("user_int", message)
            assert result.offset == 1

            # Check stats
            stats = producer.get_stats()
            assert stats["messages_sent"] == 1

            # Stop
            await producer.stop()
            assert not producer.is_connected()


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run tests with: python test_kafka_producer.py
    pytest.main([__file__, "-v", "--cov=kafka_producer", "--cov-report=term-missing"])