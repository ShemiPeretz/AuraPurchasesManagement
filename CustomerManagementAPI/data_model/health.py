from pydantic import BaseModel

class HealthResponse(BaseModel):
    """
    Health check response model.
    """
    status: str
    service: str
    mongodb_connected: bool
    kafka_connected: bool
    timestamp: str