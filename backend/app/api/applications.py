from fastapi import APIRouter, Request, Depends
from ..config import TOKEN
from .. import storage, vpn_access
from .dependencies import authorize

router = APIRouter()


@router.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "api_version": "v2",
        "engine": "BAPETEN v46",
        "authentication_configured": bool(TOKEN),
    }


@router.post("/api/v1/applications", dependencies=[Depends(authorize)])
def create_application(request: Request):
    aid = storage.create_application()
    if vpn_access.enabled():
        vpn_access.register_new(aid, request.headers.get("x-bapeten-vpn-user", "").strip())
    return {"application_id": aid}
