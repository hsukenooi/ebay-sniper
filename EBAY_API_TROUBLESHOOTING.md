# eBay API Troubleshooting & Known Issues

This document anticipates common problems you might encounter when working with the eBay API for bid sniping and provides solutions.

## Critical Issues (Must Fix)

### 1. Trading API XML Format Issues ⚠️

**Problem**: The current `place_bid()` implementation uses a simplified XML structure that may not match eBay's exact requirements. eBay Trading API is extremely strict about XML format.

**Current Issues**:
- Missing `SiteID` parameter (required for Trading API)
- XML namespace may need adjustment
- Service version might be outdated (currently 1.0.0)
- No proper XML escaping for special characters in values

**Solution**:
```python
# Proper XML should include:
<PlaceOfferRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <ItemID>{listing_number}</ItemID>
    <Offer>
        <MaxBid>{bid_amount}</MaxBid>
        <Quantity>1</Quantity>
    </Offer>
    <SiteID>0</SiteID>  # 0 = US site, required!
</PlaceOfferRequest>
```

**Action Required**: Update `server/ebay_client.py` `place_bid()` method to include `SiteID` and verify XML format matches eBay docs exactly.

---

### 2. Refresh Token Expiration Not Handled

**Problem**: Refresh tokens can expire or be revoked (e.g., user changes password, revokes access, 18 months of inactivity). Currently, if refresh fails, we raise an exception, but we don't have a way to prompt the user to re-authenticate.

**Current Behavior**: 
- `refresh_user_token()` returns `False` on failure
- Worker raises `ValueValue` exception
- User must manually re-run `get_ebay_tokens.py`

**Solution Needed**: 
- Add detection for refresh token expiration (specific error codes)
- Log clear error message indicating user needs to re-authenticate
- Consider adding a CLI command to test/refresh tokens

**Error Codes to Watch For**:
- `invalid_grant`: Refresh token expired or revoked
- `invalid_client`: App credentials invalid

---

### 3. XML Response Parsing is Fragile

**Problem**: Current code checks for "Error" or "Ack" in response text, which is unreliable. eBay Trading API returns structured XML with specific error codes we should parse properly.

**Current Code**:
```python
if "Error" in response.text or "Ack" not in response.text:
    raise requests.exceptions.RequestException("Bid placement failed")
```

**Issues**:
- Doesn't extract specific error codes (e.g., `10736` = "Bid amount is below the minimum bid")
- Doesn't distinguish between recoverable and non-recoverable errors
- Response might be valid but contain warnings

**Solution**: Use `xml.etree.ElementTree` to properly parse XML responses:
```python
import xml.etree.ElementTree as ET

root = ET.fromstring(response.text)
ack = root.find('.//{urn:ebay:apis:eBLBaseComponents}Ack')
if ack is None or ack.text != 'Success':
    errors = root.findall('.//{urn:ebay:apis:eBLBaseComponents}Errors')
    for error in errors:
        code = error.find('.//{urn:ebay:apis:eBLBaseComponents}ErrorCode')
        message = error.find('.//{urn:ebay:apis:eBLBaseComponents}LongMessage')
        # Handle specific error codes
```

---

### 4. ✅ Bid Amount Strategy - FIXED

**Problem**: Initially implemented bid increment calculation, but this was incorrect. eBay uses **proxy bidding** - when you submit your maximum bid, eBay automatically bids incrementally on your behalf.

**Solution**: Use `max_bid` directly when placing bids. eBay's proxy bidding system will:
- Accept your maximum bid amount
- Automatically bid incrementally as needed to stay ahead of other bidders
- Only bid as much as necessary (up to your max_bid)
- Handle all bid increment rules automatically

**Implementation**: 
- Changed `worker.py` to use `auction.max_bid` directly instead of calculating `current_price + increment`
- eBay's `<MaxBid>` element in PlaceOffer API accepts your maximum bid amount
- eBay handles all increment logic server-side

**Note**: The `calculate_min_bid_increment()` method still exists in `ebay_client.py` for potential future use, but is not used for bid placement.

---

### 5. Trading API Endpoint May Be Incorrect

**Problem**: Current code uses `/ws/api.dll` endpoint. For OAuth 2.0 tokens, Trading API might need a different endpoint or headers.

**Current**:
```python
url = f"{self.base_url}/ws/api.dll"
```

**Issue**: OAuth 2.0 tokens might require different endpoint structure or additional headers compared to legacy auth tokens.

**Solution**: Verify endpoint is correct for OAuth 2.0. Some sources suggest it should be:
- Production: `https://api.ebay.com/ws/api.dll`
- Sandbox: `https://api.sandbox.ebay.com/ws/api.dll`

**Action Required**: Test in sandbox first to confirm endpoint works with OAuth tokens.

---

## Important Issues (Should Fix)

### 6. Currency Handling

**Problem**: Code assumes USD for all auctions. eBay supports multiple currencies (USD, EUR, GBP, etc.). Bid amounts must match auction currency.

**Current Issue**: No currency validation or conversion.

**Solution**: 
- Extract currency from Browse API response (already done in `_parse_browse_api_response`)
- Store currency in database
- Validate bid amount currency matches auction currency

---

### 7. Auction Type Validation Missing

**Problem**: System doesn't check if listing is actually an auction vs. Buy It Now. Trying to bid on Buy It Now items will fail.

**Error Code**: `10729` = "Invalid item. The item specified is not a valid item or cannot be found."

