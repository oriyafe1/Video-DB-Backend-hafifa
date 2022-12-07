import sys

from given_functions import is_frame_tagged, generate_metadata
from models import Video, Metadata, Frame, session
from flask import Flask, request
from minio import Minio
from io import BytesIO
import cv2
import os

app = Flask(__name__)

minio_client = Minio('localhost:9000', access_key='s3manager', secret_key='s3manager', secure=False)
minio_bucket_name = 'bionic'


def save_frame_metadata(frame):
    is_threat = is_frame_tagged(frame)
    fov, azimuth, elevation = generate_metadata(frame)
    frame_metadata = Metadata(is_threat=is_threat, fov=fov, azimuth=azimuth, elevation=elevation)
    session.add(frame_metadata)

    return frame_metadata


def save_video(video_path, video_filename):
    observation_post_name = video_filename.split("_")[0]
    video_os_filepath = f'/videos/{video_filename}'
    minio_client.fput_object(minio_bucket_name, video_os_filepath, video_path)
    video_instance = Video(observation_post_name=observation_post_name, OS_filepath=video_os_filepath, frame_count=5)
    session.add(video_instance)

    return video_instance


def save_frame(frame, curr_frame_index, video_instance, video_name, frame_metadata):
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


@app.post("/video")
def upload_video_from_local_path():
    video_path = request.json['path']
    video_name = os.path.basename(video_path)
    video_instance = save_video(video_path, video_name)
    video = cv2.VideoCapture(video_path)
    curr_frame_index = 0

    while True:
        ret, frame = video.read()

        if ret:
            frame_metadata = save_frame_metadata(frame)
            save_frame(frame, curr_frame_index, video_name, video_instance, frame_metadata)
            curr_frame_index += 1
        else:
            break

    video.release()

    session.commit()

    return 'Success'


@app.route("/")
def hello_world():
    print('pipi kaki')
    return "App is running"


app.run()
