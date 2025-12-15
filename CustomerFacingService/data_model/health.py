from pydantic import BaseModel

class HealthResponse(BaseModel):
    """
    Health check response model.
    """
    status: str
    service: str
    kafka_connected: bool
    customer_management_api_reachable: bool
    timestamp: str
