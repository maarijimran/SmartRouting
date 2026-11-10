from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.analytics.router import router as analytics_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.db.session import init_db
from app.documents.router import router as documents_router
from app.feedback.router import router as feedback_router
from app.gateway.router import router as gateway_router
from app.keys.router import router as keys_router
from app.privacy.router import router as privacy_router
from app.registry.router import router as registry_router

app = FastAPI(title="SmartRoute API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(auth_router)
app.include_router(keys_router)
app.include_router(registry_router)
app.include_router(documents_router)
app.include_router(gateway_router)
app.include_router(privacy_router)
app.include_router(feedback_router)
app.include_router(analytics_router)
app.include_router(admin_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
