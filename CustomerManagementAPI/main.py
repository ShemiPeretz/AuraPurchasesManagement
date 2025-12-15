"""
Customer Management API Service

This service is responsible for:
1. Consuming purchase messages from Kafka
2. Storing purchases in MongoDB
3. Providing REST API to retrieve user purchases
"""

import os
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from CustomerManagementAPI.kafka.kafka_consumer import KafkaConsumer
from CustomerManagementAPI.database.database_manager import DatabaseManager
from CustomerManagementAPI.data_model.health import HealthResponse
from CustomerManagementAPI.data_model.purchase import Purchase, PurchaseResponse, UserPurchasesResponse
from CustomerManagementAPI.logger.logger import Logger

# ============================================================================
# CONFIGURATION
# ============================================================================


# Environment variables with defaults for local development
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "ecommerce")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "purchases")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "purchases")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "customer-management-group")



# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================

# Global instances
db_manager: DatabaseManager = None
kafka_consumer: KafkaConsumer = None
logger: Logger = Logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle: startup and shutdown.

    On startup:
    - Connect to MongoDB
    - Start Kafka consumer

    On shutdown:
    - Stop Kafka consumer
    - Disconnect from MongoDB
    """
    global db_manager, kafka_consumer

    # STARTUP
    logger.info("Starting Customer Management API...")

    # Initialize and connect to MongoDB
    db_manager = DatabaseManager(MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION)
    await db_manager.connect()

    # Initialize and start Kafka consumer
    kafka_consumer = KafkaConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        topic=KAFKA_TOPIC,
        group_id=KAFKA_GROUP_ID,
        db_manager=db_manager
    )
    await kafka_consumer.start()

    logger.info("Customer Management API started successfully")

    yield

    # SHUTDOWN
    logger.info("Shutting down Customer Management API...")

    # Stop Kafka consumer
    if kafka_consumer:
        await kafka_consumer.stop()

    # Disconnect from MongoDB
    if db_manager:
        await db_manager.disconnect()

    logger.info("Customer Management API shutdown complete")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Customer Management API",
    description="Manages customer purchases via Kafka consumption and MongoDB storage",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_model=dict)
async def root():
    """
    Root endpoint providing API information.
    """
    return {
        "service": "Customer Management API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "purchases": "/purchases/{user_id}"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for Kubernetes liveness and readiness probes.

    Checks:
    - MongoDB connection status
    - Kafka consumer status

    Returns:
        200 OK if all systems are healthy
        503 Service Unavailable if any system is down
    """
    mongodb_connected = await db_manager.is_connected() if db_manager else False
    kafka_connected = kafka_consumer.is_running() if kafka_consumer else False

    is_healthy = mongodb_connected and kafka_connected

    response = HealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        service="CustomerManagementAPI",
        mongodb_connected=mongodb_connected,
        kafka_connected=kafka_connected,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )

    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump()
    )


@app.get("/purchases/{user_id}", response_model=UserPurchasesResponse)
async def get_user_purchases(user_id: str):
    """
    Retrieve all purchases for a specific user.

    This endpoint is called by the Customer Facing Web Server to display
    user purchase history.

    Args:
        user_id: Unique identifier for the user

    Returns:
        UserPurchasesResponse: Purchase history with statistics

    Raises:
        404: If user has no purchases
        500: If database query fails
    """
    try:
        # Retrieve purchases from MongoDB
        purchases = await db_manager.get_user_purchases(user_id)

        if not purchases:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No purchases found for user_id: {user_id}"
            )

        # Calculate statistics
        total_purchases = len(purchases)
        total_spent = sum(p["price"] for p in purchases)
        username = purchases[0].get("username", "Unknown") if purchases else "Unknown"

        # Convert to response model
        purchase_responses = [
            PurchaseResponse(**purchase) for purchase in purchases
        ]

        return UserPurchasesResponse(
            user_id=user_id,
            username=username,
            total_purchases=total_purchases,
            total_spent=round(total_spent, 2),
            purchases=purchase_responses
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving purchases for user_id={user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving purchases"
        )


@app.get("/metrics")
async def metrics():
    """
    Prometheus-compatible metrics endpoint for monitoring and autoscaling.

    Metrics exposed:
    - Total purchases processed
    - Kafka consumer lag (if available)
    - MongoDB connection status

    This can be used by Prometheus for custom HPA metrics.
    """
    # In a production system, you would use prometheus_client library
    # For now, we'll return basic metrics in a simple format

    kafka_lag = kafka_consumer.get_lag() if kafka_consumer else 0
    mongodb_status = 1 if await db_manager.is_connected() else 0

    return {
        "kafka_consumer_lag": kafka_lag,
        "mongodb_connected": mongodb_status,
        "service": "CustomerManagementAPI"
    }


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Run the application
    # In production, this is handled by the Docker container CMD
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,  # Only for development
        log_level="info"
    )