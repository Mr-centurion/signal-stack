import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.scheduler.manager import scheduler_manager
from backend.api.routes import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    init_db()
    # Restore persisted LLM provider if saved
    from backend.database import SessionLocal
    from backend.models import Setting
    from backend.services.llm_client import llm_client
    if os.environ.get("APP_ENV") != "test":
        try:
            with SessionLocal() as db:
                llm_setting = db.query(Setting).filter_by(key="llm_provider").first()
                if llm_setting and llm_setting.value:
                    llm_client.set_provider(llm_setting.value)
        except Exception as e:
            print(f"Could not restore LLM provider setting: {e}")

    # Start APScheduler
    scheduler_manager.start()
    yield
    # Clean shutdown
    scheduler_manager.shutdown()

app = FastAPI(
    title="Signal Stack API",
    description="Company Intelligence and Monday Morning Brief Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router, prefix="/api")

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Signal Stack API"
    }

@app.get("/")
def root():
    return {
        "app": "Signal Stack",
        "description": "Company Intelligence & Monday Morning Brief Engine",
        "docs": "/docs",
        "status": "online"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
