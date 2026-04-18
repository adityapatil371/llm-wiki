# Pydantic BaseModel
**What it is:** A class provided by Pydantic used within FastAPI to declare the structure and types of API request bodies.
**How it works:** You define a Python class that inherits from `BaseModel` with type-hinted attributes; FastAPI then uses this model to automatically validate incoming JSON data, convert it to Python types, and document it for the API.
**The 20%:** Create a class inheriting from `pydantic.BaseModel` to define complex data structures for request bodies, using standard Python type hints for attributes like `name: str` and `price: float`, enabling automatic validation and serialization.
**Concrete example:**
```python
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float
    is_offer: bool | None = None
```
**Common mistake:** Submitting a request body that does not conform to the defined `BaseModel`'s structure or data types, which will result in automatic validation errors from FastAPI.
**Interview answer (30 seconds):** Pydantic's `BaseModel` is how you define the expected structure and types for data sent to your FastAPI application, especially in request bodies. By simply declaring a class with type hints, FastAPI automatically handles data validation, serialization, and generates documentation for these complex data structures, making your API robust and easy to use.
**Source:** fastapi.txt
**Related:** [[FastAPI Parameter Declaration]], [[Type Hints]]