"""
saas/api/main.py — FastAPI entry point for the AIOps Platform SaaS API.

This API wraps the IaC Generator agent and exposes it as a streaming service.
Phase 1 scaffold: stub endpoints with TODO markers for auth + billing.

Usage:
    uvicorn main:app --reload --port 8080

Endpoints:
    POST /runs          — Submit an IaC generation job (SSE streaming)
    GET  /runs/{run_id} — Poll a job by ID
    GET  /healthz       — Health check (no auth required)

TODO — before shipping to production:
    - [ ] Replace stub auth with Supabase JWT verification (see src/core/auth.py)
    - [ ] Replace stub billing with Stripe metered usage (see src/core/billing.py)
    - [ ] Add persistent run storage (PostgreSQL via asyncpg or SQLModel)
    - [ ] Rate limiting per user (slowapi or nginx upstream)
    - [ ] Add /runs/{run_id}/cancel endpoint
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from src.routers import runs, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("saas.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("AIOps Platform API starting up")
    yield
    log.info("AIOps Platform API shutting down")


app = FastAPI(
    title="AIOps Platform API",
    description=(
        "Wraps the IaC Generator agent. "
        "Submit a natural-language infrastructure prompt, "
        "stream back Terraform HCL files as they're generated."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS — allow the Next.js dev server ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(runs.router, prefix="/runs")
