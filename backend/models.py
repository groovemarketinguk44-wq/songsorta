from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_files = relationship("SourceFile", back_populates="user", cascade="all, delete-orphan")
    playlists = relationship("Playlist", back_populates="user", cascade="all, delete-orphan")


class SourceFile(Base):
    __tablename__ = "source_files"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_songs = Column(Text, default="[]")   # JSON array, never changes
    remaining_songs = Column(Text, default="[]")  # JSON array, songs not yet added
    current_index = Column(Integer, default=0)     # position in remaining_songs
    total_count = Column(Integer, default=0)
    last_action = Column(Text, nullable=True)      # JSON for undo
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="source_files")


class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    songs = Column(Text, default="[]")            # JSON array of song strings
    speed_dial_slot = Column(Integer, nullable=True)  # 1-9
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="playlists")
