from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional
from app.models import MatchStatus

class TenantCreate(BaseModel):
    name: str

class TenantResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class InvoiceCreate(BaseModel):
    amount: float
    currency: str = "USD"
    invoice_date: Optional[datetime] = None
    description: Optional[str] = None
    invoice_number: Optional[str] = None
    vendor_id: Optional[str] = None

class InvoiceResponse(BaseModel):
    id: str
    tenant_id: str
    vendor_id: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: float
    currency: str
    invoice_date: Optional[datetime] = None
    description: Optional[str] = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TransactionCreate(BaseModel):
    amount: float
    currency: str = "USD"
    posted_at: str
    description: str
    external_id: Optional[str] = None

class TransactionResponse(BaseModel):
    id: str
    amount: float
    currency: str
    posted_at: datetime
    description: str
    external_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class MatchExplanationResponse(BaseModel):
    explanation: str

class MatchCandidateResponse(BaseModel):
    id: str
    invoice_id: str
    transaction_id: str
    score: float
    status: MatchStatus
    model_config = ConfigDict(from_attributes=True)

class ImportResponse(BaseModel):
    message: str
    count: int
    transaction_ids: List[str]
