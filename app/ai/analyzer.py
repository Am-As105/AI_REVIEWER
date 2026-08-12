"""
app/ai/analyzer.py

Orchestrates the AI-powered code analysis workflow using Google Gemini:
1. Formats incoming file diffs into structured evaluation prompts
2. Executes structured evaluation against Gemini model
3. Returns normalized findings and raw output for persistence
"""

import json
import logging
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from app.ai.prompts import FULL_REVIEW_PROMPT, BUGS_PROMPT, SECURITY_PROMPT, SUMMARY_PROMPT
from app.ai.output_schema import AnalysisResult

load_dotenv()

logger = logging.getLogger("ai_analyzer")

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    temperature=0.2,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

structured_llm = llm.with_structured_output(AnalysisResult)


class AIResponse:
    """Container holding both the raw JSON representation and structured findings list."""
    def __init__(self, raw_text: str, findings: list[dict], summary: str = ""):
        self.raw_text = raw_text
        self.findings = findings
        self.summary = summary


async def analyze_diff(diffs: list[dict], review_type: str = "full") -> AIResponse:
    """
    Analyzes code diffs using Gemini model and returns structured findings.
    Selects the prompt based on review_type ("full", "bugs", "security", "summary").
    """
    if not diffs:
        logger.warning("No diffs provided for analysis, returning empty result.")
        return AIResponse(raw_text="No diffs found", findings=[])

    # 1. Select the right prompt based on user's emoji choice
    if review_type == "summary":
        prompt_template = SUMMARY_PROMPT
    elif review_type == "bugs":
        prompt_template = BUGS_PROMPT
    elif review_type == "security":
        prompt_template = SECURITY_PROMPT
    else:
        prompt_template = FULL_REVIEW_PROMPT

    # 2. Prepare the diff text safely
    diff_text = ""
    for item in diffs:
        file_path = item.get("file_path", "unknown")
        diff_content = str(item.get("diff", "") or "")
        diff_text += f"\n--- File: {file_path} ---\n{diff_content}"

    formatted_prompt = prompt_template.format(code_diff=diff_text)

    # 3. Call AI safely
    try:
        logger.info("Sending %d file diff(s) to Gemini for analysis (type: %s)", len(diffs), review_type)
        result = await structured_llm.ainvoke(formatted_prompt)
        findings_list = [finding.model_dump() for finding in result.findings] if result and getattr(result, "findings", None) else []
        summary = getattr(result, "summary", "")
        raw_text = json.dumps({"summary": summary, "findings": findings_list}, indent=2)
        
        logger.info("Analysis completed successfully. Generated %d finding(s)", len(findings_list))
        return AIResponse(raw_text=raw_text, findings=findings_list, summary=summary)
    except Exception:
        logger.exception("Failed to execute AI analysis")
        return AIResponse(raw_text="Error during analysis execution", findings=[], summary="")
