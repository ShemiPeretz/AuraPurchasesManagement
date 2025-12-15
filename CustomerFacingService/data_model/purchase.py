from typing import Optional, List

from pydantic import BaseModel, Field

class Purchase(BaseModel):
    """
    Purchase model (from Customer Management API response).
    """
    id: str = Field(..., alias="_id")
    username: str
    user_id: str
    item_name: str
    price: float
    timestamp: str

    class Config:
        populate_by_name = True


class UserPurchasesResponse(BaseModel):
    """
    Response model for user purchases list (from Customer Management API).
    """
    user_id: str
    username: Optional[str] = None
    total_purchases: int
    total_spent: float
    purchases: List[Purchase]


class PurchaseEvent(BaseModel):
    """
    Purchase event model that gets published to Kafka.

    This is the complete purchase data structure sent to the message broker.
    """
    username: str = Field(..., description="Name of the user making the purchase")
    user_id: str = Field(..., description="Unique identifier for the user")
    item_name: str = Field(..., description="Name of the item purchased")
    price: float = Field(..., gt=0, description="Price of the item (must be positive)")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the purchase")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "user_id": "user_123",
                "item_name": "Laptop",
                "price": 999.99,
                "timestamp": "2025-12-15T10:30:00Z"
            }
        }
