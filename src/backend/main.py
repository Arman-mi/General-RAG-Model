from __future__ import annotations

import os
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pipeline import index_site
from rag import ask_site
from schemas import ChatRequest, ChatResponse, SiteIndexRequest, SiteIndexResponse, SiteStatusResponse

app = FastAPI(title="TwoDots RAG API")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "*")

origins = [
    "https://twodots-rag-model.onrender.com",
    "http://localhost:3000",   
    "http://127.0.0.1:3000",
]

if frontend_origin != "*" and frontend_origin not in origins:
    origins.append(frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent  # src/
RUNS_DIR = BASE_DIR / "data" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

_lock = Lock()
_jobs: dict[str, dict] = {}
_active_site_id: str | None = None


def _set_job(site_id: str, **fields) -> None:
    with _lock:
        job = _jobs.get(site_id, {"site_id": site_id})
        job.update(fields)
        _jobs[site_id] = job


def _get_job(site_id: str) -> dict | None:
    with _lock:
        return _jobs.get(site_id)


def _set_active(site_id: str) -> None:
    global _active_site_id
    with _lock:
        _active_site_id = site_id


def _get_active() -> str | None:
    with _lock:
        return _active_site_id


def _cleanup_other_runs(keep_site_id: str) -> None:
    for child in RUNS_DIR.glob("*"):
        if not child.is_dir():
            continue
        if child.name == keep_site_id:
            continue
        shutil.rmtree(child, ignore_errors=True)


def _run_indexing(site_id: str, url: str, max_pages: int) -> None:
    _set_job(site_id, status="running", url=url)
    try:
        work_dir = RUNS_DIR / site_id
        info = index_site(url=url, work_dir=work_dir, max_pages=max_pages)
        _set_job(
            site_id,
            status="done",
            message=f"Indexed {info['pages']} pages / {info['chunks']} chunks.",
            persist_dir=info["persist_dir"],
            collection_name=info["collection_name"],
            start_url=info["start_url"],
        )
        _set_active(site_id)
        _cleanup_other_runs(keep_site_id=site_id)
    except Exception as e:
        _set_job(site_id, status="error", message=str(e))


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/site", response_model=SiteIndexResponse)
def create_site_index(request: SiteIndexRequest, background: BackgroundTasks) -> SiteIndexResponse:
    site_id = uuid4().hex
    _set_job(site_id, status="queued", url=request.url)
    background.add_task(_run_indexing, site_id, request.url, request.max_pages)
    return SiteIndexResponse(site_id=site_id)


@app.get("/api/site/{site_id}", response_model=SiteStatusResponse)
def get_site_status(site_id: str) -> SiteStatusResponse:
    job = _get_job(site_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown site_id")
    return SiteStatusResponse(
        site_id=site_id,
        status=job.get("status", "queued"),
        url=job.get("url"),
        message=job.get("message"),
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    site_id = request.site_id or _get_active()
    if not site_id:
        raise HTTPException(status_code=400, detail="No site indexed yet. Call POST /api/site first.")

    job = _get_job(site_id)
    if not job or job.get("status") != "done":
        raise HTTPException(status_code=400, detail="Site is not ready yet.")

    answer, citations = ask_site(
        request.message,
        persist_dir=job["persist_dir"],
        collection_name=job["collection_name"],
        site_url=job.get("start_url") or job.get("url"),
    )
    return ChatResponse(response=answer, citations=citations)
