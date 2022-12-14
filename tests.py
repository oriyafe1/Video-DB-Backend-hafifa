import cv2
import pytest
from models import Video, FrameMetadata, Frame, session
from app import app, save_video, save_frame_metadata, save_frame


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client


def test_upload_video_from_local_path(client):
    response = client.post('/video', json={'path': 'test_video.mp4'})
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'Success'

    video = session.query(Video).first()
    assert video is not None
    assert video.observation_post_name == 'test'
    assert video.OS_filepath == f'/videos/{video.id}_test_video.mp4'
    assert video.frame_count == 466


def test_save_video(client):
    video_path = 'test_video.mp4'
    video_filename = 'test_video.mp4'
    video = save_video(video_path, video_filename)

    assert video is not None
    assert video.observation_post_name == 'test'


def test_save_frame_metadata():
    frame = cv2.imread('test_frame.jpg')
    metadata = save_frame_metadata(frame)

    assert metadata is not None
    assert metadata.is_threat is not None
    assert metadata.fov is not None
    assert metadata.azimuth is not None
    assert metadata.elevation is not None


def test_save_frame(client):
    video_instance = Video(observation_post_name='test', OS_filepath='/videos/test_video.mp4', frame_count=5)
    session.add(video_instance)
    session.commit()
    cv_frame = cv2.imread('test_frame.jpg')
    frame_instance = save_frame(cv_frame, 0, video_instance, 'test_video.mp4')
    session.commit()

    saved_frame = session.query(Frame).get(frame_instance.id)
    assert saved_frame is not None
    assert saved_frame.OS_filepath == f'/frames/{video_instance.id}_test_video.mp4/frame_0.jpg'
    assert saved_frame.video_id == video_instance.id
    assert saved_frame.frame_index == 0
