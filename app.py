import os
import cv2
import time
import logging
import zipfile
from io import BytesIO
from minio import Minio
from flask import Flask, request, jsonify, abort, send_file
from models import Video, FrameMetadata, Frame, session
from given_functions import is_frame_tagged, generate_metadata
from multiprocessing import Pool

app = Flask(__name__)

minio_client = Minio('localhost:9000', access_key='s3manager', secret_key='s3manager', secure=False)
minio_bucket_name = 'bionic'

logging.basicConfig(level=logging.INFO)


def save_frame_metadata(frame):
    is_threat = is_frame_tagged(frame)
    fov, azimuth, elevation = generate_metadata(frame)
    frame_metadata = FrameMetadata(is_threat=is_threat, fov=fov, azimuth=azimuth, elevation=elevation)
    session.add(frame_metadata)
    session.commit()

    return frame_metadata


def save_video(video_path, video_filename):
    observation_post_name = video_filename.split("_")[0]
    video_os_filepath = f'/videos/{video_filename}'
    minio_client.fput_object(minio_bucket_name, video_os_filepath, video_path)
    video_instance = Video(observation_post_name=observation_post_name, OS_filepath=video_os_filepath, frame_count=5)
    session.add(video_instance)
    session.commit()

    return video_instance


def save_frame(frame, curr_frame_index, video_instance, video_name):
    frame_metadata = save_frame_metadata(frame)

    frame_os_filepath = f'/frames/{video_name}/frame_{curr_frame_index}.jpg'
    _, jpeg_frame = cv2.imencode('.jpg', frame)
    image_bytes = BytesIO(jpeg_frame)
    minio_client.put_object(minio_bucket_name, frame_os_filepath,
                            image_bytes,
                            len(jpeg_frame))

    frame_db_instance = Frame(video_id=video_instance.id, metadata_id=frame_metadata.id,
                              OS_filepath=frame_os_filepath,
                              frame_index=curr_frame_index)
    session.add(frame_db_instance)

    return frame_db_instance


@app.post("/video")
def upload_video_from_local_path():
    start_time = time.perf_counter()

    video_path = request.json['path']
    logging.info(f'Uploading video from local path: "{video_path}"')
    video_name = os.path.basename(video_path)
    video_instance = save_video(video_path, video_name)
    video = cv2.VideoCapture(video_path)
    curr_frame_index = 0

    with Pool(20) as thread_pool:
        while True:
            ret, frame = video.read()

            if ret:
                thread_pool.apply_async(save_frame, (frame, curr_frame_index, video_instance, video_name))
                curr_frame_index += 1
            else:
                break

    video.release()
    video_instance.frame_count = curr_frame_index - 1
    session.commit()

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    logging.info(f'Uploaded video in {elapsed_time:.2f} seconds. Saved {curr_frame_index} frames')

    return 'Success'


@app.get("/video/paths")
def get_videos_os_filepaths():
    paths_as_tuples = session.query(Video.OS_filepath).all()
    paths = [path_tuple[0] for path_tuple in paths_as_tuples]

    return jsonify(paths)


@app.get("/video/<video_id>/path")
def get_video_path_by_id(video_id):
    video_instance = session.query(Video).get(video_id)

    if video_instance is None:
        abort(404)

    return video_instance.OS_filepath


@app.get("/video/<video_id>/frames/path")
def get_video_frame_paths(video_id):
    video_instance = session.query(Video).get(video_id)

    if video_instance is None:
        abort(404)

    return [frame.OS_filepath for frame in video_instance.frames]


@app.get("/video/<video_id>/frames/<frame_index>/path")
def get_video_frame_path_by_index(video_id, frame_index):
    frame_instance = session.query(Frame).filter(Frame.video_id == video_id, Frame.frame_index == frame_index).first()

    if frame_instance is None:
        abort(404)

    return frame_instance.OS_filepath


@app.get("/video/<video_id>/download")
def download_video(video_id):
    video_instance = session.query(Video).get(video_id)

    if video_instance is None:
        abort(404)

    video_file = minio_client.get_object('bionic', video_instance.OS_filepath)
    video_name = os.path.basename(video_instance.OS_filepath)

    return send_file(video_file, download_name=video_name, as_attachment=True)


@app.get("/video/<video_id>/download_threat_frames")
def download_threat_frames(video_id):
    frames = session.query(Frame).filter(Frame.video_id == video_id,
                                         Frame.frame_metadata.has(FrameMetadata.is_threat)).all()

    if len(frames) == 0:
        abort(404)

    mem_zip = BytesIO()

    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for frame in frames:
            frame_object = minio_client.get_object('bionic', frame.OS_filepath)
            zf.writestr(os.path.basename(frame.OS_filepath), frame_object.read())

    mem_zip.seek(0)
    zip_file_name = "threat_frames.zip"

    return send_file(mem_zip, mimetype="application/zip", download_name=zip_file_name, as_attachment=True)


@app.get("/")
def hello_world():
    return "App is running"


if __name__ == '__main__':
    app.run(threaded=True, debug=True)
