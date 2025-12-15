from typing import Optional, List

from pydantic import BaseModel, Field

class Purchase(BaseModel):
    """
    Purchase data model representing a user's purchase transaction.

    This matches the schema published by the Customer Facing Service.
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


class PurchaseResponse(Purchase):
    """
    Purchase response model including MongoDB's _id field.
    """
    id: str = Field(..., alias="_id", description="MongoDB document ID")

    class Config:
        populate_by_name = True


class UserPurchasesResponse(BaseModel):
    """
    Response model for user purchases list.
    """
    user_id: str
    username: Optional[str] = None
    total_purchases: int
    total_spent: float
    purchases: List[PurchaseResponse]

