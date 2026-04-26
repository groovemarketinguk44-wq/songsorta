import os
import time
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from jose import jwt as jose_jwt
from ..database import get_db
from ..models import User, Playlist, SourceFile
from ..auth import get_current_user

router = APIRouter(prefix="/api/apple", tags=["apple"])

APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY = os.getenv("APPLE_PRIVATE_KEY", "").replace("\\n", "\n")


def _dev_token() -> str:
    if not all([APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_PRIVATE_KEY]):
        raise HTTPException(503, "Apple Music not configured — set APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_PRIVATE_KEY")
    payload = {"iss": APPLE_TEAM_ID, "iat": int(time.time()), "exp": int(time.time()) + 43200}
    return jose_jwt.encode(payload, APPLE_PRIVATE_KEY, algorithm="ES256",
                           headers={"kid": APPLE_KEY_ID, "alg": "ES256"})


@router.get("/status")
def apple_status(_: User = Depends(get_current_user)):
    return {"configured": bool(APPLE_TEAM_ID and APPLE_KEY_ID and APPLE_PRIVATE_KEY)}


@router.get("/developer-token")
def developer_token(_: User = Depends(get_current_user)):
    return {"token": _dev_token()}


class ImportRequest(BaseModel):
    name: str
    songs: list[str]
    import_as: str = "playlist"  # "playlist" or "songlist"


@router.post("/import")
def apple_import(data: ImportRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    songs = [s.strip() for s in data.songs if s.strip()]
    if not songs:
        raise HTTPException(400, "No songs provided")
    if data.import_as == "songlist":
        songs_json = json.dumps(songs)
        sf = SourceFile(
            name=data.name, user_id=user.id,
            original_songs=songs_json, remaining_songs=songs_json,
            current_index=0, total_count=len(songs),
        )
        db.add(sf)
        db.commit()
        db.refresh(sf)
        return {"type": "songlist", "id": sf.id, "name": sf.name, "count": len(songs)}
    else:
        max_order = db.query(Playlist).filter_by(user_id=user.id).count()
        p = Playlist(name=data.name, user_id=user.id, songs=json.dumps(songs), sort_order=max_order)
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"type": "playlist", "id": p.id, "name": p.name, "count": len(songs)}
