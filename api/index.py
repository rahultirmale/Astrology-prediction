"""
Vercel serverless function entry point.
Wraps the FastAPI app for Vercel's Python runtime.
"""

import sys
import traceback
from pathlib import Path

# Add the project root to Python path so our modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now import the FastAPI app — wrap in try/except for debugging
try:
    from app import app
except Exception as e:
    # If app import fails, create a minimal app that shows the error
    from fastapi import FastAPI
    app = FastAPI()

    _startup_error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    @app.get("/api/{path:path}")
    @app.post("/api/{path:path}")
    async def error_handler(path: str):
        return {"error": "App failed to start", "detail": _startup_error}

# Vercel looks for an `app` variable or a `handler` function
# FastAPI/Starlette ASGI apps are automatically detected by @vercel/python
