
from typing import List
from pydantic import BaseModel, Field


class FindingResult(BaseModel):
    file_path: str = Field(description="The path of the file where the issue was found")
    line_number: int = Field(description="The exact line number of the added code where the issue is")
    severity: str = Field(description="One of: critical, error, warning, info")
    category: str = Field(description="One of: Security, Bugs, Code Quality, Performance")
    description: str = Field(description="A clear and concise explanation of the issue")
    suggestion: str = Field(description="Actionable suggestion on how to fix the issue")


class AnalysisResult(BaseModel):
    summary: str = Field(description="A high-level summary paragraph of the code changes, if requested by the prompt. Otherwise empty.", default="")
    findings: List[FindingResult] = Field(description="List of all issues found in the code", default_factory=list)
