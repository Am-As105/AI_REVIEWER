from fastapi import FastAPI
from app.api.webhooks import router as webhook_router

app = FastAPI()

app.include_router(webhook_router)
