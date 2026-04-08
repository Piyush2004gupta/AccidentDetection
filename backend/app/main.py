from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging_config import setup_logging

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(title=settings.app_name)

# Hardened CORS for production
allowed_origins = [origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router, prefix="/api")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

# Serve frontend static files
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
