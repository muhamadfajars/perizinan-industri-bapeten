import hmac
import os
import re
from fastapi import Header, HTTPException
from ..config import TOKEN
from .. import storage


def authorize(authorization: str | None = Header(default=None)):
    if os.environ.get("BAPETEN_ALLOW_UNAUTHENTICATED_LOCAL_DEV") == "1":
        return
    if not TOKEN:
        raise HTTPException(503, "BAPETEN_API_TOKEN belum disetel pada server")
    candidate = (
        authorization.removeprefix("Bearer ").strip()
        if authorization and authorization.startswith("Bearer ")
        else ""
    )
    if not hmac.compare_digest(candidate, TOKEN):
        raise HTTPException(401, "Token akses tidak valid")


def must_app(aid):
    if not re.fullmatch(r"[0-9a-f]{32}", aid) or not storage.app_exists(aid):
        raise HTTPException(404, "Permohonan tidak ditemukan")
