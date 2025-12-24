# Codebase Cleanup Report

## Phase 0: Baseline Report

### How to Run

**Server:**
```bash
python -m server
# Or via Procfile: web: python -m server
```

**CLI:**
```bash
python -m cli <command>
# Or via entry point: sniper <command>
```

**Tests:**
```bash
pytest tests/ -v
```

**Linter/Typecheck:**
- No linter configured (Python, no mypy/ruff)
- Type hints present but not enforced

### Baseline Status

✅ **Python Version**: 3.14.2  
✅ **Pytest**: 9.0.2  
✅ **Test Suite**: 68 tests, all passing  
✅ **Imports**: All modules import successfully  
✅ **Entry Points**: Server and CLI start without errors

---

## Phase 1: Entry Point Map

### Server Entry Points

**Main Entry**: `server/__main__.py`
- Initializes database
- Starts worker thread (daemon)
- Starts FastAPI server via uvicorn

**API Routes** (`server/api.py`):
- `POST /auth` - Authentication
- `POST /sniper/add` - Add listing
- `GET /sniper/list` - List listings
- `GET /sniper/{id}/status` - Get listing status
- `DELETE /sniper/{id}` - Remove listing
- `GET /sniper/{id}/logs` - Get bid attempt logs

**Worker Loop** (`server/worker.py`):
- `Worker.run_loop()` - Main worker loop (runs every 500ms)
- `Worker._process_auction()` - Processes individual auctions
- `Worker._execute_bid()` - Executes bid placement

### CLI Entry Points

**Main Entry**: `cli/__main__.py` → `cli/main.py`
- Commands: `auth`, `add`, `list`, `status`, `remove`, `logs`

**Client** (`cli/client.py`):
- `SniperClient` - HTTP client for API communication

### Database

**Schema** (`database/models.py`):
- `Auction` table (with relationships)
- `BidAttempt` table (1:1 with Auction)

**Initialization** (`database/session.py`):
- `init_db()` - Creates tables
- `get_db()` - FastAPI dependency

---

## Phase 2: Orphan Candidates (with Evidence)

### 🔴 HIGH CONFIDENCE - Safe to Remove

#### 1. Unused Function: `save_timezone()` 
**File**: `cli/config.py:40`  
**Evidence**: 
- Defined but never called
- `get_timezone()` is used, but `save_timezone()` is imported but never invoked
- No CLI command sets timezone
**Risk**: **LOW** - Function is never called

#### 2. Unused Variable: `timeout` in `_execute_bid()`
**File**: `server/worker.py:124`  
**Evidence**:
- `timeout = random.uniform(*timeout_range)` is calculated
- Never passed to `place_bid()` (which has hardcoded `timeout=0.6`)
- `timeout_range` variable also unused
**Risk**: **LOW** - Variable is calculated but never used

#### 3. Unused Import: `random` module
**File**: `server/worker.py:123`  
**Evidence**:
- `import random` inside function (line 123)
- Only used for unused `timeout` variable
**Risk**: **LOW** - Only used for unused code

#### 4. Unused Method: `_get_item_via_trading_api()`
**File**: `server/ebay_client.py:292`  
**Evidence**:
- Never called anywhere
- Only raises `NotImplementedError`
- Comment says "placeholder"
**Risk**: **LOW** - Dead stub code

#### 5. Unused Return Field: `listing_type` in `_parse_browse_api_response()`
**File**: `server/ebay_client.py:259`  
**Evidence**:
- Returned in dict but never used by callers
- Only used for validation (raises error if not AUCTION)
- Not stored in database, not in API responses
**Risk**: **LOW** - Returned but never consumed

#### 6. Unused Legacy Attribute: `oauth_token`
**File**: `server/ebay_client.py:33, 42-45`  
**Evidence**:
- Set in `set_oauth_token()` but never read
- Replaced by `oauth_app_token` and `oauth_user_token`
- Only used in test: `test_set_oauth_token()`
**Risk**: **MEDIUM** - Legacy compatibility, but not used in production

#### 7. Unused Attribute: `dev_id`
**File**: `server/ebay_client.py:24`  
**Evidence**:
- Set from `EBAY_DEV_ID` env var
- Never used in any API calls
- Only checked in test: `test_ebay_client_init()`
**Risk**: **LOW** - eBay API doesn't require Dev ID for OAuth 2.0

#### 8. Unused Method: `calculate_min_bid_increment()`
**File**: `server/ebay_client.py:263`  
**Evidence**:
- Static method, only used in tests
- Not called in production code (worker uses `max_bid` directly)
- Documented as "for potential future use"
**Risk**: **LOW** - Only test usage

### 🟡 MEDIUM CONFIDENCE - Review Before Removing

#### 9. Unused Database Columns: `created_at`, `updated_at`
**File**: `database/models.py:38-39`  
**Evidence**:
- Defined with defaults but never read/queried
- Not in API responses (`AuctionResponse` model)
- Not used in any business logic
**Risk**: **MEDIUM** - Database columns, might be used for debugging/auditing

