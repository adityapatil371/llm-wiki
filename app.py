import os
import time
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
from db import init_db, get_all_ingested
from ingest import ingest_document
from query import query_wiki
from lint import run_lint
from fetch_source import fetch_and_save, search_and_fetch_docs

load_dotenv()
init_db()

st.set_page_config(
    page_title="ML Wiki",
    page_icon="📖",
    layout="centered"
)

st.markdown("""
<style>
.block-container { padding-top: 2rem; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] { font-size: 13px; }
</style>
""", unsafe_allow_html=True)


def render_add_page():
    st.header("Add source")

    tab_upload, tab_search, tab_url = st.tabs([
        "📄  Upload file", "📚  Find docs", "🔗  Paste URL"
    ])

    # initialise queue in session state
    if "queue" not in st.session_state:
        st.session_state.queue = []

    with tab_upload:
        uploaded = st.file_uploader(
            "Upload PDF, TXT, or MD",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True
        )
        if uploaded:
            for f in uploaded:
                already = any(
                    item["filename"] == f.name
                    for item in st.session_state.queue
                )
                if not already:
                    st.session_state.queue.append({
                        "filename": f.name,
                        "type": "upload",
                        "bytes": f.read(),
                        "label": f.name
                    })
            st.success(f"Added {len(uploaded)} file(s) to queue.")

    with tab_search:
        col1, col2 = st.columns([4, 1])
        with col1:
            tool_name = st.text_input(
                "Tool name",
                placeholder="e.g. XGBoost, FastAPI, LangChain...",
                label_visibility="collapsed"
            )
        with col2:
            find_btn = st.button("Find docs", use_container_width=True)

        if find_btn and tool_name:
            with st.spinner(f"Finding docs for {tool_name}..."):
                result = search_and_fetch_docs(tool_name)
            if result["status"] == "success":
                st.session_state.queue.append({
                    "filename": result["filename"],
                    "type": "docs",
                    "filepath": result["filepath"],
                    "label": f"{tool_name} — {result.get('source_url', '')}",
                    "description": result.get("description", "")
                })
                st.success(f"Found: {result['source_url']}")
                st.caption(result.get("description", ""))
            else:
                st.error(result["message"])

    with tab_url:
        col1, col2 = st.columns([4, 1])
        with col1:
            url_input = st.text_input(
                "URL",
                placeholder="Paste any URL — YouTube, docs page, article...",
                label_visibility="collapsed"
            )
        with col2:
            url_btn = st.button("Add URL", use_container_width=True)

        if url_btn and url_input:
            is_yt = "youtube.com" in url_input or "youtu.be" in url_input
            with st.spinner("Downloading transcript..." if is_yt else "Fetching page..."):
                result = fetch_and_save(url_input)
            if result["status"] == "success":
                st.session_state.queue.append({
                    "filename": result["filename"],
                    "type": "youtube" if is_yt else "url",
                    "filepath": result["filepath"],
                    "label": url_input,
                })
                st.success(f"Saved: {result['filename']}")
                st.caption(result.get("preview", "")[:200])
            else:
                st.error(result["message"])

    # queue display
    if st.session_state.queue:
        st.divider()
        st.subheader(f"Queue — {len(st.session_state.queue)} source(s)")

        for i, item in enumerate(st.session_state.queue):
            col1, col2 = st.columns([5, 1])
            with col1:
                type_icons = {
                    "upload": "📄", "docs": "📚",
                    "youtube": "▶", "url": "🔗"
                }
                icon = type_icons.get(item["type"], "📄")
                st.markdown(
                    f"{icon} **{item['filename']}**  \n"
                    f"<span style='font-size:12px;color:gray'>{item.get('label', '')}</span>",
                    unsafe_allow_html=True
                )
            with col2:
                if st.button("Remove", key=f"remove_{i}"):
                    st.session_state.queue.pop(i)
                    st.rerun()

        st.divider()
        if st.button("Start ingestion →", type="primary", use_container_width=True):
            st.session_state.show_preview = True
            st.rerun()

    if st.session_state.get("show_preview"):
        render_preview()


