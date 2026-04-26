import json
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from docx import Document
import io
from ..database import get_db
from ..models import Playlist, SourceFile, User
from ..auth import get_current_user
from ..schemas import PlaylistCreate, PlaylistUpdate

SECRET_KEY = os.getenv("SECRET_KEY", "songsorta-secret-change-in-prod")
ALGORITHM = "HS256"

def get_user_by_token(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(401)
    return u

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


def pl_detail(p: Playlist) -> dict:
    songs = json.loads(p.songs)
    return {
        "id": p.id, "name": p.name, "songs": songs,
        "song_count": len(songs), "speed_dial_slot": p.speed_dial_slot,
        "created_at": p.created_at, "updated_at": p.updated_at,
    }


@router.get("/")
def list_playlists(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    playlists = db.query(Playlist).filter_by(user_id=user.id).order_by(Playlist.updated_at.desc()).all()
    return [pl_detail(p) for p in playlists]


@router.post("/")
def create_playlist(data: PlaylistCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = Playlist(name=data.name.strip(), user_id=user.id, songs="[]")
    db.add(p)
    db.commit()
    db.refresh(p)
    return pl_detail(p)


@router.post("/upload")
async def upload_playlist(
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

    songs = []
    for line in text.splitlines():
        line = line.strip().replace('–', '-').replace('—', '-')
        if line:
            songs.append(line)

    if not songs:
        raise HTTPException(400, "No songs found in file")

    p = Playlist(name=name.strip(), user_id=user.id, songs=json.dumps(songs))
    db.add(p)
    db.commit()
    db.refresh(p)
    return pl_detail(p)


@router.get("/{playlist_id}")
def get_playlist(playlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404)
    return pl_detail(p)


@router.put("/{playlist_id}")
def update_playlist(playlist_id: int, data: PlaylistUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404)
    if data.name is not None:
        p.name = data.name.strip()
    if data.songs is not None:
        p.songs = json.dumps(data.songs)
    if data.speed_dial_slot is not None:
        # Clear slot from any other playlist first
        existing = db.query(Playlist).filter_by(user_id=user.id, speed_dial_slot=data.speed_dial_slot).first()
        if existing and existing.id != playlist_id:
            existing.speed_dial_slot = None
        p.speed_dial_slot = data.speed_dial_slot
    p.updated_at = datetime.utcnow()
    db.commit()
    return pl_detail(p)


@router.put("/{playlist_id}/speed-dial")
def set_speed_dial(playlist_id: int, slot: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if slot not in range(0, 10):  # 0 = clear
        raise HTTPException(400, "Slot must be 0-9")
    p = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404)
    if slot == 0:
        p.speed_dial_slot = None
    else:
        existing = db.query(Playlist).filter_by(user_id=user.id, speed_dial_slot=slot).first()
        if existing and existing.id != playlist_id:
            existing.speed_dial_slot = None
        p.speed_dial_slot = slot
    p.updated_at = datetime.utcnow()
    db.commit()
    return pl_detail(p)


@router.post("/{playlist_id}/sort")
def sort_playlist(playlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404)
    songs = json.loads(p.songs)
    if not songs:
        raise HTTPException(400, "Playlist is empty")
    songs_json = json.dumps(songs)
    sf = SourceFile(
        name=f"{p.name} (sort)",
        user_id=user.id,
        original_songs=songs_json,
        remaining_songs=songs_json,
        current_index=0,
        total_count=len(songs),
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)
    remaining = json.loads(sf.remaining_songs)
    return {
        "id": sf.id, "name": sf.name, "total_count": sf.total_count,
        "remaining_count": len(remaining), "current_index": sf.current_index,
        "progress_pct": 0, "is_complete": False,
        "current_song": remaining[0] if remaining else None,
        "songs_added": 0, "created_at": sf.created_at, "updated_at": sf.updated_at,
    }


@router.delete("/{playlist_id}")
def delete_playlist(playlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/{playlist_id}/export")
def export_playlist(playlist_id: int, token: str = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if token:
        user = get_user_by_token(token, db)
    p = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404)
    songs = json.loads(p.songs)
    text = "\n".join(songs)
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{p.name}.txt"'})
