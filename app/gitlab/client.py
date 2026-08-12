import logging
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("gitlab_client")

GITLAB_URL = os.getenv("GITLAB_URL", "").rstrip("/")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "").strip()


async def get_current_user_id() -> int | None:
    # Fetches the ID of the authenticated user (the bot) to prevent infinite webhook loops
    url = f"{GITLAB_URL}/api/v4/user"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.json().get("id")
    except Exception:
        logger.exception("Failed to fetch bot user ID")
    return None


async def get_merge_request_diff(project_gitlab_id: int, mr_gitlab_iid: int) -> list[dict]:
    # Fetches modified file diffs for a given project and merge request IID from GitLab API
    url = f"{GITLAB_URL}/api/v4/projects/{project_gitlab_id}/merge_requests/{mr_gitlab_iid}/changes"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

        data = response.json()
        changes = data.get("changes", [])

        diffs = []
        for change in changes:
            diff = change.get("diff")
            if diff and isinstance(diff, str) and diff.strip():
                diffs.append({
                    "file_path": change.get("new_path") or change.get("old_path") or "unknown",
                    "diff": diff,
                })

        logger.info("Fetched %d valid diff(s) for MR %s in project %s", len(diffs), mr_gitlab_iid, project_gitlab_id)
        return diffs
    except Exception:
        logger.exception("Failed to fetch diffs for MR %s in project %s", mr_gitlab_iid, project_gitlab_id)
        return []


def format_review_comment(findings: list[dict], summary: str = "", review_type: str = "full") -> str:
    # Each analysis type gets its own unique title
    titles = {
        "summary": "📖 **Code Summary Report**",
        "bugs": "🐛 **Bugs & Errors Report**",
        "security": "🔍 **Security Vulnerabilities Report**",
        "full": "📋 **Full Code Review Report**",
    }
    title = titles.get(review_type, titles["full"])
    text = f"{title}\n\n"
    
    if summary:
        text += f"{summary}\n\n"
        
    if findings:
        text += "**Detailed Findings:**\n"
        for idx, f in enumerate(findings, 1):
            severity = str(f.get('severity', 'info')).upper()
            text += f"\n{idx}. **[{severity}]** `{f.get('file_path')}` (Line {f.get('line_number')})\n"
            text += f"   - {f.get('description')}\n"
            text += f"   - 💡 **Suggestion:** {f.get('suggestion')}\n"
    elif not summary:
        return "🎉 **Excellent!** The AI analyzed the code and found no issues."
        
    return text


async def post_comment(project_gitlab_id: int, mr_gitlab_iid: int, comment_text: str) -> int | None:
    # Posts an automated Markdown review comment to a GitLab Merge Request timeline
    url = f"{GITLAB_URL}/api/v4/projects/{project_gitlab_id}/merge_requests/{mr_gitlab_iid}/notes"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    payload = {"body": comment_text}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        comment_id = data.get("id")
        logger.info("Successfully posted review comment (ID: %s) to MR %s in project %s", comment_id, mr_gitlab_iid, project_gitlab_id)
        return comment_id
    except Exception:
        logger.exception("Failed to post review comment to MR %s in project %s", mr_gitlab_iid, project_gitlab_id)
        return None


async def update_comment(project_gitlab_id: int, mr_gitlab_iid: int, comment_id: int, comment_text: str) -> None:
    # Updates an existing Markdown review comment on a GitLab Merge Request
    url = f"{GITLAB_URL}/api/v4/projects/{project_gitlab_id}/merge_requests/{mr_gitlab_iid}/notes/{comment_id}"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    payload = {"body": comment_text}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(url, headers=headers, json=payload)
            response.raise_for_status()
        logger.info("Successfully updated comment (ID: %s) to MR %s in project %s", comment_id, mr_gitlab_iid, project_gitlab_id)
    except Exception:
        logger.exception("Failed to update comment %s on MR %s in project %s", comment_id, mr_gitlab_iid, project_gitlab_id)


async def post_interactive_menu(project_gitlab_id: int, mr_gitlab_iid: int) -> int | None:
    menu_text = "👋 Welcome! The AI Code Reviewer is ready. Click an emoji below to request a specific analysis:\n\n* 📖 - Full Summary\n* 🐛 - Bugs & Errors\n* 🔍 - Security Vulnerabilities"
    comment_id = await post_comment(project_gitlab_id, mr_gitlab_iid, menu_text)
    if comment_id:
        # Automatically add the emoji reactions so users can just click them
        await add_emoji_reaction(project_gitlab_id, mr_gitlab_iid, comment_id, "book")
        await add_emoji_reaction(project_gitlab_id, mr_gitlab_iid, comment_id, "bug")
        await add_emoji_reaction(project_gitlab_id, mr_gitlab_iid, comment_id, "mag")
    return comment_id


async def add_emoji_reaction(project_gitlab_id: int, mr_gitlab_iid: int, comment_id: int, emoji_name: str) -> None:
    url = f"{GITLAB_URL}/api/v4/projects/{project_gitlab_id}/merge_requests/{mr_gitlab_iid}/notes/{comment_id}/award_emoji"
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json={"name": emoji_name})
            response.raise_for_status()
    except Exception:
        logger.exception("Failed to add %s emoji to comment %s", emoji_name, comment_id)
