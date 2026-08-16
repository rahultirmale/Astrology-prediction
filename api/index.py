"""
Vercel serverless function entry point.
Wraps the FastAPI app for Vercel's Python runtime.

NOTE: @vercel/python detects the entrypoint by scanning the module's AST for a
*top-level* binding named `app`, `application`, or `handler`. A name bound only
inside a try/except block is not top-level, so `app` must be assigned by a plain
module-level statement at the end of this file.
"""

import sys
import traceback
from pathlib import Path

# Add the project root to Python path so our modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_app():
    """Import the real FastAPI app, falling back to an error-reporting stub."""
    try:
        from app import app as fastapi_app

        return fastapi_app
    except Exception as exc:  # noqa: BLE001 - surface any startup failure
        from fastapi import FastAPI

        startup_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        fallback = FastAPI()

        @fallback.get("/api/{path:path}")
        @fallback.post("/api/{path:path}")
        async def error_handler(path: str):
            return {"error": "App failed to start", "detail": startup_error}

        return fallback


# Top-level binding — this is what Vercel looks for.
app = _load_app()
handler = app
