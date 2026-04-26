import os
import httpx
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..database import get_db
from ..models import User
from ..auth import create_token, SECRET_KEY, ALGORITHM
from jose import JWTError, jwt as jose_jwt

router = APIRouter(prefix="/api/auth", tags=["oauth"])

APP_BASE_URL = os.getenv("APP_BASE_URL", "https://songsorta.fly.dev")

# ── Google ─────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = f"{APP_BASE_URL}/api/auth/google/callback"


@router.get("/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google login not configured")
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/auth?{params}")


@router.get("/google/callback")
async def google_callback(code: str = None, error: str = None, db: Session = Depends(get_db)):
    if error or not code:
        return RedirectResponse("/login?error=google_denied")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        })
        tokens = token_resp.json()
        if "error" in tokens:
            return RedirectResponse("/login?error=google_failed")
        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        info = user_resp.json()

    google_id = info.get("id", "")
    email = info.get("email", "")
    name = info.get("name", "")

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_id = google_id
    if not user:
        base = (name or email.split("@")[0] or f"user{google_id[:6]}").lower().replace(" ", "_")[:18]
        username = base
        n = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base}{n}"; n += 1
        user = User(username=username, password_hash="", email=email, google_id=google_id)
        db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return RedirectResponse(f"/?_token={token}&_user={user.username}")


# ── Spotify ────────────────────────────────────────────────────────────────

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = f"{APP_BASE_URL}/api/auth/spotify/callback"
SPOTIFY_SCOPES = (
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-public playlist-modify-private user-read-private user-read-email"
)


@router.get("/spotify")
def spotify_login(state: str = "login"):
    if not SPOTIFY_CLIENT_ID:
        raise HTTPException(503, "Spotify not configured")
    params = urlencode({
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "state": state,
    })
    return RedirectResponse(f"https://accounts.spotify.com/authorize?{params}")


@router.get("/spotify/callback")
async def spotify_callback(
    code: str = None, error: str = None, state: str = "login",
    db: Session = Depends(get_db),
):
    if error or not code:
        return RedirectResponse("/connect?error=spotify_denied")

    import base64
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": SPOTIFY_REDIRECT_URI},
        )
        tokens = token_resp.json()
        if "error" in tokens:
            return RedirectResponse("/connect?error=spotify_failed")
        me_resp = await client.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        sp = me_resp.json()

    spotify_id = sp.get("id", "")
    email = sp.get("email", "")
    display_name = sp.get("display_name") or spotify_id
    expires_at = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))

    def _save_spotify(user: User):
        user.spotify_id = spotify_id
        user.spotify_display_name = display_name
        user.spotify_access_token = tokens["access_token"]
        user.spotify_refresh_token = tokens.get("refresh_token") or user.spotify_refresh_token
        user.spotify_token_expires = expires_at
        if email and not user.email:
            user.email = email

    if state == "login":
        # Login / register via Spotify
        user = db.query(User).filter(User.spotify_id == spotify_id).first()
        if not user and email:
            user = db.query(User).filter(User.email == email).first()
        if not user:
            base = display_name.lower().replace(" ", "_")[:18]
            username = base
            n = 1
            while db.query(User).filter(User.username == username).first():
                username = f"{base}{n}"; n += 1
            user = User(username=username, password_hash="", email=email)
            db.add(user)
            db.flush()
        _save_spotify(user)
        db.commit()
        db.refresh(user)
        token = create_token(user.id)
        return RedirectResponse(f"/?_token={token}&_user={user.username}")
    else:
        # Connecting Spotify to an existing logged-in account
        try:
            payload = jose_jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
            user = db.query(User).filter(User.id == int(payload["sub"])).first()
            if not user:
                raise ValueError
        except (JWTError, ValueError):
            return RedirectResponse("/connect?error=invalid_state")
        # Clear this spotify_id from any other user first
        other = db.query(User).filter(User.spotify_id == spotify_id, User.id != user.id).first()
        if other:
            other.spotify_id = None
        _save_spotify(user)
        db.commit()
        return RedirectResponse("/connect?spotify=connected")


@router.post("/spotify/disconnect")
def spotify_disconnect(db: Session = Depends(get_db)):
    # Called with JWT in body — use auth dependency inline
    from ..auth import get_current_user, bearer_scheme
    # Can't use Depends here easily without restructuring; handled via separate endpoint in spotify router
    raise HTTPException(405, "Use DELETE /api/spotify/disconnect")
