from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from serv01 import __version__
from serv01.config import Settings, get_settings
from serv01.database import Base, create_database_engine, create_session_factory
from serv01.routers import auth, reports, tasks, templates
from serv01.schemas import HealthResponse


def create_app(settings: Settings | None = None) -> FastAPI:
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

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": app_settings.app_name, "docs": "/docs", "health": "/health"}

    return app


app = create_app()
