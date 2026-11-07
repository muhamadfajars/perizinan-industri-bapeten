import hashlib
from pathlib import Path
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    Depends,
    HTTPException,
    BackgroundTasks,
)
from fastapi.responses import FileResponse
from ..config import CATEGORIES, EXT, MAX_FILE, MAX_DOCS
from .. import storage, classifier
from ..schemas import DocumentCategoryUpdate
from ..services.jobs import SUBMIT_LOCK
from .dependencies import authorize, must_app

router = APIRouter()


@router.get("/api/v1/applications/{aid}/documents", dependencies=[Depends(authorize)])
def list_documents(aid: str):
    must_app(aid)
    return {"documents": storage.documents(aid)}


@router.post("/api/v1/applications/{aid}/documents", dependencies=[Depends(authorize)])
async def upload(
    aid: str,
    category: str | None = Form(None),
    subtype: str | None = Form(None),
    file: UploadFile = File(...),
):
    must_app(aid)
    j = storage.get_job_latest_running(aid) if hasattr(storage, "get_job_latest_running") else None
    if j:
        raise HTTPException(409, "Tidak dapat mengunggah saat analisis aktif")
    if len(storage.documents(aid)) >= MAX_DOCS:
        raise HTTPException(413, "Batas jumlah dokumen tercapai")
    filename = Path(file.filename or "").name[:180]
    ext = Path(filename).suffix.lower()
    if not filename or ext not in EXT:
        raise HTTPException(415, "Format dokumen tidak didukung")

    temp_name = storage.make_id() + ext
    folder = storage.ROOT / "uploads" / aid
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / temp_name
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE:
                    raise HTTPException(413, f"File melebihi {MAX_FILE // (1024 * 1024)} MB")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "File kosong")
        with target.open("rb") as src:
            head = src.read(16)
        if ext == ".pdf" and not head.startswith(b"%PDF-"):
            raise HTTPException(415, "File bukan PDF valid")
        if ext == ".docx" and not head.startswith(b"PK"):
            raise HTTPException(415, "File bukan DOCX valid")

        # Auto-classify if category is missing, empty, or 'auto'
        if not category or category.strip() == "" or category == "auto":
            with target.open("rb") as src:
                bytes_content = src.read()
            detected = classifier.classify_document(filename, bytes_content)
            if detected["category"] == "unknown":
                raise HTTPException(
                    422,
                    f'Kategori dokumen "{filename}" tidak terdeteksi otomatis. Silakan tentukan kategori dokumen.',
                )
            category = detected["category"]
            if not subtype:
                subtype = detected.get("subtype")

        if category not in CATEGORIES:
            raise HTTPException(422, "Kategori tidak dikenal")
        if category == "formulir" and ext != ".pdf":
            raise HTTPException(415, "Formulir acuan saat ini harus PDF")
        if category == "personel" and not subtype:
            raise HTTPException(422, "Pilih subjenis dokumen personel")

        # Do not deduplicate different categories or uploads silently.
        did = storage.add_document(
            aid, category, subtype, filename, size, digest.hexdigest(), temp_name
        )
        return {"document": next(d for d in storage.documents(aid) if d["id"] == did)}
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.patch("/api/v1/applications/{aid}/documents/{did}", dependencies=[Depends(authorize)])
def update_document_category(aid: str, did: str, payload: DocumentCategoryUpdate):
    must_app(aid)
    with SUBMIT_LOCK:
        if storage.get_job_latest_running(aid):
            raise HTTPException(409, "Tidak dapat mengubah kategori saat analisis aktif")
        doc = storage.document(did, aid)
        if not doc:
            raise HTTPException(404, "Berkas tidak ditemukan")
        if payload.category not in CATEGORIES:
            raise HTTPException(422, "Kategori tidak dikenal")
        if payload.category == "formulir" and Path(doc["filename"]).suffix.lower() != ".pdf":
            raise HTTPException(415, "Formulir acuan saat ini harus PDF")
        subtype = (payload.subtype or "").strip() if payload.category == "personel" else None
        if payload.category == "personel" and not subtype:
            raise HTTPException(422, "Pilih subjenis dokumen personel")
        storage.update_document_category(did, aid, payload.category, subtype)
        return {"document": next(d for d in storage.documents(aid) if d["id"] == did)}


