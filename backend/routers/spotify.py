import os
import base64
import json
import httpx
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Playlist, SourceFile
from ..auth import get_current_user, create_token, SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/api/spotify", tags=["spotify"])

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://songsorta.fly.dev")


async def valid_token(user: User, db: Session) -> str:
    if not user.spotify_access_token:
        raise HTTPException(400, "Spotify not connected")
    if user.spotify_token_expires and user.spotify_token_expires > datetime.utcnow() + timedelta(minutes=5):
        return user.spotify_access_token
    # Refresh
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "refresh_token", "refresh_token": user.spotify_refresh_token or ""},
        )
        tokens = resp.json()
    if "error" in tokens:
        raise HTTPException(401, "Spotify session expired — please reconnect")
    user.spotify_access_token = tokens["access_token"]
    user.spotify_token_expires = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
    if "refresh_token" in tokens:
        user.spotify_refresh_token = tokens["refresh_token"]
    db.commit()
    return user.spotify_access_token


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return {
        "connected": bool(user.spotify_id),
        "display_name": user.spotify_display_name,
        "configured": bool(SPOTIFY_CLIENT_ID),
        "connect_url": f"/api/auth/spotify?state={create_token(user.id)}",
    }


@router.delete("/disconnect")
def disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.spotify_id = None
    user.spotify_display_name = None
    user.spotify_access_token = None
    user.spotify_refresh_token = None
    user.spotify_token_expires = None
    db.commit()
    return {"ok": True}


@router.get("/playlists")
async def list_playlists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    token = await valid_token(user, db)
    playlists = []
    url = "https://api.spotify.com/v1/me/playlists?limit=50"
    async with httpx.AsyncClient() as client:
        while url:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
            playlists.extend(p for p in data.get("items", []) if p)
            url = data.get("next")
    return [
        {"id": p["id"], "name": p["name"],
         "track_count": p["tracks"]["total"],
         "image": p["images"][0]["url"] if p.get("images") else None}
        for p in playlists
    ]


@router.post("/import/{spotify_playlist_id}")
async def import_playlist(
    spotify_playlist_id: str,
    import_as: str = "playlist",
    name: str = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = await valid_token(user, db)
    async with httpx.AsyncClient() as client:
        pl_resp = await client.get(
            f"https://api.spotify.com/v1/playlists/{spotify_playlist_id}?fields=name",
            headers={"Authorization": f"Bearer {token}"},
        )
        playlist_name = name or pl_resp.json().get("name", "Spotify Playlist")

        songs = []
        url = f"https://api.spotify.com/v1/playlists/{spotify_playlist_id}/tracks?limit=100&fields=next,items(track(name,artists,is_local))"
        while url:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
            for item in data.get("items", []):
                track = item.get("track")
                if not track or track.get("is_local"):
                    continue
                artist = track["artists"][0]["name"] if track.get("artists") else "Unknown"
                songs.append(f"{artist} - {track.get('name', 'Unknown')}")
            url = data.get("next")

    if not songs:
        raise HTTPException(400, "No tracks found")

    if import_as == "songlist":
        songs_json = json.dumps(songs)
        sf = SourceFile(
            name=playlist_name, user_id=user.id,
            original_songs=songs_json, remaining_songs=songs_json,
            current_index=0, total_count=len(songs),
        )
        db.add(sf)
        db.commit()
        db.refresh(sf)
        return {"type": "songlist", "id": sf.id, "name": sf.name, "count": len(songs)}
    else:
        max_order = db.query(Playlist).filter_by(user_id=user.id).count()
        p = Playlist(name=playlist_name, user_id=user.id, songs=json.dumps(songs), sort_order=max_order)
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"type": "playlist", "id": p.id, "name": p.name, "count": len(songs)}


@router.post("/export/{playlist_id}")
async def export_playlist(
    playlist_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = await valid_token(user, db)
    pl = db.query(Playlist).filter_by(id=playlist_id, user_id=user.id).first()
    if not pl:
        raise HTTPException(404)
    songs = json.loads(pl.songs)
    if not songs:
        raise HTTPException(400, "Playlist is empty")

    async with httpx.AsyncClient() as client:
        me = (await client.get("https://api.spotify.com/v1/me",
                               headers={"Authorization": f"Bearer {token}"})).json()
        create = await client.post(
            f"https://api.spotify.com/v1/users/{me['id']}/playlists",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"name": pl.name, "public": False, "description": "Created with SongSorta"},
        )
        new_pl = create.json()
        new_pl_id = new_pl["id"]

        uris, not_found = [], []
        for song in songs:
            search = await client.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": song, "type": "track", "limit": 1},
            )
            items = search.json().get("tracks", {}).get("items", [])
            if items:
                uris.append(items[0]["uri"])
            else:
                not_found.append(song)

        for i in range(0, len(uris), 100):
            await client.post(
                f"https://api.spotify.com/v1/playlists/{new_pl_id}/tracks",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"uris": uris[i:i + 100]},
            )

    pl.spotify_playlist_id = new_pl_id
    db.commit()
    return {
        "ok": True,
        "added": len(uris),
        "not_found": not_found,
        "spotify_url": new_pl.get("external_urls", {}).get("spotify", ""),
    }
