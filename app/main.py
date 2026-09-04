import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.routes import router as api_router
from app.db.repository import repository
from app.engine.synthetic import generate_synthetic_batch
from app.engine.classifier import decline_classifier
from app.engine.compliance import compliance_engine
from app.engine.clock import virtual_clock

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-populate initial synthetic batch if database is empty
    existing = repository.get_all_mandates()
    if not existing:
        records = generate_synthetic_batch(count=60, seed=42)
        repository.save_mandates(records)
        now = virtual_clock.get_now()
        for r in records:
            cls = decline_classifier.classify(r.raw_decline_code, r.raw_decline_message)
            r.decline_type = cls.get("decline_type", r.decline_type)
            decision = compliance_engine.evaluate(r, current_time=now)
            event = compliance_engine.apply_decision(r, decision, current_time=now)
            repository.save_audit_event(event)
            repository.save_mandate(r)
    yield

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="PACT: Proactive AutoPay Compliance & Tracking (Track 03)",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Mount static files directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "PACT API is running. Please access the dashboard once frontend is installed."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
