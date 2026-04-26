import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from docx import Document
import io
from ..database import get_db
from ..models import SourceFile, User
from ..auth import get_current_user
from jose import JWTError, jwt
import os

SECRET_KEY = os.getenv("SECRET_KEY", "songsorta-secret-change-in-prod")
ALGORITHM = "HS256"

def get_user_by_token(token: str, db: Session) -> User:
    from ..models import User as U
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401)
    user = db.query(U).filter(U.id == user_id).first()
    if not user:
        raise HTTPException(401)
    return user
from ..schemas import SourceFileResponse, SourceFileDetail

router = APIRouter(prefix="/api/files", tags=["files"])


def parse_songs(text: str) -> list[str]:
    songs = []
    for line in text.splitlines():
        line = line.strip().replace('–', '-').replace('—', '-')
        if line:
            songs.append(line)
    return songs


def file_progress(f: SourceFile) -> dict:
    remaining = json.loads(f.remaining_songs)
    songs_added = f.total_count - len(remaining)
    songs_processed = songs_added + f.current_index
    pct = round(songs_processed / f.total_count * 100, 1) if f.total_count > 0 else 0
    is_complete = f.current_index >= len(remaining)
    current_song = remaining[f.current_index] if not is_complete else None
    return {
        "id": f.id, "name": f.name, "total_count": f.total_count,
        "remaining_count": len(remaining), "current_index": f.current_index,
        "progress_pct": pct, "is_complete": is_complete,
        "current_song": current_song, "songs_added": songs_added,
        "created_at": f.created_at, "updated_at": f.updated_at,
    }


@router.get("/")
def list_files(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    files = db.query(SourceFile).filter(SourceFile.user_id == user.id).order_by(SourceFile.updated_at.desc()).all()
    return [file_progress(f) for f in files]


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content = await file.read()
    if file.filename.endswith(".docx"):
        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:
        text = content.decode("utf-8", errors="ignore")

    songs = parse_songs(text)
    if not songs:
        raise HTTPException(400, "No songs found in file")

    songs_json = json.dumps(songs)
    sf = SourceFile(
        name=name.strip(),
        user_id=user.id,
        original_songs=songs_json,
        remaining_songs=songs_json,
        current_index=0,
        total_count=len(songs),
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)
    return file_progress(sf)


@router.get("/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    return file_progress(f)


@router.get("/{file_id}/remaining-songs")
def get_remaining_songs(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    return {"songs": json.loads(f.remaining_songs)}


@router.post("/{file_id}/restart")
def restart_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    f.current_index = 0
    f.last_action = None
    f.updated_at = datetime.utcnow()
    db.commit()
    return file_progress(f)


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    db.delete(f)
    db.commit()
    return {"ok": True}


@router.get("/{file_id}/export")
def export_remaining(file_id: int, token: str = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if token:
        user = get_user_by_token(token, db)
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    remaining = json.loads(f.remaining_songs)
    text = "\n".join(remaining)
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{f.name}_remaining.txt"'})
