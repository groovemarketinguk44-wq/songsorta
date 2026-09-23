import json
import re
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


def sort_by_artist(songs: list[str]) -> list[str]:
    def key(song):
        idx = song.find(' - ')
        artist = song[:idx].strip() if idx != -1 else song.split('-')[0].strip()
        return artist.lower().lstrip('the ').lstrip('a ').lstrip('an ')
    return sorted(songs, key=key)


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


@router.get("/all-remaining")
def all_remaining_songs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    files = db.query(SourceFile).filter_by(user_id=user.id).all()
    all_songs = []
    seen = set()
    for f in files:
        for s in json.loads(f.remaining_songs):
            key = s.lower().strip()
            if key not in seen:
                seen.add(key)
                all_songs.append(s)
    all_songs = sort_by_artist(all_songs)
    return {"songs": all_songs, "total": len(all_songs)}


@router.post("/manual-bulk-add")
def manual_bulk_add(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Playlist
    songs_to_add = body.get("songs", [])
    playlist_id = body.get("playlist_id")
    if not playlist_id:
        raise HTTPException(400, "playlist_id required")
    pl = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not pl:
        raise HTTPException(404, "Playlist not found")

    songs_keys = {s.lower().strip() for s in songs_to_add}
    existing = {s.lower().strip() for s in json.loads(pl.songs)}
    new_songs = [s for s in songs_to_add if s.lower().strip() not in existing]
    if new_songs:
        pl.songs = json.dumps(json.loads(pl.songs) + new_songs)
        pl.updated_at = datetime.utcnow()

    files = db.query(SourceFile).filter_by(user_id=user.id).all()
    for f in files:
        remaining = json.loads(f.remaining_songs)
        new_remaining = [s for s in remaining if s.lower().strip() not in songs_keys]
        removed = len(remaining) - len(new_remaining)
        if removed:
            f.remaining_songs = json.dumps(new_remaining)
            f.total_count = max(0, f.total_count - removed)
            f.current_index = min(f.current_index, max(0, len(new_remaining) - 1))
            f.updated_at = datetime.utcnow()

    db.commit()
    return {"added": len(new_songs), "duplicates": len(songs_to_add) - len(new_songs)}


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

    songs = sort_by_artist(parse_songs(text))
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
    remaining = sort_by_artist(json.loads(f.remaining_songs))
    f.remaining_songs = json.dumps(remaining)
    f.current_index = 0
    f.last_action = None
    f.updated_at = datetime.utcnow()
    db.commit()
    return file_progress(f)


def extract_artist(song: str) -> str:
    """Single main artist — used for alphabetical sort."""
    song = song.replace('–', '-').replace('—', '-')
    idx = song.find(' - ')
    artist = song[:idx].strip() if idx != -1 else song.split('-')[0].strip()
    return artist.lower()


def extract_all_artists(song: str) -> list[str]:
    """All artists including ft./feat./featuring in the title."""
    song_norm = song.replace('–', '-').replace('—', '-')
    idx = song_norm.find(' - ')
    if idx != -1:
        artist_part = song_norm[:idx]
        title_part = song_norm[idx + 3:]
    else:
        dash = song_norm.find('-')
        artist_part = song_norm[:dash] if dash != -1 else song_norm
        title_part = song_norm[dash + 1:] if dash != -1 else ''

    artists = []
    for a in re.split(r'\s*[&,]\s*|\s+and\s+', artist_part, flags=re.IGNORECASE):
        a = a.strip()
        if a:
            artists.append(a.lower())

    for match in re.findall(
        r'(?:ft\.?|feat\.?|featuring|with)\s+([^(\[\]\n]+?)(?:\s*[(\[]|$)',
        title_part, re.IGNORECASE
    ):
        for a in re.split(r'\s*[&,]\s*|\s+and\s+', match.strip(), flags=re.IGNORECASE):
            a = a.strip().rstrip(')').rstrip(']').strip()
            if a:
                artists.append(a.lower())

    return artists or [song_norm.lower()]


@router.get("/{file_id}/smart-sort")
def smart_sort_suggestions(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Playlist
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)

    playlists = db.query(Playlist).filter_by(user_id=user.id).all()

    # Build artist → {playlist_id: count} map from playlist songs
    artist_pl_counts: dict[str, dict[int, int]] = {}
    for pl in playlists:
        for song in json.loads(pl.songs):
            for a in extract_all_artists(song):
                artist_pl_counts.setdefault(a, {})
                artist_pl_counts[a][pl.id] = artist_pl_counts[a].get(pl.id, 0) + 1

    # Pre-build per-playlist song sets for duplicate checking
    pl_song_keys = {pl.id: {s.lower().strip() for s in json.loads(pl.songs)} for pl in playlists}
    pl_name = {pl.id: pl.name for pl in playlists}
    remaining = json.loads(f.remaining_songs)
    hints: dict[str, list[int]] = json.loads(f.smart_sort_hints or '{}')

    suggestions: dict[int, list[str]] = {}
    unmatched = 0
    for song in remaining:
        song_key = song.lower().strip()
        excluded = set(hints.get(song_key, []))
        best_pl = None
        for a in extract_all_artists(song):
            if a in artist_pl_counts:
                candidates = {pid: cnt for pid, cnt in artist_pl_counts[a].items() if pid not in excluded}
                if candidates:
                    best_pl = max(candidates, key=lambda pid: candidates[pid])
                    break
        if best_pl is not None:
            if song_key not in pl_song_keys[best_pl]:
                suggestions.setdefault(best_pl, []).append(song)
        else:
            unmatched += 1

    return {
        "suggestions": [
            {"playlist_id": pid, "playlist_name": pl_name[pid], "songs": songs}
            for pid, songs in suggestions.items()
        ],
        "unmatched_count": unmatched,
    }


@router.get("/{file_id}/seed-sort")
def seed_sort(file_id: int, limit: int = 40, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Playlist
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)

    playlists = db.query(Playlist).filter_by(user_id=user.id).all()

    # Build set of all artists already known in any playlist
    known_artists: set[str] = set()
    for pl in playlists:
        for song in json.loads(pl.songs):
            for a in extract_all_artists(song):
                known_artists.add(a)

    remaining = json.loads(f.remaining_songs)

    # Count remaining songs per artist
    artist_songs: dict[str, list[str]] = {}
    for song in remaining:
        for a in extract_all_artists(song):
            artist_songs.setdefault(a, []).append(song)

    # Only unknown artists, ranked by how many songs they'd unlock
    unknown = [(a, songs) for a, songs in artist_songs.items() if a not in known_artists]
    top = sorted(unknown, key=lambda x: len(x[1]), reverse=True)[:limit]

    seen: set[str] = set()
    seeds = []
    for artist, songs in top:
        for song in songs:
            if song not in seen:
                seeds.append({"artist": artist, "song": song, "unlocks": len(songs)})
                seen.add(song)
                break

    total_unlockable = sum(len(s) for _, s in top)
    return {"seeds": seeds, "total_unlockable": total_unlockable, "total_unknown_artists": len(unknown)}


@router.post("/{file_id}/smart-sort-apply")
def smart_sort_apply(file_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Playlist
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)

    assignments = body.get("assignments", [])
    rejections = body.get("rejections", [])  # [{song, playlist_id}]
    assigned_keys: set[str] = set()
    total_added = 0

    for a in assignments:
        pl = db.query(Playlist).filter_by(id=a.get("playlist_id"), user_id=user.id).first()
        if not pl:
            continue
        songs_to_add = a.get("songs", [])
        existing = {s.lower().strip() for s in json.loads(pl.songs)}
        new_songs = [s for s in songs_to_add if s.lower().strip() not in existing]
        if new_songs:
            pl.songs = json.dumps(json.loads(pl.songs) + new_songs)
            pl.updated_at = datetime.utcnow()
            total_added += len(new_songs)
        assigned_keys.update(s.lower().strip() for s in songs_to_add)

    if rejections:
        hints: dict[str, list[int]] = json.loads(f.smart_sort_hints or '{}')
        for r in rejections:
            key = r.get("song", "").lower().strip()
            pl_id = r.get("playlist_id")
            if key and pl_id:
                if key not in hints:
                    hints[key] = []
                if pl_id not in hints[key]:
                    hints[key].append(pl_id)
        f.smart_sort_hints = json.dumps(hints)

    remaining = json.loads(f.remaining_songs)
    new_remaining = [s for s in remaining if s.lower().strip() not in assigned_keys]
    removed = len(remaining) - len(new_remaining)
    f.remaining_songs = json.dumps(new_remaining)
    f.total_count = max(0, f.total_count - removed)
    f.current_index = 0
    f.updated_at = datetime.utcnow()
    db.commit()
    return {**file_progress(f), "total_added": total_added}


@router.post("/{file_id}/remove-in-playlists")
def remove_in_playlists(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Playlist
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    playlists = db.query(Playlist).filter_by(user_id=user.id).all()
    in_playlists = {s.lower().strip() for pl in playlists for s in json.loads(pl.songs)}
    remaining = json.loads(f.remaining_songs)
    filtered = [s for s in remaining if s.lower().strip() not in in_playlists]
    removed = len(remaining) - len(filtered)
    f.remaining_songs = json.dumps(filtered)
    f.total_count = f.total_count - removed
    f.current_index = 0
    f.updated_at = datetime.utcnow()
    db.commit()
    return {**file_progress(f), "removed": removed}


@router.post("/{file_id}/bulk-to-playlist")
def bulk_to_playlist(file_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..models import Playlist
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    playlist_id = body.get("playlist_id")
    if not playlist_id:
        raise HTTPException(400, "playlist_id required")
    pl = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not pl:
        raise HTTPException(404, "Playlist not found")

    remaining = json.loads(f.remaining_songs)
    existing = {s.lower().strip() for s in json.loads(pl.songs)}
    to_add = [s for s in remaining if s.lower().strip() not in existing]
    dupes = len(remaining) - len(to_add)

    if to_add:
        current_songs = json.loads(pl.songs)
        pl.songs = json.dumps(current_songs + to_add)
        pl.updated_at = datetime.utcnow()

    f.remaining_songs = json.dumps([])
    f.current_index = 0
    f.updated_at = datetime.utcnow()
    db.commit()

    return {"added": len(to_add), "duplicates": dupes, "total": len(remaining)}


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    db.delete(f)
    db.commit()
    return {"ok": True}


@router.get("/{file_id}/export")
def export_remaining(file_id: int, token: str = Query(...), db: Session = Depends(get_db)):
    user = get_user_by_token(token, db)
    f = db.query(SourceFile).filter_by(id=file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    remaining = json.loads(f.remaining_songs)
    text = "\n".join(remaining)
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{f.name}_remaining.txt"'})
