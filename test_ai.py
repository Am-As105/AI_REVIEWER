import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ai.analyzer import analyze_diff
from app.gitlab.client import format_review_comment

async def main():
    dummy_diffs = [
        {
            "file_path": "test.css",
            "diff": "@@ -1,2 +1,2 @@\n-:root\n+:root {"
        }
    ]
    
    print("--- Running SUMMARY analysis ---")
    res_summary = await analyze_diff(dummy_diffs, review_type="summary")
    print(f"Summary text: {res_summary.summary}")
    print(f"Findings count: {len(res_summary.findings)}")
    print(f"Formatted Comment:\n{format_review_comment(res_summary.findings, summary=res_summary.summary)}")
    
    print("\n--- Running BUGS analysis ---")
    res_bugs = await analyze_diff(dummy_diffs, review_type="bugs")
    print(f"Summary text: {res_bugs.summary}")
    print(f"Findings count: {len(res_bugs.findings)}")
    print(f"Formatted Comment:\n{format_review_comment(res_bugs.findings, summary=res_bugs.summary)}")

if __name__ == "__main__":
    asyncio.run(main())
