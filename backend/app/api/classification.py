from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from .. import classifier
from .dependencies import authorize

router = APIRouter()


@router.post("/api/v1/classify", dependencies=[Depends(authorize)])
async def classify_file(file: UploadFile | None = File(None), filename: str | None = Form(None)):
    name = (file.filename if file else filename) or ""
    if not name:
        raise HTTPException(422, "Nama berkas harus disertakan")
    content = None
    if file:
        content = await file.read()
    res = classifier.classify_document(name, content)
    return res


@router.post("/api/v1/classify-batch", dependencies=[Depends(authorize)])
async def classify_batch(files: list[UploadFile] = File(...)):
    results = []
    for f in files:
        name = f.filename or ""
        content = await f.read()
        res = classifier.classify_document(name, content)
        results.append(res)
    return {"results": results}
