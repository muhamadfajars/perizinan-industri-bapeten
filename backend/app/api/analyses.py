import json
from fastapi import APIRouter, Depends, HTTPException
from .. import storage
from ..services.jobs import POOL, SUBMIT_LOCK, _run
from .dependencies import authorize, must_app

router = APIRouter()


@router.post("/api/v1/applications/{aid}/analyses", dependencies=[Depends(authorize)])
def start_analysis(aid: str):
    must_app(aid)
    with SUBMIT_LOCK:
        docs = storage.documents(aid)
        forms = [d for d in docs if d["category"] == "formulir"]
        if len(forms) != 1:
            raise HTTPException(
                422, "Wajib tepat satu Formulir Permohonan PDF untuk acuan analisis"
            )
        with storage.db() as con:
            active = storage.row(
                con,
                "SELECT id,status FROM jobs WHERE app_id=? AND status IN ('queued','running') ORDER BY created DESC LIMIT 1",
                (aid,),
            )
        if active:
            raise HTTPException(409, "Analisis sudah berjalan untuk permohonan ini")
        jid = storage.create_job(aid)
        POOL.submit(_run, jid, aid)
    return {"job_id": jid, "status": "queued", "progress": 0}


@router.get("/api/v1/applications/{aid}/jobs/latest", dependencies=[Depends(authorize)])
def latest_job(aid: str):
    must_app(aid)
    j = storage.get_latest_job(aid)
    return {
        "job": {k: j[k] for k in ("id", "status", "progress", "message", "error")} if j else None
    }


@router.get("/api/v1/applications/{aid}/jobs/{jid}/results", dependencies=[Depends(authorize)])
def job_results(aid: str, jid: str):
    must_app(aid)
    j = storage.get_job(jid, aid)
    if not j or j["status"] != "completed" or not j.get("result"):
        raise HTTPException(404, "Hasil analisis belum tersedia atau sudah tidak berlaku")
    result = json.loads(j["result"])
    if result is None:
        raise HTTPException(404, "Hasil analisis sudah tidak berlaku")
    return result


@router.get("/api/v1/applications/{aid}/jobs/{jid}", dependencies=[Depends(authorize)])
def job(aid: str, jid: str):
    must_app(aid)
    j = storage.get_job(jid, aid)
    if not j:
        raise HTTPException(404, "Job tidak ditemukan")
    return {k: j[k] for k in ("id", "status", "progress", "message", "error", "created", "updated")}


@router.get("/api/v1/applications/{aid}/results", dependencies=[Depends(authorize)])
def results(aid: str):
    must_app(aid)
    result = storage.latest_result(aid)
    if result is None:
        raise HTTPException(404, "Belum ada analisis yang selesai")
    return result
