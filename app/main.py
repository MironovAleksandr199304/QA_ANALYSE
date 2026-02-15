import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth import hash_password, require_user_id, verify_password
from .database import Base, SessionLocal, engine, get_db
from .models import Analysis, Job, Org, Resume, User
from .services.parser import extract_text
from .services.scoring import analyze_resume

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
STORAGE_DIR = BASE_DIR / "storage"

STATIC_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="QA Resume Analyzer MVP")
app.add_middleware(SessionMiddleware, secret_key="mvp-secret-key")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def current_user(request: Request, db: Session) -> User:
    user_id = require_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def run_analysis(analysis_id: int, path: str, db_factory):
    db = db_factory()
    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            return

        analysis.status = "processing"
        db.commit()

        text = extract_text(path)
        result = analyze_resume(text)

        analysis.status = "done"
        analysis.score_total = result["score_total"]
        analysis.score_hard = result["score_hard"]
        analysis.score_soft = result["score_soft"]
        analysis.score_sanity = result["score_sanity"]
        analysis.label = result["label"]
        analysis.details_json = result["details_json"]
        db.commit()
    except Exception:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis:
            analysis.status = "failed"
            db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/jobs", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    org_name: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already exists"})

    org = db.query(Org).filter(Org.name == org_name).first()
    if not org:
        org = Org(name=org_name, plan="free")
        db.add(org)
        db.commit()
        db.refresh(org)

    user = User(email=email, password_hash=hash_password(password), org_id=org.id, role="admin")
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/jobs", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    request.session["user_id"] = user.id
    return RedirectResponse(url="/jobs", status_code=302)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    jobs = db.query(Job).filter(Job.org_id == user.org_id).order_by(Job.id.desc()).all()
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs, "user": user})


@app.get("/jobs/new", response_class=HTMLResponse)
def jobs_new_page(request: Request, db: Session = Depends(get_db)):
    _ = current_user(request, db)
    return templates.TemplateResponse("job_new.html", {"request": request})


@app.post("/jobs")
def create_job(
    request: Request,
    title: str = Form(...),
    description_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)

    ext = Path(description_file.filename or "").suffix.lower()
    if ext not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Description file must be PDF or DOCX")

    content = description_file.file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Description file is too large (max 5MB)")

    file_name = f"job_desc_{uuid4().hex}{ext}"
    file_path = STORAGE_DIR / file_name
    file_path.write_bytes(content)
    description_text = extract_text(str(file_path)).strip()
    if not description_text:
        raise HTTPException(status_code=400, detail="Description file does not contain readable text")

    job = Job(org_id=user.org_id, title=title, description=description_text, config_json="{}", created_by=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=302)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = current_user(request, db)
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == user.org_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    analyses = (
        db.query(Analysis)
        .join(Resume, Analysis.resume_id == Resume.id)
        .filter(Analysis.job_id == job.id, Resume.org_id == user.org_id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    view_rows = []
    for row in analyses:
        details = json.loads(row.details_json or "{}") if row.details_json else {}
        view_rows.append({"analysis": row, "resume": row.resume, "details": details})

    return templates.TemplateResponse("job_detail.html", {"request": request, "job": job, "rows": view_rows})

@app.get("/jobs/{job_id}/analyses/status")
def job_analyses_status(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = current_user(request, db)
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == user.org_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    analyses = (
        db.query(Analysis)
        .join(Resume, Analysis.resume_id == Resume.id)
        .filter(Analysis.job_id == job.id, Resume.org_id == user.org_id)
        .all()
    )

    return {
        "items": [
            {
                "analysis_id": a.id,
                "status": a.status,
                "score_total": a.score_total,
                "score_hard": a.score_hard,
                "score_soft": a.score_soft,
                "score_sanity": a.score_sanity,
                "label": a.label,
            }
            for a in analyses
        ]
    }


@app.post("/jobs/{job_id}/resumes/upload")
def upload_resume(
    request: Request,
    background_tasks: BackgroundTasks,
    job_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == user.org_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for file in files:
        content = file.file.read()
        if len(content) > 5 * 1024 * 1024:
            continue

        ext = Path(file.filename).suffix.lower()
        if ext not in {".pdf", ".docx", ".txt"}:
            continue

        file_name = f"{uuid4().hex}{ext}"
        file_path = STORAGE_DIR / file_name
        file_path.write_bytes(content)

        text_hash = hashlib.sha256(content).hexdigest()
        resume = Resume(
            org_id=user.org_id,
            filename=file.filename,
            storage_url=str(file_path),
            text_hash=text_hash,
            uploaded_by=user.id,
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)

        analysis = Analysis(resume_id=resume.id, job_id=job.id, status="queued", label="red")
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        background_tasks.add_task(run_analysis, analysis.id, str(file_path), db_factory=SessionLocal)

    return RedirectResponse(url=f"/jobs/{job.id}", status_code=302)


@app.get("/jobs/{job_id}/export.csv")
def export_csv(request: Request, job_id: int, db: Session = Depends(get_db)):
    user = current_user(request, db)
    job = db.query(Job).filter(Job.id == job_id, Job.org_id == user.org_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    analyses = (
        db.query(Analysis)
        .join(Resume, Analysis.resume_id == Resume.id)
        .filter(Analysis.job_id == job.id, Resume.org_id == user.org_id)
        .all()
    )

    def iter_csv():
        yield "filename,status,score_total,score_hard,score_soft,score_sanity,label\n"
        for a in analyses:
            row = [a.resume.filename, a.status, a.score_total, a.score_hard, a.score_soft, a.score_sanity, a.label]
            yield ",".join(map(lambda x: str(x).replace(",", " "), row)) + "\n"

    headers = {"Content-Disposition": f'attachment; filename="job_{job.id}_analyses.csv"'}
    return StreamingResponse(iter_csv(), media_type="text/csv", headers=headers)
