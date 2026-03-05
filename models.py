

from pydantic import BaseModel, Field
from typing import Optional
import uuid


# --- Reference generator ---
def generate_reference(prefix: str = "TXN") -> str:
    """Generates a unique reference 32 chars long, safe for provider APIs."""
    return f"{prefix}-{uuid.uuid4().hex[:24]}"  # total length ~29 chars



class RequestPayment(BaseModel):
    account_no: str = Field(..., example="1234567890")
    msisdn: str = Field(..., example="+256701234567")
    currency: str = Field(..., example="UGX")
    amount: float = Field(..., gt=0)
    description: str


class SendPayment(BaseModel):
    account_no: str = Field(..., example="1234567890")
    msisdn: str = Field(..., example="+256701234567")
    currency: str = Field(..., example="UGX")
    amount: float = Field(..., gt=0)
    description: str


class ValidateMsisdn(BaseModel):
    msisdn: str = Field(..., example="+256701234567")


class RelworxWebhookPayload(BaseModel):
    status: str
    customer_reference: str
    internal_reference: str
    msisdn: str
    amount: float
    currency: str
    provider: Optional[str]
    completed_at: str
    provider_response: Optional[dict] = None  