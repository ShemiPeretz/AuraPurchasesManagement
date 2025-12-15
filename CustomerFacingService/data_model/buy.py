from typing import Optional

from pydantic import BaseModel, Field, field_validator

from CustomerFacingService.data_model.purchase import PurchaseEvent


class BuyRequest(BaseModel):
    """
    Request model for purchase transactions.

    The user provides their username and user_id. The system will:
    - Select a random item to purchase
    - Generate a timestamp
    - Publish to Kafka
    """
    username: str = Field(..., min_length=1, max_length=100, description="Username of the buyer")
    user_id: str = Field(..., min_length=1, max_length=100, description="Unique user identifier")

    @field_validator('username')
    def validate_username(cls, v):
        """Validate username format."""
        if not v.strip():
            raise ValueError("Username cannot be empty or whitespace")
        return v.strip()

    @field_validator('user_id')
    def validate_user_id(cls, v):
        """Validate user_id format."""
        if not v.strip():
            raise ValueError("User ID cannot be empty or whitespace")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "user_id": "user_123"
            }
        }


class BuyResponse(BaseModel):
    """
    Response model for successful purchase.
    """
    success: bool = True
    message: str = "Purchase successful"
    purchase: PurchaseEvent
    kafka_partition: Optional[int] = None
    kafka_offset: Optional[int] = None

