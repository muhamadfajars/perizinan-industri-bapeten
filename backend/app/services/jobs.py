import os
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from .. import storage

POOL = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("BAPETEN_ANALYSIS_WORKERS", "1"))))
SUBMIT_LOCK = Lock()


def _run(jid, aid):
    from ..analysis.pipeline import analyze_application
    from .. import performance

    try:
        storage.update_job(jid, status="running", progress=1, message="Memulai parser formulir")
        with performance.analysis_session():
            result = analyze_application(
                aid, lambda p, msg: storage.update_job(jid, progress=p, message=msg)
            )
            result["job_id"] = jid
            storage.update_job(
                jid,
                status="completed",
                progress=100,
                message="Analisis selesai",
                result=result,
            )
    except Exception as exc:
        storage.update_job(
            jid,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            message="Analisis gagal",
        )
