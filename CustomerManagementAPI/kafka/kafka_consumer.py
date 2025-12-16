"""
Kafka Consumer Service

This module handles:
1. Consuming messages from Kafka topic
2. Deserializing purchase data
3. Saving to MongoDB via DatabaseManager
4. Error handling and retry logic
"""

import asyncio
import json
import logging
from typing import Optional
from datetime import datetime

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from CustomerManagementAPI.data_model.purchase import Purchase
from CustomerManagementAPI.database.database_manager import DatabaseManager
# Configure logging

logger = logging.getLogger(__name__)


class KafkaConsumer:
    """
    Asynchronous Kafka consumer that processes purchase messages.

    This service:
    - Connects to Kafka broker
    - Subscribes to purchases topic
    - Deserializes JSON messages
    - Saves purchases to MongoDB
    - Handles errors and retries
    """

    def __init__(
            self,
            bootstrap_servers: str,
            topic: str,
            group_id: str,
            db_manager: DatabaseManager
    ):
        """
        Initialize Kafka consumer.

        Args:
            bootstrap_servers: Kafka broker address (e.g., "localhost:9092")
            topic: Kafka topic to consume from
            group_id: Consumer group ID for load balancing
            db_manager: Database manager instance for saving purchases
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.db_manager = db_manager

        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False
        self.consumer_task: Optional[asyncio.Task] = None

        # Metrics for monitoring
        self.messages_processed = 0
        self.messages_failed = 0
        self.last_message_time: Optional[datetime] = None

        logger.info(
            f"Kafka Consumer initialized: "
            f"servers={bootstrap_servers}, topic={topic}, group={group_id}"
        )

    async def start(self):
        """
        Start the Kafka consumer.

        This method:
        1. Creates the consumer instance
        2. Connects to Kafka
        3. Subscribes to the topic
        4. Starts the consumption loop in a background task
        """
        try:
            logger.info("Starting Kafka consumer...")

            # Create consumer instance
            # auto_offset_reset='earliest' ensures we process all messages from the beginning
            # enable_auto_commit=True automatically commits offsets
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset='earliest',  # Start from earliest message if no offset
                enable_auto_commit=True,  # Auto-commit offsets
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),  # Deserialize JSON
                session_timeout_ms=30000,  # 30 seconds
                heartbeat_interval_ms=10000,  # 10 seconds
            )

            # Connect to Kafka
            await self.consumer.start()
            logger.info(f"Kafka consumer connected and subscribed to topic: {self.topic}")

            # Start consuming messages in background
            self.running = True
            self.consumer_task = asyncio.create_task(self._consume_loop())
            logger.info("Kafka consumer loop started")

        except KafkaError as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting Kafka consumer: {e}")
            raise

    async def stop(self):
        """
        Stop the Kafka consumer gracefully.

        This method:
        1. Signals the consumption loop to stop
        2. Waits for the loop to finish
        3. Closes the consumer connection
        """
        logger.info("Stopping Kafka consumer...")
        self.running = False

        # Wait for consumer task to finish
        if self.consumer_task:
            try:
                await asyncio.wait_for(self.consumer_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Consumer task did not stop within timeout")
                self.consumer_task.cancel()

        # Close consumer connection
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    def is_running(self) -> bool:
        """
        Check if consumer is currently running.

        Returns:
            bool: True if consumer is active, False otherwise
        """
        return self.running and self.consumer is not None

    def get_lag(self) -> int:
        """
        Get consumer lag (messages behind).

        This is useful for autoscaling decisions.
        If lag is high, we need more consumer instances.

        Returns:
            int: Number of messages behind (0 if not available)
        """
        # In a production system, you would query Kafka for actual lag
        # For now, we'll return 0 as a placeholder
        # You can implement this using self.consumer.highwater() and self.consumer.position()
        return 0

    async def _consume_loop(self):
        """
        Main consumption loop that processes messages continuously.

        This loop:
        1. Fetches messages from Kafka
        2. Processes each message
        3. Handles errors
        4. Continues until stopped
        """
        logger.info("Kafka consumption loop started")

        try:
            async for message in self.consumer:
                if not self.running:
                    logger.info("Consumer loop stopping...")
                    break

                # Process the message
                await self._process_message(message)

        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled")
        except Exception as e:
            logger.error(f"Error in consumer loop: {e}")
        finally:
            logger.info("Consumer loop ended")

    async def _process_message(self, message):
        """
        Process a single Kafka message.

        This method:
        1. Extracts message value (already deserialized by consumer)
        2. Validates the purchase data
        3. Saves to MongoDB
        4. Updates metrics

        Args:
            message: Kafka message object
        """
        try:
            # Log message details
            logger.info(
                f"Received message: "
                f"partition={message.partition}, "
                f"offset={message.offset}, "
                f"key={message.key}"
            )

            # Extract message value (already deserialized to dict)
            purchase_data = message.value
            logger.debug(f"Purchase data: {purchase_data}")

            # Validate and create Purchase object
            # This ensures data conforms to our schema
            purchase = Purchase(**purchase_data)

            # Save to MongoDB
            purchase_id = await self.db_manager.save_purchase(purchase)

            # Update metrics
            self.messages_processed += 1
            self.last_message_time = datetime.utcnow()

            logger.info(
                f"Successfully processed purchase: "
                f"purchase_id={purchase_id}, "
                f"user_id={purchase.user_id}, "
                f"item={purchase.item_name}"
            )

        except ValueError as e:
            # Invalid data format
            logger.error(f"Invalid purchase data format: {e}")
            logger.error(f"Message content: {message.value}")
            self.messages_failed += 1

        except Exception as e:
            # Database or other errors
            logger.error(f"Failed to process message: {e}")
            logger.error(f"Message content: {message.value}")
            self.messages_failed += 1

            # In production, you might want to:
            # - Send to dead letter queue (DLQ)
            # - Implement retry logic
            # - Alert monitoring systems

    def get_stats(self) -> dict:
        """
        Get consumer statistics for monitoring.

        Returns:
            dict: Consumer metrics including messages processed, failed, etc.
        """
        return {
            "running": self.running,
            "messages_processed": self.messages_processed,
            "messages_failed": self.messages_failed,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "topic": self.topic,
            "group_id": self.group_id
        }
