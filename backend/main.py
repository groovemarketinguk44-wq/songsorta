from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from sqlalchemy import text
import os

from .database import engine
from .models import Base
from .routers import auth, files, playlists, sorting
from .routers import oauth, spotify, apple

MIGRATIONS = [
    # playlist sort_order (original)
    "ALTER TABLE playlists ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0",
    # OAuth columns on users
    "ALTER TABLE users ADD COLUMN email TEXT",
    "ALTER TABLE users ADD COLUMN google_id TEXT",
    "ALTER TABLE users ADD COLUMN spotify_id TEXT",
    "ALTER TABLE users ADD COLUMN spotify_access_token TEXT",
    "ALTER TABLE users ADD COLUMN spotify_refresh_token TEXT",
    "ALTER TABLE users ADD COLUMN spotify_token_expires TIMESTAMP",
    "ALTER TABLE users ADD COLUMN spotify_display_name TEXT",
    # Playlist: track last Spotify export
    "ALTER TABLE playlists ADD COLUMN spotify_playlist_id TEXT",
    # Playlist: download tracking
    "ALTER TABLE playlists ADD COLUMN downloaded_songs TEXT DEFAULT '[]'",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        os.makedirs("/data", exist_ok=True)
    except OSError:
        pass
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for sql in MIGRATIONS:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists
    yield


app = FastAPI(title="SongSorta", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(spotify.router)
app.include_router(apple.router)
app.include_router(files.router)
app.include_router(playlists.router)
app.include_router(sorting.router)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def root():
    return FileResponse("frontend/index.html")

@app.get("/login")
def login_page():
    return FileResponse("frontend/login.html")

@app.get("/sort")
def sort_page():
    return FileResponse("frontend/sort.html")

@app.get("/playlist")
def playlist_page():
    return FileResponse("frontend/playlist.html")

@app.get("/connect")
def connect_page():
    return FileResponse("frontend/connect.html")
