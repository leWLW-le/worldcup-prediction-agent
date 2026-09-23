"""V2 application: a single prediction core, optional LLM coordinator."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v2 import router
from app.core.config import get_settings, validate_settings
from app.db.database import check_db_connection, engine, init_db
from app.infrastructure.jobs import Jobs
from app.infrastructure.store import Store
from app.models.registry import get_registry
from app.pipelines.prediction import PredictionPipeline

settings = get_settings()


@asynccontextmanager
async def lifespan(app):
    validate_settings(settings)
    init_db()
    store = Store()
    registry = get_registry(settings.MODEL_BUNDLE_DIR)
    pipeline = PredictionPipeline(
        store, registry, settings.COMPUTE_TIMEOUT_SECONDS, settings.ALLOW_DEMO_DATA
    )
    jobs = Jobs(store, pipeline)
    app.state.services = SimpleNamespace(
        store=store, registry=registry, pipeline=pipeline, jobs=jobs
    )
    try:
        yield
    finally:
        jobs.close()
        engine.dispose()


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in settings.ALLOWED_ORIGINS.split(",") if s.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key"],
)
app.include_router(router, prefix="/api/v2")


@app.middleware("http")
async def body_budget(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings.MAX_REQUEST_BYTES):
            return JSONResponse(status_code=413, content={"detail": "Request body exceeds budget"})
        size, chunks = 0, []
        async for chunk in request.stream():
            size += len(chunk)
            if size > settings.MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413, content={"detail": "Request body exceeds budget"}
                )
            chunks.append(chunk)
        request._body = b"".join(chunks)
    return await call_next(request)


@app.exception_handler(KeyError)
async def missing_resource(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def invalid_value(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    connected = check_db_connection()
    return JSONResponse(
        status_code=200 if connected else 503,
        content={"status": "healthy" if connected else "unhealthy"},
    )


@app.get("/ready")
def ready(request: Request):
    service = getattr(request.app.state, "services", None)
    connected = check_db_connection()
    return JSONResponse(
        status_code=200 if service and connected else 503,
        content={
            "database": connected,
            "model_version": service.registry.version if service else None,
            "model_mode": "trained" if service and service.registry.manifest else "baseline",
            "llm_configured": bool(settings.LLM_API_KEY),
        },
    )


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def retired(path: str):
    return JSONResponse(
        status_code=410,
        content={"detail": "V1 retired: use /api/v2 and versioned snapshots", "migration": "/docs"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT)
