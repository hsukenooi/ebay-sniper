import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from database import SessionLocal, Auction, BidAttempt, AuctionStatus, BidResult, AuctionOutcome
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
        # Check user token expiration (used for bidding)
        if self.ebay_client.oauth_user_token_expires_at:
            # Refresh if token expires within 5 minutes of auction end
            if self.ebay_client.oauth_user_token_expires_at < auction_end_time - timedelta(minutes=5):
                logger.info("User OAuth token will expire before auction ends, refreshing...")
                self.ebay_client.refresh_user_token()
    
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
        
        # Use max_bid directly - eBay's proxy bidding system will automatically
        # bid incrementally up to this amount as needed to stay ahead of other bidders
        bid_amount = auction.max_bid
        
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
                # Place bid
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
    
    def _check_auction_outcomes(self, db: Session):
        """Check outcomes and final prices for auctions that have ended."""
        try:
            now = datetime.utcnow()
            
            # Find auctions that ended and have BidPlaced status but don't have an outcome yet
            bid_placed_auctions = db.query(Auction).filter(
                Auction.status == AuctionStatus.BID_PLACED.value,
                Auction.auction_end_time_utc < now,
                Auction.outcome == AuctionOutcome.PENDING.value
            ).all()
            
            for auction in bid_placed_auctions:
                try:
                    # Wait a bit after auction ends for eBay to update
                    # Check if at least 30 seconds have passed since auction ended
                    time_since_end = (now - auction.auction_end_time_utc).total_seconds()
                    if time_since_end < 30:
                        continue  # Too soon, eBay might not have updated yet
                    
                    outcome_data = self.ebay_client.get_auction_outcome(auction.listing_number)
                    
                    auction.outcome = outcome_data["outcome"]
                    if outcome_data["final_price"]:
                        auction.final_price = outcome_data["final_price"]
                    
                    db.commit()
                    logger.info(f"Auction {auction.id} outcome: {outcome_data['outcome']}, final price: {outcome_data['final_price']}")
                    
                except Exception as e:
                    logger.error(f"Error checking outcome for auction {auction.id}: {e}", exc_info=True)
                    db.rollback()
                    # Don't fail the entire loop, continue with other auctions
                    continue
            
            # Also try to get final price for ended auctions that don't have it yet
            # (e.g., FAILED auctions where we want to know what the final price was)
            auctions_needing_final_price = db.query(Auction).filter(
                Auction.auction_end_time_utc < now,
                Auction.final_price.is_(None),
                Auction.outcome == AuctionOutcome.PENDING.value
            ).all()
            
            for auction in auctions_needing_final_price:
                try:
                    # Wait at least 30 seconds after auction ends
                    time_since_end = (now - auction.auction_end_time_utc).total_seconds()
                    if time_since_end < 30:
                        continue
                    
                    # Try to get final price from Trading API GetItem (works even if we didn't bid)
                    final_price = self.ebay_client.get_final_price_from_trading_api(auction.listing_number)
                    
                    if final_price:
                        auction.final_price = final_price
                        db.commit()
                        logger.info(f"Retrieved final price ${final_price} for auction {auction.id} from Trading API")
                    
                except Exception as e:
                    logger.error(f"Error getting final price for auction {auction.id}: {e}", exc_info=True)
                    db.rollback()
                    continue
                    
        except Exception as e:
            logger.error(f"Error in _check_auction_outcomes: {e}", exc_info=True)
            db.rollback()
            # Don't fail the worker loop - let caller handle cleanup
    
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
        
        # Cleanup: Handle Scheduled auctions that have already ended
        # This can happen if the worker wasn't running when the auction ended
        if auction.status == AuctionStatus.SCHEDULED.value:
            if now >= auction.auction_end_time_utc:
                auction.status = AuctionStatus.FAILED.value
                if not db.query(BidAttempt).filter(BidAttempt.auction_id == auction.id).first():
                    bid_attempt = BidAttempt(
                        auction_id=auction.id,
                        attempt_time_utc=now,
                        result=BidResult.FAILED.value,
                        error_message="Auction ended before worker could process it"
                    )
                    db.add(bid_attempt)
                db.commit()
                logger.info(f"Auction {auction.id} was still Scheduled after ending, marked as Failed")
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
                # Process active auctions
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
                            logger.error(f"Error processing auction {auction.id}: {e}", exc_info=True)
                            db.rollback()
                            continue
                    
                    db.commit()
                finally:
                    db.close()
                
                # Check outcomes for ended auctions with BidPlaced status (use separate session)
                outcome_db = SessionLocal()
                try:
                    self._check_auction_outcomes(outcome_db)
                except Exception as e:
                    logger.error(f"Error checking auction outcomes: {e}", exc_info=True)
                    outcome_db.rollback()
                finally:
                    outcome_db.close()
                
                # Sleep briefly before next iteration
                time.sleep(0.5)  # Check every 500ms
                
            except KeyboardInterrupt:
                logger.info("Worker loop interrupted")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                time.sleep(1)
    
    def stop(self):
        """Stop the worker loop."""
        self.running = False

