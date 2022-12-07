from given_functions import is_frame_tagged, generate_metadata
from models import Video, Metadata, Frame, session
from flask import Flask, request
from minio import Minio
import cv2
import os

app = Flask(__name__)

minio_client = Minio('localhost:9000', access_key='s3manager', secret_key='s3manager', secure=False)
minio_bucket_name = 'bionic'


def get_frame_metadata(frame):
    is_threat = is_frame_tagged(frame)
    fov, azimuth, elevation = generate_metadata(frame)

    return Metadata(is_threat=is_threat, fov=fov, azimuth=azimuth, elevation=elevation)


def save_video(video_path):
    video_filename = os.path.basename(video_path)
    observation_post_name = video_filename.split("_")[0]
    video_os_filepath = f'/videos/{video_filename}'
    minio_client.fput_object(minio_bucket_name, video_os_filepath, video_path)
    video_instance = Video(observation_post_name=observation_post_name, OS_filepath=video_os_filepath, frame_count=5)
    session.add(video_instance)

    return video_instance


@app.post("/video")
def upload_video_from_local_path():
    video_path = request.json['path']

    video_instance = save_video(video_path)

    video = cv2.VideoCapture(video_path)
    curr_frame_index = 0

    while True:
        ret, frame = video.read()

        if ret:
            curr_frame_metadata = get_frame_metadata(frame)
            session.add(curr_frame_metadata)
            frame_db_instance = Frame(video_id=video_instance.id, metadata_id=curr_frame_metadata.id,
                                      OS_filepath='test',
                                      frame_index=curr_frame_index)
            session.add(frame_db_instance)
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