@router.delete("/api/v1/applications/{aid}/documents/{did}", dependencies=[Depends(authorize)])
def remove_document(aid: str, did: str):
    must_app(aid)
    j = storage.get_job_latest_running(aid) if hasattr(storage, "get_job_latest_running") else None
    if j:
        raise HTTPException(409, "Tidak dapat menghapus saat analisis aktif")
    if not storage.delete_document(did, aid):
        raise HTTPException(404, "Berkas tidak ditemukan")
    return {"deleted": True}


@router.get("/api/v1/applications/{aid}/documents/{did}/file", dependencies=[Depends(authorize)])
def get_document(aid: str, did: str):
    must_app(aid)
    d = storage.document(did, aid)
    if not d:
        raise HTTPException(404, "Berkas tidak ditemukan")
    path = storage.file_path(d)
    if not path.is_file():
        raise HTTPException(404, "Berkas fisik tidak ditemukan")
    return FileResponse(
        path,
        media_type="application/pdf"
        if d["filename"].lower().endswith(".pdf")
        else "application/octet-stream",
        filename=d["filename"],
        content_disposition_type="inline"
        if d["filename"].lower().endswith(".pdf")
        else "attachment",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/api/v1/applications/{aid}/documents/{did}/evidence-page/{page_number}",
    dependencies=[Depends(authorize)],
)
def get_evidence_page(aid: str, did: str, page_number: int):
    """Private rendering of EXACTLY ONE source page; never stream the full PDF."""
    from fastapi.responses import Response
    import fitz

    must_app(aid)
    doc = storage.document(did, aid)
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    source = storage.file_path(doc)
    if not source.is_file():
        raise HTTPException(404, "File tidak tersedia")
    # No arbitrary paths, no guessing page number, bounded image memory.
    if source.suffix.lower() != ".pdf":
        raise HTTPException(415, "Halaman bukti hanya tersedia untuk PDF")
    if page_number < 1:
        raise HTTPException(422, "Nomor halaman tidak valid")
    with fitz.open(str(source)) as pdf:
        if page_number > len(pdf):
            raise HTTPException(404, "Halaman bukti tidak ditemukan")
        pg = pdf[page_number - 1]
        factor = min(1.7, 2000 / max(pg.rect.width, pg.rect.height))
        pix = pg.get_pixmap(matrix=fitz.Matrix(factor, factor), alpha=False, colorspace=fitz.csRGB)
        image = pix.tobytes("jpeg", jpg_quality=80)
    return Response(
        image,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/api/v1/applications/{aid}/documents/{did}/preview",
    dependencies=[Depends(authorize)],
)
def preview_document(aid: str, did: str, background_tasks: BackgroundTasks):
    """Authenticated inline preview. Temporary DOCX conversion never replaces upload."""
    must_app(aid)
    d = storage.document(did, aid)
    if not d:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    path = storage.file_path(d)
    if not path.is_file():
        raise HTTPException(404, "Berkas fisik tidak ditemukan")
    ext = path.suffix.lower()
    if ext == ".docx":
        import sys

        engine = str(Path(__file__).resolve().parents[2] / "engine")
        if engine not in sys.path:
            sys.path.insert(0, engine)
        from src.extraction.office_conversion import convert_word_to_pdf

        try:
            converted = convert_word_to_pdf(str(path))
        except Exception as exc:
            raise HTTPException(503, f"Pratinjau DOCX memerlukan LibreOffice: {exc}") from exc
        background_tasks.add_task(Path(converted).unlink, missing_ok=True)
        return FileResponse(
            converted,
            media_type="application/pdf",
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    if ext == ".pdf":
        return FileResponse(
            path,
            media_type="application/pdf",
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        media = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }[ext]
        return FileResponse(
            path,
            media_type=media,
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    raise HTTPException(415, "Pratinjau format ini belum didukung")
