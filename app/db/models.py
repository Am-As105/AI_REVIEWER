"""
SQLAlchemy ORM models for the MR Reviewer application.

Tables:
    - Project:        Tracked GitLab projects.
    - MergeRequest:   Merge requests received from GitLab webhooks.
    - Analysis:       AI analysis runs tied to a merge request.
    - Finding:        Individual code review findings within an analysis.
    - GitlabComment:  Comments posted back to GitLab for each finding.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class Project(Base):
    """Represents a GitLab project being monitored for code reviews."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    gitlab_project_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    path_with_namespace = Column(String(512), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    merge_requests = relationship(
        "MergeRequest", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}')>"


# ---------------------------------------------------------------------------
# Merge Request
# ---------------------------------------------------------------------------
class MergeRequest(Base):
    """Represents a GitLab merge request submitted for review."""

    __tablename__ = "merge_requests"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    gitlab_mr_iid = Column(Integer, nullable=False, index=True)
    title = Column(String(512), nullable=False)
    source_branch = Column(String(255), nullable=False)
    target_branch = Column(String(255), nullable=False)
    state = Column(String(50), nullable=False, default="opened")
    author = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    project = relationship("Project", back_populates="merge_requests")
    analyses = relationship(
        "Analysis", back_populates="merge_request", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MergeRequest(id={self.id}, iid={self.gitlab_mr_iid})>"


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
class Analysis(Base):
    """Tracks an AI analysis run for a specific merge request."""

    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    merge_request_id = Column(
        Integer,
        ForeignKey("merge_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        Enum(
            "pending",
            "in_progress",
            "completed",
            "failed",
            name="analysis_status",
        ),
        nullable=False,
        default="pending",
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    merge_request = relationship("MergeRequest", back_populates="analyses")
    findings = relationship(
        "Finding", back_populates="analysis", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Analysis(id={self.id}, status='{self.status}')>"


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------
class Finding(Base):
    """An individual code review finding produced by the AI analyzer."""

    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(
        Integer,
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path = Column(String(1024), nullable=False)
    line_number = Column(Integer, nullable=True)
    severity = Column(
        Enum("info", "warning", "error", "critical", name="finding_severity"),
        nullable=False,
        default="info",
    )
    category = Column(String(255), nullable=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    analysis = relationship("Analysis", back_populates="findings")
    gitlab_comment = relationship(
        "GitlabComment",
        back_populates="finding",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Finding(id={self.id}, severity='{self.severity}', title='{self.title}')>"


# ---------------------------------------------------------------------------
# GitLab Comment
# ---------------------------------------------------------------------------
class GitlabComment(Base):
    """Records a comment posted back to GitLab for a specific finding."""

    __tablename__ = "gitlab_comments"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(
        Integer,
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    gitlab_discussion_id = Column(String(255), nullable=True)
    gitlab_note_id = Column(Integer, nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    finding = relationship("Finding", back_populates="gitlab_comment")

    def __repr__(self) -> str:
        return f"<GitlabComment(id={self.id}, finding_id={self.finding_id})>"