#### 10. Legacy Method: `set_oauth_token()`
**File**: `server/ebay_client.py:42`  
**Evidence**:
- Marked as "legacy method" in docstring
- Only used in test: `test_set_oauth_token()`
- Sets `oauth_token` (unused) and `oauth_app_token_expires_at`
**Risk**: **MEDIUM** - Legacy compatibility, but docstring says use alternatives

### 🟢 LOW CONFIDENCE - Keep (Used or Potentially Useful)

#### 11. Unused Import: `save_timezone` in `cli/main.py`
**File**: `cli/main.py:6`  
**Evidence**:
- Imported but never called
- Function exists but no CLI command uses it
**Risk**: **LOW** - Import cleanup only

#### 12. Unused Import: `timedelta` in `cli/main.py`
**File**: `cli/main.py:4`  
**Evidence**:
- Imported but only used in `server/worker.py` context
- Actually used in `list()` command for date calculations
**Risk**: **NONE** - Actually used

---

## Phase 3: Cleanup Plan

### Step 1: Remove Unused Imports (Safest)
- Remove `save_timezone` import from `cli/main.py`
- Remove `random` import from `server/worker.py` (and unused timeout code)

### Step 2: Remove Unused Functions/Methods
- Remove `save_timezone()` from `cli/config.py`
- Remove `_get_item_via_trading_api()` stub from `server/ebay_client.py`
- Remove `calculate_min_bid_increment()` from `server/ebay_client.py` (or keep with deprecation comment)

### Step 3: Remove Unused Variables/Attributes
- Remove `timeout` and `timeout_range` from `server/worker.py`
- Remove `oauth_token` legacy attribute (or deprecate)
- Remove `dev_id` attribute (or verify eBay API doesn't need it)

### Step 4: Remove Unused Return Fields
- Remove `listing_type` from `_parse_browse_api_response()` return dict

### Step 5: Database Cleanup (Last - Requires Migration)
- Consider removing `created_at`, `updated_at` if truly unused
- **SKIP for now** - requires migration, low priority

---

## Phase 4: Verification Checklist

After cleanup:
- [x] All tests pass (68 tests, all passing)
- [x] Server starts without errors (imports work)
- [x] CLI commands work (imports work)
- [x] Worker loop starts (imports work)
- [x] API endpoints respond (app loads)
- [x] No import errors

---

## Phase 5: Cleanup Summary

### ✅ Removed (Safe Deletions)

1. **`save_timezone()` function** (`cli/config.py`)
   - Never called, only imported but unused
   - Removed function definition

2. **`save_timezone` import** (`cli/main.py`)
   - Unused import removed

3. **`_get_item_via_trading_api()` method** (`server/ebay_client.py`)
   - Dead stub code, never called, only raises NotImplementedError
   - Removed entire method

4. **`listing_type` return field** (`server/ebay_client.py`)
   - Returned but never consumed by callers
   - Removed from return dict (validation still happens)

5. **Unused `timeout` variable** (`server/worker.py`)
   - Calculated but never used (place_bid has hardcoded timeout)
   - Removed calculation and `timeout_range` variable

6. **`random` import** (`server/worker.py`)
   - Only used for unused timeout variable
   - Removed import

7. **Test assertion for `listing_type`** (`tests/unit/test_ebay_client.py`)
   - Updated test to not check removed field

### 📝 Deprecated (Kept with Comments)

1. **`oauth_token` attribute** (`server/ebay_client.py`)
   - Legacy attribute, set but never read in production
   - Added deprecation comment, kept for test compatibility

2. **`set_oauth_token()` method** (`server/ebay_client.py`)
   - Legacy method, only used in tests
   - Enhanced deprecation docstring, kept for backwards compatibility

3. **`dev_id` attribute** (`server/ebay_client.py`)
   - Not required for OAuth 2.0, never used
   - Added comment explaining it's for backwards compatibility

4. **`calculate_min_bid_increment()` method** (`server/ebay_client.py`)
   - Only used in tests, not in production code
   - Added note that it's unused but kept for potential future use

### ⚠️ Not Removed (Requires Migration or Higher Risk)

1. **`created_at`, `updated_at` database columns** (`database/models.py`)
   - Defined but never read/queried
   - **SKIPPED**: Database columns, removing requires migration
   - Low priority, not causing harm

### 📊 Cleanup Statistics

- **Functions removed**: 2 (`save_timezone`, `_get_item_via_trading_api`)
- **Imports removed**: 2 (`save_timezone`, `random`)
- **Variables removed**: 2 (`timeout`, `timeout_range`)
- **Return fields removed**: 1 (`listing_type`)
- **Methods deprecated**: 2 (`set_oauth_token`, `calculate_min_bid_increment`)
- **Attributes deprecated**: 2 (`oauth_token`, `dev_id`)
- **Tests updated**: 1 (removed `listing_type` assertion)

### ✅ Verification Results

- **All 68 tests pass** ✓
- **All imports work** ✓
- **Server API loads** ✓
- **Worker loads** ✓
- **CLI loads** ✓
- **No breaking changes** ✓

### 🎯 Impact

- **Code reduction**: ~30 lines removed
- **Complexity reduction**: Removed dead code paths
- **Maintainability**: Clearer codebase with deprecated items marked
- **Risk**: **LOW** - Only removed clearly unused code, kept tested items

