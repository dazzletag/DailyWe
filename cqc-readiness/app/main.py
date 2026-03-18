from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import app.database as db_module
from app.config import get_settings
from app.database import get_engine, get_session_factory
from app.routers import admin, health, respond
from app.services.scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "web")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Application lifespan:
    - On startup: create DB engine, session factory, start APScheduler
    - On shutdown: dispose DB engine, stop scheduler
    """
    logger.info("Starting up cqc-readiness application…")
    settings = get_settings()

    # Initialise database
    engine = get_engine()
    session_factory = get_session_factory(engine)

    # Inject into module-level variables so get_db() dependency works
    db_module.engine = engine
    db_module.SessionFactory = session_factory

    # Create all tables if they don't exist
    from app.database import Base
    import app.models  # noqa: F401 — registers all ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created")

    # Start scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started")

    yield

    # Shutdown
    logger.info("Shutting down…")
    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="CQC Readiness",
        description=(
            "Daily CQC readiness check system for Bristol Care Homes. "
            "Sends personalised We Statement checks to care home managers "
            "and tracks confidence levels."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — restrict in production
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Routers
    application.include_router(health.router)
    application.include_router(respond.router)
    application.include_router(admin.router)

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------
    @application.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Page Not Found",
                "error_message": "The page you're looking for doesn't exist.",
            },
            status_code=404,
        )

    @application.exception_handler(500)
    async def internal_error_handler(request: Request, exc):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Internal Server Error",
                "error_message": (
                    "Something went wrong on our end. "
                    "Please try again or contact support."
                ),
            },
            status_code=500,
        )

    return application


app = create_app()
