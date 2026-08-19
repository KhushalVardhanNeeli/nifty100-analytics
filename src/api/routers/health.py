"""Health endpoint — status, table row counts, uptime."""

import time

from fastapi import APIRouter

from src.api.db import table_counts

router = APIRouter(tags=["health"])
START = time.time()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "db_row_counts": table_counts(),
        "uptime_seconds": round(time.time() - START, 1),
        "version": "1.0.0",
    }
