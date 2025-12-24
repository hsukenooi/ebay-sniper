import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from database import SessionLocal, Auction, BidAttempt, AuctionStatus, BidResult
from .ebay_client import eBayClient
import requests

logger = logging.getLogger(__name__)

BID_OFFSET_SECONDS = 3  # Default offset
PRE_BID_CHECK_SECONDS = 60  # Check price at T-60s


class Worker:
    """Single-worker bid execution engine."""
    
    def __init__(self):
        self.ebay_client = eBayClient()
        self.running = False
        
    def _refresh_token_if_needed(self, auction_end_time: datetime):
        """Refresh OAuth token if it will expire before auction ends."""
        if not self.ebay_client.oauth_token_expires_at:
            return
        
        # Refresh if token expires within 5 minutes of auction end
        if self.ebay_client.oauth_token_expires_at < auction_end_time - timedelta(minutes=5):
            # Trigger token refresh (simplified - in production, implement actual refresh)
            logger.info("Token refresh needed but not implemented in this version")
    
    def _pre_bid_price_check(self, db: Session, auction: Auction) -> bool:
        """
        Perform price check at T-60s.
        Returns True if should proceed, False if should skip.
        """
        try:
            details = self.ebay_client.get_auction_details(auction.listing_number)
            current_price = details["current_price"]
            
            # Update cached price
            auction.current_price = current_price
            auction.last_price_refresh_utc = datetime.utcnow()
            db.commit()
            
            if current_price > auction.max_bid:
                auction.status = AuctionStatus.SKIPPED.value
                auction.skip_reason = "Current price exceeded max bid at T−60s"
                db.commit()
                logger.info(f"Auction {auction.id} skipped: price {current_price} > max_bid {auction.max_bid}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error in pre-bid price check for auction {auction.id}: {e}")
            # Continue with normal execution on error (per requirements)
            return True
    
    def _execute_bid(self, db: Session, auction: Auction) -> bool:
        """
        Execute bid with retry logic and idempotency check.
        Returns True if bid succeeded, False otherwise.
        """
        # Atomic update: Scheduled -> Executing
        # This ensures idempotency - only one worker can transition this auction
        rows_updated = db.query(Auction).filter(
            Auction.id == auction.id,
            Auction.status == AuctionStatus.SCHEDULED.value
        ).update({"status": AuctionStatus.EXECUTING.value})
        
        db.commit()
        
        if rows_updated == 0:
            # Auction already in Executing or another state - another worker got it or it changed
            logger.info(f"Auction {auction.id} already in non-Scheduled state, skipping execution")
            return False
        
        # Refresh auction object
        db.refresh(auction)
        
        # Check if auction has ended
        if datetime.utcnow() >= auction.auction_end_time_utc:
            auction.status = AuctionStatus.FAILED.value
            bid_attempt = BidAttempt(
                auction_id=auction.id,
                attempt_time_utc=datetime.utcnow(),
                result=BidResult.FAILED.value,
                error_message="Auction ended before bid could be placed"
            )
            db.add(bid_attempt)
            db.commit()
            return False
        
        # Refresh token if needed
        self._refresh_token_if_needed(auction.auction_end_time_utc)
        
        # Retry logic
        max_attempts = 4
        delays = [0.1, 0.25, 0.5]  # 100ms, 250ms, 500ms
        timeout_range = (0.3, 0.6)  # 300-600ms
        
        # Calculate bid amount with proper increment
        min_increment = self.ebay_client.calculate_min_bid_increment(auction.current_price)
        bid_amount = min(auction.current_price + min_increment, auction.max_bid)
        
        for attempt in range(max_attempts):
            # Check if we've run out of time
            if datetime.utcnow() >= auction.auction_end_time_utc - timedelta(milliseconds=300):
                auction.status = AuctionStatus.FAILED.value
                bid_attempt = BidAttempt(
                    auction_id=auction.id,
                    attempt_time_utc=datetime.utcnow(),
                    result=BidResult.FAILED.value,
                    error_message="Ran out of time window for bid placement"
                )
                db.add(bid_attempt)
                db.commit()
                return False
            
            try:
                # Place bid with timeout
                import random
                timeout = random.uniform(*timeout_range)
                
                result = self.ebay_client.place_bid(auction.listing_number, bid_amount)
                
                # Success!
                auction.status = AuctionStatus.BID_PLACED.value
                bid_attempt = BidAttempt(
                    auction_id=auction.id,
                    attempt_time_utc=datetime.utcnow(),
                    result=BidResult.SUCCESS.value,
                    error_message=None
                )
                db.add(bid_attempt)
                db.commit()
                logger.info(f"Bid placed successfully for auction {auction.id}")
                return True
                
            except requests.exceptions.Timeout:
                logger.warning(f"Bid attempt {attempt + 1}/{max_attempts} timed out for auction {auction.id}")
                if attempt < max_attempts - 1:
                    time.sleep(delays[attempt] if attempt < len(delays) else delays[-1])
                continue
                
            except requests.exceptions.RequestException as e:
                error_str = str(e)
                # Check if retryable
                is_retryable = False
                if "429" in error_str and attempt < max_attempts - 1:
                    # Rate limited - retry if time allows
                    is_retryable = True
                    logger.warning(f"Rate limited on attempt {attempt + 1}, retrying")
                elif "5" in error_str or "server error" in error_str.lower():
                    # 5xx error - retry if attempts remaining
                    if attempt < max_attempts - 1:
                        is_retryable = True
                        logger.warning(f"Server error on attempt {attempt + 1}, retrying")
                
                if is_retryable:
                    time.sleep(delays[attempt] if attempt < len(delays) else delays[-1])
                    continue
                else:
                    # Non-retryable error
                    auction.status = AuctionStatus.FAILED.value
                    bid_attempt = BidAttempt(
                        auction_id=auction.id,
                        attempt_time_utc=datetime.utcnow(),
                        result=BidResult.FAILED.value,
                        error_message=str(e)
                    )
                    db.add(bid_attempt)
                    db.commit()
                    return False
                    
            except Exception as e:
                # Unexpected error
                auction.status = AuctionStatus.FAILED.value
                bid_attempt = BidAttempt(
                    auction_id=auction.id,
                    attempt_time_utc=datetime.utcnow(),
                    result=BidResult.FAILED.value,
                    error_message=str(e)
                )
                db.add(bid_attempt)
                db.commit()
                logger.error(f"Unexpected error placing bid for auction {auction.id}: {e}")
                return False
        
        # All retries exhausted
        auction.status = AuctionStatus.FAILED.value
        bid_attempt = BidAttempt(
            auction_id=auction.id,
            attempt_time_utc=datetime.utcnow(),
            result=BidResult.FAILED.value,
            error_message="All retry attempts exhausted"
        )
        db.add(bid_attempt)
        db.commit()
        return False
    
    def _process_auction(self, db: Session, auction: Auction):
        """Process a single auction according to its timing."""
        now = datetime.utcnow()
        bid_execution_time = auction.auction_end_time_utc - timedelta(seconds=BID_OFFSET_SECONDS)
        pre_check_time = auction.auction_end_time_utc - timedelta(seconds=PRE_BID_CHECK_SECONDS)
        
        # Skip if auction is in terminal state
        if auction.status in [AuctionStatus.BID_PLACED.value, AuctionStatus.FAILED.value, 
                             AuctionStatus.SKIPPED.value, AuctionStatus.CANCELLED.value]:
            return
        
        # Handle auctions stuck in Executing state (crashed worker)
        if auction.status == AuctionStatus.EXECUTING.value:
            if now >= auction.auction_end_time_utc:
                auction.status = AuctionStatus.FAILED.value
                if not db.query(BidAttempt).filter(BidAttempt.auction_id == auction.id).first():
                    bid_attempt = BidAttempt(
                        auction_id=auction.id,
                        attempt_time_utc=now,
                        result=BidResult.FAILED.value,
                        error_message="Worker crashed during execution, auction ended"
                    )
                    db.add(bid_attempt)
                db.commit()
            return
        
        # Pre-bid price check at T-60s
        if auction.status == AuctionStatus.SCHEDULED.value:
            time_until_pre_check = (pre_check_time - now).total_seconds()
            if 0 <= time_until_pre_check < 1:  # Within 1 second of pre-check time
                if not self._pre_bid_price_check(db, auction):
                    return  # Auction was skipped
                # Refresh auction object after pre-check
                db.refresh(auction)
            
            # Execute bid at bid_execution_time (only if still Scheduled)
            if auction.status == AuctionStatus.SCHEDULED.value:
                time_until_bid = (bid_execution_time - now).total_seconds()
                if 0 <= time_until_bid < 1:  # Within 1 second of bid time
                    self._execute_bid(db, auction)
    
    def run_loop(self):
        """Main worker loop."""
        self.running = True
        logger.info("Worker loop started")
        
        while self.running:
            try:
                db = SessionLocal()
                try:
                    # Get all scheduled or executing auctions
                    auctions = db.query(Auction).filter(
                        Auction.status.in_([AuctionStatus.SCHEDULED.value, AuctionStatus.EXECUTING.value])
                    ).all()
                    
                    for auction in auctions:
                        try:
                            self._process_auction(db, auction)
                        except Exception as e:
                            logger.error(f"Error processing auction {auction.id}: {e}")
                            db.rollback()
                            continue
                    
                    db.commit()
                finally:
                    db.close()
                
                # Sleep briefly before next iteration
                time.sleep(0.5)  # Check every 500ms
                
            except KeyboardInterrupt:
                logger.info("Worker loop interrupted")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(1)
    
    def stop(self):
        """Stop the worker loop."""
        self.running = False

