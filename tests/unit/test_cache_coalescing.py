"""Tests for request coalescing to prevent duplicate eBay API calls."""
import threading
import time
from unittest.mock import Mock
from server.cache import RequestCoalescer


def test_concurrent_requests_coalesce():
    """Test that concurrent requests for same key execute function only once."""
    coalescer = RequestCoalescer()
    call_count = {'value': 0}
    lock = threading.Lock()
    
    def expensive_operation(key):
        with lock:
            call_count['value'] += 1
        time.sleep(0.1)  # Simulate API call
        return f'result-{key}'
    
    def make_request(key):
        return coalescer.get_or_execute(key, lambda: expensive_operation(key))
    
    # Make 5 concurrent requests for same key
    threads = []
    results = []
    for i in range(5):
        t = threading.Thread(target=lambda: results.append(make_request('same-key')))
        threads.append(t)
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Function should have been called only once
    assert call_count['value'] == 1, f"Expected 1 call but got {call_count['value']}"
    
    # All results should be the same
    assert len(set(results)) == 1, "All results should be identical"
    assert results[0] == 'result-same-key'


def test_different_keys_execute_separately():
    """Test that different keys execute independently."""
    coalescer = RequestCoalescer()
    call_count = {'value': 0}
    
    def operation(key):
        call_count['value'] += 1
        return f'result-{key}'
    
    result1 = coalescer.get_or_execute('key1', lambda: operation('key1'))
    result2 = coalescer.get_or_execute('key2', lambda: operation('key2'))
    
    assert call_count['value'] == 2
    assert result1 == 'result-key1'
    assert result2 == 'result-key2'


def test_error_propagates_to_all_waiters():
    """Test that if function raises, all waiting threads get the same error."""
    coalescer = RequestCoalescer()
    
    def failing_operation(key):
        raise ValueError(f"Error for {key}")
    
    errors = []
    def make_request(key):
        try:
            coalescer.get_or_execute(key, lambda: failing_operation(key))
        except ValueError as e:
            errors.append(str(e))
    
    # Make 3 concurrent requests
    threads = []
    for i in range(3):
        t = threading.Thread(target=lambda: make_request('error-key'))
        threads.append(t)
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # All should have received the error
    assert len(errors) == 3
    assert all(e == "Error for error-key" for e in errors)


def test_clear_key():
    """Test that clear_key removes cached state."""
    coalescer = RequestCoalescer()
    call_count = {'value': 0}
    
    def operation(key):
        call_count['value'] += 1
        return f'result-{key}'
    
    # First call
    result1 = coalescer.get_or_execute('test-key', lambda: operation('test-key'))
    assert call_count['value'] == 1
    
    # Clear key
    coalescer.clear_key('test-key')
    
    # Second call should execute again (not coalesced)
    result2 = coalescer.get_or_execute('test-key', lambda: operation('test-key'))
    assert call_count['value'] == 2
    assert result1 == result2 == 'result-test-key'

