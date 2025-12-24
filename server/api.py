from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
import jwt
import os
import requests
from dotenv import load_dotenv
from database import get_db, Auction, BidAttempt, AuctionStatus, BidResult, SessionLocal
from .models import AuthRequest, AuthResponse, AddSniperRequest, AuctionResponse, BidAttemptResponse
from .ebay_client import eBayClient
import logging

# Load environment variables before creating any clients
load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI()
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ebay_client = eBayClient()


def verify_token(authorization: str = Header(None)) -> str:
    """Verify and extract token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub", "")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _should_refresh_price(auction: Auction) -> bool:
    """Check if price should be refreshed (cache TTL 60s)."""
    if not auction.last_price_refresh_utc:
        return True
    return (datetime.utcnow() - auction.last_price_refresh_utc).total_seconds() > 60


def _refresh_auction_price(db: Session, auction: Auction):
    """Refresh auction price from eBay."""
    try:
        details = ebay_client.get_auction_details(auction.listing_number)
        auction.current_price = details["current_price"]
        auction.currency = details["currency"]
        auction.listing_url = details["listing_url"]
        auction.item_title = details["item_title"]
        auction.auction_end_time_utc = details["auction_end_time_utc"]
        auction.last_price_refresh_utc = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"Error refreshing price for auction {auction.id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh auction price: {str(e)}")


@app.post("/auth", response_model=AuthResponse)
def auth(request: AuthRequest):
    """Authenticate user and return API token."""
    # Simplified auth - in production, verify credentials properly
    # For now, accept any username/password and issue a token
    token = jwt.encode(
        {"sub": request.username, "exp": datetime.utcnow() + timedelta(days=30)},
        SECRET_KEY,
        algorithm="HS256"
    )
    return AuthResponse(token=token)


@app.post("/sniper/add", response_model=AuctionResponse)
def add_sniper(request: AddSniperRequest, db: Session = Depends(get_db), username: str = Depends(verify_token)):
    """Add a new listing for an auction."""
    # Check if auction already exists
    existing = db.query(Auction).filter(Auction.listing_number == request.listing_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Auction already exists")
    
    # Fetch auction details from eBay
    try:
        details = ebay_client.get_auction_details(request.listing_number)
    except ValueError as e:
        # OAuth token or configuration issues
        logger.error(f"Configuration error fetching auction {request.listing_number}: {e}")
        raise HTTPException(status_code=400, detail=f"eBay API configuration error: {str(e)}")
    except requests.exceptions.RequestException as e:
        # Network or API errors
        logger.error(f"eBay API error fetching auction {request.listing_number}: {e}")
        error_detail = f"Failed to fetch auction from eBay: {str(e)}"
        if hasattr(e.response, 'status_code'):
            status_code = e.response.status_code
            error_detail += f" (HTTP {status_code})"
            # Provide more helpful message for 404 errors
            if status_code == 404:
                error_detail = (
                    f"Listing {request.listing_number} not found via eBay Browse API. "
                    f"This listing may not be accessible through the API, may have ended, "
                    f"or may have regional restrictions. Please verify the listing exists and is active on eBay."
                )
        if hasattr(e.response, 'text') and e.response.text:
            if not (hasattr(e.response, 'status_code') and e.response.status_code == 404):
                error_detail += f" - {e.response.text[:200]}"
        raise HTTPException(status_code=400, detail=error_detail)
    except Exception as e:
        logger.error(f"Unexpected error fetching auction {request.listing_number}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to fetch auction details: {str(e)}")
    
    # Create auction
    auction = Auction(
        listing_number=request.listing_number,
        listing_url=details["listing_url"],
        item_title=details["item_title"],
        current_price=details["current_price"],
        max_bid=request.max_bid,
        currency=details["currency"],
        auction_end_time_utc=details["auction_end_time_utc"],
        last_price_refresh_utc=datetime.utcnow(),
        status=AuctionStatus.SCHEDULED.value,
    )
    
    db.add(auction)
    db.commit()
    db.refresh(auction)
    
    return AuctionResponse.model_validate(auction)


@app.get("/sniper/list", response_model=List[AuctionResponse])
def list_snipers(db: Session = Depends(get_db), username: str = Depends(verify_token)):
    """List all listings, refreshing prices if cache expired."""
    auctions = db.query(Auction).order_by(Auction.auction_end_time_utc).all()
    
    # Refresh prices if cache expired
    for auction in auctions:
        if _should_refresh_price(auction):
            try:
                _refresh_auction_price(db, auction)
            except Exception as e:
                logger.warning(f"Failed to refresh price for auction {auction.id}: {e}")
                # Continue with cached price
    
    return [AuctionResponse.model_validate(a) for a in auctions]


@app.get("/sniper/{auction_id}/status", response_model=AuctionResponse)
def get_status(auction_id: int, db: Session = Depends(get_db), username: str = Depends(verify_token)):
    """Get status of a specific auction, refreshing price if cache expired."""
    auction = db.query(Auction).filter(Auction.id == auction_id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    # Refresh price if cache expired
    if _should_refresh_price(auction):
        try:
            _refresh_auction_price(db, auction)
        except Exception as e:
            logger.warning(f"Failed to refresh price for auction {auction.id}: {e}")
    
    return AuctionResponse.model_validate(auction)


@app.delete("/sniper/{auction_id}")
def remove_sniper(auction_id: int, db: Session = Depends(get_db), username: str = Depends(verify_token)):
    """Remove (cancel) a listing."""
    auction = db.query(Auction).filter(Auction.id == auction_id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    # Only allow cancelling if still scheduled
    if auction.status != AuctionStatus.SCHEDULED.value:
        raise HTTPException(status_code=400, detail=f"Cannot cancel auction with status {auction.status}")
    
    auction.status = AuctionStatus.CANCELLED.value
    db.commit()
    
    return {"message": "Listing cancelled"}


@app.get("/sniper/{auction_id}/logs", response_model=Optional[BidAttemptResponse])
def get_logs(auction_id: int, db: Session = Depends(get_db), username: str = Depends(verify_token)):
    """Get bid attempt logs for an auction."""
    auction = db.query(Auction).filter(Auction.id == auction_id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    bid_attempt = db.query(BidAttempt).filter(BidAttempt.auction_id == auction_id).first()
    if not bid_attempt:
        return None
    
    return BidAttemptResponse.model_validate(bid_attempt)