def render_preview():
    st.divider()
    st.subheader("Preview")
    st.caption("Review sources before ingesting. Each will be processed by the ingestion agent and reviewed by the critic.")

    for item in st.session_state.queue:
        with st.expander(item["filename"]):
            st.markdown(f"**Type:** {item['type']}")
            st.markdown(f"**Label:** {item.get('label', '-')}")
            if item.get("description"):
                st.markdown(f"**Description:** {item['description']}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            st.session_state.show_preview = False
            st.rerun()
    with col2:
        if st.button("Confirm + ingest", type="primary", use_container_width=True):
            run_ingestion()


def run_ingestion():
    queue = st.session_state.queue
    progress = st.progress(0)
    status = st.empty()
    results = []

    for i, item in enumerate(queue):
        status.text(f"Ingesting {item['filename']}...")

        try:
            if item["type"] == "upload":
                file_bytes = item["bytes"]
            else:
                file_bytes = Path(item["filepath"]).read_bytes()

            result = ingest_document(file_bytes, item["filename"])
            results.append({
                "filename": item["filename"],
                "status": result["status"],
                "pages": result.get("pages_created", []),
                "critic_approved": result.get("critic_approved", False),
                "message": result.get("message", "")
            })
        except Exception as e:
            results.append({
                "filename": item["filename"],
                "status": "error",
                "message": str(e)
            })

        progress.progress((i + 1) / len(queue))
        time.sleep(0.5)

    status.text("Done.")
    st.session_state.queue = []
    st.session_state.show_preview = False
    st.session_state.ingestion_results = results
    st.rerun()


def render_wiki_page():
    st.header("Wiki")

    ingested = get_all_ingested()
    wiki_path = Path("wiki")
    all_pages = list(wiki_path.rglob("*.md"))
    concept_pages = [p for p in all_pages if p.stem != "index"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Concepts", len(concept_pages))
    col2.metric("Sources ingested", len(ingested))
    flagged = sum(
        1 for p in concept_pages
        if "FLAGGED FOR REVIEW" in p.read_text()
    )
    col3.metric("Flagged", flagged)

    if concept_pages:
        st.divider()
        st.subheader("Concepts")
        for page in sorted(concept_pages):
            content = page.read_text()
            is_flagged = "FLAGGED FOR REVIEW" in content
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{page.stem}**")
            with col2:
                if is_flagged:
                    st.markdown(
                        "<span style='color:orange;font-size:12px'>flagged</span>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        "<span style='color:green;font-size:12px'>ok</span>",
                        unsafe_allow_html=True
                    )
            with st.expander("View page"):
                st.markdown(content)

    if ingested:
        st.divider()
        st.subheader("Sources")
        for doc in ingested:
            st.markdown(
                f"**{doc['document_name']}** — "
                f"<span style='font-size:12px;color:gray'>{doc['date_ingested'][:10]}</span>",
                unsafe_allow_html=True
            )

    st.divider()
    if st.button("Run lint check", use_container_width=True):
        with st.spinner("Checking wiki health..."):
            result = run_lint()
        if result["deterministic_issues"]:
            st.warning(f"{len(result['deterministic_issues'])} issue(s) found")
            for issue in result["deterministic_issues"]:
                st.markdown(f"- {issue}")
        else:
            st.success("No structural issues found.")
        st.divider()
        st.markdown("**Semantic health check**")
        st.markdown(result["llm_report"])


def render_query_page():
    st.header("Ask your wiki")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("Ask anything you've learned...")

    if question:
        st.session_state.chat_history.append({
            "role": "user",
            "content": question
        })
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Searching wiki..."):
                result = query_wiki(question)
            if result["status"] == "success":
                st.markdown(result["answer"])
                st.caption(f"Model: {result.get('model_used', '-')}")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": result["answer"]
                })
            else:
                st.error(result["message"])


# main navigation
page = st.sidebar.radio(
    "Navigation",
    ["Add source", "Wiki", "Ask"],
    label_visibility="collapsed"
)

if st.session_state.get("ingestion_results"):
    results = st.session_state.ingestion_results
    st.sidebar.divider()
    st.sidebar.markdown("**Last ingestion**")
    for r in results:
        icon = "✓" if r["status"] == "success" else "✗"
        st.sidebar.markdown(f"{icon} {r['filename']}")
    if st.sidebar.button("Clear results"):
        st.session_state.ingestion_results = None
        st.rerun()

if page == "Add source":
    render_add_page()
elif page == "Wiki":
    render_wiki_page()
elif page == "Ask":
    render_query_page()