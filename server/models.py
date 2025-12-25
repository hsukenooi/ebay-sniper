from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Optional, List


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str


class AddSniperRequest(BaseModel):
    listing_number: str
    max_bid: Decimal


class AuctionResponse(BaseModel):
    id: int
    listing_number: str
    listing_url: str
    item_title: str
    seller_name: Optional[str]
    current_price: Decimal
    max_bid: Decimal
    currency: str
    auction_end_time_utc: datetime
    last_price_refresh_utc: Optional[datetime]
    status: str
    skip_reason: Optional[str]
    outcome: Optional[str]
    final_price: Optional[Decimal]
    
    model_config = {"from_attributes": True}


class BidAttemptResponse(BaseModel):
    auction_id: int
    attempt_time_utc: datetime
    result: str
    error_message: Optional[str]
    
    model_config = {"from_attributes": True}


class BulkAddItemRequest(BaseModel):
    listing_number: str
    max_bid: Decimal


class BulkAddRequest(BaseModel):
    items: List[BulkAddItemRequest]


class BulkAddItemResult(BaseModel):
    listing_number: str
    max_bid: Decimal
    success: bool
    auction_id: Optional[int] = None
    item_title: Optional[str] = None
    current_price: Optional[Decimal] = None
    auction_end_time_utc: Optional[datetime] = None
    listing_url: Optional[str] = None
    error_message: Optional[str] = None
    
    model_config = {"from_attributes": True}


class BulkAddResponse(BaseModel):
    results: List[BulkAddItemResult]

