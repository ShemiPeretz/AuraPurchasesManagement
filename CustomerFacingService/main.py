import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from CustomerFacingService.data_model.buy import *
from CustomerFacingService.data_model.health import HealthResponse
from CustomerFacingService.data_model.purchase import *
from CustomerFacingService.kafka.kafak_producer import KafkaProducer

# CONFIGURATION

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "purchases")
CUSTOMER_MANAGEMENT_API_URL = os.getenv(
    "CUSTOMER_MANAGEMENT_API_URL",
    "http://localhost:8001"
)

# List of random items for purchase simulation
RANDOM_ITEMS = [
    {"name": "Laptop", "price": 999.99},
    {"name": "Smartphone", "price": 699.99},
    {"name": "Headphones", "price": 199.99},
    {"name": "Keyboard", "price": 89.99},
    {"name": "Mouse", "price": 49.99},
    {"name": "Monitor", "price": 349.99},
    {"name": "Tablet", "price": 499.99},
    {"name": "Smartwatch", "price": 299.99},
    {"name": "Camera", "price": 799.99},
    {"name": "Speaker", "price": 149.99},
    {"name": "USB Cable", "price": 19.99},
    {"name": "External SSD", "price": 129.99},
    {"name": "Webcam", "price": 79.99},
    {"name": "Gaming Console", "price": 499.99},
    {"name": "Router", "price": 159.99},
]

kafka_producer: Optional[KafkaProducer] = None
http_client: Optional[httpx.AsyncClient] = None

# APPLICATION LIFECYCLE

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle: startup and shutdown.

    On startup:
    - Initialize Kafka producer
    - Create HTTP client for API calls

    On shutdown:
    - Close Kafka producer
    - Close HTTP client
    """
    global kafka_producer, http_client

    # STARTUP
    logger.info("Starting Customer Facing Web Server...")

    # Initialize Kafka producer
    kafka_producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        topic=KAFKA_TOPIC
    )
    await kafka_producer.start()

    # Initialize HTTP client for Customer Management API calls
    http_client = httpx.AsyncClient(
        base_url=CUSTOMER_MANAGEMENT_API_URL,
        timeout=30.0,
        follow_redirects=True
    )

    logger.info("Customer Facing Web Server started successfully")

    yield

    # SHUTDOWN
    logger.info("Shutting down Customer Facing Web Server...")

    # Stop Kafka producer
    if kafka_producer:
        await kafka_producer.stop()

    # Close HTTP client
    if http_client:
        await http_client.aclose()

    logger.info("Customer Facing Web Server shutdown complete")


# FASTAPI APPLICATION

app = FastAPI(
    title="Customer Facing Web Server",
    description="Handles customer purchase requests and retrieves purchase history",
    version="1.0.0",
    lifespan=lifespan
)

# CORS MIDDLEWARE

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HELPER FUNCTIONS

def select_random_item() -> dict:
    """
    Select a random item from the catalog.

    Returns:
        dict: Item with 'name' and 'price' keys
    """
    import random
    return random.choice(RANDOM_ITEMS)


def generate_purchase_event(buy_request: BuyRequest) -> PurchaseEvent:
    """
    Generate a purchase event from a buy request.

    This function:
    1. Selects a random item
    2. Generates a timestamp
    3. Creates a complete purchase event

    Args:
        buy_request: Buy request from user

    Returns:
        PurchaseEvent: Complete purchase event ready for Kafka
    """
    # TODO: switch to a list of items maybe??
    item = select_random_item()

    return PurchaseEvent(
        username=buy_request.username,
        user_id=buy_request.user_id,
        item_name=item["name"],
        price=item["price"],
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


# API ENDPOINTS

@app.get("/", response_model=dict)
async def root():
    """
    Root endpoint providing API information.
    """
    return {
        "service": "Customer Facing Web Server",
        "version": "1.0.0",
        "description": "API for customer purchase interactions",
        "endpoints": {
            "buy": "POST /buy",
            "purchases": "GET /purchases/{user_id}",
            "health": "GET /health"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for Kubernetes liveness and readiness probes.

    Checks:
    - Kafka producer status
    - Customer Management API reachability

    Returns:
        200 OK if all systems are healthy
        503 Service Unavailable if any system is down
    """
    kafka_connected = kafka_producer.is_connected() if kafka_producer else False

    # Check Customer Management API reachability
    cm_api_reachable = False
    try:
        response = await http_client.get("/health", timeout=5.0)
        cm_api_reachable = response.status_code == 200
    except Exception as e:
        logger.warning(f"Customer Management API health check failed: {e}")

    is_healthy = kafka_connected and cm_api_reachable

    response = HealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        service="customer-facing-web-server",
        kafka_connected=kafka_connected,
        customer_management_api_reachable=cm_api_reachable,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )

    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump()
    )


