# FastAPI CLI Dev Command
**What it is:** A command-line interface tool, `fastapi dev`, used to run FastAPI applications specifically during local development.
**How it works:** This command automatically reads your `main.py` file, detects the FastAPI application instance within it, and starts a Uvicorn server with auto-reload enabled, watching for code changes.
**The 20%:** To run your FastAPI application in development mode with automatic code reloading, execute `fastapi dev` from your terminal after installing `fastapi[standard]`.
**Concrete example:**
```
$ fastapi dev
╭────────── FastAPI CLI - Development mode ───────────╮
│                                                     │
│  Serving at: http://127.0.0.1:8000                  │
│                                                     │
│  API docs: http://127.0.0.1:8000/docs               │
│                                                     │
╰─────────────────────────────────────────────────────╯
```
**Common mistake:** Using `fastapi dev` for production deployments instead of a production-ready ASGI server like Uvicorn directly or `fastapi run`, as `fastapi dev` is designed for local development with auto-reload.
**Interview answer (30 seconds):** The `fastapi dev` command is a convenient tool for local development with FastAPI. It automatically starts your application server using Uvicorn, detects your FastAPI instance, and enables auto-reloading whenever you save changes to your code. This streamlines the development workflow, letting you see changes instantly without manual restarts.
**Source:** fastapi.txt
**Related:** [[Uvicorn]], [[FastAPI Cloud]]