from .main import run_worker
import uvicorn
import logging
import threading
from database import init_db
from .api import app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def run_worker_thread():
    """Run the worker in a separate thread."""
    from .worker import Worker
    worker = Worker()
    worker.run_loop()


if __name__ == "__main__":
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Start worker in background thread
    worker_thread = threading.Thread(target=run_worker_thread, daemon=True)
    worker_thread.start()
    logger.info("Worker thread started")
    
    # Start API server
    uvicorn.run(app, host="0.0.0.0", port=8000)