@app.post("/buy", response_model=BuyResponse, status_code=status.HTTP_201_CREATED)
async def buy(buy_request: BuyRequest):
    """
    Handle a purchase request.

    This endpoint:
    1. Receives username and user_id from the client
    2. Selects a random item to purchase
    3. Generates a purchase event
    4. Publishes the event to Kafka
    5. Returns the purchase details

    Args:
        buy_request: Purchase request containing username and user_id

    Returns:
        BuyResponse: Purchase confirmation with details

    Raises:
        503: If Kafka is unavailable
        500: If message publishing fails
    """
    try:
        # Check if Kafka producer is ready
        if not kafka_producer or not kafka_producer.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Purchase service temporarily unavailable (Kafka connection issue)"
            )

        # Generate purchase event
        purchase_event = generate_purchase_event(buy_request)

        logger.info(
            f"Processing purchase: user={purchase_event.username}, "
            f"item={purchase_event.item_name}, price=${purchase_event.price}"
        )

        # Publish to Kafka
        # The key is user_id to ensure all purchases from same user go to same partition
        record_metadata = await kafka_producer.send_message(
            key=purchase_event.user_id,
            value=purchase_event.model_dump()
        )

        logger.info(
            f"Purchase published to Kafka: partition={record_metadata.partition}, "
            f"offset={record_metadata.offset}"
        )

        # Return success response
        return BuyResponse(
            success=True,
            message=f"Successfully purchased {purchase_event.item_name} for ${purchase_event.price}",
            purchase=purchase_event,
            kafka_partition=record_metadata.partition,
            kafka_offset=record_metadata.offset
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process purchase: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process purchase request"
        )


@app.get("/getAllUserBuys/{user_id}", response_model=UserPurchasesResponse)
async def get_all_user_purchases(user_id: str):
    """
    Retrieve all purchases for a specific user.

    This endpoint proxies the request to the Customer Management API.
    It acts as a gateway between the frontend and the backend service.

    Args:
        user_id: Unique identifier for the user

    Returns:
        UserPurchasesResponse: Purchase history with statistics

    Raises:
        404: If user has no purchases
        503: If Customer Management API is unavailable
        500: If proxy request fails
    """
    try:
        logger.info(f"Fetching purchases for user_id={user_id}")

        # Make request to Customer Management API
        response = await http_client.get(
            f"/purchases/{user_id}",
            timeout=10.0
        )

        # Handle different response codes
        if response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No purchases found for user_id: {user_id}"
            )

        if response.status_code != 200:
            logger.error(
                f"Customer Management API returned status {response.status_code}: "
                f"{response.text}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to retrieve purchases at this time"
            )

        # Parse and return response
        data = response.json()
        logger.info(f"Retrieved {data['total_purchases']} purchases for user_id={user_id}")

        return UserPurchasesResponse(**data)

    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.error(f"Timeout while fetching purchases for user_id={user_id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request timeout - Customer Management API not responding"
        )
    except httpx.ConnectError:
        logger.error(f"Connection error to Customer Management API")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer Management API unavailable"
        )
    except Exception as e:
        logger.error(f"Failed to fetch purchases for user_id={user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve purchase history"
        )


@app.get("/items", response_model=List[dict])
async def get_available_items():
    """
    Get list of available items for purchase.

    This is a helper endpoint for the frontend to display
    what items are available (even though purchases are random).

    Returns:
        List of items with name and price
    """
    return RANDOM_ITEMS


@app.get("/metrics")
async def metrics():
    """
    Prometheus-compatible metrics endpoint for monitoring and autoscaling.

    Metrics exposed:
    - Total messages sent
    - Messages failed
    - Kafka producer status

    This can be used by Prometheus for custom HPA metrics.
    """
    stats = kafka_producer.get_stats() if kafka_producer else {}

    return {
        "service": "customer-facing-web-server",
        "messages_sent": stats.get("messages_sent", 0),
        "messages_failed": stats.get("messages_failed", 0),
        "kafka_connected": kafka_producer.is_connected() if kafka_producer else False,
        "last_message_time": stats.get("last_message_time")
    }


# MAIN ENTRY POINT

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )