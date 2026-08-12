"""
app/db/crud.py

CRUD helper functions for the MR Reviewer database models.
Each function takes an active SQLAlchemy Session (from get_db() or a
background-task-local SessionLocal()) and performs one clear operation.
"""

from sqlalchemy.orm import Session

from app.db import models


# --------------------------------------------------------------------------
# Project
# --------------------------------------------------------------------------

def get_project_by_gitlab_id(db: Session, project_gitlab_id: int) -> models.Project | None:
    """Fetch a project by its GitLab project ID, or None if it doesn't exist yet."""
    return (
        db.query(models.Project)
        .filter(models.Project.project_gitlab_id == project_gitlab_id)
        .first()
    )


def create_project(db: Session, project_gitlab_id: int, project_name: str) -> models.Project:
    """Create and persist a new project row."""
    project = models.Project(
        project_gitlab_id=project_gitlab_id,
        project_name=project_name,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_or_create_project(db: Session, project_gitlab_id: int, project_name: str) -> models.Project:
    """Return the existing project for this GitLab ID, or create it if missing."""
    project = get_project_by_gitlab_id(db, project_gitlab_id)
    if project:
        return project
    return create_project(db, project_gitlab_id, project_name)


# --------------------------------------------------------------------------
# MergeRequest
# --------------------------------------------------------------------------

def get_merge_request_by_gitlab_iid(
    db: Session, project_id: int, merge_request_gitlab_iid: int
) -> models.MergeRequest | None:
    """Fetch a merge request by its GitLab iid, scoped to one project."""
    return (
        db.query(models.MergeRequest)
        .filter(
            models.MergeRequest.merge_request_project_id == project_id,
            models.MergeRequest.merge_request_gitlab_iid == merge_request_gitlab_iid,
        )
        .first()
    )


def create_merge_request(
    db: Session,
    project_id: int,
    merge_request_gitlab_iid: int,
    merge_request_title: str,
    merge_request_status: str,
) -> models.MergeRequest:
    """Create and persist a new merge request row."""
    merge_request = models.MergeRequest(
        merge_request_project_id=project_id,
        merge_request_gitlab_iid=merge_request_gitlab_iid,
        merge_request_title=merge_request_title,
        merge_request_status=merge_request_status,
    )
    db.add(merge_request)
    db.commit()
    db.refresh(merge_request)
    return merge_request


def get_or_create_merge_request(
    db: Session,
    project_id: int,
    merge_request_gitlab_iid: int,
    merge_request_title: str,
    merge_request_status: str,
) -> models.MergeRequest:
    """Return the existing MR for this project+iid, or create it if missing."""
    merge_request = get_merge_request_by_gitlab_iid(db, project_id, merge_request_gitlab_iid)
    if merge_request:
        # Keep title/status up to date on repeated webhook events (e.g. "update" action)
        merge_request.merge_request_title = merge_request_title
        merge_request.merge_request_status = merge_request_status
        db.commit()
        db.refresh(merge_request)
        return merge_request
    return create_merge_request(
        db, project_id, merge_request_gitlab_iid, merge_request_title, merge_request_status
    )


def update_merge_request_status(
    db: Session, merge_request_id: int, status: str
) -> models.MergeRequest | None:
    """Update just the status field of an existing merge request."""
    merge_request = (
        db.query(models.MergeRequest)
        .filter(models.MergeRequest.merge_request_id == merge_request_id)
        .first()
    )
    if merge_request is None:
        return None
    merge_request.merge_request_status = status
    db.commit()
    db.refresh(merge_request)
    return merge_request


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def create_analysis(
    db: Session, merge_request_id: int, analysis_status: str = "Pending"
) -> models.Analysis:
    """Create a new analysis row (called when we start processing an MR event)."""
    analysis = models.Analysis(
        analysis_merge_request_id=merge_request_id,
        analysis_status=analysis_status,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def update_analysis_status(db: Session, analysis_id: int, status: str) -> models.Analysis | None:
    """Update just the status field of an analysis (e.g. Pending -> Processing)."""
    analysis = (
        db.query(models.Analysis)
        .filter(models.Analysis.analysis_id == analysis_id)
        .first()
    )
    if analysis is None:
        return None
    analysis.analysis_status = status
    db.commit()
    db.refresh(analysis)
    return analysis


def update_analysis_result(
    db: Session, analysis_id: int, status: str, raw_llm_response: str
) -> models.Analysis | None:
    """Store the AI's raw response and update the analysis status (e.g. Completed/Failed)."""
    analysis = (
        db.query(models.Analysis)
        .filter(models.Analysis.analysis_id == analysis_id)
        .first()
    )
    if analysis is None:
        return None
    analysis.analysis_status = status
    analysis.analysis_raw_llm_response = raw_llm_response
    db.commit()
    db.refresh(analysis)
    return analysis


def get_analysis(db: Session, analysis_id: int) -> models.Analysis | None:
    """Fetch a single analysis by id."""
    return (
        db.query(models.Analysis)
        .filter(models.Analysis.analysis_id == analysis_id)
        .first()
    )


# --------------------------------------------------------------------------
# Finding
# --------------------------------------------------------------------------

def create_finding(
    db: Session,
    analysis_id: int,
    file_path: str,
    line_number: int,
    severity: str,
    description: str,
) -> models.Finding:
    """Create a single finding (one bug/issue detected by the AI) for an analysis."""
    finding = models.Finding(
        finding_analysis_id=analysis_id,
        finding_file_path=file_path,
        finding_line_number=line_number,
        finding_severity=severity,
        finding_description=description,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


def create_findings_bulk(db: Session, analysis_id: int, findings: list[dict]) -> list[models.Finding]:
    """
    Create multiple findings at once from a list of dicts, e.g.:
    [{"file_path": ..., "line_number": ..., "severity": ..., "description": ...}, ...]
    Useful right after parsing the AI's JSON output.
    """
    created = []
    for f in findings:
        created.append(
            create_finding(
                db,
                analysis_id=analysis_id,
                file_path=f["file_path"],
                line_number=f.get("line_number"),
                severity=f.get("severity"),
                description=f.get("description"),
            )
        )
    return created


def get_findings_for_analysis(db: Session, analysis_id: int) -> list[models.Finding]:
    """Return all findings linked to a given analysis."""
    return (
        db.query(models.Finding)
        .filter(models.Finding.finding_analysis_id == analysis_id)
        .all()
    )


# --------------------------------------------------------------------------
# GitlabComment
# --------------------------------------------------------------------------

def create_gitlab_comment(
    db: Session, finding_id: int, gitlab_comment_gitlab_id: int
) -> models.GitlabComment:
    """
    Record that a finding was posted as a comment on GitLab.
    gitlab_comment_gitlab_id is the ID returned by the GitLab API after posting.
    """
    comment = models.GitlabComment(
        gitlab_comment_finding_id=finding_id,
        gitlab_comment_gitlab_id=gitlab_comment_gitlab_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def mark_comment_resolved(db: Session, gitlab_comment_id: int) -> models.GitlabComment | None:
    """Mark a posted comment as resolved (e.g. once the dev fixed the issue)."""
    comment = (
        db.query(models.GitlabComment)
        .filter(models.GitlabComment.gitlab_comment_id == gitlab_comment_id)
        .first()
    )
    if comment is None:
        return None
    comment.gitlab_comment_resolved = True
    db.commit()
    db.refresh(comment)
    return comment
