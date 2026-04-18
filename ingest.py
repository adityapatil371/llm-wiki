import os
import base64
import time
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from google.api_core.exceptions import ServiceUnavailable, ResourceExhausted
from db import init_db, hash_file, is_already_ingested, record_ingestion
from config import (
    INGEST_MODEL, INGEST_MODEL_FALLBACK,
    WIKI_DIR, WIKI_CONCEPTS_DIR, RAW_SOURCES_DIR
)

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


def read_wiki_context() -> str:
    """Read all existing wiki pages and return as a single string."""
    wiki_path = Path(WIKI_DIR)
    existing_pages = []

    for md_file in wiki_path.rglob("*.md"):
        content = md_file.read_text()
        existing_pages.append(f"=== {md_file.name} ===\n{content}")

    if not existing_pages:
        return "The wiki is currently empty."

    return "\n\n".join(existing_pages)


def update_wiki_index(new_pages: list[str]):
    """Append newly created pages to wiki/index.md."""
    index_path = Path("wiki/index.md")

    if not index_path.exists():
        index_path.write_text("# Wiki Index\n\n")

    existing = index_path.read_text()

    with open(index_path, "a") as f:
        for page in new_pages:
            page_name = Path(page).stem
            if f"[[{page_name}]]" not in existing:
                f.write(f"- [[{page_name}]]\n")


def save_wiki_pages(pages: dict[str, str]) -> list[str]:
    saved = []
    concepts_path = Path(WIKI_CONCEPTS_DIR)
    concepts_path.mkdir(parents=True, exist_ok=True)

    for filename, content in pages.items():
        # Skip index.md — that's managed separately
        if filename == "index.md":
            continue
        # Skip stub pages — too short to be useful
        if len(content) < 200:
            print(f"Skipping stub page: {filename} ({len(content)} chars)")
            continue
        filepath = concepts_path / filename
        filepath.write_text(content)
        saved.append(str(filepath))

    return saved


def parse_agent_response(response_text: str) -> dict[str, str]:
    """Parse FILE: blocks from agent response into {filename: content}."""
    pages = {}
    current_file = None
    current_content = []

    for line in response_text.split("\n"):
        if line.startswith("FILE:"):
            if current_file:
                pages[current_file] = "\n".join(current_content).strip()
            current_file = line.replace("FILE:", "").strip()
            current_content = []
        elif line.startswith("SUMMARY:"):
            break
        else:
            if current_file:
                current_content.append(line)

    if current_file and current_content:
        pages[current_file] = "\n".join(current_content).strip()

    return pages


def build_ingest_prompt(wiki_context: str, filename: str, text_content: str) -> str:
    """Build the ingestion prompt for text files."""
    return f"""You are ingesting a new source document into a personal ML engineering wiki.

EXISTING WIKI CONTEXT:
{wiki_context}

IMPORTANT RULES:
- Only create a page if the source document provides enough information
  to fill ALL required fields completely.
- Do NOT create stub pages for related concepts mentioned in passing.
- It is better to create one complete page than five incomplete ones.
- [[related_concept]] links are just references — do not create pages for them.
- Concrete examples must come directly from the source document, never invented.

INSTRUCTIONS:
Extract the core 20% of concepts from the source document.
For each concept you have COMPLETE information for, produce a wiki page in this exact format:

FILE: concept_name.md
# Concept Name
**What it is:** ...
**How it works:** ...
**The 20%:** ...
**Concrete example:** ...
**Common mistake:** ...
**Interview answer (30 seconds):** ...
**Source:** {filename}
**Related:** [[related_concept]]

Produce one FILE: block per concept. Use lowercase_with_underscores for filenames.
After all FILE: blocks, add a SUMMARY: section listing:
- Pages created
- Key concepts extracted
- Any contradictions with existing wiki content

SOURCE DOCUMENT:
{text_content}"""


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    """Main ingestion function."""
    init_db()

    # Step 1 — check if already ingested
    file_hash = hash_file(file_bytes)
    if is_already_ingested(filename, file_hash):
        return {
            "status": "skipped",
            "message": f"{filename} has already been ingested and hasn't changed."
        }

    # Step 2 — save to raw_sources
    raw_path = Path(RAW_SOURCES_DIR)
    raw_path.mkdir(exist_ok=True)
    (raw_path / filename).write_bytes(file_bytes)

    # Step 3 — read existing wiki for context
    wiki_context = read_wiki_context()

    # Step 4 — build message based on file type
    if filename.endswith(".pdf"):
        file_data = base64.standard_b64encode(file_bytes).decode("utf-8")
        message = HumanMessage(content=[
            {
                "type": "media",
                "mime_type": "application/pdf",
                "data": file_data
            },
            {
                "type": "text",
                "text": build_ingest_prompt(wiki_context, filename, "[See attached PDF]")
            }
        ])
    else:
        text_content = file_bytes.decode('utf-8', errors='ignore')
        message = HumanMessage(
            content=build_ingest_prompt(wiki_context, filename, text_content)
        )

    # Step 5 — call ingestion agent
    response_text = invoke_with_fallback(message)

    # DEBUG — remove after confirmed working
    print("=== AGENT RESPONSE (first 500 chars) ===")
    print(response_text[:500])
    print("=== END ===")

    # Step 6 — parse pages
    pages = parse_agent_response(response_text)

    if not pages:
        return {
            "status": "error",
            "message": "Agent produced no wiki pages. Check the response format.",
            "agent_response": response_text
        }

    # Step 7 — critic review loop
    from critic import critique_pages, add_warning_to_page

    max_attempts = 2
    attempt = 0
    critique_result = None

    while attempt < max_attempts:
        critique_result = critique_pages(pages, file_bytes, filename)

        if critique_result["approved"]:
            break

        attempt += 1
        if attempt < max_attempts:
            revision_prompt = f"""Your previous wiki pages were rejected by the critic.

CRITIC FEEDBACK:
{critique_result['feedback']}

Please revise the pages addressing all issues raised.
Use the same FILE: format as before.

ORIGINAL SOURCE:
{file_bytes.decode('utf-8', errors='ignore') if not filename.endswith('.pdf') else '[PDF source]'}
"""
            response_text = invoke_with_fallback(HumanMessage(content=revision_prompt))
            pages = parse_agent_response(response_text)

    # Step 8 — save pages
    saved_pages = save_wiki_pages(pages)
    update_wiki_index(list(pages.keys()))

    if critique_result and not critique_result["approved"]:
        for page_path in saved_pages:
            add_warning_to_page(page_path, critique_result["feedback"])

    # Step 9 — record in SQLite
    record_ingestion(filename, file_hash, saved_pages)

    return {
        "status": "success",
        "message": f"Ingested {filename} successfully.",
        "pages_created": saved_pages,
        "critic_approved": critique_result["approved"] if critique_result else True,
        "critic_feedback": critique_result["feedback"] if critique_result else None
    }