"""DRAS web app: queue dissertations, get editable AI grades, download the reports.

Run:  uv run uvicorn server:app --port 8502

Every upload is a job saved under data/jobs/<id>/ (source file, page-view PDF, job.json), so graded
work and the assessor's edits survive a refresh or a restart.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from time import time

import mammoth
import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from grader import CHECKLIST, SCORE_MAXIMA, STUDENT_SECTIONS, Review, grade
from reports import Assessor, combined_report, confidential_report, main_report

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_UPLOAD = 60 * 1024 * 1024
WORKERS = int(os.getenv("DRAS_WORKERS", "3"))  # dissertations graded at the same time
FRONTEND = Path(__file__).parent / "frontend"
JOBS_DIR = Path(os.getenv("DRAS_DATA", Path(__file__).parent / "data")) / "jobs"

app = FastAPI(title="DRAS")
pool = ThreadPoolExecutor(max_workers=WORKERS)
jobs: dict[str, dict] = {}
write_lock = threading.Lock()


class Report(BaseModel):
    review: Review
    assessor: Assessor = Assessor()


class Edit(Report):
    confirmed: bool = False


# ---- rendering a Word file as pages --------------------------------------------------

WORD_APP = Path("/Applications/Microsoft Word.app")
WORD_BOX = Path.home() / "Library/Group Containers/UBF8T346G9.Office"  # the only place Word's sandbox lets it read
WORD_SCRIPT = """on run argv
  tell application "Microsoft Word"
    set d to open file name (item 1 of argv)
    save as d file name (item 2 of argv) file format format PDF
    close d saving no
  end tell
end run"""
word_lock = threading.Lock()  # one document at a time through Word


def word_pdf(name: str, data: bytes) -> bytes | None:
    """Word's own layout, so page breaks match what the assessor would see in Word."""
    if not (WORD_APP.exists() and WORD_BOX.exists()):
        return None
    work = WORD_BOX / f"dras-{uuid.uuid4().hex}"
    work.mkdir()
    try:
        src, out = work / f"source{Path(name).suffix.lower()}", work / "source.pdf"
        src.write_bytes(data)
        with word_lock:
            try:
                subprocess.run(["osascript", "-e", WORD_SCRIPT, str(src), str(out)],
                               capture_output=True, timeout=180, check=False)
            except subprocess.TimeoutExpired:
                return None
        return out.read_bytes() if out.exists() else None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def libreoffice_pdf(name: str, data: bytes) -> bytes | None:
    """Fallback renderer when Word is not available; page breaks can differ slightly."""
    soffice = shutil.which("soffice")
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"source{Path(name).suffix.lower()}"
        src.write_bytes(data)
        try:
            subprocess.run([soffice, f"-env:UserInstallation=file://{tmp}/profile", "--headless", "--convert-to", "pdf",
                            "--outdir", tmp, str(src)], capture_output=True, timeout=180, check=False)
        except subprocess.TimeoutExpired:
            return None
        out = Path(tmp) / "source.pdf"
        return out.read_bytes() if out.exists() else None


def render(name: str, data: bytes) -> tuple[bytes | None, str]:
    if name.lower().endswith(".pdf"):
        return data, "pdf"
    if view := word_pdf(name, data):
        return view, "word"
    if view := libreoffice_pdf(name, data):
        return view, "libreoffice"
    return None, "html"


# ---- jobs ----------------------------------------------------------------------------


def save(job: dict) -> None:
    with write_lock:
        path = JOBS_DIR / job["id"] / "job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job))
        tmp.replace(path)


def source_of(job_id: str) -> Path:
    return next((JOBS_DIR / job_id).glob("source.*"))


def process(job_id: str) -> None:
    job = jobs[job_id]
    try:
        job.update(status="working", error="")
        data = source_of(job_id).read_bytes()
        review = grade(job["filename"], data)
        view, renderer = render(job["filename"], data)
        if view:
            (JOBS_DIR / job_id / "view.pdf").write_bytes(view)
        job.update(review=review.model_dump(), renderer=renderer, status="ready")
    except Exception as exc:  # a failed job must never stop the rest of the batch
        job.update(status="error", error=str(exc) or "Grading failed. Try again.")
    if job_id in jobs:  # it may have been removed while grading
        save(job)


def summary(job: dict) -> dict:
    review = job.get("review")
    return {
        "id": job["id"], "filename": job["filename"], "status": job["status"], "error": job["error"],
        "candidate": review["candidate_name"] if review else "", "title": review["title"] if review else "",
        "total": sum(s["score"] for s in review["scores"]) if review else None,
        "confirmed": job["confirmed"], "created": job["created"],
    }


def load_jobs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(JOBS_DIR.glob("*/job.json")):
        job = json.loads(path.read_text())
        jobs[job["id"]] = job
        if job["status"] in ("queued", "working"):  # the server stopped mid-grade: start it again
            job["status"] = "queued"
            pool.submit(process, job["id"])


def get_job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(404, "That dissertation is no longer available. Upload it again.")
    return jobs[job_id]


