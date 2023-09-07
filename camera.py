import cv2

class Camera:
    def __init__(self, camera_id, w=640, h=480, fps=25):
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        
        
    def get_frame(self):
        success, frame = self.cap.read()
        if not success:
            return None
        ret, buffer = cv2.imencode('.jpg', frame)
        return buffer.tobytes()
