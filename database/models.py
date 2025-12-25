from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from enum import Enum

Base = declarative_base()


class AuctionStatus(str, Enum):
    SCHEDULED = "Scheduled"
    EXECUTING = "Executing"
    BID_PLACED = "BidPlaced"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    SKIPPED = "Skipped"


class AuctionOutcome(str, Enum):
    PENDING = "Pending"
    WON = "Won"
    LOST = "Lost"


class BidResult(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class Auction(Base):
    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True, index=True)
    listing_number = Column(String, nullable=False, index=True)
    listing_url = Column(String, nullable=False)
    item_title = Column(String, nullable=False)
    seller_name = Column(String, nullable=True)
    current_price = Column(Numeric(10, 2), nullable=False)
    max_bid = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    auction_end_time_utc = Column(DateTime, nullable=False, index=True)
    last_price_refresh_utc = Column(DateTime, nullable=True, index=True)  # Added index for refresh-on-read queries
    status = Column(String, nullable=False, default=AuctionStatus.SCHEDULED.value, index=True)
    skip_reason = Column(Text, nullable=True)
    outcome = Column(String, nullable=True, default=AuctionOutcome.PENDING.value, index=True)
    final_price = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    bid_attempt = relationship("BidAttempt", back_populates="auction", uselist=False)


class BidAttempt(Base):
    __tablename__ = "bid_attempts"

    auction_id = Column(Integer, ForeignKey("auctions.id"), primary_key=True, unique=True)
    attempt_time_utc = Column(DateTime, nullable=False)
    result = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)

    auction = relationship("Auction", back_populates="bid_attempt")

