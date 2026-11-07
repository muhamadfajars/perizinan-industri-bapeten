"""FastAPI entry point and middleware wiring."""

from __future__ import annotations
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import TOKEN as TOKEN
from . import storage, vpn_access
from .api import applications, documents, classification, analyses


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    if vpn_access.enabled():
        vpn_access.init_vpn_db()
    storage.recover_stale_jobs()
    yield


app = FastAPI(
    title="BAPETEN AI Evaluator API",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
origins = [
    v.strip()
    for v in os.environ.get(
        "BAPETEN_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if v.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Bapeten-Vpn-User"],
)

app.include_router(applications.router)
app.include_router(documents.router)
app.include_router(classification.router)
app.include_router(analyses.router)

# Optional single-port intranet deployment: a prebuilt React dist/ served by FastAPI.
# This is intentionally registered AFTER every /api route so the API takes priority.
# The static bundle contains no uploaded source documents or authentication tokens.
_frontend_dist = os.environ.get("BAPETEN_FRONTEND_DIST", "").strip()
if _frontend_dist:
    from fastapi.staticfiles import StaticFiles

    _frontend_path = Path(_frontend_dist).expanduser().resolve()
    if not (_frontend_path / "index.html").is_file():
        raise RuntimeError("BAPETEN_FRONTEND_DIST harus menunjuk frontend/dist berisi index.html")
    app.mount("/", StaticFiles(directory=str(_frontend_path), html=True), name="frontend")

# VPN reverse proxy boundary. Must register before ASGI application starts.
app.middleware("http")(vpn_access.gateway_middleware)

# Reverse proxy subpath middleware.
# When deployed behind Nginx (e.g. http://192.168.30.75/rdi1/), Nginx forwards
# requests with the /rdi1 prefix intact. This middleware strips the prefix so
# FastAPI and mounted static files handle the request identically to root path,
# while still supporting direct root access (e.g. via SSH tunnel localhost:8001).
# Registered after gateway_middleware so it executes FIRST on incoming requests.
_URL_PREFIXES = tuple(
    p.strip().rstrip("/")
    for p in os.environ.get("BAPETEN_URL_PREFIXES", "/rdi1").split(",")
    if p.strip()
)


@app.middleware("http")
async def subpath_prefix_middleware(request: Request, call_next):
    path = request.scope.get("path", "")
    if path in _URL_PREFIXES:
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"{path}/{query}", status_code=307)
    for prefix in _URL_PREFIXES:
        if path.startswith(prefix + "/"):
            new_path = path[len(prefix) :] or "/"
            request.scope["path"] = new_path
            if "raw_path" in request.scope:
                request.scope["raw_path"] = new_path.encode("latin-1")
            break
    return await call_next(request)
