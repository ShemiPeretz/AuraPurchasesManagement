from typing import Optional, List

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from datetime import datetime

from CustomerManagementAPI.data_model.purchase import Purchase
from CustomerManagementAPI.logger.logger import Logger


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

class DatabaseManager:
    """
    Manages MongoDB connection and operations.

    This class handles all database interactions including:
    - Connection management
    - Purchase storage
    - Query operations
    - Index creation
    """

    def __init__(self, uri: str, db_name: str, collection_name: str):
        """
        Initialize database manager.

        Args:
            uri: MongoDB connection URI
            db_name: Database name
            collection_name: Collection name for purchases
        """
        self.uri = uri
        self.db_name = db_name
        self.collection_name = collection_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.collection = None
        self.logger = Logger()

    async def connect(self):
        """
        Establish connection to MongoDB and create indexes.

        Indexes:
        - user_id: For fast lookup of user purchases
        - timestamp: For sorting by purchase date
        """
        try:
            self.logger.info(f"Connecting to MongoDB at {self.uri}")
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]

            # Verify connection
            await self.client.admin.command('ping')
            self.logger.info("Successfully connected to MongoDB")

            # Create indexes for optimized queries
            await self.collection.create_index([("user_id", ASCENDING)])
            await self.collection.create_index([("timestamp", ASCENDING)])
            self.logger.info("Database indexes created successfully")

        except Exception as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def disconnect(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.logger.info("Disconnected from MongoDB")

    async def is_connected(self) -> bool:
        """
        Check if MongoDB connection is active.

        Returns:
            bool: True if connected, False otherwise
        """
        try:
            if self.client:
                await self.client.admin.command('ping')
                return True
        except Exception as e:
            self.logger.error(f"MongoDB connection check failed: {e}")
        return False

    async def save_purchase(self, purchase: Purchase) -> str:
        """
        Save a purchase to MongoDB.

        Args:
            purchase: Purchase object to save

        Returns:
            str: MongoDB document ID

        Raises:
            Exception: If save operation fails
        """
        try:
            # Convert purchase to dict and prepare for MongoDB
            purchase_dict = purchase.model_dump()

            # Convert timestamp string to datetime for better querying
            purchase_dict["timestamp_dt"] = datetime.fromisoformat(
                purchase_dict["timestamp"].replace('Z', '+00:00')
            )

            result = await self.collection.insert_one(purchase_dict)
            self.logger.info(f"Purchase saved: user_id={purchase.user_id}, item={purchase.item_name}")
            return str(result.inserted_id)

        except DuplicateKeyError:
            self.logger.warning(f"Duplicate purchase detected: {purchase.user_id}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to save purchase: {e}")
            raise

    async def get_user_purchases(self, user_id: str) -> List[dict]:
        """
        Retrieve all purchases for a specific user.

        Args:
            user_id: User identifier

        Returns:
            List of purchase documents sorted by timestamp (newest first)
        """
        try:
            cursor = self.collection.find(
                {"user_id": user_id}
            ).sort("timestamp_dt", -1)  # Sort by newest first

            purchases = await cursor.to_list(length=None)

            # Convert ObjectId to string for JSON serialization
            for purchase in purchases:
                purchase["_id"] = str(purchase["_id"])

            self.logger.info(f"Retrieved {len(purchases)} purchases for user_id={user_id}")
            return purchases

        except Exception as e:
            self.logger.error(f"Failed to retrieve purchases for user_id={user_id}: {e}")
            raise

