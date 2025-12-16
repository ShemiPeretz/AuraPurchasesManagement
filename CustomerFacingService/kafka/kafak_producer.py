"""
Kafka Producer Service

This module handles:
1. Publishing messages to Kafka topic
2. Message serialization
3. Error handling and retries
4. Metrics tracking
"""

import asyncio
import json
import logging
from typing import Optional, Any, Dict
from datetime import datetime

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError, KafkaTimeoutError

# Configure logging
logger = logging.getLogger(__name__)


class KafkaProducer:
    """
    Asynchronous Kafka producer that publishes purchase events.

    This service:
    - Connects to Kafka broker
    - Publishes messages to purchases topic
    - Serializes messages to JSON
    - Handles errors and retries
    - Tracks metrics for monitoring
    """

    def __init__(self, bootstrap_servers: str, topic: str):
        """
        Initialize Kafka producer.

        Args:
            bootstrap_servers: Kafka broker address
            topic: Kafka topic to publish to
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic

        self.producer: Optional[AIOKafkaProducer] = None
        self.connected = False

        # Metrics for monitoring
        self.messages_sent = 0
        self.messages_failed = 0
        self.last_message_time: Optional[datetime] = None

        logger.info(
            f"Kafka Producer initialized: "
            f"servers={bootstrap_servers}, topic={topic}"
        )

    async def start(self):
        """
        Start the Kafka producer.

        This method:
        1. Creates the producer instance
        2. Connects to Kafka
        3. Handles connection errors with retry

        Raises:
            KafkaError: If connection fails after retries
        """
        try:
            logger.info("Starting Kafka producer...")

            # Create producer instance
            # value_serializer: Converts Python dict to JSON bytes
            # key_serializer: Converts string keys to bytes
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                # Wait for acknowledgment from all replicas (most reliable)
                acks='all',
                # Timeout for sending messages
                request_timeout_ms=30000,
                # Compression for better network efficiency
                compression_type='gzip',
            )

            # Connect to Kafka
            await self.producer.start()
            self.connected = True

            logger.info(f"Kafka producer connected and ready to publish to topic: {self.topic}")

        except KafkaError as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            self.connected = False
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting Kafka producer: {e}")
            self.connected = False
            raise

    async def stop(self):
        """
        Stop the Kafka producer gracefully.

        This method:
        1. Flushes pending messages
        2. Closes the connection
        """
        logger.info("Stopping Kafka producer...")

        if self.producer:
            try:
                # Flush any pending messages
                await self.producer.flush()
                # Close the producer
                await self.producer.stop()
                logger.info("Kafka producer stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")

        self.connected = False

    def is_connected(self) -> bool:
        """
        Check if producer is connected to Kafka.

        Returns:
            bool: True if connected, False otherwise
        """
        return self.connected and self.producer is not None

    async def send_message(
            self,
            key: str,
            value: Dict[str, Any],
            partition: Optional[int] = None
    ):
        """
        Send a message to Kafka.

        This method:
        1. Validates the producer is connected
        2. Sends the message to Kafka
        3. Waits for acknowledgment
        4. Updates metrics
        5. Handles errors

        Args:
            key: Message key (used for partitioning, typically user_id)
            value: Message value (purchase data as dict)
            partition: Optional specific partition (None for automatic)

        Returns:
            RecordMetadata: Kafka record metadata (partition, offset, etc.)

        Raises:
            KafkaError: If message sending fails
            ValueError: If producer is not connected
        """
        if not self.is_connected():
            raise ValueError("Kafka producer is not connected")

        try:
            logger.debug(f"Sending message to topic {self.topic}: key={key}")

            # Send message to Kafka
            # The send() method is async and returns a future
            # We await the future to get the RecordMetadata
            future = await self.producer.send(
                topic=self.topic,
                key=key,
                value=value,
                partition=partition
            )

            # Wait for the message to be acknowledged
            record_metadata = await future

            # Update metrics
            self.messages_sent += 1
            self.last_message_time = datetime.utcnow()

            logger.info(
                f"Message sent successfully: "
                f"topic={record_metadata.topic}, "
                f"partition={record_metadata.partition}, "
                f"offset={record_metadata.offset}"
            )

            return record_metadata

        except KafkaTimeoutError as e:
            logger.error(f"Timeout sending message to Kafka: {e}")
            self.messages_failed += 1
            raise KafkaError(f"Timeout sending message: {e}")

        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}")
            self.messages_failed += 1
            raise

        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            self.messages_failed += 1
            raise KafkaError(f"Failed to send message: {e}")

    async def send_batch(self, messages: list) -> list:
        """
        Send multiple messages in a batch.

        This is more efficient than sending messages one by one.

        Args:
            messages: List of tuples (key, value)

        Returns:
            List of RecordMetadata for each message

        Example:
            messages = [
                ("user_123", {"username": "john", "item": "laptop", ...}),
                ("user_456", {"username": "jane", "item": "phone", ...}),
            ]
            results = await producer.send_batch(messages)
        """
        if not self.is_connected():
            raise ValueError("Kafka producer is not connected")

        logger.info(f"Sending batch of {len(messages)} messages")

        futures = []
        for key, value in messages:
            future = await self.producer.send(
                topic=self.topic,
                key=key,
                value=value
            )
            futures.append(future)

        # Wait for all messages to be acknowledged
        results = []
        for future in futures:
            try:
                record_metadata = await future
                results.append(record_metadata)
                self.messages_sent += 1
            except Exception as e:
                logger.error(f"Failed to send message in batch: {e}")
                self.messages_failed += 1
                results.append(None)

        self.last_message_time = datetime.utcnow()

        logger.info(
            f"Batch send complete: "
            f"success={len([r for r in results if r])}, "
            f"failed={len([r for r in results if not r])}"
        )

        return results

    async def flush(self):
        """
        Flush any pending messages.

        This ensures all messages are sent before continuing.
        Useful before shutting down or when you need to ensure
        all messages are delivered.
        """
        if self.producer:
            logger.info("Flushing pending messages...")
            await self.producer.flush()
            logger.info("All pending messages flushed")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get producer statistics for monitoring.

        Returns:
            dict: Producer metrics including messages sent, failed, etc.
        """
        return {
            "connected": self.connected,
            "messages_sent": self.messages_sent,
            "messages_failed": self.messages_failed,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "topic": self.topic,
            "bootstrap_servers": self.bootstrap_servers
        }
