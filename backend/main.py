from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from .database import engine
from .models import Base
from .routers import auth, files, playlists, sorting


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        os.makedirs("/data", exist_ok=True)
    except OSError:
        pass
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SongSorta", lifespan=lifespan)

app.include_router(auth.router)
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
