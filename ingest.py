import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from db import init_db, hash_file, is_already_ingested, record_ingestion
from config import INGEST_MODEL, WIKI_DIR, WIKI_CONCEPTS_DIR, RAW_SOURCES_DIR
import base64

load_dotenv()

def get_llm():
    """Initialise Gemini."""
    return ChatGoogleGenerativeAI(
        model=INGEST_MODEL,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )


def read_wiki_context() -> str:
    """
    Read all existing wiki pages and return as a single string.
    This gives the agent context about what's already in the wiki
    so it can integrate rather than duplicate.
    """
    wiki_path = Path(WIKI_DIR)
    existing_pages = []

    for md_file in wiki_path.rglob("*.md"):
        content = md_file.read_text()
        existing_pages.append(f"=== {md_file.name} ===\n{content}")

    if not existing_pages:
        return "The wiki is currently empty."

    return "\n\n".join(existing_pages)


def update_wiki_index(new_pages: list[str]):
    """
    Append newly created pages to wiki/index.md.
    Creates index.md if it doesn't exist.
    """
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
    """
    Save a dict of {filename: content} to wiki/concepts/.
    Returns list of filenames saved.
    """
    saved = []
    concepts_path = Path(WIKI_CONCEPTS_DIR)
    concepts_path.mkdir(parents=True, exist_ok=True)

    for filename, content in pages.items():
        filepath = concepts_path / filename
        filepath.write_text(content)
        saved.append(str(filepath))

    return saved


def parse_agent_response(response_text: str) -> dict[str, str]:
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
            # Stop capturing — everything after this is metadata
            break
        else:
            if current_file:
                current_content.append(line)

    if current_file and current_content:
        pages[current_file] = "\n".join(current_content).strip()

    return pages


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    """
    Main ingestion function.
    Returns a result dict with status and details.
    """
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
    llm = get_llm()

    if filename.endswith(".pdf"):
        # Pass PDF natively to Gemini as base64 attachment
        file_data = base64.standard_b64encode(file_bytes).decode("utf-8")
        message = HumanMessage(content=[
            {
                "type": "media",
                "mime_type": "application/pdf",
                "data": file_data
            },
            {
                "type": "text",
                "text": f"""You are ingesting a new source document into a personal ML engineering wiki.

    EXISTING WIKI CONTEXT:
    {wiki_context}

    INSTRUCTIONS:
    Follow the INGEST mode instructions from your schema exactly.
    Extract the core 20% of concepts from the source document above.
    For each concept, produce a wiki page in this exact format:

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
    - Any contradictions with existing wiki content"""
            }
        ])
    else:
        # Text files — decode and pass as string
        text_content = file_bytes.decode('utf-8', errors='ignore')
        message = HumanMessage(content=f"""You are ingesting a new source document into a personal ML engineering wiki.

    EXISTING WIKI CONTEXT:
    {wiki_context}

    INSTRUCTIONS:
    Follow the INGEST mode instructions from your schema exactly.
    Extract the core 20% of concepts from the source document.
    For each concept, produce a wiki page in this exact format:

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
    {text_content}""")

    # Step 5 — call ingestion agent
    response = llm.invoke([message])
    response_text = response.content

    # Step 6 — parse and save wiki pages
    pages = parse_agent_response(response_text)

    if not pages:
        return {
            "status": "error",
            "message": "Agent produced no wiki pages. Check the response format."
        }

    saved_pages = save_wiki_pages(pages)
    update_wiki_index(list(pages.keys()))

    # Step 7 — record in SQLite
    record_ingestion(filename, file_hash, saved_pages)

    return {
        "status": "success",
        "message": f"Ingested {filename} successfully.",
        "pages_created": saved_pages,
        "agent_response": response_text
    }