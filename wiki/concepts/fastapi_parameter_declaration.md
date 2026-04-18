# FastAPI Parameter Declaration
**What it is:** The method in FastAPI of defining API endpoint parameters (path, query, body) using standard Python type annotations directly in function signatures.
**How it works:** FastAPI inspects these type hints to automatically perform data validation, type conversion from incoming requests, and generate the corresponding OpenAPI documentation.
**The 20%:** Declare function parameters with Python type hints (e.g., `item_id: int`, `q: str | None = None`) to automatically get data validation, type conversion, and documentation for path and query parameters; for request bodies, use a Pydantic `BaseModel`.
**Concrete example:**
```python
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}
```
**Common mistake:** Providing data for a parameter (e.g., `item_id`) that does not match its declared Python type, leading to an automatic and clear error from FastAPI instead of unexpected behavior.
**Interview answer (30 seconds):** FastAPI uses standard Python type hints in your function parameters to automatically validate incoming data, convert it to the correct Python types, and generate interactive API documentation. This means you declare your API's expected data once, using familiar Python syntax, and FastAPI handles the rest, significantly reducing boilerplate and potential errors.
**Source:** fastapi.txt
**Related:** [[Pydantic BaseModel]], [[OpenAPI]]