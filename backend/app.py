"""
backend/app.py  —  Owner: Rani Gupta (24BIT0543)
=================================================
The ONE backend of the project (replaces the two competing apps src/api/main.py and
the old backend/ package; see INITIAL_PROJECT_AUDIT.md).

    uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8000
    OpenAPI docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from backend.audit import write_audit
from backend.config import Settings
from backend.db import Database, run_migrations
from backend.deps import RateLimiter
from backend.metrics import Metrics
from backend.models import User
from backend.security import hash_password
from backend.services.alerts import default_channels, dispatch_alert
from backend.services.pipeline import PipelineContext
from src.execution.adapters import Executor, LocalCloudObjectStoreAdapter, LocalEdgeAdapter, S3CloudAdapter
from src.prediction.predict_service import LatencyPredictor

API_VERSION = "2.0.0"
log = logging.getLogger("app")


def _bootstrap_admin(db: Database, s: Settings) -> None:
    with db.session() as session:
        if session.execute(select(func.count()).select_from(User)).scalar_one() > 0:
            return
        if not (s.bootstrap_admin_username and s.bootstrap_admin_password):
            log.warning("No users exist. Set BOOTSTRAP_ADMIN_USERNAME/BOOTSTRAP_ADMIN_PASSWORD or run "
                        "`python -m scripts.create_user` to create the first admin.")
            return
        session.add(User(username=s.bootstrap_admin_username, full_name="Bootstrap administrator", role="admin",
                         password_hash=hash_password(s.bootstrap_admin_password, s.password_iterations)))
        session.flush()
        write_audit(session, "system", "user_bootstrapped", f"user/{s.bootstrap_admin_username}", {"role": "admin"})


def create_app(settings: Settings | None = None, predictor: LatencyPredictor | None = None,
               alert_channels: list | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.db.dispose()

    app = FastAPI(title="Healthcare Edge/Cloud Routing API", version=API_VERSION, lifespan=lifespan,
                  description="Predict (LSTM on RIPE Atlas) -> decide (AHP + safety vetoes) -> execute (edge/cloud) "
                              "-> persist, audit, alert. Research prototype; not a medical device.")
    if s.auto_migrate:
        run_migrations(s.database_url)
    db = Database(s.database_url)
    _bootstrap_admin(db, s)
    edge = LocalEdgeAdapter(s.runtime_dir)
    cloud = S3CloudAdapter(s.s3_bucket) if s.cloud_adapter == "s3" else LocalCloudObjectStoreAdapter(s.runtime_dir)
    executor = Executor(edge, cloud, max_attempts=s.execution_max_attempts)
    predictor = predictor or LatencyPredictor.load(s.model_dir)
    channels = alert_channels if alert_channels is not None else default_channels(s)

    app.state.settings, app.state.db, app.state.predictor, app.state.executor = s, db, predictor, executor
    app.state.alert_channels = channels
    app.state.pipeline = PipelineContext(session_factory=db.session, predictor=predictor, executor=executor)
    app.state.rate_limiter = RateLimiter(s.rate_limit_per_minute)
    app.state.metrics = Metrics()
    app.state.dispatch_alert = partial(dispatch_alert, db.session, s, channels=channels)

    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def guard_and_time(request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > s.max_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "request body too large"})
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # never leak stack traces or secrets to clients
            log.exception("unhandled error rid=%s path=%s", rid, request.url.path)
            response = JSONResponse(status_code=500, content={"detail": "internal server error", "request_id": rid})
        dt = time.perf_counter() - t0
        response.headers["X-Request-ID"] = rid
        response.headers["X-Process-Time-Ms"] = f"{dt * 1000:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        route = request.scope.get("route")
        app.state.metrics.observe_request(request.method, getattr(route, "path", "unmatched"), response.status_code, dt)
        return response

    from backend.routers import auth, dashboard, events, records
    for r in (auth.router, events.router, records.router, dashboard.router):
        app.include_router(r)

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "version": API_VERSION}

    @app.get("/ready", tags=["ops"])
    def ready():
        try:
            with db.session() as session:
                session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        body = {"database": db_ok, "model_loaded": predictor.model_loaded, "model_version": predictor.model_version}
        return JSONResponse(status_code=200 if db_ok else 503, content={"ready": db_ok, **body})

    @app.get("/metrics", tags=["ops"])
    def metrics():
        data, ctype = app.state.metrics.render()
        return Response(content=data, media_type=ctype)

    dist = s.frontend_dist
    if (dist / "index.html").exists():  # serve the built React dashboard from the same origin
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse(status_code=404, content={"detail": "not found"})
            f = (dist / full_path).resolve()
            if full_path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    return app
