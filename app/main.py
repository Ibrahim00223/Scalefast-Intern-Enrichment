from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import contacts, lookup


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Intern Enrichment — Scalefast",
    description="Vérification et déduplication de contacts internes",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contacts.router, prefix="/api/v1")
app.include_router(lookup.router, prefix="/api/v1")

# Serve the HTML interface on /
STATIC_DIR = Path(__file__).parent.parent / "static"

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
