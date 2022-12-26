import os
import cv2
import time
import logging
import zipfile
import functools
from io import BytesIO
from multiprocessing.pool import ThreadPool as Pool
from sqlalchemy.orm import sessionmaker
from models import Video, FrameMetadata, Frame, engine
from minio_config import minio_client, minio_bucket_name
from flask import Flask, request, jsonify, abort, send_file
from given_functions import is_frame_tagged, generate_metadata

app = Flask(__name__)
max_workers = 10
logging.basicConfig(level=logging.INFO)


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class DBService(metaclass=SingletonMeta):
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def update_video_frame_count(self, video_id, frame_count):
        with self.Session() as session:
            video_instance = session.query(Video).get(video_id)
            video_instance.frame_count = frame_count
            session.commit()

    def save_video(self, video_file_path, video_filename):
        with self.Session() as session:
            observation_post_name = video_filename.split("_")[0]
            video_instance = Video(observation_post_name=observation_post_name)
            session.add(video_instance)
            session.commit()
            video_os_filepath = f'/videos/{video_instance.id}_{video_filename}'
            minio_client.fput_object(minio_bucket_name, video_os_filepath, video_file_path)
            video_instance.OS_filepath = video_os_filepath
            session.commit()

        return video_instance

    def save_frame_metadata(self, frame, session):
        is_threat = is_frame_tagged(frame)
        fov, azimuth, elevation = generate_metadata(frame)
        frame_metadata = FrameMetadata(is_threat=is_threat, fov=fov, azimuth=azimuth, elevation=elevation)
        session.add(frame_metadata)

        return frame_metadata

    def save_frame(self, curr_frame_index, frame, video_id, video_name, session):
        frame_metadata = self.save_frame_metadata(frame, session)
        frame_os_filepath = f'/frames/{video_id}_{video_name}/frame_{curr_frame_index}.jpg'
        _, jpeg_frame = cv2.imencode('.jpg', frame)
        image_bytes = BytesIO(jpeg_frame)
        minio_client.put_object(minio_bucket_name, frame_os_filepath,
                                image_bytes,
                                len(jpeg_frame))
        frame_db_instance = Frame(video_id=video_id, frame_metadata=frame_metadata,
                                  OS_filepath=frame_os_filepath,
                                  frame_index=curr_frame_index)
        session.add(frame_db_instance)

        return frame_db_instance

    def save_video_frames(self, video_frames, video_id, video_name):
        with self.Session() as session:
            with Pool(max_workers) as thread_pool:
                save_frame_copier = functools.partial(self.save_frame, video_id=video_id, video_name=video_name,
                                                      session=session)
                thread_pool.starmap(save_frame_copier, enumerate(video_frames))
            session.commit()

    def get_videos_os_filepaths(self):
        with self.Session() as session:
            paths_as_tuples = session.query(Video.OS_filepath).all()
            paths = [path_tuple[0] for path_tuple in paths_as_tuples]

        return paths

    def get_video_by_id(self, video_id):
        with self.Session() as session:
            video_instance = session.query(Video).get(video_id)

        return video_instance

    def get_video_frame_at_index(self, video_id, frame_index):
        with self.Session() as session:
            frame_instance = session.query(Frame).filter(Frame.video_id == video_id,
                                                         Frame.frame_index == frame_index).first()
        return frame_instance

    def get_video_frames(self, video_id):
        with self.Session() as session:
            frames = session.query(Frame).filter(Frame.video_id == video_id,
                                                 Frame.frame_metadata.has(FrameMetadata.is_threat)).all()

        return frames


db_service = DBService()


@app.post("/video")
def upload_video_from_local_path():
    start_time = time.perf_counter()

    video_file_path = request.json['path']
    logging.info(f'Uploading video from local path: "{video_file_path}"')
    video_name = os.path.basename(video_file_path)
    video_instance = db_service.save_video(video_file_path, video_name)
    video = cv2.VideoCapture(video_file_path)
    video_frames = []

    while True:
        ret, frame = video.read()

        if ret:
            video_frames.append(frame)
        else:
            break

    db_service.save_video_frames(video_frames, video_instance.id, video_name)
    video.release()
    db_service.update_video_frame_count(video_instance.id, len(video_frames))

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    logging.info(f'Uploaded video in {elapsed_time:.2f} seconds. Saved {len(video_frames)} frames')

    return 'Success'


@app.get("/video/paths")
def get_videos_os_filepaths():
    return jsonify(db_service.get_videos_os_filepaths())


@app.get("/video/<video_id>/path")
def get_video_path_by_id(video_id):
    video_instance = db_service.get_video_by_id(video_id)

    if video_instance is None:
        abort(404)

    return video_instance.OS_filepath


@app.get("/video/<video_id>/frames/path")
def get_video_frame_paths(video_id):
    video_instance = db_service.get_video_by_id(video_id)

    if video_instance is None:
        abort(404)

    return [frame.OS_filepath for frame in video_instance.frames]


@app.get("/video/<video_id>/frames/<frame_index>/path")
def get_video_frame_path_by_index(video_id, frame_index):
    frame_instance = db_service.get_video_frame_at_index(video_id, frame_index)

    if frame_instance is None:
        abort(404)

    return frame_instance.OS_filepath


@app.get("/video/<video_id>/download")
def download_video(video_id):
    video_instance = db_service.get_video_by_id(video_id)

    if video_instance is None:
        abort(404)

    video_file = minio_client.get_object(minio_bucket_name, video_instance.OS_filepath)
    video_name = os.path.basename(video_instance.OS_filepath)

    return send_file(video_file, download_name=video_name, as_attachment=True)


@app.get("/video/<video_id>/download_threat_frames")
def download_threat_frames(video_id):
    frames = db_service.get_video_frames(video_id)

    if len(frames) == 0:
        abort(404)

    threat_frames_zip = BytesIO()

    with zipfile.ZipFile(threat_frames_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for frame in frames:
            frame_object = minio_client.get_object(minio_bucket_name, frame.OS_filepath)
            zf.writestr(os.path.basename(frame.OS_filepath), frame_object.read())

    threat_frames_zip.seek(0)
    zip_file_name = "threat_frames.zip"

    return send_file(threat_frames_zip, mimetype="application/zip", download_name=zip_file_name, as_attachment=True)


if __name__ == '__main__':
    app.run(threaded=True, debug=True)
