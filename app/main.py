"""
app/main.py

Entry point of the FastAPI application.
Starts the server, registers routers, and initializes the DB connection.
"""

import logging
from fastapi import FastAPI

from app.api import webhooks
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(
    title="MR Reviewer",
    description="AI system for automatic GitLab Merge Request review",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    # Creates tables if they don't exist yet (dev only).
    init_db()
    logging.getLogger("main").info("Database ready, server started.")


@app.get("/health")
def health_check():
    """Simple route to check the server is running (useful for the tunnel/CI)."""
    return {"status": "ok"}


# Registers the GitLab webhook route: POST /webhooks/gitlab
app.include_router(webhooks.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)