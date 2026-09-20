from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from serv01 import __version__
from serv01.config import Settings, get_settings
from serv01.database import Base, create_database_engine, create_session_factory
from serv01.queueing import TaskQueue, create_task_queue
from serv01.routers import auth, reports, runs, tasks, templates, web
from serv01.schemas import HealthResponse


def create_app(settings: Settings | None = None, *, task_queue: TaskQueue | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_database_engine(app_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        description="API for configuring and monitoring website automation tasks.",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.session_factory = session_factory
    app.state.task_queue = task_queue or create_task_queue(app_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(templates.router)
    app.include_router(reports.router)
    app.include_router(runs.router)
    app.include_router(web.router)
    static_directory = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_directory), name="static")

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/dashboard")

    return app


app = create_app()
