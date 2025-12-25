from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Optional


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

