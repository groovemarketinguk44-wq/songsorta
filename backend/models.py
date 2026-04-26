from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False, default="")
    email = Column(String, nullable=True)
    # OAuth
    google_id = Column(String, nullable=True)
    spotify_id = Column(String, nullable=True)
    spotify_access_token = Column(Text, nullable=True)
    spotify_refresh_token = Column(Text, nullable=True)
    spotify_token_expires = Column(DateTime, nullable=True)
    spotify_display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_files = relationship("SourceFile", back_populates="user", cascade="all, delete-orphan")
    playlists = relationship("Playlist", back_populates="user", cascade="all, delete-orphan")


class SourceFile(Base):
    __tablename__ = "source_files"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_songs = Column(Text, default="[]")
    remaining_songs = Column(Text, default="[]")
    current_index = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    last_action = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="source_files")


class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    songs = Column(Text, default="[]")
    speed_dial_slot = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0)
    spotify_playlist_id = Column(String, nullable=True)
    downloaded_songs = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="playlists")
