import os
import time
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from google.api_core.exceptions import ServiceUnavailable, ResourceExhausted
from config import INGEST_MODEL, INGEST_MODEL_FALLBACK, WIKI_DIR

load_dotenv()


def get_llm(use_fallback: bool = False):
    model = INGEST_MODEL_FALLBACK if use_fallback else INGEST_MODEL
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )


def invoke_with_fallback(message) -> str:
    try:
        llm = get_llm(use_fallback=False)
        response = llm.invoke([message])
        return response.content
    except (ServiceUnavailable, ResourceExhausted):
        print("Primary model unavailable. Trying fallback...")
        time.sleep(5)

    try:
        llm = get_llm(use_fallback=True)
        response = llm.invoke([message])
        return response.content
    except (ServiceUnavailable, ResourceExhausted):
        time.sleep(15)
        llm = get_llm(use_fallback=True)
        response = llm.invoke([message])
        return response.content


def deterministic_lint(wiki_dir: str = WIKI_DIR) -> list[str]:
    """
    Rule-based wiki health checks — no LLM needed.
    Returns list of issues found.
    """
    issues = []
    wiki_path = Path(wiki_dir)
    all_pages = list(wiki_path.rglob("*.md"))

    if not all_pages:
        return ["Wiki is empty — no pages found."]

    # collect all page names for link checking
    all_page_names = {p.stem for p in all_pages}

    # collect all wikilinks across all pages
    import re
    all_links = {}
    page_link_counts = {p.stem: 0 for p in all_pages}

    for page in all_pages:
        content = page.read_text()
        links = re.findall(r"\[\[(\w+)\]\]", content)
        all_links[page.stem] = links

        # count how many pages link TO this page
        for link in links:
            if link in page_link_counts:
                page_link_counts[link] += 1

    for page in all_pages:
        stem = page.stem
        content = page.read_text()

        # skip index page
        if stem == "index":
            continue

        # orphaned pages — no other page links to them
        if page_link_counts.get(stem, 0) == 0:
            issues.append(f"Orphaned: {stem}.md — no other pages link to it")

        # broken links — links to pages that don't exist
        for link in all_links.get(stem, []):
            if link not in all_page_names:
                issues.append(f"Broken link: {stem}.md links to [[{link}]] which doesn't exist")

        # missing required fields
        required_fields = [
            "**What it is:**",
            "**How it works:**",
            "**Concrete example:**",
            "**Source:**"
        ]
        for field in required_fields:
            if field not in content:
                issues.append(f"Missing field: {stem}.md is missing '{field}'")

        # suspiciously short
        if len(content) < 200:
            issues.append(f"Too short: {stem}.md ({len(content)} chars) — may be incomplete")

    return issues


def llm_lint(wiki_dir: str = WIKI_DIR) -> str:
    """
    LLM-based lint — finds semantic issues deterministic checks miss.
    Contradictions, vague explanations, outdated content signals.
    """
    wiki_path = Path(wiki_dir)
    pages = []

    for md_file in sorted(wiki_path.rglob("*.md")):
        if md_file.stem == "index":
            continue
        content = md_file.read_text()
        pages.append(f"=== {md_file.stem} ===\n{content}")

    if not pages:
        return "Wiki is empty."

    wiki_content = "\n\n".join(pages)

    prompt = f"""You are performing a health check on a personal ML engineering wiki.

WIKI CONTENT:
{wiki_content}

Check for:
1. Contradictions — two pages making conflicting claims about the same concept
2. Concepts referenced across multiple pages that don't have their own page yet
3. Pages where the explanation is too vague to be useful in an interview
4. Pages where the concrete example doesn't actually demonstrate the concept

Respond in this format:

CONTRADICTIONS:
- <page1> vs <page2>: <what conflicts>
(or "None found")

MISSING PAGES NEEDED:
- <concept>: referenced in <page> but has no page
(or "None found")

VAGUE EXPLANATIONS:
- <page>: <what's vague and why>
(or "None found")

WEAK EXAMPLES:
- <page>: <why the example is weak>
(or "None found")"""

    return invoke_with_fallback(HumanMessage(content=prompt))


def run_lint(wiki_dir: str = WIKI_DIR) -> dict:
    """
    Run full lint — both deterministic and LLM checks.
    Returns structured report for Streamlit UI.
    """
    deterministic_issues = deterministic_lint(wiki_dir)
    llm_report = llm_lint(wiki_dir)

    return {
        "status": "success",
        "deterministic_issues": deterministic_issues,
        "llm_report": llm_report,
        "total_issues": len(deterministic_issues)
    }