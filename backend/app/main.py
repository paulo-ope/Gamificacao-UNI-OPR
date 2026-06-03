from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audit, auth, calculation_runs, collaborators, dashboard, gamification, health, imports, leadership, rules, scoring, service_orders, settings, users
from app.core.config import get_settings
from app.core.security import ensure_initial_admin
from app.db.base import Base
from app.db.migrations import ensure_runtime_schema
from app.db.session import SessionLocal, engine
from app.seed import seed_database
from app.services.calculation import calculate_scores, latest_run
from app.services.gamification_config import ensure_active_config_version


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    settings_obj = get_settings()
    with SessionLocal() as db:
        ensure_initial_admin(db)
    if settings_obj.auto_seed:
        with SessionLocal() as db:
            seed_database(db, include_demo=settings_obj.demo_seed)
            ensure_active_config_version(db)
            if latest_run(db) is None:
                calculate_scores(db)
    yield


settings_obj = get_settings()
app = FastAPI(title=settings_obj.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings_obj.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings_obj.api_prefix)
app.include_router(auth.router, prefix=settings_obj.api_prefix)
app.include_router(users.router, prefix=settings_obj.api_prefix)
app.include_router(imports.router, prefix=settings_obj.api_prefix)
app.include_router(audit.router, prefix=settings_obj.api_prefix)
app.include_router(collaborators.router, prefix=settings_obj.api_prefix)
app.include_router(scoring.router, prefix=settings_obj.api_prefix)
app.include_router(rules.router, prefix=settings_obj.api_prefix)
app.include_router(gamification.router, prefix=settings_obj.api_prefix)
app.include_router(service_orders.router, prefix=settings_obj.api_prefix)
app.include_router(leadership.router, prefix=settings_obj.api_prefix)
app.include_router(calculation_runs.router, prefix=settings_obj.api_prefix)
app.include_router(dashboard.router, prefix=settings_obj.api_prefix)
app.include_router(settings.router, prefix=settings_obj.api_prefix)
