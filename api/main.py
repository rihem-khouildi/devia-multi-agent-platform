"""
FastAPI application factory for the AI-SDLC backend.
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from api.db import initialize_database
from api.services import graphrag_service
from config.settings import Settings
from api.routes import health, projects, stories, graphrag, runs, auth, project_sources, integrations


def create_app() -> FastAPI:
    settings = Settings()
    allow_origins = settings.app.cors_allow_origins or ["*"]
    allow_credentials = "*" not in allow_origins

    app = FastAPI(
        title="AI-SDLC API",
        description="Backend API for the AI-powered SDLC pipeline",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(project_sources.router)
    app.include_router(stories.router)
    app.include_router(graphrag.router)
    app.include_router(runs.router)
    app.include_router(integrations.router)

    Instrumentator().instrument(app).expose(app)

    @app.on_event("startup")
    async def startup() -> None:
        initialize_database(settings)
        _autoload_graphrag(settings)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logging.exception("Unhandled API exception", exc_info=exc)
        detail = str(exc) if (settings.app.debug or not settings.app.is_production()) else None
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": detail},
        )

    return app


def _autoload_graphrag(settings: Settings) -> None:
    filename = os.getenv("GRAPHRAG_FILE", "test-graph.json")
    candidate = settings.pipeline.docs_dir / filename
    if not candidate.exists():
        logging.info("GraphRAG autoload skipped: %s not found", candidate)
        return
    try:
        graphrag_service.load_context(str(candidate), source="default")
        logging.info("GraphRAG autoloaded from %s", candidate)
    except Exception:
        logging.exception("GraphRAG autoload failed for %s", candidate)


app = create_app()
