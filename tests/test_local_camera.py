import modules.opencv_stream as opencv_stream
from unittest.mock import patch


def test_local_camera_windows_backend():
    with patch.object(opencv_stream.BaseCameraStream, "__init__", return_value=None), \
         patch.object(opencv_stream.platform, "system", return_value="Windows"), \
         patch.object(opencv_stream.cv2, "VideoCapture") as mock_capture:
        mock_capture.return_value.isOpened.return_value = True
        stream = opencv_stream.OpenCVCameraStream("0")
        stream.buffer_size = 3
        stream._init_stream()
        mock_capture.assert_called_once_with(0, opencv_stream.cv2.CAP_DSHOW)

