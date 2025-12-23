import uvicorn
import logging
import threading
import os
from dotenv import load_dotenv
from database import init_db
from server.api import app

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def run_worker_thread():
    """Run the worker in a separate thread."""
    from server.worker import Worker
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
    # Railway and other PaaS providers set PORT environment variable
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

