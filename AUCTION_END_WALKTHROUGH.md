# Walkthrough: What Happens Just Before An Auction Ends

This document walks through exactly what the code does in the final moments before an auction ends.

## Timeline Overview

- **T-60 seconds**: Pre-bid price check
- **T-3 seconds**: Bid execution window opens
- **T-0 seconds**: Auction ends

The worker loop runs **every 500ms** (0.5 seconds), checking if it's time to act.

---

## Constants

```python
BID_OFFSET_SECONDS = 3      # Bid at T-3 seconds
PRE_BID_CHECK_SECONDS = 60  # Price check at T-60 seconds
```

Worker loop sleep: `0.5 seconds` between iterations

---

## Step-by-Step Execution

### Phase 1: T-60 Seconds (Pre-Bid Price Check)

**When**: Auction end time minus 60 seconds  
**Trigger**: Worker loop detects we're within 1 second of `pre_check_time`

**What Happens** (`_pre_bid_price_check()`):

1. **Fetch Current Price from eBay**
   - Calls `ebay_client.get_auction_details(auction.listing_number)`
   - Uses Application OAuth token (for reading auction data)
   - Gets latest price, end time, and auction details

2. **Update Cached Price**
   ```python
   auction.current_price = details["current_price"]
   auction.last_price_refresh_utc = datetime.utcnow()
   db.commit()
   ```

3. **Price Validation**
   - **If `current_price > max_bid`**:
     - Status → `SKIPPED`
     - `skip_reason = "Current price exceeded max bid at T−60s"`
     - Returns `False` (auction will not proceed to bidding)
     - **Auction stops here - no bid will be placed**
   
   - **If `current_price <= max_bid`**:
     - Returns `True` (proceed with bidding)
     - Auction remains in `SCHEDULED` status

4. **Error Handling**
   - If price check fails (network error, API error, etc.):
     - Logs error
     - Returns `True` (proceeds anyway - fail-open behavior)
     - Continues to bid execution

---

### Phase 2: T-3 Seconds (Bid Execution Window)

**When**: Auction end time minus 3 seconds  
**Trigger**: Worker loop detects we're within 1 second of `bid_execution_time`

**What Happens** (`_execute_bid()`):

#### Step 1: Atomic Status Transition (Idempotency)

```python
rows_updated = db.query(Auction).filter(
    Auction.id == auction.id,
    Auction.status == AuctionStatus.SCHEDULED.value
).update({"status": AuctionStatus.EXECUTING.value})
```

- **Critical**: This is an **atomic database operation**
- Only **one worker/process** can transition from `SCHEDULED` → `EXECUTING`
- If `rows_updated == 0`, another worker already grabbed it → exit early
- This prevents **duplicate bids** even with multiple workers running

#### Step 2: Final Time Check

```python
if datetime.utcnow() >= auction.auction_end_time_utc:
    # Too late! Auction already ended
    status → FAILED
    error_message = "Auction ended before bid could be placed"
    return False
```

#### Step 3: Token Refresh Check

```python
self._refresh_token_if_needed(auction.auction_end_time_utc)
```

- Checks if User OAuth token expires within 5 minutes of auction end
- If so, refreshes the token automatically
- Ensures we have a valid token for bid placement

#### Step 4: Retry Loop (Up to 4 Attempts)

**Bid Amount**: `auction.max_bid` (your maximum bid - eBay proxy bidding handles increments)

**Retry Configuration**:
- Max attempts: **4**
- Delays between retries: `100ms → 250ms → 500ms`
- Request timeout: `300-600ms` (randomized to avoid thundering herd)

**For Each Attempt**:

1. **Time Window Check** (Critical!)
   ```python
   if datetime.utcnow() >= auction.auction_end_time_utc - timedelta(milliseconds=300):
       # Less than 300ms remaining - abort!
       status → FAILED
       error_message = "Ran out of time window for bid placement"
       return False
   ```
   - If less than **300ms** remaining until auction end, abort all retries
   - Prevents placing bids after auction ends

2. **Place Bid via eBay API**
   ```python
   result = self.ebay_client.place_bid(auction.listing_number, bid_amount)
   ```
   
   **What `place_bid()` does**:
   - Ensures User OAuth token is valid (refreshes if needed)
   - Constructs XML request:
     ```xml
     <PlaceOfferRequest>
         <RequesterCredentials>
             <eBayAuthToken>{user_token}</eBayAuthToken>
         </RequesterCredentials>
         <ItemID>{listing_number}</ItemID>
         <Offer>
             <MaxBid>{max_bid}</MaxBid>
             <Quantity>1</Quantity>
         </Offer>
         <SiteID>0</SiteID>
     </PlaceOfferRequest>
     ```
   - Sends to eBay Trading API endpoint: `https://api.ebay.com/ws/api.dll`
   - Uses **User OAuth token** (required for bidding)
   - Timeout: **600ms** maximum

