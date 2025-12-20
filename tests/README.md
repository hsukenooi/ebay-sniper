# Tests

This directory contains unit and integration tests for the eBay sniper system.

## Structure

- `conftest.py`: Shared pytest fixtures
- `unit/`: Unit tests for individual components
  - `test_models.py`: Database model tests
  - `test_api.py`: API endpoint tests
  - `test_worker.py`: Worker logic tests
  - `test_ebay_client.py`: eBay client tests (mocked)
- `integration/`: Integration tests for end-to-end workflows
  - `test_workflow.py`: Complete workflow tests

## Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=. --cov-report=html
```

Run specific test file:
```bash
pytest tests/unit/test_api.py
```

Run specific test:
```bash
pytest tests/unit/test_api.py::test_auth_endpoint
```

Run integration tests only:
```bash
pytest tests/integration/
```

Run unit tests only:
```bash
pytest tests/unit/
```

## Test Coverage

The tests cover:
- Database models and relationships
- API endpoints (authentication, CRUD operations)
- Worker bid execution logic
- eBay client interactions (mocked)
- End-to-end workflows (add, list, cancel, bid execution)
- Idempotency and error handling
- Price refresh logic
- State transitions

