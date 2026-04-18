import os
import re
import time
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

load_dotenv()


def get_groq():
    return ChatGroq(
        model=os.getenv("QUERY_MODEL", "llama-3.1-8b-instant"),
        api_key=os.getenv("GROQ_API_KEY")
    )


def find_docs_url(tool_name: str) -> dict:
    """
    Use Groq to find the official documentation URL for a tool.
    Returns {"url": str, "description": str}
    """
    llm = get_groq()
    prompt = f"""Find the official documentation URL for: {tool_name}

Respond in exactly this format and nothing else:
URL: <the official docs URL>
DESCRIPTION: <one sentence describing what this tool does>

Rules:
- URL must be the official documentation site, not a tutorial or blog
- If you are not confident, say URL: UNKNOWN
- No markdown, no extra text"""

    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content.strip()

    url = None
    description = None

    for line in text.split("\n"):
        if line.startswith("URL:"):
            url = line.replace("URL:", "").strip()
        if line.startswith("DESCRIPTION:"):
            description = line.replace("DESCRIPTION:", "").strip()

    if not url or url == "UNKNOWN":
        return {"url": None, "description": None, "error": f"Could not find docs for {tool_name}"}

    return {"url": url, "description": description}


def fetch_url_content(url: str) -> dict:
    """
    Fetch text content from a URL.
    Detects YouTube URLs and routes to transcript fetcher.
    Returns {"content": str, "filename": str, "type": str}
    """
    if "youtube.com" in url or "youtu.be" in url:
        return fetch_youtube_transcript(url)

    return fetch_webpage_text(url)


def fetch_youtube_transcript(url: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "transcript")
        
        result = subprocess.run([
            "yt-dlp",
            "--write-auto-sub",
            "--sub-format", "ttml",
            "--convert-subs", "srt",
            "--skip-download",
            "--no-playlist",
            "-o", output_template,
            url
        ], capture_output=True, text=True)

        if result.returncode != 0:
            return {
                "content": None,
                "error": f"yt-dlp failed: {result.stderr[:200]}"
            }

        srt_files = list(Path(tmpdir).glob("*.srt"))
        if not srt_files:
            return {"content": None, "error": "No transcript found for this video"}

        raw_srt = srt_files[0].read_text(encoding="utf-8", errors="ignore")

        clean_lines = []
        for line in raw_srt.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.isdigit():
                continue
            if "-->" in line:
                continue
            line = re.sub(r"<[^>]+>", "", line)
            if line:
                clean_lines.append(line)

        content = " ".join(clean_lines)

        video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else "youtube"
        filename = f"yt_{video_id}.txt"

        title_match = re.search(r'\[download\] Destination: (.+?)\.', result.stdout)
        if title_match:
            raw_title = Path(title_match.group(1)).name
            filename = re.sub(r'[^\w\s-]', '', raw_title).strip().replace(' ', '_')[:50] + ".txt"

        return {
            "content": content,
            "filename": filename,
            "type": "youtube_transcript"
        }


def fetch_webpage_text(url: str) -> dict:
    try:
        import urllib.request
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.skip_tags = {"script", "style", "nav", "footer", "head"}
                self.current_skip = False
                self.skip_depth = 0

            def handle_starttag(self, tag, attrs):
                if tag in self.skip_tags:
                    self.current_skip = True
                    self.skip_depth += 1

            def handle_endtag(self, tag):
                if tag in self.skip_tags and self.current_skip:
                    self.skip_depth -= 1
                    if self.skip_depth == 0:
                        self.current_skip = False

            def handle_data(self, data):
                if not self.current_skip:
                    text = data.strip()
                    if text:
                        self.text_parts.append(text)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LLMWiki/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="ignore")

        parser = TextExtractor()
        parser.feed(html)
        content = "\n".join(parser.text_parts)

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            raw_title = title_match.group(1).strip()
            raw_title = re.split(r"[—\-\|]", raw_title)[0].strip()
            filename = re.sub(r"[^\w\s]", "", raw_title).strip().replace(" ", "_").lower() + ".txt"
        else:
            clean_url = url.rstrip("/").split("?")[0]
            parts = clean_url.split("/")
            filename = "_".join(p for p in parts[-2:] if p) + ".txt"
            filename = re.sub(r"[^\w_.-]", "", filename)

        return {
            "content": content,
            "filename": filename or "webpage.txt",
            "type": "webpage"
        }

    except Exception as e:
        return {"content": None, "error": str(e)}


def fetch_and_save(url: str, raw_sources_dir: str = "raw_sources") -> dict:
    """
    Main function — fetch content from URL and save to raw_sources/.
    Returns result dict for Streamlit to display.
    """
    Path(raw_sources_dir).mkdir(exist_ok=True)

    result = fetch_url_content(url)

    if not result.get("content"):
        return {
            "status": "error",
            "message": result.get("error", "Failed to fetch content")
        }

    filepath = Path(raw_sources_dir) / result["filename"]
    filepath.write_text(result["content"], encoding="utf-8")

    return {
        "status": "success",
        "filename": result["filename"],
        "filepath": str(filepath),
        "type": result["type"],
        "preview": result["content"][:300] + "..."
    }


def search_and_fetch_docs(tool_name: str, raw_sources_dir: str = "raw_sources") -> dict:
    """
    Find official docs URL for a tool name, then fetch and save it.
    """
    url_result = find_docs_url(tool_name)

    if not url_result.get("url"):
        return {
            "status": "error",
            "message": url_result.get("error", f"Could not find docs for {tool_name}")
        }

    url = url_result["url"]
    fetch_result = fetch_and_save(url, raw_sources_dir)

    if fetch_result["status"] == "success":
        fetch_result["description"] = url_result.get("description")
        fetch_result["source_url"] = url

    return fetch_result