from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user_id: int
    username: str


class SourceFileCreate(BaseModel):
    name: str
    songs: List[str]


class SourceFileResponse(BaseModel):
    id: int
    name: str
    total_count: int
    remaining_count: int
    current_index: int
    progress_pct: float
    is_complete: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceFileDetail(SourceFileResponse):
    current_song: Optional[str]
    songs_added: int


class PlaylistCreate(BaseModel):
    name: str


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    songs: Optional[List[str]] = None
    speed_dial_slot: Optional[int] = None


class PlaylistResponse(BaseModel):
    id: int
    name: str
    song_count: int
    speed_dial_slot: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlaylistDetail(PlaylistResponse):
    songs: List[str]


class SortAction(BaseModel):
    source_file_id: int
    action: str  # "add" or "skip"
    playlist_id: Optional[int] = None


class SortUndo(BaseModel):
    source_file_id: int


class SortActionResponse(BaseModel):
    success: bool
    duplicate: bool
    is_complete: bool
    next_song: Optional[str]
    current_index: int
    remaining_count: int
    total_count: int
    progress_pct: float
    songs_added: int
