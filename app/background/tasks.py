"""
app/background/tasks.py

Orchestrates the background workflow triggered by a GitLab webhook:
1. Open a dedicated DB session (the request's session is already closed by now)
2. Extract project/MR info from the payload
3. Create/update the Project and MergeRequest rows
4. Create a new Analysis row (status "Pending")
5. Fetch the diff and run the AI analysis
6. Post the interactive menu and review comment back to GitLab
"""

import logging

from app.db.database import SessionLocal
from app.db import crud
from app.gitlab.client import get_merge_request_diff, format_review_comment, post_comment, post_interactive_menu, update_comment, get_current_user_id
from app.ai.analyzer import analyze_diff

logger = logging.getLogger("tasks")


async def process_merge_request_event(payload: dict) -> None:
    """
    Entry point called by webhooks.py via BackgroundTasks.
    Opens its own DB session since the request-scoped one is already closed.
    """
    db = SessionLocal()
    try:
        project_attrs = payload.get("project", {})
        mr_attrs = payload.get("object_attributes", {})

        project_gitlab_id = project_attrs.get("id")
        project_name = project_attrs.get("name", "Unknown Project")
        mr_gitlab_iid = mr_attrs.get("iid")
        mr_title = mr_attrs.get("title", "Untitled MR")
        mr_status = mr_attrs.get("state", "opened")

        if not project_gitlab_id or not mr_gitlab_iid:
            logger.error("Missing project_id or mr_iid in webhook payload")
            return

        logger.info("Processing MR %s in project %s", mr_gitlab_iid, project_gitlab_id)

        project = crud.get_or_create_project(
            db, project_gitlab_id=project_gitlab_id, project_name=project_name
        )
        crud.get_or_create_merge_request(
            db,
            project_id=project.project_id,
            merge_request_gitlab_iid=mr_gitlab_iid,
            merge_request_title=mr_title,
            merge_request_status=mr_status,
        )
        
        # --- ADDED BY AMINE & AI (AI-GitLab-Integration) ---
        # Post the interactive menu. We wait for the user to click an emoji before running the AI.
        await post_interactive_menu(project_gitlab_id, mr_gitlab_iid)
        # ---------------------------------------------------

    except Exception:
        logger.exception("Failed to process MR webhook event")
    finally:
        db.close()


# --- ADDED BY AMINE & AI (AI-GitLab-Integration) ---
# New function to handle emoji clicks and trigger specific AI modes
async def process_emoji_event(payload: dict) -> None:
    """
    Called when a user clicks an emoji in GitLab.
    Determines the analysis mode (summary, bugs, security) and triggers the AI.
    """
    db = SessionLocal()
    try:
        emoji_name = payload.get("object_attributes", {}).get("name")
        project_id = payload.get("project", {}).get("id")
        
        # Get MR IID. If the emoji was clicked on a note (comment), it's inside 'merge_request'
        mr_iid = payload.get("merge_request", {}).get("iid")
            
        if not project_id or not mr_iid or not emoji_name:
            logger.warning("Missing project_id, mr_iid, or emoji_name in emoji payload")
            return

        user_id = payload.get("user", {}).get("id")
        event_type = payload.get("event_type", "")  # "award" or "revoke"
        
        # Smart bot-detection:
        # - "award" from the bot itself = bot auto-placing emojis, IGNORE
        # - "revoke" = a human clicked an existing emoji (GitLab removes it), PROCESS
        if event_type == "award":
            bot_id = await get_current_user_id()
            if bot_id and user_id == bot_id:
                logger.info("Ignored automatic emoji placement by the bot (ID: %s)", bot_id)
                return

        # Map emoji to AI analysis type
        review_type = "full"
        if emoji_name == "book":
            review_type = "summary"
        elif emoji_name == "bug":
            review_type = "bugs"
        elif emoji_name == "mag":
            review_type = "security"
        else:
            logger.info("Ignored non-supported emoji click: %s", emoji_name)
            return

        logger.info("Emoji '%s' clicked on MR %s, running '%s' analysis", emoji_name, mr_iid, review_type)
        
        # Post temporary loading comment
        loading_text = f"⏳ **AI Code Reviewer is analyzing ({review_type})...** Please wait a moment."
        loading_comment_id = await post_comment(project_id, mr_iid, loading_text)
        
        diffs = await get_merge_request_diff(project_id, mr_iid)
        gitlab_comment_id = None
        
        if diffs:
            # Trigger the specific AI analysis mode
            ai_response = await analyze_diff(diffs, review_type=review_type)
            
            # Format the final report
            comment_text = format_review_comment(ai_response.findings, summary=ai_response.summary, review_type=review_type)
            
            # Update the loading comment with the final report
            if loading_comment_id:
                await update_comment(project_id, mr_iid, loading_comment_id, comment_text)
                gitlab_comment_id = loading_comment_id
            else:
                gitlab_comment_id = await post_comment(project_id, mr_iid, comment_text)
                
            logger.info("Successfully posted '%s' analysis to MR %s", review_type, mr_iid)
            
            # SAVE TO DATABASE
            # 1. Ensure project and MR exist
            project = crud.get_or_create_project(db, project_gitlab_id=project_id, project_name=f"Project {project_id}")
            mr = crud.get_or_create_merge_request(db, project_id=project.project_id, merge_request_gitlab_iid=mr_iid, merge_request_title=f"MR {mr_iid}", merge_request_status="opened")
            
            # 2. Create Analysis record
            analysis = crud.create_analysis(db, merge_request_id=mr.merge_request_id, analysis_status=f"Completed ({review_type})")
            crud.update_analysis_result(db, analysis.analysis_id, f"Completed ({review_type})", ai_response.raw_text)
            
            # 3. Create Findings and Link GitLab Comment
            if ai_response.findings:
                created_findings = crud.create_findings_bulk(db, analysis.analysis_id, ai_response.findings)
                if gitlab_comment_id:
                    for finding in created_findings:
                        crud.create_gitlab_comment(db, finding.finding_id, gitlab_comment_id)
        else:
            if loading_comment_id:
                await update_comment(project_id, mr_iid, loading_comment_id, "❌ **Analysis Failed:** No valid code changes found to analyze.")

    except Exception:
        logger.exception("Failed to process emoji event")
    finally:
        db.close()
# ---------------------------------------------------