**Solution**: Check `listingType` from Browse API:
```python
listing_type = data.get("listingType", "")
if listing_type != "AUCTION":
    raise ValueError(f"Item {listing_number} is not an auction (type: {listing_type})")
```

---

### 8. Reserve Price Not Handled

**Problem**: If auction has a reserve price not met, bids below reserve won't count. System should warn user or handle this case.

**Solution**: Check `hasReservePrice` and `reservePrice` from Browse API response and store/validate accordingly.

---

### 9. Item Already Ended / Ended During Sniping

**Problem**: Auction might end between scheduling and execution. Current code checks timing but doesn't verify auction is still active.

**Solution**: 
- Re-check auction status before placing bid
- Handle error code `10729` (item not found/ended) gracefully
- Mark auction as `FAILED` with appropriate message

---

### 10. Rate Limiting - Retry-After Header Not Honored

**Problem**: When we get a 429 (rate limited), we retry with fixed delays but don't check `Retry-After` header from eBay.

**Current Code**:
```python
if "429" in error_str and attempt < max_attempts - 1:
    is_retryable = True
    time.sleep(delays[attempt])  # Fixed delay
```

**Solution**: Parse `Retry-After` header and wait accordingly:
```python
if response.status_code == 429:
    retry_after = response.headers.get('Retry-After')
    if retry_after:
        wait_time = int(retry_after)
        time.sleep(wait_time)
```

---

### 11. Token Expiration Race Condition

**Problem**: Token might expire between `_ensure_token_valid()` check and actual API call. Especially problematic for bid placement where timing is critical.

**Solution**: 
- Implement token refresh lock to prevent concurrent refreshes
- Re-check token validity right before API call if time has passed
- Consider shorter refresh window (e.g., 10 minutes instead of 5)

---

### 12. Missing Error Code Handling for Common eBay Errors

**Problem**: eBay Trading API returns specific error codes we should handle gracefully:

- `10736`: Bid amount is below the minimum bid
- `10729`: Invalid item / item not found / auction ended
- `10730`: Bid retraction is not allowed
- `10731`: Cannot bid on own item
- `10732`: Bid on behalf of another user is not allowed
- `10733`: Bidder blocked
- `10734`: Cannot bid - auction ended
- `10735`: Bid amount exceeds maximum bid

**Solution**: Parse XML errors and map to specific exceptions or error messages.

---

## Nice-to-Have Improvements

### 13. Item ID Format Variations

**Problem**: Some listings might use legacy IDs or different formats that Browse API doesn't handle well.

**Current**: Uses `getItemByLegacyId` as fallback, but implementation is `NotImplementedError`.

**Solution**: Complete the Trading API fallback implementation if Browse API fails.

---

### 14. Testing in Sandbox

**Problem**: Hard to test bid placement without actually bidding. eBay Sandbox exists but requires separate credentials and test items.

**Recommendation**: 
- Document how to set up sandbox testing
- Consider adding a "dry run" mode that validates bid without placing it
- Use mocks in tests (already done, but could be more comprehensive)

---

### 15. Concurrent Bid Attempts

**Problem**: If multiple auctions end at same time, worker might try to place bids concurrently. eBay might rate limit or reject simultaneous bids.

**Current**: Worker processes one auction at a time, so this is handled.

**Potential Issue**: If we parallelize in future, need to throttle bid placements.

---

### 16. Marketplace/Regional Restrictions

**Problem**: Currently hardcoded to `EBAY_US` marketplace. Items from other marketplaces might fail.

**Solution**: Extract marketplace from listing URL or Browse API response and use appropriate marketplace ID.

---

## Monitoring & Debugging

### 17. Logging Improvements Needed

**Current Issues**:
- XML responses logged as text (could be large)
- Token refresh failures might not be clearly logged
- No structured logging for eBay API calls

**Recommendation**: 
- Log request/response summaries instead of full XML
- Add correlation IDs for tracking bid attempts
- Log token expiration times for debugging

---

### 18. Error Metrics Missing

**Problem**: No way to track:
- Bid success/failure rates
- Token refresh success rates
- Most common error codes
- API latency

**Recommendation**: Add metrics/monitoring (e.g., Prometheus, or simple counters in database).

---

## Summary: Priority Actions

### ✅ COMPLETED (January 2025)

1. **✅ HIGH PRIORITY - COMPLETED**:
   - ✅ Fix XML format (add `SiteID`) - Added SiteID=0 for US marketplace
   - ✅ Implement proper XML response parsing - Added `_parse_trading_api_response()` with error code extraction
   - ✅ Add bid increment calculation - Added `calculate_min_bid_increment()` method
   - ✅ Handle refresh token expiration gracefully - Added specific error handling for `invalid_grant` and `invalid_client`

2. **✅ MEDIUM PRIORITY - COMPLETED**:
   - ✅ Currency validation - Already handled in database (currency field exists)
   - ✅ Validate auction type (auction vs Buy It Now) - Added validation in `_parse_browse_api_response()`
   - ✅ Handle common eBay error codes - Added error code mapping (10729, 10734, 10736, etc.)
   - ✅ Honor `Retry-After` header - Added `Retry-After` header parsing for rate limiting

### 🔄 REMAINING (Lower Priority)

3. **LOW PRIORITY**:
   - Complete Trading API fallback (`_get_item_via_trading_api`)
   - Add reserve price handling (check `hasReservePrice` and `reservePrice`)
   - Improve logging and metrics (structured logging, correlation IDs)
   - Add marketplace detection (dynamic marketplace ID based on listing)

