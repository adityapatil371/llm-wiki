import os
import base64
import time
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from google.api_core.exceptions import ServiceUnavailable, ResourceExhausted
from config import INGEST_MODEL, INGEST_MODEL_FALLBACK

load_dotenv()


def get_llm(use_fallback: bool = False):
    """Initialise Gemini with optional fallback model."""
    model = INGEST_MODEL_FALLBACK if use_fallback else INGEST_MODEL
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )


def invoke_with_fallback(message) -> str:
    """Try primary model first. On 503/429, wait and try fallback."""
    try:
        llm = get_llm(use_fallback=False)
        response = llm.invoke([message])
        return response.content
    except (ServiceUnavailable, ResourceExhausted) as e:
        print(f"Primary model unavailable ({e.__class__.__name__}). Waiting 5s then trying fallback...")
        time.sleep(5)

    try:
        llm = get_llm(use_fallback=True)
        response = llm.invoke([message])
        return response.content
    except (ServiceUnavailable, ResourceExhausted) as e:
        print(f"Fallback model also unavailable. Waiting 15s and retrying fallback...")
        time.sleep(15)
        llm = get_llm(use_fallback=True)
        response = llm.invoke([message])
        return response.content

def deterministic_checks(pages: dict[str, str]) -> list[str]:
    """
    Rule-based checks that don't need an LLM.
    Returns list of issues found.
    """
    issues = []
    
    for filename, content in pages.items():
        # Check for explicit "not provided" admissions
        not_provided_phrases = [
            "not provided in source",
            "not mentioned in source",
            "not available in source",
            "no information provided",
            "not specified in source"
        ]
        for phrase in not_provided_phrases:
            if phrase.lower() in content.lower():
                issues.append(
                    f"{filename}: contains '{phrase}' — agent lacked sufficient source material"
                )

        # Check required fields are present and not empty
        required_fields = [
            "**What it is:**",
            "**How it works:**",
            "**The 20%:**",
            "**Concrete example:**",
            "**Common mistake:**",
            "**Interview answer (30 seconds):**",
            "**Source:**"
        ]
        for field in required_fields:
            if field not in content:
                issues.append(f"{filename}: missing required field '{field}'")

        # Check page isn't suspiciously short
        if len(content) < 200:
            issues.append(f"{filename}: suspiciously short ({len(content)} chars) — likely incomplete")

    return issues

def critique_pages(pages, source_bytes, filename) -> dict:
    
    # Run deterministic checks first — no LLM needed
    deterministic_issues = deterministic_checks(pages)
    
    if deterministic_issues:
        return {
            "approved": False,
            "feedback": "VERDICT: REVISION NEEDED\n\nDETERMINISTIC ISSUES:\n" + 
                       "\n".join(f"- {issue}" for issue in deterministic_issues),
            "flagged_pages": list(pages.keys())
        }
    """Critic agent reviews ingested pages against the original source."""
    pages_text = ""
    for fname, content in pages.items():
        pages_text += f"\n\nPAGE: {fname}\n{content}"

    critique_prompt = f"""You are a critic reviewing wiki pages produced by an ingestion agent.

WIKI PAGES TO REVIEW:
{pages_text}

INSTRUCTIONS:
Check each page for:
1. Meaning inverted or lost under compression
2. Concrete examples NOT derivable from the source document
3. Common mistakes not grounded in the source
4. Important concepts the ingestion agent missed entirely

Respond in exactly this format:

VERDICT: APPROVED or REVISION NEEDED

FEEDBACK:
- Page: <filename>
  Issue: <specific issue or "None">
  Fix: <what needs to change or "N/A">

MISSED CONCEPTS:
- <concept name>: <why it matters>
(or "None" if nothing was missed)"""

    if filename.endswith(".pdf"):
        file_data = base64.standard_b64encode(source_bytes).decode("utf-8")
        message = HumanMessage(content=[
            {
                "type": "media",
                "mime_type": "application/pdf",
                "data": file_data
            },
            {
                "type": "text",
                "text": f"SOURCE DOCUMENT: {filename} (attached above)\n\n{critique_prompt}"
            }
        ])
    else:
        source_text = source_bytes.decode('utf-8', errors='ignore')
        message = HumanMessage(
            content=f"SOURCE DOCUMENT: {filename}\n{source_text}\n\n{critique_prompt}"
        )

    response_text = invoke_with_fallback(message)

    # Parse verdict
    approved = "VERDICT: APPROVED" in response_text

    # Parse flagged pages
    flagged_pages = []
    for fname in pages.keys():
        if fname in response_text:
            page_section = response_text[response_text.find(fname):]
            next_lines = page_section.split("\n")[:3]
            for line in next_lines:
                if "Issue:" in line and "None" not in line:
                    flagged_pages.append(fname)
                    break

    return {
        "approved": approved,
        "feedback": response_text,
        "flagged_pages": flagged_pages
    }


def add_warning_to_page(filepath: str, feedback: str):
    """Add a warning banner to a page that failed critic review."""
    path = Path(filepath)
    if not path.exists():
        return

    content = path.read_text()
    warning = f"""> ⚠️ **FLAGGED FOR REVIEW**
> This page was saved but not approved by the critic agent.
> Feedback: {feedback[:200]}...
> Please review and update manually.

"""
    path.write_text(warning + content)