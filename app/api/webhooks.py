"""
app/api/webhooks.py

Receives GitLab webhooks (Merge Request events and emoji reactions).
Responds immediately (200) then delegates the actual work
(fetch diff → AI analysis → save → comment) to a background task,
to avoid GitLab timing out the request.
"""

import os
import json
import logging
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks

from app.background.tasks import process_merge_request_event, process_emoji_event

logger = logging.getLogger("webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

GITLAB_SECRET_TOKEN = os.getenv("GITLAB_WEBHOOK_SECRET", "")

# Username of the account used by the bot to post comments/reactions.
# Must match the account behind GITLAB_TOKEN, so we can ignore emoji
# events the bot triggers on itself (e.g. posting its own menu reactions),
# which would otherwise cause an infinite loop of re-triggered analyses.
GITLAB_BOT_USERNAME = os.getenv("GITLAB_BOT_USERNAME", "")

# MR statuses we want to process (ignore close/merge, not relevant for analysis)
RELEVANT_ACTIONS = {"open", "update", "reopen"}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_gitlab_token: str = Header(default=None),
    x_gitlab_event: str = Header(default=None),
):
    # 1. Verify the secret configured in GitLab (Settings > Webhooks)
    if GITLAB_SECRET_TOKEN and x_gitlab_token != GITLAB_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    payload = await request.json()

    # DEBUG: Dump the payload to a file so we can see what GitLab actually sends
    with open("webhook_debug.json", "a") as f:
        f.write(json.dumps(payload) + "\n")

    # 2. Check if it's an Emoji click
    # This allows the AI to respond when a user clicks the interactive emoji menu
    if payload.get("object_kind") == "emoji":
        triggering_user = payload.get("user", {}).get("username")

        # Ignore emoji events the bot itself triggers (e.g. posting its own
        # welcome menu reactions) — only react to real user clicks.
        # Without this check, the bot's own reactions re-trigger new
        # analyses, which post new comments, which the bot reacts to
        # again, causing an infinite loop.
        if GITLAB_BOT_USERNAME and triggering_user == GITLAB_BOT_USERNAME:
            logger.info("Emoji event ignored: self-triggered by bot (%s)", triggering_user)
            return {"status": "ignored", "reason": "self-triggered emoji"}

        if payload.get("event_type") in ["award", "revoke"]:
            background_tasks.add_task(process_emoji_event, payload)
            return {"status": "accepted", "type": "emoji"}

        return {"status": "ignored", "reason": "unknown emoji event"}

    # 3. Check if it's a Merge Request event
    if x_gitlab_event != "Merge Request Hook":
        logger.info("Event ignored: %s", x_gitlab_event)
        return {"status": "ignored", "reason": "not a merge request or emoji event"}

    object_attrs = payload.get("object_attributes", {})
    action = object_attrs.get("action")  # open / update / close / merge / reopen

    if action not in RELEVANT_ACTIONS:
        logger.info("MR action ignored: %s", action)
        return {"status": "ignored", "reason": f"action '{action}' not relevant"}

    logger.info(
        "MR event received: project=%s mr_iid=%s action=%s",
        payload.get("project", {}).get("id"),
        object_attrs.get("iid"),
        action,
    )

    # 4. Respond immediately to GitLab (avoids the ~10s timeout)
    #    The actual processing (diff, AI, DB, comments) runs in the background.
    background_tasks.add_task(process_merge_request_event, payload)

    return {"status": "accepted"}
