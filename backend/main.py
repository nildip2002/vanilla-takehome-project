"""
FastAPI Application Entry Point.

Configures middleware, lifecycle hooks, telemetry, and mounts the API router.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_db_and_tables
from router import router
from telemetry import setup_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: runs startup and shutdown logic."""
    setup_telemetry()
    logger.info("Creating database tables...")
    create_db_and_tables()
    logger.info("Application startup complete.")
    yield
    logger.info("Application shutdown.")


app = FastAPI(
    title="Agentic Execution Framework",
    description="Production-grade AI agent with ReAct loop, MCP tool orchestration, and real-time SSE telemetry.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def read_root():
    """Root endpoint — confirms the API is operational."""
    return {"message": "Agentic Execution Framework API is running", "version": "2.0.0"}
