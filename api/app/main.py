from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services import literature_rag
from app.services.action_logger import start_purge_worker, stop_purge_worker
from app.routes.agent import router as agent_router
from app.routes.auth import router as auth_router
from app.routes.content import router as content_router
from app.routes.expression import router as expression_router
from app.routes.feedback import router as feedback_router
from app.routes.genes import router as genes_router
from app.routes.genomes import router as genomes_router
from app.routes.health import router as health_router
from app.routes.legal import router as legal_router
from app.routes.literature import router as literature_router
from app.routes.proteins import router as proteins_router
from app.routes.visits import router as visits_router
from app.services.auth_store import init_auth_db
from app.services.user_analytics import init_analytics_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_db()
    init_analytics_db()
    literature_rag.initialize()
    start_purge_worker()
    yield
    stop_purge_worker()


def _docs_enabled() -> bool:
    raw = (settings.disable_docs or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return False
    if raw in ("0", "false", "no", "off"):
        return True
    # Default: hide Swagger/ReDoc in production
    return settings.env not in ("production", "prod")


_docs = _docs_enabled()
app = FastAPI(
    title="CucurbitAgent API",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)


def _cors_kwargs() -> dict:
    raw = (settings.cors_origins or "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        return {
            "allow_origins": origins,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    # Local / unspecified: open CORS but credentials incompatible with "*"
    return {
        "allow_origins": ["*"],
        "allow_credentials": False,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


app.add_middleware(CORSMiddleware, **_cors_kwargs())

# Soft nudge if production secrets look missing
if settings.env in ("production", "prod") and not (settings.admin_api_token or "").strip():
    # Avoid hard-failing boot; ops should set CUAGENT_ADMIN_TOKEN.
    pass

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(legal_router)
app.include_router(content_router)
app.include_router(visits_router)
app.include_router(feedback_router)
app.include_router(agent_router)
app.include_router(expression_router)
app.include_router(genes_router)
app.include_router(genomes_router)
app.include_router(proteins_router)
app.include_router(literature_router)
