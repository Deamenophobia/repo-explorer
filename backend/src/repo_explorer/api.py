"""HTTP adapter. This local workbench must remain bound to loopback."""

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver

from repo_explorer.config import Settings, WorkspaceConfig, load_settings
from repo_explorer.plugins import PluginRegistry, default_registry
from repo_explorer.runtime import WorkspaceRuntime
from repo_explorer.schemas import ReviewDecision, RunRequest, RunView

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, registry: PluginRegistry | None = None) -> FastAPI:
    settings = settings or load_settings()
    registry = registry or default_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(settings.data_dir / "checkpoints.sqlite")) as saver:
            app.state.workspace = WorkspaceRuntime(settings, registry, saver)
            app.state.runs = app.state.workspace.runs
            yield

    app = FastAPI(title="Repo Explorer", version="0.1.0", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
        )

    @app.get("/api/health")
    def health():
        return {"status": "ready", "mode": app.state.workspace.settings.mode}

    @app.get("/api/settings")
    def read_settings():
        return app.state.workspace.describe()

    @app.put("/api/settings")
    def update_settings(public: WorkspaceConfig):
        try:
            return app.state.workspace.apply(public)
        except (ValueError, FileNotFoundError) as exc:
            # Never return provider exception bodies, which may contain credentials.
            logger.warning("Configuration rejected: %s", type(exc).__name__)
            raise HTTPException(
                422,
                "Configuration could not be applied. Check source paths, "
                "installed adapters, models and server credentials.",
            ) from exc
        except Exception as exc:
            logger.warning("Configuration preparation failed: %s", type(exc).__name__)
            raise HTTPException(
                422,
                "Could not prepare or save this configuration. "
                "The previous configuration remains active.",
            ) from exc

    @app.get("/api/corpus")
    def corpus():
        workspace = app.state.workspace
        with workspace.runs.lock:
            index = workspace.index
            current = workspace.settings
            return {
                "files": index.files,
                "chunks": len(index.documents),
                "snapshot": index.snapshot,
                "retrieval": index.retrieval,
                "mode": current.mode,
                "workspace_name": current.workspace_name,
                "repository_name": current.repository_name,
                "corpus_description": current.corpus_description,
                "suggestions": current.suggestions,
            }

    @app.post("/api/runs", response_model=RunView)
    def create_run(request: RunRequest):
        try:
            return app.state.runs.create(request)
        except Exception as exc:
            logger.exception("Run generation failed")
            raise HTTPException(
                502, "Generation failed. Check provider configuration and retry."
            ) from exc

    @app.get("/api/runs/{run_id}", response_model=RunView)
    def read_run(run_id: UUID):
        try:
            return app.state.runs.get(str(run_id))
        except KeyError as exc:
            raise HTTPException(404, "Run not found.") from exc

    @app.post("/api/runs/{run_id}/decision", response_model=RunView)
    def decide(run_id: UUID, decision: ReviewDecision):
        try:
            return app.state.runs.decide(str(run_id), decision.approved)
        except KeyError as exc:
            raise HTTPException(404, "Run not found.") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return app


app = create_app()
