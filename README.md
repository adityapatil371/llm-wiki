# LLM Wiki

A self-maintaining personal ML engineering knowledge base. 
Upload documents, paste URLs, or search for official docs — 
an LLM agent extracts the core 20% of concepts and builds 
a structured wiki. A critic agent fact-checks every page 
before saving. Query your entire wiki in plain English.

## Why not just use RAG?
Standard RAG re-derives knowledge from scratch on every query. 
This system compiles knowledge once into structured wiki pages 
and loads them directly into context at query time — faster, 
more accurate, and fully traceable.

## Stack
- Gemini 2.5 Flash — ingestion and critic agents
- Groq Llama 3.1 8B — fast interactive queries
- SQLite — document hash tracking
- Git — wiki version history
- Streamlit — UI

## How to run

```bash
git clone https://github.com/adityapatil371/llm-wiki
cd llm-wiki
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your API keys
streamlit run app.py
```

Or with Docker:
```bash
docker run -p 8501:8501 \
  -e GOOGLE_API_KEY=your_key \
  -e GROQ_API_KEY=your_key \
  llm-wiki
```

## Key design decisions
- **No vector database** — wiki fits in Gemini's 1M token context window
- **Multi-agent validation** — deterministic checks run before LLM critic
- **Hash-based deduplication** — re-uploading unchanged docs is a no-op
- **Source immutability** — agent reads raw sources but never modifies them

## What I'd improve
- Cloud Run deployment for 24/7 access from any device
- Automated source freshness checks when docs update
- Graph visualisation of concept connections