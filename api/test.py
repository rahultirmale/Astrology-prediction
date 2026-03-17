"""Minimal test endpoint to diagnose Vercel runtime issues."""
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
app = FastAPI()

@app.get("/api/test")
def test():
    results = {}

    # Test 1: basic imports
    try:
        import fastapi
        results["fastapi"] = "ok"
    except Exception as e:
        results["fastapi"] = str(e)

    # Test 2: psycopg2
    try:
        import psycopg2
        results["psycopg2"] = "ok"
    except Exception as e:
        results["psycopg2"] = str(e)

    # Test 3: database module
    try:
        from database import engine
        results["database_engine"] = str(engine.url).split("@")[0][:30] + "..."
    except Exception as e:
        results["database_engine"] = str(e)

    # Test 4: connect to database
    try:
        from database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
            results["db_connection"] = f"ok: {row}"
    except Exception as e:
        results["db_connection"] = f"{type(e).__name__}: {e}"

    # Test 5: init_db
    try:
        from database import init_db
        init_db()
        results["init_db"] = "ok"
    except Exception as e:
        results["init_db"] = f"{type(e).__name__}: {e}"

    # Test 6: app import
    try:
        from app import app as main_app
        results["app_import"] = "ok"
    except Exception as e:
        results["app_import"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}"

    return results