3. **Handle Response**:

   **Success**:
   ```python
   auction.status = AuctionStatus.BID_PLACED.value
   bid_attempt = BidAttempt(
       result=BidResult.SUCCESS.value,
       attempt_time_utc=datetime.utcnow()
   )
   db.commit()
   return True  # Done! Bid placed successfully
   ```

   **Timeout Error**:
   - Logs warning
   - Sleeps (100ms, 250ms, or 500ms depending on attempt)
   - **Retries** if attempts remaining and time allows

   **Rate Limit (429)**:
   - Checks for `Retry-After` header
   - If retryable and time allows → retry
   - Otherwise → fail

   **5xx Server Error**:
   - If retryable and time allows → retry
   - Otherwise → fail

   **401 Unauthorized**:
   - Attempts token refresh
   - Retries with new token

   **Non-Retryable Errors** (4xx errors like bid too low, item not found, etc.):
   ```python
   auction.status = AuctionStatus.FAILED.value
   bid_attempt = BidAttempt(
       result=BidResult.FAILED.value,
       error_message=str(e)
   )
   return False
   ```

4. **If All Retries Exhausted**:
   ```python
   auction.status = AuctionStatus.FAILED.value
   error_message = "All retry attempts exhausted"
   return False
   ```

---

## Example Timeline

Let's say an auction ends at **2025-01-20 12:00:00 UTC**:

| Time | What Happens |
|------|--------------|
| **11:58:59** | Worker checks: `now = 11:58:59`, `pre_check_time = 11:59:00` → Within 1 second, trigger pre-check |
| **11:59:00** | Pre-bid price check executes:<br>- Fetches current price from eBay<br>- If price > max_bid → SKIP<br>- If price ≤ max_bid → Continue |
| **11:59:57** | Worker checks: `now = 11:59:57`, `bid_execution_time = 11:59:57` → Within 1 second, trigger bid |
| **11:59:57.0** | `_execute_bid()` starts:<br>- Atomic transition: SCHEDULED → EXECUTING<br>- Check token validity<br>- Prepare bid amount = max_bid |
| **11:59:57.1** | **Attempt 1**: Place bid via eBay API (timeout: 300-600ms) |
| **11:59:57.4** | If Attempt 1 fails (timeout/error):<br>- Wait 100ms<br>- **Attempt 2** (if time allows) |
| **11:59:57.7** | If Attempt 2 fails:<br>- Wait 250ms<br>- **Attempt 3** (if time allows) |
| **11:59:58.2** | If Attempt 3 fails:<br>- Wait 500ms<br>- **Attempt 4** (final attempt, if time allows) |
| **11:59:59.7** | If time remaining < 300ms → Abort all retries, mark as FAILED |
| **12:00:00.0** | Auction ends (eBay stops accepting bids) |

---

## Key Design Decisions

1. **T-3 Seconds**: Gives enough time for retries (up to 4 attempts) while still being "last second"

2. **Atomic Status Transition**: Prevents duplicate bids even with multiple workers

3. **Time Window Check**: Aborts if less than 300ms remaining (prevents bidding after auction ends)

4. **Retry Strategy**: 
   - Fast retries (100ms, 250ms, 500ms delays)
   - Handles transient errors (timeouts, 5xx errors)
   - Aborts on non-retryable errors immediately

5. **Max Bid Amount**: Uses `max_bid` directly - eBay's proxy bidding handles incremental bidding automatically

6. **Fail-Open on Price Check**: If price check fails, proceeds to bid (better to try than skip)

7. **Worker Loop Frequency**: Checks every 500ms for precision (can catch the 1-second window reliably)

---

## Failure Scenarios

| Scenario | Outcome |
|----------|---------|
| Price > max_bid at T-60s | Status → `SKIPPED`, no bid placed |
| Auction already ended when bid executes | Status → `FAILED`, "Auction ended before bid could be placed" |
| All 4 bid attempts fail (timeouts/errors) | Status → `FAILED`, "All retry attempts exhausted" |
| Less than 300ms remaining during retry | Status → `FAILED`, "Ran out of time window for bid placement" |
| Network error, eBay API down | Retries up to 4 times, then FAILED |
| Invalid OAuth token | Refreshes token, retries |
| Bid amount below minimum | Status → `FAILED`, specific error message from eBay |

