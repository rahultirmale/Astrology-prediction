"""
Vercel serverless function entry point.
Wraps the FastAPI app for Vercel's Python runtime.
"""

import sys
from pathlib import Path

# Add the project root to Python path so our modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now import the FastAPI app
from app import app

# Vercel looks for an `app` variable or a `handler` function
# FastAPI/Starlette ASGI apps are automatically detected by @vercel/python
