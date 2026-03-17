"""Minimal test endpoint to diagnose Vercel runtime issues."""
import os
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
    results["DATABASE_URL_preview"] = os.getenv("DATABASE_URL", "NOT SET")[:60] + "..."

    # Test connection with multiple pooler regions
    import psycopg2
    password = "rahulPACE@066"
    ref = "xtijxyfzbibteluyrxrn"
    regions = ["ap-south-1", "ap-southeast-1", "us-east-1", "eu-west-1", "eu-central-1", "ap-northeast-1"]

    for region in regions:
        host = f"aws-0-{region}.pooler.supabase.com"
        user = f"postgres.{ref}"
        try:
            conn = psycopg2.connect(
                host=host, port=6543, dbname="postgres",
                user=user, password=password,
                connect_timeout=5, sslmode="require"
            )
            cur = conn.cursor()
            cur.execute("SELECT 1")
            results[f"pooler_{region}"] = f"OK: {cur.fetchone()}"
            cur.close()
            conn.close()
        except Exception as e:
            results[f"pooler_{region}"] = str(e)[:120]

    # Also try direct connection with IPv4 workaround
    try:
        import socket
        direct_host = f"db.{ref}.supabase.co"
        addrs = socket.getaddrinfo(direct_host, 5432)
        results["direct_dns"] = str([(a[0].name, a[4]) for a in addrs[:3]])
    except Exception as e:
        results["direct_dns"] = str(e)

    # Try direct with current DATABASE_URL
    try:
        from database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
            results["sqlalchemy_connect"] = f"OK: {row}"
    except Exception as e:
        results["sqlalchemy_connect"] = f"{type(e).__name__}: {str(e)[:150]}"

    return results
