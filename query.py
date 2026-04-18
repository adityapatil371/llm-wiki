import os
import time
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from google.api_core.exceptions import ServiceUnavailable, ResourceExhausted
from config import QUERY_MODEL, INGEST_MODEL_FALLBACK, WIKI_DIR

load_dotenv()


def load_wiki() -> str:
    """Load all wiki pages into a single string."""
    wiki_path = Path(WIKI_DIR)
    pages = []

    for md_file in sorted(wiki_path.rglob("*.md")):
        content = md_file.read_text()
        pages.append(f"=== {md_file.stem} ===\n{content}")

    if not pages:
        return None

    return "\n\n".join(pages)


def query_wiki(question: str) -> dict:
    """
    Answer a question using the wiki as context.
    Uses Groq for speed — fast interactive responses.
    Falls back to Gemini if Groq fails.
    """
    wiki_content = load_wiki()

    if not wiki_content:
        return {
            "status": "error",
            "message": "Your wiki is empty. Add some sources first."
        }

    prompt = f"""You are answering questions from a personal ML engineering knowledge base.

RULES:
- Answer ONLY from the wiki content provided below
- Cite which concept pages you drew from at the end
- If the answer is not in the wiki, say exactly:
  "This concept is not in your wiki yet. Consider adding a source about [topic]."
- Never draw from general training knowledge
- Be concise — this is a personal reference tool, not a tutorial

WIKI CONTENT:
{wiki_content}

QUESTION: {question}"""

    # try Groq first — faster for interactive queries
    try:
        llm = ChatGroq(
            model=QUERY_MODEL,
            api_key=os.getenv("GROQ_API_KEY")
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return {
            "status": "success",
            "answer": response.content,
            "model_used": QUERY_MODEL
        }

    except Exception as e:
        print(f"Groq failed ({e.__class__.__name__}), falling back to Gemini...")
        time.sleep(3)

    # fallback to Gemini
    try:
        llm = ChatGoogleGenerativeAI(
            model=INGEST_MODEL_FALLBACK,
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return {
            "status": "success",
            "answer": response.content,
            "model_used": INGEST_MODEL_FALLBACK
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Both models failed: {str(e)}"
        }