load_jobs()


@app.get("/api/config")
def config() -> dict:
    return {"checklist": CHECKLIST, "score_maxima": SCORE_MAXIMA, "sections": STUDENT_SECTIONS,
            "assessor": Assessor().model_dump()}


@app.post("/api/jobs")
def create_jobs(files: list[UploadFile] = File(...)) -> dict:
    created, rejected = [], []
    for file in files:
        name = Path(file.filename or "dissertation").name
        data = file.file.read(MAX_UPLOAD + 1)
        if not name.lower().endswith((".pdf", ".docx", ".doc")):
            rejected.append({"filename": name, "reason": "Only PDF, DOC and DOCX files can be graded."})
        elif len(data) > MAX_UPLOAD:
            rejected.append({"filename": name, "reason": "The file is over 60 MB."})
        else:
            job_id = uuid.uuid4().hex[:12]
            (JOBS_DIR / job_id).mkdir(parents=True)
            (JOBS_DIR / job_id / f"source{Path(name).suffix.lower()}").write_bytes(data)
            job = {"id": job_id, "filename": name, "status": "queued", "error": "", "renderer": "",
                   "review": None, "assessor": Assessor().model_dump(), "confirmed": False, "created": time()}
            jobs[job_id] = job
            save(job)
            pool.submit(process, job_id)
            created.append(summary(job))
    return {"jobs": created, "rejected": rejected}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return sorted((summary(j) for j in jobs.values()), key=lambda j: j["created"])


@app.get("/api/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    return get_job(job_id)


@app.put("/api/jobs/{job_id}")
def edit_job(job_id: str, body: Edit) -> dict:
    job = get_job(job_id)
    for s in body.review.scores:
        s.score = max(0, min(s.score, SCORE_MAXIMA.get(s.criterion, s.score)))
    job.update(review=body.review.model_dump(), assessor=body.assessor.model_dump(), confirmed=body.confirmed)
    save(job)
    return summary(job)


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job["status"] != "error":
        raise HTTPException(409, "Only failed dissertations can be retried.")
    job.update(status="queued", error="")
    save(job)
    pool.submit(process, job_id)
    return summary(job)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    get_job(job_id)
    jobs.pop(job_id)
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    return {"deleted": job_id}


# ---- the document ------------------------------------------------------------------


def view_pdf(job_id: str) -> bytes | None:
    path = JOBS_DIR / job_id / "view.pdf"
    return path.read_bytes() if path.exists() else None


@app.get("/api/file/{job_id}")
def page_view(job_id: str) -> Response:
    get_job(job_id)
    view = view_pdf(job_id)
    if view is None:
        raise HTTPException(404, "No page view for this document.")
    return Response(view, media_type="application/pdf")


@app.get("/api/html/{job_id}")
def as_html(job_id: str) -> Response:
    job = get_job(job_id)
    src = source_of(job_id)
    if src.suffix == ".docx":
        html = mammoth.convert_to_html(BytesIO(src.read_bytes())).value
    else:  # .doc: the macOS converter keeps tables
        html = subprocess.run(["textutil", "-convert", "html", "-stdout", str(src)],
                              capture_output=True, text=True, check=False).stdout
    return Response(html or f"<p>{job['filename']} could not be displayed.</p>", media_type="text/html")


def _snippet(quote: str, words: int) -> str:
    return " ".join(re.sub(r"[“”]", '"', quote).replace("’", "'").split()[:words])


@app.get("/api/locate/{job_id}")
def locate(job_id: str, q: str) -> dict:
    """Where a quoted passage sits in the page view: page size plus highlight rectangles, in PDF points."""
    get_job(job_id)
    view = view_pdf(job_id)
    if view is None:
        return {"page": None, "rects": []}
    with pymupdf.open(stream=view, filetype="pdf") as pdf:
        for words in (12, 6, 4):  # long quotes break on line ends; shorter openings still match
            snippet = _snippet(q, words)
            if not snippet:
                break
            for number, page in enumerate(pdf, 1):
                rects = page.search_for(snippet)
                if rects:
                    return {"page": number, "width": page.rect.width, "height": page.rect.height,
                            "rects": [[r.x0, r.y0, r.x1, r.y1] for r in rects]}
    return {"page": None, "rects": []}


# ---- reports -----------------------------------------------------------------------


@app.post("/api/report/{kind}")
def report(kind: str, body: Report) -> Response:
    review = body.review
    for s in review.scores:
        s.score = max(0, min(s.score, SCORE_MAXIMA.get(s.criterion, s.score)))
    if kind == "assessment":
        data = main_report(review)
    elif kind == "confidential":
        data = confidential_report(review, body.assessor)
    elif kind == "combined":
        data = combined_report(review, body.assessor)
    else:
        raise HTTPException(404, "Unknown report.")
    return Response(data, media_type=DOCX)


class Frontend(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"  # always revalidate, so an update shows up on refresh
        return response


app.mount("/", Frontend(directory=FRONTEND, html=True), name="frontend")
