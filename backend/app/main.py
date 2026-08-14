import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api.routes import audit, auth, calculation_runs, collaborators, dashboard, gamification, health, imports, leadership, notifications, point_balance, portal, rules, scoring, service_orders, settings, users
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.core.security import ensure_access_profiles, ensure_initial_admin
from app.modules.admin.router import router as admin_router
from app.modules.ai.router import public_router as ai_public_router, router as ai_router
from app.modules.ai_governance.bootstrap import ensure_ai_governance_seed
from app.modules.ai_governance.router import router as ai_governance_router
from app.modules.management.router import router as management_router
from app.modules.mcp_connector.router import router as mcp_connector_router
from app.modules.mcp_connector.server import build_mcp_server
from app.modules.operations.backlog_snapshot import run_backlog_snapshot_loop
from app.modules.operations.login_status_snapshot import run_login_status_snapshot_loop
from app.modules.operations.onu_signal_snapshot import run_onu_signal_snapshot_loop
from app.modules.operations.router import router as operations_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.workspace.router import router as workspace_router
from app.services.ixc_scheduler import run_ixc_sync_loop


settings_obj = get_settings()

# Instanciado uma vez, em nível de módulo (não dentro de `lifespan`), porque tanto `lifespan`
# (que precisa iniciar o gerenciador de sessão do MCP) quanto o `app.mount` abaixo (que precisa
# do app ASGI dele) precisam do MESMO objeto `FastMCP` - dois `build_mcp_server()` criariam dois
# gerenciadores de sessão independentes, um dos quais nunca seria inicializado.
mcp_server_instance = build_mcp_server() if settings_obj.public_base_url else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings_ = get_settings()
    inspector = inspect(engine)
    if inspector.has_table("users") and inspector.has_table("access_profiles"):
        with SessionLocal() as db:
            ensure_initial_admin(db)
            ensure_access_profiles(db)
    if inspector.has_table("ai_endpoints") and inspector.has_table("ai_field_permissions"):
        with SessionLocal() as db:
            ensure_ai_governance_seed(db)

    # O loop fica sempre rodando quando o IXC está configurado - se ligar/desligar e o intervalo passam a
    # ser controlados pelo banco (AppSetting), lidos a cada ciclo, para dar pra mudar pela própria tela de
    # configuração sem precisar reiniciar o backend. `settings_.ixc_sync_enabled` só serve de valor inicial
    # (variável de ambiente) até alguém configurar isso pela ferramenta.
    ixc_sync_task = None
    if settings_.ixc_api_base_url and settings_.ixc_api_token:
        ixc_sync_task = asyncio.create_task(
            run_ixc_sync_loop(settings_.ixc_sync_interval_minutes, initial_enabled=settings_.ixc_sync_enabled)
        )

    # Sem dependência de configuração externa (ao contrário do IXC) - sempre roda, é só uma
    # leitura do próprio banco de O.S. já sincronizado.
    backlog_snapshot_task = asyncio.create_task(run_backlog_snapshot_loop())

    # Histórico de status de conexão dos logins (para detecção de queda de fibra por proximidade
    # geográfica) - só roda quando o IXC está configurado, mesma condição do `ixc_sync_task`.
    login_status_snapshot_task = None
    if settings_.ixc_api_base_url and settings_.ixc_api_token:
        login_status_snapshot_task = asyncio.create_task(run_login_status_snapshot_loop())

    # Telemetria óptica/ONU (sinal RX/TX, causa da última queda, transmissor) dos logins já
    # monitorados - mesma condição de configuração do IXC, intervalo mais espaçado (ver
    # docstring de run_onu_signal_snapshot_loop).
    onu_signal_snapshot_task = None
    if settings_.ixc_api_base_url and settings_.ixc_api_token:
        onu_signal_snapshot_task = asyncio.create_task(run_onu_signal_snapshot_loop())

    # `streamable_http_app()` tem seu próprio lifespan (inicia o gerenciador de sessão MCP), mas
    # Starlette não propaga o protocolo ASGI "lifespan" automaticamente para apps montados via
    # `app.mount` - sem isso, toda chamada de tool falha com "Task group is not initialized"
    # (achado real, confirmado testando o fluxo OAuth de ponta a ponta antes de subir isso).
    if mcp_server_instance is not None:
        async with mcp_server_instance.session_manager.run():
            yield
    else:
        yield

    if ixc_sync_task:
        ixc_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ixc_sync_task

    backlog_snapshot_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await backlog_snapshot_task

    if login_status_snapshot_task:
        login_status_snapshot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await login_status_snapshot_task

    if onu_signal_snapshot_task:
        onu_signal_snapshot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await onu_signal_snapshot_task


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
app.include_router(notifications.router, prefix=settings_obj.api_prefix)
app.include_router(portal.router, prefix=settings_obj.api_prefix)
app.include_router(workspace_router, prefix=settings_obj.api_prefix)
app.include_router(admin_router, prefix=settings_obj.api_prefix)
app.include_router(ai_governance_router, prefix=settings_obj.api_prefix)
app.include_router(management_router, prefix=settings_obj.api_prefix)
app.include_router(operations_router, prefix=settings_obj.api_prefix)
app.include_router(scheduling_router, prefix=settings_obj.api_prefix)
app.include_router(ai_router, prefix=settings_obj.api_prefix)
app.include_router(ai_public_router, prefix=settings_obj.api_prefix)

# Conector MCP remoto (Claude.ai/Cowork) - servidor OAuth + endpoint MCP, montado só quando
# PUBLIC_BASE_URL está configurada (ver app/core/config.py). `app.mount` porque
# `streamable_http_app()` devolve um app Starlette pronto (com as rotas de OAuth do SDK do MCP já
# registradas), não um APIRouter do FastAPI - `include_router` não serviria aqui.
app.include_router(mcp_connector_router, prefix=settings_obj.api_prefix)
if mcp_server_instance is not None:
    app.mount(f"{settings_obj.api_prefix}/mcp", mcp_server_instance.streamable_http_app())
