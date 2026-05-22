from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.api import projects, samples, upload, analysis, results, metadata, file_manager, comparative


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="RADAR API",
    description="Resistome Analysis, Detection, and Annotation Resource - "
                "A bioinformatics platform for antibiotic resistance analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix="/api")
app.include_router(samples.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(metadata.router, prefix="/api")
app.include_router(file_manager.router, prefix="/api")
app.include_router(comparative.router, prefix="/api")


@app.get("/")
def health_check():
    return {"status": "ok", "name": "RADAR"}
