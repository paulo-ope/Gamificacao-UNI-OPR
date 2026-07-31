import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api.routes import audit, auth, calculation_runs, collaborators, dashboard, gamification, health, imports, leadership, point_balance, portal, rules, scoring, service_orders, settings, users
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.core.security import ensure_access_profiles, ensure_initial_admin
from app.modules.admin.router import router as admin_router
from app.modules.management.router import router as management_router
from app.modules.operations.router import router as operations_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.workspace.router import router as workspace_router
from app.services.ixc_scheduler import run_ixc_sync_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings_ = get_settings()
    inspector = inspect(engine)
    if inspector.has_table("users") and inspector.has_table("access_profiles"):
        with SessionLocal() as db:
            ensure_initial_admin(db)
            ensure_access_profiles(db)

    # O loop fica sempre rodando quando o IXC está configurado - se ligar/desligar e o intervalo passam a
    # ser controlados pelo banco (AppSetting), lidos a cada ciclo, para dar pra mudar pela própria tela de
    # configuração sem precisar reiniciar o backend. `settings_.ixc_sync_enabled` só serve de valor inicial
    # (variável de ambiente) até alguém configurar isso pela ferramenta.
    ixc_sync_task = None
    if settings_.ixc_api_base_url and settings_.ixc_api_token:
        ixc_sync_task = asyncio.create_task(
            run_ixc_sync_loop(settings_.ixc_sync_interval_minutes, initial_enabled=settings_.ixc_sync_enabled)
        )

    yield

    if ixc_sync_task:
        ixc_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ixc_sync_task


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
app.include_router(point_balance.router, prefix=settings_obj.api_prefix)
app.include_router(portal.router, prefix=settings_obj.api_prefix)
app.include_router(workspace_router, prefix=settings_obj.api_prefix)
app.include_router(admin_router, prefix=settings_obj.api_prefix)
app.include_router(management_router, prefix=settings_obj.api_prefix)
app.include_router(operations_router, prefix=settings_obj.api_prefix)
app.include_router(scheduling_router, prefix=settings_obj.api_prefix)
