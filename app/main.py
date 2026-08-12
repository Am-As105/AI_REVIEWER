"""
app/main.py

Entry point of the FastAPI application.
Starts the server, registers routers, and initializes the DB connection.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api import webhooks
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger("main")

# Validate required environment variables at startup
REQUIRED_ENV_VARS = ["GITLAB_URL", "GITLAB_TOKEN", "GOOGLE_API_KEY", "DATABASE_URL"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI lifespan handler (replaces deprecated on_event)."""
    # Startup
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    init_db()
    logger.info("Database ready, server started.")
    yield
    # Shutdown
    logger.info("Server shutting down.")


app = FastAPI(
    title="MR Reviewer",
    description="AI system for automatic GitLab Merge Request review",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    """Simple route to check the server is running (useful for the tunnel/CI)."""
    return {"status": "ok"}


# Registers the GitLab webhook route: POST /webhooks/gitlab
app.include_router(webhooks.router)


if __name__ == "__main__":
    import uvicorn

    debug = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=debug)