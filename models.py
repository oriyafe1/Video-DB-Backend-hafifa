import os
import sqlalchemy as db
from dotenv import load_dotenv
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DB_URI = os.getenv('DB_URI')
engine = db.create_engine(DB_URI, echo=True)
Base = declarative_base()


class Video(Base):
    __tablename__ = "videos"

    id = db.Column('id', db.Integer(), primary_key=True)
    observation_post_name = db.Column('observation_post_name', db.String())
    OS_filepath = db.Column('OS_filepath', db.String())
    frame_count = db.Column('frame_count', db.Integer())


class Metadata(Base):
    __tablename__ = "metadata"

    id = db.Column('id', db.Integer(), primary_key=True)
    is_threat = db.Column('is_threat', db.Boolean())
    azimuth = db.Column('azimuth', db.Float())
    fov = db.Column('fov', db.Float())
    elevation = db.Column('elevation', db.Float())


class Frame(Base):
    __tablename__ = "frames"

    id = db.Column('id', db.Integer(), primary_key=True)
    video_id = db.Column('video_id', db.ForeignKey('videos.id'))
    metadata_id = db.Column('metadata_id', db.ForeignKey('metadata.id'))
    OS_filepath = db.Column('OS_filepath', db.String())
    frame_index = db.Column('frame_index', db.Integer())


Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()
