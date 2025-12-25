"""
In-memory request coalescing for eBay API calls.
Prevents duplicate concurrent requests for the same listing.
"""
import threading
import time
from typing import Dict, Optional, Callable, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class RequestCoalescer:
    """
    Coalesces concurrent requests for the same resource.
    Only the first request executes; others wait for its result.
    """
    
    def __init__(self):
        # Maps key -> (result_or_none, exception_or_none, done_event)
        self._requests: Dict[str, Tuple[Optional[Any], Optional[Exception], threading.Event]] = {}
        self._lock = threading.Lock()  # Protects the _requests dict
    
    def get_or_execute(self, key: str, func: Callable[[], Any]) -> Any:
        """
        Execute func() if no concurrent request for key exists.
        Otherwise, wait for the concurrent request's result.
        
        Args:
            key: Unique identifier for the resource (e.g., listing_number)
            func: Callable that returns the result (will be called only once)
        
        Returns:
            Result from func()
        
        Raises:
            Exception: If func() raises, all waiting requests get the same exception
        """
        # Get or create request state for this key
        with self._lock:
            if key not in self._requests:
                # First request - create state
                done_event = threading.Event()
                self._requests[key] = (None, None, done_event)
                is_first = True
            else:
                # Subsequent request - wait for existing one
                _, _, done_event = self._requests[key]
                is_first = False
        
        if is_first:
            # First request: execute function
            try:
                result = func()
                with self._lock:
                    if key in self._requests:
                        _, _, evt = self._requests[key]
                        self._requests[key] = (result, None, evt)
                        evt.set()  # Signal waiting threads
                # Small delay to allow waiting threads to read result
                time.sleep(0.01)
                with self._lock:
                    self._requests.pop(key, None)
                return result
            except Exception as e:
                with self._lock:
                    if key in self._requests:
                        _, _, evt = self._requests[key]
                        self._requests[key] = (None, e, evt)
                        evt.set()  # Signal waiting threads
                # Small delay before cleanup
                time.sleep(0.01)
                with self._lock:
                    self._requests.pop(key, None)
                raise
        else:
            # Subsequent request: wait for first request to complete
            done_event.wait()
            
            with self._lock:
                if key not in self._requests:
                    # Cleaned up before we could read - fallback to executing ourselves
                    return func()
                
                result, error, _ = self._requests[key]
                if error is not None:
                    raise error
                if result is not None:
                    return result
            
            # Shouldn't reach here
            return func()
    
    def clear_key(self, key: str):
        """Clear cached result/error for a key (used after successful refresh)."""
        with self._lock:
            self._requests.pop(key, None)


# Global instance for request coalescing
_request_coalescer = RequestCoalescer()
