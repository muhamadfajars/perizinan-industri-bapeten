from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
import asyncio
import os
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from .. import classifier
from ..config import MAX_FILE, MAX_DOCS, EXT
from .dependencies import authorize

router = APIRouter()


def _classification_concurrency() -> int:
    """Return validated max concurrent document classification inspections."""
    raw = os.getenv("BAPETEN_CLASSIFY_CONCURRENCY", "2")
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("BAPETEN_CLASSIFY_CONCURRENCY harus antara 1 dan 16") from exc
    if not 1 <= limit <= 16:
        raise ValueError("BAPETEN_CLASSIFY_CONCURRENCY harus antara 1 dan 16")
    return limit


_classification_slots = asyncio.Semaphore(_classification_concurrency())


async def inspect_file(file):
    if Path(file.filename or "").suffix.lower() not in EXT:
        raise HTTPException(415, "Format dokumen tidak didukung")
    async with _classification_slots:
        content = await file.read(MAX_FILE + 1)
        if not content:
            raise HTTPException(422, "Berkas kosong")
        if len(content) > MAX_FILE:
            raise HTTPException(413, "Ukuran berkas melebihi batas upload")
        return await run_in_threadpool(classifier.classify_document, file.filename, content)


@router.post("/api/v1/classify", dependencies=[Depends(authorize)])
async def classify_file(file: UploadFile | None = File(None), filename: str | None = Form(None)):
    name = (file.filename if file else filename) or ""
    if not name:
        raise HTTPException(422, "Nama berkas harus disertakan")
    if file:
        return await inspect_file(file)
    return classifier.classify_document(name)


@router.post("/api/v1/classify-batch", dependencies=[Depends(authorize)])
async def classify_batch(files: list[UploadFile] = File(...)):
    results = []
    if len(files) > MAX_DOCS:
        raise HTTPException(413, "Jumlah dokumen melebihi batas upload")
    for f in files:
        results.append(await inspect_file(f))
    return {"results": results}
