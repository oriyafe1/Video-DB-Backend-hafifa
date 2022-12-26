import os
import sqlalchemy as db
from dotenv import load_dotenv
from sqlalchemy.orm import declarative_base, relationship

load_dotenv()

DB_URI = os.getenv('DB_URI')
engine = db.create_engine(DB_URI)
Base = declarative_base()


class Video(Base):
    __tablename__ = "videos"

    id = db.Column('id', db.Integer(), primary_key=True)
    observation_post_name = db.Column('observation_post_name', db.String())
    OS_filepath = db.Column('OS_filepath', db.String())
    frame_count = db.Column('frame_count', db.Integer())
    frames = relationship("Frame", back_populates='video')


class FrameMetadata(Base):
    __tablename__ = "frame_metadata"

    id = db.Column('id', db.Integer(), primary_key=True)
    is_threat = db.Column('is_threat', db.Boolean())
    azimuth = db.Column('azimuth', db.Float())
    fov = db.Column('fov', db.Float())
    elevation = db.Column('elevation', db.Float())
    frame = relationship("Frame", back_populates="frame_metadata", uselist=False)


class Frame(Base):
    __tablename__ = "frames"

    id = db.Column('id', db.Integer(), primary_key=True)
    video_id = db.Column('video_id', db.ForeignKey('videos.id'))
    metadata_id = db.Column('metadata_id', db.ForeignKey('frame_metadata.id'))
    OS_filepath = db.Column('OS_filepath', db.String())
    frame_index = db.Column('frame_index', db.Integer())
    video = relationship("Video", back_populates="frames")
    frame_metadata = relationship("FrameMetadata", back_populates="frame", uselist=False)


Base.metadata.create_all(engine)
