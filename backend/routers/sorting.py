import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SourceFile, Playlist, User
from ..auth import get_current_user
from ..schemas import SortAction, SortUndo

router = APIRouter(prefix="/api/sort", tags=["sort"])


def build_response(f: SourceFile) -> dict:
    remaining = json.loads(f.remaining_songs)
    is_complete = f.current_index >= len(remaining)
    songs_added = f.total_count - len(remaining)
    songs_processed = songs_added + f.current_index
    pct = round(songs_processed / f.total_count * 100, 1) if f.total_count > 0 else 0
    return {
        "success": True,
        "duplicate": False,
        "is_complete": is_complete,
        "next_song": remaining[f.current_index] if not is_complete else None,
        "current_index": f.current_index,
        "remaining_count": len(remaining),
        "total_count": f.total_count,
        "progress_pct": pct,
        "songs_added": songs_added,
    }


@router.post("/action")
def sort_action(data: SortAction, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=data.source_file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)

    remaining = json.loads(f.remaining_songs)
    if f.current_index >= len(remaining):
        raise HTTPException(400, "No more songs to sort")

    current_song = remaining[f.current_index]
    is_duplicate = False

    if data.action == "add":
        if not data.playlist_id:
            raise HTTPException(400, "playlist_id required for add action")
        playlist = db.query(Playlist).filter_by(id=data.playlist_id, user_id=user.id).first()
        if not playlist:
            raise HTTPException(404, "Playlist not found")

        songs = json.loads(playlist.songs)
        song_lower = current_song.lower().strip()
        if any(s.lower().strip() == song_lower for s in songs):
            is_duplicate = True
        else:
            songs.append(current_song)
            playlist.songs = json.dumps(songs)
            playlist.updated_at = datetime.utcnow()

        f.last_action = json.dumps({
            "type": "add", "song": current_song,
            "playlist_id": data.playlist_id, "position": f.current_index,
            "was_duplicate": is_duplicate,
        })
        remaining.pop(f.current_index)
        f.remaining_songs = json.dumps(remaining)

    elif data.action == "skip":
        f.last_action = json.dumps({
            "type": "skip", "song": current_song, "position": f.current_index,
        })
        f.current_index += 1

    else:
        raise HTTPException(400, "action must be 'add' or 'skip'")

    f.updated_at = datetime.utcnow()
    db.commit()

    resp = build_response(f)
    resp["duplicate"] = is_duplicate
    return resp


@router.post("/undo")
def sort_undo(data: SortUndo, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = db.query(SourceFile).filter_by(id=data.source_file_id, user_id=user.id).first()
    if not f:
        raise HTTPException(404)
    if not f.last_action:
        raise HTTPException(400, "Nothing to undo")

    action = json.loads(f.last_action)
    remaining = json.loads(f.remaining_songs)

    if action["type"] == "add":
        # Restore song to remaining at original position
        pos = action["position"]
        remaining.insert(pos, action["song"])
        f.remaining_songs = json.dumps(remaining)
        # Remove from playlist (if it wasn't a duplicate add)
        if not action.get("was_duplicate"):
            playlist = db.query(Playlist).filter_by(id=action["playlist_id"], user_id=user.id).first()
            if playlist:
                songs = json.loads(playlist.songs)
                # Remove last occurrence matching this song
                song_lower = action["song"].lower().strip()
                for i in range(len(songs) - 1, -1, -1):
                    if songs[i].lower().strip() == song_lower:
                        songs.pop(i)
                        break
                playlist.songs = json.dumps(songs)
                playlist.updated_at = datetime.utcnow()

    elif action["type"] == "skip":
        f.current_index = max(0, f.current_index - 1)

    f.last_action = None
    f.updated_at = datetime.utcnow()
    db.commit()
    return build_response(f)
