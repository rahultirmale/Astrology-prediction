"""Minimal test endpoint to diagnose Vercel runtime issues."""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
app = FastAPI()

@app.get("/api/test")
def test():
    results = {}
    db_url = os.getenv("DATABASE_URL", "NOT SET")
    # Show only host portion (hide credentials)
    if "@" in db_url:
        results["db_host"] = db_url.split("@")[1][:60]
    else:
        results["db_host"] = "NOT SET"

    try:
        from database import engine, init_db
        from sqlalchemy import text
        init_db()
        results["init_db"] = "ok"
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
            results["db_connection"] = f"ok: {row}"
    except Exception as e:
        results["db_connection"] = f"{type(e).__name__}: {str(e)[:200]}"

    try:
        from app import app as main_app
        results["app_import"] = "ok"
    except Exception as e:
        results["app_import"] = f"{type(e).__name__}: {str(e)[:200]}"

    return results
