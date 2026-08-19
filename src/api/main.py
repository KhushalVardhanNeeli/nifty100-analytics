"""Nifty 100 Analytics API — FastAPI entry point.

Serves 16 endpoints under /api/v1 across 8 routers.
"""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import (
    companies,
    documents,
    health,
    peers,
    portfolio,
    screener,
    sectors,
    valuation,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Nifty 100 Analytics API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    logger.info("%s %s %.3fs", request.method, request.url.path, time.time() - start)
    return response


API_V1 = "/api/v1"
for router in (
    health.router,
    companies.router,
    screener.router,
    sectors.router,
    peers.router,
    valuation.router,
    portfolio.router,
    documents.router,
):
    app.include_router(router, prefix=API_V1)
