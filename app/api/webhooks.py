from fastapi import APIRouter

router = APIRouter()


@router.post("/webhook")
async def handle_webhook():
    return {"status": "ok"}
